# syntax=docker/dockerfile:1.7
# ─── Backend — Multi-Stage Build ──────────────────────────────────────────────
# Stages:
#   base        — system deps + uv (shared by all stages, NO Python packages yet)
#   deps-core   — core Python packages only (no ML extras)
#   deps-full   — core + ML packages (PyTorch, transformers, etc.)
#   migration   — lightweight DB init, inherits deps-core (~2-3 GB lighter)
#   app         — shared source + dirs + bytecode (inherits deps-full)
#   development — hot-reload dev server  (used by: docker-compose.dev.yml)
#   production  — hardened, non-root, read-only container (default)
#
# Why split deps-core / deps-full?
#   The migration job only runs scripts/init_db.py (asyncpg + pydantic).
#   It does NOT need PyTorch, ultralytics, transformers, speechbrain.
#   Keeping those out of the migration image saves ~2-3 GB of image size.
#
# Requires BuildKit (enabled by default in Docker 23+ and Docker Desktop).
# Manual override: DOCKER_BUILDKIT=1 docker compose build
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 0: base — system packages + uv only (no Python venv yet) ───────────
# Pinned to bookworm (Debian 12) — NOT trixie (Debian 13).
# Reason: python:3.12-slim now resolves to Debian 13 which uses sqv (Rust OpenPGP
# verifier) instead of gpgv. sqv strictly enforces NotBefore timestamps in
# Debian mirror release signatures, causing apt-get to fail with exit 100 when
# the Debian CDN pre-signs releases ~5 hours before their official publish time.
# Bookworm uses gpgv which does not enforce NotBefore; switch to trixie once
# Debian resolves the pre-signing window or sqv gains a tolerance option.
FROM python:3.12-slim-bookworm AS base

# System deps — cached aggressively via BuildKit cache mount.
# gcc is needed at install time (some packages compile C extensions);
# it is purged in the deps-* stages to shrink the final layers.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get -o Acquire::Check-Date=false update \
    && apt-get install -y --no-install-recommends \
        curl \
        tesseract-ocr \
        tesseract-ocr-eng \
        exiftool \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        gcc \
        libmediainfo-dev \
        libmagic-dev \
        util-linux \
        procps \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager).
# Pinned for reproducible builds; using pip to avoid ghcr.io TLS issues.
RUN pip install --no-cache-dir uv==0.6.5

WORKDIR /app

# Copy only the dependency manifests first.
# Source-code changes do NOT invalidate the uv sync layers below.
COPY pyproject.toml uv.lock ./

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=600 \
    UV_CACHE_DIR=/root/.cache/uv

# ── Stage 1: deps-core — core packages only, NO ML extras ────────────────────
# Used by: migration (keeps that image ~2-3 GB lighter)
FROM base AS deps-core

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Purge gcc after install — runtime code does not need the compiler.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-mark manual libgl1 libglib2.0-0 libmediainfo-dev libmagic-dev \
    && apt-get purge -y gcc \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Stage 2: deps-full — core + ML packages (PyTorch, transformers, etc.) ────
# Used by: app → development, production
FROM base AS deps-full

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra ml

# Purge gcc after install (~60 MB saving).
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-mark manual libgl1 libglib2.0-0 libmediainfo-dev libmagic-dev \
    && apt-get purge -y gcc \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Stage 3: migration — lightweight DB init (no ML deps) ────────────────────
FROM deps-core AS migration

COPY pyproject.toml uv.lock ./
COPY scripts/ scripts/
COPY core/ core/
COPY api/ api/
COPY agents/ agents/
COPY tools/ tools/
COPY orchestration/ orchestration/
COPY reports/ reports/
COPY config/ config/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1 \
    CURL_HOME="/tmp" \
    XDG_CACHE_HOME="/tmp"

RUN mkdir -p \
    /app/storage/evidence \
    /app/storage/keys \
    /app/storage/calibration_models

RUN chmod +x scripts/docker_entrypoint.sh

# SECURITY: run as non-root
RUN addgroup --system --gid 1001 appgroup \
 && adduser  --system --uid  1001 --ingroup appgroup --no-create-home appuser \
 && chown -R appuser:appgroup /app/storage

USER appuser

CMD ["python", "scripts/init_db.py"]

# ── Stage 4: app — shared source + dirs + bytecode (inherits deps-full) ──────
# This intermediate stage is the common ancestor of development and production.
# It avoids duplicating COPY / mkdir / compileall / chmod across both targets.
FROM deps-full AS app

COPY pyproject.toml uv.lock ./
COPY scripts/ scripts/
COPY core/ core/
COPY api/ api/
COPY agents/ agents/
COPY tools/ tools/
COPY orchestration/ orchestration/
COPY reports/ reports/
COPY config/ config/
COPY worker.py .

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1 \
    CURL_HOME="/tmp" \
    MPLCONFIGDIR="/tmp/matplotlib" \
    XDG_CACHE_HOME="/tmp"

# ML model cache dirs — must match the volume mounts in docker-compose.yml.
# Models download once on first run into these paths and persist in named volumes.
ENV NUMBA_CACHE_DIR="/app/cache/numba_cache" \
    YOLO_CONFIG_DIR="/app/cache/ultralytics" \
    TORCH_HOME="/app/cache/torch" \
    HF_HOME="/app/cache/huggingface" \
    TRANSFORMERS_CACHE="/app/cache/huggingface/transformers" \
    EASYOCR_MODEL_DIR="/app/cache/easyocr"

RUN mkdir -p \
    /app/storage/evidence \
    /app/storage/keys \
    /app/storage/calibration_models \
    /app/cache/huggingface \
    /app/cache/torch \
    /app/cache/numba_cache \
    /app/cache/ultralytics \
    /app/cache/easyocr

# Pre-compile application bytecode for faster cold starts.
# UV_COMPILE_BYTECODE=1 compiled venv packages; this handles app source code.
RUN python -m compileall -q api/ core/ orchestration/ agents/ tools/ scripts/ reports/ 2>/dev/null || true

RUN chmod +x scripts/docker_entrypoint.sh

# ── Stage 5: development — hot-reload server ─────────────────────────────────
FROM app AS development

# Add dev + test dependencies on top of the full ML env
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --extra ml --extra dev

ENV RELOAD=true \
    APP_ENV=development \
    DEBUG=true

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD curl -f -s http://localhost:8000/health || exit 1

CMD ["sh", "scripts/docker_entrypoint.sh"]

# ── Stage 6: production — hardened, non-root ─────────────────────────────────
FROM app AS production

# Create a dedicated non-root user. All writable paths are chown'd here;
# volume mounts in docker-compose inherit these permissions.
RUN addgroup --system --gid 1001 appgroup \
 && adduser  --system --uid  1001 --ingroup appgroup --no-create-home appuser \
 && chown -R appuser:appgroup /app/cache /app/storage

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD curl -f -s http://localhost:8000/health || exit 1

EXPOSE 8000

USER appuser
ENTRYPOINT ["sh", "scripts/docker_entrypoint.sh"]
