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

    # Save the uploaded file
    settings = get_settings()
    storage_dir = Path(settings.evidence_dir) if hasattr(settings, "evidence_dir") else Path("storage/evidence")
    storage_dir.mkdir(parents=True, exist_ok=True)

    artifact_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    safe_name = Path(file.filename or "upload").name
    ext = Path(safe_name).suffix.lower() or ".bin"
    dest = storage_dir / f"{session_id}{ext}"

    contents = await file.read()
    dest.write_bytes(contents)

    artifact = CaseArtifact(
        artifact_id=artifact_id,
        session_id=session_id,
        original_filename=safe_name,
        mime_type=file.content_type or "application/octet-stream",
        file_size_bytes=len(contents),
        added_at=datetime.now(UTC).isoformat(),
    )

    case.artifacts.append(artifact)
    await redis.set(meta_key, case.model_dump_json(), ex=_CASE_TTL)

    logger.info(
        "Artifact added to case",
        case_id=case_id,
        artifact_id=artifact_id,
        filename=safe_name,
        size_bytes=len(contents),
    )

    return {
        "artifact_id": artifact_id,
        "session_id": session_id,
        "case_id": case_id,
        "filename": safe_name,
        "status": "pending",
    }


@cases_router.post("/{case_id}/analyze")
async def analyze_case(
    case_id: str,
    current_user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Start forensic analysis for all pending artifacts in the case.

    Dispatches each artifact to the existing investigation pipeline.
    Returns immediately — poll GET /cases/{case_id} for progress.
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

    # Import investigation pipeline lazily
    from orchestration.investigation_runner import run_investigation_task
    from orchestration.pipeline import ForensicCouncilPipeline

    settings = get_settings()
    dispatched = []

    for artifact in pending:
        try:
            pipeline = ForensicCouncilPipeline(config=settings)

            # Update artifact status to running
            artifact.status = "running"

            # Dispatch pipeline as background task
            asyncio.create_task(
                run_investigation_task(
                    session_id=artifact.session_id,
                    pipeline=pipeline,
                    evidence_file_path=str(
                        Path("storage/evidence") / f"{artifact.session_id}{Path(artifact.original_filename).suffix}"
                    ),
                    case_id=case_id,
                    investigator_id=str(current_user.user_id),
                    original_filename=artifact.original_filename,
                ),
                name=f"case:{case_id}:artifact:{artifact.artifact_id}",
            )
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

    for artifact in case.artifacts:
        meta = await get_active_pipeline_metadata(artifact.session_id)
        if meta:
            session_status = meta.get("status", "running")
            if session_status == "completed":
                artifact.status = "completed"
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
                artifact.status = "failed"
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
    if not any_running and not any_failed:
        case.status = "completed"
        case.combined_verdict = combined_verdict
        case.manipulation_probability = combined_prob
        case.completed_at = datetime.now(UTC).isoformat()
    elif not any_running and any_failed:
        case.status = "partial_failure"
    else:
        case.status = "analyzing"

    # Persist updated case
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
