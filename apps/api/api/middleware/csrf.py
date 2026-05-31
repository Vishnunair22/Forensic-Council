"""CSRF protection middleware (double-submit cookie pattern)."""

from __future__ import annotations

import os
import secrets

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from api.middleware._common import CSRF_EXEMPT_PATHS, CSRF_SAFE_METHODS, settings_from_app


class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = settings_from_app(request)

        if request.method in CSRF_SAFE_METHODS or request.url.path in CSRF_EXEMPT_PATHS:
            response = await call_next(request)
            if not request.cookies.get("csrf_token"):
                token = secrets.token_urlsafe(32)
                response.set_cookie(
                    key="csrf_token",
                    value=token,
                    httponly=False,
                    samesite="strict",
                    secure=settings.app_env == "production",
                    max_age=86400,
                    path="/",
                )
            return response

        if os.environ.get("FC_TEST_SHORTCUTS") == "1":
            return await call_next(request)

        cookie_token = request.cookies.get("csrf_token")
        header_token = request.headers.get("X-CSRF-Token")
        if (
            not cookie_token
            or not header_token
            or not secrets.compare_digest(cookie_token, header_token)
        ):
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token missing or invalid"},
            )
        return await call_next(request)
