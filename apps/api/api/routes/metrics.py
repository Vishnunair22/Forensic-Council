"""
Metrics and Monitoring Routes
=============================

Prometheus-compatible metrics endpoint for monitoring and observability.

Counters are stored in Redis (INCR / GET) so they survive backend restarts
and are correct across multiple replicas.  When Redis is unavailable the
module degrades gracefully to in-process counters (single-replica accuracy).
"""

import asyncio
import time
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from core.auth import User, require_admin
from core.config import get_settings
from core.structured_logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])

# ── Redis key names ───────────────────────────────────────────────────────────
_KEY_REQUESTS = "metrics:requests_total"
_KEY_DURATION_SUM = "metrics:request_duration_sum"
_KEY_DURATION_COUNT = "metrics:request_duration_count"
_KEY_ERRORS = "metrics:errors_total"
_KEY_ACTIVE_SESSIONS = "metrics:active_sessions"
_KEY_INV_STARTED = "metrics:investigations_started"
_KEY_INV_COMPLETED = "metrics:investigations_completed"
_KEY_INV_FAILED = "metrics:investigations_failed"
_KEY_START_TIME = "metrics:start_time"
_KEY_RATE_LIMIT_BYPASSES = "metrics:rate_limit_redis_bypasses"

# Pipeline phase durations (histogram buckets in seconds)
_KEY_PHASE_INITIAL = "metrics:pipeline_phase_seconds_initial"
_KEY_PHASE_HITL = "metrics:pipeline_phase_seconds_hitl"
_KEY_PHASE_DEEP = "metrics:pipeline_phase_seconds_deep"
_KEY_PHASE_ARBITER = "metrics:pipeline_phase_seconds_arbiter"
_KEY_PHASE_ENRICH = "metrics:pipeline_phase_seconds_enrich"
_KEY_PHASE_SIGN = "metrics:pipeline_phase_seconds_sign"

# Histogram buckets for pipeline phase durations (in seconds)
PHASE_BUCKETS = [1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0, 900.0]

# ── Process-local fallback (used when Redis is unavailable) ──────────────────
_local: dict[str, Any] = {
    "request_count": 0,
    "request_duration_sum": 0.0,
    "request_duration_count": 0,
    "error_count": 0,
    "active_sessions": 0,
    "investigations_started": 0,
    "investigations_completed": 0,
    "investigations_failed": 0,
    "start_time": time.time(),
    "rate_limit_redis_bypasses": 0,
    # Phase durations stored as sum and count for histogram approximation
    "phase_initial_sum": 0.0,
    "phase_initial_count": 0,
    "phase_hitl_sum": 0.0,
    "phase_hitl_count": 0,
    "phase_deep_sum": 0.0,
    "phase_deep_count": 0,
    "phase_arbiter_sum": 0.0,
    "phase_arbiter_count": 0,
    "phase_enrich_sum": 0.0,
    "phase_enrich_count": 0,
    "phase_sign_sum": 0.0,
    "phase_sign_count": 0,
}


# ── Internal helpers ──────────────────────────────────────────────────────────


async def _redis_incr(key: str, amount: int = 1) -> None:
    """Increment a Redis counter; fall back to _local on error."""
    try:
        from core.persistence.redis_client import get_redis_client

        r = await get_redis_client()
        if r:
            await r.client.incrby(key, amount)
            return
    except Exception:
        pass
    # local fallback
    local_key = key.rsplit(":", maxsplit=1)[-1]
    _local[local_key] = _local.get(local_key, 0) + amount


async def _redis_set(key: str, value: Any) -> None:
    try:
        from core.persistence.redis_client import get_redis_client

        r = await get_redis_client()
        if r:
            await r.set(key, str(value))
            return
    except Exception:
        pass
    _local[key.rsplit(":", maxsplit=1)[-1]] = value


async def _redis_get_int(key: str, local_fallback_key: str) -> int:
    try:
        from core.persistence.redis_client import get_redis_client

        r = await get_redis_client()
        if r:
            val = await r.get(key)
            return int(val) if val else 0
    except Exception:
        pass
    return int(_local.get(local_fallback_key, 0))


async def _redis_get_float(key: str, local_fallback_key: str) -> float:
    try:
        from core.persistence.redis_client import get_redis_client

        r = await get_redis_client()
        if r:
            val = await r.get(key)
            return float(val) if val else 0.0
    except Exception:
        pass
    return float(_local.get(local_fallback_key, 0.0))


