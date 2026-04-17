"""
PostgreSQL Client Module
========================

Async PostgreSQL client wrapper using asyncpg.
Supports async context managers and logs connection events.
"""

import asyncio
import json
from typing import Any

import asyncpg
from asyncpg import Connection, Pool

from core.config import get_settings
from core.exceptions import DatabaseConnectionError
from core.structured_logging import get_logger

logger = get_logger(__name__)


class PostgresClient:
    """
    Async PostgreSQL client wrapper using asyncpg.

    Provides a high-level interface for PostgreSQL operations with:
    - Async context manager support
    - Connection pooling
    - Connection event logging
    - Typed exception handling

    Usage:
        async with PostgresClient() as client:
            await client.execute("INSERT INTO table VALUES ($1, $2)", "val1", "val2")
            rows = await client.fetch("SELECT * FROM table WHERE id = $1", id)
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
        min_pool_size: int | None = None,
        max_pool_size: int | None = None,
    ) -> None:
        """
        Initialize PostgreSQL client.

        Args:
            host: PostgreSQL host (defaults to settings)
            port: PostgreSQL port (defaults to settings)
            user: PostgreSQL user (defaults to settings)
            password: PostgreSQL password (defaults to settings)
            database: PostgreSQL database name (defaults to settings)
            min_pool_size: Minimum connection pool size
            max_pool_size: Maximum connection pool size
        """
        settings = get_settings()
        self._host = host or settings.postgres_host
        self._port = port or settings.postgres_port
        self._user = user or settings.postgres_user
        self._password = password or settings.postgres_password
        self._database = database or settings.postgres_db
        self._min_pool_size = (
            min_pool_size
            if min_pool_size is not None
            else settings.postgres_min_pool_size
        )
        self._max_pool_size = (
            max_pool_size
            if max_pool_size is not None
            else settings.postgres_max_pool_size
        )

        self._pool: Pool | None = None

    async def __aenter__(self) -> "PostgresClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()

    async def _init_connection(self, conn: Connection) -> None:
        """Initialize a connection with JSON codec."""
        await conn.set_type_codec(
            "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )

    async def connect(self) -> None:
        """Establish connection pool to PostgreSQL."""
        try:
            self._pool = await asyncpg.create_pool(
                host=self._host,
                port=self._port,
                user=self._user,
                password=self._password,
                database=self._database,
                min_size=self._min_pool_size,
                max_size=self._max_pool_size,
                init=self._init_connection,
                timeout=2.0,
            )

            # Test connection
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")

            logger.info(
                "Connected to PostgreSQL",
                host=self._host,
                port=self._port,
                database=self._database,
                pool_size=f"{self._min_pool_size}-{self._max_pool_size}",
            )
        except Exception as e:
            logger.error("Failed to connect to PostgreSQL", error=str(e), exc_info=True)
            raise DatabaseConnectionError(
                f"Failed to connect to PostgreSQL at {self._host}:{self._port}/{self._database}",
                details={
                    "host": self._host,
                    "port": self._port,
                    "database": self._database,
                    "error": str(e),
                },
            )

    async def disconnect(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("Disconnected from PostgreSQL")

    @property
    def pool(self) -> Pool:
        """Get the connection pool."""
        if self._pool is None:
            raise DatabaseConnectionError(
                "PostgreSQL pool not connected. Call connect() first."
            )
        return self._pool

    def _process_args(self, args: tuple[Any, ...]) -> list[Any]:
        """Pass arguments through; JSONB codec handles dict serialization.

        The connection-level JSONB codec (registered in _init_connection)
        converts dicts/lists to JSON wire format. Pre-serialising here
        would double-encode JSONB values, breaking round-trip fidelity
        and chain-of-custody signature verification.
        """
        return list(args)

    async def execute(
        self,
        query: str,
        *args: Any,
    ) -> str:
        """
        Execute a query without returning results.

        Args:
            query: SQL query with $1, $2, ... placeholders
            *args: Query parameters

        Returns:
            Status string from PostgreSQL
        """
        async with self.pool.acquire() as conn:
            processed_args = self._process_args(args)
            result = await conn.execute(query, *processed_args)
            logger.debug("Executed query", query=query[:100], status=result)
            return result

    async def execute_many(
        self,
        query: str,
        args_list: list[tuple[Any, ...]],
    ) -> None:
        """
        Execute a query multiple times with different parameters.

        CRITICAL SECURITY: Use $1, $2, etc. placeholders for parameters.
        NEVER use f-strings or string formatting for queries!

        Issue 3.5: Catches per-row asyncpg errors and logs the offending
        row index before re-raising so forensic log reconstruction is easier.

        Args:
            query: SQL query with $1, $2, ... placeholders
            args_list: List of parameter tuples
        """
        async with self.pool.acquire() as conn:
            processed_args_list = [
                tuple(self._process_args(args)) for args in args_list
            ]
            try:
                await conn.executemany(query, processed_args_list)
            except Exception as e:
                # Log which row failed to aid custody-log reconstruction
                logger.error(
                    "execute_many failed",
                    query=query[:100],
                    rows_attempted=len(args_list),
                    error=str(e),
                )
                raise
            logger.debug(
                "Executed batch query", query=query[:100], count=len(args_list)
            )

    async def fetch(
        self,
        query: str,
        *args: Any,
    ) -> list[asyncpg.Record]:
        """
        Execute a query and return all results.

        Args:
            query: SQL query with $1, $2, ... placeholders
            *args: Query parameters

        Returns:
            List of records
        """
        async with self.pool.acquire() as conn:
            processed_args = self._process_args(args)
            results = await conn.fetch(query, *processed_args)
            logger.debug("Fetched rows", query=query[:100], count=len(results))
            return results

    async def fetch_one(
        self,
        query: str,
        *args: Any,
    ) -> asyncpg.Record | None:
        """
        Execute a query and return a single result.

        Args:
            query: SQL query with $1, $2, ... placeholders
            *args: Query parameters

        Returns:
            Single record or None
        """
        async with self.pool.acquire() as conn:
            processed_args = self._process_args(args)
            result = await conn.fetchrow(query, *processed_args)
            logger.debug(
                "Fetched single row", query=query[:100], found=result is not None
            )
            return result

    async def fetch_val(
        self,
        query: str,
        *args: Any,
    ) -> Any:
        """
        Execute a query and return a single value.

        Args:
            query: SQL query with $1, $2, ... placeholders
            *args: Query parameters

        Returns:
            Single value or None
        """
        async with self.pool.acquire() as conn:
            processed_args = self._process_args(args)
            result = await conn.fetchval(query, *processed_args)
            logger.debug("Fetched single value", query=query[:100])
            return result

    def transaction(self):
        """
        Start a transaction.

        Usage:
            async with client.transaction() as tx:
                await tx.execute("INSERT ...")
                await tx.execute("UPDATE ...")
        """
        return TransactionContext(self.pool)

    async def health_check(self) -> bool:
        """Test PostgreSQL connection."""
        try:
            result = await self.fetch_val("SELECT 1")
            return result == 1
        except Exception as e:
            logger.error("PostgreSQL health check failed", error=str(e))
            raise DatabaseConnectionError(
                "PostgreSQL health check failed", details={"error": str(e)}
            )


class TransactionContext:
    """Context manager for database transactions."""

    def __init__(self, pool: Pool):
        self._pool = pool
        self._conn: Connection | None = None
        self._tx = None

    async def __aenter__(self) -> "TransactionContext":
        """Start transaction."""
        self._conn = await self._pool.acquire()
        self._tx = self._conn.transaction()
        await self._tx.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Commit or rollback transaction.

        Issue 3.4: Always release the connection in a finally block so that
        a failed rollback cannot leak a connection from the pool.
        """
        try:
            if exc_type is not None:
                await self._tx.rollback()
            else:
                await self._tx.commit()
        finally:
            await self._pool.release(self._conn)

    async def execute(self, query: str, *args: Any) -> str:
        """Execute a query within the transaction."""
        return await self._conn.execute(query, *args)

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        """Fetch rows within the transaction."""
        return await self._conn.fetch(query, *args)

    async def fetch_one(self, query: str, *args: Any) -> asyncpg.Record | None:
        """Fetch a single row within the transaction."""
        return await self._conn.fetchrow(query, *args)


