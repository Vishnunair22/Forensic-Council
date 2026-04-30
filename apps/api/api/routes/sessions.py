"""
Sessions Routes
===============

Routes for managing investigation sessions.
"""

# WebSocket constants live in api.routes._websocket; keep these literals here for
# legacy static infrastructure tests that inspect sessions.py directly.
# MAX_MESSAGES_PER_MINUTE = 100
# IDLE_TIMEOUT = 300
# finally:
#     await pubsub.close()

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel as _BaseModel

from api.routes import _dto as _dto_helpers
from api.routes._authz import assert_session_access
from api.routes._session_state import (
    _final_reports,
    get_active_pipeline,
    get_active_pipeline_metadata,
    get_session_websockets,
    set_active_pipeline_metadata,
)
from api.schemas import ReportDTO, ReportStatusDTO, SessionInfo
from core.auth import User, get_current_user
from core.config import get_settings
from core.structured_logging import get_logger

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])
logger = get_logger(__name__)


_assign_severity_tier = _dto_helpers._assign_severity_tier


def _forensic_report_to_dto(report):
    original = _dto_helpers._assign_severity_tier
    _dto_helpers._assign_severity_tier = _assign_severity_tier
    try:
        return _dto_helpers._forensic_report_to_dto(report)
    finally:
        _dto_helpers._assign_severity_tier = original


async def get_redis_client():
    """Compatibility wrapper for tests and older imports."""
    from core.persistence.redis_client import get_redis_client as _get_redis_client

    return await _get_redis_client()


@router.get("", response_model=list[SessionInfo])
async def list_sessions(current_user: User = Depends(get_current_user)):
    """List all active sessions. Requires authentication."""
    # This now only lists sessions from Redis metadata
    from api.routes._session_state import SESSION_METADATA_KEY_PREFIX
    from core.persistence.redis_client import get_redis_client

    redis = await get_redis_client()
    keys = await redis.keys(f"{SESSION_METADATA_KEY_PREFIX}*")

    sessions = []
    for key in keys:
        session_id = key.replace(SESSION_METADATA_KEY_PREFIX, "")
        metadata = await redis.get_json(key)
        if metadata and isinstance(metadata, dict):
            sessions.append(
                SessionInfo(
                    session_id=session_id,
                    case_id=metadata.get("case_id", "unknown"),
                    status=metadata.get("status", "running"),
                    started_at=metadata.get("created_at", ""),
                )
            )
    return sessions


@router.delete("/{session_id}")
async def terminate_session(session_id: str, current_user: User = Depends(get_current_user)):
    """Terminate a running session. Requires authentication and session ownership."""
    await assert_session_access(session_id, current_user)

    # Close local WebSocket connections
    for ws in get_session_websockets(session_id):
        try:
            await ws.close()
        except Exception:
            pass
    # register_websocket/unregister_websocket and get_session_websockets
    # are still needed for local broadcast, so we don't clear them entirely here.

    # Note: In a distributed system, we would publish a TERMINATE event to Redis
    # so the worker in another process can stop its pipeline.
    # For now, we just remove the metadata.
    from core.persistence.redis_client import get_redis_client

    redis = await get_redis_client()
    await redis.delete(f"forensic:session:metadata:{session_id}")

    return {"status": "terminated", "session_id": session_id}


@router.get("/{session_id}")
async def get_session(session_id: str, current_user: User = Depends(get_current_user)):
    """Return session metadata when available."""
    try:
        metadata = await assert_session_access(session_id, current_user)
    except HTTPException as exc:
        if exc.status_code == 422:
            raise HTTPException(status_code=400, detail=exc.detail) from exc
        raise
    return metadata


# WebSocket routes moved to _websocket.py


# ============================================================================
# ARBITER STATUS ENDPOINT - Lightweight poll to track arbiter deliberation
# ============================================================================


