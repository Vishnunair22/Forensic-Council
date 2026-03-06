# ─── Unified Build & Runtime Stage ──────────────────────────────────────────
FROM python:3.11-slim

# 1. Install system dependencies (including gcc for building wheels if needed)
# Leverages BuildKit APT cache so rebuilding the OS layer doesn't re-download binaries
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
    && rm -rf /var/lib/apt/lists/*

# 2. Install uv package manager natively
COPY --from=ghcr.io/astral-sh/uv:0.6.6 /uv /uvx /bin/

WORKDIR /app

# 3. Cache and install dependencies FIRST
COPY pyproject.toml uv.lock ./

# Use -v (verbose) to stream the download progress to the terminal
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_HTTP_TIMEOUT=300
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra ml -v

# 4. Remove compiler toolchain to flatten the image size
RUN apt-get purge -y gcc && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# 5. Bring in application payload
COPY . .

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 6. ML model cache directories
ENV NUMBA_CACHE_DIR="/app/cache/numba_cache"
ENV YOLO_CONFIG_DIR="/app/cache/ultralytics"
ENV TORCH_HOME="/app/cache/torch"
ENV HF_HOME="/app/cache/huggingface"
ENV DEEPFACE_HOME="/app/cache/deepface"
ENV TRANSFORMERS_CACHE="/app/cache/huggingface/transformers"

RUN mkdir -p /app/storage/evidence /app/storage/keys /app/cache/huggingface /app/cache/torch /app/cache/numba_cache /app/cache/ultralytics /app/cache/deepface /app/cache/calibration_models

# Pre-compile app bytecode
RUN /app/.venv/bin/python -m compileall -q api/ core/ orchestration/ scripts/ 2>/dev/null || true

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f -s http://localhost:8000/health || \
    (echo "Health check failed at $$(date)" >&2 && exit 1)

EXPOSE 8000

CMD ["python", "scripts/run_api.py"]