async def _ensure_start_time() -> None:
    """Set start_time in Redis if not already set (NX flag = only if absent)."""
    try:
        from core.persistence.redis_client import get_redis_client

        r = await get_redis_client()
        if r:
            await r.set(_KEY_START_TIME, str(_local["start_time"]), nx=True)
    except Exception:
        pass


# ── Public counter functions (called from other route modules) ────────────────


def increment_request_count() -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_redis_incr(_KEY_REQUESTS))
    except RuntimeError:
        _local["request_count"] = _local.get("request_count", 0) + 1


def increment_error_count() -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_redis_incr(_KEY_ERRORS))
    except RuntimeError:
        _local["error_count"] = _local.get("error_count", 0) + 1


def record_request_duration(duration_ms: float) -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_redis_incr(_KEY_DURATION_SUM, int(duration_ms)))
        loop.create_task(_redis_incr(_KEY_DURATION_COUNT))
    except RuntimeError:
        _local["request_duration_sum"] = _local.get("request_duration_sum", 0.0) + duration_ms
        _local["request_duration_count"] = _local.get("request_duration_count", 0) + 1


def set_active_sessions(count: int) -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_redis_set(_KEY_ACTIVE_SESSIONS, count))
    except RuntimeError:
        _local["active_sessions"] = count


def increment_investigations_started() -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_redis_incr(_KEY_INV_STARTED))
    except RuntimeError:
        _local["investigations_started"] = _local.get("investigations_started", 0) + 1


def increment_investigations_completed() -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_redis_incr(_KEY_INV_COMPLETED))
    except RuntimeError:
        _local["investigations_completed"] = _local.get("investigations_completed", 0) + 1


def increment_investigations_failed() -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_redis_incr(_KEY_INV_FAILED))
    except RuntimeError:
        _local["investigations_failed"] = _local.get("investigations_failed", 0) + 1


