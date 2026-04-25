"""
Circuit Breaker Pattern Implementation
======================================

Prevents cascading failures in external service calls by temporarily
blocking requests to failing services and allowing recovery.

Usage:
    breaker = CircuitBreaker("gemini_api", CircuitBreakerConfig())
    result = await breaker.call(some_async_function, arg1, arg2)
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

from core.structured_logging import get_logger

logger = get_logger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_seconds: int = 60
    expected_exceptions: tuple = (Exception,)


class CircuitBreaker:
    """
    Implements the circuit breaker pattern to prevent cascading failures.

    Monitors calls to external services and opens the circuit (stops making
    calls) when failures exceed a threshold. After a timeout, it allows
    test calls to see if the service has recovered.
    """

    def __init__(self, service_name: str, config: CircuitBreakerConfig | None = None):
        self.service_name = service_name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: datetime | None = None
        self.last_state_change = datetime.now()
        self._lock = asyncio.Lock()

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function through the circuit breaker.

        Args:
            func: Async function to call
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            Result from the function call

        Raises:
            Exception: If circuit is open or function fails
        """
        async with self._lock:
            if self.state == CircuitState.OPEN:
                if self._should_attempt_recovery():
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    logger.info(
                        "Circuit breaker transitioning to HALF_OPEN", service=self.service_name
                    )
                else:
                    wait_time = self._time_until_recovery()
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker OPEN for {self.service_name}. "
                        f"Retry after {wait_time:.1f}s"
                    )

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except self.config.expected_exceptions as e:
            await self._on_failure(e)
            raise

    async def _on_success(self):
        """Handle successful call."""
        async with self._lock:
            self.failure_count = 0
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.last_state_change = datetime.now()
                    logger.info("Circuit breaker CLOSED (recovered)", service=self.service_name)

    async def _on_failure(self, exception: Exception):
        """Handle failed call."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()

            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.last_state_change = datetime.now()
                logger.warning("Circuit breaker OPEN (recovery failed)", service=self.service_name)
            elif self.failure_count >= self.config.failure_threshold:
                self.state = CircuitState.OPEN
                self.last_state_change = datetime.now()
                logger.warning(
                    "Circuit breaker OPEN (threshold exceeded)",
                    service=self.service_name,
                    failures=self.failure_count,
                )

    def _should_attempt_recovery(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if not self.last_failure_time:
            return True
        return datetime.now() - self.last_failure_time > timedelta(
            seconds=self.config.timeout_seconds
        )

    def _time_until_recovery(self) -> float:
        """Calculate seconds until recovery attempt is allowed."""
        if not self.last_failure_time:
            return 0
        elapsed = (datetime.now() - self.last_failure_time).total_seconds()
        return max(0, self.config.timeout_seconds - elapsed)

    def get_state(self) -> dict:
        """Get current circuit breaker state for monitoring."""
        return {
            "service": self.service_name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time.isoformat()
            if self.last_failure_time
            else None,
            "time_until_recovery": self._time_until_recovery()
            if self.state == CircuitState.OPEN
            else 0,
        }

    def reset(self):
        """Manually reset the circuit breaker (for testing/admin)."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.last_state_change = datetime.now()
        logger.info("Circuit breaker manually reset", service=self.service_name)


class CircuitBreakerOpenError(Exception):
    """Raised when a call is blocked by an open circuit breaker."""

    pass


class CircuitBreakerRegistry:
    """
    Central registry for all circuit breakers in the application.
    Provides monitoring and management capabilities.
    """

    _instance: Optional["CircuitBreakerRegistry"] = None
    _breakers: dict[str, CircuitBreaker] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get(cls, service_name: str, config: CircuitBreakerConfig | None = None) -> CircuitBreaker:
        """Get or create a circuit breaker for a service."""
        if service_name not in cls._breakers:
            cls._breakers[service_name] = CircuitBreaker(service_name, config)
        return cls._breakers[service_name]

    @classmethod
    def get_all_states(cls) -> dict[str, dict]:
        """Get states of all registered circuit breakers."""
        return {name: breaker.get_state() for name, breaker in cls._breakers.items()}

    @classmethod
    def reset_all(cls):
        """Reset all circuit breakers (for testing/admin)."""
        for breaker in cls._breakers.values():
            breaker.reset()

    @classmethod
    def clear(cls):
        """Clear all registered breakers (for testing)."""
        cls._breakers.clear()


async def with_retry(
    func: Callable,
    max_retries: int = 3,
    initial_backoff: float = 1.0,
    max_backoff: float = 60.0,
    exponential_base: float = 2.0,
    retryable_exceptions: tuple = (Exception,),
) -> Any:
    """
    Execute a function with exponential backoff retry logic.

    Args:
        func: Async function to retry
        max_retries: Maximum number of retry attempts
        initial_backoff: Initial delay between retries (seconds)
        max_backoff: Maximum delay between retries (seconds)
        exponential_base: Base for exponential backoff calculation
        retryable_exceptions: Tuple of exceptions that trigger retries

    Returns:
        Result from the function call

    Raises:
        Exception: Last exception if all retries exhausted
    """
    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except retryable_exceptions as e:
            last_exception = e

            if attempt == max_retries:
                logger.error("All retry attempts exhausted", attempts=attempt + 1, error=str(e))
                raise

            backoff = min(initial_backoff * (exponential_base**attempt), max_backoff)
            logger.warning(
                f"Retry attempt {attempt + 1}/{max_retries} failed, backing off",
                backoff_seconds=backoff,
                error=str(e),
            )
            await asyncio.sleep(backoff)

    raise last_exception  # Should never reach here
