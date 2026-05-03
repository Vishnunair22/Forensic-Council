# Forensic Council — Docker Build Guide

Complete reference for building, running, and verifying the Forensic Council stack in both **developer** and **production** modes.

> **Shell syntax note:** All multi-line commands below use `\` (Unix/Git Bash/WSL2).
> On **Windows PowerShell**, replace each `\` with a backtick `` ` ``.

---

## Table of Contents

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

### Step 1 — Build and start

```bash
docker compose \
  -f infra/docker-compose.yml \
  --env-file .env \
  up --build
```

The first build downloads OS packages, Python dependencies, and ML model weights into the image. Expect **15–40 minutes** depending on your network speed. Subsequent builds use Docker layer cache and finish in under a minute.

**To run in the background (detached):**
```bash
docker compose \
  -f infra/docker-compose.yml \
  --env-file .env \
  up --build -d
```

### Step 2 — Monitor build and startup logs

Open a second terminal while the build runs:

```bash
# All services
docker compose \
  -f infra/docker-compose.yml \
  --env-file .env \
  logs -f

# Single service
docker compose -f infra/docker-compose.yml logs -f backend
docker compose -f infra/docker-compose.yml logs -f worker
docker compose -f infra/docker-compose.yml logs -f frontend
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

### Step 3 — Confirm all containers are healthy

```bash
docker compose \
  -f infra/docker-compose.yml \
  --env-file .env \
  ps
```

All services should show `healthy` or `running`. The `migration` service will show `exited (0)` — that is correct (it runs once then stops).

Quick status table:
```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

### Step 4 — Verify ML models downloaded

