"""Tests for Redis client infrastructure."""

from unittest.mock import AsyncMock, patch

import pytest

from core.persistence.redis_client import get_redis_client


@pytest.mark.asyncio
class TestRedisClient:
    async def test_connection_failure_handling(self):
        """Verify graceful degradation when Redis is unavailable."""
        with patch("redis.asyncio.Redis.from_url", side_effect=ConnectionError("Redis down")):
            client = await get_redis_client()
            # Should return fallback in-memory client
            assert client is not None
            assert hasattr(client, "_fallback_store")

    async def test_rate_limit_counter(self):
        """Test rate limiting logic with Redis."""
        from core.rate_limiting import RateLimiter

        limiter = RateLimiter(window_seconds=60, max_requests=10)
        # Mock Redis to avoid external dependency
        with patch("core.persistence.redis_client.get_redis_client") as mock_get:
            mock_redis = AsyncMock()
            mock_redis.incr = AsyncMock(side_effect=list(range(1, 12)))
            mock_redis.expire = AsyncMock(return_value=True)
            mock_get.return_value = mock_redis

            # First 10 requests should pass
            for i in range(10):
                assert await limiter.is_allowed("test_user") is True

            # 11th should be blocked
            assert await limiter.is_allowed("test_user") is False
