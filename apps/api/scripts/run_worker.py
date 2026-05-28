"""
Forensic Council — Worker Entrypoint
====================================

Starts the background worker to consume and process forensic tasks from Redis.
"""

import asyncio
import os
import sys

# Ensure the backend directory is in the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Must be the first project import — patches bcrypt.__about__ before passlib loads
from core._bcrypt_shim import ensure_bcrypt_compat  # noqa: E402

ensure_bcrypt_compat()

from core.structured_logging import configure_root_logger, get_logger  # noqa: E402

from core.config import get_settings  # noqa: E402
from orchestration.worker import main  # noqa: E402

if __name__ == "__main__":
    settings = get_settings()
    configure_root_logger(settings.log_level)
    logger = get_logger("run_worker")
    logger.info("Starting Forensic Council Background Worker...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user.")
    except Exception as e:
        logger.critical(f"Worker failed with unhandled exception: {e}", exc_info=True)
        sys.exit(1)
