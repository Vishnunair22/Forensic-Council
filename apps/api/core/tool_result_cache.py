"""
Content-hash-keyed shared tool-result cache.

Lets the local visual ensemble's heavy tool runs (CLIP scene classification,
FFT frequency analysis) be reused by the per-agent tool handlers instead of
re-executing them — eliminating double-runs on the Gemini-down path where both
the ensemble (preflight fallback) and the agents run the same tool.

Keyed by content SHA-256 so the result is reused across:
  - ensemble → agent (the primary redundancy this closes)
  - agent → agent (two agents needing the same whole-image tool)
  - initial → deep phase, and re-uploads of the same file

Only whole-image, parameter-free initial-pass tools whose ensemble and handler
code paths call the *identical* underlying function are cached here, so a hit
is byte-for-byte equivalent to a fresh run. ROI-guided / deep-phase variants
use different inputs, miss the cache, and correctly run fresh.
"""

from __future__ import annotations

from typing import Any

from core.structured_logging import get_logger

logger = get_logger(__name__)

# 4-hour TTL, matching the visual-context store.
_TTL_SECONDS = 14400

# Canonical tool names safe to share (ensemble path == handler path).
SHAREABLE_TOOLS = frozenset({"analyze_image_content", "frequency_domain_analysis"})


def _key(content_hash: str, tool_name: str) -> str:
    return f"tool_result_v2:{content_hash}:{tool_name}"


async def cache_tool_result(content_hash: str, tool_name: str, result: Any) -> None:
    """Persist a tool result keyed by content hash. Best-effort — never raises."""
    if not content_hash or tool_name not in SHAREABLE_TOOLS:
        return
    if not isinstance(result, (dict, list)):
        return
    try:
        from core.persistence.redis_client import get_redis_client

        redis = await get_redis_client()
        await redis.set(_key(content_hash, tool_name), result, ex=_TTL_SECONDS)
    except Exception as exc:
        logger.debug("Tool result cache write skipped", tool=tool_name, error=str(exc))


async def get_cached_tool_result(content_hash: str, tool_name: str) -> Any | None:
    """Return a cached tool result, or None on miss. Best-effort — never raises."""
    if not content_hash or tool_name not in SHAREABLE_TOOLS:
        return None
    try:
        from core.persistence.redis_client import get_redis_client

        redis = await get_redis_client()
        cached = await redis.get_json(_key(content_hash, tool_name))
        if isinstance(cached, (dict, list)):
            return cached
    except Exception as exc:
        logger.debug("Tool result cache read skipped", tool=tool_name, error=str(exc))
    return None
