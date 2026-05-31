"""Upload size limiting middleware."""

from __future__ import annotations

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

MAX_BODY_SIZE = 55 * 1024 * 1024  # 55MB (to allow 50MB uploads + overhead)


class UploadLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method not in ["POST", "PUT", "PATCH"]:
            return await call_next(request)

        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_BODY_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Request body too large (max {MAX_BODY_SIZE // (1024 * 1024)}MB)",
            )

        if hasattr(request.state, "body_size"):
            if request.state.body_size > MAX_BODY_SIZE:
                raise HTTPException(status_code=413, detail="Request body exceeds limit (pre-read)")
            return await call_next(request)

        _count = 0
        _original_receive = request.scope.get("receive")

        async def _receive_with_limit():
            nonlocal _count
            message = await _original_receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                _count += len(body)
                request.state.body_size = _count
                if _count > MAX_BODY_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="Request body too large (stream exceeded limit)",
                    )
            return message

        request.scope["receive"] = _receive_with_limit
        return await call_next(request)
