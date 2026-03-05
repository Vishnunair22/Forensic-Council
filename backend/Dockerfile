# ─── Stage 1: Build ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# Install build tools (only in this stage)
RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

# Install uv via binary directly
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy only dependency files first (cache layer)
COPY pyproject.toml uv.lock ./

# Sync production deps only, use lockfile, cache wheels across builds
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_HTTP_TIMEOUT=300
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ─── Stage 2: Production ─────────────────────────────────────────────────────
FROM python:3.11-slim

# Install system dependencies with apt cache mount for faster rebuilds
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tesseract-ocr \
    tesseract-ocr-eng \
    exiftool \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only the built venv and app code (no gcc, no build tools)
COPY --from=builder /app/.venv /app/.venv
COPY . .

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

# ML model cache directories - moved to /app/cache to avoid tmpfs conflict
ENV NUMBA_CACHE_DIR="/app/cache/numba_cache"
ENV YOLO_CONFIG_DIR="/app/cache/ultralytics"
ENV TORCH_HOME="/app/cache/torch"
ENV HF_HOME="/app/cache/huggingface"
ENV DEEPFACE_HOME="/app/cache/deepface"
ENV TRANSFORMERS_CACHE="/app/cache/huggingface/transformers"

# Pre-compile app bytecode at build time (not at runtime)
RUN /app/.venv/bin/python -m compileall -q api/ core/ orchestration/ scripts/ 2>/dev/null || true

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["python", "scripts/run_api.py"]
