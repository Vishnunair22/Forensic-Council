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
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Form, Request, status
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

# ── Per-user upload rate limiter ──────────────────────────────────────────────
# Limits how many investigations a single authenticated user can start within
# a rolling window. Prevents a single account from exhausting pipeline capacity.
_MAX_INVESTIGATIONS_PER_USER = 10      # max concurrent/recent investigations
_USER_RATE_WINDOW_SECS = 300           # 5-minute rolling window
_USER_RATE_LOCKOUT_SECS = 120          # 2-minute lockout after limit hit

# In-memory fallback: {user_id: [timestamp, ...]}
_user_investigation_times: dict[str, list[float]] = {}


async def _check_investigation_rate_limit(user_id: str) -> None:
    """
    Raise HTTP 429 if the user has exceeded the investigation rate limit.

    Prefers Redis when available (replica-safe); falls back to an in-process
    dict when Redis is unavailable (single-replica safe).
    """
    key = f"inv_rate:{user_id}"
    now = time.time()

    # ── Redis path ────────────────────────────────────────────────────────────
    try:
        from infra.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            count_raw = await redis.get(key)
            count = int(count_raw) if count_raw else 0
            if count >= _MAX_INVESTIGATIONS_PER_USER:
                ttl = await redis.ttl(key)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"Too many investigations started. "
                        f"Try again in {max(ttl, 1)} seconds."
                    ),
                    headers={"Retry-After": str(max(ttl, 1))},
                )
            pipe = redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, _USER_RATE_LOCKOUT_SECS)
            await pipe.execute()
            return
    except HTTPException:
        raise
    except Exception:
        pass  # fall through to in-memory fallback

    # ── In-memory fallback ────────────────────────────────────────────────────
    cutoff = now - _USER_RATE_WINDOW_SECS
    times = _user_investigation_times.setdefault(user_id, [])
    times[:] = [t for t in times if t > cutoff]
    if len(times) >= _MAX_INVESTIGATIONS_PER_USER:
        retry_after = int(_USER_RATE_WINDOW_SECS - (now - times[0])) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Too many investigations started. "
                f"Try again in {max(retry_after, 1)} seconds."
            ),
            headers={"Retry-After": str(max(retry_after, 1))},
        )
    times.append(now)

# Allowed MIME types (declared early — used in start_investigation)
ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/tiff", "image/webp", "image/gif", "image/bmp",
    "video/mp4", "video/quicktime", "video/x-msvideo",
    "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp4", "audio/flac",
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

# Allowed file extensions — must match an accepted MIME type
_ALLOWED_EXTENSIONS: frozenset[str] = frozenset({
    ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp", ".gif", ".bmp",
    ".mp4", ".mov", ".avi",
    ".wav", ".mp3", ".m4a", ".flac",
})

# Strict allow-list pattern for case_id and investigator_id.
# Alphanumerics, hyphens, underscores, and dots only — prevents log injection,
# shell metacharacter injection, and DB issues with unusual unicode.
_SAFE_ID_RE = re.compile(r'^[A-Za-z0-9_\-\.]{1,128}$')


