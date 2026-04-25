#!/usr/bin/env python3
"""
Evidence retention enforcer.
Deletes evidence older than EVIDENCE_RETENTION_DAYS from the evidence store.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def get_db_connection():
    """Connect to Postgres for evidence queries."""
    import asyncpg
    
    return asyncpg.create_pool(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        user=os.getenv("POSTGRES_USER", "forensic_user"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        database=os.getenv("POSTGRES_DB", "forensic_council"),
        min_size=1,
        max_size=2,
    )


def get_evidence_paths_to_delete(pool: asyncpg.Pool, retention_days: int) -> list[str]:
    """Find evidence files older than retention_days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    
    query = """
        SELECT file_path FROM evidence 
        WHERE created_at < $1 
        AND file_path IS NOT NULL
    """
    
    async def _query():
        async with pool.acquire() as conn:
            return await conn.fetchval(query, cutoff)
    
    # For sync context, we'll just use file mtime instead
    evidence_dir = Path(os.getenv("EVIDENCE_STORAGE_PATH", "/app/storage/evidence"))
    if not evidence_dir.exists():
        return []
    
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=retention_days)
    to_delete = []
    
    for f in evidence_dir.rglob("*"):
        if f.is_file():
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff_dt:
                to_delete.append(str(f))
    
    return to_delete


def delete_evidence_files(paths: list[str]) -> int:
    """Delete old evidence files."""
    deleted = 0
    for path in paths:
        try:
            Path(path).unlink()
            deleted += 1
        except OSError as e:
            print(f"Failed to delete {path}: {e}")
    return deleted


async def enforce_retention() -> int:
    """Main retention enforcement."""
    retention_days = int(os.getenv("EVIDENCE_RETENTION_DAYS", "7"))
    
    # If we can't connect, skip (will retry next run)
    try:
        pool = await get_db_connection()
    except Exception as e:
        print(f"Skipping retention - DB unavailable: {e}")
        return 0
    
    paths = get_evidence_paths_to_delete(pool, retention_days)
    deleted = delete_evidence_files(paths)
    
    if deleted > 0:
        print(f"Deleted {deleted} old evidence files (retention: {retention_days} days)")
    else:
        print(f"No evidence to purge (retention: {retention_days} days)")
    
    await pool.close()
    return 0


if __name__ == "__main__":
    import asyncio
    exit(asyncio.run(enforce_retention()))