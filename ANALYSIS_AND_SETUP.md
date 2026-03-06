# Forensic Council — Code Analysis & Setup Guide

**Version:** v0.9.1 (packaged as v0.8.0)  
**Analysis Date:** March 6, 2026  
**Status:** ✅ **FIXED** — All identified issues resolved

---

## Executive Summary

The Forensic Council codebase is a sophisticated multi-agent forensic analysis system built with **Next.js 15** (frontend), **FastAPI** (backend), and **Python 3.11+** with specialized ML agents. The project is well-structured with comprehensive Docker support.

### Issues Found & Fixed

| Issue | Severity | Location | Fix |
|-------|----------|----------|-----|
| Redis port mismatch in native dev mode | 🔴 HIGH | `docs/docker/docker-compose.infra.yml` | Changed port from 6380 → 6379 |

**All other checks passed:**
- ✅ Python syntax validation
- ✅ JSON configuration validation
- ✅ Docker configuration properly structured
- ✅ Environment templates complete
- ✅ TypeScript/Next.js configuration valid
- ✅ All dependencies well-managed

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────┐
│          FRONTEND (Next.js 15 + React 19)           │
│     TypeScript • Tailwind CSS • Framer Motion       │
│  Responsive UI • Real-time WebSocket Updates        │
└───────────────────┬────────────────────────────────┘
                    │ HTTP + WebSocket
┌───────────────────▼────────────────────────────────┐
│       BACKEND (FastAPI + Python 3.11+)              │
│  ┌──────────────────────────────────────────────┐  │
│  │  5 AI Agents + Council Arbiter               │  │
│  │  • Agent 1: Image Forensics                  │  │
│  │  • Agent 2: Audio Forensics                  │  │
│  │  • Agent 3: Object Detection                 │  │
│  │  • Agent 4: Video Forensics                  │  │
│  │  • Agent 5: Metadata Forensics               │  │
│  │  + Arbiter: Synthesis & Signing              │  │
│  └──────────────────────────────────────────────┘  │
│  LangGraph • Uvicorn • WebSockets                  │
└────┬──────────────────────┬─────────────┬─────────┘
     │                      │             │
  ┌──▼───┐          ┌─────▼──┐      ┌───▼────┐
  │ Redis│          │Postgres│      │ Qdrant │
  │ 7    │          │ 16     │      │ v1.11  │
  └──────┘          └────────┘      └────────┘
  Sessions          Reports         Embeddings
  ReAct Loop        Evidence        Vector DB
