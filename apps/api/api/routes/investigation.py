"""
Investigation Routes
====================

Routes for starting and managing forensic investigations.
Orchestration logic has been moved to orchestration/investigation_runner.py.
"""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from api.constants import _EXACT_MIME_EXT_MAP
from api.routes._rate_limiting import (
    check_daily_cost_quota,
    check_investigation_rate_limit,
)
from api.routes._session_state import (
    cleanup_connections,  # noqa: F401 - re-exported for api.main shutdown.
    get_active_pipeline_metadata,
    get_active_pipelines_count,  # noqa: F401 - re-exported for api.main metrics.
    set_active_pipeline,
    set_active_pipeline_metadata,
    set_active_task,
    update_active_pipeline_metadata,
)
from api.routes.metrics import (
    increment_investigations_started,
)
from api.schemas import (
    InvestigationResponse,
)
from core.auth import User, get_current_user
from core.config import get_settings
from core.structured_logging import get_logger
from orchestration.pipeline import ForensicCouncilPipeline

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/v1", tags=["investigation"])

# Allowed MIME types
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
    "video/x-matroska",
    "video/webm",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp4",
    "audio/x-m4a",
    "audio/flac",
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
_ALLOWED_EXTENSIONS = frozenset(
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
        ".mkv",
        ".webm",
        ".wav",
        ".mp3",
        ".m4a",
        ".flac",
    }
)

# B-H-3: hold strong references to deferred-cleanup tasks so the GC
# can't collect them mid-sleep and silently skip the file unlink.
_deferred_cleanup_tasks: set[asyncio.Task[Any]] = set()


async def _detect_mime_from_head(head: bytes) -> str:
    try:
        import magic
    except ImportError as exc:
        logger.error("python-magic is not installed", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Evidence MIME detection service is unavailable.",
        ) from exc
    try:
        return await asyncio.to_thread(magic.from_buffer, head, mime=True)
    except Exception as exc:
        logger.error("libmagic MIME detection failed", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Evidence MIME detection service is unavailable.",
        ) from exc


