"""Diagnostic logging middleware (debug mode only)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from core.config import get_settings
from core.structured_logging import get_logger

logger = get_logger(__name__)


class DiagnosticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not get_settings().debug:
            return await call_next(request)
        origin = request.headers.get("origin")
        logger.info(
            "Incoming request",
            method=request.method,
            path=request.url.path,
            origin=origin,
        )
        return await call_next(request)
