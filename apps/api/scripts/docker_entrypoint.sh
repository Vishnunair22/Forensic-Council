#!/bin/sh
# ============================================================================
# Forensic Council - Docker Entrypoint
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
export HOME="${HOME:-/tmp}"

EXPECTED_PROJECT="forensic-council"
if [ -n "${COMPOSE_PROJECT_NAME:-}" ] && [ "$COMPOSE_PROJECT_NAME" != "$EXPECTED_PROJECT" ]; then
    echo "  WARN: COMPOSE_PROJECT_NAME=$COMPOSE_PROJECT_NAME — model volumes will not be shared with the default 'forensic-council' project."
fi

echo "Starting Forensic Council entrypoint as user: $(id -u)"

# Mounted Docker volumes may be created as root on first use.  The production
# image starts as root only for this short permission repair step, then drops to
# appuser before running the API or worker.
if [ "$(id -u)" = "0" ]; then
    for WRITABLE_DIR in \
        /app/storage/evidence \
        /app/storage/keys \
        /app/storage/calibration_models \
        /app/cache/huggingface \
        /app/cache/torch \
        /app/cache/numba_cache \
        /app/cache/ultralytics \
        /app/cache/easyocr
    do
        mkdir -p "$WRITABLE_DIR" 2>/dev/null || true
        if ! runuser -u appuser -- test -w "$WRITABLE_DIR" 2>/dev/null; then
            echo "  Repairing write permissions for $WRITABLE_DIR"
            chown -R appuser:appgroup "$WRITABLE_DIR" 2>/dev/null || true
        fi
    done
fi

# ------ 1a. Seed calibration models into volume on first start ---------------------------------------------------------
# Calibration model JSON files are baked into the image at /app/storage/calibration_models.
# CALIBRATION_MODELS_PATH points to /app/cache/calibration_models (a named Docker volume)
# so models can be updated at runtime without rebuilding the image.
# On first start the volume is empty - copy the baked-in models in so agents find them.
CAL_SRC="${FORENSIC_MODEL_SEED_DIR:-/opt/forensic-model-cache}/calibration_models"
CAL_DST="${CALIBRATION_MODELS_PATH:-/app/cache/calibration_models}"
if [ -d "$CAL_SRC" ] && [ -d "$CAL_DST" ]; then
    CAL_COUNT=$(find "$CAL_DST" -type f -name "*.json" 2>/dev/null | wc -l | tr -d ' ' || echo 0)
    if [ "${CAL_COUNT:-0}" -lt 1 ]; then
        echo "  Seeding calibration models into volume: $CAL_SRC -> $CAL_DST"
        cp -r "$CAL_SRC/." "$CAL_DST/" 2>/dev/null || true
        if [ "$(id -u)" = "0" ]; then
            chown -R appuser:appgroup "$CAL_DST" 2>/dev/null || true
        fi
        echo "  Calibration model seed complete."
    fi
fi

CAL_FINAL=$(find "$CAL_DST" -type f -name "*.json" 2>/dev/null | wc -l | tr -d ' ' || echo 0)
if [ "${CAL_FINAL:-0}" -lt 1 ]; then
    echo "  WARNING: Calibration models volume is EMPTY after seed step."
    echo "  Forensic probabilities will fall back to identity calibration."
fi

# ------ 1b. Seed build-time ML model cache into mounted volumes ---------------------------------------------------------
# Docker builds bake model assets into /opt/forensic-model-cache. Runtime named
# volumes shadow /app/cache/*, so first startup must copy the baked seed into
# the volumes before agents run. This avoids first-analysis lazy downloads.
MODEL_SEED_DIR="${FORENSIC_MODEL_SEED_DIR:-/opt/forensic-model-cache}"

