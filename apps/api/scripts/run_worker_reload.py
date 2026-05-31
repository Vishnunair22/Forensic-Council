"""
Forensic Council — Worker Entrypoint with Auto-Reload
=====================================================

Watches source files for changes and restarts the worker process.
Used in development mode when RELOAD=true.
"""

import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core._bcrypt_shim import ensure_bcrypt_compat  # noqa: E402

ensure_bcrypt_compat()


def _run_worker():
    import asyncio
    from core.config import get_settings
    from core.structured_logging import configure_root_logger, get_logger
    from orchestration.worker import main

    settings = get_settings()
    configure_root_logger(settings.log_level)
    logger = get_logger("run_worker_reload")
    logger.info("Starting Forensic Council Background Worker (with auto-reload)...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user.")
    except Exception as e:
        logger.critical(f"Worker failed with unhandled exception: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    reload_enabled = os.environ.get("RELOAD", "false").lower() in ("true", "1", "yes")

    if reload_enabled:
        try:
            from watchfiles import run

            # Watch these directories for .py changes
            watch_dirs = [
                os.path.join(os.path.dirname(__file__), "..", "core"),
                os.path.join(os.path.dirname(__file__), "..", "agents"),
                os.path.join(os.path.dirname(__file__), "..", "orchestration"),
                os.path.join(os.path.dirname(__file__), "..", "tools"),
                os.path.join(os.path.dirname(__file__), "..", "api"),
            ]
            watch_paths = [os.path.abspath(d) for d in watch_dirs if os.path.isdir(d)]

            print(f"[worker-reload] Watching {len(watch_paths)} directories for changes...")
            for p in watch_paths:
                print(f"  - {p}")

            run(
                _run_worker,
                *watch_paths,
                watch_filter=lambda change, path: path.endswith(".py"),
                debug=False,
            )
        except ImportError:
            print("[worker-reload] watchfiles not installed — falling back to no-reload mode")
            _run_worker()
    else:
        _run_worker()
