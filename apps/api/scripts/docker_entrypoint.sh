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
unset TRANSFORMERS_CACHE

# ── Guard: fail fast if required vars are missing or still placeholders ──────
REQUIRED_VARS="SIGNING_KEY JWT_SECRET_KEY"
if [ "${1:-}" != "worker" ]; then
  REQUIRED_VARS="$REQUIRED_VARS BOOTSTRAP_INVESTIGATOR_PASSWORD BOOTSTRAP_ADMIN_PASSWORD"
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
# Calibration model JSON files are generated at runtime by the forensic agents.
# CALIBRATION_MODELS_PATH points to /app/cache/calibration_models (a named Docker volume).
# On first start the volume is empty — this is expected and agents will generate models
# on first analysis run and write them to the volume for subsequent runs.
# If /app/storage/calibration_models contains pre-seeded JSON files (baked into image),
# copy them into the volume now.
CAL_SRC="${FORENSIC_MODEL_SEED_DIR:-/opt/forensic-model-cache}/calibration_models"
CAL_APP_SRC="/app/storage/calibration_models"
CAL_DST="${CALIBRATION_MODELS_PATH:-/app/cache/calibration_models}"

# Try the primary seed dir, then fall back to the app storage dir
_seed_calibration() {
    SRC="$1"
    SRC_JSONS=$(find "$SRC" -type f -name "*.json" 2>/dev/null | wc -l | tr -d ' ' || echo 0)
    if [ "${SRC_JSONS:-0}" -ge 1 ]; then
        echo "  Seeding calibration models into volume: $SRC -> $CAL_DST"
        cp -r "$SRC/." "$CAL_DST/" 2>/dev/null || true
        if [ "$(id -u)" = "0" ]; then
            chown -R appuser:appgroup "$CAL_DST" 2>/dev/null || true
        fi
        echo "  Calibration model seed complete ($SRC_JSONS model files)."
        return 0
    fi
    return 1
}

if [ -d "$CAL_DST" ]; then
    CAL_COUNT=$(find "$CAL_DST" -type f -name "*.json" 2>/dev/null | wc -l | tr -d ' ' || echo 0)
    if [ "${CAL_COUNT:-0}" -lt 1 ]; then
        # Try primary seed dir first, then app storage fallback
        _seed_calibration "$CAL_SRC" || _seed_calibration "$CAL_APP_SRC" || true
    fi
fi

CAL_FINAL=$(find "$CAL_DST" -type f -name "*.json" 2>/dev/null | wc -l | tr -d ' ' || echo 0)
if [ "${CAL_FINAL:-0}" -lt 1 ]; then
    # First-boot: calibration models are runtime-generated, this is expected on a fresh volume.
    echo "  INFO: Calibration volume empty on startup (expected on first run)."
    echo "  Agents will use identity calibration until models are generated after first analysis."
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
    # OpenCLIP (ViT-B-32 default) stores weights under $HF_HOME/open_clip/ as flat files,
    # not under a hub/models--* slug. Check only that directory.
    CLIP_READY=$(find "$HF_DIR/open_clip" -type f -size +100M 2>/dev/null | wc -l | tr -d ' ' || echo 0)
    ECAPA_READY=$(find -L "$HF_DIR/hub/models--speechbrain--spkrec-ecapa-voxceleb" -type f \( -name "*.ckpt" -o -name "embedding_model.ckpt" -o -name "*.yaml" \) -size +5k 2>/dev/null | wc -l | tr -d ' ' || echo 0)
    AASIST_READY=$(find "$HF_DIR/hub/models--$AASIST_SAFE_NAME/blobs" "$HF_DIR/transformers/models--$AASIST_SAFE_NAME/blobs" -type f -size +1M 2>/dev/null | wc -l | tr -d ' ' || echo 0)
    AI_GEN_SAFE_NAME=$(printf '%s' "${AI_IMAGE_DETECTOR_MODEL:-Organika/sdxl-detector}" | sed 's#/#--#g')
    AI_GEN_READY=$(find "$HF_DIR/hub/models--$AI_GEN_SAFE_NAME/blobs" "$HF_DIR/transformers/models--$AI_GEN_SAFE_NAME/blobs" -type f -size +1M 2>/dev/null | wc -l | tr -d ' ' || echo 0)

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
    AI_GEN_OK=0;[ "${AI_GEN_READY:-0}"          -ge 1 ] && AI_GEN_OK=1

    # Decide whether the seed cache is complete enough to skip the download
    # fallback. Audio models (ECAPA, AASIST) are only baked when
    # ENABLE_AUDIO_MODELS=true, so they are only required here when audio is
    # enabled — otherwise this gate would be permanently unsatisfiable and the
    # download fallback would re-run on every container start. The AI-generation
    # detector is optional (degrades to a spectral heuristic) so its absence
    # must not force a re-download attempt each boot.
    NEED_DOWNLOAD=0
    [ "$CLIP_OK"  -eq 0 ] && NEED_DOWNLOAD=1
    [ "$OBJ_OK"   -eq 0 ] && NEED_DOWNLOAD=1
    [ "$TORCH_OK" -eq 0 ] && NEED_DOWNLOAD=1
    [ "$OCR_OK"   -eq 0 ] && NEED_DOWNLOAD=1
    if [ "${ENABLE_AUDIO_MODELS:-false}" = "true" ]; then
        [ "$ECAPA_OK"  -eq 0 ] && NEED_DOWNLOAD=1
        [ "$AASIST_OK" -eq 0 ] && NEED_DOWNLOAD=1
    fi

    if [ "$NEED_DOWNLOAD" -eq 1 ]; then
        echo ""
        echo "============================================================"
        echo "  ML cache incomplete - downloading models before startup"
        echo "  Normal Docker builds should bake these into the image."
        echo "  This fallback runs once per empty volume."
        echo "============================================================"
        # chmod is best-effort: scripts/ is bind-mounted read-only in dev, and the
        # script is invoked via `sh` anyway, so a failed chmod must not be fatal.
        chmod +x scripts/model_download_with_retry.sh 2>/dev/null || true
        # Non-fatal at RUNTIME: a model download that fails after retries (e.g. a
        # transient Hugging Face / network outage) must NOT crash-loop the service.
        # The app starts and any missing-model tool degrades to an honest coverage
        # gap. (Build-time preload in the Dockerfile stays fail-fast so a broken
        # image is caught by the developer, not shipped.)
        DL_FAILED=0
        if [ "$(id -u)" = "0" ]; then
            runuser -u appuser -- sh scripts/model_download_with_retry.sh --strict || DL_FAILED=1
        else
            sh scripts/model_download_with_retry.sh --strict || DL_FAILED=1
        fi
        if [ "$DL_FAILED" = "1" ]; then
            echo "  WARNING: model pre-download incomplete - starting anyway; affected tools will report coverage gaps (not a crash)."
        else
            echo "  Model download complete."
        fi
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
    if [ "${RELOAD:-false}" = "true" ]; then
        echo "  Mode: Forensic Worker - consuming tasks from Redis (auto-reload enabled)"
        set -- python scripts/run_worker_reload.py
    else
        echo "  Mode: Forensic Worker - consuming tasks from Redis"
        set -- python scripts/run_worker.py
    fi
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
