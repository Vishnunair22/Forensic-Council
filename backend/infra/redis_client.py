"""
Redis Client Module
===================

Async Redis client wrapper for working memory and caching.
Supports async context managers and logs connection events.
"""

from typing import Any, Optional
import redis.asyncio as redis
from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool

from core.config import get_settings
from core.logging import get_logger
from core.exceptions import RedisConnectionError

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
        host: Optional[str] = None,
        port: Optional[int] = None,
        db: Optional[int] = None,
        password: Optional[str] = None,
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
        self._password = password or settings.redis_password
        
        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[Redis] = None
    
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
            self._pool = ConnectionPool(
                host=self._host,
                port=self._port,
                db=self._db,
                password=self._password,
                decode_responses=True,
            )
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
            raise RedisConnectionError("Redis client not connected. Call connect() first.")
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
        ex: Optional[int] = None,
        px: Optional[int] = None,
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
        import json
        
        if not isinstance(value, str):
            value = json.dumps(value)
        
        result = await self.client.set(key, value, ex=ex, px=px, nx=nx, xx=xx)
        return result is not None or xx
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get a value from Redis.
        
        Args:
            key: Key name
        
        Returns:
            Value if exists, None otherwise
        """
        import json
        
        value = await self.client.get(key)
        if value is None:
            return None
        
        # Try to parse as JSON, fall back to raw string
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
        Find all keys matching pattern.
        
        Args:
            pattern: Key pattern (supports wildcards)
        
        Returns:
            List of matching keys
        """
        return await self.client.keys(pattern)
    
    async def flushdb(self) -> bool:
        """Clear all keys in current database."""
        await self.client.flushdb()
        return True
    
    # Hash operations
    async def hset(self, name: str, key: str, value: Any) -> int:
        """Set a field in a hash."""
        import json
        if not isinstance(value, str):
            value = json.dumps(value)
        return await self.client.hset(name, key, value)
    
    async def hget(self, name: str, key: str) -> Optional[Any]:
        """Get a field from a hash."""
        import json
        value = await self.client.hget(name, key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    
    async def hgetall(self, name: str) -> dict[str, Any]:
        """Get all fields from a hash."""
        import json
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


# Singleton instance
_redis_client: Optional[RedisClient] = None


async def get_redis_client() -> RedisClient:
    """
    Get or create the Redis client singleton.
    
    Returns:
        RedisClient instance
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
        await _redis_client.connect()
    return _redis_client


async def close_redis_client() -> None:
    """Close the Redis client singleton."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.disconnect()
        _redis_client = None
