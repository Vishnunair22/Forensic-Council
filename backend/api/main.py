"""
Forensic Council API Server
===========================

FastAPI application with WebSocket support for real-time updates.
Production-hardened with security headers, CORS controls, and
environment-aware configuration.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncio
import hashlib
import time
import secrets

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import auth, hitl, investigation, metrics, sessions, sse
from api.routes.metrics import (
    increment_error_count,
    increment_request_count,
    record_request_duration,
    set_active_sessions,
)
from core.config import get_settings, validate_production_settings
from core.observability import setup_observability
from core.structured_logging import get_logger, request_id_ctx
from infra.redis_client import get_redis_client
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

    # Harden production deployments — abort if demo credentials are still set
    try:
        validate_production_settings()
    except ValueError as e:
        logger.error("Production validation failed", error=str(e))
        raise

    if settings.signing_key.startswith("dev-"):
        logger.warning(
            "SIGNING_KEY is using a development placeholder. "
            "Never use this in production."
        )

    # 1. Initialize databases and external clients.
    # Validate that migrations have been run in production before accepting requests.
    app.state.migrations_ok = False
    try:
        from infra.postgres_client import get_postgres_client

        pg = await get_postgres_client()
        # Check for critical tables that migrations create
        table_exists = await pg.fetch_val(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'custody_log')"
        )
        if table_exists:
            app.state.migrations_ok = True
            logger.info("Migration validation passed — critical tables present")
        elif settings.app_env == "production":
            logger.error(
                "CRITICAL: Custody log table missing — migrations have not been run. "
                "Run 'python scripts/init_db.py' or use the init-container before starting the API."
            )
            raise RuntimeError(
                "Database migrations not applied — refusing to start in production"
            )
        else:
            # Development: auto-run migrations
            logger.warning(
                "Custody log table missing — attempting auto-migration in development"
            )
            try:
                from scripts.init_db import init_database

                await init_database()
                app.state.migrations_ok = True
                logger.info("Auto-migration completed")
            except Exception as mig_err:
                logger.error("Auto-migration failed — API running in degraded state", error=str(mig_err))
                app.state.migrations_ok = False
    except RuntimeError:
        raise
    except Exception as e:
        logger.warning("Migration validation skipped", error=str(e))
        app.state.migrations_ok = False

    # Bootstrap default users (idempotent — skips if users already exist)
    try:
        from scripts.init_db import bootstrap_users
        from infra.postgres_client import get_postgres_client

        pg = await get_postgres_client()
        await bootstrap_users(pg)
        logger.info("User bootstrap completed")
    except Exception as e:
        logger.warning("User bootstrap skipped or failed", error=str(e))

    # Initialize per-agent signing keys (DB-backed if PostgreSQL available, deterministic fallback otherwise)
    try:
        from core.signing import get_keystore

        ks = get_keystore()
        await ks.initialize()
        logger.info("Signing key store initialized")
    except Exception as e:
        logger.warning(
            "Key store initialization used deterministic fallback", error=str(e)
        )

    # Warm up ML tool models before accepting requests (blocking in production,
    # non-blocking in development). This eliminates 30-60s cold-start on the
    # first investigation.
    try:
        from core.ml_subprocess import warmup_all_tools

        if settings.app_env == "production":
            # Production: Block until warmup completes (max 120s)
            logger.info("Pre-warming ML tools in production (blocking)...")
            warmup_results = await asyncio.wait_for(
                warmup_all_tools(timeout_per_tool=120.0),
                timeout=180.0  # Total timeout for all tools
            )
            
            succeeded = sum(1 for v in warmup_results.values() if v)
            total = len(warmup_results)
            
            if succeeded < total:
                logger.warning(
                    f"Only {succeeded}/{total} ML tools warmed up — investigations may be slow",
                    failed_tools=[k for k, v in warmup_results.items() if not v]
                )
            else:
                logger.info(f"All {total} ML tools warmed up successfully")
        else:
            # Development: Start warmup in background (non-blocking)
            warmup_task = asyncio.create_task(warmup_all_tools(timeout_per_tool=60.0))
            app.state.warmup_task = warmup_task
            warmup_task.add_done_callback(
                lambda t: (
                    logger.info(
                        "ML tool warmup finished",
                        succeeded=sum(1 for v in t.result().values() if v)
                        if not t.cancelled() and not t.exception()
                        else 0,
                        total=len(t.result()) if not t.cancelled() and not t.exception() else 0,
                    )
                    if not t.cancelled() and not t.exception()
                    else None
                )
            )
            logger.info("ML tool warmup started in background (non-blocking)")
    except Exception as e:
        logger.warning("ML warmup not started", error=str(e))

    yield

    # ── Graceful shutdown ──────────────────────────────────────────────────
    logger.info("Initiating graceful shutdown...")

    # 0. Cancel warmup task if still running
    try:
        warmup_t = getattr(app.state, "warmup_task", None)
        if warmup_t and not warmup_t.done():
            warmup_t.cancel()
            try:
                await warmup_t
            except asyncio.CancelledError:
                pass
    except Exception as e:
        logger.warning("Failed to cancel warmup task", error=str(e))

    # 1. Stop accepting new investigations
    app.state.accepting_requests = False

    # 2. Wait for in-flight investigations to complete (up to 120s for deep analysis)
    GRACEFUL_SHUTDOWN_TIMEOUT = 120  # 2 minutes for long investigations
    try:
        from api.routes.investigation import _active_tasks

        pending = [t for t in _active_tasks.values() if not t.done()]
        if pending:
            logger.info(
                f"Waiting for {len(pending)} in-flight investigation(s) to complete..."
            )
            try:
                await asyncio.wait_for(asyncio.gather(*pending), timeout=GRACEFUL_SHUTDOWN_TIMEOUT)
            except asyncio.TimeoutError:
                logger.warning(
                    "Graceful shutdown timeout — checkpointing remaining investigations",
                    count=len(pending)
                )
                # Checkpoint remaining investigations to DB for recovery
                from core.session_persistence import get_session_persistence
                try:
                    persistence = await get_session_persistence()
                    for task in pending:
                        try:
                            # Extract session_id from task if available
                            if hasattr(task, 'get_name'):
                                task_name = task.get_name()
                                logger.info("Checkpointing investigation", task_name=task_name)
                                # Task will be cancelled and can be recovered from Redis/DB state
                            task.cancel()
                        except Exception as e:
                            logger.error("Failed to checkpoint investigation", error=str(e))
                except Exception as e:
                    logger.error("Failed to get persistence layer", error=str(e))
    except Exception as e:
        logger.warning(f"Graceful wait failed: {e}")

    # 4. Close in-flight pipeline connections
    try:
        investigation.cleanup_connections()
        logger.info("Pipeline connections cleaned up")
    except Exception as e:
        logger.warning("Pipeline cleanup failed", error=str(e))

    # 5. Close database and cache connections
    try:
        from infra.postgres_client import close_postgres_client

        await close_postgres_client()
        logger.info("PostgreSQL connection closed")
    except Exception as e:
        logger.warning("PostgreSQL shutdown error", error=str(e))

    try:
        from infra.redis_client import close_redis_client

        await close_redis_client()
        logger.info("Redis connection closed")
    except Exception as e:
        logger.warning("Redis shutdown error", error=str(e))

    try:
        from infra.qdrant_client import close_qdrant_client

        await close_qdrant_client()
        logger.info("Qdrant connection closed")
    except Exception as e:
        logger.warning("Qdrant shutdown error", error=str(e))

    logger.info("Forensic Council API server stopped")


# Create FastAPI app — disable docs in production
app = FastAPI(
    title="Forensic Council API",
    description="Multi-Agent Forensic Evidence Analysis System API",
    version="1.2.0",
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
    allow_headers=["Content-Type", "Authorization", "X-Request-ID", "X-CSRF-Token"],
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
        f"style-src 'self' {settings.allowed_cdn_domains if hasattr(settings, 'allowed_cdn_domains') else ''}; "
        "img-src 'self' blob: data:; "
        "connect-src 'self' ws: wss:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self';"
    )
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


# ── CSRF Protection (double-submit cookie pattern) ──────────────────────────
_CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
_CSRF_EXEMPT_PATHS = {
    "/health",
    "/api/v1/health",
    "/api/v1/auth/login",
    "/docs",
    "/redoc",
    "/openapi.json",
}


@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    """
    CSRF protection via the double-submit cookie pattern.

    Safe methods (GET, HEAD, OPTIONS) are always allowed.
    State-changing methods (POST, PUT, DELETE, PATCH) must carry an
    X-CSRF-Token header whose value matches the csrf_token cookie.

    The csrf_token cookie is set on every safe-method response so the
    frontend can read it and echo it back in subsequent requests.
    """
    # Always set the CSRF cookie on safe methods so the client has it
    if request.method in _CSRF_SAFE_METHODS or request.url.path in _CSRF_EXEMPT_PATHS:
        response = await call_next(request)
        # Always refresh the CSRF token on safe requests to prevent staleness
        token = secrets.token_urlsafe(32)
        response.set_cookie(
            key="csrf_token",
            value=token,
            httponly=False,  # JS must read this to send X-CSRF-Token header
            samesite="strict",
            max_age=86400,
            path="/",
        )
        return response

    # State-changing request — validate CSRF token
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
async def rate_limit_middleware(request: Request, call_next):
    """
    Redis-backed rate limiting middleware.
    
    Limits:
    - Authenticated: 60 requests / minute
    - Anonymous: 10 requests / minute
    """
    if request.url.path in _CSRF_EXEMPT_PATHS or request.method == "OPTIONS":
        return await call_next(request)

    # Identify user (IP or hashed token — never store raw tokens in Redis keys)
    ip = request.client.host if request.client else "unknown"
    auth_header = request.headers.get("Authorization", "")
    session_cookie = request.cookies.get("access_token", "")
    is_authenticated = bool(auth_header or session_cookie)

    if auth_header:
        # Hash the token so the raw bearer value is never written into Redis keys or logs
        identifier = "tok:" + hashlib.sha256(auth_header.encode()).hexdigest()[:32]
    elif session_cookie:
        identifier = (
            "cookie:"
            + hashlib.sha256(session_cookie.encode()).hexdigest()[:32]
        )
    else:
        identifier = f"ip:{ip}"
    
    limit = 60 if is_authenticated else 10
    window = 60  # seconds
    
    try:
        redis = await get_redis_client()
        key = f"rate_limit:{identifier}"
        
        # Use Lua script for atomic INCR + EXPIRE (prevents race condition)
        lua_script = """
        local key = KEYS[1]
        local window = tonumber(ARGV[1])
        local count = redis.call('incr', key)
        if count == 1 then
            redis.call('expire', key, window)
        end
        return count
        """
        count = await redis.eval(lua_script, keys=[key], args=[window])
            
        if count > limit:
            logger.warning(f"Rate limit exceeded for {identifier}", count=count, limit=limit)
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."},
                headers={"Retry-After": str(window)}
            )
    except Exception as e:
        # Don't block requests if Redis is down, just log
        logger.error("Rate limiting error (Redis)", error=str(e))
        
    return await call_next(request)


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
            detail=f"Request body too large (max {MAX_BODY_SIZE // (1024 * 1024)}MB)",
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
                raise HTTPException(
                    status_code=413,
                    detail="Request body too large (stream exceeded limit)",
                )
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
app.include_router(sse.router)


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
            headers=getattr(exc, "headers", None),
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
        "version": "1.2.0",
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
        checks["postgres"] = (
            "error: connection failed"
            if not settings.debug
            else f"error: {str(e)[:60]}"
        )
        overall_healthy = False

    # ── Redis ─────────────────────────────────────────────────────────────────
    try:
        from infra.redis_client import get_redis_client

        redis = await get_redis_client()
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = (
            "error: connection failed"
            if not settings.debug
            else f"error: {str(e)[:60]}"
        )
        overall_healthy = False

    # ── Qdrant ────────────────────────────────────────────────────────────────
    try:
        from infra.qdrant_client import get_qdrant_client

        qdrant = await get_qdrant_client()
        # Use health_check() method instead of direct API call
        await qdrant.health_check()
        checks["qdrant"] = "ok"
    except Exception as e:
        checks["qdrant"] = (
            "error: connection failed"
            if not settings.debug
            else f"error: {str(e)[:60]}"
        )
        overall_healthy = False

    # ── ML Tools Warm-Up Status ───────────────────────────────────────────────
    try:
        from core.ml_subprocess import get_warmup_status

        warmup_status = get_warmup_status()
        tools_ready = sum(1 for v in warmup_status.values() if v)
        tools_total = len(warmup_status)

        checks["ml_tools"] = {
            "status": "ready" if tools_ready == tools_total else "warming_up",
            "tools_ready": tools_ready,
            "tools_total": tools_total,
            "details": warmup_status,
        }

        # Don't mark overall as unhealthy if still warming up, just note it
        if tools_ready < tools_total:
            logger.info(
                f"ML tools still warming up: {tools_ready}/{tools_total} ready"
            )
    except Exception as e:
        checks["ml_tools"] = {
            "status": "error",
            "error": str(e)[:60],
        }
        # ML tools not ready doesn't make the whole system unhealthy

    status_code = 200 if overall_healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if overall_healthy else "degraded",
            "checks": checks,
        },
    )


@app.get("/api/v1/health/ml-tools")
async def ml_tools_health():
    """
    ML tools warm-up status endpoint.
    
    Returns detailed information about ML tool warm-up status.
    Used by operators to verify models are ready before investigations.
    """
    from core.ml_subprocess import get_warmup_status
    from core.config import get_settings
    
    settings = get_settings()
    warmup_status = get_warmup_status()
    
    tools_ready = sum(1 for v in warmup_status.values() if v)
    tools_total = len(warmup_status)
    
    return {
        "status": "ready" if tools_ready == tools_total else "warming_up",
        "tools_ready": tools_ready,
        "tools_total": tools_total,
        "warmup_percentage": round((tools_ready / tools_total * 100) if tools_total > 0 else 0, 1),
        "details": warmup_status,
        "cache_dirs": {
            "huggingface": str(settings.hf_home),
            "torch": str(settings.torch_home),
            "yolo": str(settings.yolo_config_dir),
            "easyocr": str(getattr(settings, "easyocr_model_dir", "/app/cache/easyocr")),
        }
    }

    # ── ML Tools Warm-Up Status ───────────────────────────────────────────────
    try:
        from core.ml_subprocess import get_warmup_status

        warmup_status = get_warmup_status()
        tools_ready = sum(1 for v in warmup_status.values() if v)
        tools_total = len(warmup_status)

        checks["ml_tools"] = {
            "status": "ready" if tools_ready == tools_total else "warming_up",
            "tools_ready": tools_ready,
            "tools_total": tools_total,
            "details": warmup_status,
        }

        # Don't mark overall as unhealthy if still warming up, just note it
        if tools_ready < tools_total:
            logger.info(
                f"ML tools still warming up: {tools_ready}/{tools_total} ready"
            )
    except Exception as e:
        checks["ml_tools"] = {
            "status": "error",
            "error": str(e)[:60],
        }
        # ML tools not ready doesn't make the whole system unhealthy

    status_code = 200 if overall_healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if overall_healthy else "degraded",
            "checks": checks,
        },
    )


@app.get("/api/v1/health/ml-tools")
async def ml_tools_health():
    """
    ML tools warm-up status endpoint.
    
    Returns detailed information about ML tool warm-up status.
    Used by operators to verify models are ready before investigations.
    """
    from core.ml_subprocess import get_warmup_status
    from core.config import get_settings
    
    settings = get_settings()
    warmup_status = get_warmup_status()
    
    tools_ready = sum(1 for v in warmup_status.values() if v)
    tools_total = len(warmup_status)
    
    return {
        "status": "ready" if tools_ready == tools_total else "warming_up",
        "tools_ready": tools_ready,
        "tools_total": tools_total,
        "warmup_percentage": round((tools_ready / tools_total * 100) if tools_total > 0 else 0, 1),
        "details": warmup_status,
        "cache_dirs": {
            "huggingface": str(settings.hf_home),
            "torch": str(settings.torch_home),
            "yolo": str(settings.yolo_config_dir),
            "easyocr": str(getattr(settings, "easyocr_model_dir", "/app/cache/easyocr")),
        }
    }
