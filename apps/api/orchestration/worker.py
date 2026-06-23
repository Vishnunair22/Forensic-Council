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
from typing import Any

# Add current directory to path so imports work when the worker is launched as a script.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from api.routes._session_state import (  # noqa: E402
    _active_pipelines,
    broadcast_update,
    clear_session_websockets,
    update_active_pipeline_metadata,
)
from api.schemas import BriefUpdate  # noqa: E402
from core.config import get_settings  # noqa: E402
from core.provider_quota_guard import configure_provider_quota_guards  # noqa: E402
from core.signing import get_keystore  # noqa: E402
from core.structured_logging import get_logger  # noqa: E402
from orchestration.investigation_queue import (  # noqa: E402
    InvestigationWorker,
    get_investigation_queue,
)
from orchestration.pipeline import ForensicCouncilPipeline  # noqa: E402
from orchestration.pipeline_registry import register_pipeline, unregister_pipeline  # noqa: E402
from orchestration.session_finalization import (  # noqa: E402
    mark_investigation_completed,
    mark_investigation_failed,
)
from scripts.cleanup_storage import cleanup_evidence  # noqa: E402

logger = get_logger("worker")


async def main() -> None:
    """Main worker entry point."""
    settings = get_settings()
    configure_provider_quota_guards(settings)
    logger.info("Starting Forensic Council Worker", pid=os.getpid())

    # Fail-loud self-test + numba/librosa pre-warm. Catches the silent-degradation
    # class (e.g. NUMBA_DISABLE_JIT breaking audio tools, model load failures) and
    # warms the JIT so the first audio analysis isn't slow. Threaded so the compile
    # doesn't block boot; never fatal.
    try:
        from core.startup_diagnostics import run_startup_diagnostics

        await asyncio.to_thread(run_startup_diagnostics)
    except Exception as _diag_exc:
        logger.warning("Startup diagnostics failed (non-fatal)", error=str(_diag_exc))

    keystore = get_keystore()
    await keystore.initialize()
    logger.info("Signing key store initialized in worker")

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
            logger.error("ML warmup failed in worker", error=str(exc), exc_info=True)

        # Pre-warm EasyOCR reader so model init never happens on the request path
        try:
            import asyncio as _asyncio

            from tools.ocr_tools import _get_easyocr_reader
            loop = _asyncio.get_running_loop()
            await loop.run_in_executor(None, _get_easyocr_reader)
            logger.info("EasyOCR reader pre-warmed successfully")
        except Exception as exc:
            logger.warning("EasyOCR pre-warm failed (non-fatal)", error=str(exc))

        # Pre-warm in-process inference models (SigLIP/CLIP perceptual fingerprint
        # + object detector). These are lazy-loaded on first use; if the FIRST
        # investigation cold-loads them on the request path, the load can exceed
        # the per-tool timeout (e.g. neural_fingerprint's 20s) under tool
        # contention and fall back — making neural_fingerprint intermittently
        # NOT_APPLICABLE and the per-agent confidence/check-count wobble between
        # otherwise identical clean runs (87%/3 checks vs 90%/4). Warming them
        # here keeps the applicable-tool set, confidence and counts deterministic.
        try:
            from core.inference_client import get_inference_client

            _ic = await get_inference_client()
            await _ic.get_siglip_analyzer()
            await _ic.get_yolo_model()
            logger.info("In-process inference models (SigLIP, object detector) pre-warmed")
        except Exception as exc:
            logger.warning("Inference-model pre-warm failed (non-fatal)", error=str(exc))

    _warmup_task = asyncio.create_task(_warmup_background())

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
        detected_mime: str | None = None,
        validated_extension: str | None = None,
        content_sha256: str | None = None,
        file_size_bytes: int | None = None,
    ):
        session_str = str(session_id)

        try:
            # F-15: use atomic CAS for session status transition; the route
            # already wrote metadata before enqueueing.
            await update_active_pipeline_metadata(
                session_str,
                {
                    "status": "running",
                    "brief": "Initializing forensic pipeline...",
                    "case_id": case_id,
                    "file_path": evidence_file_path,
                    "original_filename": original_filename,
                    "detected_mime": detected_mime,
                    "validated_extension": validated_extension,
                    "content_sha256": content_sha256,
                    "file_size_bytes": file_size_bytes,
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

            try:
                from core.persistence.redis_client import get_redis_client as _get_rc

                _rc = await _get_rc()
                await _rc.client.sadd("metrics:active_sessions", session_str)
            except Exception as _reg_err:
                logger.debug(
                    "Failed to register session in metrics:active_sessions",
                    session_id=session_str,
                    error=str(_reg_err),
                )

            report = await pipeline.run_investigation(
                evidence_file_path=evidence_file_path,
                case_id=case_id,
                investigator_id=investigator_id,
                original_filename=original_filename,
                session_id=session_id,
                detected_mime=detected_mime,
                validated_extension=validated_extension,
                content_sha256=content_sha256,
                file_size_bytes=file_size_bytes,
            )

            await mark_investigation_completed(
                session_id=session_str,
                case_id=case_id,
                investigator_id=investigator_id,
                evidence_file_path=evidence_file_path,
                original_filename=original_filename,
                report=report,
                arbiter=getattr(pipeline, "arbiter", None),
            )

            return report

        except Exception as exc:
            error_msg = str(exc)
            await mark_investigation_failed(
                session_id=session_str,
                case_id=case_id,
                investigator_id=investigator_id,
                evidence_file_path=evidence_file_path,
                original_filename=original_filename,
                error=error_msg,
            )
            # Clear the content-hash dedup key so the same file can be
            # re-submitted after a failure. In in-process mode this is
            # handled by investigation_runner.py; the worker must do it here.
            try:
                from core.persistence.redis_client import get_redis_client as _get_rc
                _rc = await _get_rc()
                _meta_raw = await _rc.get(f"forensic:session:metadata:{session_str}")
                if _meta_raw:
                    import json as _json
                    _m = _json.loads(_meta_raw) if isinstance(_meta_raw, (str, bytes)) else {}
                    # Route writes "content_hash"; worker writes "content_sha256".
                    # Read both so dedup cleanup works regardless of which path set it.
                    _hash = _m.get("content_sha256") or _m.get("content_hash") or ""
                    _cid = _m.get("case_id") or case_id
                    if _hash:
                        await _rc.delete(f"dedup:{_cid}:{_hash}")
            except Exception as _dedup_err:
                logger.warning("Failed to clear dedup key on worker failure", error=str(_dedup_err))
            raise
        finally:
            try:
                if os.path.exists(evidence_file_path):
                    os.unlink(evidence_file_path)
                    logger.debug("Cleaned up temporary evidence file", path=evidence_file_path)
            except Exception as e:
                logger.warning(
                    "Failed to cleanup evidence file", path=evidence_file_path, error=str(e)
                )
            _active_pipelines.pop(session_str, None)
            unregister_pipeline(session_id)
            clear_session_websockets(session_str)
            # O-C-1 (B-H-10): remove from the Redis-backed active-sessions
            # set so the gauge reflects only currently-running pipelines.
            try:
                from core.persistence.redis_client import get_redis_client as _get_rc

                _rc = await _get_rc()
                await _rc.client.srem("metrics:active_sessions", session_str)
            except Exception as _unreg_err:
                logger.debug(
                    "Failed to unregister session from metrics:active_sessions",
                    session_id=session_str,
                    error=str(_unreg_err),
                )

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

            # Prune expired investigation_state rows from Postgres so the
            # table doesn't grow without bound. This is the only place where
            # cleanup_expired_sessions is invoked.
            try:
                from core.session_persistence import get_session_persistence
                _persistence = await get_session_persistence()
                _pruned = await _persistence.cleanup_expired_sessions()
                if _pruned:
                    logger.info("Pruned expired investigation_state rows", count=_pruned)
            except Exception as exc:
                logger.warning("DB session cleanup failed (non-fatal)", error=str(exc))

            try:
                await asyncio.wait_for(shutdown.wait(), timeout=24 * 3600)
            except TimeoutError:
                pass  # 24-hour timer expired normally; loop back for another cleanup cycle.

    cleanup_task = asyncio.create_task(periodic_cleanup())

    async def notify_decision_consumer() -> None:
        import json

        from core.persistence.redis_client import get_redis_client
        from orchestration.pipeline_registry import notify_decision

        while not shutdown.is_set():
            pubsub = None
            try:
                redis = await get_redis_client()
                pubsub = redis.get_pubsub()
                await pubsub.subscribe("forensic:notify_decision")
                logger.info("Worker subscribed to forensic:notify_decision")

                while not shutdown.is_set():
                    try:
                        message = await pubsub.get_message(
                            ignore_subscribe_messages=True,
                            timeout=5.0,
                        )
                    except TimeoutError:
                        continue
                    if not message or message.get("type") != "message":
                        continue
                    try:
                        data = json.loads(message["data"])
                        session_id_val = data.get("session_id")
                        deep_analysis_val = data.get("deep_analysis")
                        checkpoint_id_val = data.get("checkpoint_id")
                        from uuid import UUID

                        if session_id_val is not None and deep_analysis_val is not None:
                            # Initial→deep / deep→report gate decision.
                            notify_decision(UUID(session_id_val), deep_analysis_val)
                        elif session_id_val is not None and checkpoint_id_val is not None:
                            # Per-agent HITL checkpoint decision. The pipeline runs
                            # in THIS worker process, so look it up in the registry
                            # and apply the decision directly. Without this branch
                            # worker-mode HITL decisions were silently dropped.
                            from orchestration.pipeline_registry import get_pipeline

                            _pipeline = get_pipeline(UUID(session_id_val))
                            if _pipeline is None:
                                logger.warning(
                                    "HITL decision received but no live pipeline in worker",
                                    session_id=session_id_val,
                                    checkpoint_id=checkpoint_id_val,
                                )
                            else:
                                from core.react_loop import HumanDecision

                                _human = HumanDecision(
                                    decision_type=data.get("decision"),
                                    investigator_id=data.get("investigator_id", "system"),
                                    notes=data.get("note", "") or "",
                                    override_finding=data.get("override_finding"),
                                )
                                await _pipeline.handle_hitl_decision(
                                    session_id=UUID(session_id_val),
                                    checkpoint_id=UUID(checkpoint_id_val),
                                    decision=_human,
                                )
                                logger.info(
                                    "Applied worker-mode HITL decision",
                                    session_id=session_id_val,
                                    checkpoint_id=checkpoint_id_val,
                                    decision=data.get("decision"),
                                )
                    except Exception as parse_err:
                        logger.error(
                            "Failed to parse notify_decision message", error=str(parse_err)
                        )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("notify_decision_consumer reconnecting", error=str(e))
                await asyncio.sleep(2)
            finally:
                if pubsub is not None:
                    try:
                        await pubsub.close()
                    except Exception:
                        logger.debug("Failed to close pubsub on reconnect", exc_info=True)

    consumer_task = asyncio.create_task(notify_decision_consumer())

    # Wait for model warmup BEFORE starting the worker so the first
    # investigation doesn't pay the cold-start penalty (CLIP ~26s, DETR ~15s).
    try:
        await asyncio.wait_for(_warmup_task, timeout=90.0)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        logger.warning("Model warmup timed out or was cancelled — worker will cold-start on first request")

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
        _warmup_task.cancel()
        try:
            await _warmup_task
        except (asyncio.CancelledError, Exception):
            pass
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
