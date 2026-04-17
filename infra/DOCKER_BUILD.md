# Forensic Council — Docker Build & Caching Guide

> **Version:** v1.5.0 | **Last Updated:** 2026-04-16
>
> This is the definitive reference for building, rebuilding, and managing
> Docker layer and ML model caches for Forensic Council.
> **Both** frontend and backend use proper multi-stage Dockerfiles:
> - **Frontend:** `base` → `development` → `builder` → `runner` stages
> - **Backend:** `base` → `development` → `production` stages
>
> `docker-compose.dev.yml` uses `target: development` for both services.
> `docker-compose.prod.yml` uses `target: production` (backend) / `runner` (frontend).

---

## Table of Contents

1. [How Caching Works](#how-caching-works)
2. [Shared Model Volumes — Dev & Prod](#shared-model-volumes--dev--prod)
3. [Startup Cache Check](#startup-cache-check)
4. [First Build (Cold Start)](#first-build-cold-start)
5. [Code-Only Rebuild (Fast Path)](#code-only-rebuild-fast-path)
6. [Dependency Rebuild](#dependency-rebuild)
7. [Full No-Cache Rebuild](#full-no-cache-rebuild)
8. [Per-Service Targeted Rebuild](#per-service-targeted-rebuild)
9. [ML Model Cache Management](#ml-model-cache-management)
10. [BuildKit Cache Mounts](#buildkit-cache-mounts)
11. [Layer Cache Invalidation Reference](#layer-cache-invalidation-reference)
12. [Quick Reference](#quick-reference)
13. [Troubleshooting Stale Builds](#troubleshooting-stale-builds)

---

## How Caching Works

Forensic Council uses **three distinct cache systems**, each operating independently:

| Cache System | What It Stores | Location | Evicted By |
|---|---|---|---|
| **Docker layer cache** | OS packages, Python/Node deps | Docker's local image store | `--no-cache` or image prune |
| **BuildKit cache mounts** | `uv` packages, `npm` packages, Next.js compiler | `/root/.cache/uv`, `/root/.npm`, `/app/.next/cache` inside build | `docker builder prune` |
| **Named volumes (ML models)** | HuggingFace, PyTorch, EasyOCR, YOLO, DeepFace weights | Docker named volumes | `docker compose down -v` |

> ⚠️ **Critical:** Never run `docker compose down -v` unless you intentionally want to delete all ML model caches.
> Models can take 15–60 minutes to re-download on first start.

---

## Shared Model Volumes — Dev & Prod

**All compose variants share the exact same named volumes.** Dev and production builds
read from and write to the same pool. Switching from dev to production mode (or back)
never triggers a model re-download.

This is enforced via two mechanisms:

### 1. Pinned project name

Every compose file has `name: forensic-council` at the top level:

```yaml
name: forensic-council
services:
  ...
```

Docker uses the project name as a prefix for all named volumes. Without a consistent name,
Docker falls back to the working directory name — which varies between machines and CI
environments, causing separate volume pools and duplicate downloads.

### 2. `COMPOSE_PROJECT_NAME` in `.env`

```dotenv
COMPOSE_PROJECT_NAME=forensic-council
```

This is a belt-and-suspenders backup. If the compose file is invoked without the top-level
`name:` (e.g. via an older Docker version), the env var ensures the same project prefix.

### Verifying volumes are shared

```bash
# List all volumes for the forensic-council project
docker volume ls | grep forensic-council

# Expected output — all 6 model volumes use the same prefix:
# DRIVER    VOLUME NAME
# local     forensic-council_hf_cache
# local     forensic-council_torch_cache
# local     forensic-council_easyocr_cache
# local     forensic-council_yolo_cache
# local     forensic-council_numba_cache
# local     forensic-council_calibration_models
```

```bash
# Quick check:
docker system df -v | grep forensic
```

---

## Startup Cache Check

Every time a backend container starts, it runs `scripts/model_cache_check.py` via
the Docker entrypoint before the API server launches. This takes ~3 seconds and:

1. Scans each cache directory and reports size + file count
2. Verifies all core Python imports are working
3. Logs a clear warning if any cache is empty (first run)
4. Always exits 0 — empty cache is not an error, just means first-use download is pending

Sample output on a cold start (first ever run):

```
━━━  ML Model Cache Status  ━━━

  ✓ CACHED   HuggingFace       1024.5 MB  (247 files)  /app/cache/huggingface
  ⚠ EMPTY    PyTorch              (will download on first use)
  ⚠ EMPTY    EasyOCR              (will download on first use)
  ✓ CACHED   YOLO                  52.3 MB  (4 files)
  ⚠ EMPTY    DeepFace              (will download on first use)
  ○ EMPTY    Numba                 (populated at runtime)
  ○ EMPTY    Calibration           (populated at runtime)

  3 of 7 cache directories are empty.
  Models will be downloaded automatically on first use.

Verifying Python environment...
  ✓  FastAPI
  ✓  Pydantic
  ✓  Redis async client
  ...
  All core modules verified.
```

To skip the cache check (useful in CI/CD):

```bash
docker run ... -e SKIP_CACHE_CHECK=1 ...
# or in compose:
environment:
  - SKIP_CACHE_CHECK=1
```

---

## First Build (Cold Start)

Use this when setting up from scratch. All layers and ML model volumes will be created fresh.

```bash
# 1. Copy and fill in your environment variables
# Windows PowerShell: Copy-Item .env.example .env
# Linux/macOS:        cp .env.example .env
# Edit .env — at minimum set LLM_API_KEY and GEMINI_API_KEY

# 2. Build and start all services
docker compose -f infra/docker-compose.yml --env-file .env up --build -d

# 3. Check that all containers are healthy
docker compose -f infra/docker-compose.yml ps
```

**Expected first-build times:**
- Backend image (with ML deps): **10–20 min** (downloads PyTorch, transformers, etc.)
- Frontend image: **2–5 min**
- ML model downloads (first container start): **15–60 min** (depends on connection speed)

> Models only download once. Every subsequent start or rebuild will reuse the named volumes.

---

## Code-Only Rebuild (Fast Path)

When you've changed Python or TypeScript source files but **not** `pyproject.toml` or `package.json`:

```bash
# Rebuild and restart in one command — Docker reuses all dependency layers
docker compose -f infra/docker-compose.yml --env-file .env up --build -d
```

**Why this is fast:** Both Dockerfiles copy source code in the final layer, *after* the
dependency installation layers. Changing only source files invalidates only the last layer,
so the multi-GB PyTorch and npm layers are reused from cache.

**Expected rebuild time:** **30–90 seconds** (backend), **20–60 seconds** (frontend).

---

## Dependency Rebuild

When you've updated `pyproject.toml` (Python deps) or `package.json` (Node deps):

```bash
# The dependency layer will be rebuilt; the OS/apt layer will be reused
docker compose -f infra/docker-compose.yml --env-file .env up --build -d
```

Because the Dockerfiles use **BuildKit cache mounts** (`--mount=type=cache`), even a
dependency rebuild reuses the package download cache:

- `uv` packages: cached at `/root/.cache/uv` — packages that haven't changed download
  only the diff
- `npm` packages: cached at `/root/.npm` — same logic

**Expected rebuild time:** **2–8 min** depending on how many new packages were added.

To rebuild just one service's dependencies:

```bash
# Backend only
docker compose -f infra/docker-compose.yml --env-file .env build backend

# Frontend only
docker compose -f infra/docker-compose.yml --env-file .env build frontend
```

---

## Full No-Cache Rebuild

Use this when you suspect a stale or corrupted build layer, or after changing the Dockerfile itself.

### Option A — No-cache for all services

```bash
docker compose -f infra/docker-compose.yml --env-file .env build --no-cache
docker compose -f infra/docker-compose.yml --env-file .env up -d
```

> ⚠️ `--no-cache` bypasses **Docker layer cache only**. It does NOT delete named volumes.
> ML model weights in `hf_cache`, `torch_cache`, etc. are **not affected** — they are
> re-mounted from the existing named volumes. Models do not re-download.

### Option B — No-cache for a single service

```bash
# Rebuild backend from scratch (useful after Dockerfile changes)
docker compose -f infra/docker-compose.yml --env-file .env build --no-cache backend

# Rebuild frontend from scratch
docker compose -f infra/docker-compose.yml --env-file .env build --no-cache frontend
```

### Option C — Wipe BuildKit cache (nuclear option)

The BuildKit mount caches (`uv`, `npm`, Next.js compiler) are separate from the layer cache.
If you suspect a corrupted package cache:

```bash
# Prune all BuildKit cache
docker builder prune -f

# Then rebuild
docker compose -f infra/docker-compose.yml --env-file .env up --build -d
```

---

## Per-Service Targeted Rebuild

Rebuild only one service without touching the rest:

```bash
# 1. Build the new image
docker compose -f infra/docker-compose.yml --env-file .env build backend

# 2. Restart just that service (zero-downtime for other services)
docker compose -f infra/docker-compose.yml --env-file .env up -d --no-deps backend
```

This is the fastest way to iterate on backend changes in production without restarting
the frontend, Redis, Postgres, or Qdrant.

---

## ML Model Cache Management

ML model weights are stored in Docker **named volumes**, not in images. This means:

- They persist across `docker compose down && docker compose up`
- They persist across full image rebuilds (`--no-cache`)
- They are shared between dev and production stacks (same volume names)
- They are only deleted by `docker compose down -v`

### View current volume sizes

```bash
docker system df -v | grep forensic
```

### Named volumes and their contents

| Volume | Contents | Approx Size |
|---|---|---|
| `hf_cache` | HuggingFace models (Wav2Vec2, CLIP, pyannote) | 5–15 GB |
| `torch_cache` | PyTorch hub models | 500 MB – 2 GB |
| `easyocr_cache` | EasyOCR text recognition models | ~100 MB |
| `yolo_cache` | YOLOv8 object detection weights | ~50 MB |
| `numba_cache` | Numba JIT compiled kernels | ~100 MB |
| `calibration_models_cache` | Platt scaling calibration checkpoints | ~10 MB |

### Force re-download of a specific model cache

```bash
# Delete one specific volume (e.g. just EasyOCR models)
docker volume rm forensic-council-main_easyocr_cache

# Models re-download automatically on next container start
docker compose -f infra/docker-compose.yml --env-file .env up -d backend
```

### Full model cache wipe (⚠️ long re-download)

```bash
# This DELETES ALL volumes including postgres, redis, and all ML models
docker compose -f infra/docker-compose.yml --env-file .env down -v

# Or stop and remove volumes explicitly:
docker compose -f infra/docker-compose.yml --env-file .env down -v
```

---

## BuildKit Cache Mounts

Both Dockerfiles use BuildKit `--mount=type=cache` to speed up repeated builds.
These caches survive `docker compose down`, `docker compose build --no-cache`, and
image deletion. They only disappear when explicitly pruned.

### Backend (uv package cache)

```dockerfile
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev
```

Effect: Even after `--no-cache`, if the same packages are needed, uv finds them in
the BuildKit cache and installs in seconds without network access.

### Frontend (npm + Next.js compiler cache)

```dockerfile
RUN --mount=type=cache,target=/root/.npm \
    npm ci --prefer-offline

RUN --mount=type=cache,target=/app/.next/cache \
    npm run build
```

Effect: `npm ci` resolves packages from the BuildKit cache. Next.js compiler reuses
previously compiled modules for unchanged files — near-instant recompilation on
code-only changes.

### Inspect and prune BuildKit caches

```bash
# View cache size
docker builder du

# Prune unused BuildKit caches
docker builder prune -f

# Prune everything (aggressive)
docker builder prune --all -f
```

---

## Layer Cache Invalidation Reference

Understanding when cache is invalidated helps avoid surprises:

### Backend Dockerfile layer order

```
Layer 1  → FROM python:3.12-slim (never invalidates)
Layer 2  → apt install (invalidates if apt list changes)
Layer 3  → uv install (invalidates if pyproject.toml changes)
Layer 4  → COPY source code (invalidates if any .py file changes)
Layer 5  → compileall (always runs, but fast)
```

### Frontend Dockerfile layer order

The frontend uses a multi-stage Dockerfile with three named targets:
`base` → `development` → `builder` → `runner`.

```
# base stage (shared)
Layer 1  → FROM node:22-alpine (never invalidates)
Layer 2  → npm ci (invalidates if package-lock.json changes)

# development target (dev mode)
Layer 3  → COPY source files (invalidates if any .ts/.tsx/.css changes)

# builder stage (production only)
Layer 3  → COPY source files (invalidates if any .ts/.tsx/.css changes)
Layer 4  → npm run build (always runs, but Next.js uses .next/cache internally)
```

### What triggers a full rebuild?

| Change | Backend | Frontend |
|---|---|---|
| Edit a `.py` file | Layer 4 only (~30s) | No change |
| Edit a `.ts/.tsx` file | No change | Layer 3+4 (~30-60s) |
| Add a Python package | Layer 3+4 (~2-8min) | No change |
| Add a Node package | No change | Layer 2+3+4 (~2-5min) |
| Edit `apps/api/Dockerfile` | All layers | No change |
| Edit `apps/web/Dockerfile` | No change | All layers |
| Edit `.env` values | No rebuild needed | `NEXT_PUBLIC_*` requires frontend rebuild |

> **Important:** `NEXT_PUBLIC_*` environment variables are baked into the JS bundle at
> build time. Changing them in `.env` requires rebuilding the frontend image:
> ```bash
> docker compose -f infra/docker-compose.yml --env-file .env build frontend
> docker compose -f infra/docker-compose.yml --env-file .env up -d --no-deps frontend
> ```

---

## Quick Reference

| Action | Command |
|---|---|
| Start all | `docker compose -f infra/docker-compose.yml --env-file .env up -d --build` |
| Start Hot-Reload | `docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env up -d --build` |
| Build only | `docker compose -f infra/docker-compose.yml --env-file .env build` |
| Stop (keep volumes) | `docker compose -f infra/docker-compose.yml --env-file .env down` |
| Stop (wipe volumes) | `docker compose -f infra/docker-compose.yml --env-file .env down -v` |
| View Logs | `docker compose -f infra/docker-compose.yml --env-file .env logs -f` |
| Production Mode | `docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file .env up -d --build` |

---

## Troubleshooting Stale Builds

### Symptom: Old code still running after rebuild

The running container may not have been restarted. Force restart:

```bash
docker compose -f infra/docker-compose.yml --env-file .env up --build -d --force-recreate
```

### Symptom: Frontend shows old UI despite `--build`

`NEXT_PUBLIC_*` vars are baked at build time. If you changed them:

```bash
docker compose -f infra/docker-compose.yml --env-file .env build --no-cache frontend
docker compose -f infra/docker-compose.yml --env-file .env up -d --no-deps frontend
```

### Symptom: Backend fails to start with import error after adding package

The `uv.lock` file may be out of sync. Run locally (requires uv):

```bash
cd apps/api && uv lock
# Then rebuild
docker compose -f infra/docker-compose.yml --env-file .env build --no-cache backend
```

### Symptom: BuildKit `--mount=type=cache` not working

Requires Docker 23+ (BuildKit enabled by default) or Docker Desktop 4.x.
Check your version: `docker --version`

For older Docker:

```bash
DOCKER_BUILDKIT=1 docker compose -f infra/docker-compose.yml --env-file .env up --build
```

### Symptom: `Error: NEXT_PUBLIC_DEMO_PASSWORD not set in .env`

The `docker-compose.yml` uses `:?` guard for this variable:

```bash
# Windows PowerShell: Copy-Item .env.example .env
# Linux/macOS:        cp .env.example .env
# Ensure DEMO_PASSWORD is set (not commented out)
```

### Symptom: Models re-downloading after every rebuild

This means the named volumes aren't persisting. Likely cause: running with `-v` flag.
Check with: `docker volume ls | grep forensic`

If volumes are missing, they will be re-created and models will re-download on next start.
This is normal and only happens once.


