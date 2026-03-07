# Forensic Council — Startup Guide

> **Version:** v1.0.0 | **Last Updated:** 2026-03-07
>
> This is the single source of truth for building and running Forensic Council in Docker.
> Follow it step-by-step for a guaranteed working deployment from scratch.
>
> 📖 For detailed build/rebuild/caching strategies, see **[docs/docker/DOCKER_BUILD.md](../docker/DOCKER_BUILD.md)**.

---

## Table of Contents

1. [Step 0 — Prerequisites](#step-0--prerequisites)
2. [Section A — Fresh Build (First-Time / Full Clean Start)](#section-a--fresh-build-first-time--full-clean-start)
3. [Section B — Production Mode](#section-b--production-mode)
4. [Section C — Development Mode (Hot Reload)](#section-c--development-mode-hot-reload)
5. [Section D — No-Cache Rebuild (Frontend / Backend / Both)](#section-d--no-cache-rebuild-frontend--backend--both)
6. [Model Cache Behaviour](#model-cache-behaviour)
7. [Access Points & Demo Login](#access-points--demo-login)
8. [Docker Compose Files Reference](#docker-compose-files-reference)
9. [Makefile Shortcuts](#makefile-shortcuts)
10. [Troubleshooting](#troubleshooting)
11. [Incident Response](#incident-response)

---

## Step 0 — Prerequisites

Before doing anything, verify the required tools are installed.

### Required (Docker-only deployment)

| Tool | Minimum Version | Check Command |
|------|----------------|---------------|
| Docker Desktop | 24+ | `docker --version` |
| Docker Compose v2 | bundled with Desktop | `docker compose version` |

> **Windows/WSL2:** Docker Desktop must be running and WSL2 integration enabled.

### Optional (native development without Docker)

| Tool | Version | Check Command |
|------|---------|---------------|
| Python | 3.12+ | `python --version` |
| Node.js | 22+ | `node --version` |
| uv | 0.7+ | `uv --version` |

---

## Section A — Fresh Build (First-Time / Full Clean Start)

> Use this when setting up for the **first time**, or when you want a completely clean slate — no leftover containers, volumes, images, or stale data.

### A.1 — Check for Existing Docker Resources

```bash
# Check running containers
docker ps --filter "name=forensic_" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Check stopped containers
docker ps -a --filter "name=forensic_" --format "table {{.Names}}\t{{.Status}}"

# Check volumes (look for names starting with "forensic-council-main_")
docker volume ls | grep forensic

# Check images
docker images | grep forensic
```

⏱️ **~2 seconds.** If everything is empty, skip to A.3. If resources exist, continue to A.2.

---

### A.2 — Stop and Remove Existing Resources

```bash
# Stop all services and remove containers + orphans
docker compose -f docs/docker/docker-compose.yml --env-file .env down --remove-orphans 2>/dev/null

# Also stop infra-only stack if it was used
docker compose -f docs/docker/docker-compose.infra.yml --env-file .env down --remove-orphans 2>/dev/null

# Force-remove any leftover forensic containers
docker ps -aq --filter "name=forensic_" | xargs -r docker stop
docker ps -aq --filter "name=forensic_" | xargs -r docker rm

# Remove all volumes (DELETES DB data, ML model caches, evidence files)
docker compose -f docs/docker/docker-compose.yml --env-file .env down -v --remove-orphans

# Remove built images
docker images --format "{{.Repository}}:{{.Tag}}" | grep forensic | xargs -r docker rmi

# Prune all build cache, dangling images, unused networks
docker system prune -a --volumes -f
```

⏱️ **~30–60 seconds.**

> **Windows PowerShell alternative for force-removing containers:**
> ```powershell
> docker ps -aq --filter "name=forensic_" | ForEach-Object { docker stop $_; docker rm $_ }
> ```

---

### A.3 — Verify Clean State

```bash
# All three commands should return NO output
docker ps -a --filter "name=forensic_" --format "{{.Names}}"
docker volume ls | grep forensic
docker images | grep forensic
```

⏱️ **~2 seconds.** All must return **empty output** before continuing.

---

### A.4 — Create Environment Files

From the **project root** directory:

```bash
cp .env.example .env
cp backend/.env.example backend/.env
```

Then open `.env` and **verify these critical variables**:

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `SIGNING_KEY` | ✅ Yes | `dev-placeholder-...` | Change for production. Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `POSTGRES_PASSWORD` | ✅ Yes | `forensic_pass` | Change for production |
| `NEXT_PUBLIC_DEMO_PASSWORD` | ✅ Yes | `inv123!` | Demo login password |
| `NEXT_PUBLIC_API_URL` | ✅ Yes | `http://localhost:8000` | Must be reachable from the browser |
| `HF_TOKEN` | Optional | empty | Required for Agent 2 speaker diarization. Free at https://hf.co/settings/tokens |
| `LLM_PROVIDER` | Optional | `none` | Set to `openai` or `anthropic` + add `LLM_API_KEY` to enable LLM reasoning |

> **Tip:** For local development the defaults work out-of-the-box. No changes needed.

---

### A.5 — Build and Start All Services

```bash
docker compose -f docs/docker/docker-compose.yml --env-file .env up -d --build
```

**What gets built:**

| Service | Image | First Build | Subsequent |
|---------|-------|------------|------------|
| `backend` | `python:3.11-slim` | ~3–5 min | ~30s (layer cache) |
| `frontend` | `node:20-alpine` | ~2–3 min | ~30s (layer cache) |
| `redis` | `redis:7-alpine` | ~5s (pull) | instant |
| `postgres` | `postgres:16-alpine` | ~5s (pull) | instant |
| `qdrant` | `qdrant/qdrant:v1.11.0` | ~10s (pull) | instant |

**Startup order** (enforced by `depends_on` + healthchecks):
```
1. redis       → healthcheck: redis-cli ping           (~5s)
2. postgres    → healthcheck: pg_isready               (~5s)
3. qdrant      → healthcheck: TCP port 6333            (~10s)
4. backend     → waits for all 3 infra to be healthy   (~15s after infra)
                → auto-runs DB schema init + migrations
5. frontend    → waits for backend to be healthy        (~30s after backend)
```

⏱️ **First build:** ~5–8 minutes total. **Subsequent starts:** ~60 seconds.

---

### A.6 — Verify Healthy Containers

```bash
docker compose -f docs/docker/docker-compose.yml --env-file .env ps
```

**Expected output (all services `Up (healthy)`):**

```
NAME               STATUS                    PORTS
forensic_api       Up (healthy)              0.0.0.0:8000->8000/tcp
forensic_ui        Up (healthy)              0.0.0.0:3000->3000/tcp
forensic_redis     Up (healthy)
forensic_postgres  Up (healthy)
forensic_qdrant    Up (healthy)
```

**Verify HTTP endpoints:**

```bash
# Backend health — expect: {"status": "healthy", ...}
curl http://localhost:8000/health

# Backend root — expect: {"name": "Forensic Council API", "version": "1.0.0", ...}
curl http://localhost:8000/

# Frontend — expect: 200
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
```

**Open the app:** http://localhost:3000
**Demo login:** Username `investigator` · Password `inv123!` (auto-login is enabled).

---

## Section B — Production Mode

> Production mode uses the same Docker images as Section A but with hardened settings:
> `APP_ENV=production`, `DEBUG=false`, no Swagger docs, Caddy TLS proxy.

### B.1 — Set Production Environment

Edit `.env` and change:

```bash
APP_ENV=production
DEBUG=false
LOG_LEVEL=WARNING
SIGNING_KEY=<generate: python -c "import secrets; print(secrets.token_hex(32))">
POSTGRES_PASSWORD=<strong-unique-password-16-chars-min>
NEXT_PUBLIC_API_URL=https://your-domain.com   # or http://your-server-ip:8000
DOMAIN=your-domain.com                         # for Caddy HTTPS
```

### B.2 — Build and Start Production Stack

```bash
docker compose \
  -f docs/docker/docker-compose.yml \
  -f docs/docker/docker-compose.prod.yml \
  --env-file .env \
  up -d --build
```

This adds Caddy as a reverse proxy on ports 80/443 with automatic HTTPS (Let's Encrypt).

⏱️ **~5–8 minutes first build, ~60 seconds subsequent.**

### B.3 — Verify Production Stack

```bash
docker compose \
  -f docs/docker/docker-compose.yml \
  -f docs/docker/docker-compose.prod.yml \
  --env-file .env ps
```

Expected: All 6 services (redis, postgres, qdrant, backend, frontend, caddy) show `Up (healthy)`.

---

## Section C — Development Mode (Hot Reload)

> Use this for active development. **Both backend and frontend auto-reload on file save** — no manual rebuild needed.

### C.1 — Start Dev Stack

```bash
docker compose \
  -f docs/docker/docker-compose.yml \
  -f docs/docker/docker-compose.dev.yml \
  --env-file .env \
  up -d --build
```

Or with the Makefile shortcut: `make dev`

⏱️ **First build:** ~5–8 min. **Subsequent:** ~30 seconds.

### C.2 — What's Different in Dev Mode

| Feature | Production Build | Dev Mode |
|---------|-----------------|----------|
| **Frontend Dockerfile** | `Dockerfile` (`next build` → standalone) | `Dockerfile.dev` (`npm run dev`) |
| **Frontend Hot Reload** | ❌ | ✅ Edit `src/` → instant browser refresh |
| **Backend Hot Reload** | ❌ | ✅ Edit `.py` → Uvicorn auto-restarts in ~2s |
| **Backend Debug Mode** | `DEBUG=false` | `DEBUG=true`, `LOG_LEVEL=DEBUG` |
| **Backend Read-Only FS** | `read_only: true` | `read_only: false` (Uvicorn writes `.pyc`) |
| **ML Model Caches** | Named volumes | Same named volumes (models cached identically) |
| **Source Code** | Baked into image | Bind-mounted from host |

### C.3 — Hot Reload: What Triggers What

| Change | Effect | Action Needed |
|--------|--------|---------------|
| Edit `frontend/src/**/*.tsx` | Next.js Fast Refresh | None — auto-reloads in browser |
| Edit `frontend/public/**` | Static files updated | None — auto-served |
| Edit `backend/**/*.py` | Uvicorn auto-restarts | None — wait ~2s |
| Edit `frontend/package.json` | Dependencies changed | Rebuild: `docker compose ... build frontend` |
| Edit `backend/pyproject.toml` | Dependencies changed | Rebuild: `docker compose ... build backend` |
| Edit any `Dockerfile` | Image definition changed | Rebuild the affected service |

### C.4 — View Logs

```bash
# All services
docker compose -f docs/docker/docker-compose.yml -f docs/docker/docker-compose.dev.yml --env-file .env logs -f

# Backend only (watch for reload messages)
docker compose -f docs/docker/docker-compose.yml -f docs/docker/docker-compose.dev.yml --env-file .env logs -f backend

# Frontend only (watch for compile messages)
docker compose -f docs/docker/docker-compose.yml -f docs/docker/docker-compose.dev.yml --env-file .env logs -f frontend
```

### C.5 — Stop Dev Stack

```bash
docker compose -f docs/docker/docker-compose.yml -f docs/docker/docker-compose.dev.yml --env-file .env down
```

---

## Section D — No-Cache Rebuild (Frontend / Backend / Both)

> Use this when you've changed `package.json`, `pyproject.toml`, a `Dockerfile`, or need to force a clean rebuild without wiping database data.

### ⚠️ Model Cache Preserved

`--no-cache` only clears the **Docker layer build cache** (pip/apt/npm installs). It does **NOT** delete named volumes. Your downloaded ML models (`hf_cache`, `torch_cache`, `yolo_cache`, etc.) are safe and will **not** be re-downloaded. Models only re-download if you explicitly run `docker compose down -v`.

---

### Rebuild Frontend Only (no cache)

```bash
docker compose -f docs/docker/docker-compose.yml --env-file .env build --no-cache frontend
docker compose -f docs/docker/docker-compose.yml --env-file .env up -d frontend
```

⏱️ ~2–3 minutes.

---

### Rebuild Backend Only (no cache)

```bash
docker compose -f docs/docker/docker-compose.yml --env-file .env build --no-cache backend
docker compose -f docs/docker/docker-compose.yml --env-file .env up -d backend
```

⏱️ ~3–5 minutes (includes Python dependency installation).

---

### Rebuild Both (no cache)

```bash
docker compose -f docs/docker/docker-compose.yml --env-file .env build --no-cache backend frontend
docker compose -f docs/docker/docker-compose.yml --env-file .env up -d
```

⏱️ ~5–8 minutes.

---

### Verify After Rebuild

```bash
# All services Up (healthy)
docker compose -f docs/docker/docker-compose.yml --env-file .env ps

# Backend health
curl http://localhost:8000/health

# Frontend
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
```

---

## Groq LLM Setup (Recommended)

Forensic Council uses an LLM to power each agent's ReAct reasoning loop and
to write the Arbiter's executive summary. **Groq with Llama 3.3 70B is the
recommended provider** — ~700 tokens/second, free tier, full function-calling.

### Quick setup (5 minutes)

1. Get a free API key at [console.groq.com/keys](https://console.groq.com/keys)
2. Add to your `.env`:

```env
LLM_PROVIDER=groq
LLM_API_KEY=gsk_your_key_here
LLM_MODEL=llama-3.3-70b-versatile
```

3. Restart backend: `docker compose restart backend`

### What the LLM does

| Component | With LLM | Without LLM (`LLM_PROVIDER=none`) |
|-----------|----------|------------------------------------|
| Agent ReAct loops | LLM selects tools, interprets results, reasons about anomalies | Deterministic task→tool mapping |
| Arbiter summary | LLM-written forensic prose with confidence analysis | Short template paragraph |
| Arbiter uncertainty | Legally-aware limitations statement | Template sentence |

All forensic analysis tools (ELA, EasyOCR, MediaInfo, DeepFace, etc.) run regardless
of LLM configuration — only the narrative reasoning layer changes.

### Alternative providers

```env
LLM_PROVIDER=openai     LLM_MODEL=gpt-4o
LLM_PROVIDER=anthropic  LLM_MODEL=claude-3-5-sonnet-20241022
LLM_PROVIDER=none       # Disable LLM entirely
```

---

## Model Cache Behaviour

Forensic Council downloads large ML models (HuggingFace transformers, PyTorch weights, YOLO, DeepFace, EasyOCR) on first use. These are stored in Docker named volumes:

| Volume | Path in container | Contents |
|--------|------------------|----------|
| `hf_cache` | `/app/cache/huggingface` | HuggingFace models (Transformers, Pyannote) |
| `torch_cache` | `/app/cache/torch` | PyTorch model weights |
| `yolo_cache` | `/app/cache/ultralytics` | YOLO v8 weights |
| `deepface_cache` | `/app/cache/deepface` | DeepFace models |
| `numba_cache` | `/app/cache/numba_cache` | Numba JIT compilation cache |
| `calibration_models` | `/app/cache/calibration_models` | Calibration model weights |
| `easyocr_cache` | `/app/cache/easyocr` | EasyOCR neural OCR model (~100MB) |

### Dev and prod share the same volumes

All compose files pin `name: forensic-council` and all `.env` files set
`COMPOSE_PROJECT_NAME=forensic-council`. This guarantees that `make dev` and `make up`
use identical volume names — models downloaded in dev are available in prod and vice versa.
**Models are never downloaded twice.**

```bash
# Check which model volumes exist and their sizes
make cache-status
```

### Startup cache check

Every container start runs `scripts/model_cache_check.py` before the API server.
It reports the state of every cache directory and verifies core Python imports (~3s).
Empty caches are reported as warnings — the API still starts normally and models
download on first use.

**These volumes persist across:**
- `docker compose down` (stop without `-v`)
- `docker compose up --build` (rebuild images)
- `--no-cache` rebuilds
- Container restarts
- Switching between `make dev` and `make up`

**These volumes are wiped only by:**
- `docker compose down -v` (the `-v` flag)
- `docker system prune --volumes`
- `make down-clean` (asks for confirmation)

> **First investigation after fresh install** will be slower as models download. Subsequent investigations are fast.

---

## Access Points & Demo Login

| Service | URL | Notes |
|---------|-----|-------|
| 🌐 **Frontend** | http://localhost:3000 | Main application UI |
| 🔌 **Backend API** | http://localhost:8000 | REST API base URL |
| 📚 **Swagger Docs** | http://localhost:8000/docs | Interactive API docs (dev/staging only) |
| 📖 **ReDoc API Docs** | http://localhost:8000/redoc | Alternative API docs (dev/staging only) |
| ❤️ **Health Check** | http://localhost:8000/health | Backend health status |
| 🔗 **Qdrant UI** | http://localhost:6333/dashboard | Vector DB dashboard (dev/infra mode only) |

### Demo Login

- **Username:** `investigator`
- **Password:** value of `NEXT_PUBLIC_DEMO_PASSWORD` in `.env` (default: `inv123!`)
- The frontend **auto-logs in** — no manual login required on first page load.

---

## Docker Compose Files Reference

All compose files are in `docs/docker/`. Always run compose commands from the **project root**.

| File | Purpose | Use Case |
|------|---------|----------|
| `docker-compose.yml` | Base — all 5 services, production Dockerfiles | Required for all modes |
| `docker-compose.dev.yml` | Dev overlay — hot-reload Dockerfiles + volume mounts | Active development |
| `docker-compose.prod.yml` | Prod overlay — hardened settings + Caddy TLS | Production deployment |
| `docker-compose.infra.yml` | Infra only — Redis, Postgres, Qdrant with host ports | Native backend/frontend dev |
| `docker-compose.override.yml` | ⚠️ Deprecated — use `docker-compose.dev.yml` instead | Legacy compatibility only |
| `Caddyfile` | Caddy reverse proxy config | Used by `docker-compose.prod.yml` |

---

## Makefile Shortcuts

Run from the **project root**:

```bash
# ── Start / Stop ─────────────────────────────────────────────────────────
make up                  # Build (if needed) and start all services
make dev                 # Start with hot-reload (backend + frontend)
make infra               # Start databases only (for native development)
make prod                # Production mode with Caddy TLS
make down                # Stop services — model caches PRESERVED ✅
make down-clean          # Stop services and DELETE volumes ⚠️ (requires confirmation)

# ── Smart Rebuilds (model caches always preserved) ────────────────────────
make rebuild             # Auto-detect what changed, rebuild only that service
make rebuild-backend     # Rebuild and restart backend only
make rebuild-frontend    # Rebuild and restart frontend only

# ── ML Model Cache ────────────────────────────────────────────────────────
make cache-status        # Show which model volumes exist and their sizes
make cache-warm          # Run cache check script in a temporary container

# ── Logs / Status ─────────────────────────────────────────────────────────
make logs                # Tail all container logs
make logs-backend        # Tail backend logs only
make logs-frontend       # Tail frontend logs only
make ps                  # Show container status and health

# ── Cleanup ───────────────────────────────────────────────────────────────
make prune               # Remove dangling images (safe — volumes untouched)
make prune-all           # System prune: stopped containers + networks + images
```

---

## Troubleshooting

### "NEXT_PUBLIC_DEMO_PASSWORD not set" error at build time

```bash
# Ensure .env exists and contains NEXT_PUBLIC_DEMO_PASSWORD
cat .env | grep NEXT_PUBLIC_DEMO_PASSWORD
# If missing, copy from template:
cp .env.example .env
```

### Backend keeps restarting

```bash
# Check the error
docker compose -f docs/docker/docker-compose.yml --env-file .env logs backend --tail=50

# Common causes:
# 1. Missing .env file                → cp .env.example .env
# 2. SIGNING_KEY is empty             → check .env
# 3. Infra not healthy yet            → wait 30s and check: docker compose ... ps
# 4. Python import error              → rebuild: docker compose ... build --no-cache backend
```

### Frontend shows blank page

```bash
# Check NEXT_PUBLIC env vars are baked into the image
docker exec forensic_ui printenv | grep NEXT_PUBLIC

# If wrong or missing, force rebuild with correct .env
docker compose -f docs/docker/docker-compose.yml --env-file .env build --no-cache frontend
docker compose -f docs/docker/docker-compose.yml --env-file .env up -d frontend
```

### Database connection refused

```bash
# Check Postgres health
docker inspect forensic_postgres --format='{{.State.Health.Status}}'

# View Postgres logs
docker logs forensic_postgres --tail=20

# If Postgres is healthy but backend still fails, verify env vars:
docker exec forensic_api printenv | grep POSTGRES
```

### Port already in use

```bash
# Find the process using the port (macOS/Linux)
lsof -i :8000
lsof -i :3000

# Windows
netstat -ano | findstr :8000

# Kill the process or change port mapping in docker-compose.yml
```

### Build appears frozen / "Exporting layers" hangs

This is normal during large downloads (Python packages, Node modules). View live progress:

```bash
docker compose -f docs/docker/docker-compose.yml --env-file .env build --progress=plain
```

Without `.dockerignore` files in `backend/` and `frontend/`, Docker sends the entire directory as build context (including `node_modules/`, `.git/`). Ensure `.dockerignore` files exist (they are included in this project).

### ML models downloading on every build

This means Docker named volumes were deleted. After `docker compose down -v` or `docker system prune --volumes`, all model caches are wiped and must re-download on the next investigation. This is expected behavior after a full wipe. See [Model Cache Behaviour](#model-cache-behaviour).

---

## Incident Response

### Redis Memory Bloat (OOM)

If the backend returns `OOM command not allowed`:

```bash
# Check memory usage
docker exec -it forensic_redis redis-cli info memory

# Immediate fix (terminates running investigations)
docker exec -it forensic_redis redis-cli FLUSHDB
```

### WebSocket Hanging (>5 min on "Processing")

An ML subprocess is likely zombie'd:

```bash
docker restart forensic_api
```

Users will see "Connection lost" and need to re-upload their evidence.

### Signing Key Compromise

```bash
# 1. Generate new key
python -c "import secrets; print(secrets.token_hex(32))"

# 2. Update SIGNING_KEY in .env

# 3. Restart backend with new key
docker compose -f docs/docker/docker-compose.yml --env-file .env up -d --force-recreate backend
```

> **Impact:** Previously signed reports will fail verification against the new key. This is intentional.

### Database Corruption / Backup / Recovery

```bash
# Manual DB access
docker exec -it forensic_postgres psql -U forensic_user -d forensic_council

# Backup
docker exec -t forensic_postgres pg_dumpall -c -U forensic_user > dump_$(date +%Y-%m-%d).sql

# Complete reset (destructive — wipes all data and caches)
docker compose -f docs/docker/docker-compose.yml --env-file .env down -v
docker compose -f docs/docker/docker-compose.yml --env-file .env up --build -d
```

---

*For API reference, see [API.md](../API.md).*
*For architecture overview, see [ARCHITECTURE.md](../ARCHITECTURE.md).*
*For error history, see [ERROR_LOG.md](../status/ERROR_LOG.md).*
