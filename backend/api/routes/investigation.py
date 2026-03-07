"""
Investigation Routes
====================

Routes for starting and managing forensic investigations.
"""

import asyncio
import os
import re
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Form, Request
from fastapi.responses import JSONResponse

from core.auth import get_current_user, require_investigator, User

from api.routes.metrics import (
    increment_investigations_started,
    increment_investigations_completed,
    increment_investigations_failed,
)
from api.schemas import (
    AgentFindingDTO,
    BriefUpdate,
    InvestigationRequest,
    InvestigationResponse,
    ReportDTO,
)
from core.config import get_settings
from core.logging import get_logger
from orchestration.pipeline import ForensicCouncilPipeline, AgentLoopResult
from orchestration.session_manager import SessionManager

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/v1", tags=["investigation"])

# Store active pipelines, WebSocket connections, background tasks, and cached reports
_active_pipelines: dict[str, ForensicCouncilPipeline] = {}
_websocket_connections: dict[str, list] = {}
_active_tasks: dict[str, asyncio.Task] = {}
_final_reports: dict[str, tuple[Any, datetime]] = {}

# Agent IDs in execution order
_AGENT_IDS = ["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"]
_AGENT_NAMES = {
    "Agent1": "Image Forensics",
    "Agent2": "Audio Forensics",
    "Agent3": "Object Detection",
    "Agent4": "Video Forensics",
    "Agent5": "Metadata Forensics",
}


def cleanup_connections():
    """Clean up all WebSocket connections, tasks, and active pipelines on shutdown."""
    for task in _active_tasks.values():
        task.cancel()
    _active_tasks.clear()
    _websocket_connections.clear()
# Expose accessors instead of direct private attribute access
def get_active_pipelines_count() -> int:
    return len(_active_pipelines)

def get_active_pipeline(session_id: str) -> Optional[ForensicCouncilPipeline]:
    return _active_pipelines.get(session_id)

def get_all_active_pipelines() -> dict:
    return _active_pipelines.copy()

def remove_active_pipeline(session_id: str):
    _active_pipelines.pop(session_id, None)

def clear_active_pipelines():
    _active_pipelines.clear()
    _final_reports.clear()  # Prevent memory leak

# Allowed MIME types - includes common forensic evidence formats
ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
    "video/mp4",
    "video/quicktime",  # .mov (iPhone)
    "video/x-msvideo",  # .avi
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",       # .mp3
    "audio/mp4",        # .m4a (iPhone)
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


async def broadcast_update(session_id: str, update: BriefUpdate):
    """Broadcast a WebSocket update to all connected clients."""
    if session_id in _websocket_connections:
        for ws in _websocket_connections[session_id]:
            try:
                await ws.send_json(update.model_dump())
            except Exception as e:
                logger.warning(f"Failed to send WebSocket message: {e}")


