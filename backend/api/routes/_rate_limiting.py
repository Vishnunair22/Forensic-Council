"""
Rate Limiting & Cost Quota
===========================

Per-user rate limiting and daily API cost quota enforcement.
Prefers Redis (replica-safe); falls back to in-process dicts.

In production, rate limiting fails CLOSED when Redis is unavailable.
"""
import os
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
    "investigator": float(os.getenv("DAILY_COST_QUOTA_USD", "50.0")),
    "auditor":      float(os.getenv("DAILY_COST_QUOTA_USD", "50.0")),
    "admin":        float(os.getenv("DAILY_COST_QUOTA_ADMIN_USD", "500.0")),
}
_DAILY_COST_QUOTA_DEFAULT_USD = float(os.getenv("DAILY_COST_QUOTA_USD", "50.0"))
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
        from infra.redis_client import get_redis_client
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

    if user_id not in _user_investigation_times and len(_user_investigation_times) >= _MEM_RATE_MAX_USERS:
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
    """
    key = f"cost_quota:{user_id}"
    quota = _DAILY_COST_QUOTA_USD.get(user_role, _DAILY_COST_QUOTA_DEFAULT_USD)

    try:
        from infra.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            cost_raw = await redis.get(key)
            current_cost = float(cost_raw) if cost_raw else 0.0

            if current_cost + _COST_PER_INVESTIGATION_USD > quota:
                ttl = await redis.ttl(key)
                retry_after = ttl if ttl > 0 else _COST_QUOTA_WINDOW_SECS
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"Daily API cost quota exceeded (${quota:.0f}/day). "
                        f"Current usage: ${current_cost:.2f}. "
                        f"Quota resets in {retry_after // 3600}h {(retry_after % 3600) // 60}m."
                    ),
                    headers={"Retry-After": str(retry_after)},
                )

            new_cost = await redis.incrbyfloat(key, _COST_PER_INVESTIGATION_USD)
            if new_cost <= _COST_PER_INVESTIGATION_USD:
                await redis.expire(key, _COST_QUOTA_WINDOW_SECS)
            return
    except HTTPException:
        raise
    except Exception:
        pass

    # ── In-memory fallback ────────────────────────────────────────────────────
    now = time.time()

    if user_id not in _mem_cost_tracker and len(_mem_cost_tracker) >= _MEM_COST_MAX_USERS:
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

    _mem_cost_tracker[user_id] = (current_cost + _COST_PER_INVESTIGATION_USD, window_start)
