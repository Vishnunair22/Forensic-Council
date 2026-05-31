"""Startup gate middleware — refuses requests when settings failed."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class StartupGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if getattr(request.app.state, "startup_failed", False):
            if request.url.path in {"/live", "/api/v1/live"}:
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
        return await call_next(request)
