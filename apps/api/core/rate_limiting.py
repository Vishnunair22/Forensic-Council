"""Redis-backed investigation rate limits with local fallback."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from fastapi import HTTPException

from core.config import Settings
from core.persistence import redis_client as _redis_client

MAX_INVESTIGATIONS_PER_USER = 50
USER_RATE_WINDOW_SECS = 3600
COST_QUOTA_WINDOW_SECS = 86400
ESTIMATED_INVESTIGATION_COST_USD = 1.0

DAILY_COST_QUOTA_USD = {
    "investigator": 50.0,
    "auditor": 50.0,
    "admin": 500.0,
}

user_investigation_times: dict[str, list[float]] = defaultdict(list)
mem_cost_tracker: dict[str, tuple[float, float]] = {}


async def get_redis_client():
    """Patch-friendly Redis accessor used by tests and route wrappers."""
    return await _redis_client.get_redis_client()


def _rate_limit_error(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail="Investigation rate limit exceeded. Please retry later.",
        headers={"Retry-After": str(max(1, retry_after))},
    )


def _quota_error(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail="Daily investigation cost quota exceeded. Please retry later.",
        headers={"Retry-After": str(max(1, retry_after))},
    )


def _decode_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bytes):
        value = value.decode()
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _decode_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, bytes):
        value = value.decode()
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _quota_for_role(user_role: str, settings: Settings | None = None) -> float:
    if settings is not None:
        if user_role == "admin":
            return float(getattr(settings, "daily_cost_quota_admin_usd", DAILY_COST_QUOTA_USD["admin"]))
        return float(getattr(settings, "daily_cost_quota_usd", DAILY_COST_QUOTA_USD["investigator"]))
    return DAILY_COST_QUOTA_USD.get(user_role, DAILY_COST_QUOTA_USD["investigator"])


def _record_rate_limit_bypass() -> None:
    try:
        from api.routes.metrics import increment_rate_limit_redis_bypasses

        increment_rate_limit_redis_bypasses()
    except Exception:
        pass


async def check_investigation_rate_limit(user_id: str, settings: Settings | None = None) -> None:
    """Limit investigation starts per user, failing open only for Redis failures."""
    del settings
    now = time.time()
    retry_after = USER_RATE_WINDOW_SECS
    try:
        redis = await get_redis_client()
        key = f"rate:investigation:{user_id}"
        current = _decode_int(await redis.get(key))
        if current >= MAX_INVESTIGATIONS_PER_USER:
            try:
                ttl = _decode_int(await redis.ttl(key), USER_RATE_WINDOW_SECS)
                retry_after = ttl if ttl > 0 else USER_RATE_WINDOW_SECS
            except Exception:
                retry_after = USER_RATE_WINDOW_SECS
            raise _rate_limit_error(retry_after)
        new_value = await redis.incr(key)
        if _decode_int(new_value) == 1:
            await redis.expire(key, USER_RATE_WINDOW_SECS)
        return
    except HTTPException:
        raise
    except Exception:
        _record_rate_limit_bypass()

    entries = [ts for ts in user_investigation_times[user_id] if now - ts < USER_RATE_WINDOW_SECS]
    user_investigation_times[user_id] = entries
    if len(entries) >= MAX_INVESTIGATIONS_PER_USER:
        oldest = min(entries)
        raise _rate_limit_error(int(USER_RATE_WINDOW_SECS - (now - oldest)))
    entries.append(now)


async def check_daily_cost_quota(
    user_id: str,
    user_role: str = "investigator",
    settings: Settings | None = None,
) -> None:
    """Track coarse daily investigation cost before accepting a new upload."""
    quota = _quota_for_role(user_role, settings)
    if quota <= 0:
        return

    try:
        redis = await get_redis_client()
        key = f"quota:daily-cost:{user_id}"
        current = _decode_float(await redis.get(key))
        if current + ESTIMATED_INVESTIGATION_COST_USD > quota:
            try:
                ttl = _decode_int(await redis.ttl(key), COST_QUOTA_WINDOW_SECS)
            except Exception:
                ttl = COST_QUOTA_WINDOW_SECS
            raise _quota_error(ttl if ttl > 0 else COST_QUOTA_WINDOW_SECS)
        new_value = current + ESTIMATED_INVESTIGATION_COST_USD
        try:
            await redis.set(key, str(new_value), ex=COST_QUOTA_WINDOW_SECS)
        except TypeError:
            await redis.set(key, str(new_value))
            await redis.expire(key, COST_QUOTA_WINDOW_SECS)
        return
    except HTTPException:
        raise
    except Exception:
        _record_rate_limit_bypass()

    now = time.time()
    spent, started_at = mem_cost_tracker.get(user_id, (0.0, now))
    if now - started_at >= COST_QUOTA_WINDOW_SECS:
        spent, started_at = 0.0, now
    if spent + ESTIMATED_INVESTIGATION_COST_USD > quota:
        raise _quota_error(int(COST_QUOTA_WINDOW_SECS - (now - started_at)))
    mem_cost_tracker[user_id] = (spent + ESTIMATED_INVESTIGATION_COST_USD, started_at)
