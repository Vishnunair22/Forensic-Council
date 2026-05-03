"""
Run API Server Script
=====================

Starts the FastAPI server with uvicorn.
"""

import os
import sys
from pathlib import Path

# Ensure project root is on the path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

# Apply bcrypt compatibility shim before any passlib usage
from core._bcrypt_shim import ensure_bcrypt_compat  # noqa: E402

ensure_bcrypt_compat()

import uvicorn  # noqa: E402

from core.structured_logging import configure_root_logger  # noqa: E402

if __name__ == "__main__":
    from core.config import get_settings

    try:
        settings = get_settings()
    except Exception as exc:
        print(
            "\nForensic Council API configuration is invalid.\n"
            f"{type(exc).__name__}: {exc}\n\n"
            "Check .env for required values such as JWT_SECRET_KEY, SIGNING_KEY, "
            "database credentials, and API keys. Use .env.example as the template.\n",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc

    configure_root_logger(settings.log_level)

    is_production = settings.app_env == "production"
    reload_enabled = os.getenv("RELOAD", "false").lower() == "true"

    uvicorn.run(
        "api.main:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=reload_enabled and not is_production,
        log_level=settings.log_level.lower(),
        # In production: multiple workers are handled externally (e.g. gunicorn/k8s).
        # Single-worker uvicorn is correct here because the pipeline uses in-process
        # asyncio state (_active_pipelines, WebSocket registries) that cannot be
        # shared across OS processes without a distributed store.
        workers=1,
        # Keep-alive timeout: 65 s is recommended behind most load balancers.
        timeout_keep_alive=65,
        # Disable the access log in production (structured request logging is
        # handled by the correlation-ID middleware instead).
        access_log=not is_production,
    )
