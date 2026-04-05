"""
Investigation Routes
====================

Routes for starting and managing forensic investigations with
real-time WebSocket updates and two-phase HITL pipeline support.

Modules extracted:
  - _rate_limiting: Per-user rate limiting and daily cost quota
  - Rate limiting, cost quota, and WebSocket management are imported
    from their respective modules to keep this file focused on route handlers.
"""

import asyncio
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Form, status

from core.auth import get_current_user, User

from api.routes.metrics import (
    increment_investigations_started,
    increment_investigations_completed,
    increment_investigations_failed,
)
from api.schemas import (
    BriefUpdate,
    InvestigationResponse,
)
from core.config import get_settings
from core.severity import assign_severity_tier
from core.structured_logging import get_logger
from orchestration.pipeline import ForensicCouncilPipeline, AgentLoopResult

# Import extracted modules
from api.routes._rate_limiting import (
    check_investigation_rate_limit,
    check_daily_cost_quota,
)
from api.routes._session_state import (
    _active_pipelines,
    _final_reports,
    _active_tasks,
    AGENT_NAMES,
    evict_stale_sessions,
    set_active_pipeline,
    set_active_pipeline_metadata,
    set_active_task,
    set_final_report,
    get_active_pipeline,
    get_all_active_pipelines,
    get_active_pipelines_count,
    remove_active_pipeline,
    pop_active_task,
    get_session_websockets,
    clear_session_websockets,
    cleanup_connections,
    broadcast_update,
)

logger = get_logger(__name__)
settings = get_settings()


def _assign_severity_tier(f: Any) -> str:
    """Assign INFO/LOW/MEDIUM/HIGH/CRITICAL to a finding. Uses shared logic."""
    return assign_severity_tier(f)


router = APIRouter(prefix="/api/v1", tags=["investigation"])

# Allowed MIME types (declared early — used in start_investigation)
ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
    "image/gif",
    "image/bmp",
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp4",
    "audio/flac",
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

# Allowed file extensions — must match an accepted MIME type
_ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".tiff",
        ".tif",
        ".webp",
        ".gif",
        ".bmp",
        ".mp4",
        ".mov",
        ".avi",
        ".wav",
        ".mp3",
        ".m4a",
        ".flac",
    }
)

# Strict allow-list pattern for case_id and investigator_id.
# Alphanumerics, hyphens, underscores, and dots only — prevents log injection,
# shell metacharacter injection, and DB issues with unusual unicode.
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_\-\.]{1,128}$")


