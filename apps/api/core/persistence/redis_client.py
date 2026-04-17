"""
Redis Client Module
===================

Async Redis client wrapper for working memory and caching.
Supports async context managers and logs connection events.
"""

import asyncio
import json
from typing import Any

from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool

from core.config import get_settings
from core.exceptions import RedisConnectionError
from core.structured_logging import get_logger

logger = get_logger(__name__)


class RedisClient:
    """
    Async Redis client wrapper.

    Provides a high-level interface for Redis operations with:
    - Async context manager support
    - Connection event logging
    - Typed exception handling

    Usage:
        async with RedisClient() as client:
            await client.set("key", "value")
            value = await client.get("key")
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        db: int | None = None,
        password: str | None = None,
    ) -> None:
        """
        Initialize Redis client.

        Args:
            host: Redis host (defaults to settings)
            port: Redis port (defaults to settings)
            db: Redis database number (defaults to settings)
            password: Redis password (defaults to settings)
        """
        settings = get_settings()
        self._host = host or settings.redis_host
        self._port = port or settings.redis_port
        self._db = db or settings.redis_db
        self._password = password if password is not None else settings.redis_password

        self._pool: ConnectionPool | None = None
        self._client: Redis | None = None

    async def __aenter__(self) -> "RedisClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()

    async def connect(self) -> None:
        """Establish connection to Redis."""
        try:
            connection_kwargs = {
                "host": self._host,
                "port": self._port,
                "db": self._db,
                "decode_responses": True,
                "socket_timeout": 30.0,
                "socket_connect_timeout": 2.0,
            }

            # Explicitly check for None not truthy to allow empty string passwords
            if self._password is not None:
                connection_kwargs["password"] = self._password

            self._pool = ConnectionPool(**connection_kwargs)
            self._client = Redis(connection_pool=self._pool)

            # Test connection
            await self._client.ping()

            logger.info(
                "Connected to Redis",
                host=self._host,
                port=self._port,
                db=self._db,
            )
        except Exception as e:
            logger.error("Failed to connect to Redis", error=str(e))
            raise RedisConnectionError(
                f"Failed to connect to Redis at {self._host}:{self._port}",
                details={"host": self._host, "port": self._port, "error": str(e)},
            )

    async def disconnect(self) -> None:
        """Close connection to Redis."""
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._pool:
            await self._pool.aclose()
            self._pool = None
            logger.info("Disconnected from Redis")

    @property
    def client(self) -> Redis:
        """Get the underlying Redis client."""
        if self._client is None:
            raise RedisConnectionError(
                "Redis client not connected. Call connect() first."
            )
        return self._client

    async def ping(self) -> bool:
        """Test Redis connection."""
        try:
            result = await self.client.ping()
            return result is True
        except Exception as e:
            logger.error("Redis ping failed", error=str(e))
            raise RedisConnectionError("Redis ping failed", details={"error": str(e)})

    async def set(
        self,
        key: str,
        value: Any,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """
        Set a key-value pair in Redis.

        Args:
            key: Key name
            value: Value to store (will be JSON-serialized if not a string)
            ex: Expire time in seconds
            px: Expire time in milliseconds
            nx: Only set if key does not exist
            xx: Only set if key exists

        Returns:
            True if successful
        """

        if not isinstance(value, str):
            value = json.dumps(value)

        result = await self.client.set(key, value, ex=ex, px=px, nx=nx, xx=xx)
        # redis-py returns True on success for basic SET, or None if nx=True and key exists
        return result is True or result == "OK"

    async def get(self, key: str) -> str | None:
        """
        Get a raw string value from Redis.

        Returns the value as-is (string). Use `get_json` if you need
        automatic JSON decoding.

        Issue 3.1: Removed auto-JSON parse — callers must decode explicitly
        to avoid silent type coercions (e.g. a JSON string being returned as
        a Python dict when the caller expected a str).

        Args:
            key: Key name

        Returns:
            Raw string value if exists, None otherwise
        """
        raw = await self.client.get(key)
        if raw is None:
            return None
        # redis-py returns bytes; decode to str to match declared return type.
        return raw.decode("utf-8") if isinstance(raw, bytes) else raw

    async def get_json(self, key: str) -> Any | None:
        """
        Get and JSON-decode a value from Redis.

        Use this when you know the stored value is JSON-serialised.
        Falls back to returning the raw string if JSON parsing fails.
        """
        value = await self.client.get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    async def delete(self, *keys: str) -> int:
        """
        Delete one or more keys.

        Args:
            keys: Key names to delete

        Returns:
            Number of keys deleted
        """
        return await self.client.delete(*keys)

    async def exists(self, *keys: str) -> int:
        """
        Check if keys exist.

        Args:
            keys: Key names to check

        Returns:
            Number of keys that exist
        """
        return await self.client.exists(*keys)

    async def expire(self, key: str, seconds: int) -> bool:
        """
        Set expiration on a key.

        Args:
            key: Key name
            seconds: Expiration time in seconds

        Returns:
            True if successful
        """
        return await self.client.expire(key, seconds)

    async def incr(self, key: str, amount: int = 1) -> int:
        """
        Increment a numeric value.

        Args:
            key: Key name
            amount: Amount to increment by

        Returns:
            The value after incrementing
        """
        return await self.client.incr(key, amount)

    async def ttl(self, key: str) -> int:
        """
        Get time-to-live for a key.

        Args:
            key: Key name

        Returns:
            TTL in seconds, -1 if no expiration, -2 if key doesn't exist
        """
        return await self.client.ttl(key)

    async def keys(self, pattern: str = "*") -> list[str]:
        """
        Find all keys matching pattern using SCAN (non-blocking).

        Uses `scan_iter` internally — this is safe for production because it
        does NOT block Redis the way the `KEYS` command does.

        Args:
            pattern: Key pattern (supports wildcards)

        Returns:
            List of matching keys
        """
        keys = []
        async for key in self.client.scan_iter(match=pattern, count=100):
            keys.append(key)
        return keys

    def pipeline(self):
        """Return a Redis pipeline for batched commands."""
        return self.client.pipeline()

    async def flushdb(self, allow_in_tests: bool = False) -> bool:
        """Clear all keys in current database.

        Issue 3.3: Gated behind allow_in_tests=True to prevent accidental
        production data loss from a stray call in route handlers.
        Only test code or maintenance scripts should pass allow_in_tests=True.
        """
        if not allow_in_tests:
            raise RuntimeError(
                "flushdb() is disabled in production code. "
                "Pass allow_in_tests=True only from test helpers or maintenance scripts."
            )
        await self.client.flushdb()
        return True

    # Hash operations
    async def hset(self, name: str, key: str, value: Any) -> int:
        """Set a field in a hash."""
        if not isinstance(value, str):
            value = json.dumps(value)
        return await self.client.hset(name, key, value)

    async def hget(self, name: str, key: str) -> Any | None:
        """Get a field from a hash."""
        value = await self.client.hget(name, key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    async def hgetall(self, name: str) -> dict[str, Any]:
        """Get all fields from a hash."""
        result = await self.client.hgetall(name)
        parsed = {}
        for k, v in result.items():
            try:
                parsed[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                parsed[k] = v
        return parsed

    async def hdel(self, name: str, *keys: str) -> int:
        """Delete fields from a hash."""
        return await self.client.hdel(name, *keys)


# Singleton instance — protected by a lock to prevent concurrent init races
_redis_client: RedisClient | None = None
_redis_lock: asyncio.Lock | None = None


def _get_redis_lock() -> asyncio.Lock:
    """Lazily create the Redis init lock on first use (must run inside an event loop)."""
    global _redis_lock
    if _redis_lock is None:
        _redis_lock = asyncio.Lock()
    return _redis_lock


async def get_redis_client() -> RedisClient:
    """
    Get or create the Redis client singleton.

    Thread-safe via asyncio.Lock — concurrent callers will wait rather than
    each creating their own connection pool.

    Returns:
        RedisClient instance
    """
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    async with _get_redis_lock():
        # Double-checked locking: another coroutine may have connected while
        # we were waiting for the lock.
        if _redis_client is None:
            client = RedisClient()
            await client.connect()
            _redis_client = client
    return _redis_client


async def close_redis_client() -> None:
    """Close the Redis client singleton."""
    global _redis_client
    async with _get_redis_lock():
        if _redis_client is not None:
            await _redis_client.disconnect()
            _redis_client = None
