"""Shared utilities for HTTP middleware."""

from __future__ import annotations

import os

from fastapi import Request
from fastapi.responses import JSONResponse

from core.config import get_settings
from core.structured_logging import get_logger

logger = get_logger(__name__)

# ── CSRF constants (used by csrf + rate_limit middleware) ───────────────────
CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
CSRF_EXEMPT_PATHS = {
    "/health",
    "/api/v1/health",
    "/api/v1/health/ml-tools",
    "/api/v1/health/tools",
    "/api/v1/health/providers",
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/api/v1/auth/refresh",
    "/docs",
    "/redoc",
    "/openapi.json",
}


def settings_from_app(request: Request):
    """Retrieve validated settings from app.state, or raise."""
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        raise RuntimeError(
            "Application settings are unavailable; startup configuration validation failed."
        )
    return settings


def app_env_from_env() -> str:
    return os.environ.get("APP_ENV", "development").strip().lower() or "development"
