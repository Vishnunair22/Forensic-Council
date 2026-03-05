"""
Investigation Routes
====================

Routes for starting and managing forensic investigations.
"""

import asyncio
import os
import re
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Form
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
_final_reports: dict[str, Any] = {}

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

            if type_val == "THOUGHT" and isinstance(content, dict) and "text" in content:
                if content.get("action") != "session_start":
                    agent_name = _AGENT_NAMES.get(agent_id, agent_id)
                    await broadcast_update(
                        ws_session_id,
                        BriefUpdate(
                            type="AGENT_UPDATE",
                            session_id=ws_session_id,
                            agent_id=agent_id,
                            agent_name=agent_name,
                            message=f"{agent_name} is analyzing...",
                            data={"status": "running", "thinking": content["text"]},
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
                # Brief delay to show 'checking file format...' instead of instant completion
                unsupported_steps = [
                    f"Initializing {agent_name} subsystems...",
                    f"Inspecting file headers and MIME signature: {mime}",
                    f"Cross-referencing {mime} against supported forensic analysis modules...",
                ]
                for step in unsupported_steps:
                    await broadcast_update(
                        ws_session_id,
                        BriefUpdate(
                            type="AGENT_UPDATE",
                            session_id=ws_session_id,
                            agent_id=agent_id,
                            agent_name=agent_name,
                            message=f"{agent_name} is processing...",
                            data={"status": "running", "thinking": step},
                        )
                    )
                    await asyncio.sleep(1.2)
                await broadcast_update(
                    ws_session_id,
                    BriefUpdate(
                        type="AGENT_COMPLETE",
                        session_id=ws_session_id,
                        agent_id=agent_id,
                        agent_name=agent_name,
                        message=f"Format not supported ({mime})",
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
                agent = AgentClass(
                    agent_id=agent_id,
                    session_id=session_id or evidence_artifact.artifact_id,
                    evidence_artifact=evidence_artifact,
                    config=pipeline.config,
                    working_memory=pipeline.working_memory,
                    episodic_memory=pipeline.episodic_memory,
                    custody_logger=pipeline.custody_logger,
                    evidence_store=pipeline.evidence_store,
                    inter_agent_bus=pipeline.inter_agent_bus,
                )
                findings = await asyncio.wait_for(
                    agent.run_investigation(),
                    timeout=60.0
                )
                
                # --- FORMATTING ENFORCEMENT ---
                # Retrieve the original filename from metadata (fallback to os.path.basename if missing)
                base_name = evidence_artifact.metadata.get("original_filename", os.path.basename(evidence_file_path))
                prefix = f"The {agent_name} detected an {mime} file named {base_name}."
                
                is_unsupported = any(getattr(f, 'finding_type', '') == "Format not supported" for f in findings)
                
                if is_unsupported:
                    formatted_text = f"{prefix}\n{agent_name} can not analyse this file type so agent has no findings to show."
                    for f in findings:
                        f.reasoning_summary = formatted_text
                else:
                    confidences = [getattr(f, 'confidence_raw', 0.5) for f in findings]
                    avg_conf = sum(confidences) / len(confidences) if confidences else 0.5
                    
                    doc_type = "standard configuration file"
                    all_text = " ".join([getattr(f, 'reasoning_summary', '') for f in findings])
                    if "screenshot" in all_text.lower() or "text extracted" in all_text.lower():
                        doc_type = "screenshot"
                    elif "document" in all_text.lower():
                        doc_type = "document"
                    elif "portrait" in all_text.lower() or "face" in all_text.lower():
                        doc_type = "portrait photo"
                    elif mime.startswith("image/"):
                        doc_type = "image file"
                    elif mime.startswith("video/"):
                        doc_type = "video file"
                    elif mime.startswith("audio/"):
                        doc_type = "audio recording"
                        
                    middle_line = f"It appears to be a {doc_type}."
                    final_line = f"{int(avg_conf * 100)}% sure of result."
                    
                    # Deduplicate generic texts safely
                    unique_findings = []
                    for f in findings:
                        summary = getattr(f, 'reasoning_summary', '').strip()
                        if summary and summary not in unique_findings:
                            unique_findings.append(summary)
                    
                    findings_text = "\n".join(unique_findings)
                    formatted_text = f"{prefix}\n{middle_line}\n{findings_text}\n{final_line}"
                    
                    if findings:
                        findings[0].reasoning_summary = formatted_text
                        findings[0].confidence_raw = avg_conf
                        findings = [findings[0]]
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
                for f in result.findings:
                    if isinstance(f, dict) and f.get("reasoning_summary"):
                        finding_summary = f["reasoning_summary"]
                        break
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
        # Wait for WebSocket client to connect before broadcasting
        # The frontend needs time to establish the WS connection after receiving session_id
        await asyncio.sleep(0.5)

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
             _final_reports[session_id] = report
        
        _active_pipelines.pop(session_id, None)
        
        # Close WebSocket connections
        if session_id in _websocket_connections:
            for ws in _websocket_connections[session_id]:
                try:
                    await ws.close()
                except Exception:
                    pass
            _websocket_connections.pop(session_id, None)


@router.post("/investigate", response_model=InvestigationResponse)
async def investigate(
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
    if not re.match(r"^CASE-\d+$", case_id) and not re.match(r"^CASE-[a-f0-9-]+$", case_id, re.I):
        raise HTTPException(status_code=400, detail="Invalid case_id format. Expected CASE-[timestamp] or CASE-[uuid].")
    
    if not re.match(r"^REQ-\d{5,10}$", investigator_id):
        raise HTTPException(status_code=400, detail="Invalid investigator_id format. Expected REQ-[5-10 digits].")

    # 2. Rate Limiting (SEC 2)
    from infra.redis_client import get_redis_client
    redis = await get_redis_client()
    rate_limit_key = f"rate_limit:upload:{investigator_id}"
    
    # 5 uploads per 10 minutes
    current_count = await redis.client.get(rate_limit_key)
    if current_count and int(current_count) >= 5:
        ttl = await redis.client.ttl(rate_limit_key)
        raise HTTPException(
            status_code=429, 
            detail=f"Rate limit exceeded. Please wait {ttl} seconds."
        )
    
    async with redis.client.pipeline() as pipe:
        await pipe.incr(rate_limit_key)
        if not current_count:
            await pipe.expire(rate_limit_key, 600)
        await pipe.execute()

    # 3. File Size Validation
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB"
        )

    # 4. MIME type validation
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid file type. Allowed types: {', '.join(ALLOWED_MIME_TYPES)}"
        )

    # Create session ID
    session_id = str(uuid4())
    
    # Track investigation started
    increment_investigations_started()

    # S6: Sanitize uploaded filename extension
    raw_ext = Path(file.filename or "").suffix
    safe_ext = re.sub(r'[^a-zA-Z0-9.]', '', raw_ext) or ".bin"

    content = await file.read()
    
    def write_temp_file(data: bytes, ext: str) -> str:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
            tmp_file.write(data)
            return tmp_file.name
            
    evidence_file_path = await asyncio.to_thread(write_temp_file, content, safe_ext)

    try:
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
        # Clean up temp file on error
        if os.path.exists(evidence_file_path):
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
    
    if session_id in _final_reports:
        report = _final_reports[session_id]
    elif session_id in _active_pipelines:
        pipeline = _active_pipelines[session_id]
        
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
    if session_id not in _active_pipelines:
        raise HTTPException(status_code=404, detail="Session not found")

    pipeline = _active_pipelines[session_id]

    # Get brief from session manager (not working memory — it doesn't have this method)
    try:
        brief = await pipeline.session_manager.get_investigator_brief(
            session_id=UUID(session_id),
            agent_id=agent_id,
        )
        if brief:
            return {"brief": brief}
    except Exception:
        pass

    return {"brief": "No brief available yet."}


@router.get("/sessions/{session_id}/checkpoints")
async def get_checkpoints(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get pending HITL checkpoints for a session."""
    if session_id not in _active_pipelines:
        raise HTTPException(status_code=404, detail="Session not found")

    pipeline = _active_pipelines[session_id]

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
