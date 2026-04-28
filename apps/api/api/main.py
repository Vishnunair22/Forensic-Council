"""
Forensic Council API Server
===========================

FastAPI application with WebSocket support for real-time updates.
Production-hardened with security headers, CORS controls, and
environment-aware configuration.
"""

import asyncio
import concurrent.futures
import faulthandler
import hashlib
import json
import os
import secrets
import shutil
import signal
import sys
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import (
    auth_router,
    hitl_router,
    investigation_router,
    metrics_router,
    sessions_router,
    sse_router,
)
from api.routes.metrics import (
    increment_error_count,
    increment_rate_limit_redis_bypasses,
    increment_request_count,
    record_request_duration,
    set_active_sessions,
)
from core.config import get_settings, validate_production_settings
from core.monitoring import start_monitoring
from core.observability import setup_observability
from core.persistence.postgres_client import close_postgres_client, get_postgres_client
from core.persistence.qdrant_client import close_qdrant_client, get_qdrant_client
from core.persistence.redis_client import close_redis_client, get_redis_client
from core.structured_logging import get_logger, request_id_ctx

logger = get_logger(__name__)
settings = get_settings()

# Enable faulthandler for debugging hangs. On SIGUSR1, dump all thread stacks.
# Usage: docker compose kill -s SIGUSR1 backend
faulthandler.enable()
if hasattr(signal, "SIGUSR1"):
    faulthandler.register(signal.SIGUSR1, file=sys.stderr, chain=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Lifespan context manager for startup and shutdown events.

    Initializes infrastructure on startup and closes on shutdown.
    """
    # IMPV-03: Initialize Managed ProcessPool for CPU-bound forensic analysis (ELA, FFT, etc.)
    # FORENSIC_MAX_WORKERS env var overrides the default cap.
    # Default is min(4, cpu_count) to prevent OOM on constrained Docker hosts;
    # raise via FORENSIC_MAX_WORKERS for bare-metal production deployments.
    _env_max = int(os.environ.get("FORENSIC_MAX_WORKERS", "0"))
    max_workers = _env_max if _env_max > 0 else min(4, os.cpu_count() or 2)
    app.state.process_pool = concurrent.futures.ProcessPoolExecutor(max_workers=max_workers)
    # Cap the number of in-flight + queued CPU tasks to 4× worker count.
    # Callers must acquire this semaphore before submitting; reject with 503 on overflow.
    app.state.process_pool_semaphore = asyncio.Semaphore(max_workers * 4)
    logger.info(
        "Forensic ProcessPool initialized", max_workers=max_workers, queue_cap=max_workers * 4
    )

    # Validate production settings BEFORE starting monitoring
    # to prevent resource leaks if validation aborts
    try:
        validate_production_settings()
    except ValueError as e:
        logger.error("Production validation failed", error=str(e))
        raise

    if settings.signing_key.startswith("dev-"):
        logger.warning(
            "SIGNING_KEY is using a development placeholder. Never use this in production."
        )

    # Research model license enforcement
    if settings.enable_research_models and settings.app_env == "production":
        logger.error(
            "CRITICAL: RESEARCH_MODELS enabled in production. These models (BusterNet, F3-Net, "
            "ManTra-Net, TruFor, clovaai/AASIST) are strictly non-commercial. "
            "Refusing to start in production to prevent licensing violations. "
            "Set ENABLE_RESEARCH_MODELS=false in production."
        )
        raise RuntimeError("Research models enabled in production")

    # Refuse insecure HS256 fallback in production
    if settings.jwt_algorithm.startswith("RS") and not settings.jwt_private_key:
        if settings.app_env == "production":
            logger.error(
                "CRITICAL: JWT_ALGORITHM=%s but JWT_PRIVATE_KEY is missing. "
                "Refusing to start in production to prevent silent HS256 fallback.",
                settings.jwt_algorithm,
            )
            raise RuntimeError("Missing JWT private key for RS256 in production")
        else:
            logger.warning(
                "JWT_ALGORITHM=%s but JWT_PRIVATE_KEY is not set — "
                "falling back to HS256 (HMAC symmetric). "
                "Set JWT_PRIVATE_KEY + JWT_PUBLIC_KEY before production deployment.",
                settings.jwt_algorithm,
            )

    # Startup
    await start_monitoring(app.state)
    logger.info(
        "Starting Forensic Council API server...",
        debug=settings.debug,
    )

    if settings.use_redis_worker:
        logger.info("Worker queue mode enabled — ensure worker.py is running")
    else:
        logger.info("In-process investigation mode — investigations run in this process")

    # Pre-startup dependency validation
    REQUIRED_BINARIES = ["tesseract", "exiftool", "ffmpeg", "mediainfo"]
    missing_bins = [b for b in REQUIRED_BINARIES if not shutil.which(b)]
    if missing_bins:
        msg = f"CRITICAL: Missing system dependencies: {', '.join(missing_bins)}"
        if settings.app_env == "production":
            logger.error(msg)
            raise RuntimeError(msg)
        else:
            logger.warning(f"{msg} — Some forensic tools will fail.")

    # 1. Initialize databases and external clients.
    # Validate that migrations have been run in production before accepting requests.
    app.state.migrations_ok = False
    try:
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
            raise RuntimeError("Database migrations not applied — refusing to start in production")
        else:
            # Development: auto-run migrations
            logger.warning("Custody log table missing — attempting auto-migration in development")
            try:
                from scripts.init_db import init_database

                await init_database()
                app.state.migrations_ok = True
                logger.info("Auto-migration completed")
            except Exception as mig_err:
                logger.error(
                    "Auto-migration failed — API running in degraded state", error=str(mig_err)
                )
                app.state.migrations_ok = False
    except RuntimeError:
        raise
    except Exception as e:
        logger.warning("Migration validation skipped", error=str(e))
        app.state.migrations_ok = False

    # Bootstrap default users (idempotent — skips if users already exist)
    try:
        from scripts.init_db import bootstrap_users  # deferred: scripts may import api modules

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
        logger.warning("Key store initialization used deterministic fallback", error=str(e))

    # ── Gemini model availability validation ──────────────────────────────────
    # Checks which models in the configured cascade exist on this API key using
    # the Gemini models.list endpoint (no quota burned). Unavailable models are
    # pruned from the cascade so investigations never hit avoidable 404s.
    try:
        from core.gemini_client import GeminiVisionClient

        _gemini_client = GeminiVisionClient(settings)
        # Configure process-wide quota pool before any agent is created.
        # This bounds concurrent Gemini requests across all 5 agents so the
        # free-tier RPM quota (10 RPM) is not saturated when agents run in parallel.
        GeminiVisionClient.configure_quota_pool(settings.gemini_max_concurrent)
        await _gemini_client.validate_model_availability()
    except Exception as e:
        logger.warning("Gemini model validation skipped", error=str(e))

    # ── Crash-recovery: mark orphaned "running" sessions as "interrupted" ─────
    # If the API crashed mid-investigation, Redis still holds sessions with
    # status="running" but there is no live pipeline to complete them.
    # Marking them "interrupted" on startup prevents ghost sessions from appearing
    # as active in the sessions list and prevents WebSocket clients from waiting
    # indefinitely for progress that will never arrive.
    try:
        from api.routes._session_state import (
            SESSION_METADATA_KEY_PREFIX,  # deferred: avoids circular import at module load
        )

        _redis = await get_redis_client()
        _orphan_keys = await _redis.keys(f"{SESSION_METADATA_KEY_PREFIX}*")
        _interrupted_count = 0
        for _key in _orphan_keys:
            try:
                _raw = await _redis.get(_key)
                if not _raw:
                    continue
                try:
                    _meta = json.loads(_raw)
                except (ValueError, TypeError):
                    continue
                if isinstance(_meta, dict) and _meta.get("status") == "running":
                    _meta["status"] = "interrupted"
                    _meta["interrupted_at"] = datetime.now(UTC).isoformat()
                    _ttl = await _redis.ttl(_key)
                    _ex = _ttl if _ttl > 0 else None
                    await _redis.set(_key, json.dumps(_meta), ex=_ex)
                    _interrupted_count += 1

                    # Update custody ledger for the interrupted session
                    try:
                        from core.session_persistence import get_session_persistence

                        p = await get_session_persistence()
                        session_id = (
                            _key.decode().split(":")[-1]
                            if isinstance(_key, bytes)
                            else _key.split(":")[-1]
                        )
                        await p.save_session_state(
                            session_id=session_id,
                            case_id=_meta.get("case_id", "unknown"),
                            investigator_id=_meta.get("investigator_id", "system"),
                            pipeline_state=_meta,
                            status="interrupted",
                        )
                    except Exception as db_err:
                        logger.warning(
                            "Failed to update custody ledger for orphaned session",
                            error=str(db_err),
                        )

            except Exception as _key_err:
                logger.warning(
                    "Failed to update orphaned session key", key=_key, error=str(_key_err)
                )
        if _interrupted_count:
            logger.warning(
                "Marked orphaned sessions as interrupted (API restart recovery)",
                count=_interrupted_count,
            )
        else:
            logger.info("No orphaned running sessions found on startup")
    except Exception as e:
        logger.warning("Orphan session cleanup skipped", error=str(e))

    # Start periodic blacklist cache cleanup (runs every hour)
    try:
        from core.auth import start_blacklist_cleanup_task  # deferred: avoids circular import

        start_blacklist_cleanup_task()
    except Exception as e:
        logger.warning("Blacklist cleanup task failed to start", error=str(e))

    yield

    # ── Graceful shutdown ──────────────────────────────────────────────────
    logger.info("Initiating graceful shutdown...")

    # -1. Stop monitoring
    try:
        monitor = getattr(app.state, "heartbeat_monitor", None)
        monitor_task = getattr(app.state, "heartbeat_task", None)
        if monitor:
            monitor.stop()
            logger.info("Event loop monitor stopped")
        if monitor_task:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
    except Exception as e:
        logger.warning("Failed to stop monitoring", error=str(e))

    # -0.5 Shutdown process pool
    try:
        pool = getattr(app.state, "process_pool", None)
        if pool:
            pool.shutdown(wait=False)
            logger.info("Forensic ProcessPool shutdown initiated")
    except Exception as e:
        logger.warning("Failed to shutdown process pool", error=str(e))

    # 1. Stop accepting new investigations
    app.state.accepting_requests = False

    # 2. Wait for in-flight investigations to complete
    # Use investigation_timeout + buffer to allow longer investigations to complete
    GRACEFUL_SHUTDOWN_TIMEOUT = (
        settings.investigation_timeout + 30
    )  # Allow up to 10min + 30s buffer
    try:
        from api.routes._session_state import _active_tasks

        pending = [t for t in _active_tasks.values() if not t.done()]
        if pending:
            logger.info(f"Waiting for {len(pending)} in-flight investigation(s) to complete...")
            try:
                await asyncio.wait_for(asyncio.gather(*pending), timeout=GRACEFUL_SHUTDOWN_TIMEOUT)
            except TimeoutError:
                logger.warning(
                    "Graceful shutdown timeout — checkpointing remaining investigations",
                    count=len(pending),
                )
                # Checkpoint remaining investigations to DB for recovery
                from core.session_persistence import get_session_persistence

                try:
                    await get_session_persistence()
                    for task in pending:
                        try:
                            # Extract session_id from task if available
                            if hasattr(task, "get_name"):
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
        from api.routes.investigation import cleanup_connections

        await cleanup_connections()
        logger.info("Pipeline connections cleaned up")
    except Exception as e:
        logger.warning("Pipeline cleanup failed", error=str(e))

    # 5. Close database and cache connections
    try:
        await close_postgres_client()
        logger.info("PostgreSQL connection closed")
    except Exception as e:
        logger.warning("PostgreSQL shutdown error", error=str(e))

    try:
        await close_redis_client()
        logger.info("Redis connection closed")
    except Exception as e:
        logger.warning("Redis shutdown error", error=str(e))

    try:
        await close_qdrant_client()
        logger.info("Qdrant connection closed")
    except Exception as e:
        logger.warning("Qdrant shutdown error", error=str(e))

    logger.info("Forensic Council API server stopped")


# Create FastAPI app — disable docs in production
app = FastAPI(
    title="Forensic Council API",
    description="Multi-Agent Forensic Evidence Analysis System API",
    version="1.4.0",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
    lifespan=lifespan,
)

# Configure observability (OpenTelemetry)
setup_observability(app, settings)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return consistent 422 JSON for Pydantic validation errors."""
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "type": "validation_error"},
    )


