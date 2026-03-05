# Forensic Council — Startup Guide

> **Version:** 1.0.0 | **Last Updated:** 2026-03-05
>
> This file is the single source of truth for building and running the Forensic Council app in Docker.
> Give this file to an LLM or follow it step-by-step for a guaranteed working deployment.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Pre-Flight: Check for Existing Instances](#pre-flight-check-for-existing-instances)
3. [Clean Docker Wipe (Fresh Rebuild)](#clean-docker-wipe-fresh-rebuild)
4. [Environment Setup](#environment-setup)
5. [Docker Build & Run — Full Stack](#docker-build--run--full-stack)
6. [Health Check & Verification](#health-check--verification)
7. [Access Points](#access-points)
8. [Alternative Workflows](#alternative-workflows)
9. [Docker Compose Files Reference](#docker-compose-files-reference)
10. [Useful Commands](#useful-commands)
11. [Troubleshooting](#troubleshooting)

---

## Prerequisites

| Tool | Version | Check Command |
|------|---------|---------------|
| Docker Desktop | 24+ | `docker --version` |
| Docker Compose | v2+ (bundled with Desktop) | `docker compose version` |
| Python | 3.11+ (only for native dev) | `python --version` |
| Node.js | 20+ (only for native dev) | `node --version` |
| uv | 0.6+ (only for native dev) | `uv --version` |

> **Note:** For Docker-only deployment, you only need Docker Desktop. Python/Node/uv are only required for native (non-Docker) development.

---

## Pre-Flight: Check for Existing Instances

**Before building, check if any containers, images, volumes, or networks from this app already exist.**

### Check Running Containers

```bash
docker ps --filter "name=forensic_" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Container names to look for:
- `forensic_api` (backend)
- `forensic_ui` (frontend)
- `forensic_redis` (Redis)
- `forensic_postgres` (PostgreSQL)
- `forensic_qdrant` (Qdrant vector DB)
- `forensic_caddy` (reverse proxy — production only)

### Check Stopped Containers

```bash
docker ps -a --filter "name=forensic_" --format "table {{.Names}}\t{{.Status}}"
```

### Check Images

```bash
docker images --filter "reference=*forensic*" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
docker images --filter "reference=docker-*" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
```

### Check Volumes

```bash
docker volume ls --filter "name=docker_" --format "table {{.Name}}\t{{.Driver}}"
```

Volume names used by this app (prefixed by the compose project directory name):
- `docker_redis_data`
- `docker_postgres_data`
- `docker_qdrant_data`
- `docker_evidence_data`
- `docker_hf_cache`
- `docker_torch_cache`
- `docker_numba_cache`
- `docker_yolo_cache`
- `docker_deepface_cache`
- `docker_calibration_models`

### Check Networks

```bash
docker network ls --filter "name=docker_" --format "table {{.Name}}\t{{.Driver}}"
```

---

## Clean Docker Wipe (Fresh Rebuild)

> ⚠️ **WARNING:** This deletes ALL app data — database contents, cached ML models, evidence files, and Redis state. Only do this if you want a completely fresh start.

### Step 1: Stop All Running Containers

```bash
# Stop the full-stack compose
docker compose -f docker/docker-compose.yml --env-file .env down --remove-orphans

# Stop infrastructure-only compose (if used separately)
docker compose -f docker/docker-compose.infra.yml --env-file .env down --remove-orphans
```

### Step 2: Remove All Volumes (Deletes DB Data)

```bash
# Remove volumes for the full-stack compose
docker compose -f docker/docker-compose.yml --env-file .env down -v --remove-orphans

# Remove volumes for infrastructure compose
docker compose -f docker/docker-compose.infra.yml --env-file .env down -v --remove-orphans
```

### Step 3: Remove Built Images

```bash
# Remove the app images built by compose
docker rmi docker-backend docker-frontend 2>/dev/null
# Or with force if they are in use
docker rmi -f docker-backend docker-frontend 2>/dev/null
```

### Step 4: Prune Build Cache

```bash
# Remove unused build cache (frees disk space from layer caching)
docker builder prune -f
```

### Step 5: Verify Clean State

```bash
# Should all return empty
docker ps -a --filter "name=forensic_" --format "{{.Names}}"
docker volume ls --filter "name=docker_" --format "{{.Name}}"
docker images --filter "reference=docker-*" --format "{{.Repository}}"
```

### Nuclear Option (Clean EVERYTHING Docker-wide)

> ⚠️ **DANGER:** This removes ALL Docker data across ALL projects, not just Forensic Council.

```bash
docker system prune -a --volumes -f
```

---

## Environment Setup

### Step 1: Create Environment Files

```bash
# From the project root directory
cp .env.example .env
cp backend/.env.example backend/.env
```

### Step 2: Generate a Signing Key

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the output and set it as `SIGNING_KEY` in your `.env` file.

### Step 3: Configure Required Variables

Edit `.env` and verify these critical variables:

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `SIGNING_KEY` | ✅ Yes | `dev-placeholder-...` | Must change for production |
| `POSTGRES_PASSWORD` | ✅ Yes | `forensic_pass` | Must change for production |
| `HF_TOKEN` | Optional | empty | Needed for audio speaker diarization (Agent 2) |
| `LLM_PROVIDER` | Optional | `none` | Set to `openai` or `anthropic` for LLM reasoning |
| `LLM_API_KEY` | If LLM ≠ none | empty | Your OpenAI/Anthropic API key |
| `NEXT_PUBLIC_DEMO_PASSWORD` | ✅ Yes | `inv123!` | Demo login password |

> **Note:** The dev defaults work out-of-the-box for local development. Only change them for staging/production.

---

## Docker Build & Run — Full Stack

This is the primary workflow. It builds and runs all 5 services (Redis, PostgreSQL, Qdrant, Backend, Frontend) in Docker.

### File Paths

All Docker files are relative to the project root:

```
Forensic-Council-main/
├── .env                                  ← Root env file (must exist)
├── .env.example                          ← Template to copy from
├── backend/
│   ├── .env                              ← Backend env file (must exist)
│   ├── .env.example                      ← Template to copy from
│   └── Dockerfile                        ← Backend multi-stage build
├── frontend/
│   └── Dockerfile                        ← Frontend multi-stage build (3 stages)
└── docker/
    ├── docker-compose.yml                ← Base: all 5 services
    ├── docker-compose.override.yml       ← Dev: port bindings + debug mode (auto-loaded)
    ├── docker-compose.infra.yml          ← Infra-only: Redis + Postgres + Qdrant
    ├── docker-compose.prod.yml           ← Prod: pre-built images + Caddy TLS
    └── Caddyfile                         ← Reverse proxy config (prod only)
```

### Step 1: Build All Images

```bash
docker compose -f docker/docker-compose.yml --env-file .env build
```

**What this builds:**

| Service | Dockerfile | Base Image | Build Stages |
|---------|-----------|------------|-------------|
| `backend` | `backend/Dockerfile` | `python:3.11-slim` | 2-stage: builder (uv + deps) → runner (app + system libs) |
| `frontend` | `frontend/Dockerfile` | `node:20-alpine` | 3-stage: deps (npm ci) → builder (next build) → runner (standalone) |
| `redis` | — | `redis:7-alpine` | Pre-built official image |
| `postgres` | — | `postgres:16-alpine` | Pre-built official image |
| `qdrant` | — | `qdrant/qdrant:v1.11.0` | Pre-built official image |

> **Build time:** First build takes ~3-5 minutes (downloads base images + installs dependencies). Subsequent builds use Docker layer cache and complete in ~30 seconds.

To force a clean rebuild with no cache:
```bash
docker compose -f docker/docker-compose.yml --env-file .env build --no-cache
```

### Step 2: Start All Services

```bash
docker compose -f docker/docker-compose.yml --env-file .env up -d
```

> **Note:** `docker-compose.override.yml` is auto-loaded alongside `docker-compose.yml` when in the same directory. It exposes infrastructure ports and enables debug mode. You don't need to specify it explicitly.

**Startup order (enforced by `depends_on` + healthchecks):**

```
1. redis       → starts first, healthcheck: redis-cli ping
2. postgres    → starts first, healthcheck: pg_isready
3. qdrant      → starts first, healthcheck: TCP port 6333
4. backend     → waits for all 3 infra services to be healthy
                  → auto-runs DB schema init + migrations on startup
5. frontend    → waits for backend to be healthy
```

### Step 3: Watch Startup Progress

```bash
# Watch container status and health transitions
docker compose -f docker/docker-compose.yml --env-file .env ps

# Or watch logs in real-time
docker compose -f docker/docker-compose.yml --env-file .env logs -f
```

Wait until all services show `(healthy)` status. This typically takes:
- Infrastructure (Redis, Postgres, Qdrant): ~10 seconds
- Backend: ~15-20 seconds (includes DB init + migration)
- Frontend: ~30 seconds (Next.js cold start)

### Step 4: Verify Build Success

```bash
# Show all container statuses — all should be "Up" and "(healthy)"
docker compose -f docker/docker-compose.yml --env-file .env ps
```

Expected output:
```
NAME               STATUS                    PORTS
forensic_api       Up (healthy)              0.0.0.0:8000->8000/tcp
forensic_ui        Up (healthy)              0.0.0.0:3000->3000/tcp
forensic_redis     Up (healthy)              0.0.0.0:6379->6379/tcp
forensic_postgres  Up (healthy)              0.0.0.0:5432->5432/tcp
forensic_qdrant    Up (healthy)              0.0.0.0:6333->6333/tcp, 0.0.0.0:6334->6334/tcp
```

---

## Health Check & Verification

### Backend Health

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status": "healthy", "environment": "development", "active_sessions": 0}
```

### Backend Root

```bash
curl http://localhost:8000/
```

Expected response:
```json
{"name": "Forensic Council API", "version": "1.0.0", "status": "running", "docs": "/docs"}
```

### Frontend Health

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
```

Expected: `200`

### API Docs

Open in browser: http://localhost:8000/docs

This should show the Swagger UI with all available endpoints.

### Container-Level Health

```bash
# Check individual container health
docker inspect forensic_api --format='{{.State.Health.Status}}'
docker inspect forensic_ui --format='{{.State.Health.Status}}'
docker inspect forensic_redis --format='{{.State.Health.Status}}'
docker inspect forensic_postgres --format='{{.State.Health.Status}}'
```

All should return `healthy`.

---

## Access Points

| Service | URL | Notes |
|---------|-----|-------|
| 🌐 **Frontend** | http://localhost:3000 | Main application UI |
| 🔌 **Backend API** | http://localhost:8000 | REST API base URL |
| 📚 **API Docs (Swagger)** | http://localhost:8000/docs | Interactive API documentation |
| 📖 **API Docs (ReDoc)** | http://localhost:8000/redoc | Alternative API documentation |
| ❤️ **Health Check** | http://localhost:8000/health | Backend health status |

### Demo Login

The app auto-creates a demo user on first startup:
- **Username:** `investigator`
- **Password:** Value of `NEXT_PUBLIC_DEMO_PASSWORD` in `.env` (default: `inv123!`)

The frontend auto-logs in using this demo user. No manual login is required.

---

## Alternative Workflows

### Infrastructure Only (for Native Development)

Run databases in Docker, backend/frontend natively with hot reload:

```bash
# 1. Start databases only
docker compose -f docker/docker-compose.infra.yml --env-file .env up -d

# 2. In terminal 1 — Backend (with hot reload)
cd backend && uv sync --extra dev && uv run uvicorn api.main:app --reload --port 8000

# 3. In terminal 2 — Frontend (with hot reload)
cd frontend && npm install && npm run dev
```

**Ports (infra-only compose):**

| Service | Host Port | Note |
|---------|-----------|------|
| Redis | 6380 | Mapped to 6380 to avoid conflicts with local Redis |
| PostgreSQL | 5432 | Standard port |
| Qdrant REST | 6333 | Standard port |
| Qdrant gRPC | 6334 | Standard port |

> ⚠️ The infra compose maps Redis to **6380** (not 6379). Set `REDIS_PORT=6380` in `backend/.env` if using this workflow.

### Production Deployment

```bash
# Requires pre-built images pushed to a registry
docker compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml --env-file .env up -d
```

Production adds: Caddy reverse proxy with auto-HTTPS, restart policies, no debug mode.

---

## Docker Compose Files Reference

| File | Path | Purpose | Port Exposure |
|------|------|---------|---------------|
| **Base** | `docker/docker-compose.yml` | All 5 services with build contexts | Backend: 8000, Frontend: 3000 |
| **Override** | `docker/docker-compose.override.yml` | Dev ports + debug + hot reload CMD | Redis: 6379, Postgres: 5432, Qdrant: 6333/6334 |
| **Infra** | `docker/docker-compose.infra.yml` | Databases only (Redis, Postgres, Qdrant) | Redis: 6380, Postgres: 5432, Qdrant: 6333/6334 |
| **Prod** | `docker/docker-compose.prod.yml` | Pre-built images + Caddy TLS | HTTP: 80, HTTPS: 443 |

> **Auto-loading:** `docker-compose.override.yml` is NOT auto-loaded because it's inside the `docker/` subdirectory, not alongside the compose command's working directory. However, when you pass `-f docker/docker-compose.yml`, Docker Compose looks for an override file in the same directory as the specified file, so it IS auto-loaded.

---

## Useful Commands

### Makefile Shortcuts

The project root includes a `Makefile` with shortcuts:

```bash
make infra       # Start databases only
make up          # Build + start full stack
make down        # Stop all containers
make logs        # Tail all logs
make backend     # Run backend natively (requires infra running)
make frontend    # Run frontend natively
make test        # Run backend tests
make clean       # DESTRUCTIVE: remove all volumes
make rebuild     # Force rebuild from scratch
```

### Viewing Logs

```bash
# All services
docker compose -f docker/docker-compose.yml --env-file .env logs -f

# Specific service
docker compose -f docker/docker-compose.yml --env-file .env logs -f backend
docker compose -f docker/docker-compose.yml --env-file .env logs -f frontend
```

### Restart a Service

```bash
docker compose -f docker/docker-compose.yml --env-file .env restart backend
```

### Enter a Container Shell

```bash
# Backend shell
docker exec -it forensic_api bash

# Frontend shell
docker exec -it forensic_ui sh

# PostgreSQL CLI
docker exec -it forensic_postgres psql -U forensic_user -d forensic_council
```

### Run Backend Tests Inside Container

```bash
docker exec -it forensic_api python -m pytest tests/ -v
```

---

## Troubleshooting

### Build Fails: "SIGNING_KEY must be set"

```bash
# You forgot to create .env or set SIGNING_KEY
cp .env.example .env
# Edit .env and set SIGNING_KEY (or leave the dev default for local development)
```

### Port Conflicts

```bash
# Windows: find what's using port 8000
netstat -ano | findstr :8000

# Linux/Mac: find what's using port 8000
lsof -i :8000
```

### Backend Keeps Restarting

```bash
# Check backend logs for the error
docker compose -f docker/docker-compose.yml --env-file .env logs backend --tail=50

# Common causes:
# 1. Missing .env file → create it
# 2. Redis/Postgres not healthy yet → wait longer or check infra logs
# 3. Python import error → rebuild with --no-cache
```

### Frontend Shows Blank Page

```bash
# Check if NEXT_PUBLIC_API_URL is correctly set
docker exec forensic_ui printenv | grep NEXT_PUBLIC

# If wrong, rebuild frontend with correct build args
docker compose -f docker/docker-compose.yml --env-file .env build --no-cache frontend
docker compose -f docker/docker-compose.yml --env-file .env up -d frontend
```

### Database Connection Refused

```bash
# Verify Postgres is healthy
docker inspect forensic_postgres --format='{{.State.Health.Status}}'

# If not healthy, check logs
docker logs forensic_postgres --tail=20

# Nuclear option: wipe and recreate
docker compose -f docker/docker-compose.yml --env-file .env down -v
docker compose -f docker/docker-compose.yml --env-file .env up --build -d
```
