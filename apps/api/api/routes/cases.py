"""
Multi-Artifact Case Manager
=============================

Extends the investigation system to support multi-artifact cases —
e.g., an image + its matching audio + a suspected source video.

Problem solved (TD-09): Current system accepts exactly ONE file per session.
This prevents analysis of correlated evidence across media types.

Architecture:
  A CaseSession groups multiple artifacts under one case_id.
  Each artifact runs its own pipeline (same session_id family).
  The Arbiter aggregates findings across all artifacts.

API routes added:
  POST /api/v1/cases                    — Create a multi-artifact case
  POST /api/v1/cases/{case_id}/artifacts — Add evidence to a case
  POST /api/v1/cases/{case_id}/analyze  — Start analysis of all pending artifacts
  GET  /api/v1/cases/{case_id}          — Get case status + all artifact results

Usage pattern:
  1. POST /cases          → get case_id
  2. POST /cases/{id}/artifacts (repeat for each file)
  3. POST /cases/{id}/analyze
  4. GET  /cases/{id}     → poll for results
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from api.routes.investigation import (
    MAX_FILE_SIZE,
    _append_chunk,
    _detect_mime_from_head,
)
from core.file_type_policy import SUPPORTED_MIME_TYPES
from core.auth import get_current_user
from core.config import get_settings
from core.persistence.redis_client import get_redis_client
from core.structured_logging import get_logger

logger = get_logger(__name__)

cases_router = APIRouter(prefix="/api/v1/cases", tags=["cases"])

# Redis key prefixes
_CASE_META_PREFIX = "case_meta:"
_CASE_ARTIFACTS_PREFIX = "case_artifacts:"
_CASE_TTL = 60 * 60 * 24 * 7  # 7 days

# B-C-3: track dispatched case tasks so the graceful-shutdown sweep in
# main.py and `terminate_session` can observe them, and to prevent the
# garbage collector from cancelling an unrooted asyncio.create_task.
_dispatched_case_tasks: set[asyncio.Task[Any]] = set()


def _evidence_storage_dir() -> Path:
    """B-C-2: resolve evidence storage from the canonical setting
    (`evidence_storage_path`) rather than a non-existent `evidence_dir`
    attribute. Returns an absolute path so workers running in any CWD
    locate files reliably."""
    settings = get_settings()
    return Path(settings.evidence_storage_path).resolve()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class CaseArtifact(BaseModel):
    artifact_id: str
    session_id: str
    original_filename: str
    mime_type: str
    file_size_bytes: int
    status: str = "pending"  # pending | running | completed | failed
    added_at: str
    # B-C-2: persist the absolute storage path used at upload so analyze_case
    # can replay it without re-deriving from a hard-coded relative directory.
    storage_path: str | None = None


class CaseRecord(BaseModel):
    case_id: str
    investigator_id: str
    label: str
    artifacts: list[CaseArtifact] = []
    status: str = "open"  # open | analyzing | completed | partial_failure
    created_at: str
    completed_at: str | None = None
    combined_verdict: str | None = None
    manipulation_probability: float | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@cases_router.post("/", status_code=201)
async def create_case(
    label: str = Form(default=""),
    current_user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Create a new multi-artifact case.

    Returns case_id which is used to attach evidence artifacts.
    """
    redis = await get_redis_client()
    case_id = str(uuid.uuid4())[:8].upper()  # Short human-readable ID

    record = CaseRecord(
        case_id=case_id,
        investigator_id=str(current_user.user_id),
        label=label or f"Case {case_id}",
        created_at=datetime.now(UTC).isoformat(),
    )

    key = f"{_CASE_META_PREFIX}{case_id}"
    await redis.set(key, record.model_dump_json(), ex=_CASE_TTL)

    logger.info(
        "Case created",
        case_id=case_id,
        investigator_id=current_user.user_id,
        label=record.label,
    )

    return {
        "case_id": case_id,
        "label": record.label,
        "status": "open",
        "artifacts_url": f"/api/v1/cases/{case_id}/artifacts",
        "analyze_url": f"/api/v1/cases/{case_id}/analyze",
    }