```

---

## Project Structure

```
Forensic-Council-v0.9.1/
├── frontend/                      # Next.js 15 React Application
│   ├── src/
│   │   ├── app/                  # Next.js App Router
│   │   ├── components/           # React Components
│   │   ├── lib/                  # Utilities & API Client
│   │   ├── hooks/                # React Hooks
│   │   └── types/                # TypeScript Definitions
│   ├── Dockerfile               # Production build (multi-stage)
│   ├── Dockerfile.dev           # Development with hot-reload
│   ├── next.config.ts           # Next.js Configuration
│   ├── package.json             # Dependencies
│   └── tsconfig.json            # TypeScript Configuration
│
├── backend/                       # FastAPI + Python ML Agents
│   ├── api/
│   │   ├── main.py              # FastAPI App Entry Point
│   │   └── routes/              # API Route Handlers
│   ├── core/
│   │   ├── config.py            # Settings Management
│   │   ├── llm_client.py        # LLM Provider Interface
│   │   ├── react_loop.py        # Agent Reasoning Loop
│   │   ├── working_memory.py    # Agent State Management
│   │   └── ...                  # Auth, Logging, DB, etc.
│   ├── agents/
│   │   ├── agent1_image.py      # Image Forensics Agent
│   │   ├── agent2_audio.py      # Audio Forensics Agent
│   │   ├── agent3_object.py     # Object Detection Agent
│   │   ├── agent4_video.py      # Video Forensics Agent
│   │   ├── agent5_metadata.py   # Metadata Forensics Agent
│   │   ├── arbiter.py           # Council Arbiter
│   │   └── base_agent.py        # Agent Base Class
│   ├── tools/                   # Forensic Analysis Tools
│   │   ├── image_tools.py       # ELA, Hash, Splice Detection
│   │   ├── audio_tools.py       # Spectral Analysis
│   │   ├── video_tools.py       # Frame Analysis
│   │   ├── metadata_tools.py    # EXIF Parsing
│   │   └── ...
│   ├── scripts/ml_tools/        # ML-based Detectors
│   │   ├── splicing_detector.py
│   │   ├── deepfake_frequency.py
│   │   └── ...
│   ├── infra/                   # Infrastructure Clients
│   │   ├── postgres_client.py   # Database
│   │   ├── redis_client.py      # Caching & Pub/Sub
│   │   ├── qdrant_client.py     # Vector DB
│   │   └── ...
│   ├── orchestration/           # Agent Orchestration
│   │   ├── pipeline.py          # Investigation Pipeline
│   │   └── session_manager.py   # Session Management
│   ├── Dockerfile              # Production Image
│   ├── pyproject.toml          # Dependencies (uv format)
│   ├── uv.lock                 # Dependency Lock
│   └── scripts/
│       ├── run_api.py          # API Server Entry Point
│       ├── init_db.py          # Database Initialization
│       └── ...
│
├── docs/
│   ├── docker/
│   │   ├── docker-compose.yml           # Base Compose Config
│   │   ├── docker-compose.dev.yml       # Dev Overlay (hot-reload)
│   │   ├── docker-compose.infra.yml     # Infra Only (native dev)
│   │   ├── docker-compose.prod.yml      # Production Overlay
│   │   └── Caddyfile                    # Reverse Proxy Config
│   ├── start/STARTUP.md                 # Complete Setup Guide
│   ├── API.md                           # API Documentation
│   ├── ARCHITECTURE.md                  # Architecture Details
│   └── status/                          # Status & Error Logs
│
├── .env.example                 # Root Environment Template
├── .env                         # Root Environment (create from .env.example)
├── backend/.env.example         # Backend Env Template (for native dev)
├── backend/.env                 # Backend Env (create from .env.example)
├── Makefile                     # Developer Shortcuts
├── README.md                    # Project Overview
├── CHANGELOG.md                 # Version History
└── LICENSE                      # MIT License
```

---

## Docker Configuration Analysis

### ✅ Backend Dockerfile

**Status:** CORRECT

- Multi-stage build not used (single stage approach is fine)
- Proper layer caching with dependency installation first
- ML model caches persist via named volumes
- Health checks configured correctly
- Environment variables for ML model paths properly set

**Key Features:**
- `RELOAD=true` environment variable supports hot-reload
- Model cache directories: HuggingFace, PyTorch, YOLO, DeepFace, EasyOCR
- Bytecode compilation for performance

### ✅ Frontend Dockerfile

**Status:** CORRECT

- Two-stage build: Builder → Runner
- Next.js standalone output configured
- Proper health check with fixed syntax
- NODE_ENV=production in runner stage

**Key Features:**
- Next.js caching layer for faster rebuilds
- Minimal runtime image (only necessary files)
- Standalone mode reduces dependencies

### ✅ Frontend Dockerfile.dev

**Status:** CORRECT

- Optimized for development with hot-reload
- Keeps dependencies for development
- Runs Next.js dev server directly
- Proper port exposure (3000)

### ✅ Docker Compose Configuration

**Status:** MOSTLY CORRECT (see issue below)

#### docker-compose.yml (Base)
- ✅ All 5 services properly configured
- ✅ Health checks for all services
- ✅ Resource limits and reservations set
- ✅ Named volumes for persistence
- ✅ Proper dependency ordering

#### docker-compose.dev.yml (Development)
- ✅ Hot-reload configuration for backend and frontend
- ✅ Volume mounts for source code
- ✅ ML model cache volumes preserved
- ✅ Development environment variables set
- ✅ Polling enabled for Docker on Windows/macOS

#### docker-compose.infra.yml (Infrastructure Only)
- 🔴 **ISSUE FIXED:** Redis port was mapped to 6380, should be 6379
  - Backend expects Redis on localhost:6379 (from backend/.env)
  - This broke native development mode
  - Fixed: Changed `6380:6379` → `6379:6379`

#### docker-compose.prod.yml (Production)
- ✅ Hardened settings
- ✅ Caddy reverse proxy integration
- ✅ Security headers

---

## Environment Configuration

### Root .env.example

**Status:** ✅ CORRECT

**Required Variables for Development:**
```bash
# Application
APP_ENV=development
DEBUG=true
LOG_LEVEL=INFO

