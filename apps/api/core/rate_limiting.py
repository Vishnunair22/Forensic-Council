"""Redis-backed investigation rate limits with local fallback."""

from __future__ import annotations

import time
from collections import defaultdict
from contextlib import suppress
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
    with suppress(Exception):
        from api.routes.metrics import increment_rate_limit_redis_bypasses

        increment_rate_limit_redis_bypasses()


_RATE_LIMIT_LUA = """
-- D-C-3: atomic check-and-increment for per-user investigation rate limit.
-- Without the Lua, concurrent requests could both observe current<MAX and
-- both INCR, exceeding the limit by N-1 every burst.
-- KEYS[1] = rate key, ARGV[1] = max, ARGV[2] = window seconds
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
if current >= tonumber(ARGV[1]) then
    local ttl = redis.call('TTL', KEYS[1])
    return {0, ttl}
end
local new_value = redis.call('INCR', KEYS[1])
if tonumber(new_value) == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return {1, redis.call('TTL', KEYS[1])}
"""


async def check_investigation_rate_limit(user_id: str, settings: Settings | None = None) -> None:
    """Limit investigation starts per user, failing open only for Redis failures."""
    del settings
    now = time.time()
    retry_after = USER_RATE_WINDOW_SECS
    try:
        redis = await get_redis_client()
        key = f"rate:investigation:{user_id}"
        client: Any = redis.client
        result = await client.eval(
            _RATE_LIMIT_LUA,
            1,
            key,
            str(MAX_INVESTIGATIONS_PER_USER),
            str(USER_RATE_WINDOW_SECS),
        )
        allowed = int(result[0]) if isinstance(result, (list, tuple)) else int(result)
        ttl_val = int(result[1]) if isinstance(result, (list, tuple)) and len(result) > 1 else USER_RATE_WINDOW_SECS
        if not allowed:
            retry_after = ttl_val if ttl_val > 0 else USER_RATE_WINDOW_SECS
            raise _rate_limit_error(retry_after)
        return
    except HTTPException:
        raise
    except Exception:
        _record_rate_limit_bypass()

    entries = [ts for ts in user_investigation_times[user_id] if now - ts < USER_RATE_WINDOW_SECS]
    user_investigation_times[user_id] = entries
    # Prune stale users to prevent unbounded memory growth
    if len(user_investigation_times) > 10000:
        window_start = now - USER_RATE_WINDOW_SECS
        stale_users = [
            uid for uid, ts_list in user_investigation_times.items()
            if not ts_list or max(ts_list) < window_start
        ]
        for uid in stale_users[:1000]:  # prune in batches
            del user_investigation_times[uid]
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
        # D-C-3: atomic check-and-increment via Lua. The previous
        # GET → compute → SET pattern lost concurrent writers' spend.
        cost_lua = """
        local current = tonumber(redis.call('GET', KEYS[1]) or '0')
        local quota = tonumber(ARGV[1])
        local cost = tonumber(ARGV[2])
        local window = tonumber(ARGV[3])
        if current + cost > quota then
            local ttl = redis.call('TTL', KEYS[1])
            return {0, ttl}
        end
        local new_value = current + cost
        redis.call('SET', KEYS[1], tostring(new_value), 'EX', window)
        return {1, window}
        """
        client: Any = redis.client
        result = await client.eval(
            cost_lua,
            1,
            key,
            str(quota),
            str(ESTIMATED_INVESTIGATION_COST_USD),
            str(COST_QUOTA_WINDOW_SECS),
        )
        allowed = int(result[0]) if isinstance(result, (list, tuple)) else int(result)
        ttl_val = int(result[1]) if isinstance(result, (list, tuple)) and len(result) > 1 else COST_QUOTA_WINDOW_SECS
        if not allowed:
            raise _quota_error(ttl_val if ttl_val > 0 else COST_QUOTA_WINDOW_SECS)
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
