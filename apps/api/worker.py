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
    get_active_pipeline_metadata,
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
from orchestration.pipeline_registry import register_pipeline, unregister_pipeline  # noqa: E402
from scripts.cleanup_storage import cleanup_evidence  # noqa: E402

logger = get_logger("worker")
settings = get_settings()


async def main() -> None:
    """Main worker entry point."""
    logger.info("Starting Forensic Council Worker", pid=os.getpid())

    async def _warmup_background() -> None:
        try:
            from core.ml_subprocess import warmup_all_tools

            logger.info("Pre-warming ML tools in worker (background)")
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

    asyncio.create_task(_warmup_background())

    shutdown = asyncio.Event()

    def handle_signal(sig: signal.Signals) -> None:
        logger.info("Received shutdown signal; draining worker", signal=sig.name)
        shutdown.set()

    def handle_signal_sync(sig: signal.Signals, frame: Any) -> None:
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(shutdown.set)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, handle_signal, sig)
        except (NotImplementedError, OSError):
            signal.signal(sig, handle_signal_sync)

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
            # Robust identity preservation: check for existing metadata
            # This is critical for the Redis worker where uvicorn/main API may have 
            # already set the initial UUID.
            existing_meta = await get_active_pipeline_metadata(session_str) or {}
            _investigator_id = existing_meta.get("investigator_id", investigator_id)
            _investigator_role = existing_meta.get("investigator_role")
            _case_label = existing_meta.get("case_investigator_label")

            await set_active_pipeline_metadata(
                session_str,
                {
                    "status": "running",
                    "brief": "Initializing forensic pipeline...",
                    "case_id": case_id,
                    "investigator_id": _investigator_id,
                    "investigator_role": _investigator_role,
                    "case_investigator_label": _case_label,
                    "file_path": evidence_file_path,
                    "original_filename": original_filename,
                    "created_at": existing_meta.get("created_at") or datetime.now(UTC).isoformat(),
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
            _active_pipelines[session_str] = pipeline
            register_pipeline(session_id, pipeline)

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
            # Refresh metadata to get the latest UUID/label
            existing_meta = await get_active_pipeline_metadata(session_str) or {}
            _investigator_id = existing_meta.get("investigator_id", investigator_id)
            _investigator_role = existing_meta.get("investigator_role")
            _case_label = existing_meta.get("case_investigator_label")

            await set_active_pipeline_metadata(
                session_str,
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
                # Refresh metadata to get the latest UUID/label
                existing_meta = await get_active_pipeline_metadata(session_str) or {}
                _investigator_id = existing_meta.get("investigator_id", investigator_id)
                _investigator_role = existing_meta.get("investigator_role")
                _case_label = existing_meta.get("case_investigator_label")

                await set_active_pipeline_metadata(
                    session_str,
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
            except Exception:
                pass  # Redis may be down in the error path; outer exception is re-raised regardless.
            raise
        finally:
            try:
                if os.path.exists(evidence_file_path):
                    os.unlink(evidence_file_path)
                    logger.debug("Cleaned up temporary evidence file", path=evidence_file_path)
            except Exception as e:
                logger.warning("Failed to cleanup evidence file", path=evidence_file_path, error=str(e))
            _active_pipelines.pop(session_str, None)
            unregister_pipeline(session_id)
            clear_session_websockets(session_str)

    worker.set_handler(investigation_handler)

    async def periodic_cleanup() -> None:
        cleanup_timeout = int(os.environ.get("CLEANUP_TIMEOUT_SECONDS", "3600"))
        while not shutdown.is_set():
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(cleanup_evidence),
                    timeout=cleanup_timeout,
                )
            except TimeoutError:
                logger.error("Periodic cleanup exceeded 1-hour timeout; skipping cycle")
            except Exception as exc:
                logger.error("Periodic cleanup failed", error=str(exc))

            try:
                await asyncio.wait_for(shutdown.wait(), timeout=24 * 3600)
            except TimeoutError:
                pass  # 24-hour timer expired normally; loop back for another cleanup cycle.

    cleanup_task = asyncio.create_task(periodic_cleanup())

    async def notify_decision_consumer() -> None:
        from core.persistence.redis_client import get_redis_client
        import json
        from orchestration.pipeline_registry import notify_decision
        
        try:
            redis = await get_redis_client()
            pubsub = redis.pubsub()
            await pubsub.subscribe("forensic:notify_decision")
            logger.info("Worker subscribed to forensic:notify_decision")
            
            async for message in pubsub.listen():
                if shutdown.is_set():
                    break
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        session_id_val = data.get("session_id")
                        deep_analysis_val = data.get("deep_analysis")
                        if session_id_val is not None and deep_analysis_val is not None:
                            from uuid import UUID
                            notify_decision(UUID(session_id_val), deep_analysis_val)
                    except Exception as parse_err:
                        logger.error("Failed to parse notify_decision message", error=str(parse_err))
        except Exception as e:
            logger.error("notify_decision_consumer failed", error=str(e))

    consumer_task = asyncio.create_task(notify_decision_consumer())

    try:
        worker_task = asyncio.create_task(worker.start())
        await shutdown.wait()
        logger.info("Shutdown signal received; stopping worker gracefully")
        worker_task.cancel()
        try:
            await worker_task
        except (asyncio.CancelledError, Exception):
            pass  # Expected: task was just cancelled for graceful shutdown.
    except Exception as exc:
        logger.critical("Worker crashed", error=str(exc), exc_info=True)
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except (asyncio.CancelledError, Exception):
            pass  # Expected: cleanup task was just cancelled for graceful shutdown.
        consumer_task.cancel()
        try:
            await consumer_task
        except (asyncio.CancelledError, Exception):
            pass
        await worker.stop()
        logger.info("Worker stopped cleanly")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
