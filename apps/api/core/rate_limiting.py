"""
Lightweight Redis-backed rate limiter.

Kept as a small compatibility utility for infrastructure tests and older
callers. Route-specific investigation and quota checks live in
api.routes._rate_limiting.
"""

from __future__ import annotations

from core.persistence import redis_client


class RateLimiter:
    """Fixed-window async rate limiter backed by the configured Redis client."""

    def __init__(self, window_seconds: int, max_requests: int) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if max_requests <= 0:
            raise ValueError("max_requests must be positive")
        self.window_seconds = window_seconds
        self.max_requests = max_requests

    async def is_allowed(self, identity: str) -> bool:
        """Return True while identity remains within the fixed request window."""
        key = f"rate_limit:{identity}"
        redis = await redis_client.get_redis_client()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, self.window_seconds)
        return int(count) <= self.max_requests