async def _wrap_pipeline_with_broadcasts(
    pipeline: ForensicCouncilPipeline,
    session_id: str,
    evidence_file_path: str,
    case_id: str,
    investigator_id: str,
):
    """
    Wrap the pipeline execution to broadcast per-agent WebSocket updates.
    
    Runs agents SEQUENTIALLY so the frontend can display each agent
    one at a time as they complete.
    """
    original_run = pipeline._run_agents_concurrent
    ws_session_id = session_id  # capture for closure

    # --- Hook custody logger to broadcast THOUGHTs ---
    def instrument_logger(logger_obj):
        original_log_entry = logger_obj.log_entry

        async def instrumented_log_entry(**kwargs):
            result = await original_log_entry(**kwargs)

            entry_type = kwargs.get('entry_type')
            content = kwargs.get('content', {})
            agent_id = kwargs.get('agent_id')

            # EntryType is usually an enum, but sometimes a string values depending on monkey-patch state
            type_val = getattr(entry_type, "value", str(entry_type))

            if type_val in ("THOUGHT", "ACTION") and isinstance(content, dict):
                # Skip session_start entries
                if content.get("action") == "session_start":
                    return result

                agent_name = _AGENT_NAMES.get(agent_id, agent_id)

                # For ACTION entries, show the tool name being called
                if type_val == "ACTION" and content.get("tool_name"):
                    tool_label = content["tool_name"].replace("_", " ").title()
                    thinking_text = f"Calling {tool_label}..."
                else:
                    thinking_text = content.get("text", "Analyzing...")

                await broadcast_update(
                    ws_session_id,
                    BriefUpdate(
                        type="AGENT_UPDATE",
                        session_id=ws_session_id,
                        agent_id=agent_id,
                        agent_name=agent_name,
                        message=f"{agent_name} is analyzing...",
                        data={"status": "running", "thinking": thinking_text},
                    )
                )
            return result

        logger_obj.log_entry = instrumented_log_entry

    if pipeline.custody_logger:
        instrument_logger(pipeline.custody_logger)
    # -----------------------------------------------

    async def instrumented_run(evidence_artifact, session_id=None):
        """Run each agent SEQUENTIALLY, broadcasting updates."""
        # --- MIME TYPE SKIP LOGIC ---
        mime = evidence_artifact.metadata.get("mime_type", "application/octet-stream")
        _AGENT_MIME_SUPPORT = {
            "Agent1": {"image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp", "image/tiff"},
            "Agent2": {"audio/wav", "audio/mpeg", "audio/flac", "video/mp4", "video/x-msvideo", "video/quicktime"},
            "Agent3": {"image/jpeg", "image/png", "video/mp4", "video/x-msvideo", "video/quicktime"},
            "Agent4": {"video/mp4", "video/x-msvideo", "video/quicktime"},
            "Agent5": {"image/jpeg", "image/png", "image/tiff", "video/mp4", "audio/wav", "audio/mpeg"},
        }

        # Import agent classes here to instantiate individually
        from agents.agent1_image import Agent1Image
        from agents.agent2_audio import Agent2Audio
        from agents.agent3_object import Agent3Object
        from agents.agent4_video import Agent4Video
        from agents.agent5_metadata import Agent5Metadata

        agent_configs = [
            ("Agent1", "Image Forensics", Agent1Image, "Scanning for steganographic patterns and lighting inconsistencies..."),
            ("Agent2", "Audio Forensics", Agent2Audio, "Analyzing spectral signatures and identifying synthesized voice segments..."),
            ("Agent3", "Object Detection", Agent3Object, "Detecting forensic anomalies and classifying segmented objects..."),
            ("Agent4", "Video Forensics", Agent4Video, "Performing frame-by-frame temporal consistency and motion vector analysis..."),
            ("Agent5", "Metadata Forensics", Agent5Metadata, "Extracting EXIF data and verifying file header integrity..."),
        ]

        results = []

        async def run_single_agent(agent_id, agent_name, AgentClass, thinking_phrase):
            # Check MIME compatibility
            supported_mimes = _AGENT_MIME_SUPPORT.get(agent_id, set())
            if mime not in supported_mimes:
                msg = f"Skipping unsupported file type: {mime}"
                # Brief update to show identifying process before skipping
                await broadcast_update(
                    ws_session_id,
                    BriefUpdate(
                        type="AGENT_UPDATE",
                        session_id=ws_session_id,
                        agent_id=agent_id,
                        agent_name=agent_name,
                        message=f"{agent_name} is checking file compatibility...",
                        data={"status": "running", "thinking": f"Identifying file format: {mime}"},
                    )
                )
                
                # Signal completion immediately for unsupported types to save time
                await broadcast_update(
                    ws_session_id,
                    BriefUpdate(
                        type="AGENT_COMPLETE",
                        session_id=ws_session_id,
                        agent_id=agent_id,
                        agent_name=agent_name,
                        message=f"Forensic Analysis Skipped: {agent_name} does not support {mime} files.",
                        data={
                            "status": "complete",
                            "confidence": 1.0,
                            "findings_count": 0,
                            "error": None,
                        },
                    )
                )
                return AgentLoopResult(
                    agent_id=agent_id,
                    findings=[{"finding_type": "Format not supported", "confidence_raw": 1.0, "status": "CONFIRMED", "reasoning_summary": f"This agent does not support analyzing {mime} files.", "agent_name": agent_name}],
                    reflection_report={},
                    react_chain=[],
                )

            # --- AGENT_UPDATE: agent is starting ---
            await broadcast_update(
                ws_session_id,
                BriefUpdate(
                    type="AGENT_UPDATE",
                    session_id=ws_session_id,
                    agent_id=agent_id,
                    agent_name=agent_name,
                    message=f"{agent_name} is analyzing evidence...",
                    data={"status": "running", "thinking": thinking_phrase},
                )
            )

            # --- Run the single agent ---
            try:
                agent_kwargs = {
                    "agent_id": agent_id,
                    "session_id": session_id or evidence_artifact.artifact_id,
                    "evidence_artifact": evidence_artifact,
                    "config": pipeline.config,
                    "working_memory": pipeline.working_memory,
                    "episodic_memory": pipeline.episodic_memory,
                    "custody_logger": pipeline.custody_logger,
                    "evidence_store": pipeline.evidence_store,
                }
                if agent_id in ("Agent2", "Agent3", "Agent4"):
                    agent_kwargs["inter_agent_bus"] = pipeline.inter_agent_bus
                agent = AgentClass(**agent_kwargs)
                
                findings = await asyncio.wait_for(
                    agent.run_investigation(),
                    timeout=pipeline.config.investigation_timeout
                )
                
                # --- FORMATTING ENFORCEMENT ---
                # Keep individual findings intact so the frontend can display
                # each one separately.  Only override for unsupported formats.
                is_unsupported = any(getattr(f, 'finding_type', '') == "Format not supported" for f in findings)

                if is_unsupported:
                    base_name = evidence_artifact.metadata.get("original_filename", os.path.basename(evidence_file_path))
                    clean_text = (
                        f"{agent_name} cannot analyse this file type ({mime}). "
                        f"No findings were produced for {base_name}."
                    )
                    for f in findings:
                        f.reasoning_summary = clean_text
                # For supported formats, each finding already has a clean
                # reasoning_summary from _build_readable_summary — leave them
                # as-is so per_agent_findings keeps every individual result.
                # ------------------------------

                # Make sure react step models are serialized back to dicts 
                serialized_chain = []
                for step in getattr(agent, '_react_chain', []):
                    if hasattr(step, "model_dump"):
                        serialized_chain.append(step.model_dump(mode="json"))
                    elif hasattr(step, "dict"):
                        serialized_chain.append(step.dict())
                    else:
                        serialized_chain.append(step)
                        
                result = AgentLoopResult(
                    agent_id=agent_id,
                    findings=[f.model_dump(mode="json") for f in findings],
                    reflection_report=getattr(agent, '_reflection_report', None).model_dump(mode="json") if getattr(agent, '_reflection_report', None) else {},
                    react_chain=serialized_chain,
                )
            except Exception as e:
                logger.error(f"{agent_id} failed", error=str(e))
                result = AgentLoopResult(
                    agent_id=agent_id, findings=[], reflection_report={},
                    react_chain=[], error=str(e),
                )

            # --- Build finding summary for WS message ---
            confidence = 0.0
            finding_summary = f"{agent_name} completed analysis."
            if result.findings:
                confidences = [
                    f.get("confidence_raw", 0.5) if isinstance(f, dict) else 0.5
                    for f in result.findings
                ]
                confidence = sum(confidences) / len(confidences) if confidences else 0.5
                # Collect ALL finding summaries so the frontend can show complete results
                finding_summaries = []
                for f in result.findings:
                    if isinstance(f, dict) and f.get("reasoning_summary"):
                        finding_summaries.append(f["reasoning_summary"])
                if finding_summaries:
                    finding_summary = "\n\n".join(finding_summaries)
            elif result.error:
                finding_summary = f"{agent_name}: {result.error[:100]}"

            # --- AGENT_COMPLETE: agent finished ---
            await broadcast_update(
                ws_session_id,
                BriefUpdate(
                    type="AGENT_COMPLETE",
                    session_id=ws_session_id,
                    agent_id=agent_id,
                    agent_name=agent_name,
                    message=finding_summary,
                    data={
                        "status": "complete",
                        "confidence": confidence,
                        "findings_count": len(result.findings),
                        "error": result.error,
                    },
                )
            )
            return result

        # Run each agent with a staggered start to ensure sequential activation in the UI
        async def run_with_stagger(index, agent_id, agent_name, AgentClass, thinking_phrase):
            # 0s, 1.5s, 3.0s, 4.5s, 6.0s delays
            await asyncio.sleep(index * 1.5)
            return await run_single_agent(agent_id, agent_name, AgentClass, thinking_phrase)

        tasks = [
            run_with_stagger(i, agent_id, agent_name, AgentClass, thinking_phrase)
            for i, (agent_id, agent_name, AgentClass, thinking_phrase) in enumerate(agent_configs)
        ]
        results = await asyncio.gather(*tasks)

        return results

    pipeline._run_agents_concurrent = instrumented_run

    # Now run the full investigation
    return await pipeline.run_investigation(
        evidence_file_path=evidence_file_path,
        case_id=case_id,
        investigator_id=investigator_id,
    )


