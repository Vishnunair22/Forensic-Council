"""
Investigation Routes - FIXED VERSION
=====================================

Routes for starting and managing forensic investigations with proper
real-time updates, faster analysis, and better state management.
"""

import asyncio
import os
import re
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Form, Request
from pydantic import BaseModel
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


# ============================================================================
# INVESTIGATE ENDPOINT - Start a new forensic investigation
# ============================================================================

@router.post("/investigate", response_model=InvestigationResponse)
async def start_investigation(
    file: UploadFile = File(...),
    case_id: str = Form(...),
    investigator_id: str = Form(...),
    current_user: User = Depends(get_current_user),
):
    """
    Start a new forensic investigation by uploading evidence.
    
    Accepts multipart/form-data with:
    - file: The evidence file (image, audio, or video)
    - case_id: Case identifier (e.g., CASE-20260101-001)
    - investigator_id: Investigator ID (e.g., REQ-12345)
    
    Returns session_id for tracking the investigation via WebSocket.
    """
    from uuid import uuid4
    import os
    
    # Validate file type
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"File type {file.content_type} not allowed. Allowed types: {', '.join(ALLOWED_MIME_TYPES)}"
        )
    
    # Validate file size
    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File size exceeds maximum allowed size of {MAX_FILE_SIZE / (1024*1024)}MB"
        )
    
    # Generate session ID
    session_id = str(uuid4())
    
    # Create temp file for evidence
    evidence_dir = Path(settings.evidence_storage_path)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    file_extension = Path(file.filename).suffix if file.filename else ""
    evidence_file_path = evidence_dir / f"{session_id}{file_extension}"
    
    # Save uploaded file using FastAPI's built-in async file handling
    try:
        # Use the async file directly - FastAPI UploadFile is already async
        content = await file.read()
        with open(evidence_file_path, 'wb') as f:
            f.write(content)
    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file")
    
    # Create pipeline - takes no arguments in constructor
    from orchestration.pipeline import ForensicCouncilPipeline
    pipeline = ForensicCouncilPipeline()
    _active_pipelines[session_id] = pipeline
    
    # Start investigation in background using run_investigation_task which:
    # 1. Waits for WebSocket connection
    # 2. Calls _wrap_pipeline_with_broadcasts
    # 3. Sets pipeline._final_report
    # 4. Broadcasts PIPELINE_COMPLETE
    # 5. Handles errors and cleanup
    task = asyncio.create_task(
        run_investigation_task(
            session_id=session_id,
            pipeline=pipeline,
            evidence_file_path=str(evidence_file_path),
            case_id=case_id,
            investigator_id=investigator_id,
        )
    )
    _active_tasks[session_id] = task
    
    increment_investigations_started()
    logger.info(f"Investigation started: session_id={session_id}, case_id={case_id}, file={file.filename}")

    # Opportunistically evict stale sessions (runs in O(n) but n is small)
    _evict_stale_sessions()
    
    return InvestigationResponse(
        session_id=session_id,
        case_id=case_id,
        status="started",
        message=f"Investigation started for {file.filename}"
    )


class ResumeRequest(BaseModel):
    """Request body for the resume endpoint."""
    deep_analysis: bool

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
        if not task.done():
            task.cancel()
    _active_tasks.clear()
    _websocket_connections.clear()
    _active_pipelines.clear()
    _final_reports.clear()

# Session TTL: keep completed sessions for 24 hours, then evict
_SESSION_TTL_SECONDS = 86_400  # 24 h


def _evict_stale_sessions() -> None:
    """
    Remove completed sessions that have exceeded SESSION_TTL.
    Called periodically to prevent unbounded memory growth in long-running deployments.
    """
    now = datetime.now(timezone.utc)
    stale = [
        sid for sid, (_, cached_at) in list(_final_reports.items())
        if (now - cached_at).total_seconds() > _SESSION_TTL_SECONDS
    ]
    for sid in stale:
        _final_reports.pop(sid, None)
        # Only remove the pipeline if there's no live task still running
        task = _active_tasks.get(sid)
        if task is None or task.done():
            _active_pipelines.pop(sid, None)
            _active_tasks.pop(sid, None)
            _websocket_connections.pop(sid, None)
    if stale:
        logger.info(f"Evicted {len(stale)} stale session(s) from memory")

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
    _final_reports.clear()


