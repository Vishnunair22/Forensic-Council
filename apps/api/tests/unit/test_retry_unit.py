"""
Unit tests for core/retry.py.

Covers:
- RetryConfig
- calculate_delay()
- retry_async() / with_retry()
- Database retry helpers
"""

import os

import pytest

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_PASSWORD", "test")
os.environ.setdefault("NEXT_PUBLIC_DEMO_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")

from core.retry import RetryConfig, calculate_delay

# ── RetryConfig ────────────────────────────────────────────────────────────────


class TestRetryConfig:
    def test_defaults(self):
        cfg = RetryConfig()
        assert cfg.max_retries == 3
        assert cfg.base_delay == 1.0
        assert cfg.max_delay == 60.0
        assert cfg.exponential_base == 2.0
        assert cfg.jitter is True

    def test_custom_values(self):
        cfg = RetryConfig(max_retries=5, base_delay=0.5, jitter=False)
        assert cfg.max_retries == 5
        assert cfg.base_delay == 0.5
        assert cfg.jitter is False

    def test_retry_exceptions_default(self):
        cfg = RetryConfig()
        assert cfg.retry_exceptions == (Exception,)

    def test_on_retry_callback(self):
        calls = []

        def on_retry(exc, attempt):
            calls.append(attempt)

        cfg = RetryConfig(on_retry=on_retry)
        assert cfg.on_retry is on_retry


# ── calculate_delay ────────────────────────────────────────────────────────────


class TestCalculateDelay:
    def test_first_attempt_returns_base_delay(self):
        cfg = RetryConfig(base_delay=1.0, jitter=False)
        delay = calculate_delay(1, cfg)
        assert delay == 1.0

    def test_second_attempt_doubles(self):
        cfg = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter=False)
        delay = calculate_delay(2, cfg)
        assert delay == 2.0

    def test_third_attempt_quadruples(self):
        cfg = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter=False)
        delay = calculate_delay(3, cfg)
        assert delay == 4.0

    def test_capped_at_max_delay(self):
        cfg = RetryConfig(base_delay=1.0, max_delay=5.0, exponential_base=2.0, jitter=False)
        delay = calculate_delay(10, cfg)
        assert delay == 5.0

    def test_jitter_adds_variance(self):
        cfg = RetryConfig(base_delay=1.0, jitter=True)
        delays = [calculate_delay(1, cfg) for _ in range(10)]
        # With jitter, delays should vary
        assert len({f"{d:.4f}" for d in delays}) > 1

    def test_jitter_stays_non_negative(self):
        cfg = RetryConfig(base_delay=0.01, jitter=True)
        for _ in range(20):
            delay = calculate_delay(1, cfg)
            assert delay >= 0


# ── retry_async ───────────────────────────────────────────────────────────────


class TestRetryAsync:
    @pytest.mark.asyncio
    async def test_succeeds_on_first_try(self):
        from core.retry import retry_async

        call_count = 0

        async def succeeding():
            nonlocal call_count
            call_count += 1
            return "success"

        cfg = RetryConfig(max_retries=3)
        result = await retry_async(succeeding, config=cfg)
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure(self):
        from core.retry import retry_async

        call_count = 0

        async def fails_twice_then_succeeds():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError(f"fail {call_count}")
            return "eventual_success"

        cfg = RetryConfig(max_retries=3, base_delay=0.001, jitter=False)
        result = await retry_async(fails_twice_then_succeeds, config=cfg)
        assert result == "eventual_success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        from core.retry import retry_async

        call_count = 0

        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("always fails")

        cfg = RetryConfig(max_retries=2, base_delay=0.001, jitter=False)
        with pytest.raises(RuntimeError, match="always fails"):
            await retry_async(always_fails, config=cfg)
        assert call_count == 3  # 1 initial + 2 retries

    @pytest.mark.asyncio
    async def test_on_retry_callback_called(self):
        from core.retry import retry_async

        attempts = []

        def on_retry(exc, attempt):
            attempts.append(attempt)

        call_count = 0

        async def fails_once():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("first failure")
            return "ok"

        cfg = RetryConfig(max_retries=2, base_delay=0.001, jitter=False, on_retry=on_retry)
        result = await retry_async(fails_once, config=cfg)
        assert result == "ok"
        assert len(attempts) == 1
        assert attempts[0] == 1

    @pytest.mark.asyncio
    async def test_does_not_retry_non_matching_exception(self):
        from core.retry import retry_async

        async def raises_value_error():
            raise ValueError("not retried")

        cfg = RetryConfig(
            max_retries=3,
            base_delay=0.001,
            retry_exceptions=(RuntimeError,),
            jitter=False,
        )
        with pytest.raises(ValueError):
            await retry_async(raises_value_error, config=cfg)


# ── with_retry decorator ──────────────────────────────────────────────────────


class TestWithRetryDecorator:
    @pytest.mark.asyncio
    async def test_decorator_wraps_function(self):
        from core.retry import with_retry

        call_count = 0

        @with_retry(max_retries=1, base_delay=0.001, jitter=False)
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("flaky")
            return "done"

        result = await flaky()
        assert result == "done"
        assert call_count == 2  # 1 fail + 1 retry

    @pytest.mark.asyncio
    async def test_decorator_preserves_function_name(self):
        from core.retry import with_retry

        @with_retry(RetryConfig())
        async def my_function():
            return "ok"

        # functools.wraps preserves __name__
        assert my_function.__name__ == "my_function"