async def run_investigation_task(
    session_id: str,
    pipeline: ForensicCouncilPipeline,  # R1 FIX: Accept pre-created pipeline
    evidence_file_path: str,
    case_id: str,
    investigator_id: str,
):
    """Background task to run the investigation with timeout protection."""
    # R1 FIX: Pipeline already registered in _active_pipelines by caller
    error_msg = None

    try:
        # Wait for the WebSocket client to connect before broadcasting.
        # The frontend connects immediately after receiving session_id, but the
        # TCP handshake + AUTH exchange takes ~100-500 ms.  We poll until at
        # least one WS is registered (up to 5 s) so no early broadcasts are lost.
        for _ws_wait in range(50):   # 50 × 0.1 s = 5 s max
            if session_id in _websocket_connections and _websocket_connections[session_id]:
                break
            await asyncio.sleep(0.1)

        # Send initial update
        await broadcast_update(
            session_id,
            BriefUpdate(
                type="AGENT_UPDATE",
                session_id=session_id,
                message="Activating Forensic Council...",
                data={"status": "starting", "thinking": "Initializing specialist agent subsystems..."},
            )
        )

        # E2: Run with timeout protection
        timeout = settings.investigation_timeout
        report = await asyncio.wait_for(
            _wrap_pipeline_with_broadcasts(
                pipeline=pipeline,
                session_id=session_id,
                evidence_file_path=evidence_file_path,
                case_id=case_id,
                investigator_id=investigator_id,
            ),
            timeout=float(timeout),
        )

        # Send deliberation update before full completion
        await broadcast_update(
            session_id,
            BriefUpdate(
                type="AGENT_UPDATE",
                session_id=session_id,
                agent_id="Arbiter",
                agent_name="Council Arbiter",
                message="Council Arbiter is deliberating findings...",
                data={"status": "deliberating", "thinking": "Synthesizing agent results and resolving contradictions..."},
            )
        )
        await asyncio.sleep(0.1)

        # Send pipeline completion update
        await broadcast_update(
            session_id,
            BriefUpdate(
                type="PIPELINE_COMPLETE",
                session_id=session_id,
                message="Forensic investigation concluded.",
                data={"report_id": str(report.report_id)},
            )
        )

        # Store the report for retrieval
        pipeline._final_report = report
        
        # Track successful completion
        increment_investigations_completed()

    except asyncio.TimeoutError:
        error_msg = f"Investigation timed out after {settings.investigation_timeout}s"
        logger.error(error_msg, session_id=session_id)
        increment_investigations_failed()
        await broadcast_update(
            session_id,
            BriefUpdate(
                type="ERROR",
                session_id=session_id,
                message=error_msg,
                data={"error": error_msg},
            )
        )
    except Exception as e:
        error_msg = str(e)
        # E1: Log with full traceback
        logger.error(f"Investigation failed: {e}", exc_info=True)
        increment_investigations_failed()
        await broadcast_update(
            session_id,
            BriefUpdate(
                type="ERROR",
                session_id=session_id,
                message=f"Investigation failed: {error_msg}",
                data={"error": error_msg},
            )
        )
    finally:
        # E1: Store error on pipeline so get_report can surface it
        if error_msg:
            pipeline._error = error_msg
        # Clean up temp evidence file
        try:
            if os.path.exists(evidence_file_path):
                os.unlink(evidence_file_path)
        except Exception:
            pass
        # Remove task from tracking
        _active_tasks.pop(session_id, None)
        # Wait minimally for frontend to process the final WS messages before closing connections.
        await asyncio.sleep(0.5)
        
        # Free memory and cache report if generated
        report = getattr(pipeline, "_final_report", None)
        if report:
             _final_reports[session_id] = (report, datetime.now(timezone.utc))
        
        remove_active_pipeline(session_id)
        
        # Close WebSocket connections
        if session_id in _websocket_connections:
            for ws in _websocket_connections[session_id]:
                try:
                    await ws.close()
                except Exception as e:
                    logger.error(f"Failed to close WebSocket connection: {e}", exc_info=True)
            _websocket_connections.pop(session_id, None)

