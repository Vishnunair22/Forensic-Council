# syntax=docker/dockerfile:1.7
# ─── Backend — Optimised Multi-Stage Build ────────────────────────────────────
# Requires BuildKit (enabled by default in Docker 23+ and Docker Desktop).
# Manual override: DOCKER_BUILDKIT=1 docker compose build
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

# 1. System deps — cached aggressively via BuildKit cache mount
#    Layer is reused on rebuild unless apt package list changes.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        curl \
        tesseract-ocr \
        tesseract-ocr-eng \
        exiftool \
        libgl1 \
        libglib2.0-0 \
        gcc \
        libmediainfo-dev \
        libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# 2. Install latest uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /uvx /bin/

WORKDIR /app

# ─── Dependency layer ─────────────────────────────────────────────────────────
# Copy ONLY the lock files first so this expensive layer is cache-valid
# whenever pyproject.toml and uv.lock are unchanged (i.e. every code-only change).
COPY pyproject.toml uv.lock ./

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=600

# BuildKit cache mount preserves uv's HTTP cache between rebuilds.
# Result: packages are downloaded ONCE and reused even across `docker build`.
# This is the primary fix for slow builds.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra ml

# 3. Remove compiler toolchain after install (shrinks final image ~60 MB)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get purge -y gcc && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# ─── Application layer ────────────────────────────────────────────────────────
# Source code is copied AFTER deps — code changes don't invalidate the dep layer.
COPY . .

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 4. ML model cache dirs — mapped to named Docker volumes in docker-compose.
#    Models download ONCE into the volume on first run; they persist across:
#      - Container restarts
#      - Image rebuilds  (volume is separate from the image)
#    They are ONLY re-downloaded if you explicitly run: docker volume rm <vol>
ENV NUMBA_CACHE_DIR="/app/cache/numba_cache" \
    YOLO_CONFIG_DIR="/app/cache/ultralytics" \
    TORCH_HOME="/app/cache/torch" \
    HF_HOME="/app/cache/huggingface" \
    DEEPFACE_HOME="/app/cache/deepface" \
    TRANSFORMERS_CACHE="/app/cache/huggingface/transformers" \
    EASYOCR_MODEL_DIR="/app/cache/easyocr"

RUN mkdir -p \
    /app/storage/evidence \
    /app/storage/keys \
    /app/cache/huggingface \
    /app/cache/torch \
    /app/cache/numba_cache \
    /app/cache/ultralytics \
    /app/cache/deepface \
    /app/cache/calibration_models \
    /app/cache/easyocr

# 5. Pre-compile application bytecode for faster cold starts
RUN python -m compileall -q api/ core/ orchestration/ agents/ tools/ scripts/ 2>/dev/null || true

# 6. Make entrypoint executable
RUN chmod +x scripts/docker_entrypoint.sh

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD curl -f -s http://localhost:8000/health || exit 1

EXPOSE 8000

# Entrypoint runs model_cache_check.py then exec's the API server.
# Set SKIP_CACHE_CHECK=1 to bypass the check (useful in CI/CD pipelines).
CMD ["sh", "scripts/docker_entrypoint.sh"]