def pop_active_task(session_id: str):
    """Remove and return the active task for a session."""
    return _active_tasks.pop(session_id, None)


def get_session_websockets(session_id: str) -> list:
    """Get WebSocket connections for a session."""
    return _websocket_connections.get(session_id, [])


def clear_session_websockets(session_id: str):
    """Remove all WebSocket connections for a session."""
    _websocket_connections.pop(session_id, None)


def register_websocket(session_id: str, websocket):
    """Register a WebSocket connection for a session."""
    if session_id not in _websocket_connections:
        _websocket_connections[session_id] = []
    _websocket_connections[session_id].append(websocket)


def unregister_websocket(session_id: str, websocket):
    """Unregister a WebSocket connection from a session."""
    if session_id in _websocket_connections:
        try:
            _websocket_connections[session_id].remove(websocket)
        except ValueError:
            pass


# Allowed MIME types
ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/tiff", "image/webp", "image/gif", "image/bmp",
    "video/mp4", "video/quicktime", "video/x-msvideo",
    "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp4", "audio/flac",
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
    
    FIXES:
    - Faster heartbeat (0.2s instead of 1.0s)
    - More aggressive thinking text updates
    - Better state management
    """
    original_run = pipeline._run_agents_concurrent
    ws_session_id = session_id

    # Hook custody logger for real-time thinking updates
    def instrument_logger(logger_obj):
        original_log_entry = logger_obj.log_entry

        async def instrumented_log_entry(**kwargs):
            result = await original_log_entry(**kwargs)
            
            entry_type = kwargs.get('entry_type')
            content = kwargs.get('content', {})
            agent_id = kwargs.get('agent_id')
            
            type_val = getattr(entry_type, "value", str(entry_type))
            
            if type_val in ("THOUGHT", "ACTION") and isinstance(content, dict):
                if content.get("action") == "session_start":
                    return result
                
                agent_name = _AGENT_NAMES.get(agent_id, agent_id)
                
                if type_val == "ACTION" and content.get("tool_name"):
                    tool_label = content["tool_name"].replace("_", " ").title()
                    thinking_text = f"Calling {tool_label}..."
                else:
                    thinking_text = content.get("content", "Analyzing...")
                
                await broadcast_update(
                    ws_session_id,
                    BriefUpdate(
                        type="AGENT_UPDATE",
                        session_id=ws_session_id,
                        agent_id=agent_id,
                        agent_name=agent_name,
                        message=thinking_text,
                        data={"status": "running", "thinking": thinking_text},
                    )
                )
            return result
        
        logger_obj.log_entry = instrumented_log_entry
    
    if pipeline.custody_logger:
        instrument_logger(pipeline.custody_logger)

    async def instrumented_run(evidence_artifact, session_id=None):
        """Run each agent SEQUENTIALLY with improved real-time updates."""
        
        mime = evidence_artifact.metadata.get("mime_type", "application/octet-stream")
        
        _AGENT_MIME_SUPPORT = {
            "Agent1": {"image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp", "image/tiff"},
            "Agent2": {"audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp4", "audio/flac",
                       "video/mp4", "video/x-msvideo", "video/quicktime"},
            "Agent3": {"image/jpeg", "image/png", "image/webp", "video/mp4", "video/x-msvideo", "video/quicktime"},
            "Agent4": {"video/mp4", "video/x-msvideo", "video/quicktime"},
            "Agent5": {"image/jpeg", "image/png", "image/tiff", "image/webp",
                       "video/mp4", "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp4"},
        }
        
        from agents.agent1_image import Agent1Image
        from agents.agent2_audio import Agent2Audio
        from agents.agent3_object import Agent3Object
        from agents.agent4_video import Agent4Video
        from agents.agent5_metadata import Agent5Metadata
        from core.working_memory import WorkingMemory
        
        agent_configs = [
            ("Agent1", "Image Forensics", Agent1Image, "Analyzing image patterns and inconsistencies..."),
            ("Agent2", "Audio Forensics", Agent2Audio, "Checking audio authenticity markers..."),
            ("Agent3", "Object Detection", Agent3Object, "Scanning for object anomalies..."),
            ("Agent4", "Video Forensics", Agent4Video, "Examining temporal consistency..."),
            ("Agent5", "Metadata Forensics", Agent5Metadata, "Validating metadata integrity..."),
        ]
        
        results = []

        async def make_heartbeat(agent_id: str, agent_name: str, target_memory: WorkingMemory, done_event: asyncio.Event):
            """Stream live working-memory progress to the WebSocket client."""
            last_thinking = ""
            while not done_event.is_set():
                try:
                    await asyncio.wait_for(done_event.wait(), timeout=0.2)
                    break
                except asyncio.TimeoutError:
                    pass
                try:
                    wm_state = await target_memory.get_state(
                        session_id=session_id or evidence_artifact.artifact_id,
                        agent_id=agent_id,
                    )
                    if not wm_state:
                        await asyncio.sleep(0.1)
                        continue
                    tasks_list = wm_state.tasks
                    completed_t = [t for t in tasks_list if t.status.value == "COMPLETE"]
                    in_progress_t = [t for t in tasks_list if t.status.value == "IN_PROGRESS"]
                    total = len(tasks_list)
                    done = len(completed_t)
                    thinking = ""
                    if in_progress_t:
                        current_task = in_progress_t[0].description
                        tool_name = in_progress_t[0].result_ref or ""
                        thinking = f"Running: {current_task}"
                        if tool_name:
                            thinking += f" [{tool_name}]"
                        if total > 0:
                            thinking += f" ({done+1}/{total})"
                    elif done > 0 and done >= total and total > 0:
                        thinking = "Finalizing findings..."
                    elif done > 0:
                        thinking = f"Processed {done}/{total} tasks. Running validation..."
                    elif total > 0:
                        thinking = f"Initializing {total} analysis tasks..."
                    else:
                        thinking = "Starting analysis..."
                    if thinking and thinking != last_thinking:
                        last_thinking = thinking
                        await broadcast_update(
                            ws_session_id,
                            BriefUpdate(
                                type="AGENT_UPDATE",
                                session_id=ws_session_id,
                                agent_id=agent_id,
                                agent_name=agent_name,
                                message=thinking,
                                data={"status": "running", "thinking": thinking},
                            )
                        )
                except Exception as e:
                    logger.debug(f"Heartbeat error: {e}")

        async def run_single_agent(agent_id, agent_name, AgentClass, thinking_phrase):
            supported_mimes = _AGENT_MIME_SUPPORT.get(agent_id, set())
            if mime not in supported_mimes:
                await broadcast_update(
                    ws_session_id,
                    BriefUpdate(
                        type="AGENT_UPDATE",
                        session_id=ws_session_id,
                        agent_id=agent_id,
                        agent_name=agent_name,
                        message=f"File type {mime} not supported",
                        data={"status": "running", "thinking": f"Identifying file format"},
                    )
                )
                
                await asyncio.sleep(0.5)
                
                await broadcast_update(
                    ws_session_id,
                    BriefUpdate(
                        type="AGENT_COMPLETE",
                        session_id=ws_session_id,
                        agent_id=agent_id,
                        agent_name=agent_name,
                        message=f"Skipped - {mime} not supported",
                        data={
                            "status": "complete",
                            "confidence": 0.0,
                            "findings_count": 0,
                            "error": f"Format not supported",
                        },
                    )
                )
                return AgentLoopResult(
                    agent_id=agent_id,
                    findings=[],
                    reflection_report={},
                    react_chain=[],
                ), None
            
            # Initial thinking broadcast
            await broadcast_update(
                ws_session_id,
                BriefUpdate(
                    type="AGENT_UPDATE",
                    session_id=ws_session_id,
                    agent_id=agent_id,
                    agent_name=agent_name,
                    message=thinking_phrase,
                    data={"status": "running", "thinking": thinking_phrase},
                )
            )
            
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
                
                # Use shared heartbeat helper
                heartbeat_done = asyncio.Event()
                
                # Run agent + heartbeat concurrently
                heartbeat_task = asyncio.create_task(make_heartbeat(agent_id, agent_name, agent.working_memory, heartbeat_done))
                
                # FIX: Reduce timeout to 120s for faster completion
                agent_timeout = min(120, pipeline.config.investigation_timeout * 0.6)
                try:
                    findings = await asyncio.wait_for(
                        agent.run_investigation(),
                        timeout=agent_timeout
                    )
                finally:
                    heartbeat_done.set()
                    try:
                        await asyncio.wait_for(heartbeat_task, timeout=2.0)
                    except:
                        heartbeat_task.cancel()
                
                # Format findings
                is_unsupported = any(getattr(f, 'finding_type', '') == "Format not supported" for f in findings)
                
                if is_unsupported:
                    base_name = evidence_artifact.metadata.get("original_filename", os.path.basename(evidence_file_path))
                    clean_text = f"{agent_name} cannot analyze this file type ({mime})."
                    for f in findings:
                        f.reasoning_summary = clean_text
                
                # Serialize react chain
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
            except asyncio.TimeoutError:
                logger.error(f"{agent_id} timed out after {agent_timeout}s")
                result = AgentLoopResult(
                    agent_id=agent_id,
                    findings=[],
                    reflection_report={},
                    react_chain=[],
                    error=f"Timeout after {agent_timeout:.0f}s",
                )
            except Exception as e:
                logger.error(f"{agent_id} failed", error=str(e))
                result = AgentLoopResult(
                    agent_id=agent_id,
                    findings=[],
                    reflection_report={},
                    react_chain=[],
                    error=str(e),
                )
            
            # Build completion message
            confidence = 0.0
            finding_summary = f"{agent_name} analysis complete."
            if result.findings:
                confidences = [
                    f.get("confidence_raw", 0.5) if isinstance(f, dict) else 0.5
                    for f in result.findings
                ]
                confidence = sum(confidences) / len(confidences) if confidences else 0.5
                finding_summaries = []
                for f in result.findings:
                    if isinstance(f, dict) and f.get("reasoning_summary"):
                        finding_summaries.append(f["reasoning_summary"])
                if finding_summaries:
                    finding_summary = " | ".join(finding_summaries[:2])  # Show first 2 findings
            elif result.error:
                finding_summary = f"Error: {result.error[:60]}"
            
            # Broadcast completion
            await broadcast_update(
                ws_session_id,
                BriefUpdate(
                    type="AGENT_COMPLETE",
                    session_id=ws_session_id,
                    agent_id=agent_id,
                    agent_name=agent_name,
                    message=finding_summary,
                    data={
                        "status": "error" if result.error else "complete",
                        "confidence": confidence,
                        "findings_count": len(result.findings),
                        "error": result.error,
                    },
                )
            )
            return result, agent
        
        # FIX: Removed stagger delays - run agents immediately without delays
        tasks = [
            run_single_agent(agent_id, agent_name, AgentClass, thinking_phrase)
            for agent_id, agent_name, AgentClass, thinking_phrase in agent_configs
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        results = []
        deep_pass_coroutines = []
        
        async def run_agent_deep_pass(agent_id: str, agent_name: str, agent, initial_result: AgentLoopResult):
            """Run deep analysis in background."""
            try:
                await broadcast_update(
                    ws_session_id,
                    BriefUpdate(
                        type="AGENT_UPDATE",
                        session_id=ws_session_id,
                        agent_id=agent_id,
                        agent_name=agent_name,
                        message=f"{agent_name} running deep analysis...",
                        data={"status": "running", "thinking": "Running heavy analysis models..."},
                    )
                )
                
                deep_agent_id = f"{agent_id}_deep"
                deep_heartbeat_done = asyncio.Event()
                heartbeat_task = asyncio.create_task(make_heartbeat(agent_id, agent_name, agent.working_memory, deep_heartbeat_done))
                
                try:
                    deep_timeout = min(300, pipeline.config.investigation_timeout)
                    deep_findings = await asyncio.wait_for(
                        agent.run_deep_investigation(),
                        timeout=deep_timeout
                    )
                finally:
                    deep_heartbeat_done.set()
                    try:
                        heartbeat_task.cancel()
                        await asyncio.wait_for(heartbeat_task, timeout=2.0)
                    except:
                        pass
                
                if deep_findings:
                    # run_deep_investigation returns COMBINED findings (initial + deep)
                    # Replace initial findings with combined findings to avoid duplication
                    initial_result.findings = [f.model_dump(mode="json") for f in deep_findings]
                    
                    confidences = [
                        f.get("confidence_raw", 0.5) if isinstance(f, dict) else 0.5
                        for f in initial_result.findings
                    ]
                    confidence = sum(confidences) / len(confidences) if confidences else 0.5
                    
                    finding_summaries = []
                    for f in initial_result.findings:
                        if isinstance(f, dict) and f.get("reasoning_summary"):
                            finding_summaries.append(f["reasoning_summary"])
                    finding_summary = " | ".join(finding_summaries[:2]) if finding_summaries else f"{agent_name} deep analysis complete."
                    
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
                                "findings_count": len(initial_result.findings),
                                "error": None,
                            },
                        )
                    )
            except Exception as e:
                logger.error(f"Deep pass failed for {agent_id}: {e}")
                await broadcast_update(
                    ws_session_id,
                    BriefUpdate(
                        type="AGENT_COMPLETE",
                        session_id=ws_session_id,
                        agent_id=agent_id,
                        agent_name=agent_name,
                        message=f"{agent_name} deep analysis failed",
                        data={
                            "status": "complete",
                            "confidence": 0.0,
                            "findings_count": 0,
                            "error": str(e)[:50],
                        },
                    )
                )
        
        for i, r in enumerate(raw_results):
            agent_id = agent_configs[i][0]
            agent_name = agent_configs[i][1]
            
            if isinstance(r, Exception):
                logger.error(f"{agent_id} raised exception: {str(r)}")
                results.append(AgentLoopResult(
                    agent_id=agent_id,
                    findings=[],
                    reflection_report={},
                    react_chain=[],
                    error=str(r),
                ))
                await broadcast_update(
                    ws_session_id,
                    BriefUpdate(
                        type="AGENT_COMPLETE",
                        session_id=ws_session_id,
                        agent_id=agent_id,
                        agent_name=agent_name,
                        message=f"Error: {str(r)[:50]}",
                        data={"status": "complete", "confidence": 0.0, "findings_count": 0, "error": str(r)},
                    )
                )
            else:
                result_obj, agent_instance = r
                results.append(result_obj)
                
                if agent_instance and len(agent_instance.deep_task_decomposition) > 0:
                    deep_pass_coroutines.append(
                        run_agent_deep_pass(agent_id, agent_name, agent_instance, result_obj)
                    )
        
        # FIX: Only pause if there are actual deep tasks
        if deep_pass_coroutines:
            logger.info("Initial analysis complete. Awaiting deep analysis decision...")
            await broadcast_update(
                ws_session_id,
                BriefUpdate(
                    type="PIPELINE_PAUSED",
                    session_id=ws_session_id,
                    message="Initial analysis complete. Ready for deep analysis.",
                    data={"status": "awaiting_decision", "deep_analysis_pending": True},
                )
            )
            
            await getattr(pipeline, "deep_analysis_decision_event").wait()
            
            if getattr(pipeline, "run_deep_analysis_flag"):
                logger.info(f"Running deep analysis for {len(deep_pass_coroutines)} agents...")
                await broadcast_update(
                    ws_session_id,
                    BriefUpdate(
                        type="AGENT_UPDATE",
                        session_id=ws_session_id,
                        message="Running deep forensic analysis...",
                        data={"status": "running", "thinking": "Loading heavy ML models..."},
                    )
                )
                await asyncio.gather(*deep_pass_coroutines, return_exceptions=True)
            else:
                logger.info("User skipped deep analysis.")
        else:
            logger.info("No deep analysis tasks. Proceeding to arbiter.")
        
        return results
    
    pipeline._run_agents_concurrent = instrumented_run
    
    return await pipeline.run_investigation(
        evidence_file_path=evidence_file_path,
        case_id=case_id,
        investigator_id=investigator_id,
    )


async def run_investigation_task(
    session_id: str,
    pipeline: ForensicCouncilPipeline,
    evidence_file_path: str,
    case_id: str,
    investigator_id: str,
):
    """Background task to run investigation with improved timing."""
    error_msg = None
    
    try:
        # Wait for WebSocket connection (up to 5 seconds)
        for _ws_wait in range(50):
            if session_id in _websocket_connections and _websocket_connections[session_id]:
                break
            await asyncio.sleep(0.1)
        
        # Send initial update
        await broadcast_update(
            session_id,
            BriefUpdate(
                type="AGENT_UPDATE",
                session_id=session_id,
                message="Starting forensic analysis...",
                data={"status": "starting", "thinking": "Loading analysis agents..."},
            )
        )
        
        # Run with shorter timeout
        timeout = min(settings.investigation_timeout, 600)  # Max 10 minutes
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
        
        # Arbiter synthesis
        await broadcast_update(
            session_id,
            BriefUpdate(
                type="AGENT_UPDATE",
                session_id=session_id,
                agent_id="Arbiter",
                agent_name="Council Arbiter",
                message="Council deliberating findings...",
                data={"status": "deliberating", "thinking": "Synthesizing results..."},
            )
        )
        
        # Pipeline complete
        await broadcast_update(
            session_id,
            BriefUpdate(
                type="PIPELINE_COMPLETE",
                session_id=session_id,
                message="Investigation concluded.",
                data={"report_id": str(report.report_id)},
            )
        )
        
        pipeline._final_report = report
        increment_investigations_completed()
        
    except asyncio.TimeoutError:
        error_msg = f"Investigation timed out after {timeout}s"
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
        logger.error(f"Investigation failed: {error_msg}", exc_info=True)
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
        if error_msg:
            pipeline._error = error_msg
        try:
            if os.path.exists(evidence_file_path):
                os.unlink(evidence_file_path)
        except Exception as e:
            logger.warning(f"Failed to clean up temp file: {e}")


# ============================================================================
# RESUME ENDPOINT - Handles Accept Analysis / Deep Analysis decision
# ============================================================================

@router.post("/{session_id}/resume")
async def resume_investigation(
    session_id: str,
    request: ResumeRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Resume investigation after initial analysis decision.
    
    This endpoint is called when the user clicks:
    - "Accept Analysis" -> deep_analysis=False -> Skip deep pass, proceed to arbiter
    - "Deep Analysis" -> deep_analysis=True -> Run heavy ML analysis
    
    The pipeline must be in a paused state (waiting on deep_analysis_decision_event).
    """
    logger.info(
        "Resume investigation called",
        session_id=session_id,
        deep_analysis=request.deep_analysis,
        user_id=current_user.user_id,
    )
    
    # Get the active pipeline
    pipeline = get_active_pipeline(session_id)
    if not pipeline:
        raise HTTPException(
            status_code=404,
            detail=f"No active investigation found for session {session_id}"
        )
    
    # Check if pipeline is waiting for decision
    if not hasattr(pipeline, 'deep_analysis_decision_event'):
        raise HTTPException(
            status_code=400,
            detail="Pipeline is not in a paused state waiting for decision"
        )
    
    # Check if the event has already been set (decision already made)
    if pipeline.deep_analysis_decision_event.is_set():
        raise HTTPException(
            status_code=400,
            detail="Decision already made for this investigation"
        )
    
    # Set the deep analysis flag based on user choice
    pipeline.run_deep_analysis_flag = request.deep_analysis
    
    # Signal the pipeline to continue (release the wait)
    pipeline.deep_analysis_decision_event.set()
    
    logger.info(
        "Investigation resume signal sent",
        session_id=session_id,
        deep_analysis=request.deep_analysis,
    )
    
    return {
        "status": "resumed",
        "session_id": session_id,
        "deep_analysis": request.deep_analysis,
        "message": "Deep analysis started" if request.deep_analysis else "Proceeding to final report"
    }
