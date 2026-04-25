"""
Dead Man's Switch - Working Memory WAL Cleanup
==============================================

Automated purging of file-based Write-Ahead Logs (WAL) and ephemeral
working memory artifacts. Ensures 24-hour data TTL completion for
court-defensible forensic isolation.
"""

import tempfile
import time
from pathlib import Path

from core.structured_logging import get_logger

logger = get_logger(__name__)

# Constants
WAL_DIR_NAME = "forensic_council_wal"
RETENTION_HOURS = 24
RETENTION_SECONDS = RETENTION_HOURS * 3600


def purge_wal():
    """Purges the file-based WAL for expired sessions."""
    wal_dir = Path(tempfile.gettempdir()) / WAL_DIR_NAME

    if not wal_dir.exists():
        logger.info(f"WAL directory {wal_dir} not found. Nothing to clean.")
        return

    now = time.time()
    purged_count = 0
    total_size = 0

    logger.info(f"Starting Dead Man's Switch cleanup on {wal_dir}...")

    for wal_file in wal_dir.glob("*.json"):
        try:
            mtime = wal_file.stat().st_mtime
            if (now - mtime) > RETENTION_SECONDS:
                file_size = wal_file.stat().st_size
                wal_file.unlink()
                purged_count += 1
                total_size += file_size
                logger.debug(f"Purged expired WAL: {wal_file.name}")
        except Exception as e:
            logger.error(f"Failed to purge {wal_file}: {e}")

    logger.info(
        "WAL Cleanup Complete", files_removed=purged_count, bytes_freed=total_size, status="SECURE"
    )


def main():
    try:
        purge_wal()
    except Exception as e:
        logger.critical(f"Dead Man's Switch cleanup failed: {e}")


if __name__ == "__main__":
    main()
