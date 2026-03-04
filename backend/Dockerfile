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

RUN apt-get update && apt-get install -y --no-install-recommends \
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
ENV NUMBA_CACHE_DIR="/tmp/numba_cache"
# ML model cache directories - must be writable in read-only container
ENV YOLO_CONFIG_DIR="/tmp/ultralytics"
ENV TORCH_HOME="/tmp/torch"
ENV HF_HOME="/tmp/huggingface"
ENV DEEPFACE_HOME="/tmp/deepface"
ENV TRANSFORMERS_CACHE="/tmp/huggingface/transformers"

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["python", "scripts/run_api.py"]