def increment_rate_limit_redis_bypasses() -> None:
    """Increment counter when rate limiting fails open due to Redis being unavailable."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_redis_incr(_KEY_RATE_LIMIT_BYPASSES))
    except RuntimeError:
        _local["rate_limit_redis_bypasses"] = _local.get("rate_limit_redis_bypasses", 0) + 1


def record_pipeline_phase_duration(phase: str, duration_seconds: float) -> None:
    """Record pipeline phase duration for observability."""
    phase_key_map = {
        "initial": ("phase_initial_sum", "phase_initial_count"),
        "hitl": ("phase_hitl_sum", "phase_hitl_count"),
        "deep": ("phase_deep_sum", "phase_deep_count"),
        "arbiter": ("phase_arbiter_sum", "phase_arbiter_count"),
        "enrich": ("phase_enrich_sum", "phase_enrich_count"),
        "sign": ("phase_sign_sum", "phase_sign_count"),
    }
    if phase not in phase_key_map:
        return
    sum_key, count_key = phase_key_map[phase]
    try:
        loop = asyncio.get_running_loop()
        redis_key = f"metrics:pipeline_phase_seconds_{phase}"
        loop.create_task(_redis_incr(redis_key, int(duration_seconds * 1000)))
    except RuntimeError:
        _local[sum_key] = _local.get(sum_key, 0.0) + duration_seconds
        _local[count_key] = _local.get(count_key, 0) + 1


# ── Snapshot helper ───────────────────────────────────────────────────────────


async def _snapshot() -> dict:
    """Read all metric values from Redis (with local fallbacks)."""
    await _ensure_start_time()

    start_time_raw = await _redis_get_float(_KEY_START_TIME, "start_time")
    uptime = time.time() - (start_time_raw or _local["start_time"])

    requests_total = await _redis_get_int(_KEY_REQUESTS, "request_count")
    duration_sum = await _redis_get_float(_KEY_DURATION_SUM, "request_duration_sum")
    duration_count = await _redis_get_int(_KEY_DURATION_COUNT, "request_duration_count")
    errors_total = await _redis_get_int(_KEY_ERRORS, "error_count")
    active_sessions = await _redis_get_int(_KEY_ACTIVE_SESSIONS, "active_sessions")
    inv_started = await _redis_get_int(_KEY_INV_STARTED, "investigations_started")
    inv_completed = await _redis_get_int(_KEY_INV_COMPLETED, "investigations_completed")
    inv_failed = await _redis_get_int(_KEY_INV_FAILED, "investigations_failed")
    rate_limit_bypasses = await _redis_get_int(
        _KEY_RATE_LIMIT_BYPASSES, "rate_limit_redis_bypasses"
    )

    # Pipeline phase durations
    phase_initial_avg = _local.get("phase_initial_sum", 0.0) / max(_local.get("phase_initial_count", 0), 1)
    phase_hitl_avg = _local.get("phase_hitl_sum", 0.0) / max(_local.get("phase_hitl_count", 0), 1)
    phase_deep_avg = _local.get("phase_deep_sum", 0.0) / max(_local.get("phase_deep_count", 0), 1)
    phase_arbiter_avg = _local.get("phase_arbiter_sum", 0.0) / max(_local.get("phase_arbiter_count", 0), 1)
    phase_enrich_avg = _local.get("phase_enrich_sum", 0.0) / max(_local.get("phase_enrich_count", 0), 1)
    phase_sign_avg = _local.get("phase_sign_sum", 0.0) / max(_local.get("phase_sign_count", 0), 1)

    avg_duration = duration_sum / duration_count if duration_count else 0.0
    error_rate = errors_total / requests_total if requests_total else 0.0
    total_inv = inv_completed + inv_failed
    success_rate = inv_completed / total_inv if total_inv else 1.0

    # Get database connection pool stats
    pool_stats = await _get_pool_stats()

    return {
        "uptime_seconds": uptime,
        "requests_total": requests_total,
        "request_duration_avg_ms": avg_duration,
        "errors_total": errors_total,
        "error_rate": error_rate,
        "active_sessions": active_sessions,
        "investigations_started": inv_started,
        "investigations_completed": inv_completed,
        "investigations_failed": inv_failed,
        "success_rate": success_rate,
        "rate_limit_redis_bypasses": rate_limit_bypasses,
        "db_pool_size": pool_stats["size"],
        "db_pool_available": pool_stats["available"],
        "db_pool_in_use": pool_stats["in_use"],
        "db_pool_max": pool_stats["max"],
        "phase_initial_avg": phase_initial_avg,
        "phase_hitl_avg": phase_hitl_avg,
        "phase_deep_avg": phase_deep_avg,
        "phase_arbiter_avg": phase_arbiter_avg,
        "phase_enrich_avg": phase_enrich_avg,
        "phase_sign_avg": phase_sign_avg,
    }


async def _get_pool_stats() -> dict:
    """Get connection pool statistics."""
    try:
        from core.persistence.postgres_client import get_postgres_client

        client = await get_postgres_client()
        pool = client._pool
        if pool:
            size = pool.get_size()
            idle = pool.get_idle_size()
            max_size = pool.get_max_size() if hasattr(pool, "get_max_size") else size
            return {
                "size": size,
                "available": idle,
                "in_use": size - idle,
                "max": max_size,
            }
    except Exception as e:
        logger.debug("Failed to get pool stats", error=str(e))

    return {"size": 0, "available": 0, "in_use": 0, "max": 0}


# ── Response model ────────────────────────────────────────────────────────────


class MetricsResponse(BaseModel):
    uptime_seconds: float
    requests_total: int
    request_duration_avg_ms: float
    errors_total: int
    error_rate: float
    active_sessions: int
    investigations_started: int
    investigations_completed: int
    investigations_failed: int
    success_rate: float
    rate_limit_redis_bypasses: int
    db_pool_size: int
    db_pool_available: int
    db_pool_in_use: int
    db_pool_max: int


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/", response_model=MetricsResponse)
async def get_metrics(current_user: User = Depends(require_admin)):
    """Get application metrics in JSON format. Requires admin role."""
    snap = await _snapshot()
    return MetricsResponse(**snap)


@router.get("/prometheus", response_class=PlainTextResponse)
async def get_prometheus_metrics(current_user: User = Depends(require_admin)) -> str:
    """Get metrics in Prometheus exposition format. Requires admin role."""
    snap = await _snapshot()
    lines = [
        "# HELP forensic_uptime_seconds Total uptime in seconds",
        "# TYPE forensic_uptime_seconds gauge",
        f'forensic_uptime_seconds{{app="forensic_council"}} {snap["uptime_seconds"]:.3f}',
        "",
        "# HELP forensic_requests_total Total number of HTTP requests",
        "# TYPE forensic_requests_total counter",
        f'forensic_requests_total{{app="forensic_council"}} {snap["requests_total"]}',
        "",
        "# HELP forensic_request_duration_milliseconds Average request duration",
        "# TYPE forensic_request_duration_milliseconds gauge",
        f'forensic_request_duration_milliseconds{{app="forensic_council"}} {snap["request_duration_avg_ms"]:.3f}',
        "",
        "# HELP forensic_errors_total Total number of errors",
        "# TYPE forensic_errors_total counter",
        f'forensic_errors_total{{app="forensic_council"}} {snap["errors_total"]}',
        "",
        "# HELP forensic_active_sessions Current number of active sessions",
        "# TYPE forensic_active_sessions gauge",
        f'forensic_active_sessions{{app="forensic_council"}} {snap["active_sessions"]}',
        "",
        "# HELP forensic_investigations_started_total Total investigations started",
        "# TYPE forensic_investigations_started_total counter",
        f'forensic_investigations_started_total{{app="forensic_council"}} {snap["investigations_started"]}',
        "",
        "# HELP forensic_investigations_completed_total Total investigations completed",
        "# TYPE forensic_investigations_completed_total counter",
        f'forensic_investigations_completed_total{{app="forensic_council"}} {snap["investigations_completed"]}',
        "",
        "# HELP forensic_investigations_failed_total Total investigations failed",
        "# TYPE forensic_investigations_failed_total counter",
        f'forensic_investigations_failed_total{{app="forensic_council"}} {snap["investigations_failed"]}',
        "",
        "# HELP forensic_pipeline_phase_seconds_avg Average pipeline phase duration in seconds",
        "# TYPE forensic_pipeline_phase_seconds_avg gauge",
        f'forensic_pipeline_phase_seconds_avg{{app="forensic_council",phase="initial"}} {snap["phase_initial_avg"]:.3f}',
        f'forensic_pipeline_phase_seconds_avg{{app="forensic_council",phase="hitl"}} {snap["phase_hitl_avg"]:.3f}',
        f'forensic_pipeline_phase_seconds_avg{{app="forensic_council",phase="deep"}} {snap["phase_deep_avg"]:.3f}',
        f'forensic_pipeline_phase_seconds_avg{{app="forensic_council",phase="arbiter"}} {snap["phase_arbiter_avg"]:.3f}',
        f'forensic_pipeline_phase_seconds_avg{{app="forensic_council",phase="enrich"}} {snap["phase_enrich_avg"]:.3f}',
        f'forensic_pipeline_phase_seconds_avg{{app="forensic_council",phase="sign"}} {snap["phase_sign_avg"]:.3f}',
    ]
    return "\n".join(lines) + "\n"


@router.get("/raw")
async def get_raw_metrics(request: Request):
    """
    Prometheus scrape endpoint protected by a static bearer token.

    Configure Prometheus with:
        Authorization: Bearer <METRICS_SCRAPE_TOKEN>

    Returns 503 when METRICS_SCRAPE_TOKEN is not configured.
    """
    scrape_token = getattr(settings, "metrics_scrape_token", None) or ""
    if not scrape_token:
        from fastapi.responses import JSONResponse as _JR

        return _JR(
            {"detail": "Metrics scrape endpoint disabled — set METRICS_SCRAPE_TOKEN to enable"},
            status_code=503,
        )

    import hmac as _hmac

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer ") or not _hmac.compare_digest(
        auth_header[7:], scrape_token
    ):
        from fastapi.responses import JSONResponse as _JR

        return _JR({"detail": "Unauthorized"}, status_code=401)

    snap = await _snapshot()
    lines = [
        f"forensic_uptime_seconds {snap['uptime_seconds']:.3f}",
        f"forensic_requests_total {snap['requests_total']}",
        f"forensic_errors_total {snap['errors_total']}",
        f"forensic_active_sessions {snap['active_sessions']}",
        f"forensic_investigations_started_total {snap['investigations_started']}",
        f"forensic_investigations_completed_total {snap['investigations_completed']}",
        f"forensic_investigations_failed_total {snap['investigations_failed']}",
    ]
    from fastapi.responses import PlainTextResponse as _PTR

    return _PTR("\n".join(lines) + "\n")


@router.get("/pool-status")
async def pool_status(current_user: User = Depends(require_admin)):
    """Get detailed database connection pool statistics. Requires admin role."""
    return await _get_pool_stats()
