"""
Forensic Council API Server
===========================

FastAPI application assembly — creates the app, registers middleware,
includes routers, and attaches exception handlers.  All heavy logic
lives in api/lifespan.py, api/middleware/, and api/routes/.
"""

from __future__ import annotations

import faulthandler
import json
import os
import signal
import sys

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import core
from api.middleware import register_middleware
from api.middleware._common import app_env_from_env
from core.config import get_settings
from core.structured_logging import get_logger

logger = get_logger(__name__)

# ── Pre-flight settings probe ───────────────────────────────────────────────
_settings_import_error: Exception | None = None
_settings_for_import = None
try:
    _settings_for_import = get_settings()
except Exception as exc:
    _settings_import_error = exc
    logger.error("Settings validation failed while creating API app", error=str(exc))

# ── Faulthandler (SIGUSR1 thread-dump on Linux) ────────────────────────────
faulthandler.enable()
if hasattr(signal, "SIGUSR1"):
    faulthandler.register(signal.SIGUSR1, file=sys.stderr, chain=True)


def _cors_allowed_origins_from_env() -> list[str]:
    raw = os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(origin).strip() for origin in parsed if str(origin).strip()]
    except json.JSONDecodeError:
        pass
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


# ═════════════════════════════════════════════════════════════════════════════
# Create FastAPI app
# ═════════════════════════════════════════════════════════════════════════════
from api.lifespan import lifespan  # noqa: E402 — deferred to avoid circular import

app = FastAPI(
    title="Forensic Council API",
    description="Multi-Agent Forensic Evidence Analysis System API",
    version=core.__version__,
    docs_url="/docs" if app_env_from_env() != "production" else None,
    redoc_url="/redoc" if app_env_from_env() != "production" else None,
    lifespan=lifespan,
)
if _settings_for_import is not None:
    app.state.settings = _settings_for_import
# Flag for lifespan/startup_gate to detect settings failure at import time
app.state.startup_failed = _settings_import_error is not None

# ── CORS (FastAPI built-in middleware — must stay in main.py) ────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        _settings_for_import.cors_allowed_origins
        if _settings_for_import is not None
        else _cors_allowed_origins_from_env()
    ),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID", "X-CSRF-Token"],
)

# ── Custom middleware stack ──────────────────────────────────────────────────
register_middleware(app)

# ── Observability ────────────────────────────────────────────────────────────
if _settings_for_import is not None:
    from core.observability import setup_observability
    setup_observability(app, _settings_for_import)


# ═════════════════════════════════════════════════════════════════════════════
# Exception handlers
# ═════════════════════════════════════════════════════════════════════════════

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """422 with input-stripped errors (S-M-1)."""
    safe_errors = [
        {"loc": err.get("loc"), "msg": err.get("msg"), "type": err.get("type")}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"detail": safe_errors, "type": "validation_error"},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Last-resort handler — logs full trace, returns sanitized 500."""
    logger.error("Global exception caught", error=str(exc), exc_info=True)
    settings = getattr(request.app.state, "settings", None)
    app_env = settings.app_env if settings else "production"

    if isinstance(exc, HTTPException):
        content: dict = {"detail": exc.detail}
        if app_env != "production":
            content["message"] = str(exc)
        return JSONResponse(
            status_code=exc.status_code,
            content=content,
            headers=getattr(exc, "headers", None),
        )

    content = {"detail": "An internal server error occurred."}
    if app_env != "production":
        content["message"] = str(exc)
    return JSONResponse(status_code=500, content=content)


# ═════════════════════════════════════════════════════════════════════════════
# Routers
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/")
async def root(request: Request):
    settings = getattr(request.app.state, "settings", None)
    return {
        "name": "Forensic Council API",
        "version": core.__version__,
        "status": "running",
        "docs": "/docs" if settings and settings.app_env != "production" else None,
    }


if _settings_import_error is None:
    from api.routes import (
        auth_router,
        cases_router,
        health_router,
        hitl_router,
        investigation_router,
        metrics_router,
        sessions_router,
        sse_router,
        webhooks_router,
        websocket_router,
    )

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(investigation_router)
    app.include_router(hitl_router)
    app.include_router(sessions_router)
    app.include_router(websocket_router)
    app.include_router(metrics_router)
    app.include_router(sse_router)
    app.include_router(webhooks_router)
    app.include_router(cases_router)