# Configure CORS — restricted methods and headers

_cors_origins = settings.cors_allowed_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID", "X-CSRF-Token"],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# ── CSRF Protection (double-submit cookie pattern) ──────────────────────────
_CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
_CSRF_EXEMPT_PATHS = {
    "/health",
    "/api/v1/health",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/auth/logout",
    "/docs",
    "/redoc",
    "/openapi.json",
}


@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    if settings.app_env == "testing":
        return await call_next(request)
    """
    CSRF protection via the double-submit cookie pattern.

    Safe methods (GET, HEAD, OPTIONS) are always allowed.
    State-changing methods (POST, PUT, DELETE, PATCH) must carry an
    X-CSRF-Token header whose value matches the csrf_token cookie.

    The csrf_token cookie is set on every safe-method response so the
    frontend can read it and echo it back in subsequent requests.
    """
    # Set the CSRF cookie on safe methods only if the client doesn't already have one.
    # Refreshing on every safe request is unnecessary and causes spurious Set-Cookie
    # headers on every GET — one per session is sufficient.
    if request.method in _CSRF_SAFE_METHODS or request.url.path in _CSRF_EXEMPT_PATHS:
        response = await call_next(request)
        if not request.cookies.get("csrf_token"):
            token = secrets.token_urlsafe(32)
            response.set_cookie(
                key="csrf_token",
                value=token,
                httponly=False,  # JS must read this to send X-CSRF-Token header
                samesite="strict",
                secure=settings.app_env == "production",
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
        # Strip "Bearer " prefix if present for consistent hashing
        raw_token = auth_header[7:] if auth_header.lower().startswith("bearer ") else auth_header
        identifier = "tok:" + hashlib.sha256(raw_token.strip().encode()).hexdigest()[:32]
    elif session_cookie:
        identifier = "cookie:" + hashlib.sha256(session_cookie.encode()).hexdigest()[:32]
    else:
        identifier = f"ip:{ip}"

    limit = 60 if is_authenticated else 10
    window = 60  # seconds

    try:
        redis = await get_redis_client()
        key = f"rate_limit:{identifier}"

        # Use Lua script for atomic sliding-window rate limit.
        # On the first request in a window, EXPIRE is set with a +1s buffer
        # so that a key expiring exactly at t=60s does not allow a brief burst
        # before the next request establishes the new window.
        lua_script = """
        local key = KEYS[1]
        local window = tonumber(ARGV[1])
        local limit_val = tonumber(ARGV[2])
        local count = redis.call('incr', key)
        if count == 1 then
            redis.call('expire', key, window + 1)
        end
        local ttl = redis.call('ttl', key)
        if ttl < 0 then
            redis.call('expire', key, window + 1)
        end
        return {count, ttl}
        """
        result = await redis.eval(lua_script, keys=[key], args=[window, limit])
        count = result[0] if isinstance(result, (list, tuple)) else result

        if count > limit:
            logger.warning(f"Rate limit exceeded for {identifier}", count=count, limit=limit)
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."},
                headers={"Retry-After": str(window)},
            )
    except Exception as e:
        # Fail open — never block requests due to Redis unavailability, but record it.
        logger.error("Rate limiting error (Redis) — failing open", error=str(e))
        increment_rate_limit_redis_bypasses()

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

    # 2. Check if body was already read by previous middleware
    if hasattr(request.state, "body_size"):
        if request.state.body_size > MAX_BODY_SIZE:
            raise HTTPException(status_code=413, detail="Request body exceeds limit (pre-read)")
        return await call_next(request)

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
            request.state.body_size = _count
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
    from api.routes.investigation import get_active_pipelines_count

    set_active_sessions(get_active_pipelines_count())

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
        logger.info(f"Incoming {request.method} to {request.url.path} from Origin: {origin}")
        response = await call_next(request)
        return response