See [Section 6](#6-verifying-model-downloads).

### Step 5 — Open the app

| URL | What |
|-----|------|
| `http://localhost:80` | Caddy proxy — recommended entry point (frontend + API) |
| `http://localhost:3000` | Frontend direct |
| `http://localhost:8000` | Backend API direct |
| `http://localhost:8000/docs` | FastAPI interactive docs (Swagger UI) |
| `http://localhost:16686` | Jaeger distributed tracing UI |
| `http://localhost:9090` | Prometheus metrics UI |

Click **Demo Login** on the landing page to authenticate as the investigator user. The demo route uses `BOOTSTRAP_INVESTIGATOR_PASSWORD` from your `.env` — the placeholder value works out of the box because the migration creates the user with that same password.

### Hot-reload behaviour

| Service | Trigger | Behaviour |
|---------|---------|-----------|
| **Frontend** | Save any `.tsx`, `.ts`, `.css` file | Turbopack HMR updates the browser in ~500 ms |
| **Backend** | Save any `.py` file in `api/`, `core/`, `agents/`, `tools/`, `orchestration/` | uvicorn `--reload` restarts the server in ~1 s |
| **Worker** | Save any `.py` file | Code is live in the container; run `docker compose restart worker` to apply |

---

## 4. Production Mode

### Step 1 — Generate strong secrets

Run this once from the **repo root**. It prints all required secret values to stdout — copy them into your `.env` file:

```bash
bash infra/generate_production_keys.sh
```

> On Windows without Git Bash/WSL2: run the script in Git Bash or WSL2, then paste the output values into your `.env` file manually.

### Step 2 — Configure production-specific settings

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

### Step 3 — Validate production readiness

```bash
bash infra/validate_production_readiness.sh
```

All `FAIL` lines must be resolved before starting in production. `WARN` lines are informational.

### Step 4 — Build and start

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

### Step 5 — Monitor startup

```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.prod.yml \
  --env-file .env \
  logs -f
```

### Step 6 — Confirm all containers are healthy

```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.prod.yml \
  --env-file .env \
  ps
```

### Step 7 — Verify ML models

See [Section 6](#6-verifying-model-downloads).

### Step 8 — Open the app

```
https://forensic.yourdomain.com
```

Caddy obtains a Let's Encrypt TLS certificate automatically on first request to a real domain. Allow up to 60 seconds for ACME issuance.

---

## 5. No-Cache Rebuild

Use this when Docker layer cache is stale (e.g. base image updated, dependency version changes, Dockerfile modified).

**Keeps all named volumes** (databases, model weights, evidence files are preserved).

### Developer no-cache rebuild

```bash
docker compose \
  -f infra/docker-compose.yml \
  --env-file .env \
  build --no-cache

docker compose \
  -f infra/docker-compose.yml \
  --env-file .env \
  up -d
```

### Production no-cache rebuild

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

### No-cache rebuild for a single service

```bash
# Backend only (developer)
docker compose \
  -f infra/docker-compose.yml \
  --env-file .env \
  build --no-cache backend

docker compose \
  -f infra/docker-compose.yml \
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

After the stack starts, confirm that all six ML models loaded correctly. Run this against the backend or worker container:

```bash
docker exec forensic_api python scripts/model_cache_check.py
```

Expected output (all lines should show `populated`, not `empty`):

```
=====================================================
  Forensic Council — Startup Cache Check
=====================================================

━━━  ML Model Cache Status  ━━━
  [OK]     HuggingFace  xxxx.x MB  (N files)  /app/cache/huggingface
  [OK]     PyTorch       xxx.x MB  (N files)  /app/cache/torch
  [OK]     EasyOCR        xx.x MB  (N files)  /app/cache/easyocr
  [OK]     YOLO            x.x MB  (N files)  /app/cache/ultralytics
```

To check the six individual models (YOLO, EasyOCR, OpenCLIP, ResNet-50, SpeechBrain, audio deepfake detector):

```bash
# Prints per-model SKIP (cached) or WARN (missing) lines
docker exec forensic_api python scripts/model_pre_download.py
```

If any model shows `WARN`, trigger a forced re-download:

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

### Wait for all services to become healthy

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
# Backend API
curl -s http://localhost:8000/health | python -m json.tool

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
| `forensic_api` | `healthy` | 45 s start period |
| `forensic_worker` | `healthy` | 60 s start period |
| `forensic_ui` | `healthy` | 60–300 s start period (Next.js compilation) |
| `forensic_caddy` | `healthy` | |
| `forensic_prometheus` | `healthy` | |

---

## 8. Per-Service Rebuild

Rebuild and restart one service without stopping the rest of the stack:

```bash
# Developer — rebuild backend only
docker compose \
  -f infra/docker-compose.yml \
  --env-file .env \
  build backend

docker compose \
  -f infra/docker-compose.yml \
  --env-file .env \
  up -d --no-deps backend

# Developer — rebuild frontend only
docker compose \
  -f infra/docker-compose.yml \
  --env-file .env \
  build frontend

docker compose \
  -f infra/docker-compose.yml \
  --env-file .env \
  up -d --no-deps frontend

# Restart worker (picks up bind-mounted code changes)
docker compose -f infra/docker-compose.yml restart worker
```

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
| `yolo_cache` | `/app/cache/ultralytics` | YOLO weights (~6 MB) | Triggers re-download |
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
| `docker-compose.prod.yml` | Production targets, hardened restart, log rotation | Production |

### Build arguments

| Argument | Default | Effect |
|----------|---------|--------|
| `PRELOAD_MODELS=1` | `1` | Downloads all 6 ML models into the image at build time. Clean volume starts hot. |
| `PRELOAD_MODELS=0` | — | Skips build-time download. Models are fetched lazily on first use (adds 3–10 min to first investigation). Use in CI. |
| `YOLO_MODEL_NAME` | `yolo11n.pt` | YOLO weight filename |
| `AASIST_MODEL_NAME` | `Vansh180/deepfake-audio-wav2vec2` | Audio deepfake model |

Override build args inline:

```bash
docker compose \
  -f infra/docker-compose.yml \
  --env-file .env \
  build --build-arg PRELOAD_MODELS=0 backend worker
```

---

## 11. Teardown

### Stop containers, keep volumes

```bash
docker compose -f infra/docker-compose.yml --env-file .env down
```

### Stop and remove all volumes (⚠ deletes models and data)

```bash
docker compose -f infra/docker-compose.yml --env-file .env down -v
```

Only use `-v` when you want a completely clean state — it deletes the database, all evidence files, and all downloaded ML model weights.

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

---

## 12. Troubleshooting

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

Use the base compose file (`-f infra/docker-compose.yml`) for development. It mounts the backend source subdirectories and sets `WATCHFILES_FORCE_POLLING=true`, which lets uvicorn detect file changes on Windows Docker bind mounts.

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