def _validate_safe_id(value: str, field_name: str) -> None:
    """Raise 422 if value contains unsafe characters."""
    if not _SAFE_ID_RE.match(value):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid {field_name}: must be 1–128 characters, "
                "alphanumeric with hyphens, underscores, and dots only."
            ),
        )


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
    # ── Input validation ──────────────────────────────────────────────────────
    _validate_safe_id(case_id, "case_id")
    _validate_safe_id(investigator_id, "investigator_id")

    # ── Per-user rate limit ───────────────────────────────────────────────────
    await _check_investigation_rate_limit(current_user.user_id)

    # ── MIME type check ───────────────────────────────────────────────────────
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File type '{file.content_type}' is not allowed. "
                f"Accepted types: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
            ),
        )

    # ── File extension allow-list check ───────────────────────────────────────
    raw_suffix = Path(file.filename or "").suffix.lower()
    if raw_suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File extension '{raw_suffix}' is not permitted. "
                f"Accepted extensions: {', '.join(sorted(_ALLOWED_EXTENSIONS))}"
            ),
        )
    file_extension = raw_suffix  # already safe — no path traversal possible

    # ── File size check ───────────────────────────────────────────────────────
    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File size exceeds the {MAX_FILE_SIZE // (1024 * 1024)} MB limit.",
        )

    # ── Generate session ID ───────────────────────────────────────────────────
    session_id = str(uuid4())

    # ── Stage file to /tmp (non-blocking) ────────────────────────────────────
    tmp_path = Path("/tmp") / f"{session_id}{file_extension}"
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File size exceeds the {MAX_FILE_SIZE // (1024 * 1024)} MB limit.",
            )
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, tmp_path.write_bytes, content)
    except HTTPException:
        if tmp_path.exists():
            try: tmp_path.unlink()
            except Exception: pass
        raise
    except Exception as e:
        logger.error("Failed to stage uploaded file", error=str(e))
        if tmp_path.exists():
            try: tmp_path.unlink()
            except Exception: pass
        raise HTTPException(status_code=500, detail="Failed to save uploaded file.")

    # ── Register pipeline ─────────────────────────────────────────────────────
    from orchestration.pipeline import ForensicCouncilPipeline
    pipeline = ForensicCouncilPipeline()
    _active_pipelines[session_id] = pipeline

    # ── Start background investigation task ───────────────────────────────────
    task = asyncio.create_task(
        run_investigation_task(
            session_id=session_id,
            pipeline=pipeline,
            evidence_file_path=str(tmp_path),
            case_id=case_id,
            investigator_id=investigator_id,
        )
    )

    # E2: done-callback catches any unexpected BaseException that escaped the
    # task's internal try/except (e.g. SystemExit, MemoryError) so they are
    # logged rather than silently lost.
    def _task_done_callback(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.error(
                "Investigation task raised unexpected exception",
                session_id=session_id,
                error=str(exc),
                exc_info=exc,
            )

    task.add_done_callback(_task_done_callback)
    _active_tasks[session_id] = task

    increment_investigations_started()
    logger.info(
        "Investigation started",
        session_id=session_id,
        case_id=case_id,
        content_type=file.content_type,
        size_bytes=len(content),
    )

    # ── Register session in DB immediately (best-effort, non-blocking) ────────
    # This creates a row in investigation_state so DB-backed queries work even
    # before the pipeline completes. Failure is non-fatal.
    async def _register_session_async():
        try:
            from core.session_persistence import get_session_persistence
            persistence = await get_session_persistence()
            await persistence.save_session_state(
                session_id=session_id,
                case_id=case_id,
                investigator_id=investigator_id,
                pipeline_state={"status": "running"},
                status="running",
            )
        except Exception as e:
            logger.warning("Could not register session in DB", session_id=session_id, error=str(e))

    asyncio.create_task(_register_session_async())

    _evict_stale_sessions()

    return InvestigationResponse(
        session_id=session_id,
        case_id=case_id,
        status="started",
        message=f"Investigation started for {file.filename or 'evidence'}",
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
            # Agent3 is YOLO/object-detection on still frames only — no raw video
            "Agent3": {"image/jpeg", "image/png", "image/webp", "image/bmp", "image/gif", "image/tiff"},
            "Agent4": {"video/mp4", "video/x-msvideo", "video/quicktime"},
            # Agent5 is metadata forensics — runs on every supported MIME type
            "Agent5": {
                "image/jpeg", "image/png", "image/tiff", "image/webp", "image/gif", "image/bmp",
                "video/mp4", "video/quicktime", "video/x-msvideo",
                "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp4", "audio/flac",
            },
        }
        
        from agents.agent1_image import Agent1Image
        from agents.agent2_audio import Agent2Audio
        from agents.agent3_object import Agent3Object
        from agents.agent4_video import Agent4Video
        from agents.agent5_metadata import Agent5Metadata
        from core.working_memory import WorkingMemory
        
        agent_configs = [
            ("Agent1", "Image Forensics", Agent1Image, "🔬 Launching ELA engine — scanning for pixel-level anomalies…"),
            ("Agent2", "Audio Forensics", Agent2Audio, "🎙️ Establishing voice-count baseline with diarization…"),
            ("Agent3", "Object Detection", Agent3Object, "👁️ Loading YOLO model — running primary object detection…"),
            ("Agent4", "Video Forensics", Agent4Video, "🎬 Starting optical flow analysis — building temporal heatmap…"),
            ("Agent5", "Metadata Forensics", Agent5Metadata, "📋 Extracting EXIF fields — checking for mandatory field gaps…"),
        ]

        # ── Per-agent tool-action humaniser (initial AND deep pass) ──────────
        _TASK_PHRASES: dict[str, str] = {
            # Agent 1 – Image Integrity
            "ela":                          "🔬 Running Error Level Analysis across full image…",
            "ela anomaly block":            "🧩 Classifying ELA anomaly blocks in flagged regions…",
            "jpeg ghost":                   "👻 Detecting JPEG ghost artifacts in suspicious regions…",
            "frequency domain analysis":    "📡 Running frequency-domain analysis on contested regions…",
            "frequency-domain gan":         "📡 Scanning frequency domain for GAN generation artifacts…",
            "file hash":                    "🔑 Verifying file hash against ingestion record…",
            "roi":                          "🎯 Re-analysing flagged ROIs with noise footprint…",
            "copy-move":                    "🔍 Checking for copy-move cloning artifacts…",
            "semantic image":               "🧠 Identifying what this image actually depicts…",
            "ocr":                          "📄 Extracting all visible text via OCR…",
            "visible text":                 "📄 Extracting all visible text from image…",
            "adversarial robustness":       "🛡️ Testing robustness against anti-forensics evasion…",
            "gemini":                       "🤖 Asking Gemini AI for deep visual forensic analysis…",
            # Agent 2 – Audio
            "speaker diarization":          "🎙️ Establishing voice-count baseline with diarization…",
            "anti-spoofing":                "🔊 Running anti-spoofing detection on speaker segments…",
            "prosody":                      "🎵 Analysing prosody and rhythm across full audio track…",
            "splice point":                 "✂️ Detecting ML splice points in audio segments…",
            "background noise":             "🌊 Checking background noise consistency for edit points…",
            "codec fingerprint":            "🔐 Fingerprinting codec chain for re-encoding events…",
            "audio-visual sync":            "⏱️ Verifying audio-visual sync against video timestamps…",
            "collaborative call":           "🤝 Issuing inter-agent call to Agent 4 for corroboration…",
            "cross-agent collaboration":    "🤝 Running cross-agent collaboration with Agent 4…",
            "spectral perturbation":        "📊 Running spectral perturbation adversarial check…",
            "codec chain":                  "🔐 Running advanced codec chain analysis…",
            # Agent 3 – Object/Weapon
            "full-scene primary object":    "👁️ Running YOLO primary object detection on full scene…",
            "secondary classification":     "🔎 Re-classifying low-confidence detections…",
            "scale and proportion":         "📐 Validating object scale and proportion geometry…",
            "lighting and shadow":          "💡 Checking per-object lighting and shadow consistency…",
            "contraband":                   "⚠️ Cross-referencing objects against contraband database…",
            "scene-level contextual":       "🧠 Analysing scene for contextual incongruences…",
            "image splicing":               "✂️ Running ML-based image splicing detection…",
            "camera noise fingerprint":     "📷 Checking camera noise fingerprint for region consistency…",
            "inter-agent call":             "🤝 Issuing inter-agent call to Agent 1 for lighting check…",
            "object detection evasion":     "🛡️ Testing against object detection evasion techniques…",
            # Agent 4 – Video
            "optical flow":                 "🎬 Running optical flow analysis — building anomaly heatmap…",
            "frame-to-frame":               "🖼️ Extracting frames and checking inter-frame consistency…",
            "explainable":                  "🏷️ Classifying anomalies as EXPLAINABLE or SUSPICIOUS…",
            "face-swap":                    "🧑‍💻 Running face-swap detection on human faces…",
            "face swap":                    "🧑‍💻 Running face-swap detection on human faces…",
            "rolling shutter":              "📷 Validating rolling shutter behaviour vs device metadata…",
            "deepfake frequency":           "📡 Running deepfake frequency analysis across full video…",
            "audio-visual timestamp":       "⏱️ Correlating audio-visual timestamps with Agent 2…",
            # Agent 5 – Metadata
            "exif":                         "📋 Extracting all EXIF fields — logging absent mandatory fields…",
            "gps coordinates":              "🌍 Cross-validating GPS coordinates against timestamp timezone…",
            "steganography":                "🕵️ Scanning for hidden steganographic payload…",
            "file structure":               "🗂️ Running file structure forensic analysis…",
            "hexadecimal":                  "🗂️ Running hex scan for software signature anomalies…",
            "cross-field consistency":      "📊 Synthesising cross-field metadata consistency verdict…",
            "ml metadata anomaly":          "🤖 Running ML metadata anomaly scoring…",
            "astronomical":                 "🔭 Running astronomical API check for GPS/timestamp validation…",
            "reverse image search":         "🌐 Running reverse image search for prior online appearances…",
            "device fingerprint":           "🔐 Querying device fingerprint database for claimed device…",
            "metadata spoofing":            "🛡️ Testing against metadata spoofing evasion techniques…",
            # Generic
            "self-reflection":              "🪞 Running self-reflection quality check on findings…",
            "submit":                       "📤 Submitting calibrated findings to Council Arbiter…",
            "finaliz":                      "✅ Finalising and packaging findings…",
        }

        def _humanise_task(task_desc: str) -> str:
            """Map a raw working-memory task description to a friendly action string."""
            low = task_desc.lower()
            for keyword, phrase in _TASK_PHRASES.items():
                if keyword in low:
                    return phrase
            # Fallback: capitalise the first letter
            return task_desc[:1].upper() + task_desc[1:] + "…"

        results = []

        async def make_heartbeat(agent_id: str, agent_name: str, target_memory: WorkingMemory, done_event: asyncio.Event, deep_namespace: str | None = None):
            """Stream live working-memory progress to the WebSocket client."""
            last_thinking = ""
            # Deep pass uses an isolated namespace; use it when provided
            wm_agent_id = deep_namespace if deep_namespace else agent_id
            while not done_event.is_set():
                try:
                    await asyncio.wait_for(done_event.wait(), timeout=0.2)
                    break
                except asyncio.TimeoutError:
                    pass
                try:
                    # Use UUID version of session_id for working memory lookup
                    _wm_session = session_id if session_id else evidence_artifact.artifact_id
                    if isinstance(_wm_session, str):
                        try:
                            from uuid import UUID as _UUID
                            _wm_session = _UUID(_wm_session)
                        except (ValueError, AttributeError):
                            pass
                    wm_state = await target_memory.get_state(
                        session_id=_wm_session,
                        agent_id=wm_agent_id,
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
                        friendly = _humanise_task(current_task)
                        progress_frac = f" ({done + 1}/{total})" if total > 0 else ""
                        thinking = friendly.rstrip("…") + progress_frac + "…"
                    elif done > 0 and done >= total and total > 0:
                        thinking = "✅ Finalising findings…"
                    elif done > 0:
                        thinking = f"🔄 Cross-validating results… ({done}/{total} tasks complete)"
                    elif total > 0:
                        thinking = f"⚙️ Initialising {total} analysis tasks…"
                    else:
                        thinking = "⚙️ Starting forensic analysis…"
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
                # Step 1: Show "checking" state so card appears active
                await broadcast_update(
                    ws_session_id,
                    BriefUpdate(
                        type="AGENT_UPDATE",
                        session_id=ws_session_id,
                        agent_id=agent_id,
                        agent_name=agent_name,
                        message=f"Checking file type compatibility…",
                        data={"status": "running", "thinking": "🔍 Checking file type compatibility…"},
                    )
                )
                await asyncio.sleep(0.3)

                # Step 2: Determine a human-friendly file category name
                if mime.startswith("image/"):
                    file_cat = "image"
                elif mime.startswith("video/"):
                    file_cat = "video"
                elif mime.startswith("audio/"):
                    file_cat = "audio"
                else:
                    file_cat = mime.split("/")[-1] if "/" in mime else "this file type"

                supported_cats = set()
                for m in supported_mimes:
                    if m.startswith("image/"): supported_cats.add("images")
                    elif m.startswith("video/"): supported_cats.add("video")
                    elif m.startswith("audio/"): supported_cats.add("audio")
                supported_str = " and ".join(sorted(supported_cats)) if supported_cats else "other formats"

                skip_msg = (
                    f"{agent_name} is not applicable for {file_cat} files. "
                    f"This agent analyses {supported_str} only. Skipping."
                )

                await broadcast_update(
                    ws_session_id,
                    BriefUpdate(
                        type="AGENT_COMPLETE",
                        session_id=ws_session_id,
                        agent_id=agent_id,
                        agent_name=agent_name,
                        message=skip_msg,
                        data={
                            "status": "complete",
                            "confidence": 0.0,
                            "findings_count": 0,
                            "error": f"Not applicable for {file_cat} files",
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
                # Agents expect session_id as UUID
                from uuid import UUID as _AUUID
                _agent_session_id = session_id or evidence_artifact.artifact_id
                if isinstance(_agent_session_id, str):
                    try:
                        _agent_session_id = _AUUID(_agent_session_id)
                    except (ValueError, AttributeError):
                        pass

                agent_kwargs = {
                    "agent_id": agent_id,
                    "session_id": _agent_session_id,
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
                
                # Per-agent timeout: generous enough for cold ML model loads,
                # but not so long that a hung agent blocks the whole UI.
                # YOLO/ELA first-run can take 60-120s; subsequent runs are ~10-30s.
                agent_timeout = min(180, pipeline.config.investigation_timeout * 0.35)
                logger.info(
                    f"{agent_id} starting with timeout={agent_timeout:.0f}s",
                    agent_id=agent_id,
                )
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
                
                # Broadcast "Groq synthesising" update so the card shows this step
                if (pipeline.config.llm_enable_post_synthesis
                        and pipeline.config.llm_api_key
                        and pipeline.config.llm_provider != "none"
                        and findings):
                    await broadcast_update(
                        ws_session_id,
                        BriefUpdate(
                            type="AGENT_UPDATE",
                            session_id=ws_session_id,
                            agent_id=agent_id,
                            agent_name=agent_name,
                            message="🤖 Groq synthesising tool findings into forensic narrative…",
                            data={"status": "running",
                                  "thinking": "🤖 Groq synthesising tool findings into forensic narrative…"},
                        )
                    )

                # Format findings
                is_unsupported = any(getattr(f, 'finding_type', '') == "Format not supported" for f in findings)
                
                if is_unsupported:
                    base_name = evidence_artifact.metadata.get("original_filename", os.path.basename(evidence_file_path))
                    clean_text = f"{agent_name} does not support {base_name}. {agent_name} skipped forensic analysis."
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
            
            # Build completion message — prefer the most informative finding
            confidence = 0.0
            finding_summary = f"{agent_name} analysis complete."
            if result.findings:
                confidences = [
                    f.get("confidence_raw", 0.5) if isinstance(f, dict) else 0.5
                    for f in result.findings
                ]
                confidence = sum(confidences) / len(confidences) if confidences else 0.5

                # Priority: ELA/key forensic finding > longest > first
                _PRIORITY_TOOLS = {
                    "agent1": ["ela_full_image", "jpeg_ghost_detect", "noise_fingerprint", "copy_move_detect", "frequency_domain_analysis"],
                    "agent2": ["anti_spoofing_detect", "audio_splice_detect", "speaker_diarize"],
                    "agent3": ["object_detection", "lighting_consistency", "contraband_database"],
                    "agent4": ["optical_flow_analysis", "face_swap_detection", "deepfake_frequency_check"],
                    "agent5": ["exif_extract", "hex_signature_scan", "gps_timezone_validate", "steganography_scan"],
                }
                priority_tools = _PRIORITY_TOOLS.get(agent_id.lower(), [])
                finding_summaries = []
                priority_summaries = []
                for f in result.findings:
                    if isinstance(f, dict) and f.get("reasoning_summary"):
                        summary_text = f["reasoning_summary"]
                        tool = f.get("metadata", {}).get("tool_name", "") if isinstance(f.get("metadata"), dict) else ""
                        finding_summaries.append(summary_text)
                        if tool in priority_tools:
                            priority_summaries.append(summary_text)

                if priority_summaries:
                    # Use the most informative priority finding
                    best = max(priority_summaries, key=len)
                elif finding_summaries:
                    best = max(finding_summaries, key=len)
                else:
                    best = ""

                if best:
                    finding_summary = best[:800] if len(best) > 800 else best
            elif result.error:
                finding_summary = f"Error: {result.error[:120]}"
            
            # Compute tool error rate from findings metadata
            tool_error_count = sum(
                1 for f in result.findings
                if isinstance(f, dict)
                and isinstance(f.get("metadata"), dict)
                and f["metadata"].get("court_defensible") is False
            ) if result.findings else 0
            tool_total = len(result.findings) if result.findings else 0
            tool_error_rate = round(tool_error_count / tool_total, 3) if tool_total > 0 else 0.0

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
                        "tool_error_rate": tool_error_rate,
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
        
        # Shared Gemini context injected by Agent1 for Agents 3 and 5
        _agent1_gemini_result: dict = {}

        async def run_agent_deep_pass(
            agent_id: str, agent_name: str, agent, initial_result: AgentLoopResult
        ):
            """
            Run one agent's deep analysis pass.

            Steps:
            1. Broadcast "loading" AGENT_UPDATE so the card shows activity immediately.
            2. Start heartbeat on the deep WM namespace ({agent_id}_deep).
            3. Run agent.run_deep_investigation() — returns only NEW deep findings.
            4. If Agent1, extract Gemini result and inject into Agent3 + Agent5.
            5. Run Groq synthesis on deep findings.
            6. Broadcast AGENT_COMPLETE with deep-only findings count + summary.
            """
            nonlocal _agent1_gemini_result

            _deep_phrase_map = {
                "Agent1": "🔬 Loading Gemini vision + ELA anomaly deep pass…",
                "Agent2": "🎙️ Running heavy audio ML models — anti-spoofing, splice detection…",
                "Agent3": "👁️ Running Gemini scene analysis + advanced object cross-validation…",
                "Agent4": "🎬 Running deepfake frequency check + face-swap detection…",
                "Agent5": "📊 Running ML metadata anomaly scoring + Gemini metadata cross-validation…",
            }
            start_phrase = _deep_phrase_map.get(agent_id,
                f"🔬 {agent_name} — loading heavy ML models for deep analysis…")

            try:
                # Step 1: Signal start so card becomes active immediately
                await broadcast_update(
                    ws_session_id,
                    BriefUpdate(
                        type="AGENT_UPDATE",
                        session_id=ws_session_id,
                        agent_id=agent_id,
                        agent_name=agent_name,
                        message=start_phrase,
                        data={"status": "running", "thinking": start_phrase},
                    )
                )

                # Step 2: Heartbeat on the isolated deep WM namespace
                deep_agent_id = f"{agent_id}_deep"
                deep_heartbeat_done = asyncio.Event()
                heartbeat_task = asyncio.create_task(
                    make_heartbeat(
                        agent_id, agent_name,
                        agent.working_memory, deep_heartbeat_done,
                        deep_namespace=deep_agent_id,
                    )
                )

                # Step 3: Run deep investigation
                # Returns ONLY new deep findings (initial findings stay in agent._findings)
                deep_timeout = min(300, pipeline.config.investigation_timeout)
                try:
                    deep_findings_raw = await asyncio.wait_for(
                        agent.run_deep_investigation(),
                        timeout=deep_timeout,
                    )
                except asyncio.TimeoutError:
                    deep_findings_raw = []
                    logger.error(f"{agent_id} deep pass timed out after {deep_timeout}s")
                    await broadcast_update(
                        ws_session_id,
                        BriefUpdate(
                            type="AGENT_UPDATE",
                            session_id=ws_session_id,
                            agent_id=agent_id,
                            agent_name=agent_name,
                            message=f"⚠️ {agent_name} deep analysis timed out after {deep_timeout:.0f}s — partial results kept.",
                            data={"status": "running",
                                  "thinking": f"⚠️ Timeout after {deep_timeout:.0f}s — saving partial results…"},
                        )
                    )
                except Exception as tool_err:
                    deep_findings_raw = []
                    err_msg = str(tool_err)[:120]
                    logger.error(f"{agent_id} deep pass tool error: {tool_err}")
                    await broadcast_update(
                        ws_session_id,
                        BriefUpdate(
                            type="AGENT_UPDATE",
                            session_id=ws_session_id,
                            agent_id=agent_id,
                            agent_name=agent_name,
                            message=f"⚠️ Tool error in {agent_name}: {err_msg}",
                            data={"status": "running",
                                  "thinking": f"⚠️ Tool error — {err_msg}"},
                        )
                    )
                finally:
                    deep_heartbeat_done.set()
                    try:
                        await asyncio.wait_for(heartbeat_task, timeout=2.0)
                    except Exception:
                        heartbeat_task.cancel()

                # Step 4: If Agent1, extract Gemini result and share with Agent3 + Agent5
                if agent_id == "Agent1":
                    try:
                        gemini_result = getattr(agent, "_gemini_vision_result", {})
                        if not gemini_result and deep_findings_raw:
                            for f in deep_findings_raw:
                                tool = (f.metadata.get("tool_name", "") if hasattr(f, "metadata") else "")
                                if "gemini" in tool.lower():
                                    gemini_result = f.metadata if hasattr(f, "metadata") else {}
                                    break
                        if gemini_result:
                            _agent1_gemini_result = gemini_result
                            # Import and inject into Agent3 and Agent5
                            from agents.agent3_object import Agent3Object
                            from agents.agent5_metadata import Agent5Metadata
                            Agent3Object.inject_agent1_context(gemini_result)
                            Agent5Metadata.inject_agent1_context(gemini_result)
                            logger.info(
                                "Agent1 Gemini result injected into Agent3 + Agent5",
                                has_content_type=bool(gemini_result.get("gemini_content_type")),
                                has_objects=bool(gemini_result.get("gemini_detected_objects")),
                                has_text=bool(gemini_result.get("gemini_extracted_text")),
                            )
                    except Exception as ctx_err:
                        logger.warning(f"Could not inject Agent1 Gemini context: {ctx_err}")

                # Step 5: Prepare deep-only findings list for the broadcast
                deep_findings_serial: list[dict] = []
                for f in (deep_findings_raw or []):
                    if hasattr(f, "model_dump"):
                        deep_findings_serial.append(f.model_dump(mode="json"))
                    elif isinstance(f, dict):
                        deep_findings_serial.append(f)

                # Update initial_result.findings to include combined (initial + deep)
                # The arbiter reads initial_result so it gets all findings.
                # Use self._findings which already holds combined after run_deep_investigation().
                combined_serial: list[dict] = []
                for f in (agent._findings or []):
                    if hasattr(f, "model_dump"):
                        combined_serial.append(f.model_dump(mode="json"))
                    elif isinstance(f, dict):
                        combined_serial.append(f)
                if combined_serial:
                    initial_result.findings = combined_serial

                # Step 6: Build AGENT_COMPLETE summary from deep-only findings
                conf_list = [
                    (f.get("confidence_raw", 0.5) if isinstance(f, dict) else 0.5)
                    for f in (deep_findings_serial or combined_serial)
                ]
                confidence = (sum(conf_list) / len(conf_list)) if conf_list else 0.5

                gemini_summaries, other_summaries = [], []
                for f in deep_findings_serial:
                    if not isinstance(f, dict) or not f.get("reasoning_summary"):
                        continue
                    tool = (f.get("metadata", {}) or {}).get("tool_name", "")
                    summary = f["reasoning_summary"]
                    if "gemini" in tool.lower() or "gemini" in f.get("finding_type", "").lower():
                        gemini_summaries.append(summary)
                    else:
                        other_summaries.append(summary)

                if gemini_summaries:
                    best_deep = max(gemini_summaries, key=len)
                elif other_summaries:
                    best_deep = max(other_summaries, key=len)
                elif combined_serial:
                    best_deep = f"{agent_name} deep analysis complete with {len(deep_findings_serial)} new finding(s)."
                else:
                    best_deep = f"{agent_name} deep analysis complete."

                finding_summary = f"🔬 Deep — {best_deep[:900]}"

                # Compute deep-only tool error rate
                deep_err_count = sum(
                    1 for f in deep_findings_serial
                    if isinstance(f, dict)
                    and isinstance(f.get("metadata"), dict)
                    and f["metadata"].get("court_defensible") is False
                )
                deep_total = len(deep_findings_serial)
                deep_err_rate = round(deep_err_count / deep_total, 3) if deep_total > 0 else 0.0

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
                            "findings_count": len(deep_findings_serial),
                            "error": None,
                            "tool_error_rate": deep_err_rate,
                            "deep_analysis_pending": False,
                        },
                    )
                )

            except Exception as e:
                logger.error(f"Deep pass failed for {agent_id}: {e}", exc_info=True)
                await broadcast_update(
                    ws_session_id,
                    BriefUpdate(
                        type="AGENT_COMPLETE",
                        session_id=ws_session_id,
                        agent_id=agent_id,
                        agent_name=agent_name,
                        message=f"⚠️ {agent_name} deep analysis encountered an error.",
                        data={
                            "status": "error",
                            "confidence": 0.0,
                            "findings_count": 0,
                            "error": str(e)[:120],
                            "deep_analysis_pending": False,
                        },
                    )
                )
        
        # ── Track which agents were active (not skipped) ─────────────────────
        _SKIP_FINDING_TYPES = {"file type not applicable", "format not supported",
                               "file type not applicable"}

        def _agent_was_active(result_obj: AgentLoopResult) -> bool:
            """True when the agent ran real tools (not just a file-type skip)."""
            if not result_obj.findings:
                return False
            return not all(
                (f.get("finding_type", "") if isinstance(f, dict)
                 else getattr(f, "finding_type", "")).lower()
                in _SKIP_FINDING_TYPES
                for f in result_obj.findings
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
                        message=f"Error: {str(r)[:80]}",
                        data={"status": "error", "confidence": 0.0,
                              "findings_count": 0, "error": str(r)[:120]},
                    )
                )
            else:
                result_obj, agent_instance = r
                results.append(result_obj)
                
                # Only queue deep pass for agents that actually ran during initial pass
                if (agent_instance
                        and len(agent_instance.deep_task_decomposition) > 0
                        and _agent_was_active(result_obj)):
                    deep_pass_coroutines.append(
                        (agent_id, agent_name, agent_instance, result_obj)
                    )
                elif agent_instance and not _agent_was_active(result_obj):
                    logger.info(f"Deep pass skipped for {agent_id} — agent was inactive during initial pass")
        
        # Always pause here to give the user the choice (Accept vs Deep Analysis)
        # Even if there are no deep tasks, the user should see the initial findings
        logger.info("Initial analysis complete. Awaiting deep analysis decision...")
        await broadcast_update(
            ws_session_id,
            BriefUpdate(
                type="PIPELINE_PAUSED",
                session_id=ws_session_id,
                agent_id=None,
                agent_name=None,
                message="Initial analysis complete. Ready for deep analysis.",
                data={
                    "status": "awaiting_decision",
                    "deep_analysis_pending": bool(deep_pass_coroutines),
                    "agents_completed": len([r for r in results if r is not None]),
                },
            )
        )
        
        await getattr(pipeline, "deep_analysis_decision_event").wait()
        
        if getattr(pipeline, "run_deep_analysis_flag") and deep_pass_coroutines:
            logger.info(f"Running deep analysis for {len(deep_pass_coroutines)} agents…")
            await broadcast_update(
                ws_session_id,
                BriefUpdate(
                    type="AGENT_UPDATE",
                    session_id=ws_session_id,
                    agent_id=None,
                    agent_name=None,
                    message=f"🔬 Deep analysis starting — {len(deep_pass_coroutines)} agent(s) loading heavy ML models…",
                    data={"status": "running",
                          "thinking": f"Deep analysis starting for {len(deep_pass_coroutines)} agent(s)…"},
                )
            )
            # Agent1 must finish first (Gemini result injected into Agent3 + Agent5)
            # Run Agent1 separately, then run the rest concurrently.
            agent1_tuple = next((t for t in deep_pass_coroutines if t[0] == "Agent1"), None)
            others = [t for t in deep_pass_coroutines if t[0] != "Agent1"]

            if agent1_tuple:
                try:
                    await run_agent_deep_pass(*agent1_tuple)
                except Exception as _e1:
                    logger.error(f"Agent1 deep pass raised: {_e1}")

            if others:
                await asyncio.gather(
                    *[run_agent_deep_pass(*t) for t in others],
                    return_exceptions=True,
                )
        elif getattr(pipeline, "run_deep_analysis_flag") and not deep_pass_coroutines:
            logger.info("Deep analysis requested but no deep tasks available for this file type.")
        else:
            logger.info("User skipped deep analysis.")
        
        # Broadcast arbiter is about to run before returning results to pipeline
        await broadcast_update(
            ws_session_id,
            BriefUpdate(
                type="AGENT_UPDATE",
                session_id=ws_session_id,
                agent_id="Arbiter",
                agent_name="Council Arbiter",
                message="Synthesizing all agent findings with Groq...",
                data={"status": "deliberating", "thinking": "Running council deliberation..."},
            )
        )
        
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

        # ── Persist completed report to PostgreSQL ─────────────────────────
        # This is the key production-hardening step: once a report is written
        # to the DB, it survives backend restarts and is queryable by any
        # replica without needing the in-memory pipeline object.
        try:
            from core.session_persistence import get_session_persistence
            persistence = await get_session_persistence()
            await persistence.save_report(
                session_id=session_id,
                case_id=case_id,
                investigator_id=investigator_id,
                report_data=report.model_dump(mode="json"),
            )
            await persistence.update_session_status(session_id, "completed")
            logger.info("Report persisted to database", session_id=session_id)
        except Exception as persist_err:
            # Non-fatal: report is still in-memory; log but don't crash
            logger.error(
                "Failed to persist report to database",
                session_id=session_id,
                error=str(persist_err),
            )

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
            # Persist failure status so other replicas can report it
            try:
                from core.session_persistence import get_session_persistence
                persistence = await get_session_persistence()
                await persistence.update_session_status(
                    session_id, "error", error_message=error_msg
                )
            except Exception:
                pass  # best-effort; already logged above
        try:
            if os.path.exists(evidence_file_path):
                os.unlink(evidence_file_path)
        except Exception as e:
            logger.warning(f"Failed to clean up temp file: {e}")
        # Remove pipeline from active set once fully done to free resources.
        # The report is cached in _final_reports for the report endpoint to read.
        _active_pipelines.pop(session_id, None)

        # D2: clean up WebSocket connections for this session now that it's done.
        _websocket_connections.pop(session_id, None)

        # D1: evict stale entries from _final_reports (older than 24 hours).
        # This prevents unbounded growth when many investigations complete without
        # their reports being fetched.  O(n) scan runs once per completed session.
        from datetime import datetime, timezone as _tz
        cutoff = datetime.now(_tz.utc).timestamp() - 86_400
        stale = [
            sid for sid, (_, cached_at) in list(_final_reports.items())
            if cached_at.timestamp() < cutoff
        ]
        for sid in stale:
            _final_reports.pop(sid, None)
        if stale:
            logger.debug("Evicted stale report cache entries", count=len(stale))


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
    
    # Check if the event has already been set (decision already made) — return gracefully
    if pipeline.deep_analysis_decision_event.is_set():
        logger.info(
            "Resume called but decision already made — returning idempotent 200",
            session_id=session_id,
        )
        return {
            "status": "already_resumed",
            "session_id": session_id,
            "deep_analysis": request.deep_analysis,
            "message": "Investigation already resumed"
        }
    
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