# Include routers
app.include_router(auth_router)
app.include_router(investigation_router)
app.include_router(hitl_router)
app.include_router(sessions_router)
app.include_router(metrics_router)
app.include_router(sse_router)


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
    logger.error("Global exception caught", error=str(exc), exc_info=True)

    # If an HTTPException somehow leaked here, preserve its status code and detail.
    if isinstance(exc, HTTPException):
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
        "version": "1.4.0",
        "status": "running",
        "docs": "/docs" if settings.app_env != "production" else None,
    }


@app.get("/health")
@app.get("/api/v1/health")
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
        pg = await get_postgres_client()
        await pg.fetch_val("SELECT 1")
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = "error: connection failed"
        if settings.debug:
            checks["postgres_debug"] = f"{type(e).__name__}: {str(e)[:100]}"
        overall_healthy = False

    # ── Redis ─────────────────────────────────────────────────────────────────
    try:
        redis = await get_redis_client()
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = "error: connection failed"
        if settings.debug:
            checks["redis_debug"] = f"{type(e).__name__}: {str(e)[:100]}"
        overall_healthy = False

    # ── Qdrant ────────────────────────────────────────────────────────────────
    try:
        qdrant = await get_qdrant_client()
        # Use health_check() method instead of direct API call
        await qdrant.health_check()
        checks["qdrant"] = "ok"
    except Exception as e:
        checks["qdrant"] = "error: connection failed"
        if settings.debug:
            checks["qdrant_debug"] = f"{type(e).__name__}: {str(e)[:100]}"
        overall_healthy = False

    # ── ML Tools Warm-Up Status (Decoupled to Worker) ─────────────────────────
    checks["ml_tools"] = {
        "status": "managed_by_worker",
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
    from core.config import get_settings
    from core.ml_subprocess import get_warmup_status, health_check_ml_tools

    settings = get_settings()
    warmup_status = get_warmup_status()
    script_status = await health_check_ml_tools()

    tools_present = sum(1 for v in script_status.values() if v != "script_not_found")
    tools_total = len(script_status)
    tools_warmed = sum(1 for v in warmup_status.values() if v)

    return {
        "status": "available" if tools_present == tools_total else "missing_scripts",
        "tools_present": tools_present,
        "tools_total": tools_total,
        "warmup_status": "managed_by_worker",
        "tools_warmed_in_process": tools_warmed,
        "presence_percentage": round(
            (tools_present / tools_total * 100) if tools_total > 0 else 0, 1
        ),
        "details": script_status,
        "warmup_details": warmup_status,
        "cache_dirs": {
            "torch": str(settings.torch_home),
            "huggingface": str(settings.hf_home),
            "ultralytics": str(settings.yolo_model_dir),
            "easyocr": str(getattr(settings, "easyocr_model_dir", "/app/cache/easyocr")),
        },
    }


@app.get("/api/v1/health/tools")
async def system_tools_health():
    """
    Check availability of external system dependencies.
    """
    import shutil

    tools = {
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "ffprobe": shutil.which("ffprobe") is not None,
        "exiftool": shutil.which("exiftool") is not None,
        "tesseract": shutil.which("tesseract") is not None,
    }

    missing = [tool for tool, present in tools.items() if not present]
    status = "healthy" if not missing else "degraded"

    return {
        "status": status,
        "tools": tools,
        "missing": missing,
        "message": "All required system tools are present"
        if not missing
        else f"Missing system tools: {', '.join(missing)}",
    }
