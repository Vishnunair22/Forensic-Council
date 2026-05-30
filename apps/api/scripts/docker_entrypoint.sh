#!/bin/sh
# ============================================================================
# Forensic Council - Docker Entrypoint
#
# Runs at container startup BEFORE the API server.
# 1. Guard: fail fast if required env vars are missing or still placeholders
# 2. Permission repair: fix volume ownership if running as root
# 3. Seed calibration and ML model caches into mounted volumes on first start
# 4. Optionally download any missing models (fail-safe fallback)
# 5. Verify model cache and Python imports
# 6. Drop to appuser and exec the API server, worker, or custom command
#
# Environment overrides:
#   SKIP_MODEL_DOWNLOAD=1   Skip background model pre-download (e.g. CI/CD)
#   SKIP_CACHE_CHECK=1      Skip cache status + import check
# ============================================================================
set -e
export HOME="${HOME:-/tmp}"

# ── Guard: fail fast if required vars are missing or still placeholders ──────
REQUIRED_VARS="SIGNING_KEY JWT_SECRET_KEY"
if [ "${1:-}" != "worker" ]; then
  REQUIRED_VARS="$REQUIRED_VARS BOOTSTRAP_INVESTIGATOR_PASSWORD"
fi
if [ "${LLM_PROVIDER:-groq}" != "none" ]; then
  REQUIRED_VARS="$REQUIRED_VARS LLM_API_KEY"
fi

for VAR in $REQUIRED_VARS; do
  # Use eval to get variable value in POSIX sh (no ${!VAR} indirect expansion)
  VAL=$(eval "echo \"\$$VAR\"")
  case "$VAL" in
    ""|__REPLACE_ME*|__PASTE_*|*placeholder*|*Placeholder*|*PLACEHOLDER*|change-me|changeme|change_me)
      echo "FATAL: $VAR is missing or still a placeholder. Copy .env.example to .env and fill all values." >&2
      exit 1
      ;;
  esac
done

EXPECTED_PROJECT="forensic-council"
if [ -n "${COMPOSE_PROJECT_NAME:-}" ] && [ "$COMPOSE_PROJECT_NAME" != "$EXPECTED_PROJECT" ]; then
    echo "  WARN: COMPOSE_PROJECT_NAME=$COMPOSE_PROJECT_NAME - model volumes will not be shared with the default 'forensic-council' project."
fi

echo "Starting Forensic Council entrypoint as user: $(id -u)"

