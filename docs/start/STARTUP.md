# Forensic Council — Startup Guide

> **Version:** 1.0.0 | **Last Updated:** 2026-03-06
>
> This file is the single source of truth for building and running the Forensic Council app in Docker.
> Give this file to an LLM or follow it step-by-step for a guaranteed working deployment.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Section 1: Fresh Build (Full Clean Start)](#section-1-fresh-build-full-clean-start)
3. [Section 2: No-Cache Rebuild (Frontend / Backend)](#section-2-no-cache-rebuild-frontend--backend)
4. [Section 3: Development Mode (Hot Reload)](#section-3-development-mode-hot-reload)
5. [Access Points](#access-points)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

| Tool | Version | Check Command |
|------|---------|---------------|
| Docker Desktop | 24+ | `docker --version` |
| Docker Compose | v2+ (bundled with Desktop) | `docker compose version` |
| Python | 3.11+ (only for native dev) | `python --version` |
| Node.js | 20+ (only for native dev) | `node --version` |
| uv | 0.6+ (only for native dev) | `uv --version` |

> **Note:** For Docker-only deployment, you only need Docker Desktop. Python/Node/uv are only for native development.

---

## Section 1: Fresh Build (Full Clean Start)

> Use this when you want a **completely clean slate** — no leftover containers, volumes, images, or stale data. This is the recommended path for first-time setup or when something is broken beyond repair.

### Step 1/7 — Check for Existing Docker Resources

```bash
# Check running containers
docker ps --filter "name=forensic_" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Check stopped containers
docker ps -a --filter "name=forensic_" --format "table {{.Names}}\t{{.Status}}"

# Check volumes
docker volume ls --filter "name=docker_" --format "table {{.Name}}\t{{.Driver}}"

# Check images
docker images --filter "reference=docker-*" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
```

⏱️ **Wait:** ~2 seconds. If any results appear, proceed to Step 2. If everything is empty, skip to Step 4.

### Step 2/7 — Stop and Remove All Containers

```bash
# Stop the full-stack compose (catches most containers)
docker compose -f docs/docker/docker-compose.yml --env-file .env down --remove-orphans

# Stop infrastructure-only compose (if used separately)
docker compose -f docs/docker/docker-compose.infra.yml --env-file .env down --remove-orphans 2>$null

# Force stop + remove any remaining forensic containers
docker ps -aq --filter "name=forensic_" | xargs -r docker stop | xargs -r docker rm
# (Windows PowerShell alternative: docker ps -aq --filter "name=forensic_" | ForEach-Object { docker stop $_; docker rm $_ } 2>$null)
```

⏱️ **Wait:** ~10 seconds.

### Step 3/7 — Full Docker Wipe

```bash
# Remove all volumes (deletes DB data, ML model caches, evidence files)
docker compose -f docs/docker/docker-compose.yml --env-file .env down -v --remove-orphans

# Remove built images
docker rmi docker-backend docker-frontend 2>$null

# Prune all build cache, dangling images, and unused networks
docker system prune -a --volumes -f
```

⏱️ **Wait:** ~30-60 seconds.

### Step 4/7 — Verify Clean State

```bash
# All three should return empty
docker ps -a --filter "name=forensic_" --format "{{.Names}}"
docker volume ls --filter "name=docker_" --format "{{.Name}}"
docker images --filter "reference=docker-*" --format "{{.Repository}}"
```

⏱️ **Wait:** ~2 seconds. All commands must return **no output**.

### Step 5/7 — Create Environment Files

```bash
# From the project root directory
cp .env.example .env
cp backend/.env.example backend/.env
```

Then **verify** these critical variables in `.env`:

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `SIGNING_KEY` | ✅ Yes | `dev-placeholder-...` | Must change for production |
| `POSTGRES_PASSWORD` | ✅ Yes | `forensic_pass` | Must change for production |
| `HF_TOKEN` | Optional | empty | Needed for audio speaker diarization |
| `NEXT_PUBLIC_DEMO_PASSWORD` | ✅ Yes | `inv123!` | Demo login password |

> **Tip:** For local development, the defaults work out-of-the-box. No changes needed.

### Step 6/7 — Build and Start All Services

```bash
# Build all images (first build: ~3-5 min, subsequent: ~30s)
docker compose -f docs/docker/docker-compose.yml --env-file .env up -d --build
```

**What gets built:**

| Service | Image | Build Time |
|---------|-------|-----------|
| `backend` | `python:3.11-slim` (Unified Stage) | ~2-3 min | (Does not re-download ML models if volumes exist) |
| `frontend` | `node:20-alpine` (Unified Stage) | ~1-2 min | |
| `redis` | `redis:7-alpine` (pre-built) | ~5 sec | |
| `postgres` | `postgres:16-alpine` (pre-built) | ~5 sec | |
| `qdrant` | `qdrant/qdrant:v1.11.0` (pre-built) | ~10 sec | |

**Startup order** (enforced by `depends_on` + healthchecks):
```
1. redis       → healthcheck: redis-cli ping           (~5s)
2. postgres    → healthcheck: pg_isready                (~5s)
3. qdrant      → healthcheck: TCP port 6333             (~5s)
4. backend     → waits for all 3 infra to be healthy    (~15s)
                → auto-runs DB schema init + migrations
5. frontend    → waits for backend to be healthy         (~30s)
```

⏱️ **Wait:** ~3-5 minutes for first build, then ~60 seconds for containers to become healthy.

### Step 7/7 — Health Check and Access

```bash
# Verify all services are Up and healthy
docker compose -f docs/docker/docker-compose.yml --env-file .env ps
```

**Expected output:**
```
NAME               STATUS                    PORTS
forensic_api       Up (healthy)              0.0.0.0:8000->8000/tcp
forensic_ui        Up (healthy)              0.0.0.0:3000->3000/tcp
forensic_redis     Up (healthy)              0.0.0.0:6379->6379/tcp
forensic_postgres  Up (healthy)              0.0.0.0:5432->5432/tcp
forensic_qdrant    Up (healthy)              0.0.0.0:6333->6333/tcp
```

**Verify HTTP endpoints:**

```bash
# Backend health (expect: {"status": "healthy", ...})
curl http://localhost:8000/health

# Backend root (expect: {"name": "Forensic Council API", "version": "1.0.0", ...})
curl http://localhost:8000/

# Frontend (expect: HTTP 200)
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
```

**Access the app:**

| Service | URL |
|---------|-----|
| 🌐 **Frontend** | http://localhost:3000 |
| 🔌 **Backend API** | http://localhost:8000 |
| 📚 **Swagger Docs** | http://localhost:8000/docs |
| ❤️ **Health Check** | http://localhost:8000/health |

**Demo login:** Username `investigator`, Password `inv123!` (auto-login is enabled).

---

## Section 2: No-Cache Rebuild (Frontend / Backend)

> Use this when you've changed `package.json`, `pyproject.toml`, Dockerfile, or need to force a clean rebuild of specific services **without wiping database data.**
> 
> **💡 Model Cache Preserved:** Using `--no-cache` only clears the Docker build cache (like pip/apt installs). It does **not** delete named volumes. Your downloaded ML models (HuggingFace, PyTorch, YOLO) in `hf_cache`, `torch_cache`, etc. are safe and will NOT be re-downloaded. Models only re-download if you explicitly run `docker compose down -v`.

### Rebuild Frontend Only (no cache)

```bash
# Stop frontend, rebuild from scratch, restart
docker compose -f docs/docker/docker-compose.yml --env-file .env build --no-cache frontend
docker compose -f docs/docker/docker-compose.yml --env-file .env up -d frontend
```

⏱️ **Wait:** ~2-3 minutes.

### Rebuild Backend Only (no cache)

```bash
# Stop backend, rebuild from scratch, restart
docker compose -f docs/docker/docker-compose.yml --env-file .env build --no-cache backend
docker compose -f docs/docker/docker-compose.yml --env-file .env up -d backend
```

⏱️ **Wait:** ~3-5 minutes (includes Python dependency installation).

### Rebuild Both (no cache)

```bash
# Nuclear rebuild of both app services (keeps database volumes)
docker compose -f docs/docker/docker-compose.yml --env-file .env build --no-cache backend frontend
docker compose -f docs/docker/docker-compose.yml --env-file .env up -d
```

⏱️ **Wait:** ~5-8 minutes.

### Verify After Rebuild

```bash
# All services should be Up (healthy)
docker compose -f docs/docker/docker-compose.yml --env-file .env ps

# Check backend health
curl http://localhost:8000/health

# Check frontend
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
```

---

## Section 3: Development Mode (Hot Reload)

> Use this for active development. **Both backend and frontend auto-reload on file save** — no rebuild needed. This is the fastest workflow for day-to-day coding.

### Start Dev Stack

```bash
# Build and start with hot-reload for backend + frontend
docker compose -f docs/docker/docker-compose.yml -f docs/docker/docker-compose.dev.yml --env-file .env up -d --build
```

⏱️ **Wait:** ~3-5 minutes (first build), ~30 seconds (subsequent).

### What's Different in Dev Mode

| Feature | Production Build | Dev Mode |
|---------|-----------------|----------|
| **Frontend Dockerfile** | `Dockerfile` (Unified Stage, `next build`) | `Dockerfile.dev` (1-stage, `npm run dev`) |
| **Frontend Hot Reload** | ❌ No | ✅ Yes (edit `src/` → instant browser refresh) |
| **Backend Hot Reload** | ❌ No | ✅ Yes (edit `.py` → Uvicorn auto-restarts) |
| **Backend Debug Mode** | `DEBUG=false` | `DEBUG=true`, `LOG_LEVEL=DEBUG` |
| **Backend Read-Only FS** | `read_only: true` | `read_only: false` (allows `.pyc` writes) |
| **Volume Mounts** | None (code baked into image) | Source dirs mounted for live sync |

### Hot Reload: What Triggers What

| Change | Effect | Action Needed |
|--------|--------|---------------|
| Edit `frontend/src/**/*.tsx` | Next.js Fast Refresh | None — auto-reloads in browser |
| Edit `frontend/public/**` | Static files updated | None — auto-served |
| Edit `backend/**/*.py` | Uvicorn auto-restarts | None — wait ~2s for restart |
| Edit `frontend/package.json` | Dependencies out of sync | **Rebuild frontend**: `docker compose ... build frontend` |
| Edit `backend/pyproject.toml` | Dependencies out of sync | **Rebuild backend**: `docker compose ... build backend` |
| Edit any `Dockerfile` | Image definition changed | **Rebuild affected service** |

### Health Check (Dev Mode)

```bash
# Verify all services healthy
docker compose -f docs/docker/docker-compose.yml -f docs/docker/docker-compose.dev.yml --env-file .env ps

# Backend health
curl http://localhost:8000/health

# Frontend
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
```

### View Logs (Dev Mode)

```bash
# All services
docker compose -f docs/docker/docker-compose.yml -f docs/docker/docker-compose.dev.yml --env-file .env logs -f

# Just backend (watch for reload messages)
docker compose -f docs/docker/docker-compose.yml -f docs/docker/docker-compose.dev.yml --env-file .env logs -f backend

# Just frontend (watch for compile messages)
docker compose -f docs/docker/docker-compose.yml -f docs/docker/docker-compose.dev.yml --env-file .env logs -f frontend
```

### Stop Dev Stack

```bash
docker compose -f docs/docker/docker-compose.yml -f docs/docker/docker-compose.dev.yml --env-file .env down
```

### Makefile Shortcuts

```bash
make dev          # Build + start dev stack with hot-reload
make up           # Build + start production stack
make infra        # Start databases only (for native dev)
make down         # Stop all containers
make logs         # Tail all logs
make backend      # Run backend natively with hot reload
make frontend     # Run frontend natively
make test         # Run backend tests
make clean        # DESTRUCTIVE: remove all volumes
make rebuild      # Force no-cache rebuild
```

---

## Access Points

| Service | URL | Notes |
|---------|-----|-------|
| 🌐 **Frontend** | http://localhost:3000 | Main application UI |
| 🔌 **Backend API** | http://localhost:8000 | REST API base URL |
| 📚 **Swagger Docs** | http://localhost:8000/docs | Interactive API documentation |
| 📖 **ReDoc API Docs** | http://localhost:8000/redoc | Alternative API documentation |
| ❤️ **Health Check** | http://localhost:8000/health | Backend health status |

### Demo Login

- **Username:** `investigator`
- **Password:** `inv123!` (value of `NEXT_PUBLIC_DEMO_PASSWORD` in `.env`)
- The frontend auto-logs in. No manual login required.

---

## Docker Compose Files Reference

| File | Path | Purpose | Use Case |
|------|------|---------|----------|
| **Base** | `docs/docker/docker-compose.yml` | All 5 services with production Dockerfiles | Production builds |
| **Dev** | `docs/docker/docker-compose.dev.yml` | Hot-reload Dockerfiles + volume mounts | Active development |
| **Override** | `docs/docker/docker-compose.override.yml` | Dev ports + debug mode (auto-loaded) | Exposing infra ports |
| **Infra** | `docs/docker/docker-compose.infra.yml` | Databases only (Redis, Postgres, Qdrant) | Native backend/frontend dev |
| **Prod** | `docs/docker/docker-compose.prod.yml` | Pre-built images + Caddy TLS | Production deployment |

---

## Troubleshooting

### Build Fails: "SIGNING_KEY must be set"

```bash
cp .env.example .env
# The dev default works for local — no changes needed
```

### Port Conflicts

```bash
# Windows: find what's using a port
netstat -ano | findstr :8000

# Kill the process manually or change the compose port mapping
```

### Backend Keeps Restarting

```bash
# Check logs for the error
docker compose -f docs/docker/docker-compose.yml --env-file .env logs backend --tail=50

# Common causes:
# 1. Missing .env file → cp .env.example .env
# 2. Infra not healthy → check redis/postgres logs
# 3. Python import error → rebuild: docker compose ... build --no-cache backend
```

### Frontend Shows Blank Page

```bash
# Check env vars are baked in
docker exec forensic_ui printenv | grep NEXT_PUBLIC

# If wrong, force rebuild
docker compose -f docs/docker/docker-compose.yml --env-file .env build --no-cache frontend
docker compose -f docs/docker/docker-compose.yml --env-file .env up -d frontend
```

### Database Connection Refused

```bash
# Verify Postgres is healthy
docker inspect forensic_postgres --format='{{.State.Health.Status}}'

# If not healthy, check logs
docker logs forensic_postgres --tail=20
```

### Slow Docker Build / "Exporting Layers" Freeze

If your build appears to hang (especially during Python `uv` or Node `npm` installations), **view the live download stream**:

```bash
docker compose -f docs/docker/docker-compose.yml --env-file .env build --progress=plain
```
The Dockerfiles have been heavily unified and optimized to stream `verbose` download progress directly to `stdout`.

Also, ensure `.dockerignore` files exist in both `backend/` and `frontend/` directories. Without them, Docker sends the entire project (including `node_modules/`, `.git/`, etc.) as build context to the daemon.

---

## Incident Response

### Redis Memory Bloat (OOM)

If the backend starts rejecting requests with `OOM command not allowed`:

1. **Diagnosis:** `docker exec -it forensic_redis redis-cli info memory`
2. **Immediate fix:** `docker exec -it forensic_redis redis-cli FLUSHDB`
   *(This terminates running investigations and clears HITL checkpoints)*
3. **Root cause:** The `ex=86400` TTL may have failed on a bulk task.

### WebSocket Hanging (> 5 min on "Processing")

An ML subprocess is likely zombie'd:

```bash
docker restart forensic_api
```
Users will see "Connection lost" and need to re-upload.

### Signing Key Compromise

1. Generate new key: `python -c "import secrets; print(secrets.token_hex(32))"`
2. Update `SIGNING_KEY` in `.env`
3. Restart: `docker compose -f docs/docker/docker-compose.yml --env-file .env up -d --force-recreate backend`
4. **Impact:** Past signed reports will fail the new key's verification. This is intended.

### Database Corruption / Recovery

```bash
# Manual DB access
docker exec -it forensic_postgres psql -U forensic_user -d forensic_council

# Backup
docker exec -t forensic_postgres pg_dumpall -c -U forensic_user > dump_$(date +%Y-%m-%d).sql

# Complete reset (destructive — wipes all data)
docker compose -f docs/docker/docker-compose.yml --env-file .env down -v
docker compose -f docs/docker/docker-compose.yml --env-file .env up --build -d
```

---

*For detailed error history, see [ERROR_LOG.md](status/ERROR_LOG.md).*
*For development status, see [Development-Status.md](status/Development-Status.md).*
*For architecture details, see [ARCHITECTURE.md](ARCHITECTURE.md).*

