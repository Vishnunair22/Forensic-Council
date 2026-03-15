#!/bin/sh
# ============================================================================
# Forensic Council — Docker Entrypoint
# ============================================================================
# Runs at container startup BEFORE the API server.
# 1. Validates ML model cache state (fast filesystem check, ~1s)
# 2. Verifies core Python imports (confirms venv is intact, ~2s)
# 3. Starts the API server
#
# To skip the cache check (e.g. in CI):
#   docker run ... -e SKIP_CACHE_CHECK=1 ...
# ============================================================================
set -e

if [ "${SKIP_CACHE_CHECK:-0}" != "1" ]; then
    echo "Running model cache check..."
    if ! python scripts/model_cache_check.py; then
        echo "WARNING: Model cache check failed. Some ML features may not work."
        # Don't exit - let the API start anyway
    fi
fi

# Execute the API server (replace this process — no subprocess overhead)
exec python scripts/run_api.py