def validate_case_id(case_id: str) -> bool:
    """Validate case ID format - CASE-<timestamp> or CASE-<uuid>"""
    if not case_id.startswith("CASE-"):
        return False
    remainder = case_id[5:]
    
    # Try UUID validation
    try:
        UUID(remainder)
        return True
    except ValueError:
        pass
    
    # Try timestamp format (10-14 digits)
    return remainder.isdigit() and 10 <= len(remainder) <= 14

def validate_investigator_id(investigator_id: str) -> bool:
    """Validate investigator ID format - REQ-<5-10 digits>"""
    if not investigator_id.startswith("REQ-"):
        return False
    remainder = investigator_id[4:]
    return remainder.isdigit() and 5 <= len(remainder) <= 10



@router.post("/investigate", response_model=InvestigationResponse)
async def investigate(
    request: Request,
    file: UploadFile = File(...),
    case_id: str = Form(...),
    investigator_id: str = Form(...),
    current_user: User = Depends(get_current_user),
):
    """
    Start a forensic investigation on uploaded evidence.
    
    SEC 2 & SEC 3: Implements rate limiting and strict input validation.
    """
    # 1. Input Validation (SEC 3)
    if not validate_case_id(case_id):
        raise HTTPException(status_code=400, detail="Invalid case_id format. Expected CASE-<timestamp> or CASE-<uuid>.")
    
    if not validate_investigator_id(investigator_id):
        raise HTTPException(status_code=400, detail="Invalid investigator_id format. Expected REQ-<5-10 digits>.")

    # 2. Rate Limiting (SEC 2) - Uses shared Redis singleton to avoid per-request TCP connection overhead
    try:
        from infra.redis_client import get_redis_client
        redis = await get_redis_client()
        rate_limit_key = f"rate_limit:upload:{investigator_id}"
        
        rate_limit_script = """
        local key = KEYS[1]
        local limit = tonumber(ARGV[1])
        local ttl = tonumber(ARGV[2])

        local count = redis.call('GET', key)
        if count == false then
            redis.call('SET', key, 1, 'EX', ttl)
            return {0, ttl}
        end

        count = tonumber(count)
        if count >= limit then
            local remaining = redis.call('TTL', key)
            return {1, remaining}
        end

        redis.call('INCR', key)
        return {0, ttl}
        """
        
        result = await redis.client.eval(rate_limit_script, 1, rate_limit_key, 5, 600)
        
        if result[0] == 1:
            raise HTTPException(
                status_code=429, 
                detail=f"Rate limit exceeded. Please wait {result[1]} seconds.",
                headers={"Retry-After": str(result[1])}
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Rate limiter unavailable, proceeding without limit", error=str(e))

    # 3. File Size Validation
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE // (1024 * 1024)
        actual_mb = round(int(content_length) / (1024 * 1024), 2)
        raise HTTPException(
            status_code=413,
            detail=(
                f"File size ({actual_mb}MB) exceeds maximum ({max_mb}MB). "
                f"Please compress or split your evidence file and try again."
            )
        )

    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE // (1024 * 1024)
        actual_mb = round(file_size / (1024 * 1024), 2)
        raise HTTPException(
            status_code=413,
            detail=(
                f"File size ({actual_mb}MB) exceeds maximum ({max_mb}MB). "
                f"Please compress or split your evidence file and try again."
            )
        )

    # 4. MIME type validation
    # Use python-magic for byte-level detection (most reliable).
    # Falls back to file-extension → declared content-type mapping when libmagic
    # is not available, so a missing system library never causes a bare 500.
    content = await file.read()

    _EXT_MIME_MAP: dict[str, str] = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".tif": "image/tiff", ".tiff": "image/tiff",
        ".webp": "image/webp", ".mp4": "video/mp4", ".mov": "video/quicktime",
        ".avi": "video/x-msvideo", ".wav": "audio/wav", ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
    }

    def get_actual_mime_type(file_bytes: bytes, fallback_ext: str) -> str:
        # Try libmagic first (byte-level, most accurate)
        try:
            import magic  # python-magic package
            return magic.from_buffer(file_bytes[:2048], mime=True)
        except Exception:
            pass
        # Fallback: derive from sanitised file extension
        return _EXT_MIME_MAP.get(fallback_ext.lower(), "")

    actual_mime = await asyncio.to_thread(get_actual_mime_type, content, Path(file.filename or "").suffix)
    if actual_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unsupported file type '{actual_mime}'. "
                f"Allowed types: JPEG, PNG, TIFF, WebP, MP4, MOV, AVI, WAV, MP3, M4A."
            )
        )

    # Create session ID
    session_id = str(uuid4())
    
    # Track investigation started
    increment_investigations_started()

    # S6: Sanitize uploaded filename extension
    raw_ext = Path(file.filename or "").suffix
    safe_ext = re.sub(r'[^a-zA-Z0-9.]', '', raw_ext) or ".bin"

    # BUG-290 FIX: evidence_file_path is now created INSIDE the try block so that
    # any OS-level failures (permissions, tmpfs limits, etc.) are properly caught
    # and returned as a meaningful HTTP error instead of a bare 500 from the
    # global exception handler.
    evidence_file_path: Optional[str] = None

    try:
        # Write content to temp file (must be inside try so cleanup works on error)
        def write_temp_file(data: bytes, ext: str) -> str:
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
                tmp_file.write(data)
                return tmp_file.name

        evidence_file_path = await asyncio.to_thread(write_temp_file, content, safe_ext)

        # R2: Track background task for graceful shutdown
        # R1 FIX: Register pipeline BEFORE creating task to avoid WebSocket race condition
        pipeline = ForensicCouncilPipeline()
        _active_pipelines[session_id] = pipeline
        
        task = asyncio.create_task(
            run_investigation_task(
                session_id=session_id,
                pipeline=pipeline,               # Pass pre-created pipeline
                evidence_file_path=evidence_file_path,
                case_id=case_id,
                investigator_id=investigator_id,
            )
        )
        _active_tasks[session_id] = task

        return InvestigationResponse(
            session_id=session_id,
            case_id=case_id,
            status="started",
            message="Investigation started successfully"
        )

    except Exception as e:
        logger.error("Failed to start investigation", error=str(e), exc_info=True)
        # Clean up temp file on error
        if evidence_file_path and os.path.exists(evidence_file_path):
            os.remove(evidence_file_path)
        raise HTTPException(status_code=500, detail=str(e))


