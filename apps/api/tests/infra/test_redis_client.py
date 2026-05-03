"""Tests for Redis client infrastructure."""

from unittest.mock import patch

import pytest

from core.persistence.redis_client import get_redis_client


@pytest.mark.asyncio
class TestRedisClient:
    async def test_connection_failure_handling(self):
        """Verify graceful degradation when Redis is unavailable."""
        with patch("redis.asyncio.Redis.from_url", side_effect=ConnectionError("Redis down")):
            client = await get_redis_client()
            assert client is not None
            assert hasattr(client, "_fallback_store")