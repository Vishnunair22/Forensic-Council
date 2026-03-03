"""
Redis Client Tests
==================

Tests for the Redis client wrapper.
"""

import pytest
import pytest_asyncio

from core.exceptions import RedisConnectionError
from infra.redis_client import RedisClient


class TestRedisClient:
    """Tests for RedisClient class."""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_ping(self, redis_client: RedisClient):
        """Test Redis ping command."""
        result = await redis_client.ping()
        assert result is True
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_set_and_get(self, redis_client: RedisClient):
        """Test setting and getting a value."""
        key = "test_key"
        value = "test_value"
        
        # Set value
        result = await redis_client.set(key, value)
        assert result is True
        
        # Get value
        retrieved = await redis_client.get(key)
        assert retrieved == value
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_set_and_get_json(self, redis_client: RedisClient):
        """Test setting and getting JSON values."""
        key = "test_json_key"
        value = {"name": "test", "count": 42, "nested": {"key": "value"}}
        
        # Set JSON value
        result = await redis_client.set(key, value)
        assert result is True
        
        # Get JSON value
        retrieved = await redis_client.get(key)
        assert retrieved == value
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_delete(self, redis_client: RedisClient):
        """Test deleting a key."""
        key = "test_delete_key"
        
        # Set value
        await redis_client.set(key, "value")
        
        # Delete
        count = await redis_client.delete(key)
        assert count == 1
        
        # Verify deleted
        result = await redis_client.get(key)
        assert result is None
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_exists(self, redis_client: RedisClient):
        """Test checking key existence."""
        key = "test_exists_key"
        
        # Should not exist initially
        result = await redis_client.exists(key)
        assert result == 0
        
        # Set value
        await redis_client.set(key, "value")
        
        # Should exist now
        result = await redis_client.exists(key)
        assert result == 1
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_expire_and_ttl(self, redis_client: RedisClient):
        """Test setting expiration and getting TTL."""
        key = "test_expire_key"
        
        # Set value
        await redis_client.set(key, "value")
        
        # Set expiration
        result = await redis_client.expire(key, 60)
        assert result is True
        
        # Get TTL
        ttl = await redis_client.ttl(key)
        assert 0 < ttl <= 60
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_keys_pattern(self, redis_client: RedisClient):
        """Test finding keys by pattern."""
        # Set multiple keys
        await redis_client.set("test_pattern_1", "value1")
        await redis_client.set("test_pattern_2", "value2")
        await redis_client.set("other_key", "value3")
        
        # Find keys matching pattern
        keys = await redis_client.keys("test_pattern_*")
        
        assert len(keys) == 2
        assert "test_pattern_1" in keys
        assert "test_pattern_2" in keys
        assert "other_key" not in keys
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_hash_operations(self, redis_client: RedisClient):
        """Test hash operations (hset, hget, hgetall, hdel)."""
        hash_name = "test_hash"
        
        # Set hash fields
        await redis_client.hset(hash_name, "field1", "value1")
        await redis_client.hset(hash_name, "field2", {"nested": "data"})
        
        # Get single field
        result = await redis_client.hget(hash_name, "field1")
        assert result == "value1"
        
        # Get all fields
        all_fields = await redis_client.hgetall(hash_name)
        assert all_fields["field1"] == "value1"
        assert all_fields["field2"] == {"nested": "data"}
        
        # Delete field
        count = await redis_client.hdel(hash_name, "field1")
        assert count == 1
        
        # Verify deleted
        result = await redis_client.hget(hash_name, "field1")
        assert result is None
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_context_manager(self):
        """Test using RedisClient as async context manager."""
        async with RedisClient() as client:
            result = await client.ping()
            assert result is True
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_nonexistent_key(self, redis_client: RedisClient):
        """Test getting a key that doesn't exist."""
        result = await redis_client.get("nonexistent_key_xyz")
        assert result is None
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_flushdb(self, redis_client: RedisClient):
        """Test flushing the database."""
        # Set some keys
        await redis_client.set("key1", "value1")
        await redis_client.set("key2", "value2")
        
        # Flush
        result = await redis_client.flushdb()
        assert result is True
        
        # Verify keys are gone
        assert await redis_client.get("key1") is None
        assert await redis_client.get("key2") is None