@cases_router.post("/{case_id}/artifacts", status_code=201)
async def add_artifact(
    case_id: str,
    file: UploadFile = File(...),
    current_user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Add an evidence artifact (file) to an existing case.

    Up to 10 artifacts per case. Supported types: image, audio, video, PDF.
    """
    redis = await get_redis_client()

    # Load and validate case
    meta_key = f"{_CASE_META_PREFIX}{case_id}"
    raw = await redis.get(meta_key)
    if not raw:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    case = CaseRecord.model_validate_json(raw)
    if case.investigator_id != str(current_user.user_id):
        raise HTTPException(status_code=403, detail="Not authorized for this case")
    if case.status not in ("open",):
        raise HTTPException(status_code=409, detail=f"Case is {case.status} — cannot add artifacts")
    if len(case.artifacts) >= 10:
        raise HTTPException(status_code=422, detail="Case already has 10 artifacts (maximum)")

    # B-C-1: MIME sniff + extension/size validation BEFORE writing to disk —
    # mirrors the same guarantees as /investigate.
    head = await file.read(2048)
    await file.seek(0)
    actual_mime = await _detect_mime_from_head(head)
    if actual_mime not in SUPPORTED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"File type '{actual_mime}' is not allowed.")
    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds limit.")

    # B-C-2: resolve absolute storage directory from settings.
    storage_dir = _evidence_storage_dir()
    storage_dir.mkdir(parents=True, exist_ok=True)

    artifact_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    safe_name = Path(file.filename or "upload").name
    ext = Path(safe_name).suffix.lower() or ".bin"
    dest = (storage_dir / f"{session_id}{ext}").resolve()

    # B-C-1: stream chunked to disk via the same `_append_chunk` helper used
    # by /investigate. Enforces MAX_FILE_SIZE during the write so an oversize
    # upload cannot exhaust memory or disk before the size check.
    dest.write_bytes(b"")
    total_size = 0
    try:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > MAX_FILE_SIZE:
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="File size exceeds limit.")
            await asyncio.to_thread(_append_chunk, dest, chunk)
    except HTTPException:
        raise
    except Exception as exc:
        dest.unlink(missing_ok=True)
        logger.error("Failed to persist artifact chunk", case_id=case_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to store evidence") from exc

    if total_size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="File is empty.")

    artifact = CaseArtifact(
        artifact_id=artifact_id,
        session_id=session_id,
        original_filename=safe_name,
        mime_type=actual_mime,
        file_size_bytes=total_size,
        added_at=datetime.now(UTC).isoformat(),
        storage_path=str(dest),
    )

    case.artifacts.append(artifact)
    await redis.set(meta_key, case.model_dump_json(), ex=_CASE_TTL)

    logger.info(
        "Artifact added to case",
        case_id=case_id,
        artifact_id=artifact_id,
        filename=safe_name,
        size_bytes=total_size,
    )

    return {
        "artifact_id": artifact_id,
        "session_id": session_id,
        "case_id": case_id,
        "filename": safe_name,
        "status": "pending",
    }


@cases_router.post("/{case_id}/analyze", status_code=202)
async def analyze_case(
    case_id: str,
    current_user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Start forensic analysis for all pending artifacts in the case.

    Dispatches each artifact to the existing investigation pipeline.
    Returns 202 Accepted immediately — poll GET /cases/{case_id} for progress.
    """
    redis = await get_redis_client()

    meta_key = f"{_CASE_META_PREFIX}{case_id}"
    raw = await redis.get(meta_key)
    if not raw:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    case = CaseRecord.model_validate_json(raw)
    if case.investigator_id != str(current_user.user_id):
        raise HTTPException(status_code=403, detail="Not authorized for this case")

    pending = [a for a in case.artifacts if a.status == "pending"]
    if not pending:
        raise HTTPException(status_code=409, detail="No pending artifacts to analyze")

    # Import lazily to keep module import cheap and avoid circular deps.
    from api.routes._session_state import (
        set_active_pipeline,
        set_active_pipeline_metadata,
        set_active_task,
    )
    from orchestration.investigation_runner import run_investigation_task
    from orchestration.pipeline import ForensicCouncilPipeline

    settings = get_settings()
    investigator_id = str(current_user.user_id)
    dispatched: list[str] = []

    for artifact in pending:
        try:
            # B-C-2: prefer the persisted storage_path; fall back to deriving
            # from the configured evidence directory (covers legacy artifacts
            # uploaded before storage_path was recorded).
            if artifact.storage_path:
                evidence_path = Path(artifact.storage_path)
            else:
                ext = Path(artifact.original_filename).suffix.lower() or ".bin"
                evidence_path = _evidence_storage_dir() / f"{artifact.session_id}{ext}"

            if not evidence_path.exists():
                logger.error(
                    "Artifact evidence file missing on disk",
                    case_id=case_id,
                    artifact_id=artifact.artifact_id,
                    expected_path=str(evidence_path),
                )
                artifact.status = "failed"
                continue

            pipeline = ForensicCouncilPipeline(config=settings)
            artifact.status = "running"

            # B-C-3: register the pipeline + minimal metadata before dispatch
            # so HITL/terminate endpoints + the graceful-shutdown sweep see
            # this session. Then root the task in a module-level set so the
            # GC cannot collect it mid-run.
            set_active_pipeline(artifact.session_id, pipeline)
            await set_active_pipeline_metadata(
                artifact.session_id,
                {
                    "session_id": artifact.session_id,
                    "case_id": case_id,
                    "investigator_id": investigator_id,
                    "status": "running",
                    "source": "case",
                    "started_at": datetime.now(UTC).isoformat(),
                },
            )

            task = asyncio.create_task(
                run_investigation_task(
                    session_id=artifact.session_id,
                    pipeline=pipeline,
                    evidence_file_path=str(evidence_path),
                    case_id=case_id,
                    investigator_id=investigator_id,
                    original_filename=artifact.original_filename,
                ),
                name=f"case:{case_id}:artifact:{artifact.artifact_id}",
            )
            set_active_task(artifact.session_id, task)
            _dispatched_case_tasks.add(task)
            task.add_done_callback(_dispatched_case_tasks.discard)
            dispatched.append(artifact.artifact_id)

        except Exception as e:
            logger.error(
                "Failed to dispatch artifact",
                case_id=case_id,
                artifact_id=artifact.artifact_id,
                error=str(e),
            )
            artifact.status = "failed"

    case.status = "analyzing"
    await redis.set(meta_key, case.model_dump_json(), ex=_CASE_TTL)

    return {
        "case_id": case_id,
        "status": "analyzing",
        "dispatched_artifacts": len(dispatched),
        "artifact_session_ids": [
            a.session_id for a in case.artifacts if a.artifact_id in dispatched
        ],
        "results_url": f"/api/v1/cases/{case_id}",
    }


@cases_router.get("/{case_id}")
async def get_case(
    case_id: str,
    current_user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Get the current status and results of a multi-artifact case.

    Checks each artifact's session for completion and aggregates results.
    """
    redis = await get_redis_client()

    meta_key = f"{_CASE_META_PREFIX}{case_id}"
    raw = await redis.get(meta_key)
    if not raw:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    case = CaseRecord.model_validate_json(raw)
    if case.investigator_id != str(current_user.user_id):
        raise HTTPException(status_code=403, detail="Not authorized for this case")

    # Check artifact statuses from Redis session metadata
    from api.routes._session_state import get_active_pipeline_metadata

    artifact_results = []
    all_verdicts = []
    all_probs = []
    any_running = False
    any_failed = False
    # B-M-3: track whether the in-memory case record actually changed so we
    # only write back to Redis when there's a state delta. Previously every
    # GET refreshed the TTL and rewrote the value.
    dirty = False

    for artifact in case.artifacts:
        meta = await get_active_pipeline_metadata(artifact.session_id)
        if meta:
            session_status = meta.get("status", "running")
            if session_status == "completed":
                if artifact.status != "completed":
                    artifact.status = "completed"
                    dirty = True
                verdict = meta.get("verdict") or "UNKNOWN"
                prob = float(meta.get("manipulation_probability", 0.0))
                all_verdicts.append(verdict)
                all_probs.append(prob)
                artifact_results.append({
                    "artifact_id": artifact.artifact_id,
                    "session_id": artifact.session_id,
                    "filename": artifact.original_filename,
                    "status": "completed",
                    "verdict": verdict,
                    "manipulation_probability": prob,
                    "result_url": f"/api/v1/sessions/{artifact.session_id}/report",
                })
            elif session_status == "error":
                if artifact.status != "failed":
                    artifact.status = "failed"
                    dirty = True
                any_failed = True
                artifact_results.append({
                    "artifact_id": artifact.artifact_id,
                    "session_id": artifact.session_id,
                    "filename": artifact.original_filename,
                    "status": "failed",
                    "error": meta.get("brief", "Unknown error"),
                })
            else:
                any_running = True
                artifact_results.append({
                    "artifact_id": artifact.artifact_id,
                    "session_id": artifact.session_id,
                    "filename": artifact.original_filename,
                    "status": "running",
                    "brief": meta.get("brief", ""),
                })
        else:
            artifact_results.append({
                "artifact_id": artifact.artifact_id,
                "session_id": artifact.session_id,
                "filename": artifact.original_filename,
                "status": artifact.status,
            })

    # Aggregate case-level verdict
    combined_verdict = None
    combined_prob = None
    if all_verdicts:
        # Worst-case aggregation: use the most severe verdict
        severity_order = [
            "AUTHENTIC", "LIKELY_AUTHENTIC", "INCONCLUSIVE",
            "REVIEW_REQUIRED", "SUSPICIOUS", "MANIPULATED", "TAMPERED"
        ]
        most_severe = max(all_verdicts, key=lambda v: severity_order.index(v) if v in severity_order else 3)
        combined_verdict = most_severe
        combined_prob = round(max(all_probs), 4) if all_probs else None

    # Update case status
    new_status = case.status
    if not any_running and not any_failed and all_verdicts:
        new_status = "completed"
        if case.status != new_status:
            case.status = new_status
            case.combined_verdict = combined_verdict
            case.manipulation_probability = combined_prob
            case.completed_at = datetime.now(UTC).isoformat()
            dirty = True
    elif not any_running and any_failed:
        new_status = "partial_failure"
        if case.status != new_status:
            case.status = new_status
            dirty = True
    elif any_running:
        new_status = "analyzing"
        if case.status != new_status:
            case.status = new_status
            dirty = True

    # B-M-3: only persist when state actually changed.
    if dirty:
        await redis.set(meta_key, case.model_dump_json(), ex=_CASE_TTL)

    return {
        "case_id": case_id,
        "label": case.label,
        "status": case.status,
        "combined_verdict": combined_verdict,
        "combined_manipulation_probability": combined_prob,
        "artifacts": artifact_results,
        "created_at": case.created_at,
        "completed_at": case.completed_at,
    }
