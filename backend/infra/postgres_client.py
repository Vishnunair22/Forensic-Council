"""
PostgreSQL Client Module
========================

Async PostgreSQL client wrapper using asyncpg.
Supports async context managers and logs connection events.
"""

import json
from typing import Any, Optional, AsyncGenerator
import asyncpg
from asyncpg import Pool, Connection

from core.config import get_settings
from core.logging import get_logger
from core.exceptions import DatabaseConnectionError

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
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
        min_pool_size: int = 5,
        max_pool_size: int = 20,
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
        self._min_pool_size = min_pool_size
        self._max_pool_size = max_pool_size
        
        self._pool: Optional[Pool] = None
    
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
            'jsonb',
            encoder=json.dumps,
            decoder=json.loads,
            schema='pg_catalog'
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
            logger.error("Failed to connect to PostgreSQL", error=str(e))
            raise DatabaseConnectionError(
                f"Failed to connect to PostgreSQL at {self._host}:{self._port}/{self._database}",
                details={"host": self._host, "port": self._port, "database": self._database, "error": str(e)},
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
            raise DatabaseConnectionError("PostgreSQL pool not connected. Call connect() first.")
        return self._pool
    
    async def acquire(self) -> AsyncGenerator[Connection, None]:
        """Acquire a connection from the pool."""
        async with self.pool.acquire() as conn:
            yield conn
    
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
            result = await conn.execute(query, *args)
            logger.debug("Executed query", query=query[:100], status=result)
            return result
    
    async def execute_many(
        self,
        query: str,
        args_list: list[tuple[Any, ...]],
    ) -> None:
        """
        Execute a query multiple times with different parameters.
        
        Args:
            query: SQL query with $1, $2, ... placeholders
            args_list: List of parameter tuples
        """
        async with self.pool.acquire() as conn:
            await conn.executemany(query, args_list)
            logger.debug("Executed batch query", query=query[:100], count=len(args_list))
    
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
            results = await conn.fetch(query, *args)
            logger.debug("Fetched rows", query=query[:100], count=len(results))
            return results
    
    async def fetch_one(
        self,
        query: str,
        *args: Any,
    ) -> Optional[asyncpg.Record]:
        """
        Execute a query and return a single result.
        
        Args:
            query: SQL query with $1, $2, ... placeholders
            *args: Query parameters
        
        Returns:
            Single record or None
        """
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow(query, *args)
            logger.debug("Fetched single row", query=query[:100], found=result is not None)
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
            result = await conn.fetchval(query, *args)
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
            raise DatabaseConnectionError("PostgreSQL health check failed", details={"error": str(e)})


class TransactionContext:
    """Context manager for database transactions."""
    
    def __init__(self, pool: Pool):
        self._pool = pool
        self._conn: Optional[Connection] = None
        self._tx = None
    
    async def __aenter__(self) -> "TransactionContext":
        """Start transaction."""
        self._conn = await self._pool.acquire()
        self._tx = self._conn.transaction()
        await self._tx.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Commit or rollback transaction."""
        if exc_type is not None:
            await self._tx.rollback()
        else:
            await self._tx.commit()
        await self._pool.release(self._conn)
    
    async def execute(self, query: str, *args: Any) -> str:
        """Execute a query within the transaction."""
        # Convert dict args to JSON strings for JSONB columns
        processed_args = [
            json.dumps(arg) if isinstance(arg, dict) else arg
            for arg in args
        ]
        return await self._conn.execute(query, *processed_args)
    
    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        """Fetch rows within the transaction."""
        return await self._conn.fetch(query, *args)
    
    async def fetch_one(self, query: str, *args: Any) -> Optional[asyncpg.Record]:
        """Fetch a single row within the transaction."""
        return await self._conn.fetchrow(query, *args)


# Singleton instance
_postgres_client: Optional[PostgresClient] = None


async def get_postgres_client() -> PostgresClient:
    """
    Get or create the PostgreSQL client singleton.
    
    Returns:
        PostgresClient instance
    """
    global _postgres_client
    if _postgres_client is None:
        _postgres_client = PostgresClient()
        
    if getattr(_postgres_client, "_pool", None) is None:
        try:
            await _postgres_client.connect()
        except Exception as e:
            _postgres_client = None
            raise e
            
    return _postgres_client


async def close_postgres_client() -> None:
    """Close the PostgreSQL client singleton."""
    global _postgres_client
    if _postgres_client is not None:
        await _postgres_client.disconnect()
        _postgres_client = None
