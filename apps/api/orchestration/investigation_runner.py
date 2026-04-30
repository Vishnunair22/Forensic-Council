"""
Investigation Runner
====================

Shared in-process investigation execution helper used by the API route.
The external Redis worker has its own process entry point in ``worker.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from api.routes._session_state import (
    _active_tasks,
    broadcast_update,
    clear_session_websockets,
    get_active_pipeline_metadata,
    get_session_websockets,  # noqa: F401 - kept for legacy tests/monkeypatches.
    remove_active_pipeline,
    set_active_pipeline_metadata,
    set_final_report,
)
from api.routes.metrics import (
    increment_investigations_completed,
    increment_investigations_failed,
)
from api.schemas import BriefUpdate
from core.session_persistence import get_session_persistence
from core.structured_logging import get_logger
from orchestration.pipeline import ForensicCouncilPipeline

logger = get_logger(__name__)


async def _wrap_pipeline_with_broadcasts(
    pipeline: ForensicCouncilPipeline,
    evidence_file_path: str,
    case_id: str,
    investigator_id: str,
    original_filename: str | None,
    session_id: str,
):
    """Run the pipeline and return the produced report."""
    return await pipeline.run_investigation(
        evidence_file_path=evidence_file_path,
        case_id=case_id,
        investigator_id=investigator_id,
        original_filename=original_filename,
        session_id=UUID(session_id),
    )


async def run_investigation_task(
    session_id: str,
    pipeline: ForensicCouncilPipeline,
    evidence_file_path: str,
    case_id: str,
    investigator_id: str,
    original_filename: str | None = None,
) -> None:
    """Run an investigation in-process and persist its terminal state."""
    try:
        report = await _wrap_pipeline_with_broadcasts(
            pipeline=pipeline,
            evidence_file_path=evidence_file_path,
            case_id=case_id,
            investigator_id=investigator_id,
            original_filename=original_filename,
            session_id=session_id,
        )
        # Robust identity preservation: read the investigator UUID from initial metadata
        # so that completion/error updates don't overwrite it with the frontend label.
        existing_meta = await get_active_pipeline_metadata(session_id) or {}
        _investigator_id = existing_meta.get("investigator_id", investigator_id)
        _investigator_role = existing_meta.get("investigator_role")
        _case_label = existing_meta.get("case_investigator_label")

        await set_final_report(session_id, report)
        await set_active_pipeline_metadata(
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
                "created_at": existing_meta.get("created_at"),
                "completed_at": datetime.now(UTC).isoformat(),
                "report_id": str(report.report_id),
            },
        )
        increment_investigations_completed()
        await broadcast_update(
            session_id,
            BriefUpdate(
                type="PIPELINE_COMPLETE",
                session_id=session_id,
                message="Investigation concluded.",
                data={"report_id": str(report.report_id)},
            ),
        )

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

    except Exception as exc:
        error_msg = str(exc)
        logger.error("Investigation task failed", error=error_msg, exc_info=True)
        increment_investigations_failed()
        existing_meta = await get_active_pipeline_metadata(session_id) or {}
        _investigator_id = existing_meta.get("investigator_id", investigator_id)
        _investigator_role = existing_meta.get("investigator_role")
        _case_label = existing_meta.get("case_investigator_label")

        await set_active_pipeline_metadata(
            session_id,
            {
                "status": "error",
                "brief": error_msg,
                "case_id": case_id,
                "investigator_id": _investigator_id,
                "investigator_role": _investigator_role,
                "case_investigator_label": _case_label,
                "file_path": evidence_file_path,
                "original_filename": original_filename,
                "error": error_msg,
            },
        )
        await broadcast_update(
            session_id,
            BriefUpdate(
                type="ERROR",
                session_id=session_id,
                message="Internal error. Please try again.",
                data={"error": error_msg},
            ),
        )
    finally:
        try:
            from pathlib import Path

            Path(evidence_file_path).unlink(missing_ok=True)
        except Exception:
            logger.warning("Failed to remove temporary evidence file", path=evidence_file_path)
        remove_active_pipeline(session_id)
        _active_tasks.pop(session_id, None)
        clear_session_websockets(session_id)
