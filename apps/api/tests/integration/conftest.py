"""
Integration test conftest — ensures api.routes is importable.

The backend root (apps/api/) must NOT be a Python package itself,
otherwise pytest walks up the tree and adds apps/ to sys.path first,
which makes 'api' resolve to the backend root instead of apps/api/api/.
This conftest documents that invariant and provides a safe fallback.
"""

import os
import sys

import pytest
from asyncpg import Connection

# Guarantee the backend package root is on sys.path
_backend_root = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)


@pytest.fixture(scope="function")
async def transactional_db():
    """
    Fixture that wraps each integration test in a database transaction
    and rolls it back afterward to ensure test isolation.
    """
    from core.persistence.postgres_client import get_postgres_client

    pg_client = await get_postgres_client()
    conn: Connection = await pg_client._pool.acquire()

    # Start transaction
    await conn.execute("BEGIN")

    try:
        yield conn
    finally:
        # Always rollback to clean state
        await conn.execute("ROLLBACK")
        await pg_client._pool.release(conn)


@pytest.fixture(autouse=True)
def verify_redis_cleanup(mock_redis):
    """Auto-fixture to verify Redis cleanup between tests."""
    yield
    # Verify flushdb was called if any set/get operations occurred
    if mock_redis.set.called or mock_redis.get.called:
        mock_redis.flushdb.assert_called()
