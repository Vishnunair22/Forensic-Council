#!/bin/sh
# ============================================================================
# Forensic Council — Docker Entrypoint
# ============================================================================
# Runs at container startup BEFORE the API server.
# 1. Fixes permissions on runtime-mounted volumes (they are created root:root
#    by Docker on first use; chown ensures appuser can write to them)
# 2. Validates ML model cache state (fast filesystem check, ~1s)
# 3. Verifies core Python imports (confirms venv is intact, ~2s)
# 4. Starts the API server
#
# To skip the cache check (e.g. in CI):
#   docker run ... -e SKIP_CACHE_CHECK=1 ...
# ============================================================================
set -e

# Fix ownership of volume-mounted directories.
# Docker named volumes are always created as root:root on first use; chown
# ensures appuser (uid 1001) can write to them on every container start.
# This runs as root (no USER directive in Dockerfile) then drops privileges below.
chown -R 1001:1001 /app/storage/evidence /app/cache 2>/dev/null || true

# Check if appuser exists (it is only created in the production stage).
# In development mode the container runs from the 'development' stage which
# inherits from 'base' — appuser is never added there, so runuser would fail.
if id appuser >/dev/null 2>&1; then
    RUN_AS="runuser -u appuser --"
else
    # Dev mode: appuser doesn't exist, run as current user (typically root in dev)
    RUN_AS=""
fi

if [ "${SKIP_CACHE_CHECK:-0}" != "1" ]; then
    $RUN_AS python scripts/model_cache_check.py
fi

# Start the API server (drops to appuser in production, runs directly in dev)
exec $RUN_AS python scripts/run_api.py
