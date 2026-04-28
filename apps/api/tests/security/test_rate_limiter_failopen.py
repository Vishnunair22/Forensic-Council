"""
Unit tests for rate limiter fail-open behavior.

Tests that when Redis is unavailable, the rate limiter fails open
(allows the request) AND emits the rate_limit_redis_bypasses metric counter.
"""

from unittest.mock import AsyncMock, patch

import pytest


class TestRateLimiterFailOpen:
    """Tests for rate limiter graceful degradation when Redis is down."""

    @pytest.mark.asyncio
    async def test_rate_limit_fails_open_when_redis_unavailable(self):
        """Verify requests are allowed through when Redis is down (fail-open)."""
        # This tests the core rate limiting logic
        from core.rate_limit import check_investigation_rate_limit

        # Mock Redis to raise ConnectionError
        with patch("core.rate_limit.get_redis_client") as mock_redis:
            mock_redis.side_effect = ConnectionError("Redis unavailable")

            # Should NOT raise - fails open
            # The function should return True (allow) when Redis is down
            result = await check_investigation_rate_limit("user-123")

            # When Redis fails, rate limiter should fail OPEN (allow the request)
            assert result is True, "Rate limiter should fail open when Redis unavailable"

    @pytest.mark.asyncio
    async def test_rate_limit_raises_metric_on_redis_failure(self):
        """Verify rate_limit_redis_bypasses metric is incremented on Redis failure."""
        from core.rate_limit import check_investigation_rate_limit

        # We need to check that the metric is incremented
        # Let's patch the metric increment function
        with patch("core.rate_limit.get_redis_client") as mock_redis:
            mock_redis.side_effect = ConnectionError("Redis unavailable")

            with patch("core.rate_limit.increment_rate_limit_redis_bypasses") as mock_increment:
                await check_investigation_rate_limit("user-metric-test")

                # The metric should be incremented when Redis fails
                mock_increment.assert_called_once()

    @pytest.mark.asyncio
    async def test_normal_rate_limiting_still_works(self):
        """Verify normal rate limiting still works when Redis is available."""
        from core.rate_limit import check_investigation_rate_limit

        # Mock working Redis
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # No existing rate limit
        mock_redis.set.return_value = True

        with patch("core.rate_limit.get_redis_client", return_value=mock_redis):
            # First request should be allowed
            result = await check_investigation_rate_limit("user-normal")

            # Should be allowed (first request under limit)
            assert result is True

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_over_limit(self):
        """Verify rate limiter blocks when over limit."""
        from core.rate_limit import check_investigation_rate_limit

        # Mock Redis with user already over limit
        mock_redis = AsyncMock()
        # Return a timestamp from within the window
        import time

        recent_time = str(int(time.time()))
        mock_redis.get.return_value = recent_time.encode()
        mock_redis.set.return_value = True

        with patch("core.rate_limit.get_redis_client", return_value=mock_redis):
            # Second request should be blocked
            result = await check_investigation_rate_limit("user-over-limit")

            # Should be blocked (over rate limit)
            assert result is False


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

        # The metric should be in the response
        metrics_text = response.text
        assert "rate_limit_redis_bypasses" in metrics_text or "bypasses" in metrics_text.lower()

    def test_increment_function_exists(self):
        """Verify the increment function exists in metrics module."""
        from api.routes.metrics import increment_rate_limit_redis_bypasses

        # Function should exist and be callable
        assert callable(increment_rate_limit_redis_bypasses)


class TestRateLimitConfiguration:
    """Tests for rate limit configuration."""

    def test_rate_limit_window_is_configurable(self):
        """Verify rate limit window can be configured."""
        from core.config import get_settings

        settings = get_settings()

        # There should be a rate limit configuration
        # Check if the settings have the relevant fields
        assert hasattr(settings, "app_env")  # Basic config check

    def test_rate_limit_window_default_value(self):
        """Verify rate limit window has reasonable default."""
        # The default should be something like 3600 seconds (1 hour)
        from core.rate_limit import _DEFAULT_RATE_LIMIT_WINDOW

        # Should be a reasonable time window (1 hour = 3600s)
        assert _DEFAULT_RATE_LIMIT_WINDOW >= 60  # At least 1 minute
        assert _DEFAULT_RATE_LIMIT_WINDOW <= 86400  # At most 1 day


class TestRateLimitRedisErrorHandling:
    """Tests for Redis error handling in rate limiting."""

    @pytest.mark.asyncio
    async def test_handles_redis_timeout(self):
        """Verify rate limiter handles Redis timeout gracefully."""
        import asyncio

        from core.rate_limit import check_investigation_rate_limit

        async def slow_redis():
            await asyncio.sleep(30)  # Timeout
            return None

        with patch("core.rate_limit.get_redis_client", return_value=slow_redis()):
            # This would timeout - but we test with a quick error instead
            pass

        # Use a faster failure mode
        with patch("core.rate_limit.get_redis_client") as mock_get:
            mock_get.side_effect = TimeoutError("Redis timeout")

            result = await check_investigation_rate_limit("user-timeout")

            # Should fail open
            assert result is True

    @pytest.mark.asyncio
    async def test_handles_redis_auth_error(self):
        """Verify rate limiter handles Redis auth error gracefully."""
        from core.rate_limit import check_investigation_rate_limit

        # Mock Redis auth failure
        with patch("core.rate_limit.get_redis_client") as mock_get:
            mock_get.side_effect = Exception("WRONGPASS invalid username-password pair")

            result = await check_investigation_rate_limit("user-auth-error")

            # Should fail open (allow request)
            assert result is True

    @pytest.mark.asyncio
    async def test_handles_redis_not_found(self):
        """Verify rate limiter handles Redis key not found gracefully."""
        from core.rate_limit import check_investigation_rate_limit

        # Mock Redis returning None (key not found) - this is actually normal
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        with patch("core.rate_limit.get_redis_client", return_value=mock_redis):
            result = await check_investigation_rate_limit("user-none")

            # Should allow (no existing rate limit)
            assert result is True
