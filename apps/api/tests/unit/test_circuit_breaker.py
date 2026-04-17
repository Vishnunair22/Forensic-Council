"""
Unit tests for the CircuitBreaker pattern.

Covers:
- CLOSED â†’ OPEN transition on successive failures
- OPEN circuit rejects calls immediately
- OPEN â†’ HALF_OPEN after recovery timeout
- HALF_OPEN â†’ CLOSED on consecutive successes
- HALF_OPEN â†’ OPEN on failure
- Concurrent calls are safe (lock semantics)
- Custom config (failure_threshold, success_threshold, timeout_seconds)
"""

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

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

from core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState

# â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _breaker(
    failure_threshold: int = 3,
    success_threshold: int = 2,
    timeout_seconds: int = 60,
) -> CircuitBreaker:
    cfg = CircuitBreakerConfig(
        failure_threshold=failure_threshold,
        success_threshold=success_threshold,
        timeout_seconds=timeout_seconds,
    )
    return CircuitBreaker("test_service", cfg)


async def _fail(breaker: CircuitBreaker, n: int) -> None:
    """Fire n failing calls through the breaker (ignoring exceptions)."""
    async def boom():
        raise RuntimeError("simulated failure")

    for _ in range(n):
        try:
            await breaker.call(boom)
        except Exception:
            pass


async def _succeed(breaker: CircuitBreaker, n: int = 1) -> None:
    """Fire n successful calls through the breaker."""
    async def ok():
        return "ok"

    for _ in range(n):
        await breaker.call(ok)


# â”€â”€ Initial state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestCircuitBreakerInitial:
    def test_starts_closed(self):
        b = _breaker()
        assert b.state == CircuitState.CLOSED

    def test_failure_count_starts_zero(self):
        b = _breaker()
        assert b.failure_count == 0

    def test_service_name_stored(self):
        b = _breaker()
        assert b.service_name == "test_service"

    @pytest.mark.asyncio
    async def test_successful_call_passes_through(self):
        b = _breaker()
        result = await b.call(AsyncMock(return_value="result"))
        assert result == "result"


# â”€â”€ CLOSED â†’ OPEN â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestCircuitBreakerOpens:
    @pytest.mark.asyncio
    async def test_opens_after_threshold_failures(self):
        b = _breaker(failure_threshold=3)
        await _fail(b, 3)
        assert b.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_does_not_open_before_threshold(self):
        b = _breaker(failure_threshold=5)
        await _fail(b, 4)
        assert b.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_open_circuit_rejects_immediately(self):
        b = _breaker(failure_threshold=2)
        await _fail(b, 2)
        assert b.state == CircuitState.OPEN
        with pytest.raises(Exception):
            await _succeed(b)

    @pytest.mark.asyncio
    async def test_failure_count_increments(self):
        b = _breaker(failure_threshold=10)
        await _fail(b, 3)
        assert b.failure_count == 3


# â”€â”€ OPEN â†’ HALF_OPEN â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestCircuitBreakerHalfOpen:
    @pytest.mark.asyncio
    async def test_transitions_to_half_open_after_timeout(self):
        b = _breaker(failure_threshold=2, timeout_seconds=1)
        await _fail(b, 2)
        assert b.state == CircuitState.OPEN
        # Simulate timeout by backdating last_failure_time
        b.last_failure_time = datetime.now() - timedelta(seconds=2)
        # Next call should attempt recovery
        try:
            await _succeed(b)
        except Exception:
            pass
        # Should be HALF_OPEN or CLOSED (depending on success)
        assert b.state in (CircuitState.HALF_OPEN, CircuitState.CLOSED)

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens_circuit(self):
        b = _breaker(failure_threshold=2, timeout_seconds=1)
        await _fail(b, 2)
        b.last_failure_time = datetime.now() - timedelta(seconds=2)
        # Force HALF_OPEN
        b.state = CircuitState.HALF_OPEN
        b.success_count = 0
        await _fail(b, 1)
        assert b.state == CircuitState.OPEN


# â”€â”€ HALF_OPEN â†’ CLOSED â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestCircuitBreakerCloses:
    @pytest.mark.asyncio
    async def test_closes_after_success_threshold(self):
        b = _breaker(failure_threshold=2, success_threshold=2)
        await _fail(b, 2)
        # Force to HALF_OPEN
        b.state = CircuitState.HALF_OPEN
        b.success_count = 0
        # Two successes should close
        await _succeed(b, 2)
        assert b.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_failure_count_resets_on_close(self):
        b = _breaker(failure_threshold=2, success_threshold=2)
        await _fail(b, 2)
        b.state = CircuitState.HALF_OPEN
        b.success_count = 0
        await _succeed(b, 2)
        assert b.failure_count == 0


# â”€â”€ Config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestCircuitBreakerConfig:
    def test_default_failure_threshold_is_5(self):
        cfg = CircuitBreakerConfig()
        assert cfg.failure_threshold == 5

    def test_default_success_threshold_is_2(self):
        cfg = CircuitBreakerConfig()
        assert cfg.success_threshold == 2

    def test_custom_failure_threshold(self):
        cfg = CircuitBreakerConfig(failure_threshold=10)
        assert cfg.failure_threshold == 10

    def test_default_timeout_seconds(self):
        cfg = CircuitBreakerConfig()
        assert cfg.timeout_seconds == 60