def _validate_safe_id(value: str, field_name: str) -> None:
    """Raise 422 if value contains unsafe characters."""
    if not _SAFE_ID_RE.match(value):
        logger.warning(
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
    await check_investigation_rate_limit(current_user.user_id)

    # ── Per-user daily cost quota ─────────────────────────────────────────────
    await check_daily_cost_quota(current_user.user_id, current_user.role.value)

    # ── MIME type check ───────────────────────────────────────────────────────
    # Strip parameters (e.g. "image/jpeg; charset=utf-8" → "image/jpeg") before
    # checking the allow-list — browsers can append extra content-type params.
    raw_content_type = (file.content_type or "").split(";")[0].strip().lower()
    if raw_content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File type '{raw_content_type}' is not allowed. "
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

    # ── Stage file to /tmp (streaming — avoids loading entire file into RAM) ─
    tmp_path = Path(tempfile.gettempdir()) / f"{session_id}{file_extension}"
    try:
        # Stream upload to disk with size enforcement
        import hashlib as _hl

        hasher = _hl.sha256()
        total_size = 0
        chunk_size = 1024 * 1024  # 1 MB chunks
        with open(tmp_path, "wb") as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > MAX_FILE_SIZE:
                    f.close()
                    tmp_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=400,
                        detail=f"File size exceeds the {MAX_FILE_SIZE // (1024 * 1024)} MB limit.",
                    )
                hasher.update(chunk)
                f.write(chunk)

        if total_size == 0:
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        content_hash = hasher.hexdigest()

        # ── Request deduplication: hash content + case_id ─────────────────
        dedup_key = f"dedup:{case_id}:{content_hash}"
        try:
            from infra.redis_client import get_redis_client

            _redis = await get_redis_client()
            if _redis:
                existing_session = await _redis.get(dedup_key)
                if existing_session:
                    logger.info(
                        "Duplicate investigation detected — returning existing session",
                        content_hash=content_hash[:16],
                        existing_session=existing_session,
                    )
                    tmp_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Duplicate evidence detected. An investigation for this "
                            f"file already exists: session {existing_session}"
                        ),
                        headers={"X-Existing-Session": existing_session},
                    )
                # Mark this content as being processed (TTL = investigation timeout + 60s)
                await _redis.set(
                    dedup_key, session_id, ex=settings.investigation_timeout + 60
                )
        except HTTPException:
            raise
        except Exception as _e:
            logger.debug("Redis investigation deduplication failed (non-fatal)", error=str(_e))
    except HTTPException:
        if tmp_path.exists():
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception as _e:
                logger.debug("Temp file cleanup failed", error=str(_e))
        raise
    except Exception as e:
        logger.error("Failed to stage uploaded file", error=str(e))
        if tmp_path.exists():
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception as _e:
                logger.debug("Temp file cleanup failed", error=str(_e))
        raise HTTPException(status_code=500, detail="Failed to save uploaded file.")

    # ── 3. Content-based MIME Validation (python-magic) ──────────────────
    import magic

    try:
        # Read only the first 2048 bytes from disk for magic detection
        with open(tmp_path, "rb") as _f:
            head = _f.read(2048)
        mime = magic.from_buffer(head, mime=True)
        claimed_ext = os.path.splitext(file.filename)[1].lower()

        is_valid_mime = False
        if mime.startswith("image/"):
            is_valid_mime = claimed_ext in [
                ".jpg",
                ".jpeg",
                ".png",
                ".gif",
                ".webp",
                ".bmp",
                ".tiff",
                ".tif",
            ]
        elif mime.startswith("video/"):
            is_valid_mime = claimed_ext in [".mp4", ".mov", ".avi", ".mkv"]
        else:
            is_valid_mime = False

        if not is_valid_mime:
            raise HTTPException(
                status_code=400,
                detail=f"Security violation: File content (detected as {mime}) does not match extension {claimed_ext}.",
            )
    except HTTPException:
        if tmp_path.exists():
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception as _e:
                logger.debug("Temp file cleanup failed", error=str(_e))
        raise
    except Exception as e:
        logger.error("MIME validation failed", error=str(e))
        if tmp_path.exists():
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception as _e:
                logger.debug("Temp file cleanup failed", error=str(_e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File validation failed",
        )

    # ── 3b. File structure validation (adversarial input guard) ────────────
    # Verify the file is structurally valid before passing to ML tools.
    # Catches malformed images, truncated files, and basic zip-bombs-in-image-headers.
    if mime.startswith("image/") and mime != "image/gif":
        try:
            from PIL import Image

            with Image.open(str(tmp_path)) as img:
                img.verify()  # structural integrity check — does not decode pixels
            # Re-open after verify() (verify() closes the image)
            with Image.open(str(tmp_path)) as img2:
                w, h = img2.size
            # Reject absurdly large dimensions (potential OOM during ELA/FFT)
            max_pixels = 100_000_000  # 100 megapixels
            if w * h > max_pixels:
                raise HTTPException(
                    status_code=400,
                    detail=f"Image dimensions {w}x{h} exceed maximum {max_pixels} pixels. "
                    f"Possible adversarial input.",
                )
            logger.debug("Image structure validation passed", width=w, height=h)
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("Image structure validation failed — marking as potentially corrupt", error=str(e))
            from core.working_memory import get_working_memory
            try:
                wm = await get_working_memory()
                await wm.add_metadata(session_id, "image_structure_valid", False)
            except Exception:
                pass

    pipeline = ForensicCouncilPipeline()
    set_active_pipeline(session_id, pipeline)
    task = asyncio.create_task(
        run_investigation_task(
            session_id=session_id,
            pipeline=pipeline,
            evidence_file_path=str(tmp_path),
            case_id=case_id,
            investigator_id=investigator_id,
            original_filename=file.filename or None,
        )
    )
    set_active_task(session_id, task)

    # ── 4. Submit to Redis Queue ──────────────────────────────────────────────
    try:
        from orchestration.investigation_queue import get_investigation_queue
        
        queue = get_investigation_queue()
        await queue.submit(
            session_id=session_id,
            case_id=case_id,
            investigator_id=investigator_id,
            evidence_file_path=str(tmp_path),
            original_filename=file.filename or None,
        )
    except Exception as queue_err:
        logger.warning(
            "Failed to queue investigation in Redis", session_id=session_id, error=str(queue_err)
        )
        logger.debug("Leaving temp file in place for in-process investigation")
        logger.warning(
            "Queue handoff failed; in-process investigation will continue",
            session_id=session_id,
        )

    # Store initial metadata in Redis
    await set_active_pipeline_metadata(session_id, {
        "status": "running",
        "brief": "Initialising forensic pipeline...",
        "case_id": case_id,
        "investigator_id": investigator_id,
        "file_path": str(tmp_path),
        "original_filename": file.filename,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    increment_investigations_started()
    logger.info(
        "Investigation started",
        session_id=session_id,
        case_id=case_id,
        content_type=file.content_type,
        size_bytes=total_size,
    )

    # ── Register session in DB immediately (best-effort, non-blocking) ────────
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
            logger.warning(
                "Could not register session in DB", session_id=session_id, error=str(e)
            )

    asyncio.create_task(_register_session_async())

    return InvestigationResponse(
        session_id=session_id,
        case_id=case_id,
        status="started",
        message=f"Investigation started for {file.filename or 'evidence'}. Track status via WebSocket.",
    )


async def _wrap_pipeline_with_broadcasts(
    pipeline: ForensicCouncilPipeline,
    session_id: str,
    evidence_file_path: str,
    case_id: str,
    investigator_id: str,
    original_filename: str | None = None,
):
    """
    Wrap the pipeline execution to broadcast per-agent WebSocket updates.

    FIXES:
    - Faster heartbeat (0.2s instead of 1.0s)
    - More aggressive thinking text updates
    - Better state management
    """
    ws_session_id = session_id

    # Hook custody logger for real-time thinking updates
    def instrument_logger(logger_obj):
        original_log_entry = logger_obj.log_entry

        async def instrumented_log_entry(**kwargs):
            result = await original_log_entry(**kwargs)

            entry_type = kwargs.get("entry_type")
            content = kwargs.get("content", {})
            agent_id = kwargs.get("agent_id")

            type_val = getattr(entry_type, "value", str(entry_type))

            if type_val == "HITL_CHECKPOINT" and isinstance(content, dict):
                agent_name = AGENT_NAMES.get(agent_id, agent_id)
                await broadcast_update(
                    ws_session_id,
                    BriefUpdate(
                        type="HITL_CHECKPOINT",
                        session_id=ws_session_id,
                        agent_id=agent_id,
                        agent_name=agent_name,
                        message=f"🚨 HITL Checkpoint: {content.get('reason', 'Review required')}",
                        data={
                            "status": "paused",
                            "checkpoint": {
                                "id": content.get("checkpoint_id"),
                                "agent_id": agent_id,
                                "reason": content.get("reason"),
                                "brief": content.get("brief"),
                            },
                        },
                    ),
                )
            elif type_val in ("THOUGHT", "ACTION") and isinstance(content, dict):
                if content.get("action") == "session_start":
                    return result

                agent_name = AGENT_NAMES.get(agent_id, agent_id)

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
                    ),
                )
            return result

        logger_obj.log_entry = instrumented_log_entry

    if pipeline.custody_logger:
        instrument_logger(pipeline.custody_logger)

    # Initialise arbiter step tracking on the pipeline so getArbiterStatus can read it
    pipeline._arbiter_step = ""

    async def instrumented_run(evidence_artifact, session_id=None, *args, **kwargs):
        """Run each agent SEQUENTIALLY with improved real-time updates."""

        # By the time this runs, pipeline._setup_infrastructure() has already created
        # pipeline.arbiter. Hook it so the arbiter can broadcast step-progress updates.
        async def _arbiter_step_hook(msg: str) -> None:
            pipeline._arbiter_step = msg
            await broadcast_update(
                ws_session_id,
                BriefUpdate(
                    type="AGENT_UPDATE",
                    session_id=ws_session_id,
                    agent_id=None,
                    agent_name=None,
                    message=f"🔮 {msg}",
                    data={"status": "deliberating", "thinking": f"🔮 {msg}"},
                ),
            )

        if pipeline.arbiter is not None:
            pipeline.arbiter._step_hook = _arbiter_step_hook

        mime = evidence_artifact.metadata.get("mime_type", "application/octet-stream")

        _AGENT_MIME_SUPPORT = {
            "Agent1": {
                "image/jpeg",
                "image/png",
                "image/gif",
                "image/webp",
                "image/bmp",
                "image/tiff",
            },
            "Agent2": {
                "audio/wav",
                "audio/x-wav",
                "audio/mpeg",
                "audio/mp4",
                "audio/flac",
                "video/mp4",
                "video/x-msvideo",
                "video/quicktime",
            },
            # Agent3 is YOLO/object-detection on still frames only — no raw video
            "Agent3": {
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/bmp",
                "image/gif",
                "image/tiff",
            },
            "Agent4": {"video/mp4", "video/x-msvideo", "video/quicktime"},
            # Agent5 is metadata forensics — runs on every supported MIME type
            "Agent5": {
                "image/jpeg",
                "image/png",
                "image/tiff",
                "image/webp",
                "image/gif",
                "image/bmp",
                "video/mp4",
                "video/quicktime",
                "video/x-msvideo",
                "audio/wav",
                "audio/x-wav",
                "audio/mpeg",
                "audio/mp4",
                "audio/flac",
            },
        }

        from agents.agent1_image import Agent1Image
        from agents.agent2_audio import Agent2Audio
        from agents.agent3_object import Agent3Object
        from agents.agent4_video import Agent4Video
        from agents.agent5_metadata import Agent5Metadata
        from core.working_memory import WorkingMemory

        agent_configs = [
            (
                "Agent1",
                "Image Forensics",
                Agent1Image,
                "🔬 Launching ELA engine — scanning for pixel-level anomalies…",
            ),
            (
                "Agent2",
                "Audio Forensics",
                Agent2Audio,
                "🎙️ Establishing voice-count baseline with diarization…",
            ),
            (
                "Agent3",
                "Object Detection",
                Agent3Object,
                "👁️ Loading YOLO model — running primary object detection…",
            ),
            (
                "Agent4",
                "Video Forensics",
                Agent4Video,
                "🎬 Starting optical flow analysis — building temporal heatmap…",
            ),
            (
                "Agent5",
                "Metadata Forensics",
                Agent5Metadata,
                "📋 Extracting EXIF fields — checking for mandatory field gaps…",
            ),
        ]

        # Broadcast a "queued" status for ALL agents immediately so the frontend
        # sees every agent card (allForensicAgentsLive becomes true) without
        # waiting for sequential execution to reach each one.
        for _aid, _aname, _, _ in agent_configs:
            await broadcast_update(
                ws_session_id,
                BriefUpdate(
                    type="AGENT_UPDATE",
                    session_id=ws_session_id,
                    agent_id=_aid,
                    agent_name=_aname,
                    message=f"{_aname} queued — waiting for turn…",
                    data={
                        "status": "queued",
                        "thinking": f"{_aname} queued — waiting for turn…",
                    },
                ),
            )

        # ── Per-agent tool-action humaniser (initial AND deep pass) ──────────
        _TASK_PHRASES: dict[str, str] = {
            # Agent 1 – Image Integrity
            "ela": "🔬 Running Error Level Analysis across full image…",
            "ela anomaly block": "🧩 Classifying ELA anomaly blocks in flagged regions…",
            "jpeg ghost": "👻 Detecting JPEG ghost artifacts in suspicious regions…",
            "frequency domain analysis": "📡 Running frequency-domain analysis on contested regions…",
            "frequency-domain gan": "📡 Scanning frequency domain for GAN generation artifacts…",
            "file hash": "🔑 Verifying file hash against ingestion record…",
            "perceptual hash": "🔑 Computing perceptual hash for similarity detection…",
            "roi": "🎯 Re-analysing flagged ROIs with noise footprint…",
            "copy-move": "🔍 Checking for copy-move cloning artifacts…",
            "semantic image": "🧠 Identifying what this image actually depicts…",
            "ocr": "📄 Extracting all visible text via OCR…",
            "visible text": "📄 Extracting all visible text from image…",
            "adversarial robustness": "🛡️ Testing robustness against anti-forensics evasion…",
            "gemini": "🤖 Asking Gemini AI for deep visual forensic analysis…",
            # Agent 2 – Audio
            "speaker diarization": "🎙️ Establishing voice-count baseline with diarization…",
            "anti-spoofing": "🔊 Running anti-spoofing detection on speaker segments…",
            "prosody": "🎵 Analysing prosody and rhythm across full audio track…",
            "splice point": "✂️ Detecting ML splice points in audio segments…",
            "background noise": "🌊 Checking background noise consistency for edit points…",
            "codec fingerprint": "🔐 Fingerprinting codec chain for re-encoding events…",
            "audio-visual sync": "⏱️ Verifying audio-visual sync against video timestamps…",
            "collaborative call": "🤝 Issuing inter-agent call to Agent 4 for corroboration…",
            "cross-agent collaboration": "🤝 Running cross-agent collaboration with Agent 4…",
            "spectral perturbation": "📊 Running spectral perturbation adversarial check…",
            "codec chain": "🔐 Running advanced codec chain analysis…",
            # Agent 3 – Object/Weapon
            "full-scene primary object": "👁️ Running YOLO primary object detection on full scene…",
            "secondary classification": "🔎 Re-classifying low-confidence detections…",
            "scale and proportion": "📐 Validating object scale and proportion geometry…",
            "lighting and shadow": "💡 Checking per-object lighting and shadow consistency…",
            "contraband": "⚠️ Cross-referencing objects against contraband database…",
            "scene-level contextual": "🧠 Analysing scene for contextual incongruences…",
            "image splicing": "✂️ Running ML-based image splicing detection…",
            "camera noise fingerprint": "📷 Checking camera noise fingerprint for region consistency…",
            "inter-agent call": "🤝 Issuing inter-agent call to Agent 1 for lighting check…",
            "object detection evasion": "🛡️ Testing against object detection evasion techniques…",
            # Agent 4 – Video
            "optical flow": "🎬 Running optical flow analysis — building anomaly heatmap…",
            "frame-to-frame": "🖼️ Extracting frames and checking inter-frame consistency…",
            "explainable": "🏷️ Classifying anomalies as EXPLAINABLE or SUSPICIOUS…",
            "face-swap": "🧑‍💻 Running face-swap detection on human faces…",
            "face swap": "🧑‍💻 Running face-swap detection on human faces…",
            "rolling shutter": "📷 Validating rolling shutter behaviour vs device metadata…",
            "deepfake frequency": "📡 Running deepfake frequency analysis across full video…",
            "audio-visual timestamp": "⏱️ Correlating audio-visual timestamps with Agent 2…",
            # Agent 5 – Metadata
            "exif": "📋 Extracting all EXIF fields — logging absent mandatory fields…",
            "gps coordinates": "🌍 Cross-validating GPS coordinates against timestamp timezone…",
            "steganography": "🕵️ Scanning for hidden steganographic payload…",
            "file structure": "🗂️ Running file structure forensic analysis…",
            "hexadecimal": "🗂️ Running hex scan for software signature anomalies…",
            "cross-field consistency": "📊 Synthesising cross-field metadata consistency verdict…",
            "ml metadata anomaly": "🤖 Running ML metadata anomaly scoring…",
            "astronomical": "🔭 Running astronomical API check for GPS/timestamp validation…",
            "reverse image search": "🌐 Running reverse image search for prior online appearances…",
            "device fingerprint": "🔐 Querying device fingerprint database for claimed device…",
            "metadata spoofing": "🛡️ Testing against metadata spoofing evasion techniques…",
            # Agent 1 — new deep tools
            "prnu camera sensor": "📷 Running PRNU sensor fingerprint — cross-region source check…",
            "prnu": "📷 Analysing PRNU noise residual across image blocks…",
            "cfa demosaicing": "🌈 Checking CFA Bayer pattern consistency for splice regions…",
            "cfa": "🌈 Running CFA demosaicing pattern analysis…",
            # Agent 2 — new tools
            "voice clone": "🤖 Detecting AI voice clone and TTS synthesis artifacts…",
            "ai speech synthesis": "🤖 Analysing spectral flatness for TTS synthesis markers…",
            "enf": "⚡ Tracking Electrical Network Frequency for splice detection…",
            "electrical network": "⚡ Running ENF analysis — verifying recording timestamp…",
            # Agent 3 — new tools
            "object text ocr": "📄 Running OCR on detected object regions — extracting text…",
            "ocr on detected": "📄 Extracting license plates, IDs, and signs via OCR…",
            "document authenticity": "📑 Checking document font consistency and forgery artifacts…",
            # Agent 5 — new tools
            "c2pa": "🔏 Verifying C2PA Content Credentials and provenance chain…",
            "content credentials": "🔏 Checking for C2PA/XMP provenance markers…",
            "thumbnail mismatch": "🖼️ Comparing embedded thumbnail to main image — edit check…",
            "embedded thumbnail": "🖼️ Extracting EXIF thumbnail for post-capture edit detection…",
            # Generic
            "self-reflection": "🪞 Running self-reflection quality check on findings…",
            "submit": "📤 Submitting calibrated findings to Council Arbiter…",
            "finaliz": "✅ Finalising and packaging findings…",
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

        # ── Pipeline-level progress counter ──────────────────────────────────
        # Tracks how many agents have completed so far (updated atomically inside
        # run_single_agent). Used to broadcast real-time pipeline-level messages.
        _pipeline_completed: list[int] = [0]  # mutable int via list
        _total_supported = sum(
            1
            for _id, _, _, _ in agent_configs
            if mime in _AGENT_MIME_SUPPORT.get(_id, set())
        )

        async def make_heartbeat(
            agent_id: str,
            agent_name: str,
            target_memory: WorkingMemory,
            done_event: asyncio.Event,
            deep_namespace: str | None = None,
        ):
            """Stream live working-memory progress to the WebSocket client."""
            last_thinking = ""
            last_done = -1
            last_broadcast_time = 0.0
            task_start_time = 0.0
            _CYCLING_SUBTEXTS = [
                "analysing evidence",
                "cross-referencing patterns",
                "evaluating signals",
                "processing data",
                "running forensic checks",
                "validating results",
                "scanning for anomalies",
                "building analysis",
            ]
            _cycle_index = 0
            # Deep pass uses an isolated namespace; use it when provided
            wm_agent_id = deep_namespace if deep_namespace else agent_id
            while not done_event.is_set():
                try:
                    await asyncio.wait_for(done_event.wait(), timeout=0.2)
                    break
                except asyncio.TimeoutError:
                    # Heartbeat interval reached — continue loop to broadcast next update
                    pass
                try:
                    # Use UUID version of session_id for working memory lookup
                    _wm_session = (
                        session_id if session_id else evidence_artifact.artifact_id
                    )
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
                    completed_t = [
                        t for t in tasks_list if t.status.value == "COMPLETE"
                    ]
                    in_progress_t = [
                        t for t in tasks_list if t.status.value == "IN_PROGRESS"
                    ]
                    total = len(tasks_list)
                    done = len(completed_t)
                    thinking = ""
                    # Check if a tool just failed — show error text for one heartbeat cycle
                    last_error = getattr(wm_state, "last_tool_error", None)
                    if last_error:
                        thinking = f"⚠️ {last_error}"
                        # Clear the error from working memory so it only shows once
                        try:
                            await target_memory.update_state(
                                session_id=_wm_session,
                                agent_id=wm_agent_id,
                                updates={"last_tool_error": None},
                            )
                        except Exception:
                            logger.debug(
                                "Working memory update failed (clearing last_tool_error)",
                                exc_info=True,
                            )
                    elif in_progress_t:
                        current_task = in_progress_t[0].description
                        friendly = _humanise_task(current_task)
                        progress_frac = f" ({done + 1}/{total})" if total > 0 else ""
                        # Track elapsed time on current task
                        now = time.monotonic()
                        if task_start_time == 0 or friendly != last_thinking:
                            task_start_time = now
                        elapsed_s = int(now - task_start_time)
                        if elapsed_s >= 6:
                            # After 6s, add elapsed time and rotate subtext to show activity
                            subtext = _CYCLING_SUBTEXTS[
                                _cycle_index % len(_CYCLING_SUBTEXTS)
                            ]
                            _cycle_index += 1
                            thinking = f"{friendly.rstrip('…')}{progress_frac} — {subtext} ({elapsed_s}s)…"
                        else:
                            thinking = friendly.rstrip("…") + progress_frac + "…"
                    elif done > 0 and done >= total and total > 0:
                        thinking = "✅ Finalising findings…"
                    elif done > 0:
                        thinking = f"🔄 Cross-validating results… ({done}/{total} tasks complete)"
                    elif total > 0:
                        thinking = f"⚙️ Initialising {total} analysis tasks…"
                    else:
                        # WM state exists but no tasks yet — agent still loading.
                        # Don't overwrite the pre-broadcast phrase; skip this tick.
                        thinking = ""
                    # Send update when: text changed, done count changed, OR every 4s for long-running tasks
                    now = time.monotonic()
                    should_send = (
                        (thinking and thinking != last_thinking)
                        or (done != last_done)
                        or (thinking and (now - last_broadcast_time) >= 4.0)
                    )
                    if thinking and should_send:
                        last_thinking = thinking
                        last_done = done
                        last_broadcast_time = now
                        await broadcast_update(
                            ws_session_id,
                            BriefUpdate(
                                type="AGENT_UPDATE",
                                session_id=ws_session_id,
                                agent_id=agent_id,
                                agent_name=agent_name,
                                message=thinking,
                                data={
                                    "status": "running",
                                    "thinking": thinking,
                                    "tools_done": done,
                                    "tools_total": total,
                                },
                            ),
                        )
                except Exception as e:
                    logger.debug("Heartbeat error", error=str(e))

        async def run_single_agent(agent_id, agent_name, AgentClass, thinking_phrase):
            supported_mimes = _AGENT_MIME_SUPPORT.get(agent_id, set())
            if mime not in supported_mimes:
                # Pre-broadcast already sent "checking" state before asyncio.gather,
                # so skip the redundant update and go straight to AGENT_COMPLETE.

                # Determine a human-friendly file category name
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
                    if m.startswith("image/"):
                        supported_cats.add("images")
                    elif m.startswith("video/"):
                        supported_cats.add("video")
                    elif m.startswith("audio/"):
                        supported_cats.add("audio")
                supported_str = (
                    " and ".join(sorted(supported_cats))
                    if supported_cats
                    else "other formats"
                )

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
                            "status": "skipped",
                            "confidence": 0.0,
                            "findings_count": 0,
                            "error": f"Not applicable for {file_cat} files",
                        },
                    ),
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
                ),
            )

            agent = None  # guard: defined before try so exception handlers can safely reference it
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
                heartbeat_task = asyncio.create_task(
                    make_heartbeat(
                        agent_id, agent_name, agent.working_memory, heartbeat_done
                    )
                )

                # Per-agent timeout: generous enough for cold ML model loads,
                # but not so long that a hung agent blocks the whole UI.
                #
                # Agent1 (Image Integrity) can legitimately take longer on first run
                # (ELA + ML subprocess warm-up). Give it a higher ceiling.
                # Agent3 (Object Detection) includes OCR which can be slow on complex images.
                base_budget = float(pipeline.config.investigation_timeout)
                if agent_id == "Agent1":
                    agent_timeout = min(240, max(150, base_budget * 0.40))
                elif agent_id == "Agent3":
                    # YOLO model load (via run_in_executor) + object detection + OCR
                    # (Tesseract) + scale validation + lighting check + contraband DB.
                    # First-run model download can add 10-15s even in a thread pool.
                    agent_timeout = min(240, max(150, base_budget * 0.40))
                else:
                    # Metadata/exif tools are fast; audio/video ML tools are moderate
                    agent_timeout = min(240, max(120, base_budget * 0.35))
                logger.info(
                    f"{agent_id} starting with timeout={agent_timeout:.0f}s",
                    agent_id=agent_id,
                )
                try:
                    findings = await asyncio.wait_for(
                        agent.run_investigation(), timeout=agent_timeout
                    )
                finally:
                    heartbeat_done.set()
                    try:
                        await asyncio.wait_for(heartbeat_task, timeout=2.0)
                    except Exception:
                        logger.debug("Heartbeat task cleanup failed", exc_info=True)
                        heartbeat_task.cancel()

                # Broadcast "Groq synthesising" update so the card shows this step
                if (
                    pipeline.config.llm_enable_post_synthesis
                    and pipeline.config.llm_api_key
                    and pipeline.config.llm_provider != "none"
                    and findings
                ):
                    await broadcast_update(
                        ws_session_id,
                        BriefUpdate(
                            type="AGENT_UPDATE",
                            session_id=ws_session_id,
                            agent_id=agent_id,
                            agent_name=agent_name,
                            message="🤖 Groq synthesising tool findings into forensic narrative…",
                            data={
                                "status": "running",
                                "thinking": "🤖 Groq synthesising tool findings into forensic narrative…",
                            },
                        ),
                    )

                # Format findings
                is_unsupported = any(
                    getattr(f, "finding_type", "") == "Format not supported"
                    for f in findings
                )

                if is_unsupported:
                    base_name = evidence_artifact.metadata.get(
                        "original_filename", os.path.basename(evidence_file_path)
                    )
                    clean_text = f"{agent_name} does not support {base_name}. {agent_name} skipped forensic analysis."
                    for f in findings:
                        f.reasoning_summary = clean_text

                # Serialize react chain
                serialized_chain = []
                for step in getattr(agent, "_react_chain", []):
                    if hasattr(step, "model_dump"):
                        serialized_chain.append(step.model_dump(mode="json"))
                    elif hasattr(step, "dict"):
                        serialized_chain.append(step.dict())
                    else:
                        serialized_chain.append(step)

                result = AgentLoopResult(
                    agent_id=agent_id,
                    findings=[f.model_dump(mode="json") for f in findings],
                    reflection_report=getattr(
                        agent, "_reflection_report", None
                    ).model_dump(mode="json")
                    if getattr(agent, "_reflection_report", None)
                    else {},
                    react_chain=serialized_chain,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "Agent timed out", agent_id=agent_id, timeout=agent_timeout
                )
                result = AgentLoopResult(
                    agent_id=agent_id,
                    findings=[],
                    reflection_report={},
                    react_chain=[],
                    error=f"Timeout after {agent_timeout:.0f}s",
                )
            except Exception as e:
                logger.error(
                    "Agent failed", agent_id=agent_id, error=str(e), exc_info=True
                )
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
                # Exclude NOT_APPLICABLE findings from confidence median —
                # they carry a default ~0.75 confidence that dilutes real signal.
                _NA_FLAGS = (
                    "ela_not_applicable",
                    "ghost_not_applicable",
                    "noise_fingerprint_not_applicable",
                    "prnu_not_applicable",
                )

                def _is_na(f):
                    if not isinstance(f, dict):
                        return False
                    m = f.get("metadata") or {}
                    if any(m.get(k) for k in _NA_FLAGS):
                        return True
                    if str(m.get("verdict", "")).upper() == "NOT_APPLICABLE":
                        return True
                    if str(m.get("prnu_verdict", "")).upper() == "NOT_APPLICABLE":
                        return True
                    return False

                confidences = [
                    f.get("confidence_raw", 0.5) if isinstance(f, dict) else 0.5
                    for f in result.findings
                    if not _is_na(f)
                ]
                # Use median to avoid tools that return 0.0 (e.g. CLIP no-match)
                # dragging down the agent-level confidence unfairly.
                if confidences:
                    confidences_sorted = sorted(confidences)
                    mid = len(confidences_sorted) // 2
                    confidence = (
                        confidences_sorted[mid]
                        if len(confidences_sorted) % 2 == 1
                        else (confidences_sorted[mid - 1] + confidences_sorted[mid]) / 2
                    )
                else:
                    confidence = 0.5

                # Priority: ELA/key forensic finding > longest > first
                _PRIORITY_TOOLS = {
                    "agent1": [
                        "ela_full_image",
                        "jpeg_ghost_detect",
                        "noise_fingerprint",
                        "copy_move_detect",
                        "frequency_domain_analysis",
                    ],
                    "agent2": [
                        "anti_spoofing_detect",
                        "audio_splice_detect",
                        "speaker_diarize",
                    ],
                    "agent3": [
                        "object_detection",
                        "lighting_consistency",
                        "contraband_database",
                    ],
                    "agent4": [
                        "optical_flow_analysis",
                        "face_swap_detection",
                        "deepfake_frequency_check",
                    ],
                    "agent5": [
                        "exif_extract",
                        "hex_signature_scan",
                        "gps_timezone_validate",
                        "steganography_scan",
                    ],
                }
                priority_tools = _PRIORITY_TOOLS.get(agent_id.lower(), [])
                finding_summaries = []
                priority_summaries = []
                for f in result.findings:
                    if isinstance(f, dict) and f.get("reasoning_summary"):
                        summary_text = f["reasoning_summary"]
                        tool = (
                            f.get("metadata", {}).get("tool_name", "")
                            if isinstance(f.get("metadata"), dict)
                            else ""
                        )
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

            # Compute tool error rate — prefer agent-level counters (actual tool call results)
            # over the court_defensible proxy (which only flags failed fallbacks).
            # Agent counters track every _record_tool_result / _record_tool_error call.
            _agent_err = getattr(agent, "_tool_error_count", 0) if agent else 0
            _agent_ok = getattr(agent, "_tool_success_count", 0) if agent else 0
            _agent_total = _agent_err + _agent_ok
            if _agent_total > 0:
                tool_error_rate = round(_agent_err / _agent_total, 3)
            else:
                # Fallback: derive from court_defensible flags in findings
                _cd_err = (
                    sum(
                        1
                        for f in result.findings
                        if isinstance(f, dict)
                        and isinstance(f.get("metadata"), dict)
                        and f["metadata"].get("court_defensible") is False
                    )
                    if result.findings
                    else 0
                )
                _cd_total = len(result.findings) if result.findings else 0
                tool_error_rate = (
                    round(_cd_err / _cd_total, 3) if _cd_total > 0 else 0.0
                )

            # Prefer Groq-synthesized confidence + error rate if synthesis ran.
            # Falls back to the raw-score mean computed above.
            groq_confidence = getattr(agent, "_agent_confidence", None)
            groq_error_rate = getattr(agent, "_agent_error_rate", None)
            final_confidence = (
                groq_confidence if groq_confidence is not None else confidence
            )
            final_error_rate = (
                groq_error_rate if groq_error_rate is not None else tool_error_rate
            )

            # Pull structured verdict/section metadata from findings metadata.
            # Findings are AgentFinding objects — access .metadata directly.
            agent_verdict = None
            section_flags: list[dict] = []
            if result.findings:
                seen_sections: set[str] = set()
                for f in result.findings:
                    meta = (
                        f.get("metadata", {})
                        if isinstance(f, dict)
                        else (f.metadata if hasattr(f, "metadata") else {})
                    )
                    if agent_verdict is None:
                        agent_verdict = meta.get("agent_verdict")
                    sid = meta.get("section_id", "")
                    if sid and sid not in seen_sections:
                        seen_sections.add(sid)
                        section_flags.append(
                            {
                                "id": sid,
                                "label": meta.get("section_label", sid),
                                "flag": meta.get("section_flag", "info"),
                                "key_signal": meta.get("section_key_signal", ""),
                            }
                        )

            # Rule-based verdict fallback — used when LLM synthesis is disabled
            # or when Groq did not tag findings with agent_verdict.
            if agent_verdict is None:
                if result.findings:
                    sev_list = [
                        _assign_severity_tier(f).upper()
                        for f in result.findings
                        if isinstance(f, dict)
                    ]
                    # Exclude INFO items so NA findings don't drag down confidence ratio unexpectedly
                    total_f = sum(1 for s in sev_list if s != "INFO") or 1
                    critical = sev_list.count("CRITICAL")
                    high = sev_list.count("HIGH")
                    medium = sev_list.count("MEDIUM")
                    severe_ratio = (critical + high) / total_f

                    if critical > 0 or severe_ratio >= 0.30:
                        agent_verdict = "LIKELY_MANIPULATED"
                    elif (
                        severe_ratio >= 0.10
                        or (medium / total_f) >= 0.40
                        or (final_confidence < 0.50 and total_f > 1)
                    ):
                        agent_verdict = "INCONCLUSIVE"
                    else:
                        agent_verdict = "AUTHENTIC"
                elif result.error:
                    agent_verdict = "INCONCLUSIVE"
                else:
                    agent_verdict = "AUTHENTIC"

            # Build per-finding preview (shown in agent cards when section_flags is empty)
            findings_preview = []
            for f in result.findings:
                if not isinstance(f, dict):
                    continue
                meta = (
                    f.get("metadata", {}) if isinstance(f.get("metadata"), dict) else {}
                )
                tool = meta.get("tool_name", "") or f.get("finding_type", "")
                summary = f.get("reasoning_summary", "")
                if not summary:
                    continue
                # Strip "Tool Name: " prefix if reasoning_summary already contains it
                if tool and summary.lower().startswith(tool.lower() + ":"):
                    summary = summary[len(tool) + 1 :].strip()

                # Per-tool verdict derived from existing metadata
                na_flags = (
                    "ela_not_applicable",
                    "ghost_not_applicable",
                    "noise_fingerprint_not_applicable",
                    "prnu_not_applicable",
                    "gan_not_applicable",
                )
                is_na = any(meta.get(flag) for flag in na_flags)
                is_error = meta.get("court_defensible") is False
                severity = _assign_severity_tier(f)
                is_flagged = severity in ("CRITICAL", "HIGH", "MEDIUM")
                tool_verdict = (
                    "NOT_APPLICABLE"
                    if is_na
                    else "ERROR"
                    if is_error
                    else "FLAGGED"
                    if is_flagged
                    else "CLEAN"
                )

                # Surface Groq synthesis key_signal if available
                key_signal = meta.get("section_key_signal", "")
                section_label = meta.get("section_label", "")

                # Elapsed time — from ML subprocess (elapsed_s) or Gemini (latency_ms → s)
                elapsed_s = meta.get("elapsed_s")
                if elapsed_s is None:
                    latency_ms = meta.get("latency_ms")
                    if latency_ms is not None:
                        elapsed_s = round(float(latency_ms) / 1000, 1)

                findings_preview.append(
                    {
                        "tool": tool,
                        "summary": summary[:320],
                        "confidence": f.get("confidence_raw", 0.5),
                        "flag": meta.get("section_flag", "info"),
                        "severity": severity,
                        "verdict": tool_verdict,
                        "key_signal": key_signal,
                        "section": section_label,
                        "elapsed_s": elapsed_s,
                    }
                )

            # ── Tools ran vs skipped summary ────────────────────────────────────
            _na_flags = (
                "ela_not_applicable",
                "ghost_not_applicable",
                "noise_fingerprint_not_applicable",
                "prnu_not_applicable",
                "gan_not_applicable",
            )
            tools_ran = sum(
                1
                for f in result.findings
                if isinstance(f, dict)
                and not any((f.get("metadata") or {}).get(k) for k in _na_flags)
                and (f.get("metadata") or {}).get("court_defensible") is not False
            )
            tools_skipped = sum(
                1
                for f in result.findings
                if isinstance(f, dict)
                and any((f.get("metadata") or {}).get(k) for k in _na_flags)
            )
            tools_failed = sum(
                1
                for f in result.findings
                if isinstance(f, dict)
                and (f.get("metadata") or {}).get("court_defensible") is False
            )

            # Broadcast per-agent completion
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
                        "confidence": final_confidence,
                        "findings_count": len(result.findings),
                        "error": result.error,
                        "tool_error_rate": final_error_rate,
                        "agent_verdict": agent_verdict,
                        "section_flags": section_flags,
                        "findings_preview": findings_preview,
                        "tools_ran": tools_ran,
                        "tools_skipped": tools_skipped,
                        "tools_failed": tools_failed,
                    },
                ),
            )

            # ── Pipeline-level progress update (agent_id=None → pipelineMessage) ──
            _pipeline_completed[0] += 1
            _done = _pipeline_completed[0]
            _total = _total_supported or len(agent_configs)
            _pipeline_msgs = {
                1: "🔬 First agent reporting — analysis underway…",
                2: "🔬 Two agents reporting — forensic scan in progress…",
                3: "🔬 Three agents reporting — cross-modal validation running…",
            }
            if _done < _total:
                _pl_msg = _pipeline_msgs.get(
                    _done, f"🔬 {_done} of {_total} agents reporting findings…"
                )
            else:
                _pl_msg = f"✅ All {_total} applicable agents have reported — awaiting decision…"
            await broadcast_update(
                ws_session_id,
                BriefUpdate(
                    type="AGENT_UPDATE",
                    session_id=ws_session_id,
                    agent_id=None,
                    agent_name=None,
                    message=_pl_msg,
                    data={"status": "running", "thinking": _pl_msg},
                ),
            )

            return result, agent

        # Pre-broadcast initial state for ALL agents BEFORE asyncio.gather.
        # This is critical: if Agent1's constructor blocks the event loop (ML model loading),
        # Agents 2-5 would never get to send their own initial broadcasts, leaving those
        # cards stuck in "checking" state. Broadcasting upfront ensures ALL 5 cards
        # transition from "checking" to "running" immediately regardless of scheduling.
        # Supported agents show their analysis phrase; unsupported show "checking file type".
        for _pre_id, _pre_name, _PreClass, _pre_phrase in agent_configs:
            _pre_supported = mime in _AGENT_MIME_SUPPORT.get(_pre_id, set())
            _broadcast_phrase = (
                _pre_phrase
                if _pre_supported
                else "🔍 Checking file type compatibility…"
            )
            await broadcast_update(
                ws_session_id,
                BriefUpdate(
                    type="AGENT_UPDATE",
                    session_id=ws_session_id,
                    agent_id=_pre_id,
                    agent_name=_pre_name,
                    message=_broadcast_phrase,
                    data={"status": "running", "thinking": _broadcast_phrase},
                ),
            )

        tasks = [
            run_single_agent(agent_id, agent_name, AgentClass, thinking_phrase)
            for agent_id, agent_name, AgentClass, thinking_phrase in agent_configs
        ]

        # ── Pipeline-level initial broadcast + ticker ─────────────────────
        # Broadcast an initial pipeline message so the status bar is never
        # blank while agents are running.
        _init_pl_msg = (
            f"⚙️ {_total_supported} forensic agent{'s' if _total_supported != 1 else ''} "
            "scanning evidence in parallel…"
        )
        await broadcast_update(
            ws_session_id,
            BriefUpdate(
                type="AGENT_UPDATE",
                session_id=ws_session_id,
                agent_id=None,
                agent_name=None,
                message=_init_pl_msg,
                data={"status": "running", "thinking": _init_pl_msg},
            ),
        )

        _TICKER_PHRASES = [
            "🔬 Forensic tools running — extracting pixel-level artifacts…",
            "⚡ Cross-validating signals across all forensic domains…",
            "🧠 Pattern recognition models analysing evidence…",
            "📊 Aggregating forensic findings across active agents…",
            "🔬 Analysis in progress — building forensic evidence chain…",
            "🔍 Running advanced statistical anomaly detection…",
            "⚙️ Tool results queuing — synthesis pipeline active…",
        ]

        async def _pipeline_ticker(done_event: asyncio.Event) -> None:
            """Rotate pipeline-level status phrases every ~9 s while agents run."""
            idx = 0
            while True:
                try:
                    await asyncio.wait_for(done_event.wait(), timeout=9.0)
                    return
                except asyncio.TimeoutError:
                    pass
                if done_event.is_set():
                    return
                phrase = _TICKER_PHRASES[idx % len(_TICKER_PHRASES)]
                idx += 1
                await broadcast_update(
                    ws_session_id,
                    BriefUpdate(
                        type="AGENT_UPDATE",
                        session_id=ws_session_id,
                        agent_id=None,
                        agent_name=None,
                        message=phrase,
                        data={"status": "running", "thinking": phrase},
                    ),
                )

        _ticker_done = asyncio.Event()
        _ticker_task = asyncio.create_task(_pipeline_ticker(_ticker_done))

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        _ticker_done.set()
        try:
            await asyncio.wait_for(_ticker_task, timeout=1.0)
        except Exception:
            logger.debug("Ticker task cleanup failed", exc_info=True)
            _ticker_task.cancel()

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
            start_phrase = _deep_phrase_map.get(
                agent_id,
                f"🔬 {agent_name} — loading heavy ML models for deep analysis…",
            )

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
                    ),
                )

                # Step 2: Heartbeat on the isolated deep WM namespace
                deep_agent_id = f"{agent_id}_deep"
                deep_heartbeat_done = asyncio.Event()
                heartbeat_task = asyncio.create_task(
                    make_heartbeat(
                        agent_id,
                        agent_name,
                        agent.working_memory,
                        deep_heartbeat_done,
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
                    logger.error(
                        "Deep pass timed out", agent_id=agent_id, timeout=deep_timeout
                    )
                    await broadcast_update(
                        ws_session_id,
                        BriefUpdate(
                            type="AGENT_UPDATE",
                            session_id=ws_session_id,
                            agent_id=agent_id,
                            agent_name=agent_name,
                            message=f"⚠️ {agent_name} deep analysis timed out after {deep_timeout:.0f}s — partial results kept.",
                            data={
                                "status": "running",
                                "thinking": f"⚠️ Timeout after {deep_timeout:.0f}s — saving partial results…",
                            },
                        ),
                    )
                except Exception as tool_err:
                    deep_findings_raw = []
                    err_msg = str(tool_err)[:120]
                    logger.error(
                        "Deep pass tool error", agent_id=agent_id, error=str(tool_err)
                    )
                    await broadcast_update(
                        ws_session_id,
                        BriefUpdate(
                            type="AGENT_UPDATE",
                            session_id=ws_session_id,
                            agent_id=agent_id,
                            agent_name=agent_name,
                            message=f"⚠️ Tool error in {agent_name}: {err_msg}",
                            data={
                                "status": "running",
                                "thinking": f"⚠️ Tool error — {err_msg}",
                            },
                        ),
                    )
                finally:
                    deep_heartbeat_done.set()
                    try:
                        await asyncio.wait_for(heartbeat_task, timeout=2.0)
                    except Exception:
                        heartbeat_task.cancel()

                # Step 4: Gemini context injection for Agent3/5 is handled by the
                # outer block after run_agent_deep_pass returns (line ~1700).
                # Injecting here is redundant and risks overwriting valid context
                # with {"gemini_unavailable": True} if the second injection raises.

                # Step 5: Prepare deep-only findings list for the broadcast
                deep_findings_serial: list[dict] = []
                for f in deep_findings_raw or []:
                    if hasattr(f, "model_dump"):
                        deep_findings_serial.append(f.model_dump(mode="json"))
                    elif isinstance(f, dict):
                        deep_findings_serial.append(f)

                # Update initial_result.findings to include combined (initial + deep)
                # The arbiter reads initial_result so it gets all findings.
                # Use self._findings which already holds combined after run_deep_investigation().
                combined_serial: list[dict] = []
                for f in agent._findings or []:
                    if hasattr(f, "model_dump"):
                        combined_serial.append(f.model_dump(mode="json"))
                    elif isinstance(f, dict):
                        combined_serial.append(f)
                if combined_serial:
                    initial_result.findings = combined_serial

                # Step 6: Build AGENT_COMPLETE summary from deep-only findings.
                # Use ONLY deep_findings_serial — never fall back to combined_serial
                # which includes initial-phase findings and would contaminate the score.
                if deep_findings_serial:
                    conf_list = sorted(
                        f.get("confidence_raw", 0.5)
                        for f in deep_findings_serial
                        if isinstance(f, dict)
                    )
                    _mid = len(conf_list) // 2
                    confidence = (
                        (
                            conf_list[_mid]
                            if len(conf_list) % 2 == 1
                            else (conf_list[_mid - 1] + conf_list[_mid]) / 2
                        )
                        if conf_list
                        else 0.5
                    )
                else:
                    confidence = 0.5

                gemini_summaries, other_summaries = [], []
                for f in deep_findings_serial:
                    if not isinstance(f, dict) or not f.get("reasoning_summary"):
                        continue
                    tool = (f.get("metadata", {}) or {}).get("tool_name", "")
                    summary = f["reasoning_summary"]
                    if (
                        "gemini" in tool.lower()
                        or "gemini" in f.get("finding_type", "").lower()
                    ):
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
                    1
                    for f in deep_findings_serial
                    if isinstance(f, dict)
                    and isinstance(f.get("metadata"), dict)
                    and f["metadata"].get("court_defensible") is False
                )
                deep_total = len(deep_findings_serial)
                deep_err_rate = (
                    round(deep_err_count / deep_total, 3) if deep_total > 0 else 0.0
                )

                # Prefer Groq-synthesized scores from deep synthesis pass
                deep_groq_conf = getattr(agent, "_agent_confidence", None)
                deep_groq_err = getattr(agent, "_agent_error_rate", None)
                final_deep_conf = (
                    deep_groq_conf if deep_groq_conf is not None else confidence
                )
                final_deep_err = (
                    deep_groq_err if deep_groq_err is not None else deep_err_rate
                )

                deep_agent_verdict = None
                deep_section_flags: list[dict] = []
                for f in deep_findings_serial:
                    meta = f.get("metadata", {}) if isinstance(f, dict) else {}
                    if deep_agent_verdict is None:
                        deep_agent_verdict = meta.get("agent_verdict")
                    sid = meta.get("section_id", "")
                    if sid and not any(s["id"] == sid for s in deep_section_flags):
                        deep_section_flags.append(
                            {
                                "id": sid,
                                "label": meta.get("section_label", sid),
                                "flag": meta.get("section_flag", "info"),
                                "key_signal": meta.get("section_key_signal", ""),
                            }
                        )

                # Rule-based verdict fallback for deep pass
                if deep_agent_verdict is None:
                    if deep_findings_serial:
                        dsev = [
                            _assign_severity_tier(f).upper()
                            for f in deep_findings_serial
                            if isinstance(f, dict)
                        ]
                        dtotal = sum(1 for s in dsev if s != "INFO") or 1
                        dsevere = (dsev.count("CRITICAL") + dsev.count("HIGH")) / dtotal
                        if dsev.count("CRITICAL") > 0 or dsevere >= 0.30:
                            deep_agent_verdict = "LIKELY_MANIPULATED"
                        elif (
                            dsevere >= 0.10
                            or (dsev.count("MEDIUM") / dtotal) >= 0.40
                            or (final_deep_conf < 0.50 and dtotal > 1)
                        ):
                            deep_agent_verdict = "INCONCLUSIVE"
                        else:
                            deep_agent_verdict = "AUTHENTIC"
                    else:
                        deep_agent_verdict = "AUTHENTIC"

                deep_findings_preview = []
                for f in deep_findings_serial:
                    if not isinstance(f, dict):
                        continue
                    meta = (
                        f.get("metadata", {})
                        if isinstance(f.get("metadata"), dict)
                        else {}
                    )
                    tool = meta.get("tool_name", "") or f.get("finding_type", "")
                    summary = f.get("reasoning_summary", "")
                    if not summary:
                        continue
                    if tool and summary.lower().startswith(tool.lower() + ":"):
                        summary = summary[len(tool) + 1 :].strip()
                    elapsed_s = meta.get("elapsed_s")
                    if elapsed_s is None:
                        latency_ms = meta.get("latency_ms")
                        if latency_ms is not None:
                            elapsed_s = round(float(latency_ms) / 1000, 1)
                    deep_findings_preview.append(
                        {
                            "tool": tool,
                            "summary": summary[:320],
                            "confidence": f.get("confidence_raw", 0.5),
                            "flag": meta.get("section_flag", "info"),
                            "severity": _assign_severity_tier(f),
                            "verdict": "CLEAN",
                            "key_signal": "",
                            "section": "",
                            "elapsed_s": elapsed_s,
                        }
                    )

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
                            "confidence": final_deep_conf,
                            "findings_count": len(deep_findings_serial),
                            "error": None,
                            "tool_error_rate": final_deep_err,
                            "deep_analysis_pending": False,
                            "agent_verdict": deep_agent_verdict,
                            "section_flags": deep_section_flags,
                            "findings_preview": deep_findings_preview,
                        },
                    ),
                )

            except Exception as e:
                logger.error(
                    "Deep pass failed", agent_id=agent_id, error=str(e), exc_info=True
                )
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
                            "tool_error_rate": 1.0,
                            "deep_analysis_pending": False,
                        },
                    ),
                )

        # ── Track which agents were active (not skipped) ─────────────────────
        _SKIP_FINDING_TYPES = {
            "file type not applicable",
            "format not supported",
            "file type not applicable",
        }

        def _agent_was_active(result_obj: AgentLoopResult) -> bool:
            """True when the agent ran real tools (not just a file-type skip)."""
            if not result_obj.findings:
                return False
            return not all(
                (
                    f.get("finding_type", "")
                    if isinstance(f, dict)
                    else getattr(f, "finding_type", "")
                ).lower()
                in _SKIP_FINDING_TYPES
                for f in result_obj.findings
            )

        for i, r in enumerate(raw_results):
            agent_id = agent_configs[i][0]
            agent_name = agent_configs[i][1]

            if isinstance(r, BaseException):
                logger.error("Agent raised exception", agent_id=agent_id, error=str(r))
                results.append(
                    AgentLoopResult(
                        agent_id=agent_id,
                        findings=[],
                        reflection_report={},
                        react_chain=[],
                        error=str(r),
                    )
                )
                await broadcast_update(
                    ws_session_id,
                    BriefUpdate(
                        type="AGENT_COMPLETE",
                        session_id=ws_session_id,
                        agent_id=agent_id,
                        agent_name=agent_name,
                        message=f"Error: {str(r)[:80]}",
                        data={
                            "status": "error",
                            "confidence": 0.0,
                            "findings_count": 0,
                            "error": str(r)[:120],
                            "tool_error_rate": 1.0,
                        },
                    ),
                )
            elif not isinstance(r, tuple) or len(r) != 2:
                logger.error(
                    "Agent returned unexpected result type",
                    agent_id=agent_id,
                    result_type=type(r).__name__,
                )
                results.append(
                    AgentLoopResult(
                        agent_id=agent_id,
                        findings=[],
                        reflection_report={},
                        react_chain=[],
                        error=f"Unexpected result type: {type(r).__name__}",
                    )
                )
            else:
                result_obj, agent_instance = r
                results.append(result_obj)

                # Only queue deep pass for agents that actually ran during initial pass
                if (
                    agent_instance
                    and len(agent_instance.deep_task_decomposition) > 0
                    and _agent_was_active(result_obj)
                ):
                    deep_pass_coroutines.append(
                        (agent_id, agent_name, agent_instance, result_obj)
                    )
                elif agent_instance and not _agent_was_active(result_obj):
                    logger.info(
                        "Deep pass skipped — agent was inactive during initial pass",
                        agent_id=agent_id,
                    )

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
            ),
        )

        # Signal outer loop that we are paused for user decision — this lets
        # run_investigation_task move the wait outside the computation budget.
        pipeline._awaiting_user_decision = True
        await getattr(pipeline, "deep_analysis_decision_event").wait()
        pipeline._awaiting_user_decision = False

        if getattr(pipeline, "run_deep_analysis_flag") and deep_pass_coroutines:
            logger.info("Running deep analysis", agent_count=len(deep_pass_coroutines))
            await broadcast_update(
                ws_session_id,
                BriefUpdate(
                    type="AGENT_UPDATE",
                    session_id=ws_session_id,
                    agent_id=None,
                    agent_name=None,
                    message=f"🔬 Deep analysis starting — {len(deep_pass_coroutines)} agent(s) loading heavy ML models…",
                    data={
                        "status": "running",
                        "thinking": f"Deep analysis starting for {len(deep_pass_coroutines)} agent(s)…",
                    },
                ),
            )
            # ── Concurrent deep pass with Gemini context sync ──────────────
            # Agent1 runs concurrently with Agent2/Agent4 (which don't need
            # Agent1 context). Agent3/Agent5 also start concurrently — their
            # Gemini tools wait internally on an asyncio.Event until Agent1's
            # Gemini result is injected. This eliminates the sequential
            # bottleneck while preserving cross-agent accuracy.
            agent1_context_event = asyncio.Event()

            # Inject the event into Agent3/Agent5 so their Gemini handlers
            # can await it (see agent3_object.py:1264, agent5_metadata.py:894).
            for aid, _aname, ainst, _ares in deep_pass_coroutines:
                if aid in ("Agent3", "Agent5") and hasattr(
                    ainst, "_agent1_context_event"
                ):
                    ainst._agent1_context_event = agent1_context_event

            async def _run_agent1_deep_and_signal() -> None:
                """Run Agent1 deep pass, inject Gemini context, then unblock Agent3/5."""
                agent1_tuple = next(
                    (t for t in deep_pass_coroutines if t[0] == "Agent1"), None
                )
                if not agent1_tuple:
                    agent1_context_event.set()
                    return
                await run_agent_deep_pass(*agent1_tuple)
                # Inject Agent1 Gemini context into Agent3 + Agent5
                try:
                    a1_agent_instance = agent1_tuple[2]
                    gemini_result = getattr(
                        a1_agent_instance, "_gemini_vision_result", {}
                    )
                    if not gemini_result:
                        for f in getattr(a1_agent_instance, "_findings", []):
                            tool = (
                                (f.metadata or {}).get("tool_name", "")
                                if hasattr(f, "metadata")
                                else ""
                            )
                            if "gemini" in tool.lower():
                                gemini_result = f.metadata or {}
                                break
                    if gemini_result:
                        for aid, _aname, ainst, _ares in deep_pass_coroutines:
                            if aid in ("Agent3", "Agent5") and hasattr(
                                ainst, "inject_agent1_context"
                            ):
                                ainst.inject_agent1_context(gemini_result)
                        logger.info(
                            "Agent1 Gemini context injected into Agent3 + Agent5",
                            has_content_type=bool(
                                gemini_result.get("gemini_content_type")
                            ),
                            has_objects=bool(
                                gemini_result.get("gemini_detected_objects")
                            ),
                            has_text=bool(gemini_result.get("gemini_extracted_text")),
                        )
                    else:
                        logger.info(
                            "Agent1 deep pass produced no Gemini result — Agents 3 & 5 will use local analysis"
                        )
                except Exception as _inj_err:
                    logger.warning(
                        "Post-Agent1 Gemini inject error", error=str(_inj_err)
                    )
                finally:
                    # Always unblock Agent3/5 — even if Agent1 failed or context was empty.
                    agent1_context_event.set()

            # Build all deep pass tasks — ALL run concurrently
            deep_tasks_list = [_run_agent1_deep_and_signal()]
            for aid, aname, ainst, ares in deep_pass_coroutines:
                if aid != "Agent1":
                    deep_tasks_list.append(run_agent_deep_pass(aid, aname, ainst, ares))

            # Deep-phase pipeline ticker
            _DEEP_TICKER_PHRASES = [
                "🔬 Heavy ML models running — Gemini vision analysis active…",
                "⚡ Deep forensic pass in progress — building anomaly heatmaps…",
                "🧠 AI models cross-examining high-confidence anomalies…",
                "📡 Advanced spectral and frequency analysis running…",
                "🔮 Deep evidence chain being reconstructed…",
                "🔬 Synthesising deep-pass findings across all agents…",
            ]

            async def _deep_pipeline_ticker(done_event: asyncio.Event) -> None:
                idx = 0
                while True:
                    try:
                        await asyncio.wait_for(done_event.wait(), timeout=10.0)
                        return
                    except asyncio.TimeoutError:
                        pass
                    if done_event.is_set():
                        return
                    phrase = _DEEP_TICKER_PHRASES[idx % len(_DEEP_TICKER_PHRASES)]
                    idx += 1
                    await broadcast_update(
                        ws_session_id,
                        BriefUpdate(
                            type="AGENT_UPDATE",
                            session_id=ws_session_id,
                            agent_id=None,
                            agent_name=None,
                            message=phrase,
                            data={"status": "running", "thinking": phrase},
                        ),
                    )

            _deep_ticker_done = asyncio.Event()
            _deep_ticker_task = asyncio.create_task(
                _deep_pipeline_ticker(_deep_ticker_done)
            )

            await asyncio.gather(*deep_tasks_list, return_exceptions=True)

            _deep_ticker_done.set()
            try:
                await asyncio.wait_for(_deep_ticker_task, timeout=1.0)
            except Exception:
                _deep_ticker_task.cancel()
        elif getattr(pipeline, "run_deep_analysis_flag") and not deep_pass_coroutines:
            logger.info(
                "Deep analysis requested but no deep tasks available for this file type."
            )
        else:
            logger.info("User skipped deep analysis.")

        # Hook into arbiter to broadcast deliberation steps
        async def arbiter_step_hook(msg: str):
            await broadcast_update(
                ws_session_id,
                BriefUpdate(
                    type="AGENT_UPDATE",
                    session_id=ws_session_id,
                    message=f"🔮 {msg}",
                    data={"status": "deliberating", "thinking": f"🔮 {msg}"},
                ),
            )

        pipeline.arbiter._step_hook = arbiter_step_hook
        pipeline._arbiter_step = ""  # initialize for status polling

        # Broadcast arbiter is about to run before returning results to pipeline
        await broadcast_update(
            ws_session_id,
            BriefUpdate(
                type="AGENT_UPDATE",
                session_id=ws_session_id,
                agent_id=None,
                agent_name=None,
                message="🔮 Council Arbiter deliberating — synthesising all findings…",
                data={
                    "status": "deliberating",
                    "thinking": "🔮 Council Arbiter deliberating — synthesising all findings…",
                },
            ),
        )

        return results

    pipeline._run_agents_concurrent = instrumented_run

    # Convert session_id string to UUID for pipeline
    from uuid import UUID as UUIDType

    session_uuid = UUIDType(session_id)

    return await pipeline.run_investigation(
        evidence_file_path=evidence_file_path,
        case_id=case_id,
        investigator_id=investigator_id,
        original_filename=original_filename,
        session_id=session_uuid,
    )


