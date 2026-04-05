"""
Evidence Storage Cleanup Script
===============================

Automated purging of forensic evidence files based on retention policy.
Prevents storage exhaustion and reduces data liability.
"""

import os
import time
import shutil
from pathlib import Path
from core.config import get_settings
from core.structured_logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

def cleanup_evidence():
    """
    Purge evidence files older than EVIDENCE_RETENTION_DAYS.
    """
    storage_path = Path(settings.evidence_storage_path)
    if not storage_path.exists():
        logger.info(f"Storage path {storage_path} does not exist. Skipping cleanup.")
        return

    retention_seconds = settings.evidence_retention_days * 24 * 3600
    now = time.time()
    
    purged_count = 0
    purged_bytes = 0
    
    logger.info(f"Starting evidence cleanup (retention: {settings.evidence_retention_days} days)")
    
    # Evidence is usually stored in subdirectories by investigation ID
    for item in storage_path.iterdir():
        if item.is_dir():
            # Check the mtime of the directory
            mtime = item.stat().st_mtime
            if (now - mtime) > retention_seconds:
                try:
                    # Calculate size before deletion for logging
                    dir_size = sum(f.stat().st_size for f in item.glob('**/*') if f.is_file())
                    
                    shutil.rmtree(item)
                    purged_count += 1
                    purged_bytes += dir_size
                    logger.info(f"Purged expired evidence session: {item.name}", size_kb=dir_size//1024)
                except Exception as e:
                    logger.error(f"Failed to purge {item}: {e}")
                    
    if purged_count > 0:
        logger.info(
            "Evidence cleanup complete", 
            purged_sessions=purged_count, 
            freed_mb=purged_bytes // (1024 * 1024)
        )
    else:
        logger.info("No expired evidence sessions found.")

if __name__ == "__main__":
    cleanup_evidence()
