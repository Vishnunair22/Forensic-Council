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
    logger.info("Starting Forensic Council Worker")
    
    queue = get_investigation_queue()
    worker = InvestigationWorker(queue, worker_id=os.getpid())
    
    # Define the handler for investigations
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
            session_id=session_id
        )
    
    worker.set_handler(investigation_handler)
    
    # 3. Schedule periodic cleanup (every 24 hours)
    async def periodic_cleanup():
        while True:
            try:
                # Timeout cleanup after 1 hour to prevent stacking
                await asyncio.wait_for(
                    asyncio.to_thread(cleanup_evidence),
                    timeout=3600
                )
            except asyncio.TimeoutError:
                logger.error("Periodic cleanup exceeded 1 hour timeout — cancelling")
            except Exception as e:
                logger.error(f"Periodic cleanup failed: {e}")
            await asyncio.sleep(24 * 3600)

    cleanup_task = asyncio.create_task(periodic_cleanup())
    
    try:
        await worker.start()
    except Exception as e:
        logger.critical("Worker crashed", error=str(e), exc_info=True)
    finally:
        cleanup_task.cancel()
        await worker.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