async def run_investigation_task(
    session_id: str,
    pipeline: ForensicCouncilPipeline,
    evidence_file_path: str,
    case_id: str,
    investigator_id: str,
    original_filename: str | None = None,
):
    """Background task to run investigation with improved timing."""
    error_msg = None

    try:
        # Wait for WebSocket connection (up to 2 seconds, reduced from 5)
        logger.info(
            "Background task waiting for WebSocket client", session_id=session_id
        )
        ws_connected = False
        for _ws_wait in range(20):
            if get_session_websockets(session_id):
                ws_connected = True
                break
            await asyncio.sleep(0.1)

        if ws_connected:
            logger.info(
                "WebSocket client connected, starting analysis", session_id=session_id
            )
        else:
            logger.warning(
                "WebSocket client never connected after 2s, proceeding anyway",
                session_id=session_id,
            )

        await set_active_pipeline_metadata(
            session_id,
            {
                "status": "running",
                "brief": "Initialising forensic pipeline...",
                "case_id": case_id,
                "investigator_id": investigator_id,
                "file_path": evidence_file_path,
                "original_filename": original_filename,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        # Send initial update
        await broadcast_update(
            session_id,
            BriefUpdate(
                type="AGENT_UPDATE",
                session_id=session_id,
                message="🚀 Initialising forensic pipeline — loading specialist agents…",
                data={
                    "status": "starting",
                    "thinking": "🚀 Initialising forensic pipeline — loading specialist agents…",
                },
            ),
        )

        # Run computational phases with timeout, but exclude user decision wait.
        # The pipeline signals pipeline._awaiting_user_decision = True when it
        # pauses after initial analysis.  We poll for that sentinel so the 600 s
        # budget only covers actual computation — not human think time.
        timeout = min(settings.investigation_timeout, 600)  # Max 10 minutes
        pipeline_coro = _wrap_pipeline_with_broadcasts(
            pipeline=pipeline,
            session_id=session_id,
            evidence_file_path=evidence_file_path,
            case_id=case_id,
            investigator_id=investigator_id,
            original_filename=original_filename,
        )

        pipeline_task = asyncio.create_task(pipeline_coro)

        # Track cumulative computation time (excludes user decision wait).
        # This replaces the original asyncio.wait_for which counted wall-clock
        # time including the user decision pause.
        computation_deadline = time.monotonic() + float(timeout)
        user_decision_elapsed = 0.0

        # Wait for either completion or the user-decision sentinel
        while True:
            remaining = computation_deadline - time.monotonic()
            if remaining <= 0:
                logger.error("Computation budget exhausted", timeout=timeout)
                pipeline_task.cancel()
                try:
                    await pipeline_task
                except asyncio.CancelledError:
                    raise
                except Exception as _e:
                    logger.debug("Non-cancellation exception during pipeline cleanup", error=str(_e))
                raise asyncio.TimeoutError(
                    f"Pipeline computation exceeded {timeout}s budget"
                )

            poll_interval = min(5.0, remaining)
            done, _ = await asyncio.wait(
                [pipeline_task],
                timeout=poll_interval,
            )
            if pipeline_task in done:
                break  # pipeline finished (no user decision needed, or already handled)
            # Check if pipeline is paused waiting for user
            if getattr(pipeline, "_awaiting_user_decision", False):
                # Give the user up to 1 hour to decide, outside the computation budget
                logger.info("Pipeline paused for user decision", max_wait=3600)
                user_wait_event = getattr(pipeline, "deep_analysis_decision_event")
                decision_start = time.monotonic()
                try:
                    await asyncio.wait_for(user_wait_event.wait(), timeout=3600.0)
                except asyncio.TimeoutError:
                    logger.warning(
                        "User decision timed out after 3600 s — treating as Accept (skip deep)"
                    )
                    pipeline.run_deep_analysis_flag = False
                    user_wait_event.set()
                # Exclude user decision time from computation budget
                user_decision_elapsed += time.monotonic() - decision_start
                computation_deadline += user_decision_elapsed
                user_decision_elapsed = 0.0  # reset to avoid double-counting
                # Reset sentinel and continue waiting for pipeline to finish
                pipeline._awaiting_user_decision = False

        # Re-raise any exception from the pipeline task
        report = pipeline_task.result()

        # Pipeline complete
        await broadcast_update(
            session_id,
            BriefUpdate(
                type="PIPELINE_COMPLETE",
                session_id=session_id,
                message="Investigation concluded.",
                data={"report_id": str(report.report_id)},
            ),
        )

        pipeline._final_report = report

        # Cache in _final_reports BEFORE the finally block removes the pipeline
        # from _active_pipelines. This prevents a race where the client polls
        # /report after the task finishes but before the DB write completes.
        await set_final_report(session_id, report)
        await set_active_pipeline_metadata(
            session_id,
            {
                "status": "completed",
                "brief": "Investigation complete.",
                "case_id": case_id,
                "investigator_id": investigator_id,
                "file_path": evidence_file_path,
                "original_filename": original_filename,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "report_id": str(report.report_id),
            },
        )

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
            ),
        )
    except Exception as e:
        error_msg = str(e)
        logger.error(
            "Investigation failed",
            error_msg=error_msg,
            session_id=session_id,
            exc_info=True,
        )
        increment_investigations_failed()
        await broadcast_update(
            session_id,
            BriefUpdate(
                type="ERROR",
                session_id=session_id,
                message=f"Investigation failed: {error_msg}",
                data={"error": error_msg},
            ),
        )
    finally:
        if error_msg:
            pipeline._error = error_msg
            try:
                await set_active_pipeline_metadata(
                    session_id,
                    {
                        "status": "error",
                        "brief": error_msg,
                        "case_id": case_id,
                        "investigator_id": investigator_id,
                        "file_path": evidence_file_path,
                        "original_filename": original_filename,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "error": error_msg,
                    },
                )
            except Exception:
                logger.warning(
                    "Failed to update Redis session metadata with error state",
                    session_id=session_id,
                    exc_info=True,
                )
            # Persist failure status so other replicas can report it
            try:
                from core.session_persistence import get_session_persistence

                persistence = await get_session_persistence()
                await persistence.update_session_status(
                    session_id, "error", error_message=error_msg
                )
            except Exception:
                logger.warning(
                    "Failed to persist error status",
                    session_id=session_id,
                    exc_info=True,
                )
        try:
            if os.path.exists(evidence_file_path):
                os.unlink(evidence_file_path)
        except Exception as e:
            logger.warning("Failed to clean up temp file", error=str(e))
        # Remove pipeline from active set once fully done to free resources.
        # The report is cached in _final_reports for the report endpoint to read.
        _active_pipelines.pop(session_id, None)

        # D2: clean up WebSocket connections for this session now that it's done.
        clear_session_websockets(session_id)

        # D1: evict stale entries from _final_reports (older than 24 hours).
        # This prevents unbounded growth when many investigations complete without
        # their reports being fetched.  O(n) scan runs once per completed session.
        # NOTE: do NOT import datetime here — a local import shadows the module-level
        # `datetime` name and causes UnboundLocalError at line 1640 (Python scoping).
        cutoff = datetime.now(timezone.utc).timestamp() - 86_400
        stale = [
            sid
            for sid, (_, cached_at) in list(_final_reports.items())
            if cached_at.timestamp() < cutoff
        ]
        for sid in stale:
            _final_reports.pop(sid, None)
        if stale:
            logger.debug("Evicted stale report cache entries", count=len(stale))
