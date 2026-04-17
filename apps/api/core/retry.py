"""
Retry Utilities
===============

Provides retry logic with exponential backoff for transient failures.
Includes decorators and context managers for easy integration.
"""

import asyncio
import functools
import random
import time
from collections.abc import Callable
from typing import Any

from core.exceptions import (
    CircuitBreakerOpen,
)
from core.structured_logging import get_logger

logger = get_logger(__name__)


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retry_exceptions: tuple[type[Exception], ...] = (Exception,),
        on_retry: Callable[[Exception, int], None] | None = None,
    ):
        """
        Initialize retry configuration.

        Args:
            max_retries: Maximum number of retry attempts
            base_delay: Initial delay between retries in seconds
            max_delay: Maximum delay between retries in seconds
            exponential_base: Base for exponential backoff calculation
            jitter: Whether to add random jitter to delays
            retry_exceptions: Tuple of exception types to retry on
            on_retry: Callback function called on each retry (exception, attempt)
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retry_exceptions = retry_exceptions
        self.on_retry = on_retry


def calculate_delay(attempt: int, config: RetryConfig) -> float:
    """
    Calculate delay for a retry attempt using exponential backoff.

    Args:
        attempt: Current attempt number (1-based)
        config: Retry configuration

    Returns:
        Delay in seconds
    """
    # Exponential backoff: base_delay * (exponential_base ^ attempt)
    delay = config.base_delay * (config.exponential_base ** (attempt - 1))
    delay = min(delay, config.max_delay)

    if config.jitter:
        # Add random jitter (±25% of delay)
        jitter_amount = delay * 0.25
        delay = delay + random.uniform(-jitter_amount, jitter_amount)
        delay = max(0, delay)  # Ensure non-negative

    return delay


async def retry_async(
    func: Callable[..., Any], *args, config: RetryConfig | None = None, **kwargs
) -> Any:
    """
    Execute an async function with retry logic.

    Args:
        func: Async function to execute
        *args: Positional arguments for func
        config: Retry configuration
        **kwargs: Keyword arguments for func

    Returns:
        Result of func

    Raises:
        Last exception if all retries fail
    """
    config = config or RetryConfig()
    last_exception = None

    for attempt in range(config.max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except config.retry_exceptions as e:
            last_exception = e

            if attempt >= config.max_retries:
                logger.error(
                    "All retry attempts failed",
                    func=func.__name__,
                    max_retries=config.max_retries,
                    error=str(e),
                )
                raise

            delay = calculate_delay(attempt + 1, config)

            logger.warning(
                "Retry attempt failed",
                func=func.__name__,
                attempt=attempt + 1,
                max_retries=config.max_retries,
                delay=delay,
                error=str(e),
            )

            if config.on_retry:
                config.on_retry(e, attempt + 1)

            await asyncio.sleep(delay)

    # This should never be reached, but just in case
    raise last_exception or Exception("Retry failed without exception")


def retry_sync(
    func: Callable[..., Any], *args, config: RetryConfig | None = None, **kwargs
) -> Any:
    """
    Execute a sync function with retry logic.

    Args:
        func: Function to execute
        *args: Positional arguments for func
        config: Retry configuration
        **kwargs: Keyword arguments for func

    Returns:
        Result of func

    Raises:
        Last exception if all retries fail
    """
    config = config or RetryConfig()
    last_exception = None

    for attempt in range(config.max_retries + 1):
        try:
            return func(*args, **kwargs)
        except config.retry_exceptions as e:
            last_exception = e

            if attempt >= config.max_retries:
                logger.error(
                    "All retry attempts failed",
                    func=func.__name__,
                    max_retries=config.max_retries,
                    error=str(e),
                )
                raise

            delay = calculate_delay(attempt + 1, config)

            logger.warning(
                "Retry attempt failed",
                func=func.__name__,
                attempt=attempt + 1,
                max_retries=config.max_retries,
                delay=delay,
                error=str(e),
            )

            if config.on_retry:
                config.on_retry(e, attempt + 1)

            # For sync, use time.sleep
            time.sleep(delay)

    raise last_exception or Exception("Retry failed without exception")


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retry_exceptions: tuple[type[Exception], ...] = (Exception,),
):
    """
    Decorator to add retry logic to a function.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries
        max_delay: Maximum delay between retries
        exponential_base: Base for exponential backoff
        jitter: Whether to add jitter
        retry_exceptions: Exception types to retry on

    Returns:
        Decorated function with retry logic
    """
    config = RetryConfig(
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=max_delay,
        exponential_base=exponential_base,
        jitter=jitter,
        retry_exceptions=retry_exceptions,
    )

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await retry_async(func, *args, config=config, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            return retry_sync(func, *args, config=config, **kwargs)

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


class CircuitBreaker:
    """
    Circuit breaker pattern implementation.

    Prevents repeated calls to failing services.
    States: CLOSED (normal), OPEN (failing), HALF_OPEN (testing)
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3,
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            half_open_max_calls: Max calls in half-open state
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        self._state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self._half_open_calls = 0

    @property
    def state(self) -> str:
        """
        Get current circuit state.
        Triggers a lazy transition from OPEN to HALF_OPEN if the recovery timeout has expired.
        """
        self._check_and_maybe_half_open()
        return self._state

    def _check_and_maybe_half_open(self) -> str:
        """
        Check if the circuit should transition OPEN → HALF_OPEN based on elapsed
        recovery time.  This is called explicitly inside call() — not inside the
        state property — so that simply reading .state is always idempotent.
        """
        if self._state == "OPEN" and self._last_failure_time:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                self._state = "HALF_OPEN"
                self._half_open_calls = 0
                logger.info("Circuit breaker transitioning to HALF_OPEN")
        return self._state

    def record_success(self):
        """Record a successful call."""
        self._failure_count = 0

        if self._state == "HALF_OPEN":
            self._success_count += 1
            if self._success_count >= self.half_open_max_calls:
                logger.info("Circuit breaker transitioning to CLOSED")
                self._state = "CLOSED"
                self._success_count = 0

    def record_failure(self):
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state == "HALF_OPEN":
            logger.warning("Circuit breaker transitioning to OPEN")
            self._state = "OPEN"
        elif self._failure_count >= self.failure_threshold:
            logger.warning("Circuit breaker transitioning to OPEN")
            self._state = "OPEN"

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Function to call
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpen: If circuit is open
            Exception: If function raises
        """
        state = self._check_and_maybe_half_open()

        if state == "OPEN":
            raise CircuitBreakerOpen("Circuit breaker is OPEN")

        if state == "HALF_OPEN":
            if self._half_open_calls >= self.half_open_max_calls:
                raise CircuitBreakerOpen("Circuit breaker HALF_OPEN limit reached")
            self._half_open_calls += 1

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise


# Predefined retry configs for common scenarios
RETRY_CONFIGS = {
    "database": RetryConfig(
        max_retries=5,
        base_delay=0.5,
        max_delay=30.0,
        retry_exceptions=(ConnectionError, TimeoutError, OSError),
    ),
    "external_api": RetryConfig(
        max_retries=3,
        base_delay=1.0,
        max_delay=10.0,
        retry_exceptions=(ConnectionError, TimeoutError),
    ),
    "network": RetryConfig(
        max_retries=5,
        base_delay=0.5,
        max_delay=60.0,
        retry_exceptions=(ConnectionError, TimeoutError, OSError),
    ),
}


def get_retry_config(name: str) -> RetryConfig:
    """Get a predefined retry configuration by name."""
    return RETRY_CONFIGS.get(name, RetryConfig())