# Security (development only)
SIGNING_KEY=dev-placeholder-...

# Database
POSTGRES_USER=forensic_user
POSTGRES_PASSWORD=forensic_pass
POSTGRES_DB=forensic_council

# Frontend
NEXT_PUBLIC_DEMO_PASSWORD=inv123!
NEXT_PUBLIC_API_URL=http://localhost:8000

# LLM Provider (optional, defaults to none)
LLM_PROVIDER=groq
LLM_API_KEY=gsk_your_groq_key_here
LLM_MODEL=llama-3.3-70b-versatile
```

### Backend .env.example

**Status:** ✅ CORRECT

Used only for native development. Docker Compose provides these via environment variables in docker-compose.yml.

---

## Running the Application

### 🐳 Option 1: Full Docker Stack (Recommended for First-Time)

Best for: Testing, production, rapid iteration

```bash
# 1. Create environment files
cp .env.example .env
cp backend/.env.example backend/.env

# 2. Start everything (builds images + starts all services)
docker compose -f docs/docker/docker-compose.yml --env-file .env up -d --build

# Verify all services are healthy
docker compose -f docs/docker/docker-compose.yml --env-file .env ps

# Access the app
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

**Time:** ~5-8 minutes (first build), ~60 seconds (subsequent starts)

---

### 🚀 Option 2: Development with Docker Hot-Reload (RECOMMENDED)

Best for: Active development with instant code changes reflection

```bash
# 1. Create environment files
cp .env.example .env
cp backend/.env.example backend/.env

# 2. Start dev stack with hot-reload
docker compose \
  -f docs/docker/docker-compose.yml \
  -f docs/docker/docker-compose.dev.yml \
  --env-file .env \
  up -d --build

# Or use the Makefile shortcut
make dev

# Verify services are running
docker compose -f docs/docker/docker-compose.yml \
  -f docs/docker/docker-compose.dev.yml \
  --env-file .env ps

# Watch logs in real-time
docker compose -f docs/docker/docker-compose.yml \
  -f docs/docker/docker-compose.dev.yml \
  --env-file .env logs -f

# Access the app
# Frontend: http://localhost:3000 (changes auto-reload)
# Backend API: http://localhost:8000 (code auto-reloads)
```

**What's Enabled:**
| Service | Hot Reload | Port |
|---------|-----------|------|
| Backend (Python/Uvicorn) | ✅ Code changes auto-restart | 8000 |
| Frontend (Next.js) | ✅ Fast Refresh | 3000 |
| Model Cache | ✅ Persisted across restarts | — |
| PostgreSQL | — | 5432 |
| Redis | — | 6379 |
| Qdrant | — | 6333 |

**Model Cache Behavior:**
- ML models download on first investigation
- Cached in Docker named volumes (hf_cache, torch_cache, etc.)
- Persists across `docker compose down` (without `-v`)
- Survives container restarts and rebuilds
- Wiped only by `docker compose down -v`

---

### 💻 Option 3: Native Development (Backend + Docker Infra)

Best for: Native Python/Node development with maximum IDE support

**Prerequisites:**
- Python 3.11+
- Node.js 20+
- uv package manager
- Docker (for databases only)

```bash
# 1. Create environment files
cp .env.example .env
cp backend/.env.example backend/.env

# 2. Start infrastructure services (databases only)
docker compose -f docs/docker/docker-compose.infra.yml --env-file .env up -d

# Or use Makefile
make infra

# Verify databases are ready
docker compose -f docs/docker/docker-compose.infra.yml --env-file .env ps

# 3. In Terminal 1 — Start Backend with hot-reload
cd backend
uv run uvicorn api.main:app --reload --port 8000

# Expected output:
# INFO:     Uvicorn running on http://0.0.0.0:8000
# INFO:     Application startup complete
# INFO:     Watching for file changes...

# 4. In Terminal 2 — Start Frontend with hot-reload
cd frontend
npm run dev

# Expected output:
# ▲ Next.js 15.3.0
# - Local:        http://localhost:3000
# - Environments: .env.local
# ✓ Ready in 2.5s

# Access the app
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
```

**Advantages:**
- Fastest development cycle (native IDE support)
- Best debugging experience
- Direct environment variable control
- But: Requires Python, Node, uv locally