@router.post("/investigate", response_model=InvestigationResponse)
async def start_investigation(
    file: UploadFile = File(...),  # noqa: B008
    case_id: str = Form(...),  # noqa: B008
    investigator_id: str = Form(...),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Start a new forensic investigation by uploading evidence."""
    # B-H-7: route both fields through InvestigationRequest's stricter
    # validators — same as the typed Pydantic body would. case_id is
    # required to start with CASE- (api/schemas.py:_validate_case_id);
    # the previous hand-rolled _validate_safe_id call bypassed that rule.
    from api.schemas import InvestigationRequest

    try:
        InvestigationRequest(case_id=case_id, investigator_id=investigator_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Read a small chunk of bytes in-memory to detect the true MIME type before writing to disk
    head = await file.read(8192)
    await file.seek(0)

    actual_mime = await _detect_mime_from_head(head)
    # If magic returned octet-stream, try PIL-based detection from head bytes
    if actual_mime == "application/octet-stream":
        try:
            from io import BytesIO
            from PIL import Image
            _pil_format_to_mime = {
                "JPEG": "image/jpeg", "PNG": "image/png", "GIF": "image/gif",
                "WEBP": "image/webp", "TIFF": "image/tiff", "BMP": "image/bmp",
            }
            with Image.open(BytesIO(head)) as img:
                pil_fmt = (img.format or "").upper()
            if pil_fmt in _pil_format_to_mime:
                actual_mime = _pil_format_to_mime[pil_fmt]
                logger.info("PIL fallback MIME detection from head bytes", format=pil_fmt, mime=actual_mime)
        except Exception:
            pass

    # Validate against ALLOWED_MIME_TYPES
    if actual_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"File type '{actual_mime}' is not allowed.")

    # Cross-reference with core/mime_registry.py to ensure support
    from core.mime_registry import MimeRegistry

    is_supported_by_any = False
    for aid in ["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"]:
        if MimeRegistry.is_supported(agent_name=aid, mime_type=actual_mime):
            is_supported_by_any = True
            break

    if not is_supported_by_any:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{actual_mime}' is not supported by any specialized forensic agent.",
        )

    raw_suffix = Path(file.filename or "").suffix.lower()
    if raw_suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400, detail=f"File extension '{raw_suffix}' is not permitted."
        )

    valid_exts = _EXACT_MIME_EXT_MAP.get(actual_mime, frozenset())
    if not valid_exts or raw_suffix not in valid_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Security violation: content '{actual_mime}' mismatch extension '{raw_suffix}'",
        )

    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds limit.")

    await check_investigation_rate_limit(current_user.user_id)
    await check_daily_cost_quota(current_user.user_id, current_user.role.value)

    session_id = str(uuid4())
    incoming_dir = Path(settings.evidence_storage_path) / "incoming"
    incoming_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = incoming_dir / f"{session_id}{raw_suffix}"

    pipeline_started = False
    try:
        hasher = hashlib.sha256()
        total_size = 0
        tmp_path.write_bytes(b"")
        chunks: list[bytes] = []
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > MAX_FILE_SIZE:
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="File size exceeds limit.")
            hasher.update(chunk)
            chunks.append(chunk)

        if chunks:
            await _write_file(tmp_path, chunks)

        if total_size == 0:
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="File is empty.")

        content_hash = hasher.hexdigest()
        dedup_key = f"dedup:{case_id}:{content_hash}"
        try:
            from core.persistence.redis_client import get_redis_client

            _redis = await get_redis_client()
            was_set = await _redis.set(
                dedup_key,
                session_id,
                nx=True,
                ex=settings.investigation_timeout + 60,
            )
            if not was_set:
                existing = await _redis.get(dedup_key)
                existing_session_id = (
                    existing if isinstance(existing, str) else existing.decode()
                )

                # ── Check if the existing session is actually active ─────────
                # If the session was interrupted by a restart or finished, we
                # should NOT return 409. Instead, we clear the dedup key and
                # allow the user to start a fresh investigation for the same file.
                try:
                    existing_meta = (
                        await get_active_pipeline_metadata(existing_session_id) or {}
                    )
                    status = existing_meta.get("status")
                    if status not in ("running", "paused", "queued"):
                        await _redis.delete(dedup_key)
                        # Try setting it again for the current request
                        was_set = await _redis.set(
                            dedup_key,
                            session_id,
                            nx=True,
                            ex=settings.investigation_timeout + 60,
                        )
                        if not was_set:
                            logger.info(
                                "Dedup race: another request claimed the same content_hash; "
                                "deferring to 409 response below.",
                                session_id=session_id,
                            )
                except Exception as meta_err:
                    logger.warning(
                        "Failed to check status of existing dedup session", error=str(meta_err)
                    )

                # If we successfully cleared and reset (was_set is True now),
                # then we just fall through to the rest of the investigation.
                # Otherwise, if was_set is still False, we return 409.
                if not was_set:
                    # S-H-6: do NOT mutate the existing session's
                    # investigator_id on a dedup hit. Ownership stays with
                    # whoever opened the session originally — chain-of-
                    # custody attribution depends on it. Return 409 with the
                    # existing session_id so the caller knows where to look.
                    tmp_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "duplicate_investigation",
                            "existing_session_id": existing_session_id,
                            "message": "Duplicate investigation already exists",
                        },
                    )
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(
                "Evidence deduplication failed — Redis unavailable",
                error=str(exc),
            )
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=503,
                detail="Investigation service temporarily unavailable — Redis unreachable. Please retry.",
            ) from exc

        if actual_mime.startswith("image/") and actual_mime != "image/gif":
            try:
                from PIL import Image

                # Offload image verification to a thread executor
                def _verify_image(path):
                    with Image.open(path) as img:
                        img.verify()
                    with Image.open(path) as img2:
                        return img2.size

                size = await asyncio.to_thread(_verify_image, str(tmp_path))
                w, h = size
                if w * h > 100_000_000:
                    raise HTTPException(status_code=400, detail="Image too large.")
            except HTTPException:
                raise
            except Exception as verify_error:
                logger.warning(
                    "Image integrity check failed; file may be corrupted.",
                    error=str(verify_error),
                )
                if settings.app_env == "testing":
                    logger.debug("Skipping image verification for mocked test upload")
                else:
                    tmp_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=400, detail="Image verification failed; file may be corrupted."
                    ) from verify_error

        await set_active_pipeline_metadata(
            session_id,
            {
                "status": "queued",
                "brief": "Initializing forensic pipeline...",
                "case_id": case_id,
                "investigator_id": current_user.user_id,
                "investigator_role": current_user.role.value,
                "case_investigator_label": investigator_id,
                "file_path": str(tmp_path),
                "original_filename": file.filename,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )

        if settings.app_env == "production":
            try:
                await _register_session_before_dispatch(
                    session_id=session_id,
                    case_id=case_id,
                    investigator_id=current_user.user_id,
                )
            except Exception as exc:
                await _cleanup_stale_investigation_session(
                    dedup_key=dedup_key,
                    session_id=session_id,
                    reason="initial persistence failure",
                )
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=500,
                    detail="Failed to register investigation before dispatch.",
                ) from exc
        else:
            try:
                await _register_session_before_dispatch(
                    session_id=session_id,
                    case_id=case_id,
                    investigator_id=current_user.user_id,
                )
            except Exception as exc:
                logger.warning(
                    "Session persistence registration skipped in non-production",
                    session_id=session_id,
                    error=str(exc),
                )

        if getattr(settings, "supersede_prior_investigations_on_upload", False):
            await _supersede_prior_investigations(
                investigator_user_id=current_user.user_id,
                keep_session_id=session_id,
            )

        if settings.use_redis_worker:
            from api.routes._session_state import broadcast_update
            from api.schemas import BriefUpdate
            from orchestration.investigation_queue import get_investigation_queue

            queue = get_investigation_queue()
            if not await queue.is_worker_alive():
                await _cleanup_stale_investigation_session(
                    dedup_key=dedup_key,
                    session_id=session_id,
                    reason="worker liveness failure",
                )
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Investigation worker is not running. "
                        "Start the worker service and try again."
                    ),
                )

            try:
                # Signal immediately that the task is in the queue
                await broadcast_update(
                    session_id,
                    BriefUpdate(
                        type="AGENT_UPDATE",
                        session_id=session_id,
                        message="Investigation enqueued. Awaiting available forensic worker...",
                        data={"status": "initiating", "thinking": "Queueing forensic task..."},
                    ),
                )

                await queue.submit(
                    session_id=UUID(session_id),
                    case_id=case_id,
                    investigator_id=current_user.user_id,
                    evidence_file_path=str(tmp_path),
                    original_filename=file.filename,
                )
                pipeline_started = True
            except Exception as q_err:
                await _cleanup_stale_investigation_session(
                    dedup_key=dedup_key,
                    session_id=session_id,
                    reason="enqueue failure",
                )
                logger.error("Failed to enqueue investigation", error=str(q_err))
                raise HTTPException(
                    status_code=500,
                    detail="Failed to queue investigation task. Check Redis connection.",
                ) from q_err
        else:
            pipeline = ForensicCouncilPipeline()
            set_active_pipeline(session_id, pipeline)
            await update_active_pipeline_metadata(session_id, {"status": "running"})
            task = asyncio.create_task(
                run_investigation_task(
                    session_id=session_id,
                    pipeline=pipeline,
                    evidence_file_path=str(tmp_path),
                    case_id=case_id,
                    investigator_id=current_user.user_id,
                    original_filename=file.filename,
                )
            )
            set_active_task(session_id, task)
            pipeline_started = True

        increment_investigations_started()

        return InvestigationResponse(
            session_id=session_id,
            case_id=case_id,
            status="started",
            message=f"Investigation started for {file.filename or 'evidence'}. Track status via WebSocket.",
        )

    except HTTPException:
        if not pipeline_started:
            tmp_path.unlink(missing_ok=True)
        raise
    except Exception as e:
        logger.error(
            "Investigation start failed",
            session_id=session_id,
            error=str(e),
            exc_info=True,
        )
        if not pipeline_started:
            tmp_path.unlink(missing_ok=True)
        elif tmp_path.exists():
            # B-H-3: track deferred cleanup tasks in a module-level set so
            # they aren't garbage-collected mid-sleep (which would skip the
            # unlink) and so graceful shutdown can drain pending cleanups.
            async def _deferred_cleanup(p=tmp_path):
                await asyncio.sleep(600)
                try:
                    p.unlink(missing_ok=True)
                except Exception as _cleanup_err:
                    logger.debug(
                        "Deferred tmp file cleanup failed", path=str(p), error=str(_cleanup_err)
                    )

            _task = asyncio.create_task(_deferred_cleanup())
            _deferred_cleanup_tasks.add(_task)
            _task.add_done_callback(_deferred_cleanup_tasks.discard)
        if settings.app_env != "production":
            raise HTTPException(status_code=500, detail=f"Failed to start investigation: {type(e).__name__}") from e
        raise HTTPException(
            status_code=500,
            detail="Failed to start investigation. Please retry or contact support with the session timestamp.",
        ) from e