seed_cache_dir() {
    SRC="$1"
    DST="$2"
    MIN_FILES="$3"
    LABEL="$4"

    if [ ! -d "$SRC" ] || [ ! -d "$DST" ]; then
        return 0
    fi

    DST_COUNT=$(find "$DST" -type f 2>/dev/null | wc -l | tr -d ' ' || echo 0)
    SRC_COUNT=$(find "$SRC" -type f 2>/dev/null | wc -l | tr -d ' ' || echo 0)

    if [ "${DST_COUNT:-0}" -lt "$SRC_COUNT" ] && [ "${SRC_COUNT:-0}" -ge "$MIN_FILES" ]; then
        echo "  Seeding $LABEL cache into volume: $SRC -> $DST"
        cp -a "$SRC/." "$DST/" 2>/dev/null || true
        if [ "$(id -u)" = "0" ]; then
            chown -R appuser:appgroup "$DST" 2>/dev/null || true
        fi
    fi
}

seed_cache_dir "$MODEL_SEED_DIR/huggingface" "${HF_HOME:-/app/cache/huggingface}" 3 "HuggingFace"
seed_cache_dir "$MODEL_SEED_DIR/torch" "${TORCH_HOME:-/app/cache/torch}" 1 "PyTorch"
seed_cache_dir "$MODEL_SEED_DIR/easyocr" "${EASYOCR_MODEL_DIR:-/app/cache/easyocr}" 2 "EasyOCR"
seed_cache_dir "$MODEL_SEED_DIR/ultralytics" "${YOLO_CONFIG_DIR:-/app/cache/ultralytics}" 1 "YOLO"

# ------ 1c. First-run ML model pre-download fallback ---------------------------------------------------------------------------
# If the baked seed is missing or incomplete, download synchronously before the
# API/worker starts. This is a fail-fast safety net; normal builds should have
# already populated the seed cache.
if [ "${SKIP_MODEL_DOWNLOAD:-0}" != "1" ]; then
    HF_DIR="${HF_HOME:-/app/cache/huggingface}"
    YOLO_DIR="${YOLO_CONFIG_DIR:-/app/cache/ultralytics}"
    TORCH_DIR="${TORCH_HOME:-/app/cache/torch}"
    EASYOCR_DIR="${EASYOCR_MODEL_DIR:-/app/cache/easyocr}"

    # More robust cache detection:
    # For HuggingFace - check for model hub directories (not just individual files)
    # Valid models create hub/models--* directories with blobs/ subdirectories
    HF_HUBS=$(find "$HF_DIR/hub" "$HF_DIR/transformers" -type d -name "models--*" 2>/dev/null | wc -l | tr -d ' ' || echo 0)
    HF_BLOBS=$(find "$HF_DIR/hub" "$HF_DIR/transformers" -type d -name "blobs" 2>/dev/null | wc -l | tr -d ' ' || echo 0)
    
    # For YOLO - check for actual .pt weight files (not config/settings.json)
    YOLO_WEIGHTS=$(find "$YOLO_DIR" -maxdepth 1 -type f -name "*.pt" 2>/dev/null | wc -l | tr -d ' ' || echo 0)
    TORCH_WEIGHTS=$(find "$TORCH_DIR" -type f \( -name "*.pth" -o -name "*.pt" \) 2>/dev/null | wc -l | tr -d ' ' || echo 0)
    EASYOCR_FILES=$(find "$EASYOCR_DIR" -type f 2>/dev/null | wc -l | tr -d ' ' || echo 0)

    AASIST_SAFE_NAME=$(printf '%s' "${AASIST_MODEL_NAME:-Vansh180/deepfake-audio-wav2vec2}" | sed 's#/#--#g')
    CLIP_READY=$(find "$HF_DIR/hub/models--timm--vit_base_patch32_clip_224.openai/blobs" -type f -size +100M 2>/dev/null | wc -l | tr -d ' ' || echo 0)
    ECAPA_READY=$(find "$HF_DIR/hub/models--speechbrain--spkrec-ecapa-voxceleb/blobs" -type f -size +1M 2>/dev/null | wc -l | tr -d ' ' || echo 0)
    AASIST_READY=$(find "$HF_DIR/hub/models--$AASIST_SAFE_NAME/blobs" "$HF_DIR/transformers/models--$AASIST_SAFE_NAME/blobs" -type f -size +1M 2>/dev/null | wc -l | tr -d ' ' || echo 0)

    # Need exact HF model families (OpenCLIP + SpeechBrain ECAPA + audio deepfake detector), YOLO,
    # torchvision ResNet, and EasyOCR. Count checks alone can pass with the wrong
    # cached model, so keep both exact and aggregate checks.
    if [ "${HF_HUBS:-0}" -lt 3 ] || [ "${HF_BLOBS:-0}" -lt 3 ] || [ "${CLIP_READY:-0}" -lt 1 ] || [ "${ECAPA_READY:-0}" -lt 1 ] || [ "${AASIST_READY:-0}" -lt 1 ] || [ "${YOLO_WEIGHTS:-0}" -lt 1 ] || [ "${TORCH_WEIGHTS:-0}" -lt 1 ] || [ "${EASYOCR_FILES:-0}" -lt 2 ]; then
        echo ""
        echo "============================================================"
        echo "  ML cache incomplete - downloading models before startup"
        echo "  Normal Docker builds should bake these into the image."
        echo "  This fallback runs once per empty volume."
        echo "============================================================"
        if [ "$(id -u)" = "0" ]; then
            runuser -u appuser -- python probes/model_pre_download.py --strict > /tmp/model_download.log 2>&1
        else
            python probes/model_pre_download.py --strict > /tmp/model_download.log 2>&1
        fi
        echo "  Model download complete. Log: /tmp/model_download.log"
    else
        echo "  ML model volumes already populated - skipping download."
        echo "  Found: $HF_HUBS model hubs, $HF_BLOBS blob dirs, OpenCLIP=$CLIP_READY, ECAPA=$ECAPA_READY, AASIST=$AASIST_READY, $YOLO_WEIGHTS YOLO weights, $TORCH_WEIGHTS Torch weights, $EASYOCR_FILES EasyOCR files"
    fi