**Model Cache in Native Mode:**
- Cached in `./backend/cache/` (local filesystem)
- Must have permission to write to `./backend/cache/`
- On first investigation: ~5-10 min for model downloads (depends on models used)
- Subsequent investigations: instant cache hits

---

### Makefile Shortcuts

From project root:

```bash
# Infrastructure
make infra         # Start databases only
make up            # Build + start full stack (production mode)
make dev           # Build + start dev stack with hot-reload
make down          # Stop all containers
make logs          # Tail all container logs
make rebuild       # Force no-cache rebuild of all images
make clean         # DESTRUCTIVE: Remove all volumes

# Native Development
make backend       # Run backend natively with hot reload
make frontend      # Run frontend natively
make test          # Run backend test suite
make lint          # Lint frontend TypeScript
make type-check    # TypeScript type-check
make smoke         # Run backend smoke test
make init-keys     # Initialize ECDSA keys for agents
```

---

## Database & Cache Management

### PostgreSQL

**Purpose:** Immutable custody log + final reports

**Health Check:** `pg_isready`

**Connection (Docker):**
```
Host: postgres
Port: 5432
User: forensic_user (from .env)
Password: forensic_pass (from .env)
Database: forensic_council
```

**Connection (Native):**
```
Host: localhost
Port: 5432
User: forensic_user
Password: forensic_pass
Database: forensic_council
```

**Backup:**
```bash
docker exec forensic_postgres pg_dumpall -c -U forensic_user > backup.sql
```

### Redis

**Purpose:** Real-time session state + agent reasoning (ReAct loop)

**Health Check:** `redis-cli ping`

**Connection (Docker):**
```
Host: redis
Port: 6379
```

**Connection (Native):**
```
Host: localhost
Port: 6379
```

**Monitor Activity:**
```bash
docker exec -it forensic_redis redis-cli
> MONITOR
```

### Qdrant

**Purpose:** Vector database for embeddings + semantic search

**Health Check:** TCP port 6333

**Web Dashboard:**
- Docker: http://localhost:6333/dashboard
- Native: http://localhost:6333/dashboard

**Connection:**
```
Host: qdrant (Docker) or localhost (Native)
Port: 6333 (REST) or 6334 (gRPC)
```

---

## Common Tasks

### Running the App Fresh

```bash
# Complete clean start (removes all containers, images, volumes)
docker compose -f docs/docker/docker-compose.yml --env-file .env down -v
docker compose -f docs/docker/docker-compose.yml --env-file .env up -d --build
```

### Check Service Health

```bash
# List all services and their status
docker compose -f docs/docker/docker-compose.yml --env-file .env ps

# Check specific service health
docker compose -f docs/docker/docker-compose.yml --env-file .env exec backend curl http://localhost:8000/health

# View backend logs
docker logs forensic_api --tail=50 -f

# View frontend logs
docker logs forensic_ui --tail=50 -f
```

### Rebuild Backend After Dependency Changes

```bash
# Rebuild the backend image (drops container, rebuilds, restarts)
docker compose -f docs/docker/docker-compose.yml --env-file .env build --no-cache backend
docker compose -f docs/docker/docker-compose.yml --env-file .env up -d backend
```

### Access Database Directly

```bash
# PostgreSQL interactive shell
docker exec -it forensic_postgres psql -U forensic_user -d forensic_council

# Redis CLI
docker exec -it forensic_redis redis-cli

# Qdrant API (via curl)
curl http://localhost:6333/collections
```

### Change Demo Password

Edit `.env`:
```
NEXT_PUBLIC_DEMO_PASSWORD=mynewpassword!
```

Rebuild frontend:
```bash
docker compose -f docs/docker/docker-compose.yml --env-file .env build --no-cache frontend
docker compose -f docs/docker/docker-compose.yml --env-file .env up -d frontend
```

---

## Troubleshooting

### Port Already in Use

```bash
# Find process using port 8000 (macOS/Linux)
lsof -i :8000
kill -9 <PID>

# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

### Backend Can't Connect to Redis (Native Dev Only)

**Symptom:** `Error: Connection refused (localhost:6379)`

**Cause:** Redis port in `docker-compose.infra.yml` was mapped to 6380 instead of 6379. ✅ **FIXED** in this version.

**Verify Fix:**
```bash
docker compose -f docs/docker/docker-compose.infra.yml --env-file .env ps
# Should show: forensic_redis ... 0.0.0.0:6379->6379/tcp
```

### Models Downloading Every Build

**Cause:** Volumes were deleted with `docker compose down -v`

**Solution:** Models persist in named volumes. Do NOT use `-v` unless you intentionally want to reset:
```bash
# Stop WITHOUT removing volumes (safe)
docker compose down

