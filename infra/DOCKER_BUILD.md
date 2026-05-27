# Forensic Council — Docker Build Guide

Complete reference for building, running, and verifying the Forensic Council stack in both **developer** and **production** modes.

> **Shell syntax note:** All multi-line commands below use `\` (Unix/Git Bash/WSL2).
> On **Windows PowerShell**, replace each `\` with a backtick `` ` ``.

---

## Table of Contents

0. [The "What to Use When" Reference](#0-the-what-to-use-when-reference)
1. [Prerequisites](#1-prerequisites)
2. [Environment Setup](#2-environment-setup)
3. [Developer Mode](#3-developer-mode)
4. [Production Mode](#4-production-mode)
5. [No-Cache Rebuild](#5-no-cache-rebuild)
6. [Verifying Model Downloads](#6-verifying-model-downloads)
7. [Container Health Reference](#7-container-health-reference)
8. [Per-Service Rebuild](#8-per-service-rebuild)
9. [Volumes and Cache Reference](#9-volumes-and-cache-reference)
10. [Compose File Reference](#10-compose-file-reference)
11. [Teardown](#11-teardown)
12. [Troubleshooting](#12-troubleshooting)

---

## 0. The "What to Use When" Reference

Use this quick-reference table to identify the correct command or script for every container lifecycle action:

| Operation | Developer Command / Script | Production Command / Script |
|---|---|---|
| First-time start | `bash scripts/dev.sh` | `bash scripts/prod.sh` |
| Start (after first run) | `bash scripts/dev.sh` | `bash scripts/prod.sh` |
| Build images only | `docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env build --parallel` | `docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file .env build --parallel` |
| Rebuild one service | `bash scripts/rebuild.sh dev <service>` | `bash scripts/rebuild.sh prod <service>` |
| Rebuild all (no cache) | `bash scripts/rebuild.sh dev` | `bash scripts/rebuild.sh prod` |
| Apply .env changes | `docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env up -d --force-recreate <service>` | `docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file .env up -d --force-recreate <service>` |
| Restart worker (fast) | `docker compose kill -s SIGKILL worker && docker compose up -d --no-deps worker` (or `bash scripts/dev-restart-worker.sh`) | *Do not use in production (may orphan in-flight tasks)* |
| Pause stack temporarily | `docker compose -f infra/docker-compose.yml --env-file .env stop` | `docker compose -f infra/docker-compose.yml --env-file .env stop` |
| Resume after pause | `docker compose -f infra/docker-compose.yml --env-file .env start` | `docker compose -f infra/docker-compose.yml --env-file .env start` |
| Stop and remove containers | `docker compose -f infra/docker-compose.yml --env-file .env down` | `docker compose -f infra/docker-compose.yml --env-file .env down` |
| Full clean (nuclear reset) | `down -v` → `builder prune` → `clean_project.sh --deep` → `dev.sh` | `down -v` → `builder prune` → `clean_project.sh --deep` → `prod.sh` |
| View health status | `bash scripts/troubleshoot.sh` | `bash scripts/troubleshoot.sh` |
| Wait for full health | `bash scripts/_wait_healthy.sh dev` | `bash scripts/_wait_healthy.sh prod` |
| Smoke test end-to-end | `bash scripts/_smoke.sh dev` | `bash scripts/_smoke.sh prod` |
| Verify ML models | `docker exec forensic_api python scripts/model_cache_check.py --strict` | `docker exec forensic_api python scripts/model_cache_check.py --strict` |
| View logs | `docker compose -f infra/docker-compose.yml --env-file .env logs -f <service>` | `docker compose -f infra/docker-compose.yml --env-file .env logs -f <service>` |
| Debug merged compose config | `docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env config` | `docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file .env config` |

---

## 1. Prerequisites

| Requirement | Minimum version | Check |
|-------------|----------------|-------|
| Docker Desktop (Windows/macOS) or Docker Engine (Linux) | 24.0+ | `docker --version` |
| Docker Compose plugin | 2.22+ | `docker compose version` |
| BuildKit | enabled by default in Docker 23+ | `docker buildx version` |

Docker Desktop for Windows uses WSL2. Ensure WSL2 integration is enabled in Docker Desktop → Settings → Resources → WSL Integration.

---

## 2. Environment Setup

### 2a. Create `.env` from template

Run from the **repo root** (one directory above `infra/`).

**Bash / Git Bash / WSL2:**
```bash
[ -f .env ] || cp .env.example .env
```

**PowerShell:**
```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

### 2b. Fill in required API keys

Open `.env` and set these two values — everything else has working defaults for local development:

```dotenv
# Groq — logic, reasoning, and LLM synthesis (free tier available)
# Get key: https://console.groq.com/keys
LLM_API_KEY=gsk_...

# Google Gemini — vision and audio deep analysis (free tier available)
# Get key: https://aistudio.google.com/apikey
GEMINI_API_KEY=AIza...
```

> The app starts without these keys and degrades gracefully (Gemini analysis is skipped, LLM synthesis is disabled), but forensic results will be incomplete.

### 2c. Verify `.env` is not tracked by Git

```bash
git status .env
# Should show: nothing to commit (or not listed at all)
```

`.env` is listed in `.gitignore` and must **never** be committed.

---

## 3. Developer Mode

Developer mode targets the `development` Docker stage for the backend and worker (uvicorn `--reload` enabled, dev dependencies installed) and `next dev` for the frontend (Turbopack HMR). Source code is bind-mounted so every saved file is reflected instantly without rebuilding.

### Recommended: One-shot start
To boot the developer environment with automatic `.env` verification, parallel builds, worker health checks, and ML cache checks, run from the repository root:
```bash
bash scripts/dev.sh
```

### Advanced: Manual Control
If you need to control the build process or run containers interactively, use the manual commands below.

#### Step 1 — Build and start (dev overlay provides direct host ports 8000, 5432, 6379, 6333)

```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env \
  up --build
```

The first build downloads OS packages, Python dependencies, and ML model weights into the image. Expect **15–40 minutes** depending on your network speed. Subsequent builds use Docker layer cache and finish in under a minute.

**To run in the background (detached):**
```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env \
  up --build -d
```

#### Step 2 — Monitor build and startup logs

Open a second terminal while the build runs:

```bash
# All services
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env \
  logs -f

# Single service
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env logs -f backend
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env logs -f worker
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env logs -f frontend
```

Key log lines to watch for:

| Service | Healthy indicator |
|---------|-------------------|
| `postgres` | `database system is ready to accept connections` |
| `redis` | `Ready to accept connections` |
| `migration` | `DB initialisation complete` / `exit 0` |
| `backend` | `Application startup complete` |
| `worker` | `Starting Forensic Council Background Worker` |
| `frontend` | `✓ Ready` (Turbopack) or `ready - started server on 0.0.0.0:3000` |

#### Step 3 — Confirm all containers are healthy

```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env \
  ps
```

All services should show `healthy` or `running`. The `migration` service will show `exited (0)` — that is correct (it runs once then stops).

Quick status table:
```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

#### Step 4 — Verify ML models downloaded

See [Section 6](#6-verifying-model-downloads).

#### Step 5 — Run post-start smoke test
Verify routing and authentication end-to-end:
```bash
bash scripts/_smoke.sh dev
```

#### Step 6 — Open the app

| URL | What |
|-----|------|
| `http://localhost` | Caddy proxy — recommended entry point (frontend + API) |
| `http://localhost:3000` | Frontend direct |
| `http://localhost:8000` | Backend API direct (only with dev overlay) |
| `http://localhost:8000/docs` | FastAPI interactive docs (Swagger UI, only with dev overlay) |
| `http://localhost:16686` | Jaeger distributed tracing UI |
| `http://localhost:9090` | Prometheus metrics UI |

Click **Demo Login** on the landing page to authenticate as the investigator user. The demo route uses `BOOTSTRAP_INVESTIGATOR_PASSWORD` from your `.env` — the placeholder value works out of the box because the migration creates the user with that same password.

### Build images only (no start)
To build the developer images without starting containers (useful for verifying Dockerfile changes or pre-warming the cache):
```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env \
  build --parallel
```

### Applying .env changes
Environment variables are injected at container creation. When you edit `.env`, recreate the containers to apply:
```bash
# Apply to backend and worker
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env up -d --force-recreate backend worker

# Apply to frontend
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env up -d --force-recreate frontend
```

### Hot-reload behaviour

| Service | Trigger | Behaviour |
|---------|---------|-----------|
| **Frontend** | Save any `.tsx`, `.ts`, `.css` file | Turbopack HMR updates the browser in ~500 ms (uses polling fallback inside container) |
| **Backend** | Save any `.py` file in `api/`, `core/`, `agents/`, `tools/`, `orchestration/` | uvicorn `--reload` restarts the server in ~1 s |
| **Worker** | Save any `.py` file | Code is live in the container; to apply instantly without waiting for the 300s grace period, run `bash scripts/dev-restart-worker.sh` (or `docker compose kill -s SIGKILL worker && docker compose up -d --no-deps worker`) |

---

## 4. Production Mode

### Recommended: One-shot start
To validate production readiness, generate certificates, download models, build all images, start the stack, and verify health through Caddy/worker/ML check, run from the repository root:
```bash
bash scripts/prod.sh
```
*Note: This script automatically runs `validate_production_readiness.sh` before booting.*

### Advanced: Manual Control
If you need to configure and start the production environment step by step, follow the manual workflow below:

#### Step 1 — Generate strong secrets

Run this once from the **repo root**. It prints all required secret values to stdout — copy them into your `.env` file:

```bash
bash infra/generate_production_keys.sh
```

> On Windows without Git Bash/WSL2: run the script in Git Bash or WSL2, then paste the output values into your `.env` file manually.

#### Step 2 — Configure production-specific settings

Edit `.env` and update these fields:

```dotenv
APP_ENV=production

# Your public domain (Caddy provisions TLS automatically)
DOMAIN=forensic.yourdomain.com
CADDY_SITE_ADDRESS=forensic.yourdomain.com

# Let's Encrypt expiry notifications
ACME_EMAIL=admin@yourdomain.com

# CORS: only your domain — no wildcards
CORS_ALLOWED_ORIGINS=https://forensic.yourdomain.com

# Gemini quota — raise if you have a paid-tier key
GEMINI_RPM_LIMIT=10
GEMINI_RPD_LIMIT=1500
```

#### Step 3 — Validate production readiness

```bash
bash infra/validate_production_readiness.sh
```

All `FAIL` lines must be resolved before starting in production. `WARN` lines are informational.

#### Step 4 — Build and start

```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.prod.yml \
  --env-file .env \
  up --build -d
```

The production overlay:
- Targets the hardened `production` Dockerfile stage (no dev dependencies)
- Sets `RELOAD=false` — uvicorn runs without the file watcher
- Removes source code bind mounts (image is self-contained)
- Strips direct host port bindings for backend/infra — all traffic flows through Caddy
- Enables `restart: always` for automatic crash recovery

#### Step 5 — Monitor startup

```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.prod.yml \
  --env-file .env \
  logs -f
```

#### Step 6 — Confirm all containers are healthy

```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.prod.yml \
  --env-file .env \
  ps
```

#### Step 7 — Verify ML models

See [Section 6](#6-verifying-model-downloads).

#### Step 8 — Run post-start smoke test
Verify routing and authentication end-to-end:
```bash
bash scripts/_smoke.sh prod
```

#### Step 9 — Open the app

```
https://forensic.yourdomain.com
```

Caddy obtains a Let's Encrypt TLS certificate automatically on first request to a real domain. Allow up to 60 seconds for ACME issuance.

### Build images only (no start)
To build the production images without starting containers (useful for CI/CD stages or deployment cache pre-warming):
```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.prod.yml \
  --env-file .env \
  build --parallel
```

### Applying .env changes
Environment variables are injected at container creation. When you edit `.env` in production, recreate the containers:
```bash
# Recreate backend and worker
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file .env up -d --force-recreate backend worker

# Recreate frontend
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file .env up -d --force-recreate frontend
```

---

## 5. No-Cache Rebuild

Use this when Docker layer cache is stale (e.g. base image updated, dependency version changes, Dockerfile modified).

**Keeps all named volumes** (databases, model weights, evidence files are preserved).

### Recommended: Using the rebuild helper
The `scripts/rebuild.sh` script automatically wraps the correct compose files, overlay targets, and build arguments. Run from the repository root:

```bash
# Rebuild all services in development mode
bash scripts/rebuild.sh dev

# Rebuild all services in production mode
bash scripts/rebuild.sh prod

# Rebuild a single service in development mode
bash scripts/rebuild.sh dev backend
bash scripts/rebuild.sh dev worker
bash scripts/rebuild.sh dev frontend

# Rebuild a single service in production mode
bash scripts/rebuild.sh prod backend
bash scripts/rebuild.sh prod worker
bash scripts/rebuild.sh prod frontend
```

### Advanced: Manual No-Cache Rebuild
If you need to pass additional docker build arguments or target specific layers manually:

#### Developer full stack rebuild
```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env \
  build --no-cache

docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env \
  up -d
```

#### Production full stack rebuild
```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.prod.yml \
  --env-file .env \
  build --no-cache

docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.prod.yml \
  --env-file .env \
  up -d
```

#### Manual single-service rebuilds
Make sure you include the appropriate dev/prod overlays so target build stages are correctly resolved.

**Developer Mode (e.g. backend):**
```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env \
  build --no-cache backend

docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env \
  up -d --no-deps backend
```

**Production Mode (e.g. backend):**
```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.prod.yml \
  --env-file .env \
  build --no-cache backend

docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.prod.yml \
  --env-file .env \
  up -d --no-deps backend
```

### Also prune BuildKit cache (deepest clean)

Run this only when you need a truly clean slate — it removes cached layers for all Docker projects:

```bash
docker builder prune -f
```

---

## 6. Verifying Model Downloads

After the stack starts, confirm that the model cache directories, Python ML dependencies, and individual required model artifacts are present. While they share the underlying model cache volumes, both the backend (`forensic_api`) and the background worker (`forensic_worker`) verify cache integrity independently at startup.

Run the status check against both containers:

```bash
# Verify backend container cache
docker exec forensic_api python scripts/model_cache_check.py --strict

# Verify worker container cache
docker exec forensic_worker python scripts/model_cache_check.py --strict
```

Expected output should show cache directories as healthy and required model assets as `[OK]`. With the default commercial-safe configuration, the object detector is DETR (`facebook/detr-resnet-50`) and the Ultralytics/YOLO cache may be empty.

```
=====================================================
  Forensic Council — Startup Cache Check
=====================================================

━━━  ML Model Cache Status  ━━━
  [OK]     HuggingFace  xxxx.x MB  (N files)  /app/cache/huggingface
  [OK]     PyTorch       xxx.x MB  (N files)  /app/cache/torch
  [OK]     EasyOCR        xx.x MB  (N files)  /app/cache/easyocr
  [OK]     YOLO            0.0 MB  (0 files)  /app/cache/ultralytics
```

To check the individual model artifacts without downloading:

```bash
# Check backend container model presence
docker exec forensic_api python scripts/model_pre_download.py --check --strict

# Check worker container model presence
docker exec forensic_worker python scripts/model_pre_download.py --check --strict
```

The default model set is DETR object detection, EasyOCR, OpenCLIP/SigLIP, ResNet-50, SpeechBrain ECAPA, and the configured audio deepfake detector. The full model list and their required conditions are documented in [MODEL_REGISTRY.md](../docs/MODEL_REGISTRY.md).

If any model shows `MISS`, trigger a forced re-download:

```bash
docker exec forensic_api python scripts/model_pre_download.py --force
```

To check raw volume disk usage:

```bash
docker system df -v | grep forensic-council
```

Or per-volume:

```bash
# List all Forensic Council volumes with sizes
docker volume ls --filter name=forensic-council \
  --format '{{.Name}}' | \
  xargs -I{} sh -c 'echo -n "{}: "; docker run --rm -v {}:/v alpine du -sh /v 2>/dev/null | cut -f1'
```

---

## 7. Container Health Reference

### Recommended: Automated health wait
To wait for all services to start and pass their health checks in a structured manner (with a 15-minute timeout), run from the repository root:
```bash
# Developer mode
bash scripts/_wait_healthy.sh dev

# Production mode
bash scripts/_wait_healthy.sh prod
```

### Manual health wait loop
```bash
# Poll until every container is healthy (timeout 10 minutes)
end=$((SECONDS + 600))
while [ $SECONDS -lt $end ]; do
  unhealthy=$(docker ps --filter health=unhealthy --filter name=forensic --format '{{.Names}}')
  starting=$(docker ps --filter health=starting --filter name=forensic --format '{{.Names}}')
  [ -z "$unhealthy" ] && [ -z "$starting" ] && echo "All healthy." && break
  echo "Waiting... starting: $starting  unhealthy: $unhealthy"
  sleep 10
done
```

### Manual health checks

```bash
# Backend API (direct port — only works with dev overlay)
curl -s http://localhost:8000/health | python -m json.tool

# Backend API via Caddy (works without dev overlay)
curl -s http://localhost/health | python -m json.tool

# Frontend
curl -sI http://localhost:3000/ | head -1

# Redis (inside container; REDISCLI_AUTH is set by compose)
docker exec forensic_redis redis-cli ping

# PostgreSQL (inside container)
docker exec forensic_postgres pg_isready -U forensic_user -d forensic_council

# Qdrant (port not exposed to host — run inside container)
docker exec forensic_qdrant wget -qO- http://localhost:6333/healthz
```

### Expected container states after startup

| Container | Expected state | Notes |
|-----------|---------------|-------|
| `forensic_postgres` | `healthy` | |
| `forensic_redis` | `healthy` | |
| `forensic_qdrant` | `healthy` | |
| `forensic_jaeger` | `healthy` | |
| `forensic_migration` | `exited (0)` | Runs once — exit 0 is correct |
| `forensic_api` | `healthy` | 120 s start period |
| `forensic_worker` | `healthy` | 300 s start period |
| `forensic_ui` | `healthy` | 180 s start period (Next.js compilation) |
| `forensic_caddy` | `healthy` | |
| `forensic_prometheus` | `healthy` | |

---

## 8. Per-Service Rebuild

Rebuild and restart one service without stopping the rest of the stack:

```bash
# Developer — rebuild backend only
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env \
  build backend

docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env \
  up -d --no-deps backend

# Developer — rebuild frontend only
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env \
  build frontend

docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env \
  up -d --no-deps frontend

# Developer — restart worker (picks up bind-mounted code changes instantly, bypasses 300s grace period)
bash scripts/dev-restart-worker.sh
```

**Manual worker restart equivalent (bypassing grace period):**
```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env \
  kill -s SIGKILL worker

docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env \
  up -d --no-deps worker
```

> [!WARNING]
> Bypassing the stop grace period with SIGKILL aborts any in-flight agent investigations instantly and can leave database jobs in an orphaned state. Do NOT use this method in production.

---

## 9. Volumes and Cache Reference

### Named volumes (persistent across rebuilds)

| Volume | Path in container | Contents | Safe to delete? |
|--------|------------------|----------|----------------|
| `evidence_data` | `/app/storage/evidence` | Uploaded evidence files | Only if you want to clear all evidence |
| `signing_keys` | `/app/storage/keys` | ECDSA signing key material | **Never** — deleting breaks report verification |
| `postgres_data` | `/var/lib/postgresql/data` | Full database | Deletes all investigations and reports |
| `redis_data` | `/data` | Session/queue state | Safe when no investigations are running |
| `hf_cache` | `/app/cache/huggingface` | HuggingFace models (~2–4 GB) | Triggers re-download |
| `torch_cache` | `/app/cache/torch` | PyTorch checkpoints (~100 MB) | Triggers re-download |
| `easyocr_cache` | `/app/cache/easyocr` | EasyOCR models (~50 MB) | Triggers re-download |
| `yolo_cache` | `/app/cache/ultralytics` | Ultralytics/YOLO weights when `ENABLE_AGPL_MODELS=true` | Triggers re-download |
| `numba_cache` | `/app/cache/numba_cache` | Compiled JIT cache | Safe — rebuilds on next use |
| `calibration_models_cache` | `/app/cache/calibration_models` | Calibration JSON files | Safe — re-seeded from image on next start |

> **Do not run `docker compose down -v`** unless you intend to delete all model downloads and database state. The `-v` flag removes named volumes.

### Cache types

| Layer | What is cached | Cleared by |
|-------|---------------|-----------|
| Docker layer cache | OS packages, pip/npm deps | `docker builder prune` or `--no-cache` |
| BuildKit cache mounts | `uv`, `npm`, Next.js build cache | `docker builder prune` |
| Named volumes | Models, databases, evidence | `docker compose down -v` or `docker volume rm` |

---

## 10. Compose File Reference

| File | Role | Use with |
|------|------|---------|
| `docker-compose.yml` | Base stack — always required | All modes |
| `docker-compose.dev.yml` | Dev host-port overlay — exposes ports 8000, 5432, 6379, 6333/6334 to localhost | Development only |
| `docker-compose.prod.yml` | Production targets, hardened restart, log rotation | Production |

### Build arguments

| Argument | Default | Effect |
|----------|---------|--------|
| `PRELOAD_MODELS=1` | `1` | Downloads all 6 ML models into the image at build time. Clean volume starts hot. |
| `PRELOAD_MODELS=0` | - | Skips build-time download. On container startup, the backend/worker entrypoint downloads any missing required model caches unless `SKIP_MODEL_DOWNLOAD=1` is set. Use `SKIP_MODEL_DOWNLOAD=1` only for CI/offline smoke builds. |
| `YOLO_MODEL_NAME` | `detr-resnet-50` | Object detection model (default Apache-2.0; YOLO requires ENABLE_AGPL_MODELS=true) |
| `AASIST_MODEL_NAME` | `Vansh180/deepfake-audio-wav2vec2` | Audio deepfake model |

Override build args inline:

```bash
docker compose \
  -f infra/docker-compose.yml \
  --env-file .env \
  build --build-arg PRELOAD_MODELS=0 backend worker
```

### Runtime worker mode

`USE_REDIS_WORKER` is for direct host runs and should usually stay `false`.
Docker Compose sets `USE_REDIS_WORKER` inside backend and worker containers from
`DOCKER_USE_REDIS_WORKER`, which defaults to `true`. This keeps host-local
development ergonomic while ensuring the Docker worker service consumes queued
investigations.

### Host-run infrastructure ports

The optional `infra/docker-compose.dev.yml` override exposes Postgres `5432`,
Redis `6379`, and Qdrant `6333/6334` so you can run
`uv run python scripts/run_api.py` outside Docker against Docker-managed
infrastructure. The base and production stacks keep database, cache, and vector
services internal.

### Operational Note: Worker Warm-up Coupling

In `infra/docker-compose.yml`, Caddy’s startup is coupled to the background worker (`depends_on.worker.condition: service_healthy`). When starting up the first time (especially with model downloads active), the worker’s model warm-up phase can take time. Because Caddy waits for the worker to become healthy before routing public traffic, this coupling is intentional to guarantee that all analytical agents are fully loaded and warm before the API accepts incoming evidence uploads.

### Security invariant: read-only filesystem

The backend and worker services use `read_only: true` with a `tmpfs: /tmp` mount. This configuration:

- Blocks writes to the root filesystem and all paths except `/tmp` and mounted volumes.
- Requires `PYTHONDONTWRITEBYTECODE=1` (set in docker-compose.yml line 88) to prevent `.pyc` writes to `/app/__pycache__/`.
- Requires that all writable paths (model caches, evidence storage, signing keys) be mounted as volumes.

**Never remove `PYTHONDONTWRITEBYTECODE=1` without also removing `read_only: true`** from the backend/worker services, or the container will fail at startup when Python attempts to write bytecode.

---

## 11. Teardown

### Pause and Resume (Recommended for daily pauses)
Use `stop` to pause running containers without removing them. This preserves local caches, anonymous volumes, and Next.js HMR state.
```bash
# Pause the stack
docker compose -f infra/docker-compose.yml --env-file .env stop

# Resume the stack instantly
docker compose -f infra/docker-compose.yml --env-file .env start
```

### Stop containers, keep volumes
Use `down` to stop and remove containers. This is slower to resume because containers must be recreated on next `up`.
```bash
docker compose -f infra/docker-compose.yml --env-file .env down
```

### Stop and remove all volumes (⚠ deletes models and data)
```bash
docker compose -f infra/docker-compose.yml --env-file .env down -v
```
> [!WARNING]
> Only use `-v` when you want a completely clean state — it deletes the database, all uploaded evidence files, and all downloaded ML model weights.

### Remove only model volumes (re-download on next start)
```bash
docker volume rm \
  forensic-council_hf_cache \
  forensic-council_torch_cache \
  forensic-council_easyocr_cache \
  forensic-council_yolo_cache \
  forensic-council_numba_cache \
  forensic-council_calibration_models_cache
```

### Remove only the database volume
```bash
docker volume rm forensic-council_postgres_data forensic-council_redis_data
```

### Full Clean / Nuclear Reset
When troubleshooting stubborn cache conflicts or performing a complete environment refresh, run this exact sequence:

```bash
# Step 1 — Stop containers and destroy all volumes (evidence, databases, and model weights)
docker compose -f infra/docker-compose.yml --env-file .env down -v

# Step 2 — Purge Docker BuildKit cache layers
docker builder prune -f

# Step 3 — Clean local developer workspace build artifacts (bytecode, Next.js cache, etc.)
bash scripts/clean_project.sh

# Step 4 — Deep clean host model caches
bash scripts/clean_project.sh --deep

# Step 5 — Boot fresh developer stack (re-verifies, downloads models, and starts)
bash scripts/dev.sh
```
> [!CAUTION]
> This destroys all evidence files, database records, downloaded model weights (~15–40 GB), and the ECDSA keys. Reports generated before this reset will fail cryptographic signature verification since the keys will be regenerated.

---

## 12. Troubleshooting

### Quick diagnostics (run this first)
To automatically inspect container health, capture logs of unhealthy services, check disk volumes, and report system settings:
```bash
bash scripts/troubleshoot.sh
```

### Models download again after every restart

`docker compose down -v` was run and removed the model volumes. Let them download once, then stop using `-v`. Named volumes persist across `docker compose down` (without `-v`) and across image rebuilds.

### `PRELOAD_MODELS=1` in `.env` but models not baked in

The Dockerfile checks `if [ "$PRELOAD_MODELS" = "1" ]` (exact string `1`). Ensure `.env` has `PRELOAD_MODELS=1`, not `PRELOAD_MODELS=true`.

### Frontend shows stale API URL / old environment values

`NEXT_PUBLIC_*` variables are baked into the JS bundle at build time. Changing `.env` after build has no effect until you rebuild the frontend image:

```bash
docker compose \
  -f infra/docker-compose.yml \
  --env-file .env \
  build --no-cache frontend

docker compose \
  -f infra/docker-compose.yml \
  --env-file .env \
  up -d --no-deps frontend
```

### Backend returns 503 on startup

The backend waits for Postgres, Redis, and Qdrant to pass health checks before starting. Check infra container states:

```bash
docker ps --filter name=forensic_postgres --filter name=forensic_redis --filter name=forensic_qdrant
```

If any infra container is `unhealthy`, inspect its logs:

```bash
docker logs forensic_postgres --tail 30
docker logs forensic_redis --tail 30
```

### `REDIS_PASSWORD must be set` on compose up

The base compose file uses `:?` syntax for required variables. Ensure your `.env` file exists, is in the repo root (not inside `infra/`), and the `--env-file .env` flag is present in the command.

### Backend hot-reload not picking up changes

Use the dev overlay (`-f infra/docker-compose.dev.yml`) for development. It mounts the backend source subdirectories and sets `WATCHFILES_FORCE_POLLING=true`, which lets uvicorn detect file changes on Windows Docker bind mounts.

### Prometheus cannot scrape backend metrics

`METRICS_SCRAPE_TOKEN` must be set in `.env`, passed through `docker-compose.yml` as a secret, and referenced in `infra/prometheus.yml`. Verify:

```bash
# Check secret is mounted
docker exec forensic_api cat /run/secrets/metrics_scrape_token

# Test scrape endpoint manually
curl -H "Authorization: Bearer $(cat .env | grep METRICS_SCRAPE_TOKEN | cut -d= -f2)" \
  http://localhost:8000/api/v1/metrics/raw
```

### Production: Let's Encrypt certificate not issuing

- Ensure `DOMAIN` in `.env` is a real public hostname (not `localhost`).
- Port 80 and 443 must be open on your server's firewall and reachable from the internet.
- `ACME_EMAIL` must be set — Caddy requires it for ACME registration.
- Check Caddy logs: `docker logs forensic_caddy --tail 50`

### View effective merged compose config

Useful for debugging volume and environment variable inheritance:

```bash
# Developer
docker compose \
  -f infra/docker-compose.yml \
  --env-file .env \
  config

# Production
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.prod.yml \
  --env-file .env \
  config
```

### Disk usage summary

```bash
docker system df -v
docker builder du
docker volume ls --filter name=forensic-council
```

---

## 13. Host-Run Development (API + Frontend on Host, Infra in Docker)

Use this when you want faster Python iteration without rebuilding the backend image.

### Step 1 — Start only infra services

```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env \
  up -d redis postgres qdrant
```

### Step 2 — Configure host environment

```bash
cp .env.host.example .env.host
# Edit .env.host: set POSTGRES_HOST=localhost, REDIS_HOST=localhost, QDRANT_HOST=localhost
```

### Step 3 — Start the API on host

```bash
cd apps/api
uv sync --locked --extra dev --extra observability --extra security
uv run scripts/run_api.py
```

### Step 4 — Start the frontend on host

```bash
cd apps/web
npm ci
npm run dev
```

The frontend dev server runs at `http://localhost:3000` and the API at `http://localhost:8000`.
Note: Caddy is not in the loop for this mode; `NEXT_PUBLIC_API_URL=http://localhost:8000` in `.env.host`.