# Mounted Docker volumes may be created as root on first use.  The production
# image starts as root only for this short permission repair step, then drops to
# appuser before running the API or worker.
if [ "$(id -u)" = "0" ]; then
    for WRITABLE_DIR in \
        /app/storage/evidence \
        /app/storage/keys \
        /app/storage/backups \
        /app/storage/calibration_models \
        /app/cache/calibration_models \
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

    if [ "$(id -u)" != "0" ] && ! [ -w "$DST" ]; then
        echo "  WARN: cannot seed $LABEL — running as non-root and $DST not writable. Volume should already be populated by build-time bake."
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

    # For object detection, prefer Apache-licensed DETR unless AGPL YOLO is explicitly enabled.
    YOLO_WEIGHTS=$(find "$YOLO_DIR" -maxdepth 1 -type f -name "*.pt" 2>/dev/null | wc -l | tr -d ' ' || echo 0)
    DETR_READY=$(find "$HF_DIR/hub/models--facebook--detr-resnet-50/blobs" "$HF_DIR/transformers/models--facebook--detr-resnet-50/blobs" -type f -size +1M 2>/dev/null | wc -l | tr -d ' ' || echo 0)
    TORCH_WEIGHTS=$(find "$TORCH_DIR" -type f \( -name "*.pth" -o -name "*.pt" \) 2>/dev/null | wc -l | tr -d ' ' || echo 0)
    EASYOCR_FILES=$(find "$EASYOCR_DIR" -type f 2>/dev/null | wc -l | tr -d ' ' || echo 0)

    AASIST_SAFE_NAME=$(printf '%s' "${AASIST_MODEL_NAME:-Vansh180/deepfake-audio-wav2vec2}" | sed 's#/#--#g')
    CLIP_READY=$(find "$HF_DIR/open_clip" "$HF_DIR/hub/models--timm--vit_base_patch32_clip_224.openai/blobs" -type f -size +100M 2>/dev/null | wc -l | tr -d ' ' || echo 0)
    ECAPA_READY=$(find "$HF_DIR/hub/models--speechbrain--spkrec-ecapa-voxceleb" -type f \( -name "*.ckpt" -o -name "embedding_model.ckpt" -o -name "*.yaml" \) -size +5k 2>/dev/null | wc -l | tr -d ' ' || echo 0)
    AASIST_READY=$(find "$HF_DIR/hub/models--$AASIST_SAFE_NAME/blobs" "$HF_DIR/transformers/models--$AASIST_SAFE_NAME/blobs" -type f -size +1M 2>/dev/null | wc -l | tr -d ' ' || echo 0)

    OBJECT_MODEL="${YOLO_MODEL_NAME:-detr-resnet-50}"
    if printf '%s' "$OBJECT_MODEL" | grep -qi 'yolo' && [ "${ENABLE_AGPL_MODELS:-false}" = "true" ]; then
        OBJECT_DETECTOR_READY="${YOLO_WEIGHTS:-0}"
        OBJECT_DETECTOR_LABEL="YOLO weights"
    else
        OBJECT_DETECTOR_READY="${DETR_READY:-0}"
        OBJECT_DETECTOR_LABEL="DETR object detector"
    fi

    # Per-model presence map: each required model family must pass its own check.
    # Aggregate hub/blob counts are omitted — they can pass with the wrong cached
    # models and do not add safety beyond the per-model checks below.
    # Required set: OpenCLIP, SpeechBrain ECAPA, audio deepfake (AASIST),
    #               object detector (DETR default / YOLO with AGPL flag),
    #               torchvision ResNet, EasyOCR.
    CLIP_OK=0;  [ "${CLIP_READY:-0}"            -ge 1 ] && CLIP_OK=1
    ECAPA_OK=0; [ "${ECAPA_READY:-0}"           -ge 1 ] && ECAPA_OK=1
    AASIST_OK=0;[ "${AASIST_READY:-0}"          -ge 1 ] && AASIST_OK=1
    OBJ_OK=0;   [ "${OBJECT_DETECTOR_READY:-0}" -ge 1 ] && OBJ_OK=1
    TORCH_OK=0; [ "${TORCH_WEIGHTS:-0}"         -ge 1 ] && TORCH_OK=1
    OCR_OK=0;   [ "${EASYOCR_FILES:-0}"         -ge 2 ] && OCR_OK=1

    if [ "$CLIP_OK" -eq 0 ] || [ "$ECAPA_OK" -eq 0 ] || [ "$AASIST_OK" -eq 0 ] || [ "$OBJ_OK" -eq 0 ] || [ "$TORCH_OK" -eq 0 ] || [ "$OCR_OK" -eq 0 ]; then
        echo ""
        echo "============================================================"
        echo "  ML cache incomplete - downloading models before startup"
        echo "  Normal Docker builds should bake these into the image."
        echo "  This fallback runs once per empty volume."
        echo "============================================================"
        chmod +x scripts/model_download_with_retry.sh
        if [ "$(id -u)" = "0" ]; then
            runuser -u appuser -- sh scripts/model_download_with_retry.sh --strict
        else
            sh scripts/model_download_with_retry.sh --strict
        fi
        echo "  Model download complete."
    else
        echo "  ML model volumes already populated - skipping download."
        echo "  Found: OpenCLIP=$CLIP_READY ECAPA=$ECAPA_READY AASIST=$AASIST_READY $OBJECT_DETECTOR_LABEL=$OBJECT_DETECTOR_READY TorchWeights=$TORCH_WEIGHTS EasyOCR=$EASYOCR_FILES"
    fi
fi

# ------ 2. Cache status check + Python import verification ---------------------------------------------------------------------
if [ "${SKIP_CACHE_CHECK:-0}" != "1" ]; then
    echo "  Verifying model cache and imports..."
    if [ "$(id -u)" = "0" ]; then
        runuser -u appuser -- python scripts/model_cache_check.py
    else
        python scripts/model_cache_check.py
    fi
fi

# ------ 3. Start process (API by default, Worker via CMD, or custom command) ---------------------------------------------------
if [ "$#" -eq 0 ]; then
    set -- python scripts/run_api.py
elif [ "$1" = "worker" ]; then
    echo "  Mode: Forensic Worker - consuming tasks from Redis"
    set -- python scripts/run_worker.py
elif [ "${1#*.}" = "py" ]; then
    set -- python "$@"
else
    echo "  Mode: Custom command"
fi

echo "  Executing: $*"
if [ "$(id -u)" = "0" ]; then
    exec runuser -u appuser -- env HOME=/tmp "$@"
fi
exec "$@"
