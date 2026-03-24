#!/bin/sh
# ============================================================================
# Forensic Council — Docker Entrypoint
# ============================================================================
# Runs at container startup BEFORE the API server.
# 1. Fixes permissions on runtime-mounted volumes (created root:root by Docker)
# 2. On FIRST ever start (volumes empty): pre-downloads ML models IN BACKGROUND
#    so the API starts immediately while models download concurrently.
# 3. Validates cache state and core Python imports (~3s)
# 4. Starts the API server
#
# Environment overrides:
#   SKIP_MODEL_DOWNLOAD=1   Skip background model pre-download (e.g. CI/CD)
#   SKIP_CACHE_CHECK=1      Skip cache status + import check
# ============================================================================
set -e

# ── 1. Fix ownership of volume-mounted directories ───────────────────────────
# Docker named volumes are always created as root:root on first use.
# chown ensures appuser (uid 1001) can write to them.
# This must run as root before we drop privileges below.
chown -R 1001:1001 /app/storage/evidence /app/cache 2>/dev/null || true

# ── Privilege-drop helper ────────────────────────────────────────────────────
# appuser exists only in the production stage. In the development stage the
# container inherits from 'base' where adduser was never called.
if id appuser >/dev/null 2>&1; then
    RUN_AS="runuser -u appuser --"
else
    RUN_AS=""
fi

# ── 2. First-run ML model pre-download (background) ─────────────────────────
# Check the HuggingFace and YOLO cache dirs. If they are empty this is the
# first time the container has started against these volumes.
# Download models in a background process so the API server starts immediately.
# On all subsequent starts the check completes in <1s (files already present).
if [ "${SKIP_MODEL_DOWNLOAD:-0}" != "1" ]; then
    HF_DIR="${HF_HOME:-/app/cache/huggingface}"
    YOLO_DIR="${YOLO_CONFIG_DIR:-/app/cache/ultralytics}"

    # HF: count actual model blob files (≥ 3 means OpenCLIP weights are present)
    HF_FILES=$(find "$HF_DIR" -type f -name "*.safetensors" -o -name "open_clip_model*" -o -name "*.bin" 2>/dev/null | wc -l || echo 0)
    # YOLO: look for actual model weight files (.pt), NOT settings.json
    YOLO_FILES=$(find "$YOLO_DIR" -type f -name "*.pt" 2>/dev/null | wc -l || echo 0)

    if [ "${HF_FILES:-0}" -lt 1 ] || [ "${YOLO_FILES:-0}" -lt 1 ]; then
        echo ""
        echo "============================================================"
        echo "  FIRST RUN — pre-downloading ML models into persistent volumes"
        echo "  This runs once; all future starts will be instant."
        echo "  API server will start in parallel and be ready in ~30s."
        echo "============================================================"
        # Run in background (&) so the API starts immediately
        $RUN_AS python scripts/model_pre_download.py > /tmp/model_download.log 2>&1 &
        MODEL_DL_PID=$!
        echo "  Model download started (PID $MODEL_DL_PID) — tail /tmp/model_download.log for progress"
    else
        echo "  ML model volumes already populated — skipping download."
    fi
fi

# ── 3. Cache status check + Python import verification ───────────────────────
if [ "${SKIP_CACHE_CHECK:-0}" != "1" ]; then
    $RUN_AS python scripts/model_cache_check.py
fi

# ── 4. Start the API server ──────────────────────────────────────────────────
exec $RUN_AS python scripts/run_api.py
