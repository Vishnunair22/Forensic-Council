"""
Unit tests for core/circuit_breaker.py.

Covers:
- CircuitState enum
- CircuitBreakerConfig defaults
- CircuitBreaker CLOSED → OPEN → HALF_OPEN → CLOSED cycle
- CircuitBreaker.get_state()
- CircuitBreaker.reset()
- CircuitBreakerOpenError
- CircuitBreakerRegistry
"""

import os
from datetime import datetime, timedelta

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

from core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitBreakerRegistry,
    CircuitState,
)

# ── CircuitBreakerConfig ───────────────────────────────────────────────────────

class TestCircuitBreakerConfig:
    def test_defaults(self):
        cfg = CircuitBreakerConfig()
        assert cfg.failure_threshold == 5
        assert cfg.success_threshold == 2
        assert cfg.timeout_seconds == 60
        assert cfg.expected_exceptions == (Exception,)

    def test_custom_values(self):
        cfg = CircuitBreakerConfig(failure_threshold=2, timeout_seconds=10)
        assert cfg.failure_threshold == 2
        assert cfg.timeout_seconds == 10


# ── CircuitBreaker CLOSED state ────────────────────────────────────────────────

class TestCircuitBreakerClosed:
    @pytest.mark.asyncio
    async def test_successful_call_passes_through(self):
        cb = CircuitBreaker("test_service", CircuitBreakerConfig())
        async def success():
            return "ok"
        result = await cb.call(success)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_single_failure_stays_closed(self):
        cb = CircuitBreaker("test_service", CircuitBreakerConfig(failure_threshold=3))
        async def failing():
            raise RuntimeError("fail")
        with pytest.raises(RuntimeError):
            await cb.call(failing)
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 1

    @pytest.mark.asyncio
    async def test_failures_at_threshold_open_circuit(self):
        cfg = CircuitBreakerConfig(failure_threshold=2)
        cb = CircuitBreaker("test_service", cfg)
        async def failing():
            raise RuntimeError("fail")
        for _ in range(2):
            try:
                await cb.call(failing)
            except RuntimeError:
                pass
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_state_resets_on_success(self):
        cfg = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker("test_service", cfg)
        cb.failure_count = 2  # Close to threshold

        async def success():
            return "ok"
        await cb.call(success)
        assert cb.failure_count == 0


# ── CircuitBreaker OPEN state ──────────────────────────────────────────────────

class TestCircuitBreakerOpen:
    @pytest.mark.asyncio
    async def test_open_circuit_blocks_calls(self):
        cfg = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=3600)
        cb = CircuitBreaker("test_service", cfg)
        async def failing():
            raise RuntimeError("fail")
        try:
            await cb.call(failing)
        except RuntimeError:
            pass
        assert cb.state == CircuitState.OPEN
        # Second call should be blocked
        with pytest.raises(CircuitBreakerOpenError):
            await cb.call(failing)

    @pytest.mark.asyncio
    async def test_open_circuit_attempts_recovery_after_timeout(self):
        cfg = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=0)
        cb = CircuitBreaker("test_service", cfg)
        async def failing():
            raise RuntimeError("fail")
        try:
            await cb.call(failing)
        except RuntimeError:
            pass
        assert cb.state == CircuitState.OPEN
        # Force recovery time to be past
        cb.last_failure_time = datetime.now() - timedelta(seconds=10)
        # Next call should transition to HALF_OPEN
        async def success():
            return "recovered"
        result = await cb.call(success)
        assert result == "recovered"


# ── CircuitBreaker HALF_OPEN state ─────────────────────────────────────────────

class TestCircuitBreakerHalfOpen:
    @pytest.mark.asyncio
    async def test_successful_calls_close_circuit(self):
        cfg = CircuitBreakerConfig(failure_threshold=1, success_threshold=2, timeout_seconds=0)
        cb = CircuitBreaker("test_service", cfg)
        cb.state = CircuitState.HALF_OPEN
        cb.success_count = 0

        async def success():
            return "ok"
        await cb.call(success)
        await cb.call(success)
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_failure_in_half_open_reopens_circuit(self):
        cfg = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=0)
        cb = CircuitBreaker("test_service", cfg)
        cb.state = CircuitState.HALF_OPEN

        async def failing():
            raise RuntimeError("fail")
        with pytest.raises(RuntimeError):
            await cb.call(failing)
        assert cb.state == CircuitState.OPEN


# ── get_state / reset ──────────────────────────────────────────────────────────

class TestCircuitBreakerGetStateAndReset:
    def test_get_state_returns_dict(self):
        cb = CircuitBreaker("test_service")
        state = cb.get_state()
        assert state["service"] == "test_service"
        assert state["state"] == "closed"
        assert state["failure_count"] == 0
        assert state["time_until_recovery"] == 0

    def test_get_state_open_includes_recovery_time(self):
        cb = CircuitBreaker("test_service")
        cb.state = CircuitState.OPEN
        cb.last_failure_time = datetime.now()
        state = cb.get_state()
        assert state["state"] == "open"
        assert state["time_until_recovery"] > 0

    def test_reset_clears_state(self):
        cb = CircuitBreaker("test_service")
        cb.state = CircuitState.OPEN
        cb.failure_count = 5
        cb.last_failure_time = datetime.now()
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.last_failure_time is None

    def test_should_attempt_recovery_true_when_no_failure(self):
        cb = CircuitBreaker("test_service")
        assert cb._should_attempt_recovery() is True

    def test_time_until_recovery_zero_when_no_failure(self):
        cb = CircuitBreaker("test_service")
        assert cb._time_until_recovery() == 0


# ── CircuitBreakerRegistry ─────────────────────────────────────────────────────

class TestCircuitBreakerRegistry:
    def test_get_creates_breaker(self):
        registry = CircuitBreakerRegistry()
        cb = registry.get("test_service")
        assert isinstance(cb, CircuitBreaker)
        assert cb.service_name == "test_service"

    def test_get_returns_same_instance(self):
        registry = CircuitBreakerRegistry()
        cb1 = registry.get("service_a")
        cb2 = registry.get("service_a")
        assert cb1 is cb2

    def test_get_with_custom_config(self):
        registry = CircuitBreakerRegistry()
        cfg = CircuitBreakerConfig(failure_threshold=10)
        cb = registry.get("custom_service", cfg)
        assert cb.config.failure_threshold == 10

    def test_get_all_returns_all_breakers(self):
        registry = CircuitBreakerRegistry()
        registry.get("service_x")
        registry.get("service_y")
        all_breakers = registry.get_all_states()
        assert "service_x" in all_breakers
        assert "service_y" in all_breakers

    def test_reset_all_resets_all_breakers(self):
        registry = CircuitBreakerRegistry()
        cb = registry.get("broken_service")
        cb.state = CircuitState.OPEN
        cb.failure_count = 10
        registry.reset_all()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
