"""Tests for Redis client infrastructure."""

from unittest.mock import patch

import pytest

from core.persistence.redis_client import InMemoryRedisClient, get_redis_client


@pytest.mark.asyncio
class TestRedisClient:
    async def test_connection_failure_handling(self):
        """Verify graceful degradation when Redis is unavailable."""
        with patch("redis.asyncio.Redis.from_url", side_effect=ConnectionError("Redis down")):
            client = await get_redis_client()
            assert client is not None
            assert hasattr(client, "_fallback_store")

    async def test_in_memory_fallback_exposes_client_list_and_pipeline_api(self):
        """Fallback Redis must support runtime callers that use redis.client.* directly."""
        client = InMemoryRedisClient()

        assert client.client is client

        await client.client.rpush("wal", "one")
        await client.client.rpush("wal", "two")
        assert await client.client.llen("wal") == 2
        assert await client.client.lpop("wal") == "one"
        await client.client.lpush("wal", "zero")
        assert await client.client.lrange("wal", 0, -1) == ["zero", "two"]
        await client.client.ltrim("wal", 0, 0)
        assert await client.client.lrange("wal", 0, -1) == ["zero"]

        async with client.client.pipeline(transaction=True) as pipe:
            pipe.set("decision", {"deep_analysis": True}, ex=60)
            pipe.rpush("queue", "session-1")
            pipe.publish("channel", "payload")
            results = await pipe.execute()

        assert results == [True, 1, 0]
        assert await client.get_json("decision") == {"deep_analysis": True}
        assert await client.client.lrange("queue", 0, -1) == ["session-1"]
