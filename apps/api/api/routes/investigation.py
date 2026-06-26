"""
Investigation Routes
====================

Routes for starting and managing forensic investigations.
Orchestration logic has been moved to orchestration/investigation_runner.py.
"""

import asyncio
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

try:
    import magic
except ImportError:
    from core import magic_fallback as magic
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
    CapabilitiesResponse,
    InvestigationResponse,
)
from core.auth import User, get_current_user
from core.config import get_settings
from core.file_type_policy import (
    EXACT_MIME_EXT_MAP,
    SUPPORTED_EXTENSIONS,
    SUPPORTED_MIME_TYPES,
    get_applicable_agents,
    get_mime_for_extension,
)
from core.structured_logging import get_logger
from orchestration.pipeline import ForensicCouncilPipeline

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/v1", tags=["investigation"])


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def get_capabilities():
    """Return the backend's supported file types and agent capabilities."""
    from core.file_type_policy import AGENT_FILE_CAPABILITIES, SUPPORTED_MIME_TYPES

    max_size = getattr(settings, "max_upload_size_bytes", 50 * 1024 * 1024)
    agent_caps: dict[str, list[str]] = {}
    for agent_id, caps in AGENT_FILE_CAPABILITIES.items():
        # Include both prefix matches (e.g. "image/") and exact full-MIME types
        # (e.g. "application/pdf"). The client matches with startsWith, for which
        # an exact MIME is a prefix of itself — so PDF/MP4-container agents are
        # not dropped from the client's agent filtering.
        agent_caps[agent_id] = [
            *caps.get("mime_prefixes", []),
            *caps.get("full_mimes", []),
        ]

    return CapabilitiesResponse(
        supported_mime_types=sorted(SUPPORTED_MIME_TYPES),
        max_file_size_bytes=max_size,
        agent_capabilities=agent_caps,
    )

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

# B-H-3: hold strong references to deferred-cleanup tasks so the GC
# can't collect them mid-sleep and silently skip the file unlink.
_deferred_cleanup_tasks: set[asyncio.Task[Any]] = set()

# Strong references to preflight visual-context tasks so the GC can't
# collect them before Gemini responds (typical latency 2–5s).
_preflight_tasks: set[asyncio.Task[Any]] = set()


async def _detect_mime_from_head(head: bytes) -> str:
    try:
        detected = await asyncio.to_thread(magic.from_buffer, head, mime=True)
        if not isinstance(detected, str):
            fallback_magic = sys.modules.get("magic")
            if fallback_magic is not None and fallback_magic is not magic:
                detected = await asyncio.to_thread(fallback_magic.from_buffer, head, mime=True)
        if not isinstance(detected, str):
            raise TypeError(f"libmagic returned non-string MIME value: {type(detected).__name__}")
        return detected
    except Exception as exc:
        logger.error("libmagic MIME detection failed", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Evidence MIME detection service is unavailable.",
        ) from exc


def _canonicalize_supported_mime(detected_mime: str, raw_suffix: str) -> str:
    """Normalize libmagic's generic container/text results for supported extensions.

    libmagic correctly reports many textual formats as ``text/plain`` and
    ZIP-backed Office formats as ``application/zip`` from the leading bytes.
    The product explicitly supports CSV/Markdown/DOCX/ODT, so map those known
    extension-backed cases to the policy MIME before exact extension validation.
    """
    suffix = raw_suffix.lower()
    detected = (detected_mime or "").lower()
    expected = get_mime_for_extension(suffix)
    if not expected:
        return detected_mime

    if detected == "text/plain" and suffix in {".csv", ".md"}:
        return expected

    if detected in {"application/zip", "application/x-zip-compressed"} and suffix in {".docx", ".odt"}:
        return expected

    return detected_mime


