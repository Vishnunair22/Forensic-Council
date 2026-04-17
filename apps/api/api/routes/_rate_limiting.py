"""
Rate Limiting & Cost Quota
===========================

Per-user rate limiting and daily API cost quota enforcement.
Prefers Redis (replica-safe); falls back to in-process dicts.

In production, rate limiting fails CLOSED when Redis is unavailable.
"""

import time

from fastapi import HTTPException, status

from core.config import get_settings
from core.structured_logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

# ── Per-user upload rate limiter ──────────────────────────────────────────────
_MAX_INVESTIGATIONS_PER_USER = 50
_USER_RATE_WINDOW_SECS = 300
_USER_RATE_LOCKOUT_SECS = 30

_user_investigation_times: dict[str, list[float]] = {}
_MEM_RATE_MAX_USERS = 10_000

# ── Per-user daily API cost quota ────────────────────────────────────────────
_COST_PER_INVESTIGATION_USD = 1.60
_DAILY_COST_QUOTA_USD = {
    "investigator": 50.0,
    "auditor": 50.0,
    "admin": 500.0,
}
_DAILY_COST_QUOTA_DEFAULT_USD = 50.0
_COST_QUOTA_WINDOW_SECS = 86400

_mem_cost_tracker: dict[str, tuple[float, float]] = {}
_MEM_COST_MAX_USERS = 10_000


async def check_investigation_rate_limit(user_id: str) -> None:
    """
    Raise HTTP 429 if the user has exceeded the investigation rate limit.

    Prefers Redis (replica-safe); falls back to in-process dict.
    In production, fails CLOSED when Redis is unavailable.
    """
    key = f"inv_rate:{user_id}"
    now = time.time()
    is_production = settings.app_env == "production"

    try:
        from core.persistence.redis_client import get_redis_client

        redis = await get_redis_client()
        if redis:
            count_raw = await redis.get(key)
            count = int(count_raw) if count_raw else 0
            if count >= _MAX_INVESTIGATIONS_PER_USER:
                ttl = await redis.ttl(key)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"Too many investigations started. "
                        f"Try again in {max(ttl, 1)} seconds."
                    ),
                    headers={"Retry-After": str(max(ttl, 1))},
                )
            new_count = await redis.incr(key)
            if new_count == 1:
                await redis.expire(key, _USER_RATE_WINDOW_SECS)
            return
    except HTTPException:
        raise
    except Exception:
        if is_production:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rate limiting service unavailable. Please try again later.",
                headers={"Retry-After": "30"},
            )

    # ── In-memory fallback (development only) ────────────────────────────────
    cutoff = now - _USER_RATE_WINDOW_SECS

    if (
        user_id not in _user_investigation_times
        and len(_user_investigation_times) >= _MEM_RATE_MAX_USERS
    ):
        oldest_uid = next(iter(_user_investigation_times))
        _user_investigation_times.pop(oldest_uid, None)

    times = _user_investigation_times.setdefault(user_id, [])
    times[:] = [t for t in times if t > cutoff]
    if len(times) >= _MAX_INVESTIGATIONS_PER_USER:
        retry_after = int(_USER_RATE_WINDOW_SECS - (now - times[0])) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Too many investigations started. "
                f"Try again in {max(retry_after, 1)} seconds."
            ),
            headers={"Retry-After": str(max(retry_after, 1))},
        )
    times.append(now)


async def check_daily_cost_quota(user_id: str, user_role: str = "investigator") -> None:
    """
    Raise HTTP 429 if the user has exceeded their daily API cost quota.

    Each investigation costs approximately $1.60. Quota is configurable
    via DAILY_COST_QUOTA_USD env var (default $50/day).

    Issue 8.1: Check + decrement is now atomic via a Lua script to prevent
    the TOCTOU race where two concurrent requests both see cost < quota
    and both proceed, exceeding the budget.
    """
    key = f"cost_quota:{user_id}"
    quota = _DAILY_COST_QUOTA_USD.get(user_role, _DAILY_COST_QUOTA_DEFAULT_USD)
    is_production = settings.app_env == "production"

    # Lua script: atomically check quota then increment only if within budget.
    # Returns [allowed (0|1), new_cost_cents, ttl_seconds]
    # We work in integer cents to avoid floating-point precision issues in Lua.
    _COST_CENTS = int(_COST_PER_INVESTIGATION_USD * 100)
    _QUOTA_CENTS = int(quota * 100)
    _lua_quota = """
    local key = KEYS[1]
    local cost = tonumber(ARGV[1])
    local quota = tonumber(ARGV[2])
    local window = tonumber(ARGV[3])
    local current = tonumber(redis.call('GET', key) or 0)
    if current + cost > quota then
        return {0, current, redis.call('TTL', key)}
    end
    local new_val = redis.call('INCRBYFLOAT', key, cost)
    if tonumber(new_val) <= cost then
        redis.call('EXPIRE', key, window)
    end
    return {1, new_val, window}
    """

    try:
        from core.persistence.redis_client import get_redis_client

        redis = await get_redis_client()
        if redis:
            result = await redis.client.eval(
                _lua_quota, 1, key,
                _COST_CENTS, _QUOTA_CENTS, _COST_QUOTA_WINDOW_SECS
            )
            allowed, current_cents, ttl = int(result[0]), int(result[1]), int(result[2])
            if not allowed:
                retry_after = ttl if ttl > 0 else _COST_QUOTA_WINDOW_SECS
                current_cost = current_cents / 100
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"Daily API cost quota exceeded (${quota:.0f}/day). "
                        f"Current usage: ${current_cost:.2f}. "
                        f"Quota resets in {retry_after // 3600}h {(retry_after % 3600) // 60}m."
                    ),
                    headers={"Retry-After": str(retry_after)},
                )
            return
    except HTTPException:
        raise
    except Exception:
        # Issue 8.2: Fail CLOSED in production when Redis is unavailable
        if is_production:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Cost quota service unavailable. Please try again later.",
                headers={"Retry-After": "30"},
            )

    # ── In-memory fallback ────────────────────────────────────────────────────
    now = time.time()

    if (
        user_id not in _mem_cost_tracker
        and len(_mem_cost_tracker) >= _MEM_COST_MAX_USERS
    ):
        oldest = next(iter(_mem_cost_tracker))
        _mem_cost_tracker.pop(oldest, None)

    current_cost, window_start = _mem_cost_tracker.get(user_id, (0.0, now))

    if now - window_start >= _COST_QUOTA_WINDOW_SECS:
        current_cost = 0.0
        window_start = now

    if current_cost + _COST_PER_INVESTIGATION_USD > quota:
        retry_after = int(_COST_QUOTA_WINDOW_SECS - (now - window_start)) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Daily API cost quota exceeded (${quota:.0f}/day). "
                f"Current usage: ${current_cost:.2f}. "
                f"Quota resets in {retry_after // 3600}h {(retry_after % 3600) // 60}m."
            ),
            headers={"Retry-After": str(retry_after)},
        )

    _mem_cost_tracker[user_id] = (
        current_cost + _COST_PER_INVESTIGATION_USD,
        window_start,
    )
