"""Correlation ID middleware."""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from core.structured_logging import request_id_ctx


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        token = request_id_ctx.set(request_id)

        request.state.request_id = request_id
        response = await call_next(request)

        response.headers["X-Request-ID"] = request_id
        request_id_ctx.reset(token)
        return response