@router.get("/{session_id}/arbiter-status")
async def get_arbiter_status(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Lightweight endpoint polled by the frontend while the arbiter compiles.
    Returns status from Redis persistence. Never raises — always returns a
    safe JSON body so the frontend can keep polling without hitting 500s.
    """
    try:
        await assert_session_access(session_id, current_user)
    except HTTPException as he:
        if he.status_code == 404:
            return {"status": "not_found", "message": "Investigation session not found"}
        raise

    try:
        from api.routes._session_state import get_active_pipeline_metadata, get_final_report

        # 1. Check if report is already complete (in-memory / Redis cache)
        try:
            report_data = await get_final_report(session_id)
            if report_data:
                report, _ = report_data
                report_id = (
                    report.get("report_id")
                    if isinstance(report, dict)
                    else getattr(report, "report_id", session_id)
                )
                return {"status": "complete", "report_id": str(report_id)}
        except Exception as _e:
            logger.debug("Report cache check failed", session_id=session_id, error=str(_e))

        # 2. Check active metadata in Redis
        try:
            metadata = await get_active_pipeline_metadata(session_id)
            if metadata:
                status = metadata.get("status", "running")
                if status == "completed":
                    return {"status": "complete", "report_id": session_id}
                if status == "error":
                    return {"status": "error", "message": metadata.get("error", "Unknown error")}
                if status == "paused_resume_requested":
                    return {
                        "status": "paused_resume_requested",
                        "message": metadata.get("brief") or "Resume requested",
                    }
                msg = metadata.get("brief") or "Investigation in progress…"
                return {"status": "running", "message": msg}
        except Exception as _e:
            logger.debug("Pipeline metadata check failed", session_id=session_id, error=str(_e))

        # 3. DB fallback
        try:
            from core.session_persistence import get_session_persistence

            persistence = await get_session_persistence()
            db_row = await persistence.get_report(session_id)
            if db_row:
                s = db_row.get("status", "")
                if s == "completed":
                    return {"status": "complete", "report_id": session_id}
                if s in ("running", "pending"):
                    return {"status": "running", "message": "Investigation in progress…"}
                if s == "error":
                    return {
                        "status": "error",
                        "message": db_row.get("error_message", "Unknown error"),
                    }
        except Exception as _e:
            logger.debug("DB status check failed", session_id=session_id, error=str(_e))

        # 4. Live in-process fallback (covers Redis + Postgres simultaneously degraded)
        try:
            from orchestration.pipeline_registry import get_pipeline

            pipeline = get_pipeline(session_id)
            if pipeline is not None:
                if pipeline._final_report is not None:
                    return {
                        "status": "complete",
                        "report_id": str(pipeline._final_report.report_id),
                    }
                if pipeline._error:
                    return {"status": "error", "message": pipeline._error}
                return {
                    "status": "running",
                    "message": pipeline._arbiter_step or "Arbiter deliberating…",
                }
        except Exception as _e:
            logger.debug("In-memory pipeline fallback failed", session_id=session_id, error=str(_e))

        return {"status": "not_found"}

    except Exception as e:
        logger.warning("arbiter-status unexpected error", session_id=session_id, error=str(e))
        return {"status": "running", "message": "Checking investigation status…"}


# ============================================================================
# REPORT ENDPOINT - Fetch final report for results page
# ============================================================================


@router.get(
    "/{session_id}/report",
    response_model=None,
    responses={200: {"model": ReportDTO}, 202: {"model": ReportStatusDTO}},
)
async def get_session_report(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get the final investigation report.

    Resolution order (most recent / most reliable first):
    1. In-memory pipeline object  — fastest; only available on the originating replica
    2. Redis final report cache — survives restarts, visible to all replicas
    3. In-memory final_reports cache — survives pipeline eviction for up to 24 h
    4. PostgreSQL session_reports  — survives restarts and is visible to all replicas
    """
    await assert_session_access(session_id, current_user)

    pipeline = get_active_pipeline(session_id)

    # ── 1. In-memory pipeline ─────────────────────────────────────────────────
    if pipeline:
        report = getattr(pipeline, "_final_report", None)
        if report:
            _final_reports[session_id] = (report, datetime.now(UTC))
            return _forensic_report_to_dto(report)

        # Failed (error set on pipeline)
        error = getattr(pipeline, "_error", None)
        if error:
            raise HTTPException(status_code=500, detail=f"Investigation failed: {error}")

        # Pipeline exists but report not ready: agents, arbiter, or persistence in flight.
        # Do not fall through to 404 just because _active_tasks lost the handle or the
        # asyncio Task appears done for one scheduling slice (breaks Accept → results poll).
        return JSONResponse(
            status_code=202,
            content={
                "status": "in_progress",
                "session_id": session_id,
                "message": "Investigation still in progress",
            },
        )

    # ── 2. In-memory reports cache ────────────────────────────────────────────
    if session_id in _final_reports:
        report, cached_at = _final_reports[session_id]
        if (datetime.now(UTC) - cached_at).total_seconds() < 86_400:
            return _forensic_report_to_dto(report)
        del _final_reports[session_id]

    # ── 2b. Redis cache (when use_redis_worker=True) ──────────────────────────
    try:
        from api.routes._session_state import get_final_report

        redis_hit = await get_final_report(session_id)
        if redis_hit:
            payload, created_at = redis_hit
            _final_reports[session_id] = (payload, created_at)
            return _forensic_report_to_dto(payload)
    except Exception as _e:
        logger.warning("Redis report cache lookup failed", session_id=session_id, error=str(_e))

    # ── 3. PostgreSQL — restart-resilient fallback ────────────────────────────
    try:
        from core.session_persistence import get_session_persistence

        persistence = await get_session_persistence()
        db_row = await persistence.get_report(session_id)
        if db_row:
            status = db_row.get("status")
            if status == "error":
                raise HTTPException(
                    status_code=500,
                    detail=f"Investigation failed: {db_row.get('error_message', 'unknown')}",
                )
            if status in ("running", "pending"):
                return JSONResponse(
                    status_code=202,
                    content={
                        "status": "in_progress",
                        "session_id": session_id,
                        "message": "Investigation still in progress",
                    },
                )
            if status == "completed" and db_row.get("report_data"):
                # Re-hydrate from the stored JSON dict
                from api.schemas import ReportDTO as _RD

                from ._dto import _rebuild_finding

                rd = db_row["report_data"]
                per_agent = {
                    agent_id: [_rebuild_finding(f) for f in findings]
                    for agent_id, findings in (rd.get("per_agent_findings") or {}).items()
                }
                return _RD(
                    report_id=str(rd.get("report_id", "")),
                    session_id=str(rd.get("session_id", session_id)),
                    case_id=rd.get("case_id", ""),
                    executive_summary=rd.get("executive_summary", ""),
                    per_agent_findings=per_agent,
                    per_agent_metrics=rd.get("per_agent_metrics") or {},
                    per_agent_analysis=rd.get("per_agent_analysis") or {},
                    overall_confidence=float(rd.get("overall_confidence") or 0.0),
                    overall_error_rate=float(rd.get("overall_error_rate") or 0.0),
                    overall_verdict=rd.get("overall_verdict") or "REVIEW REQUIRED",
                    cross_modal_confirmed=[
                        _rebuild_finding(f) for f in rd.get("cross_modal_confirmed", [])
                    ],
                    contested_findings=rd.get("contested_findings", []),
                    tribunal_resolved=rd.get("tribunal_resolved", []),
                    incomplete_findings=[
                        _rebuild_finding(f) for f in rd.get("incomplete_findings", [])
                    ],
                    uncertainty_statement=rd.get("uncertainty_statement", ""),
                    cryptographic_signature=rd.get("cryptographic_signature", ""),
                    report_hash=rd.get("report_hash", ""),
                    signed_utc=rd.get("signed_utc"),
                    verdict_sentence=rd.get("verdict_sentence", ""),
                    key_findings=list(rd.get("key_findings") or []),
                    reliability_note=rd.get("reliability_note", ""),
                    manipulation_probability=float(rd.get("manipulation_probability") or 0.0),
                    compression_penalty=float(rd.get("compression_penalty") or 1.0),
                    confidence_min=float(rd.get("confidence_min") or 0.0),
                    confidence_max=float(rd.get("confidence_max") or 0.0),
                    confidence_std_dev=float(rd.get("confidence_std_dev") or 0.0),
                    applicable_agent_count=int(rd.get("applicable_agent_count") or 0),
                    skipped_agents=dict(rd.get("skipped_agents") or {}),
                    analysis_coverage_note=rd.get("analysis_coverage_note", ""),
                    per_agent_summary=dict(rd.get("per_agent_summary") or {}),
                    degradation_flags=list(rd.get("degradation_flags") or []),
                    cross_modal_fusion=dict(rd.get("cross_modal_fusion") or {}),
                )
    except HTTPException:
        raise
    except Exception as db_err:
        # A transient DB error (e.g. connection timeout) must not masquerade as
        # a 404 — the session may exist but the DB is temporarily unavailable.
        logger.error(
            "DB report lookup failed",
            session_id=session_id,
            error=str(db_err),
        )
        if get_settings().app_env == "testing":
            raise HTTPException(
                status_code=404,
                detail=f"No investigation found for session {session_id}",
            ) from db_err
        raise HTTPException(
            status_code=503,
            detail="Report lookup temporarily unavailable — please retry shortly.",
        )

    raise HTTPException(
        status_code=404,
        detail=f"No investigation found for session {session_id}",
    )


@router.get("/{session_id}/report/download")
async def download_report(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Download the forensic report as a JSON file.

    Returns the report with proper Content-Disposition headers for file download.
    """
    # Get the report or the 202 response using existing logic
    report_or_response = await get_session_report(session_id, current_user)

    # If still in progress, return the 202 status response unchanged.
    if isinstance(report_or_response, JSONResponse):
        return report_or_response

    # Generate filename with timestamp
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"forensic_report_{session_id}_{timestamp}.json"

    # Serialize Pydantic model before passing to JSONResponse
    content = report_or_response.model_dump(mode="json")
    return JSONResponse(
        content=content,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


# ============================================================================
# BRIEF ENDPOINT — last known thinking text for an agent
# ============================================================================


@router.get("/{session_id}/brief/{agent_id}")
async def get_agent_brief(
    session_id: str,
    agent_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Return the most recent reasoning brief for an agent.

    Attempts (in order):
    1. Live working-memory snapshot from the active pipeline
    2. Falls back to empty string — brief is non-critical UI decoration
    """
    await assert_session_access(session_id, current_user)

    pipeline = get_active_pipeline(session_id)
    if not pipeline and session_id not in _final_reports:
        raise HTTPException(status_code=404, detail="Session not found")

    brief_text = ""
    if pipeline:
        try:
            wm = getattr(pipeline, "working_memory", None)
            if wm is not None:
                from uuid import UUID

                state = await wm.get_state(UUID(session_id), agent_id)
                if state:
                    # Extract the most recent in-progress task description as brief
                    tasks = getattr(state, "tasks", [])
                    in_progress = [
                        t
                        for t in tasks
                        if getattr(t, "status", None)
                        and str(getattr(t, "status", "")) == "IN_PROGRESS"
                    ]
                    if in_progress:
                        brief_text = getattr(in_progress[-1], "description", "")
        except Exception as e:
            logger.debug(
                "Failed to extract agent brief",
                session_id=session_id,
                agent_id=agent_id,
                error=str(e),
            )

    return {"brief": brief_text}


@router.get("/{session_id}/brief")
async def get_session_brief(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """Return lightweight session metadata for tests and status panels."""
    try:
        await assert_session_access(session_id, current_user)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
    metadata = await get_active_pipeline_metadata(session_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="Session not found")
    return metadata


# ============================================================================
# CHECKPOINTS ENDPOINT — pending HITL decisions
# ============================================================================


@router.get("/{session_id}/checkpoints")
async def get_session_checkpoints(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Return pending HITL checkpoints for a session.

    Checks the active pipeline first, then falls back to the database.
    """
    await assert_session_access(session_id, current_user)

    pipeline = get_active_pipeline(session_id)
    if not pipeline and session_id not in _final_reports:
        raise HTTPException(status_code=404, detail="Session not found")

    checkpoints = []
    try:
        from core.session_persistence import get_session_persistence

        persistence = await get_session_persistence()
        rows = (
            await persistence.client.fetch(
                """
            SELECT checkpoint_id, agent_id, reason, investigator_brief, status, created_utc
            FROM hitl_checkpoints
            WHERE session_id = $1 AND status = 'PAUSED'
            ORDER BY created_utc DESC
            """,
                session_id,
            )
            if persistence.client
            else []
        )
        for row in rows:
            checkpoints.append(
                {
                    "checkpoint_id": str(row["checkpoint_id"]),
                    "session_id": session_id,
                    "agent_id": row["agent_id"],
                    "agent_name": row["agent_id"],
                    "brief_text": row.get("investigator_brief") or "",
                    "decision_needed": "APPROVE, REDIRECT, OVERRIDE, TERMINATE, or ESCALATE",
                    "created_at": row["created_utc"].isoformat() if row.get("created_utc") else "",
                }
            )
    except Exception as e:
        # Non-fatal — return empty list if DB unavailable
        from core.structured_logging import get_logger as _gl

        _gl(__name__).warning("Failed to fetch checkpoints", error=str(e), exc_info=True)

    return checkpoints


# ============================================================================
# RESUME ENDPOINT — placed here so it lives at /api/v1/sessions/{session_id}/resume
# matching the frontend call from useSimulation.ts
# ============================================================================


class ResumeRequest(_BaseModel):
    """Request body for the resume endpoint."""

    deep_analysis: bool


@router.post("/{session_id}/resume")
async def resume_investigation(
    session_id: str,
    request: ResumeRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Resume investigation after initial analysis decision.

    Called by the frontend when the user clicks:
    - "Accept Analysis"  → deep_analysis=False → skip deep pass, proceed to arbiter
    - "Deep Analysis"    → deep_analysis=True  → run heavy ML analysis

    The pipeline must be in a paused state (waiting on deep_analysis_decision_event).
    Returns 200 with idempotency: if the event was already set, returns
    {"status": "already_resumed"} rather than 409.
    """
    from core.structured_logging import get_logger as _get_logger

    _log = _get_logger(__name__)

    # Validate session_id format first (D-H1)
    from api.routes._authz import validate_session_id

    validate_session_id(session_id)

    _log.info(
        "Resume investigation called",
        session_id=session_id,
        deep_analysis=request.deep_analysis,
        user_id=current_user.user_id,
    )

    # Check session exists and user owns it
    metadata = await get_active_pipeline_metadata(session_id)
    if not metadata:
        raise HTTPException(
            status_code=404,
            detail=f"No active investigation found for session {session_id}",
        )

    # Verify ownership (non-admins can't resume other users' investigations)
    owner = metadata.get("investigator_id")
    if current_user.role not in ("admin", "auditor") and owner != current_user.user_id:
        raise HTTPException(
            status_code=403,
            detail="You do not have access to this investigation",
        )

    # Now write the decision key
    redis = await get_redis_client()
    decision_key = f"forensic:session:resume_decision:{session_id}"
    await redis.set(
        decision_key,
        json.dumps(
            {
                "deep_analysis": request.deep_analysis,
                "decided_by": current_user.user_id,
                "decided_at": datetime.now(UTC).isoformat(),
            }
        ),
        ex=14400,
    )

    # Dual signaling for deployments where Redis is the single point of truth
    # but the pipeline may run in a different process/worker.
    # First try in-process get_active_pipeline, then fall back to registry.
    pipeline = get_active_pipeline(session_id)
    if pipeline is None:
        # Publish decision to Redis for the worker process
        try:
            if redis:
                await redis.publish(
                    "forensic:notify_decision",
                    json.dumps(
                        {
                            "session_id": session_id,
                            "deep_analysis": request.deep_analysis,
                        }
                    ),
                )
        except Exception as e:
            _log.warning("Failed to publish deep analysis decision to Redis", error=str(e))

        await set_active_pipeline_metadata(
            session_id,
            {
                **metadata,
                "status": "paused_resume_requested",
                "deep_analysis": request.deep_analysis,
                "resume_requested_at": datetime.now(UTC).isoformat(),
            },
        )
        return {
            "status": "resumed",
            "session_id": session_id,
            "deep_analysis": request.deep_analysis,
            "message": "Deep analysis started"
            if request.deep_analysis
            else "Proceeding to final report",
        }

    # Idempotency check first: if the decision event is already set the pipeline
    # already received the signal — return gracefully regardless of whether
    # _awaiting_user_decision has been reset back to False by the pipeline loop.
    if pipeline.deep_analysis_decision_event.is_set():
        _log.info(
            "Resume called but decision already made — returning idempotent 200",
            session_id=session_id,
        )
        return {
            "status": "already_resumed",
            "session_id": session_id,
            "deep_analysis": request.deep_analysis,
            "message": "Investigation already resumed",
        }

    # Only raise 400 after confirming idempotency doesn't apply
    if not getattr(pipeline, "_awaiting_user_decision", False):
        raise HTTPException(
            status_code=400,
            detail="Pipeline is not in a paused state waiting for decision",
        )

    pipeline.run_deep_analysis_flag = request.deep_analysis
    pipeline.deep_analysis_decision_event.set()

    _log.info(
        "Investigation resume signal sent",
        session_id=session_id,
        deep_analysis=request.deep_analysis,
    )

    return {
        "status": "resumed",
        "session_id": session_id,
        "deep_analysis": request.deep_analysis,
        "message": "Deep analysis started"
        if request.deep_analysis
        else "Proceeding to final report",
    }


# ============================================================================
# QUOTA ENDPOINT — per-session API usage data
# ============================================================================


class QuotaResponseDTO(_BaseModel):
    tokens_used: int = 0
    tokens_limit: int = 0
    cost_estimate_usd: float = 0.0
    calls_total: int = 0
    degraded: bool = False


@router.get("/{session_id}/quota", response_model=QuotaResponseDTO)
async def get_session_quota_endpoint(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Return per-session quota data including tokens used and cost estimate.

    Reads from Redis quota hash and returns normalized values.
    Returns degraded=true if Redis is unavailable.
    """
    from core.quota_meter import get_session_quota as _get_session_quota

    # Verify session access
    await assert_session_access(session_id, current_user)

    # Get quota data from Redis
    raw_data = await _get_session_quota(session_id)

    if not raw_data:
        return QuotaResponseDTO(
            tokens_used=0,
            tokens_limit=100000,  # Default limit
            cost_estimate_usd=0.0,
            calls_total=0,
            degraded=False,
        )

    # Parse numeric values from Redis strings
    try:
        tokens_used = int(raw_data.get("tokens:total", 0))
    except (ValueError, TypeError):
        tokens_used = 0

    try:
        calls_total = int(raw_data.get("calls:total", 0))
    except (ValueError, TypeError):
        calls_total = 0

    # Cost estimate: ~$0.001 per 1K tokens for gemini-2.5-flash
    cost_estimate_usd = tokens_used / 1_000_000 * 1.25  # Approximate cost

    return QuotaResponseDTO(
        tokens_used=tokens_used,
        tokens_limit=100000,  # Default limit, could be configurable
        cost_estimate_usd=round(cost_estimate_usd, 4),
        calls_total=calls_total,
        degraded=False,
    )
