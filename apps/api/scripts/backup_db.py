#!/usr/bin/env python3
"""
Postgres backup cron task.
Runs pg_dump to preserve custody evidence data.
"""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def run_backup() -> int:
    """Run pg_dump and save to volume mount."""
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "forensic_user")
    db = os.getenv("POSTGRES_DB", "forensic_council")

    backup_dir = Path("/app/storage/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"forensic_{db}_{timestamp}.sql.gz"
    backup_path = backup_dir / filename

    cmd = [
        "pg_dump",
        "-h",
        host,
        "-p",
        port,
        "-U",
        user,
        "-d",
        db,
        "-Fc",  # custom format for compression
        "-f",
        str(backup_path),
    ]

    env = os.environ.copy()
    env["PGPASSWORD"] = os.getenv("POSTGRES_PASSWORD", "")

    try:
        subprocess.run(
            cmd,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        print(f"Backup saved: {backup_path}")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"Backup failed: {e.stderr}")
        return 1


if __name__ == "__main__":
    exit(run_backup())
