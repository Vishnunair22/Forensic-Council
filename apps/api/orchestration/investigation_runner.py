"""
Investigation Runner
=====================

Shared in-process investigation execution helper used by the API route.
The external Redis worker has its own process entry point in ``worker.py``.
"""

from __future__ import annotations

from uuid import UUID

from api.routes._session_state import (
    _active_tasks,
    clear_session_websockets,
    remove_active_pipeline,
)
from core.structured_logging import get_logger
from orchestration.pipeline import ForensicCouncilPipeline
from orchestration.session_finalization import (
    mark_investigation_completed,
    mark_investigation_failed,
)

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

        await mark_investigation_completed(
            session_id=session_id,
            case_id=case_id,
            investigator_id=investigator_id,
            evidence_file_path=evidence_file_path,
            original_filename=original_filename,
            report=report,
            arbiter=getattr(pipeline, "arbiter", None),
        )

    except Exception as exc:
        error_msg = str(exc)
        await mark_investigation_failed(
            session_id=session_id,
            case_id=case_id,
            investigator_id=investigator_id,
            evidence_file_path=evidence_file_path,
            original_filename=original_filename,
            error=error_msg,
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
