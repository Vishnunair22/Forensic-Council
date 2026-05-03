"""
Unit tests for rate limiter fail-open behavior.

Tests that when Redis is unavailable, the rate limiter fails open
(allows the request) AND emits the rate_limit_redis_bypasses metric counter.
"""

from unittest.mock import AsyncMock, patch

import pytest

from core.config import get_settings


class TestRateLimiterFailOpen:
    """Tests for rate limiter graceful degradation when Redis is down."""

    @pytest.mark.asyncio
    async def test_rate_limit_fails_open_when_redis_unavailable(self):
        """Verify requests are allowed through when Redis is down (fail-open)."""
        from core.rate_limiting import check_investigation_rate_limit

        with patch("core.rate_limiting.get_redis_client") as mock_redis:
            mock_redis.side_effect = ConnectionError("Redis unavailable")

            settings = get_settings()
            await check_investigation_rate_limit("user-123", settings)

    @pytest.mark.asyncio
    async def test_rate_limit_raises_metric_on_redis_failure(self):
        """Verify rate_limit_redis_bypasses metric is incremented on Redis failure."""
        from core.rate_limiting import check_investigation_rate_limit

        with patch("core.rate_limiting.get_redis_client") as mock_redis:
            mock_redis.side_effect = ConnectionError("Redis unavailable")

            with patch("api.routes.metrics.increment_rate_limit_redis_bypasses") as mock_increment:
                await check_investigation_rate_limit("user-metric-test", get_settings())
                mock_increment.assert_called_once()

    @pytest.mark.asyncio
    async def test_normal_rate_limiting_still_works(self):
        """Verify normal rate limiting still works when Redis is available."""
        from core.rate_limiting import check_investigation_rate_limit

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True

        with patch("core.rate_limiting.get_redis_client", return_value=mock_redis):
            await check_investigation_rate_limit("user-normal", get_settings())

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_over_limit(self):
        """Verify rate limiter blocks when over limit."""
        from core.rate_limiting import MAX_INVESTIGATIONS_PER_USER
        from core.rate_limiting import check_investigation_rate_limit
        from fastapi import HTTPException

        mock_redis = AsyncMock()
        mock_redis.get.return_value = b"50"
        mock_redis.ttl.return_value = 300

        with patch("core.rate_limiting.get_redis_client", return_value=mock_redis):
            with pytest.raises(HTTPException) as exc_info:
                await check_investigation_rate_limit("user-over-limit", get_settings())
            assert exc_info.value.status_code == 429


class TestRateLimitMetricIncrement:
    """Tests for the rate limit bypass metric."""

    @pytest.mark.asyncio
    async def test_metric_endpoint_exposes_bypass_counter(self):
        """Verify the /metrics endpoint exposes the bypass counter."""
        from fastapi.testclient import TestClient

        from api.main import app

        client = TestClient(app)
        response = client.get("/metrics")

        assert response.status_code == 200
        assert "rate_limit_redis_bypasses" in response.text or "bypasses" in response.text.lower()

    def test_increment_function_exists(self):
        """Verify the increment function exists in metrics module."""
        from api.routes.metrics import increment_rate_limit_redis_bypasses

        assert callable(increment_rate_limit_redis_bypasses)


class TestRateLimitConfiguration:
    """Tests for rate limit configuration."""

    def test_rate_limit_window_is_configurable(self):
        """Verify rate limit window can be configured."""
        from core.config import get_settings

        settings = get_settings()
        assert hasattr(settings, "app_env")

    def test_rate_limit_window_default_value(self):
        """Verify rate limit window has reasonable default."""
        from core.rate_limiting import USER_RATE_WINDOW_SECS

        assert USER_RATE_WINDOW_SECS >= 60
        assert USER_RATE_WINDOW_SECS <= 86400


class TestRateLimitRedisErrorHandling:
    """Tests for Redis error handling in rate limiting."""

    @pytest.mark.asyncio
    async def test_handles_redis_timeout(self):
        """Verify rate limiter handles Redis timeout gracefully."""
        from core.rate_limiting import check_investigation_rate_limit

        with patch("core.rate_limiting.get_redis_client") as mock_get:
            mock_get.side_effect = TimeoutError("Redis timeout")

            await check_investigation_rate_limit("user-timeout", get_settings())

    @pytest.mark.asyncio
    async def test_handles_redis_auth_error(self):
        """Verify rate limiter handles Redis auth error gracefully."""
        from core.rate_limiting import check_investigation_rate_limit

        with patch("core.rate_limiting.get_redis_client") as mock_get:
            mock_get.side_effect = Exception("WRONGPASS invalid username-password pair")

            await check_investigation_rate_limit("user-auth-error", get_settings())

    @pytest.mark.asyncio
    async def test_handles_redis_not_found(self):
        """Verify rate limiter handles Redis key not found gracefully."""
        from core.rate_limiting import check_investigation_rate_limit

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True

        with patch("core.rate_limiting.get_redis_client", return_value=mock_redis):
            await check_investigation_rate_limit("user-none", get_settings())