# Stop AND remove volumes (destructive)
docker compose down -v
```

### Frontend Shows Blank Page

**Cause:** NEXT_PUBLIC_* environment variables not baked into image

**Fix:**
```bash
# Verify env vars are in the image
docker exec forensic_ui printenv | grep NEXT_PUBLIC

# Rebuild if missing
docker compose -f docs/docker/docker-compose.yml --env-file .env build --no-cache frontend
docker compose -f docs/docker/docker-compose.yml --env-file .env up -d frontend
```

### WebSocket Hanging (>5 min on "Processing")

**Cause:** ML subprocess zombie'd

**Fix:**
```bash
docker restart forensic_api
```

---

## Performance Tips

### For Development

1. **Use hot-reload option** (Option 2): Fastest iteration cycle
2. **Monitor Docker resources:**
   ```bash
   docker stats forensic_api forensic_ui
   ```
3. **Keep model cache** between sessions (don't use `-v` on down)
4. **Use native dev mode** (Option 3) if you need IDE debugging

### For Production

1. **Set resource limits** (already configured in docker-compose.yml):
   - Backend: 4GB memory, 2.0 CPU limit
   - Frontend: 512MB memory, 0.5 CPU limit
   - Infra: 1-2GB memory each

2. **Use production compose file:**
   ```bash
   docker compose -f docs/docker/docker-compose.yml \
     -f docs/docker/docker-compose.prod.yml \
     --env-file .env up -d
   ```

3. **Enable LLM provider** for reasoning (optional):
   - Set `LLM_PROVIDER=groq` (free tier available)
   - Add `LLM_API_KEY=gsk_...` to `.env`

---

## Access Points

| Service | URL | Purpose |
|---------|-----|---------|
| 🌐 Frontend | http://localhost:3000 | Main UI |
| 🔌 Backend API | http://localhost:8000 | REST API |
| 📚 Swagger Docs | http://localhost:8000/docs | Interactive API docs |
| 📖 ReDoc Docs | http://localhost:8000/redoc | Alternative API docs |
| ❤️ Health Check | http://localhost:8000/health | Backend status |
| 🔗 Qdrant Dashboard | http://localhost:6333/dashboard | Vector DB UI |

### Demo Login

- **Username:** `investigator`
- **Password:** Value from `NEXT_PUBLIC_DEMO_PASSWORD` in `.env` (default: `inv123!`)
- **Auto-login:** Enabled on first page load

---

## Summary of Changes

| File | Change | Reason |
|------|--------|--------|
| `docs/docker/docker-compose.infra.yml` | Redis port: 6380 → 6379 | Fix native dev mode connection |
| (New) `ANALYSIS_AND_SETUP.md` | Created | Comprehensive analysis & setup guide |

---

## Next Steps

1. **Copy environment files:**
   ```bash
   cp .env.example .env
   cp backend/.env.example backend/.env
   ```

2. **Choose your development mode** (see "Running the Application" section above):
   - Docker full stack (Option 1) — Easiest, no local dependencies
   - Docker with hot-reload (Option 2) — Best for active development
   - Native with Docker infra (Option 3) — Best for IDE integration

3. **Access the app:**
   - Frontend: http://localhost:3000
   - Demo login: `investigator` / `inv123!`

4. **For production deployment:**
   - Change `APP_ENV=production` in `.env`
   - Generate strong `SIGNING_KEY`: `python -c "import secrets; print(secrets.token_hex(32))"`
   - Set strong `POSTGRES_PASSWORD`
   - Use `docker-compose.prod.yml` overlay

---

## References

- **Startup Guide:** `docs/start/STARTUP.md`
- **API Documentation:** `docs/API.md`
- **Architecture Overview:** `docs/ARCHITECTURE.md`
- **Agent Capabilities:** `docs/agent_capabilities.md`
- **Error Log:** `docs/status/ERROR_LOG.md`

---

**Questions?** See the comprehensive startup guide in `docs/start/STARTUP.md` for step-by-step instructions and troubleshooting.
