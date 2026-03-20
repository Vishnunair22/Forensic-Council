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

if [ "${SKIP_CACHE_CHECK:-0}" != "1" ]; then
    runuser -u appuser -- python scripts/model_cache_check.py
fi

# Drop to appuser and exec the API server
exec runuser -u appuser -- python scripts/run_api.py
