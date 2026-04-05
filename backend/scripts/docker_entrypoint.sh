#!/bin/sh
# ============================================================================
# Forensic Council — Docker Entrypoint
# ============================================================================
# Runs at container startup BEFORE the API server.
# 1. On FIRST ever start (volumes empty): pre-downloads ML models IN BACKGROUND
#    so the API starts immediately while models download concurrently.
# 2. Validates cache state and core Python imports (~3s)
# 3. Starts the API server / Worker / Script
#
# Environment overrides:
#   SKIP_MODEL_DOWNLOAD=1   Skip background model pre-download (e.g. CI/CD)
#   SKIP_CACHE_CHECK=1      Skip cache status + import check
# ============================================================================
set -e

# SECURITY: Ensure we're not running as root in production
if [ "$(id -u)" = "0" ] && [ "${APP_ENV:-development}" = "production" ]; then
    echo "WARNING: Running as root in production is not recommended" >&2
fi

echo "Starting Forensic Council entrypoint as user: $(id -u)"

# ── 1a. Seed calibration models into volume on first start ───────────────────
# Calibration model JSON files are baked into the image at /app/storage/calibration_models.
# CALIBRATION_MODELS_PATH points to /app/cache/calibration_models (a named Docker volume)
# so models can be updated at runtime without rebuilding the image.
# On first start the volume is empty — copy the baked-in models in so agents find them.
CAL_SRC="/app/storage/calibration_models"
CAL_DST="${CALIBRATION_MODELS_PATH:-/app/cache/calibration_models}"
if [ -d "$CAL_SRC" ] && [ -d "$CAL_DST" ]; then
    CAL_COUNT=$(find "$CAL_DST" -type f -name "*.json" 2>/dev/null | wc -l || echo 0)
    if [ "${CAL_COUNT:-0}" -lt 1 ]; then
        echo "  Seeding calibration models into volume: $CAL_SRC → $CAL_DST"
        cp -r "$CAL_SRC/." "$CAL_DST/" 2>/dev/null || true
        echo "  Calibration model seed complete."
    fi
fi

# ── 1b. First-run ML model pre-download (background) ─────────────────────────
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
        python scripts/model_pre_download.py > /tmp/model_download.log 2>&1 &
        MODEL_DL_PID=$!
        echo "  Model download started (PID $MODEL_DL_PID) — tail /tmp/model_download.log for progress"
    else
        echo "  ML model volumes already populated — skipping download."
    fi
fi

# ── 2. Cache status check + Python import verification ───────────────────────
if [ "${SKIP_CACHE_CHECK:-0}" != "1" ]; then
    echo "  Verifying model cache and imports..."
    python scripts/model_cache_check.py
fi

# ── 3. Start process (API by default, or Worker via CMD) ──────────────────────
# Default to scripts/run_api.py if no arguments provided
CMD_TO_RUN="${1:-scripts/run_api.py}"

if [ "$CMD_TO_RUN" = "worker" ]; then
    echo "  Mode: Forensic Worker — consuming tasks from Redis"
    exec python scripts/run_worker.py
else
    echo "  Mode: Custom Script / API — serving requests"
    # Decide if we need to wrap $CMD_TO_RUN in python
    case "$CMD_TO_RUN" in
        *.py) ACTUAL_CMD="python $CMD_TO_RUN" ;;
        *)    ACTUAL_CMD="$CMD_TO_RUN" ;;
    esac

    echo "  Executing: $ACTUAL_CMD"
    # Use 'sh -c' to correctly word-split the command string into binary + args.
    # Direct 'exec "$ACTUAL_CMD"' would treat the whole string as the binary name.
    exec sh -c "$ACTUAL_CMD"
fi
