# Docker Build And Cache Guide

This guide explains how Docker builds and caches work for Forensic Council.

## Compose Files

| File | Role |
| --- | --- |
| `docker-compose.yml` | Base stack and shared volumes |
| `docker-compose.dev.yml` | Development build targets and bind mounts |
| `docker-compose.prod.yml` | Production build targets and direct-port hardening |
| `docker-compose.infra.yml` | Postgres, Redis, and Qdrant only |
| `docker-compose.test.yml` | Test service stack |

## Build Arguments

### Backend: `PRELOAD_MODELS`

The backend Dockerfile accepts a `PRELOAD_MODELS` build argument (default: `1`).

| Value | Behaviour |
| --- | --- |
| `1` (default) | Downloads all ML model weights into the image during build. Clean volume starts hot. |
| `0` | Skips model download. Models are fetched at runtime on first use and cached in named volumes. |

With `PRELOAD_MODELS=1`, the backend image runs `scripts/validate_ml_tools.py`
and `scripts/model_pre_download.py --strict`. The build fails if required Python
ML imports, system binaries, referenced ML scripts, or required model downloads
are missing. Current required build-time assets are YOLO, EasyOCR, OpenCLIP,
torchvision ResNet-50, SpeechBrain ECAPA, and the configured audio deepfake
anti-spoof model (`AASIST_MODEL_NAME`, default `Vansh180/deepfake-audio-wav2vec2`).

Use `PRELOAD_MODELS=0` in CI/CD pipelines where build time matters and named volumes
persist model caches across runs:

```bash
# Development — skip model preload for faster builds
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env \
  build --build-arg PRELOAD_MODELS=0 backend worker

# Production — default (models baked into the image, volumes start hot)
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.prod.yml \
  --env-file .env \
  build backend worker
```

> **First-run note:** When `PRELOAD_MODELS=0` and named volumes are empty, the backend
> and worker will download models on startup. This can add 3–10 minutes to the first
> investigation run depending on network speed.

## Build Targets

Backend Dockerfile:

- `development`
- `production`
- `migration`

Frontend Dockerfile:

- `development`
- `builder`
- `runner`

The dev override selects development targets. The production override selects `production` for the backend and `runner` for the frontend.

## Cache Types

| Cache | Stores | Removed By |
| --- | --- | --- |
| Docker layer cache | OS packages and dependency layers | `docker builder prune`, image prune, or `--no-cache` rebuilds |
| BuildKit cache mounts | `uv`, `npm`, and framework build cache data | `docker builder prune` |
| Named volumes | Databases, evidence storage, model weights | `docker compose down -v` or `docker volume rm` |

Named volumes are the expensive ones. Do not delete them casually.

## Model Volumes

The base compose file pins:

```yaml
name: forensic-council
```

`.env.example` also sets:

```dotenv
COMPOSE_PROJECT_NAME=forensic-council
```

This keeps model and data volumes stable across dev/prod runs.

Important model/cache volumes:

| Volume | Contents |
| --- | --- |
| `hf_cache` | HuggingFace models |
| `torch_cache` | PyTorch checkpoints |
| `easyocr_cache` | EasyOCR models |
| `yolo_cache` | Ultralytics/YOLO weights |
| `numba_cache` | Numba compiled cache |
| `calibration_models_cache` | Calibration model files |

## Common Builds

> **Shell compatibility:** Replace `\` with a backtick `` ` `` on Windows PowerShell.
> Git Bash and WSL2 bash accept the Unix `\` syntax without modification.

Development:

```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env \
  up --build
```

Production:

```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.prod.yml \
  --env-file .env \
  up --build -d
```

Build one service (development target):

```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env build backend

docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env up -d --no-deps backend
```

Build one service (production target):

```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.prod.yml \
  --env-file .env build backend

docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.prod.yml \
  --env-file .env up -d --no-deps backend
```

No-cache rebuild while keeping volumes:

```bash
docker compose -f infra/docker-compose.yml --env-file .env build --no-cache
docker compose -f infra/docker-compose.yml --env-file .env up -d
```

Full reset including data and model volumes:

```bash
docker compose -f infra/docker-compose.yml --env-file .env down -v
```

Only run the full reset when you are comfortable losing local Postgres data, evidence files, signing key volume data, and downloaded model caches.

## Useful Diagnostics

```bash
# Show effective compose config
docker compose -f infra/docker-compose.yml --env-file .env config

# Show Docker disk usage
docker system df -v

# Show BuildKit cache usage
docker builder du

# Prune unused build cache
docker builder prune -f

# List Forensic Council volumes
docker volume ls | grep forensic-council
```

## Troubleshooting

### Models download repeatedly

Most likely `docker compose down -v` deleted the model volumes. Let them download once, then avoid `down -v`.

### Frontend still shows old environment values

`NEXT_PUBLIC_*` variables are baked into the frontend bundle. Rebuild the frontend:

```bash
docker compose -f infra/docker-compose.yml --env-file .env build frontend
docker compose -f infra/docker-compose.yml --env-file .env up -d --no-deps frontend
```

### Backend cannot write files

The backend uses `read_only: true`. Writable paths must be mounted as volumes or tmpfs. Check the base compose file for:

```yaml
tmpfs:
  - /tmp:nosuid,size=512m
volumes:
  - evidence_data:/app/storage/evidence:rw
  - signing_keys:/app/storage/keys:rw
  - hf_cache:/app/cache/huggingface:rw
```

### Prometheus cannot scrape backend metrics

Check that `METRICS_SCRAPE_TOKEN` is set in `.env`, passed to the backend, and mounted into Prometheus as `/run/secrets/metrics_scrape_token`.
