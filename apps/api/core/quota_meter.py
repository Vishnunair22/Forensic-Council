"""
Per-Investigation Quota Meter
==============================

Tracks LLM API call counts per investigation session in Redis.
Keyed by session_id so each investigation has an independent budget.

Usage:
    # Set the active session before making LLM calls:
    quota_token = session_id_ctx.set("session-abc123")
    try:
        ...call LLM...
    finally:
        session_id_ctx.reset(quota_token)

    # Read current quota state:
    state = await get_session_quota("session-abc123")

Emitted on the SSE "metrics" event at pipeline completion so investigators
can see how many API calls were consumed and whether fallbacks were triggered.
"""

from __future__ import annotations

import contextvars
import json
import time

from core.structured_logging import get_logger

logger = get_logger(__name__)

# Context variable — set once per investigation run so the Gemini/LLM clients
# can record usage without explicit session_id threading through every call frame.
session_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "investigation_session_id", default=""
)

_QUOTA_TTL_SECONDS = 86400 * 7  # retain for 7 days

_KEY_PREFIX = "quota:"


def _session_key(session_id: str) -> str:
    return f"{_KEY_PREFIX}{session_id}"


async def record_api_call(
    provider: str,
    model: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    *,
    session_id: str | None = None,
) -> None:
    """
    Record one LLM/Gemini API call in the per-session quota hash.

    Reads session_id from context variable if not provided explicitly.
    Silently skips if Redis is unavailable — quota tracking must never
    block or fail the investigation pipeline.
    """
    sid = session_id or session_id_ctx.get("")
    if not sid:
        return

    try:
        from core.persistence.redis_client import get_redis_client

        redis = await get_redis_client()
        if not redis:
            return

        key = _session_key(sid)
        provider_field = f"calls:{provider}"
        tokens_field = f"tokens:{provider}:in"
        tokens_out_field = f"tokens:{provider}:out"
        total_calls_field = "calls:total"
        total_tokens_field = "tokens:total"
        ts_field = "last_call_ts"

        pipe = redis.pipeline()
        pipe.hincrby(key, provider_field, 1)
        pipe.hincrby(key, total_calls_field, 1)
        pipe.hincrby(key, tokens_field, tokens_in)
        pipe.hincrby(key, tokens_out_field, tokens_out)
        pipe.hincrby(key, total_tokens_field, tokens_in + tokens_out)
        pipe.hset(key, ts_field, str(time.time()))
        pipe.expire(key, _QUOTA_TTL_SECONDS)
        await pipe.execute()
    except Exception as e:
        logger.debug("Quota meter: Redis write failed (non-fatal)", error=str(e))


async def get_session_quota(session_id: str) -> dict:
    """
    Return the current quota state for a session.

    Returns an empty dict if Redis is unavailable or the session has no data.
    The result is suitable for inclusion in the SSE metrics event.
    """
    if not session_id:
        return {}

    try:
        from core.persistence.redis_client import get_redis_client

        redis = await get_redis_client()
        if not redis:
            return {}

        key = _session_key(session_id)
        raw = await redis.hgetall(key)
        if not raw:
            return {}

        return {k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v for k, v in raw.items()}
    except Exception as e:
        logger.debug("Quota meter: Redis read failed (non-fatal)", error=str(e))
        return {}


async def clear_session_quota(session_id: str) -> None:
    """Remove quota data for a completed/expired session."""
    if not session_id:
        return
    try:
        from core.persistence.redis_client import get_redis_client

        redis = await get_redis_client()
        if redis:
            await redis.delete(_session_key(session_id))
    except Exception as e:
        logger.debug("Quota meter: Redis delete failed (non-fatal)", error=str(e))
