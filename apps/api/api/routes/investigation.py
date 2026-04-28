"""
Investigation Routes
====================

Routes for starting and managing forensic investigations.
Orchestration logic has been moved to orchestration/investigation_runner.py.
"""

import asyncio
import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
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
)
from api.routes.metrics import (
    increment_investigations_started,
)
from api.schemas import (
    InvestigationResponse,
)
from core.auth import User, get_current_user
from core.config import get_settings
from core.session_persistence import get_session_persistence
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
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp4",
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
        ".wav",
        ".mp3",
        ".m4a",
        ".flac",
    }
)

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_\-\.]{1,128}$")


def _validate_safe_id(value: str, field_name: str) -> None:
    """Raise 422 if value contains unsafe characters."""
    if not _SAFE_ID_RE.match(value):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid {field_name}: must be 1-128 characters, "
                "alphanumeric with hyphens, underscores, and dots only."
            ),
        )


async def run_investigation_task(
    session_id: str,
    pipeline: ForensicCouncilPipeline,
    evidence_file_path: str,
    case_id: str,
    investigator_id: str,
    original_filename: str | None = None,
) -> None:
    """Compatibility wrapper for tests and older imports."""
    from orchestration.investigation_runner import (
        run_investigation_task as _run_investigation_task,
    )
    await _run_investigation_task(
        session_id=session_id,
        pipeline=pipeline,
        evidence_file_path=evidence_file_path,
        case_id=case_id,
        investigator_id=investigator_id,
        original_filename=original_filename,
    )


@router.post("/investigate", response_model=InvestigationResponse)
async def start_investigation(
    file: UploadFile = File(...),  # noqa: B008
    case_id: str = Form(...),  # noqa: B008
    investigator_id: str = Form(...),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    """Start a new forensic investigation by uploading evidence."""
    _validate_safe_id(case_id, "case_id")
    _validate_safe_id(investigator_id, "investigator_id")

    await check_investigation_rate_limit(current_user.user_id)
    await check_daily_cost_quota(current_user.user_id, current_user.role.value)

    # Read a small chunk of bytes in-memory to detect the true MIME type before writing to disk
    head = await file.read(2048)
    await file.seek(0)

    import magic

    actual_mime = await asyncio.to_thread(magic.from_buffer, head, mime=True)

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

    session_id = str(uuid4())
    incoming_dir = Path(settings.evidence_storage_path) / "incoming"
    incoming_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = incoming_dir / f"{session_id}{raw_suffix}"

    try:
        hasher = hashlib.sha256()
        total_size = 0
        with open(tmp_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > MAX_FILE_SIZE:
                    f.close()
                    tmp_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=400, detail="File size exceeds limit.")
                hasher.update(chunk)
                f.write(chunk)

        if total_size == 0:
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="File is empty.")

        content_hash = hasher.hexdigest()
        dedup_key = f"dedup:{case_id}:{content_hash}"
        try:
            from core.persistence.redis_client import get_redis_client

            _redis = await get_redis_client()
            if _redis:
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
                        if status not in ("running", "paused"):
                            await _redis.delete(dedup_key)
                            # Try setting it again for the current request
                            was_set = await _redis.set(
                                dedup_key,
                                session_id,
                                nx=True,
                                ex=settings.investigation_timeout + 60,
                            )
                            if not was_set:
                                # Highly unlikely race condition: another request won the race.
                                # Just let it return 409 normally in the next block.
                                pass
                    except Exception as meta_err:
                        logger.warning(
                            "Failed to check status of existing dedup session", error=str(meta_err)
                        )

                    # If we successfully cleared and reset (was_set is True now),
                    # then we just fall through to the rest of the investigation.
                    # Otherwise, if was_set is still False, we return 409.
                    if not was_set:
                        # Re-claim ownership: update the existing session with current user ID.
                        try:
                            existing_meta = (
                                await get_active_pipeline_metadata(existing_session_id) or {}
                            )
                            await set_active_pipeline_metadata(
                                existing_session_id,
                                {
                                    **existing_meta,
                                    "investigator_id": current_user.user_id,
                                    "investigator_role": current_user.role.value,
                                    "case_investigator_label": investigator_id,
                                },
                            )
                        except Exception as meta_exc:
                            logger.warning(
                                "Failed to re-claim session ownership on dedup",
                                session_id=existing_session_id,
                                error=str(meta_exc),
                            )

                        tmp_path.unlink(missing_ok=True)
                        raise HTTPException(
                            status_code=409,
                            detail=f"Duplicate detected: session {existing_session_id}",
                        )
        except HTTPException:
            raise
        except Exception as exc:
            logger.debug("Evidence deduplication skipped", error=str(exc))

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
            except Exception:
                logger.warning("Image integrity check failed; file may be corrupted.")
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=400, detail="Image verification failed; file may be corrupted."
                )

        await set_active_pipeline_metadata(
            session_id,
            {
                "status": "running",
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

        if settings.use_redis_worker:
            from api.routes._session_state import broadcast_update
            from api.schemas import BriefUpdate
            from orchestration.investigation_queue import get_investigation_queue

            queue = get_investigation_queue()
            if not await queue.is_worker_alive():
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
            except Exception as q_err:
                logger.error("Failed to enqueue investigation", error=str(q_err))
                raise HTTPException(
                    status_code=500,
                    detail="Failed to queue investigation task. Check Redis connection.",
                ) from q_err
        else:
            pipeline = ForensicCouncilPipeline()
            set_active_pipeline(session_id, pipeline)
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

        increment_investigations_started()

        try:
            p = await get_session_persistence()
            await p.save_session_state(
                session_id=session_id,
                case_id=case_id,
                investigator_id=current_user.user_id,
                pipeline_state={"status": "running"},
                status="running",
            )
        except Exception as exc:
            logger.error("Session persistence registration failed", error=str(exc))
            raise HTTPException(status_code=500, detail="Failed to write chain-of-custody ledger.")

        return InvestigationResponse(
            session_id=session_id,
            case_id=case_id,
            status="started",
            message=f"Investigation started for {file.filename or 'evidence'}. Track status via WebSocket.",
        )

    except HTTPException:
        tmp_path.unlink(missing_ok=True)
        raise
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=str(e)) from e
