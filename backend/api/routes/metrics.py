"""
Metrics and Monitoring Routes
=============================

Prometheus-compatible metrics endpoint for monitoring and observability.
Provides application metrics, system metrics, and business metrics.
"""

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from core.auth import require_admin, User
from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])

# In-memory metrics storage (use Redis in production for distributed setups)
_metrics_store: dict[str, Any] = {
    "request_count": 0,
    "request_duration_sum": 0.0,
    "request_duration_count": 0,
    "error_count": 0,
    "active_sessions": 0,
    "investigations_started": 0,
    "investigations_completed": 0,
    "investigations_failed": 0,
    "start_time": time.time(),
}


class MetricsResponse(BaseModel):
    """Metrics response model."""
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


class PrometheusMetricsResponse(BaseModel):
    """Prometheus-formatted metrics."""
    content: str


def increment_request_count():
    """Increment total request counter."""
    _metrics_store["request_count"] += 1


def record_request_duration(duration_ms: float):
    """Record request duration for averaging."""
    _metrics_store["request_duration_sum"] += duration_ms
    _metrics_store["request_duration_count"] += 1


def increment_error_count():
    """Increment error counter."""
    _metrics_store["error_count"] += 1


def set_active_sessions(count: int):
    """Set current active sessions count."""
    _metrics_store["active_sessions"] = count


def increment_investigations_started():
    """Increment investigations started counter."""
    _metrics_store["investigations_started"] += 1


def increment_investigations_completed():
    """Increment investigations completed counter."""
    _metrics_store["investigations_completed"] += 1


def increment_investigations_failed():
    """Increment investigations failed counter."""
    _metrics_store["investigations_failed"] += 1


@router.get("/", response_model=MetricsResponse)
async def get_metrics(current_user: User = Depends(require_admin)):
    """
    Get application metrics in JSON format.
    
    Requires admin role for access.
    
    Returns:
        MetricsResponse with current application metrics
    """
    uptime = time.time() - _metrics_store["start_time"]
    
    # Calculate averages
    if _metrics_store["request_duration_count"] > 0:
        avg_duration = (
            _metrics_store["request_duration_sum"] / _metrics_store["request_duration_count"]
        )
    else:
        avg_duration = 0.0
    
    # Calculate error rate
    if _metrics_store["request_count"] > 0:
        error_rate = _metrics_store["error_count"] / _metrics_store["request_count"]
    else:
        error_rate = 0.0
    
    # Calculate investigation success rate
    total_investigations = (
        _metrics_store["investigations_completed"] + _metrics_store["investigations_failed"]
    )
    if total_investigations > 0:
        success_rate = _metrics_store["investigations_completed"] / total_investigations
    else:
        success_rate = 1.0
    
    return MetricsResponse(
        uptime_seconds=uptime,
        requests_total=_metrics_store["request_count"],
        request_duration_avg_ms=avg_duration,
        errors_total=_metrics_store["error_count"],
        error_rate=error_rate,
        active_sessions=_metrics_store["active_sessions"],
        investigations_started=_metrics_store["investigations_started"],
        investigations_completed=_metrics_store["investigations_completed"],
        investigations_failed=_metrics_store["investigations_failed"],
        success_rate=success_rate,
    )


@router.get("/prometheus", response_class=PrometheusMetricsResponse)
async def get_prometheus_metrics(current_user: User = Depends(require_admin)):
    """
    Get metrics in Prometheus exposition format.
    
    Requires admin role for access.
    This endpoint is compatible with Prometheus scraping.
    
    Returns:
        Plain text metrics in Prometheus format
    """
    uptime = time.time() - _metrics_store["start_time"]
    
    # Build Prometheus format output
    lines = [
        "# HELP forensic_uptime_seconds Total uptime in seconds",
        "# TYPE forensic_uptime_seconds gauge",
        f'forensic_uptime_seconds{{app="forensic_council"}} {uptime}',
        "",
        "# HELP forensic_requests_total Total number of requests",
        "# TYPE forensic_requests_total counter",
        f'forensic_requests_total{{app="forensic_council"}} {_metrics_store["request_count"]}',
        "",
        "# HELP forensic_request_duration_milliseconds Average request duration",
        "# TYPE forensic_request_duration_milliseconds gauge",
    ]
    
    if _metrics_store["request_duration_count"] > 0:
        avg_duration = (
            _metrics_store["request_duration_sum"] / _metrics_store["request_duration_count"]
        )
    else:
        avg_duration = 0.0
    
    lines.extend([
        f'forensic_request_duration_milliseconds{{app="forensic_council"}} {avg_duration}',
        "",
        "# HELP forensic_errors_total Total number of errors",
        "# TYPE forensic_errors_total counter",
        f'forensic_errors_total{{app="forensic_council"}} {_metrics_store["error_count"]}',
        "",
        "# HELP forensic_active_sessions Current number of active sessions",
        "# TYPE forensic_active_sessions gauge",
        f'forensic_active_sessions{{app="forensic_council"}} {_metrics_store["active_sessions"]}',
        "",
        "# HELP forensic_investigations_started_total Total investigations started",
        "# TYPE forensic_investigations_started_total counter",
        f'forensic_investigations_started_total{{app="forensic_council"}} {_metrics_store["investigations_started"]}',
        "",
        "# HELP forensic_investigations_completed_total Total investigations completed",
        "# TYPE forensic_investigations_completed_total counter",
        f'forensic_investigations_completed_total{{app="forensic_council"}} {_metrics_store["investigations_completed"]}',
        "",
        "# HELP forensic_investigations_failed_total Total investigations failed",
        "# TYPE forensic_investigations_failed_total counter",
        f'forensic_investigations_failed_total{{app="forensic_council"}} {_metrics_store["investigations_failed"]}',
    ])
    
    content = "\n".join(lines)
    return PrometheusMetricsResponse(content=content)


# Raw endpoint for Prometheus scraping (no auth required, IP-restricted in production)
@router.get("/raw")
async def get_raw_metrics():
    """
    Get raw Prometheus metrics without authentication.
    
    WARNING: This endpoint should be IP-restricted at the infrastructure level
    (e.g., only allow Prometheus server IP). Do not expose publicly.
    
    Returns:
        Plain text metrics in Prometheus format
    """
    # In production, check source IP or use a secret token
    # For now, this is a simplified endpoint
    
    uptime = time.time() - _metrics_store["start_time"]
    
    lines = [
        f'forensic_uptime_seconds {uptime}',
        f'forensic_requests_total {_metrics_store["request_count"]}',
        f'forensic_errors_total {_metrics_store["error_count"]}',
        f'forensic_active_sessions {_metrics_store["active_sessions"]}',
        f'forensic_investigations_started_total {_metrics_store["investigations_started"]}',
        f'forensic_investigations_completed_total {_metrics_store["investigations_completed"]}',
        f'forensic_investigations_failed_total {_metrics_store["investigations_failed"]}',
    ]
    
    return "\n".join(lines)
