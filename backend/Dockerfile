# ─── Unified Build & Runtime Stage (No BuildKit Required) ──────────────────────
FROM python:3.11-slim

# 1. Install system dependencies (Docker layer caching handles APT optimization automatically)
# NOTE: This layer will be cached by Docker. Subsequent builds reuse this layer if neither
# this RUN command nor the base image changes. For the best cache hit, keep deps stable.
RUN apt-get update && apt-get install -y --no-install-recommends \
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

# 2. Install uv package manager natively
COPY --from=ghcr.io/astral-sh/uv:0.6.6 /uv /uvx /bin/

WORKDIR /app

# 3. Cache and install dependencies FIRST
# Docker layer caching: This layer is cached if pyproject.toml and uv.lock don't change.
# ML models are downloaded during this step but ALSO persisted in named volumes (docker-compose)
# so they survive container restarts and don't need to be re-downloaded.
COPY pyproject.toml uv.lock ./

# Use -v (verbose) to stream the download progress to the terminal
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_HTTP_TIMEOUT=300
RUN uv sync --frozen --no-dev --no-install-project --extra ml -v

# 4. Remove compiler toolchain to flatten the image size
RUN apt-get purge -y gcc && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# 5. Bring in application payload
COPY . .

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 6. ML model cache directories (persist via named volumes in docker-compose)
# These environment variables tell ML libraries where to store downloaded models.
# The actual persistence is handled by docker-compose named volumes:
#   - hf_cache → /app/cache/huggingface
#   - torch_cache → /app/cache/torch
#   - numba_cache → /app/cache/numba_cache
#   - yolo_cache → /app/cache/ultralytics
#   - deepface_cache → /app/cache/deepface
#   - calibration_models → /app/cache/calibration_models
ENV NUMBA_CACHE_DIR="/app/cache/numba_cache"
ENV YOLO_CONFIG_DIR="/app/cache/ultralytics"
ENV TORCH_HOME="/app/cache/torch"
ENV HF_HOME="/app/cache/huggingface"
ENV DEEPFACE_HOME="/app/cache/deepface"
ENV TRANSFORMERS_CACHE="/app/cache/huggingface/transformers"
# EasyOCR model cache — persisted via easyocr_cache named volume
ENV EASYOCR_MODEL_DIR="/app/cache/easyocr"

RUN mkdir -p /app/storage/evidence /app/storage/keys \
    /app/cache/huggingface /app/cache/torch /app/cache/numba_cache \
    /app/cache/ultralytics /app/cache/deepface /app/cache/calibration_models \
    /app/cache/easyocr

# Pre-compile app bytecode
RUN /app/.venv/bin/python -m compileall -q api/ core/ orchestration/ scripts/ 2>/dev/null || true

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f -s http://localhost:8000/health || \
    (echo "Health check failed at $$(date)" >&2 && exit 1)

EXPOSE 8000

CMD ["python", "scripts/run_api.py"]