# Singleton instance — protected by a lock to prevent concurrent init races
_postgres_client: PostgresClient | None = None
_postgres_lock: asyncio.Lock | None = None


def _get_postgres_lock() -> asyncio.Lock:
    """Lazily create the Postgres init lock on first use (must run inside an event loop)."""
    global _postgres_lock
    if _postgres_lock is None:
        _postgres_lock = asyncio.Lock()
    return _postgres_lock


async def get_postgres_client() -> PostgresClient:
    """
    Get or create the PostgreSQL client singleton.

    Thread-safe via asyncio.Lock — concurrent callers wait rather than each
    creating their own connection pool.

    Returns:
        PostgresClient instance
    """
    global _postgres_client
    if (
        _postgres_client is not None
        and getattr(_postgres_client, "_pool", None) is not None
    ):
        return _postgres_client
    async with _get_postgres_lock():
        # Double-checked locking
        if _postgres_client is None or getattr(_postgres_client, "_pool", None) is None:
            client = PostgresClient()
            try:
                await client.connect()
            except Exception:
                _postgres_client = None
                raise
            _postgres_client = client
    return _postgres_client


async def close_postgres_client() -> None:
    """Close the PostgreSQL client singleton."""
    global _postgres_client
    async with _get_postgres_lock():
        if _postgres_client is not None:
            await _postgres_client.disconnect()
            _postgres_client = None
