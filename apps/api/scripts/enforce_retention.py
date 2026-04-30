#!/usr/bin/env python3
"""
Evidence retention enforcer.
Deletes evidence older than EVIDENCE_RETENTION_DAYS from the evidence store.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import get_settings  # noqa: E402
from core.structured_logging import get_logger  # noqa: E402

logger = get_logger(__name__)


async def _connect() -> asyncpg.Pool:
    s = get_settings()
    return await asyncpg.create_pool(
        host=s.postgres_host,
        port=int(s.postgres_port),
        user=s.postgres_user,
        password=s.postgres_password,
        database=s.postgres_db,
        min_size=1,
        max_size=2,
    )


async def enforce_retention() -> int:
    s = get_settings()
    days = s.evidence_retention_days
    cutoff = datetime.now(UTC) - timedelta(days=days)
    evidence_dir = Path(s.evidence_storage_path)
    if not evidence_dir.exists():
        logger.info("evidence dir missing", path=str(evidence_dir))
        return 0

    deleted_files = 0
    pool: asyncpg.Pool | None = None
    try:
        pool = await _connect()
    except Exception as e:
        logger.warning("Postgres unreachable; running file-only sweep", error=str(e))

    for f in evidence_dir.rglob("*"):
        if not f.is_file():
            continue
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=UTC)
        if mtime >= cutoff:
            continue
        try:
            f.unlink()
            deleted_files += 1
        except OSError as e:
            logger.warning("delete failed", path=str(f), error=str(e))

    deleted_rows = 0
    if pool is not None:
        async with pool.acquire() as conn:
            result = await conn.fetchval(
                "DELETE FROM evidence WHERE created_at < $1 RETURNING count(*)",
                cutoff,
            )
            deleted_rows = result or 0
        await pool.close()

    logger.info("retention sweep complete", files=deleted_files, rows=deleted_rows, days=days)
    return deleted_files


if __name__ == "__main__":
    raise SystemExit(asyncio.run(enforce_retention()))
