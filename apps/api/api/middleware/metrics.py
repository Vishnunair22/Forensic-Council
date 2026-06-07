"""Request metrics collection middleware."""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from core.structured_logging import get_logger

logger = get_logger(__name__)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        from api.routes.metrics import (
            increment_error_count,
            increment_request_count,
            record_request_duration,
            set_active_sessions,
        )

        start_time = time.time()

        try:
            from core.persistence.redis_client import get_redis_client as _get_rc

            _rc = await _get_rc()
            # redis.asyncio scard is awaitable at runtime; the stub union with the
            # in-memory fallback makes pyright see a sync int here.
            _count = int(await _rc.client.scard("metrics:active_sessions") or 0)  # pyright: ignore[reportGeneralTypeIssues]
        except Exception:
            from api.routes.investigation import get_active_pipelines_count

            _count = get_active_pipelines_count()
        set_active_sessions(_count)

        try:
            response = await call_next(request)

            increment_request_count()
            duration_ms = (time.time() - start_time) * 1000
            record_request_duration(duration_ms)

            if response.status_code >= 400:
                increment_error_count()

            return response
        except Exception:
            increment_error_count()
            raise
