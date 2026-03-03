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

from fastapi import FastAPI, Request
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
from core.logging import get_logger

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

    # Auto-initialize DB schema on every startup (idempotent — uses IF NOT EXISTS)
    try:
        await init_database()
        logger.info("Database schema ready")
    except Exception as e:
        logger.error("DB init failed — continuing anyway", error=str(e))
    
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
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


# Metrics collection middleware
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Collect request metrics for monitoring."""
    start_time = time.time()
    
    # Update active sessions count
    set_active_sessions(len(investigation._active_pipelines))
    
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
        "active_sessions": len(investigation._active_pipelines),
    }
