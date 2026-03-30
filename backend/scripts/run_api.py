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

# Compatibility shim: bcrypt 4.x removed __about__; passlib 1.7.4 expects it.
# Suppresses the "(trapped) error reading bcrypt version" warning at startup.
try:
    import bcrypt as _bcrypt
    if not hasattr(_bcrypt, "__about__"):
        import types as _types
        _bcrypt.__about__ = _types.SimpleNamespace(__version__=_bcrypt.__version__)
except ImportError:
    pass

import uvicorn

if __name__ == "__main__":
    from core.config import get_settings

    settings = get_settings()

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