fi

# ------ 2. Cache status check + Python import verification ---------------------------------------------------------------------
if [ "${SKIP_CACHE_CHECK:-0}" != "1" ]; then
    echo "  Verifying model cache and imports..."
    if [ "$(id -u)" = "0" ]; then
        runuser -u appuser -- python probes/model_cache_check.py
    else
        python probes/model_cache_check.py
    fi
fi

# ------ 3. Start process (API by default, or Worker via CMD) ------------------------------------------------------------------
# Default to scripts/run_api.py if no arguments provided
CMD_TO_RUN="${1:-scripts/run_api.py}"

if [ "$CMD_TO_RUN" = "worker" ]; then
    echo "  Mode: Forensic Worker - consuming tasks from Redis"
    if [ "$(id -u)" = "0" ]; then
        exec runuser -u appuser -- python scripts/run_worker.py
    fi
    exec python scripts/run_worker.py
else
    echo "  Mode: Custom Script / API - serving requests"
    # Decide if we need to wrap $CMD_TO_RUN in python
    case "$CMD_TO_RUN" in
        *.py) ACTUAL_CMD="python $CMD_TO_RUN" ;;
        *)    ACTUAL_CMD="$CMD_TO_RUN" ;;
    esac

    echo "  Executing: $ACTUAL_CMD"
    # Use 'sh -c' to correctly word-split the command string into binary + args.
    # Direct 'exec "$ACTUAL_CMD"' would treat the whole string as the binary name.
    if [ "$(id -u)" = "0" ]; then
        exec runuser -u appuser -- env HOME=/tmp sh -c "$ACTUAL_CMD"
    fi
    exec sh -c "$ACTUAL_CMD"
fi
