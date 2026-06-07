"""Startup gate middleware — refuses requests when settings failed."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_GATE_EXEMPT_PATHS = {"/live", "/api/v1/live", "/health", "/api/v1/health", "/metrics"}


class StartupGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        if getattr(request.app.state, "startup_failed", False):
            if path in _GATE_EXEMPT_PATHS:
                return await call_next(request)
            return JSONResponse(
                status_code=503,
                content={
                    "detail": (
                        "API configuration error — server started without valid settings. "
                        "Check environment variables and restart."
                    )
                },
            )

        # Block investigation submissions while infrastructure is still initializing
        # (DB/Redis not yet confirmed healthy). Health and liveness endpoints are
        # always let through so Docker healthchecks pass during startup.
        if not getattr(request.app.state, "infrastructure_ready", True):
            if path in _GATE_EXEMPT_PATHS:
                return await call_next(request)
            if request.method in ("POST", "PUT", "PATCH", "DELETE"):
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "Service is starting — infrastructure not yet ready. Retry in a few seconds."
                    },
                    headers={"Retry-After": "5"},
                )

        return await call_next(request)
