"""Application lifespan — startup and shutdown logic.

Extracted from api/main.py to keep the app-assembly file small.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI

from core.config import get_settings, validate_production_settings
from core.monitoring import start_monitoring
from core.persistence import (
    close_postgres_client,
    close_qdrant_client,
    close_redis_client,
    get_postgres_client,
    get_redis_client,
)
from core.structured_logging import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown context manager for the FastAPI app."""

    settings = get_settings()
    if settings is None:
        raise RuntimeError(
            "get_settings() returned None — check your .env file and ensure all required "
            "environment variables are set. Run: cp .env.example .env and fill all values."
        )
    app.state.settings = settings

    # ── Settings-import failure marker ────────────────────────────────────────
    if getattr(app.state, "startup_failed", False):
        app.state.startup_failed = True
        logger.error(
            "Settings failed to load at module import — API started without routes. "
            "All requests will return 503 until the server is restarted with valid configuration.",
            error=str(getattr(app.state, "settings_import_error", None) or "settings import failed"),
        )

    # ── Process pool ─────────────────────────────────────────────────────────
    try:
        _env_max = int(os.environ.get("FORENSIC_MAX_WORKERS", "0"))
    except ValueError:
        logger.warning("FORENSIC_MAX_WORKERS is not numeric; falling back to auto")
        _env_max = 0
    max_workers = _env_max if _env_max > 0 else min(4, os.cpu_count() or 2)
    app.state.process_pool = concurrent.futures.ProcessPoolExecutor(max_workers=max_workers)
    app.state.process_pool_semaphore = asyncio.Semaphore(max_workers * 4)
    logger.info(
        "Forensic ProcessPool initialized", max_workers=max_workers, queue_cap=max_workers * 4
    )

    # ── Production validation ────────────────────────────────────────────────
    try:
        validate_production_settings()
    except ValueError as e:
        logger.error("Production validation failed", error=str(e))
        raise

    _dev_markers = ("dev-", "development-", "change", "placeholder", "replace")
    if any(settings.signing_key.lower().startswith(m) for m in _dev_markers):
        logger.warning(
            "SIGNING_KEY appears to be a development placeholder. "
            "Run infra/generate_production_keys.sh before production."
        )

    if settings.enable_research_models and settings.app_env == "production":
        logger.error(
            "CRITICAL: RESEARCH_MODELS enabled in production. These models (BusterNet, F3-Net, "
            "ManTra-Net, TruFor, clovaai/AASIST) are strictly non-commercial. "
            "Refusing to start in production to prevent licensing violations. "
            "Set ENABLE_RESEARCH_MODELS=false in production."
        )
        raise RuntimeError("Research models enabled in production")

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

    demo_password = os.getenv("DEMO_PASSWORD", "")
    if demo_password and demo_password != settings.bootstrap_investigator_password:
        msg = (
            "DEMO_PASSWORD != BOOTSTRAP_INVESTIGATOR_PASSWORD — "
            "/api/auth/demo login will fail. Ensure both values match in .env."
        )
        if settings.app_env == "development":
            raise RuntimeError(msg)
        else:
            logger.warning(msg)

    if settings.gemini_api_key and not settings.gemini_api_key_policy_ok:
        logger.warning(
            "GEMINI_API_KEY is set but GEMINI_API_KEY_POLICY_OK is not true. "
            "Gemini API calls will be disabled. Set GEMINI_API_KEY_POLICY_OK=true "
            "after reviewing the terms at https://ai.google.dev/terms"
        )

    # ── MIME detection check ─────────────────────────────────────────────────
    try:
        try:
            import magic
        except ImportError:
            from core import magic_fallback as magic

        await asyncio.to_thread(magic.from_buffer, b"\x89PNG\r\n\x1a\n", mime=True)
        logger.info("MIME detection dependency (libmagic) verified")
    except Exception as _mime_err:
        logger.error(
            "libmagic MIME detection check failed — file uploads may 503. "
            "Ensure libmagic is installed (e.g., apt install libmagic1).",
            error=str(_mime_err),
        )

    # ── Monitoring ───────────────────────────────────────────────────────────
    await start_monitoring(app.state)
    if not getattr(app.state, "heartbeat_monitor", None):
        logger.warning(
            "heartbeat_monitor was not set by start_monitoring — event loop "
            "stall detection is disabled for this run."
        )
    logger.info("Starting Forensic Council API server...", debug=settings.debug)

    # ── Worker heartbeat check ───────────────────────────────────────────────
    if settings.use_redis_worker:
        logger.info("Worker queue mode enabled — ensure worker.py is running")
        try:
            from core.persistence.redis_client import get_redis_client as _grc
            rc = await _grc()
            alive = await rc.get("forensic:worker:heartbeat")
            if not alive:
                logger.warning(
                    "Worker heartbeat missing (forensic:worker:heartbeat) — "
                    "investigations will queue but not execute. "
                    "Start the worker container: docker compose up worker"
                )
        except Exception as e:
            logger.warning("Worker heartbeat check failed", error=str(e))
    else:
        logger.info("In-process investigation mode — investigations run in this process")

    # ── System dependency validation ─────────────────────────────────────────
    REQUIRED_BINARIES = ["tesseract", "exiftool", "ffmpeg", "mediainfo"]
    missing_bins = [b for b in REQUIRED_BINARIES if not shutil.which(b)]
    if missing_bins:
        msg = f"CRITICAL: Missing system dependencies: {', '.join(missing_bins)}"
        if settings.app_env == "production":
            logger.error(msg)
            raise RuntimeError(msg)
        else:
            logger.warning(f"{msg} — Some forensic tools will fail.")

    # ── Database migrations ──────────────────────────────────────────────────
    app.state.migrations_ok = False
    try:
        pg = await get_postgres_client()
        table_exists = await pg.fetch_val(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN ('chain_of_custody', 'custody_log')
            )
            """
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

    # ── Bootstrap users ──────────────────────────────────────────────────────
    try:
        from scripts.init_db import bootstrap_users
        pg = await get_postgres_client()
        await bootstrap_users(pg)
        logger.info("User bootstrap completed")
    except Exception as e:
        logger.warning("User bootstrap skipped or failed", error=str(e))

    # ── Signing keys ─────────────────────────────────────────────────────────
    try:
        from core.signing import get_keystore
        ks = get_keystore()
        await ks.initialize()
        logger.info("Signing key store initialized")
    except Exception as e:
        if settings.app_env == "production":
            logger.error("CRITICAL: Failed to initialize key store in production. Aborting startup.", error=str(e))
            raise RuntimeError(f"Key store initialization failed: {e}") from e
        logger.warning("Key store initialization used deterministic fallback", error=str(e))

    # ── Gemini / provider setup ──────────────────────────────────────────────
    try:
        from core.provider_quota_guard import configure_provider_quota_guards
        configure_provider_quota_guards(settings)
        if settings.free_tier_mode:
            pass

        try:
            from core.pdf_report_exporter import probe_pdf_libs
            pdf_available = probe_pdf_libs()
            logger.info("PDF export library availability", **pdf_available)
        except Exception as pdf_err:
            logger.warning("Failed to probe PDF export library availability", error=str(pdf_err))

        from core.gemini_client import GeminiVisionClient
        GeminiVisionClient.configure_quota_pool(settings.gemini_max_concurrent)
        logger.info(
            "Skipping Gemini startup model validation; Gemini is reserved for the single Agent 1 visual probe"
        )
    except Exception as e:
        logger.warning("Gemini model validation skipped", error=str(e))

    # ── Crash-recovery: orphaned sessions ────────────────────────────────────
    try:
        from api.routes._session_state import SESSION_METADATA_KEY_PREFIX

        _redis = await get_redis_client()
        _interrupted_count = 0
        async for _key in _redis.scan_iter(
            match=f"{SESSION_METADATA_KEY_PREFIX}*", count=200,
        ):
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

    # ── LLM provider health summary ──────────────────────────────────────────
    llm_provider = settings.llm_provider
    llm_key_ok = bool(settings.llm_api_key)
    gemini_key_ok = settings.gemini_available
    arbiter_provider = settings.arbiter_llm_provider
    arbiter_key_ok = bool(settings.arbiter_llm_api_key or settings.llm_api_key)

    _llm_info = {
        "agent_llm": {"provider": llm_provider, "key_configured": llm_key_ok},
        "gemini_vision": {"available": gemini_key_ok},
        "arbiter": {"provider": arbiter_provider, "key_available": arbiter_key_ok},
    }
    if llm_provider == "none":
        logger.info("LLM provider: none — agent synthesis disabled (template fallback only)")
    elif not llm_key_ok:
        logger.warning(
            "LLM provider set to '%s' but no API key configured — synthesis will fall back to templates",
            llm_provider,
        )
    if not gemini_key_ok:
        logger.info(
            "Gemini Vision not configured — deep-phase vision analysis unavailable. "
            "Set GEMINI_API_KEY for multi-modal deep analysis."
        )
    logger.debug("LLM provider health", info=_llm_info)

    try:
        from core.auth import start_blacklist_cleanup_task
        start_blacklist_cleanup_task()
    except Exception as e:
        logger.warning("Blacklist cleanup task failed to start", error=str(e))

    yield

    # ══════════════════════════════════════════════════════════════════════════
    # Graceful shutdown
    # ══════════════════════════════════════════════════════════════════════════
    logger.info("Initiating graceful shutdown...")

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

    try:
        pool = getattr(app.state, "process_pool", None)
        if pool:
            pool.shutdown(wait=False)
            logger.info("Forensic ProcessPool shutdown initiated")
    except Exception as e:
        logger.warning("Failed to shutdown process pool", error=str(e))

    app.state.accepting_requests = False

    _shutdown_cap = int(os.environ.get("GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS", "120"))
    GRACEFUL_SHUTDOWN_TIMEOUT = min(
        settings.investigation_timeout + 30, _shutdown_cap
    )
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
                from core.session_persistence import get_session_persistence
                try:
                    await get_session_persistence()
                    for task in pending:
                        try:
                            if hasattr(task, "get_name"):
                                task_name = task.get_name()
                                logger.info("Checkpointing investigation", task_name=task_name)
                            task.cancel()
                        except Exception as e:
                            logger.error("Failed to checkpoint investigation", error=str(e))
                except Exception as e:
                    logger.error("Failed to get persistence layer", error=str(e))
    except Exception as e:
        logger.warning(f"Graceful wait failed: {e}")

    try:
        from api.routes.investigation import _deferred_cleanup_tasks
        pending_cleanups = [t for t in list(_deferred_cleanup_tasks) if not t.done()]
        if pending_cleanups:
            logger.info("Awaiting deferred cleanup tasks", count=len(pending_cleanups))
            await asyncio.gather(*pending_cleanups, return_exceptions=True)
    except Exception as e:
        logger.warning("Deferred cleanup drain failed", error=str(e))

    try:
        from api.routes.investigation import cleanup_connections
        await cleanup_connections()
        logger.info("Pipeline connections cleaned up")
    except Exception as e:
        logger.warning("Pipeline cleanup failed", error=str(e))

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