def _finding_to_dto(f: dict, fallback_agent_id: str = "") -> AgentFindingDTO:
    """Convert a raw finding dict to AgentFindingDTO."""
    return AgentFindingDTO(
        finding_id=str(f.get("finding_id", "")),
        agent_id=f.get("agent_id", fallback_agent_id),
        agent_name=f.get("agent_name", fallback_agent_id),
        finding_type=f.get("finding_type", "unknown"),
        status=f.get("status", "unknown"),
        confidence_raw=f.get("confidence_raw", 0.0),
        calibrated=f.get("calibrated", False),
        calibrated_probability=f.get("calibrated_probability"),
        court_statement=f.get("court_statement"),
        robustness_caveat=f.get("robustness_caveat", False),
        robustness_caveat_detail=f.get("robustness_caveat_detail"),
        reasoning_summary=f.get("reasoning_summary", ""),
    )


@router.get("/sessions/{session_id}/report")
async def get_report(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get the report for a completed investigation."""
    
    report = None
    
    entry = _final_reports.get(session_id)
    if entry:
        report_data, stored_at = entry
        if datetime.now(timezone.utc) - stored_at > timedelta(hours=1):
            del _final_reports[session_id]
            raise HTTPException(status_code=404, detail="Report expired")
        report = report_data
    elif get_active_pipeline(session_id):
        pipeline = get_active_pipeline(session_id)
        
        # E1: Surface pipeline errors to the client
        if hasattr(pipeline, "_error") and pipeline._error:
            return JSONResponse(
                status_code=500,
                content={"status": "failed", "message": pipeline._error}
            )
            
        # Check if investigation is still running
        if hasattr(pipeline, "_final_report"):
             report = pipeline._final_report
        else:
            return JSONResponse(
                status_code=202,
                content={"status": "in_progress", "message": "Investigation still running"}
            )
    else:
        raise HTTPException(status_code=404, detail="Session not found")

    # If we fall through and have a report, generate the DTO

    # Convert to DTOs using the helper
    per_agent_findings = {
        agent_id: [_finding_to_dto(f, agent_id) for f in findings]
        for agent_id, findings in report.per_agent_findings.items()
    }

    return ReportDTO(
        report_id=str(report.report_id),
        session_id=session_id,
        case_id=report.case_id,
        executive_summary=report.executive_summary,
        per_agent_findings=per_agent_findings,
        cross_modal_confirmed=[_finding_to_dto(f) for f in report.cross_modal_confirmed],
        contested_findings=[f.model_dump() if hasattr(f, 'model_dump') else f for f in report.contested_findings],
        tribunal_resolved=[t.model_dump() if hasattr(t, 'model_dump') else t for t in report.tribunal_resolved],
        incomplete_findings=[_finding_to_dto(f) for f in report.incomplete_findings],
        uncertainty_statement=report.uncertainty_statement,
        cryptographic_signature=report.cryptographic_signature,
        report_hash=report.report_hash,
        signed_utc=report.signed_utc.isoformat() if hasattr(report.signed_utc, 'isoformat') else str(report.signed_utc),
    )


@router.get("/sessions/{session_id}/brief/{agent_id}")
async def get_brief(
    session_id: str,
    agent_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get the current investigator brief for an agent."""
    pipeline = get_active_pipeline(session_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get brief from session manager (not working memory — it doesn't have this method)
    try:
        brief = await pipeline.session_manager.get_investigator_brief(
            session_id=UUID(session_id),
            agent_id=agent_id,
        )
        if brief:
            return {"brief": brief}
    except Exception as e:
        logger.error("Failed to retrieve brief", session_id=session_id, agent_id=agent_id, error=str(e))

    return {"brief": "No brief available yet."}


@router.get("/sessions/{session_id}/checkpoints")
async def get_checkpoints(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get pending HITL checkpoints for a session."""
    pipeline = get_active_pipeline(session_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        checkpoints = await pipeline.session_manager.get_active_checkpoints(
            session_id=UUID(session_id),
        )
        return [
            {
                "checkpoint_id": str(cp.checkpoint_id),
                "session_id": str(cp.session_id),
                "agent_id": cp.agent_id,
                "agent_name": _AGENT_NAMES.get(cp.agent_id, cp.agent_id),
                "brief_text": cp.description,
                "decision_needed": cp.checkpoint_type,
                "created_at": cp.created_at.isoformat(),
            }
            for cp in checkpoints
        ]
    except Exception:
        return []


def register_websocket(session_id: str, websocket):
    """Register a WebSocket connection for a session."""
    if session_id not in _websocket_connections:
        _websocket_connections[session_id] = []
    _websocket_connections[session_id].append(websocket)


def unregister_websocket(session_id: str, websocket):
    """Unregister a WebSocket connection."""
    if session_id in _websocket_connections:
        if websocket in _websocket_connections[session_id]:
            _websocket_connections[session_id].remove(websocket)
