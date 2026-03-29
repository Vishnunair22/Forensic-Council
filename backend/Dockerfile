# syntax=docker/dockerfile:1.7
# ─── Backend — Multi-Stage Build ──────────────────────────────────────────────
# Stages:
#   base        — system deps + uv + Python venv (shared by all stages)
#   development — hot-reload dev server  (used by: docker-compose.dev.yml)
#   production  — hardened, non-root, read-only container (default)
#
# Requires BuildKit (enabled by default in Docker 23+ and Docker Desktop).
# Manual override: DOCKER_BUILDKIT=1 docker compose build
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 0: Base — system deps + Python venv ────────────────────────────────
FROM python:3.12-slim AS base

# 1. System deps — cached aggressively via BuildKit cache mount
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

# 2. Install uv (fast Python package manager)
# Using pip install to avoid ghcr.io TLS issues on restricted networks
RUN pip install --no-cache-dir uv

WORKDIR /app

# ─── Dependency layer ──────────────────────────────────────────────────────────
# uv.lock is committed to the repo and guarantees reproducible builds.
# Copying both files here means code-only changes do not invalidate this layer.
COPY pyproject.toml uv.lock ./

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=600 \
    # Keep the uv cache inside the BuildKit cache mount, not the container layer.
    # Also required at build time because /root is read-only when read_only: true.
    UV_CACHE_DIR=/root/.cache/uv

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra ml

# 3. Remove compiler toolchain after install (shrinks final image ~60 MB)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get purge -y gcc && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Copy application source — models are NOT baked into the image.
# They are downloaded once at first container startup by the entrypoint
# and stored in named Docker volumes (hf_cache, yolo_cache, etc.) so they
# persist across all future builds and restarts without ever re-downloading.
COPY . .

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ML model cache dirs — these must match the volume mounts in docker-compose.yml.
# Models are downloaded by the entrypoint on first run into these volume-backed
# paths and persist across all subsequent builds and container restarts.
ENV NUMBA_CACHE_DIR="/app/cache/numba_cache" \
    YOLO_CONFIG_DIR="/app/cache/ultralytics" \
    TORCH_HOME="/app/cache/torch" \
    HF_HOME="/app/cache/huggingface" \
    TRANSFORMERS_CACHE="/app/cache/huggingface/transformers" \
    EASYOCR_MODEL_DIR="/app/cache/easyocr"

RUN mkdir -p \
    /app/storage/evidence \
    /app/storage/keys \
    /app/cache/huggingface \
    /app/cache/torch \
    /app/cache/numba_cache \
    /app/cache/ultralytics \
    /app/cache/calibration_models \
    /app/cache/easyocr

# Pre-compile application bytecode for faster cold starts (excluding caches)
RUN python -m compileall -q api/ core/ orchestration/ agents/ tools/ scripts/ 2>/dev/null || true

# Make entrypoint executable
RUN chmod +x scripts/docker_entrypoint.sh

# ── Stage 1: Development — hot-reload server ─────────────────────────────────
FROM base AS development

# Install dev + test dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --extra ml --extra dev

ENV RELOAD=true \
    APP_ENV=development \
    DEBUG=true

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD curl -f -s http://localhost:8000/health || exit 1

CMD ["sh", "scripts/docker_entrypoint.sh"]

# ── Stage 2: Production — hardened, non-root ─────────────────────────────────
FROM base AS production

# Create a dedicated non-root user so the process cannot write outside its
# designated directories even if exploited. All writable paths are explicitly
# chown'd here; volume mounts in docker-compose inherit these permissions.
RUN addgroup --system --gid 1001 appgroup \
 && adduser  --system --uid  1001 --ingroup appgroup --no-create-home appuser \
 && chown -R appuser:appgroup /app/cache /app/storage

# NOTE: We do NOT set USER here — the entrypoint starts as root so it can
# chown runtime-mounted volumes (Docker creates them as root:root on first use),
# then drops privileges to appuser before exec'ing the API server.

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD curl -f -s http://localhost:8000/health || exit 1

EXPOSE 8000

# Entrypoint fixes volume permissions, runs cache check, then starts the server.
# Set SKIP_CACHE_CHECK=1 to bypass the model check (useful in CI/CD pipelines).
CMD ["sh", "scripts/docker_entrypoint.sh"]

# Default target is production
FROM production
