"""
DEPRECATED: Compatibility rate-limit helpers for legacy tests.

The upload route uses ``api.routes._rate_limiting`` for enforcement. This
module keeps the older boolean API used by security tests and utility callers.
Production code should use api.routes._rate_limiting directly.
"""

from __future__ import annotations

import time

from api.routes.metrics import increment_rate_limit_redis_bypasses
from core.persistence.redis_client import get_redis_client
from core.structured_logging import get_logger

logger = get_logger(__name__)

_DEFAULT_RATE_LIMIT_WINDOW = 300


async def check_investigation_rate_limit(
    user_id: str,
    *,
    window_seconds: int = _DEFAULT_RATE_LIMIT_WINDOW,
) -> bool:
    """Return True when a user may start an investigation, failing open on Redis errors."""
    key = f"inv_rate_once:{user_id}"
    now = int(time.time())
    try:
        redis = await get_redis_client()
        previous = await redis.get(key)
        if previous:
            previous_ts = int(previous.decode() if isinstance(previous, bytes) else previous)
            return now - previous_ts >= window_seconds
        await redis.set(key, str(now), ex=window_seconds)
        return True
    except Exception as exc:
        logger.warning("Investigation rate-limit Redis check failed open", error=str(exc))
        increment_rate_limit_redis_bypasses()
        return True
