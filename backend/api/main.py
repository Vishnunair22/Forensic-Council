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
from core.migrations import run_migrations
from scripts.init_db import init_database
from core.logging import get_logger, request_id_ctx
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

    # Auto-initialize DB schema on every startup (idempotent — uses IF NOT EXISTS)
    # This is handled by run_migrations(), so we no longer call init_database() here.
    
    # Run versioned migrations
    try:
        from core.retry import with_retry
        
        @with_retry(max_retries=5, base_delay=1.0, retry_exceptions=(Exception,))
        async def run_migrations_with_retry():
            return await run_migrations()
        
        migration_success = await run_migrations_with_retry()
        if migration_success:
            logger.info("Database migrations completed")
        else:
            logger.error("Database migrations failed")
    except Exception as e:
        logger.error("Migration error", error=str(e))

    yield

    # Shutdown
    logger.info("Shutting down Forensic Council API server...")
    investigation.cleanup_connections()


# Create FastAPI app — disable docs in production
app = FastAPI(
    title="Forensic Council API",
    description="Multi-Agent Forensic Evidence Analysis System API",
    version="1.0.0",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
    lifespan=lifespan,
)

# Initialize distributed tracing in production
from core.observability import setup_observability
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
    """Limit request body size to prevent DoS."""
    if request.method in ["POST", "PUT", "PATCH"]:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_BODY_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Request body too large (max {MAX_BODY_SIZE // (1024 * 1024)}MB)"
            )
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
    """
    logger.error(f"Global Exception Caught: {exc}", exc_info=True)
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
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs" if settings.app_env != "production" else None,
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    Returns API status and basic environment info.
    """
    return {
        "status": "healthy",
        "environment": settings.app_env,
        "active_sessions": investigation.get_active_pipelines_count(),
    }
