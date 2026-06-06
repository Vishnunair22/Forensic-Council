"""
Session Finalization
===================

Shared finalization helpers used by both in-process investigation_runner and the
external Redis worker. Ensures identical metadata/persistence/broadcast behavior
regardless of execution mode.
"""

from datetime import UTC, datetime

from api.routes._session_state import (
    broadcast_update,
    get_active_pipeline_metadata,
    set_final_report,
    update_active_pipeline_metadata,
)
from api.routes.metrics import (
    increment_investigations_completed,
    increment_investigations_failed,
)
from api.schemas import BriefUpdate
from core.session_persistence import get_session_persistence
from core.structured_logging import get_logger

logger = get_logger(__name__)

_WEBHOOKS_AVAILABLE = False
try:
    from api.routes.webhooks import fire_investigation_complete_webhook as _fire_webhook

    _WEBHOOKS_AVAILABLE = True
except ImportError:
    _fire_webhook = None


async def _get_investigator_metadata(session_id: str, investigator_id: str) -> tuple:
    existing_meta = await get_active_pipeline_metadata(session_id) or {}
    return (
        existing_meta.get("investigator_id", investigator_id),
        existing_meta.get("investigator_role"),
        existing_meta.get("case_investigator_label"),
    )


async def mark_investigation_completed(
    *,
    session_id: str,
    case_id: str,
    investigator_id: str,
    evidence_file_path: str,
    original_filename: str | None,
    report,
    arbiter=None,
) -> None:
    _investigator_id, _investigator_role, _case_label = await _get_investigator_metadata(
        session_id, investigator_id
    )

    # Idempotency guard: if already finalized, skip to prevent duplicate synthesis
    _early_meta = await get_active_pipeline_metadata(session_id) or {}
    if _early_meta.get("status") == "completed":
        logger.info(
            "mark_investigation_completed: session already completed, skipping duplicate call",
            session_id=session_id,
        )
        return

    # Retry narrative generation if per_agent_analysis is empty (all Groq calls timed out)
    if arbiter is not None and hasattr(arbiter, "regenerate_missing_narratives"):
        try:
            report = await arbiter.regenerate_missing_narratives(report)
        except Exception as narr_err:
            logger.warning(
                "Narrative regeneration failed — persisting with empty narratives",
                error=str(narr_err),
            )

    # Persist the signed report to durable storage BEFORE marking the session
    # as completed or broadcasting PIPELINE_COMPLETE. This ensures the report
    # survives Redis/cache loss.
    try:
        persistence = await get_session_persistence()
        await persistence.save_report(
            session_id=session_id,
            case_id=case_id,
            investigator_id=investigator_id,
            report_data=report.model_dump(mode="json"),
        )
        await persistence.update_session_status(session_id, "completed")
    except Exception as exc:
        logger.error("Failed to persist completed investigation", error=str(exc))
        await update_active_pipeline_metadata(
            session_id,
            {
                "status": "degraded",
                "brief": "Investigation completed but report persistence failed — may be lost on cache expiry.",
                "case_id": case_id,
                "investigator_id": _investigator_id,
                "investigator_role": _investigator_role,
                "case_investigator_label": _case_label,
                "file_path": evidence_file_path,
                "original_filename": original_filename,
                "error": str(exc),
                "report_id": str(report.report_id),
            },
        )
        await broadcast_update(
            session_id,
            BriefUpdate(
                type="DEGRADED",
                session_id=session_id,
                message="Investigation completed with persistence errors.",
                data={"status": "degraded", "error": str(exc)},
            ),
        )
        return

    await set_final_report(session_id, report)
    # F-15: use atomic CAS for terminal status transition
    await update_active_pipeline_metadata(
        session_id,
        {
            "status": "completed",
            "brief": "Investigation complete.",
            "case_id": case_id,
            "investigator_id": _investigator_id,
            "investigator_role": _investigator_role,
            "case_investigator_label": _case_label,
            "file_path": evidence_file_path,
            "original_filename": original_filename,
            "completed_at": datetime.now(UTC).isoformat(),
            "report_id": str(report.report_id),
        },
    )
    increment_investigations_completed()

    if _WEBHOOKS_AVAILABLE and _fire_webhook:
        try:
            await _fire_webhook(
                user_id=str(_investigator_id),
                session_id=session_id,
                case_id=case_id,
                verdict=str(getattr(report, "overall_verdict", "UNKNOWN")),
                manipulation_probability=float(
                    getattr(report, "manipulation_probability", 0.0)
                ),
                report_hash=str(getattr(report, "report_hash", "")),
            )
        except Exception as _wh_err:
            logger.warning("Webhook fire failed (non-fatal)", error=str(_wh_err))

    await broadcast_update(
        session_id,
        BriefUpdate(
            type="PIPELINE_COMPLETE",
            session_id=session_id,
            message="Investigation concluded.",
            data={"report_id": str(report.report_id)},
        ),
    )


async def mark_investigation_failed(
    *,
    session_id: str,
    case_id: str,
    investigator_id: str,
    evidence_file_path: str,
    original_filename: str | None,
    error: str,
) -> None:
    _investigator_id, _investigator_role, _case_label = await _get_investigator_metadata(
        session_id, investigator_id
    )

    logger.error("Investigation task failed", error=error, exc_info=True)
    increment_investigations_failed()

    # Write to DB first — clients polling after the ERROR broadcast need
    # a consistent DB state, so persist before broadcasting.
    try:
        persistence = await get_session_persistence()
        await persistence.update_session_status(session_id, "error", error)
    except Exception as exc:
        logger.error("Failed to persist failed investigation status", error=str(exc))

    await update_active_pipeline_metadata(
        session_id,
        {
            "status": "error",
            "brief": error,
            "case_id": case_id,
            "investigator_id": _investigator_id,
            "investigator_role": _investigator_role,
            "case_investigator_label": _case_label,
            "file_path": evidence_file_path,
            "original_filename": original_filename,
            "error": error,
        },
    )
    await broadcast_update(
        session_id,
        BriefUpdate(
            type="ERROR",
            session_id=session_id,
            message="Internal error. Please try again.",
            data={"error": error},
        ),
    )
