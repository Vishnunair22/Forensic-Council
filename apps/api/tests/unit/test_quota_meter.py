"""
Unit tests for the quota meter module.

Tests that QuotaMeter reads/writes the correct Redis hash key,
increments counters correctly, and returns zero gracefully when
Redis is unavailable.
"""

from unittest.mock import AsyncMock, patch

import pytest

from core.quota_meter import _session_key, get_session_quota, record_api_call


class TestRecordApiCall:
    """Tests for recording API calls."""

    @pytest.mark.asyncio
    async def test_increment_tokens_uses_correct_hash_key(self):
        """Verify that increment calls use the correct Redis hash key format."""
        mock_redis = AsyncMock()
        mock_pipeline = AsyncMock()
        mock_redis.pipeline.return_value = mock_pipeline

        with patch("core.quota_meter.get_redis_client", return_value=mock_redis):
            await record_api_call(
                provider="gemini",
                model="gemini-2.5-flash",
                tokens_in=500,
                tokens_out=100,
                session_id="test-session-123",
            )

        # Verify pipeline was used
        mock_redis.pipeline.assert_called_once()

        # Verify the key format
        calls = mock_pipeline.hincrby.call_args_list
        assert any("quota:test-session-123" in str(call) for call in calls)

    @pytest.mark.asyncio
    async def test_increment_counts_per_provider(self):
        """Verify that call counts are tracked per provider."""
        mock_redis = AsyncMock()
        mock_pipeline = AsyncMock()
        mock_redis.pipeline.return_value = mock_pipeline

        with patch("core.quota_meter.get_redis_client", return_value=mock_redis):
            await record_api_call(
                provider="gemini",
                model="gemini-2.5-flash",
                tokens_in=100,
                tokens_out=50,
                session_id="session-abc",
            )

        # Check that provider-specific fields are incremented
        call_args = mock_pipeline.hincrby.call_args_list
        provider_call_found = any("calls:gemini" in str(call) for call in call_args)
        total_call_found = any("calls:total" in str(call) for call in call_args)
        assert provider_call_found, "Provider-specific call count not incremented"
        assert total_call_found, "Total call count not incremented"

    @pytest.mark.asyncio
    async def test_uses_context_variable_when_no_session_id(self):
        """Verify that session_id is read from context variable when not provided."""
        from core.quota_meter import session_id_ctx

        mock_redis = AsyncMock()
        mock_pipeline = AsyncMock()
        mock_redis.pipeline.return_value = mock_pipeline

        # Set context variable
        token = session_id_ctx.set("context-session-456")

        try:
            with patch("core.quota_meter.get_redis_client", return_value=mock_redis):
                await record_api_call(
                    provider="groq",
                    model="llama3-70b",
                    tokens_in=200,
                    tokens_out=80,
                )  # No session_id provided

            # Verify it used the context variable's session
            calls = mock_pipeline.hincrby.call_args_list
            context_session_used = any("quota:context-session-456" in str(call) for call in calls)
            assert context_session_used, "Should use session_id from context variable"
        finally:
            session_id_ctx.reset(token)

    @pytest.mark.asyncio
    async def test_skips_quietly_when_redis_unavailable(self):
        """Verify that quota tracking never blocks when Redis is down."""
        with patch("core.quota_meter.get_redis_client", return_value=None):
            # Should not raise
            await record_api_call(
                provider="gemini",
                model="gemini-2.5-flash",
                tokens_in=100,
                session_id="session-xyz",
            )

    @pytest.mark.asyncio
    async def test_skips_quietly_on_connection_error(self):
        """Verify graceful handling when Redis raises ConnectionError."""
        with patch("core.quota_meter.get_redis_client") as mock_get:
            mock_get.side_effect = ConnectionError("Redis unavailable")

            # Should not raise - silently skips
            await record_api_call(
                provider="gemini",
                model="gemini-2.5-flash",
                tokens_in=100,
                session_id="session-err",
            )


class TestGetSessionQuota:
    """Tests for reading quota data."""

    @pytest.mark.asyncio
    async def test_returns_dict_with_required_fields(self):
        """Verify get_usage returns dict with expected fields."""
        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {
            b"tokens:total": b"1500",
            b"calls:total": b"5",
            b"calls:gemini": b"3",
            b"tokens:gemini:in": b"1000",
            b"tokens:gemini:out": b"500",
            b"last_call_ts": b"1234567890.123",
        }

        with patch("core.quota_meter.get_redis_client", return_value=mock_redis):
            result = await get_session_quota("test-session-789")

        assert isinstance(result, dict)
        assert "tokens:total" in result
        assert "calls:total" in result

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_redis_unavailable(self):
        """Verify graceful degradation when Redis is unavailable."""
        with patch("core.quota_meter.get_redis_client", return_value=None):
            result = await get_session_quota("session-no-redis")

        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_session_not_found(self):
        """Verify empty result when session has no quota data."""
        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {}  # Empty result

        with patch("core.quota_meter.get_redis_client", return_value=mock_redis):
            result = await get_session_quota("session-empty")

        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_empty_dict_for_empty_session_id(self):
        """Verify empty result when session_id is empty."""
        result = await get_session_quota("")
        assert result == {}

    @pytest.mark.asyncio
    async def test_handles_connection_error_gracefully(self):
        """Verify connection errors are handled without raising."""
        with patch("core.quota_meter.get_redis_client") as mock_get:
            mock_get.side_effect = ConnectionError("Connection refused")

            result = await get_session_quota("session-error")

        assert result == {}

    @pytest.mark.asyncio
    async def test_decodes_bytes_to_strings(self):
        """Verify Redis byte keys/values are decoded to strings."""
        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {
            b"tokens:total": b"2000",
            b"last_call_ts": b"1234567890.000",
        }

        with patch("core.quota_meter.get_redis_client", return_value=mock_redis):
            result = await get_session_quota("session-encoding")

        # Keys should be strings, not bytes
        assert all(isinstance(k, str) for k in result.keys())
        assert all(isinstance(v, str) for v in result.values())


class TestSessionKeyFormat:
    """Tests for the session key formatting."""

    def test_session_key_format(self):
        """Verify the key format is quota:{session_id}."""
        key = _session_key("my-session-123")
        assert key == "quota:my-session-123"

    def test_session_key_with_special_chars(self):
        """Verify keys handle special characters in session IDs."""
        key = _session_key("session-with-dashes-123")
        assert key == "quota:session-with-dashes-123"