async def _mp4_has_real_video_stream(path: Path) -> bool | None:
    """P2.18 — disambiguate an MP4 container with ffprobe.

    Returns True if the file has a genuine (non-cover-art) video stream, False if
    it is audio-only, or None if ffprobe is unavailable/failed (caller keeps the
    libmagic-detected MIME). An audio-only ``.mp4`` is commonly detected as
    ``video/mp4`` and would misroute to the video agent; this lets the upload path
    reclassify it as audio. Album-art video streams (disposition attached_pic=1)
    are ignored so an audio file with embedded cover art is not treated as video.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-select_streams", "v",
            "-show_entries", "stream=codec_type:stream_disposition=attached_pic",
            "-of", "csv=p=0", str(path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
    except Exception as exc:
        logger.debug("ffprobe a/v disambiguation unavailable", error=str(exc))
        return None
    for line in out.decode("utf-8", "ignore").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if parts and parts[0] == "video" and (len(parts) < 2 or parts[1] != "1"):
            return True
    return False


async def _write_file(path: Path, chunks: list[bytes]) -> None:
    def _write():
        with path.open("wb") as f:
            for chunk in chunks:
                f.write(chunk)
    await asyncio.to_thread(_write)


def _append_chunk(path: Path, chunk: bytes) -> None:
    with path.open("ab") as f:
        f.write(chunk)


async def run_investigation_task(
    session_id: str,
    pipeline: ForensicCouncilPipeline,
    evidence_file_path: str,
    case_id: str,
    investigator_id: str,
    original_filename: str | None = None,
    detected_mime: str | None = None,
    validated_extension: str | None = None,
    content_sha256: str | None = None,
    file_size_bytes: int | None = None,
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
        detected_mime=detected_mime,
        validated_extension=validated_extension,
        content_sha256=content_sha256,
        file_size_bytes=file_size_bytes,
    )


async def _register_session_before_dispatch(
    *,
    session_id: str,
    case_id: str,
    investigator_id: str,
    status: str = "queued",
) -> None:
    from core import session_persistence

    p = await session_persistence.get_session_persistence()
    ok = await p.save_session_state(
        session_id=session_id,
        case_id=case_id,
        investigator_id=investigator_id,
        pipeline_state={"status": status},
        status=status,
    )
    if not ok:
        raise RuntimeError("session persistence returned false")


async def _cleanup_stale_investigation_session(
    *,
    dedup_key: str,
    session_id: str,
    reason: str,
) -> None:
    """Best-effort cleanup when a queued investigation cannot be started."""
    try:
        from core.persistence.redis_client import get_redis_client

        redis = await get_redis_client()
        await redis.delete(dedup_key)
        await redis.delete(f"forensic:session:metadata:{session_id}")
    except Exception as cleanup_error:
        logger.warning(
            "Failed to clean stale investigation session",
            session_id=session_id,
            reason=reason,
            error=str(cleanup_error),
        )


async def _supersede_prior_investigations(
    *,
    investigator_user_id: str,
    keep_session_id: str,
) -> None:
    """Retire older sessions for this investigator before starting a fresh upload."""
    try:
        from core.persistence.redis_client import get_redis_client

        redis = await get_redis_client()
        metadata_prefix = "forensic:session:metadata:"
        task_hash = "forensic:investigation:tasks"
        queue_key = "forensic:investigation:queue"

        # B-H-1: SCAN instead of KEYS — runs on every upload, must not block.
        keys: list[Any] = []
        async for _k in redis.scan_iter(match=f"{metadata_prefix}*", count=200):
            keys.append(_k)
        superseded: list[str] = []
        for key in keys:
            key_text = key.decode() if isinstance(key, bytes) else str(key)
            session_id = key_text.replace(metadata_prefix, "")
            if session_id == keep_session_id:
                continue
            metadata = await redis.get_json(key)
            if not isinstance(metadata, dict):
                continue
            if metadata.get("investigator_id") != investigator_user_id:
                continue
            status = str(metadata.get("status") or "").lower()
            if status in {"completed", "error", "interrupted", "terminated", "superseded"}:
                continue

            superseded.append(session_id)
            await redis.set(
                key,
                {
                    **metadata,
                    "status": "superseded",
                    "brief": "Superseded by a newer evidence upload.",
                    "awaiting_decision": False,
                    "superseded_by": keep_session_id,
                    "superseded_at": datetime.now(UTC).isoformat(),
                },
                ex=900,
            )
            await redis.delete(f"forensic:replay:{session_id}")
            await redis.delete(f"forensic:session:resume_decision:{session_id}")
            await redis.delete(f"forensic:session:resume_decision:{session_id}:initial_to_deep")
            await redis.delete(f"forensic:session:resume_decision:{session_id}:deep_to_report")
            try:
                await redis.hdel(task_hash, session_id)
            except Exception:
                logger.debug("Failed to delete superseded task metadata", session_id=session_id)

            try:
                for decision_key in [
                    f"forensic:session:resume_decision:{session_id}:initial_to_deep",
                    f"forensic:session:resume_decision:{session_id}:deep_to_report",
                    f"forensic:session:resume_decision:{session_id}",
                ]:
                    await redis.set(
                        decision_key,
                        {
                            "deep_analysis": False,
                            "decided_by": investigator_user_id,
                            "decided_at": datetime.now(UTC).isoformat(),
                            "superseded_by": keep_session_id,
                        },
                        ex=settings.investigation_timeout,
                    )
                await redis.client.publish(
                    "forensic:notify_decision",
                    json.dumps({"session_id": session_id, "deep_analysis": False}),
                )
            except Exception as notify_error:
                logger.debug(
                    "Failed to notify superseded investigation",
                    session_id=session_id,
                    error=str(notify_error),
                )

        if superseded:
            try:
                queued = await redis.client.lrange(queue_key, 0, -1)
                remaining = [
                    item
                    for item in queued
                    if (item.decode() if isinstance(item, bytes) else str(item)) not in superseded
                ]
                async with redis.client.pipeline(transaction=True) as pipe:
                    pipe.delete(queue_key)
                    if remaining:
                        pipe.rpush(queue_key, *remaining)
                    await pipe.execute()
            except Exception as queue_error:
                logger.debug("Failed to prune superseded queue entries", error=str(queue_error))

            logger.info(
                "Superseded prior investigations for fresh upload",
                investigator_id=investigator_user_id,
                keep_session_id=keep_session_id,
                superseded=superseded,
            )
    except Exception as exc:
        logger.warning(
            "Fresh-upload stale-session cleanup skipped",
            investigator_id=investigator_user_id,
            keep_session_id=keep_session_id,
            error=str(exc),
        )



@router.post("/investigate", response_model=InvestigationResponse)
async def start_investigation(
    file: UploadFile = File(...),  # noqa: B008
    case_id: str = Form(...),  # noqa: B008
    investigator_id: str = Form(...),  # noqa: B008
    client_sha256: str | None = Form(default=None),  # noqa: B008
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
        except Exception as exc:
            logger.debug("PIL fallback MIME detection failed", error=str(exc))

    # Sanitize original filename: take only the basename to prevent path
    # traversal, strip control chars that could corrupt log/report rendering.
    _safe_original_filename = Path(file.filename or "").name if file.filename else None
    raw_suffix = Path(file.filename or "").suffix.lower()
    if raw_suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400, detail=f"File extension '{raw_suffix}' is not permitted."
        )

    actual_mime = _canonicalize_supported_mime(actual_mime, raw_suffix)

    # Validate against SUPPORTED_MIME_TYPES
    if actual_mime not in SUPPORTED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"File type '{actual_mime}' is not allowed.")

    # Cross-reference with centralized policy to ensure agent support
    applicable_agents = get_applicable_agents(actual_mime)
    if not applicable_agents:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{actual_mime}' is not supported by any specialized forensic agent.",
        )

    valid_exts = EXACT_MIME_EXT_MAP.get(actual_mime, frozenset())
    if not valid_exts or raw_suffix not in valid_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Security violation: content '{actual_mime}' mismatch extension '{raw_suffix}'",
        )

    # Note: file.size can be None (no Content-Length header) or 0 — both are
    # valid. The authoritative size check is the streaming counter below.
    # This pre-read check is best-effort only for early rejection on large files.
    if file.size is not None and file.size > MAX_FILE_SIZE:
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
        # Stream chunks directly to the temp file using the underlying sync
        # SpooledTemporaryFile to avoid buffering the entire file in memory.
        # This prevents OOM under concurrent large uploads.
        def _stream_to_file():
            nonlocal total_size
            with tmp_path.open("wb") as out:
                while True:
                    chunk = file.file.read(1024 * 1024)
                    if not chunk:
                        break
                    total_size += len(chunk)
                    if total_size > MAX_FILE_SIZE:
                        return
                    hasher.update(chunk)
                    out.write(chunk)
        await asyncio.to_thread(_stream_to_file)
        if total_size > MAX_FILE_SIZE:
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="File size exceeds limit.")

        if total_size == 0:
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="File is empty.")

        content_hash = hasher.hexdigest()

        # P2.18 — now that the full file is on disk, use ffprobe to resolve the
        # MP4 audio/video ambiguity before the file is routed to an agent. libmagic
        # reports audio-only MP4/M4A as video/mp4; reclassify so it reaches the
        # audio specialist instead of the video one.
        if actual_mime in ("video/mp4", "application/mp4"):
            _has_video = await _mp4_has_real_video_stream(tmp_path)
            if _has_video is False:
                logger.info(
                    "ffprobe disambiguation: MP4 has no real video stream → audio/mp4",
                    session_id=session_id,
                )
                actual_mime = "audio/mp4"
                applicable_agents = get_applicable_agents(actual_mime)

        client_hash_verified = False
        if client_sha256 and isinstance(client_sha256, str):
            client_sha256_norm = client_sha256.strip().lower()
            if not re.fullmatch(r"[a-f0-9]{64}", client_sha256_norm):
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="Invalid client SHA-256 format.")
            if client_sha256_norm != content_hash:
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=400,
                    detail="Client SHA-256 does not match uploaded file content.",
                )
            client_hash_verified = True

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
        elif actual_mime.startswith(("audio/", "video/")):
            try:
                import subprocess

                result = await asyncio.to_thread(
                    subprocess.run,
                    ["ffprobe", "-v", "quiet", "-show_format", "-show_streams",
                     str(tmp_path)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode != 0:
                    raise HTTPException(
                        status_code=400,
                        detail="Audio/video container verification failed; file may be corrupted or unreadable.",
                    )
            except FileNotFoundError:
                logger.warning("ffprobe not available — skipping AV container verification")
            except HTTPException:
                raise
            except Exception as verify_error:
                logger.warning(
                    "AV container integrity check failed",
                    error=str(verify_error),
                )

        validated_extension = Path(file.filename or "").suffix.lower()

        # ── Preflight: visual context creation ────────────────────────────
        # Fire the preflight (three-section structured prompt covering
        # Agent1/Agent3/Agent5) immediately after validation, in parallel with
        # pipeline setup, so the VisualContext is waiting in Redis before agents run.
        # Restricted to image MIME types; audio/video agents don't use this context.
        #
        # IMPORTANT: only fire here when the BACKEND has its vision models warm
        # (BACKEND_PREWARM_FLORENCE). On a RAM-tight host we run the backend lean
        # (Florence pre-warm off), where a backend-built context falls back to a
        # categorical CLIP read (Florence lazy-load fails under uvicorn --reload).
        # In that mode we SKIP the backend preflight and let the WORKER build it
        # up-front (pipeline.py) — the worker has Florence pre-warmed, so the cached
        # context is the rich on-device caption, not a bare category. The worker's
        # build is awaited before any agent runs, so nothing races.
        import os as _os_pf
        _backend_has_vision = str(
            _os_pf.environ.get("BACKEND_PREWARM_FLORENCE", "")
        ).strip().lower() in ("1", "true", "yes", "on")
        if actual_mime.startswith("image/") and _backend_has_vision:
            # Best-effort optimization only — must never break the investigation
            # route. If it fails, agents fall back to their own visual profile.
            try:
                from core.visual_context_store import create_visual_context_preflight as _pf

                _pf_task = asyncio.create_task(
                    _pf(
                        session_id=session_id,
                        file_path=str(tmp_path),
                        sha256=content_hash,
                        config=settings,
                    )
                )
                _preflight_tasks.add(_pf_task)
                _pf_task.add_done_callback(_preflight_tasks.discard)
            except Exception as _pf_err:
                logger.debug("Visual context preflight dispatch skipped", error=str(_pf_err))

        session_metadata = {
            "status": "queued",
            "brief": "Initializing forensic pipeline...",
            "case_id": case_id,
            "investigator_id": current_user.user_id,
            "investigator_role": current_user.role.value,
            "case_investigator_label": investigator_id,
            "file_path": str(tmp_path),
            "original_filename": _safe_original_filename,
            "content_hash": content_hash,
            "client_hash_verified": client_hash_verified,
            "detected_mime": actual_mime,
            "validated_extension": validated_extension,
            "file_size_bytes": total_size,
            "applicable_agents": applicable_agents,
            "created_at": datetime.now(UTC).isoformat(),
        }
        await set_active_pipeline_metadata(session_id, session_metadata)

        pre_dispatch_status = "queued" if settings.use_redis_worker else "running"

        if settings.app_env == "production":
            try:
                await _register_session_before_dispatch(
                    session_id=session_id,
                    case_id=case_id,
                    investigator_id=current_user.user_id,
                    status=pre_dispatch_status,
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
                    status=pre_dispatch_status,
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
                    original_filename=_safe_original_filename,
                    detected_mime=actual_mime,
                    validated_extension=validated_extension,
                    content_sha256=content_hash,
                    file_size_bytes=total_size,
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
            await set_active_pipeline_metadata(
                session_id,
                {**session_metadata, "status": "running"},
            )
            task = asyncio.create_task(
                run_investigation_task(
                    session_id=session_id,
                    pipeline=pipeline,
                    evidence_file_path=str(tmp_path),
                    case_id=case_id,
                    investigator_id=current_user.user_id,
                    original_filename=_safe_original_filename,
                    detected_mime=actual_mime,
                    validated_extension=validated_extension,
                    content_sha256=content_hash,
                    file_size_bytes=total_size,
                )
            )
            set_active_task(session_id, task)
            pipeline_started = True

        increment_investigations_started()

        dispatch_mode = "worker" if settings.use_redis_worker else "in_process"
        response_status = "queued" if settings.use_redis_worker else "started"

        return InvestigationResponse(
            session_id=session_id,
            case_id=case_id,
            status=response_status,
            message=f"Investigation {response_status} for {_safe_original_filename or 'evidence'}. Track status via WebSocket.",
            content_hash=content_hash,
            client_hash_verified=client_hash_verified,
            dispatch_mode=dispatch_mode,
            detected_mime=actual_mime,
            applicable_agents=applicable_agents,
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
