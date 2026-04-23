"""
Forensic Council Worker Entry Point
===================================

Runs a background worker that consumes forensic investigation tasks from the
Redis queue.
"""

import asyncio
import os
import signal
import sys
from datetime import UTC, datetime
from typing import Any

# Add current directory to path so imports work when the worker is launched as a script.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from api.routes._session_state import (  # noqa: E402
    _active_pipelines,
    broadcast_update,
    clear_session_websockets,
    set_active_pipeline_metadata,
    set_final_report,
)
from api.routes.metrics import (  # noqa: E402
    increment_investigations_completed,
    increment_investigations_failed,
)
from api.schemas import BriefUpdate  # noqa: E402
from core.config import get_settings  # noqa: E402
from core.session_persistence import get_session_persistence  # noqa: E402
from core.structured_logging import get_logger  # noqa: E402
from orchestration.investigation_queue import (  # noqa: E402
    InvestigationWorker,
    get_investigation_queue,
)
from orchestration.pipeline import ForensicCouncilPipeline  # noqa: E402
from scripts.cleanup_storage import cleanup_evidence  # noqa: E402

logger = get_logger("worker")
settings = get_settings()


async def main() -> None:
    """Main worker entry point."""
    logger.info("Starting Forensic Council Worker", pid=os.getpid())

    try:
        from core.ml_subprocess import warmup_all_tools

        logger.info("Pre-warming ML tools in worker")
        warmup_results = await warmup_all_tools(timeout_per_tool=120.0)
        succeeded = sum(1 for value in warmup_results.values() if value)
        total = len(warmup_results)

        if succeeded < total:
            logger.warning(
                f"Only {succeeded}/{total} ML tools warmed up",
                failed_tools=[name for name, ok in warmup_results.items() if not ok],
            )
        else:
            logger.info(f"All {total} ML tools warmed up successfully")
    except Exception as exc:
        logger.warning("ML warmup failed in worker", error=str(exc))

    shutdown = asyncio.Event()

    def handle_signal(sig: signal.Signals) -> None:
        logger.info("Received shutdown signal; draining worker", signal=sig.name)
        shutdown.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, handle_signal, sig)
        except (NotImplementedError, OSError):
            # Windows does not support loop.add_signal_handler for SIGTERM.
            signal.signal(sig, lambda _signal, _frame: shutdown.set())

    queue = get_investigation_queue()
    worker = InvestigationWorker(queue, worker_id=os.getpid())

    async def investigation_handler(
        evidence_file_path: str,
        case_id: str,
        investigator_id: str,
        original_filename: str | None = None,
        session_id: Any = None,
    ):
        session_str = str(session_id)

        try:
            await set_active_pipeline_metadata(
                session_str,
                {
                    "status": "running",
                    "brief": "Initializing forensic pipeline...",
                    "case_id": case_id,
                    "investigator_id": investigator_id,
                    "file_path": evidence_file_path,
                    "original_filename": original_filename,
                    "created_at": datetime.now(UTC).isoformat(),
                },
            )
            await broadcast_update(
                session_str,
                BriefUpdate(
                    type="AGENT_UPDATE",
                    session_id=session_str,
                    message="Initializing forensic pipeline; loading specialist agents.",
                    data={"status": "starting"},
                ),
            )

            pipeline = ForensicCouncilPipeline()
            report = await pipeline.run_investigation(
                evidence_file_path=evidence_file_path,
                case_id=case_id,
                investigator_id=investigator_id,
                original_filename=original_filename,
                session_id=session_id,
            )

            await broadcast_update(
                session_str,
                BriefUpdate(
                    type="PIPELINE_COMPLETE",
                    session_id=session_str,
                    message="Investigation concluded.",
                    data={"report_id": str(report.report_id)},
                ),
            )
            await set_final_report(session_str, report)
            await set_active_pipeline_metadata(
                session_str,
                {
                    "status": "completed",
                    "brief": "Investigation complete.",
                    "case_id": case_id,
                    "investigator_id": investigator_id,
                    "file_path": evidence_file_path,
                    "original_filename": original_filename,
                    "created_at": datetime.now(UTC).isoformat(),
                    "completed_at": datetime.now(UTC).isoformat(),
                    "report_id": str(report.report_id),
                },
            )
            increment_investigations_completed()

            try:
                persistence = await get_session_persistence()
                await persistence.save_report(
                    session_id=session_str,
                    case_id=case_id,
                    investigator_id=investigator_id,
                    report_data=report.model_dump(mode="json"),
                )
                await persistence.update_session_status(session_str, "completed")
            except Exception as exc:
                logger.error(f"DB persistence fail: {exc}")

            return report

        except Exception as exc:
            error_msg = str(exc)
            logger.error(f"Investigation failed: {exc}", exc_info=True)
            increment_investigations_failed()
            await broadcast_update(
                session_str,
                BriefUpdate(
                    type="ERROR",
                    session_id=session_str,
                    message="Internal error. Please try again.",
                    data={"error": error_msg},
                ),
            )
            try:
                await set_active_pipeline_metadata(
                    session_str,
                    {
                        "status": "error",
                        "brief": error_msg,
                        "case_id": case_id,
                        "investigator_id": investigator_id,
                        "file_path": evidence_file_path,
                        "original_filename": original_filename,
                        "error": error_msg,
                    },
                )
            except Exception:
                pass
            raise
        finally:
            try:
                if os.path.exists(evidence_file_path):
                    os.unlink(evidence_file_path)
            except Exception:
                pass
            _active_pipelines.pop(session_str, None)
            clear_session_websockets(session_str)

    worker.set_handler(investigation_handler)

    async def periodic_cleanup() -> None:
        while not shutdown.is_set():
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(cleanup_evidence),
                    timeout=3600,
                )
            except TimeoutError:
                logger.error("Periodic cleanup exceeded 1-hour timeout; skipping cycle")
            except Exception as exc:
                logger.error("Periodic cleanup failed", error=str(exc))

            try:
                await asyncio.wait_for(shutdown.wait(), timeout=24 * 3600)
            except TimeoutError:
                pass

    cleanup_task = asyncio.create_task(periodic_cleanup())

    try:
        worker_task = asyncio.create_task(worker.start())
        await shutdown.wait()
        logger.info("Shutdown signal received; stopping worker gracefully")
        worker_task.cancel()
        try:
            await worker_task
        except (asyncio.CancelledError, Exception):
            pass
    except Exception as exc:
        logger.critical("Worker crashed", error=str(exc), exc_info=True)
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except (asyncio.CancelledError, Exception):
            pass
        await worker.stop()
        logger.info("Worker stopped cleanly")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
