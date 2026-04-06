"""
Forensic Council Worker Entry Point
===================================

This script runs a background worker that consumes forensic investigation
tasks from the Redis queue.
"""

import asyncio
import signal
import sys
import os
from typing import Any
from scripts.cleanup_storage import cleanup_evidence

# Add current directory to path so imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.structured_logging import get_logger
from orchestration.investigation_queue import get_investigation_queue, InvestigationWorker
from orchestration.pipeline import ForensicCouncilPipeline
from core.config import get_settings

logger = get_logger("worker")
settings = get_settings()

async def main():
    """Main worker entry point."""
    logger.info("Starting Forensic Council Worker", pid=os.getpid())

    # ── Graceful shutdown event ─────────────────────────────────────────────
    # Docker sends SIGTERM before SIGKILL (default grace period: 10 s).
    # We set this event on SIGTERM/SIGINT so the worker finishes its current
    # task and drains the queue before exiting rather than being killed mid-flight.
    _shutdown = asyncio.Event()

    def _handle_signal(sig):
        logger.info("Received shutdown signal — draining worker", signal=sig.name)
        _shutdown.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _handle_signal, sig)
        except (NotImplementedError, OSError):
            # Windows does not support loop.add_signal_handler for SIGTERM
            signal.signal(sig, lambda s, f: _shutdown.set())

    queue = get_investigation_queue()
    worker = InvestigationWorker(queue, worker_id=os.getpid())

    # ── Investigation handler ───────────────────────────────────────────────
    async def investigation_handler(
        evidence_file_path: str,
        case_id: str,
        investigator_id: str,
        original_filename: str | None = None,
        session_id: Any = None,
    ):
        pipeline = ForensicCouncilPipeline()
        return await pipeline.run_investigation(
            evidence_file_path=evidence_file_path,
            case_id=case_id,
            investigator_id=investigator_id,
            original_filename=original_filename,
            session_id=session_id,
        )

    worker.set_handler(investigation_handler)

    # ── Periodic evidence cleanup (every 24 hours) ──────────────────────────
    async def periodic_cleanup():
        while not _shutdown.is_set():
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(cleanup_evidence),
                    timeout=3600,
                )
            except asyncio.TimeoutError:
                logger.error("Periodic cleanup exceeded 1-hour timeout — skipping cycle")
            except Exception as e:
                logger.error("Periodic cleanup failed", error=str(e))
            # Wait 24 h or until shutdown — whichever comes first
            try:
                await asyncio.wait_for(_shutdown.wait(), timeout=24 * 3600)
            except asyncio.TimeoutError:
                pass  # Normal 24-h cycle — continue loop

    cleanup_task = asyncio.create_task(periodic_cleanup())

    try:
        # Run worker until shutdown signal
        worker_task = asyncio.create_task(worker.start())
        await _shutdown.wait()
        logger.info("Shutdown signal received — stopping worker gracefully")
        worker_task.cancel()
        try:
            await worker_task
        except (asyncio.CancelledError, Exception):
            pass
    except Exception as e:
        logger.critical("Worker crashed", error=str(e), exc_info=True)
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
