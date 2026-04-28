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
async def transactional_db(request):
    """
    Fixture that wraps each integration test in a database transaction
    and rolls it back afterward to ensure test isolation.

    Only works with a running Postgres. Mark your test with @pytest.mark.requires_docker.
    """
    import asyncpg

    from core.persistence.postgres_client import get_postgres_client

    try:
        pg_client = await get_postgres_client()
        conn: Connection = await pg_client._pool.acquire()
    except (asyncpg.PostgresConnectionError, OSError, Exception) as e:
        pytest.skip(f"Postgres not available — run with Docker stack: {e}")

    # Start transaction
    await conn.execute("BEGIN")

    try:
        yield conn
    finally:
        # Always rollback to clean state
        await conn.execute("ROLLBACK")
        await pg_client._pool.release(conn)


@pytest.fixture(autouse=True)
def reset_mock_redis_between_tests(mock_redis):
    """Ensure Redis mock call history is clean between tests."""
    yield
    mock_redis.reset_mock()
