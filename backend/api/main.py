"""
Forensic Council API Server
===========================

FastAPI application with WebSocket support for real-time updates.
Production-hardened with security headers, CORS controls, and
environment-aware configuration.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import time

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import auth, hitl, investigation, metrics, sessions
from api.routes.metrics import (
    increment_error_count,
    increment_request_count,
    record_request_duration,
    set_active_sessions,
)
from core.config import get_settings
from core.observability import setup_observability
from core.structured_logging import get_logger, request_id_ctx
import uuid

logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Lifespan context manager for startup and shutdown events.

    Initializes infrastructure on startup and closes on shutdown.
    """
    # Startup
    logger.info(
        "Starting Forensic Council API server...",
        env=settings.app_env,
        debug=settings.debug,
    )

    if settings.signing_key.startswith("dev-"):
        logger.warning(
            "SIGNING_KEY is using a development placeholder. "
            "Never use this in production."
        )

    # 1. Initialize databases and external clients.
    # (Migrations are now handled as a discrete init-container step in production).
    app.state.migrations_ok = True

    # Bootstrap default users (idempotent — skips if users already exist)
    try:
        from scripts.init_db import bootstrap_users
        from infra.postgres_client import get_postgres_client

        pg = await get_postgres_client()
        await bootstrap_users(pg)
        logger.info("User bootstrap completed")
    except Exception as e:
        logger.warning("User bootstrap skipped or failed", error=str(e))

    yield

    # Shutdown
    logger.info("Shutting down Forensic Council API server...")
    investigation.cleanup_connections()


# Create FastAPI app — disable docs in production
app = FastAPI(
    title="Forensic Council API",
    description="Multi-Agent Forensic Evidence Analysis System API",
    version="1.0.4",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
    lifespan=lifespan,
)

# Configure observability (OpenTelemetry)
setup_observability(app, settings)

# Configure CORS — restricted methods and headers
_cors_origins = settings.cors_allowed_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' blob: data:; "
        "connect-src 'self' ws: wss:;"
    )
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Inject a correlation ID (Request ID) for distributed tracing."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    token = request_id_ctx.set(request_id)
    
    request.state.request_id = request_id
    response = await call_next(request)
    
    response.headers["X-Request-ID"] = request_id
    request_id_ctx.reset(token)
    return response

@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    """Add cache control headers."""
    response = await call_next(request)
    
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        response.headers["Cache-Control"] = "no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        
    return response

MAX_BODY_SIZE = 55 * 1024 * 1024  # 55MB (to allow 50MB uploads + overhead)

@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    """
    Limit request body size to prevent DoS.
    
    Uses a stream-limited request wrapper to count bytes dynamically,
    bypassing bypasses that omit Content-Length (e.g. chunked encoding).
    """
    if request.method not in ["POST", "PUT", "PATCH"]:
        return await call_next(request)

    # 1. Fast path: check Content-Length if present
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_BODY_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Request body too large (max {MAX_BODY_SIZE // (1024 * 1024)}MB)"
        )

    # 2. Resilient path: wrap the ASGI receive callable at the protocol level
    #    instead of patching the private request._receive attribute.
    _count = 0
    _original_receive = request.scope.get("receive")

    async def _receive_with_limit():
        nonlocal _count
        message = await _original_receive()
        if message["type"] == "http.request":
            body = message.get("body", b"")
            _count += len(body)
            if _count > MAX_BODY_SIZE:
                raise HTTPException(status_code=413, detail="Request body too large (stream exceeded limit)")
        return message

    request.scope["receive"] = _receive_with_limit
    return await call_next(request)


# Metrics collection middleware
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Collect request metrics for monitoring."""
    start_time = time.time()
    
    # Update active sessions count
    set_active_sessions(investigation.get_active_pipelines_count())
    
    try:
        response = await call_next(request)
        
        # Record metrics
        increment_request_count()
        duration_ms = (time.time() - start_time) * 1000
        record_request_duration(duration_ms)
        
        # Track errors (4xx and 5xx)
        if response.status_code >= 400:
            increment_error_count()
        
        return response
    except Exception:
        increment_error_count()
        raise


# Diagnostic middleware — only in debug mode
if settings.debug:

    @app.middleware("http")
    async def diagnostic_middleware(request: Request, call_next):
        origin = request.headers.get("origin")
        logger.info(
            f"Incoming {request.method} to {request.url.path} from Origin: {origin}"
        )
        response = await call_next(request)
        return response


# Include routers
app.include_router(auth.router)
app.include_router(investigation.router)
app.include_router(hitl.router)
app.include_router(sessions.router)
app.include_router(metrics.router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler.
    Logs the full error but only exposes details in development.

    NOTE: FastAPI's built-in HTTPException handler runs first (it is registered
    during FastAPI.__init__ with higher MRO priority), so HTTPException instances
    should NEVER reach this handler in normal operation.  If they do (e.g. a bug
    re-raises an HTTPException outside of Starlette's ExceptionMiddleware), we
    honour the original status code instead of blindly returning 500 so that
    4xx errors are not silently promoted to 5xx.
    """
    from fastapi import HTTPException as _HTTPException
    logger.error("Global exception caught", error=str(exc), exc_info=True)

    # If an HTTPException somehow leaked here, preserve its status code and detail.
    if isinstance(exc, _HTTPException):
        content: dict = {"detail": exc.detail}
        if settings.app_env != "production":
            content["message"] = str(exc)
        return JSONResponse(
            status_code=exc.status_code, 
            content=content,
            headers=getattr(exc, "headers", None)
        )

    content = {"detail": "An internal server error occurred."}
    # Only expose error details in non-production environments
    if settings.app_env != "production":
        content["message"] = str(exc)
    return JSONResponse(status_code=500, content=content)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Forensic Council API",
        "version": "1.0.4",
        "status": "running",
        "docs": "/docs" if settings.app_env != "production" else None,
    }


@app.get("/health")
async def health_check():
    """
    Deep health check endpoint.

    Verifies connectivity to all infrastructure dependencies.
    Returns 200 only when the API and all dependencies are healthy.
    Returns 503 if any dependency is unavailable.
    """
    checks: dict = {}
    overall_healthy = True

    # ── Migration state ────────────────────────────────────────────────────────
    migrations_ok = getattr(app.state, "migrations_ok", True)
    checks["migrations"] = "ok" if migrations_ok else "failed"
    if not migrations_ok:
        overall_healthy = False

    # ── PostgreSQL ────────────────────────────────────────────────────────────
    try:
        from infra.postgres_client import get_postgres_client
        pg = await get_postgres_client()
        await pg.fetch_val("SELECT 1")
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {str(e)[:60]}"
        overall_healthy = False

    # ── Redis ─────────────────────────────────────────────────────────────────
    try:
        from infra.redis_client import get_redis_client
        redis = await get_redis_client()
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {str(e)[:60]}"
        overall_healthy = False

    # ── Qdrant ────────────────────────────────────────────────────────────────
    try:
        from infra.qdrant_client import get_qdrant_client
        qdrant = await get_qdrant_client()
        await qdrant.health_check()
        checks["qdrant"] = "ok"
    except Exception as e:
        logger.warning(f"Health check: Qdrant degraded: {e}")
        checks["qdrant"] = f"degraded: {str(e)[:60]}"
        checks["qdrant_note"] = "vector search unavailable"
        overall_healthy = False

    status_code = 200 if overall_healthy else 503
    from fastapi.responses import JSONResponse as _JSONResponse
    return _JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if overall_healthy else "degraded",
            "environment": settings.app_env,
            "active_sessions": investigation.get_active_pipelines_count(),
            "checks": checks,
        },
    )
