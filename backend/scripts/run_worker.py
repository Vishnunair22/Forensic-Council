"""
Forensic Council — Worker Entrypoint
====================================

Starts the background worker to consume and process forensic tasks from Redis.
"""

import asyncio
import os
import sys

from core.structured_logging import get_logger

# Ensure the backend directory is in the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from worker import main

logger = get_logger("run_worker")

if __name__ == "__main__":
    logger.info("Starting Forensic Council Background Worker...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user.")
    except Exception as e:
        logger.critical(f"Worker failed with unhandled exception: {e}", exc_info=True)
        sys.exit(1)
