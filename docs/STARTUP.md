# Forensic Council — Startup Guide

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- [Python 3.11+](https://www.python.org/downloads/) (for native development)
- [Node.js 20+](https://nodejs.org/) (for native development)
- [uv](https://docs.astral.sh/uv/) (for Python package management)

## Before First Run

### 1. Create Environment File

On a fresh clone, you must create a `.env` file before running any Docker commands. The `SIGNING_KEY` variable has a required guard that will abort the build if missing.

```bash
# Copy the example environment file
cp .env.example .env

# Generate a secure signing key (run this command and copy the output to SIGNING_KEY in .env)
python -c "import secrets; print(secrets.token_hex(32))"
```

Edit `.env` and set `SIGNING_KEY` to the generated value. You may also set:
- `HF_TOKEN=hf_your_token_here`  # Required for audio agent (pyannote.audio)

### 2. Enable BuildKit (Recommended)

```bash
export DOCKER_BUILDKIT=1
```

---

**Default Ports:**

| Service | Port | Notes |
|---------|------|-------|
| Frontend | 3000 | Always exposed in all compose files |
| Backend API | 8000 | Always exposed |
| PostgreSQL | 5432 | Only in override/prod compose files |
| Qdrant | 6333, 6334 | Only in override/prod compose files |
| Redis | 6379 | Only in override/prod compose files |

> **Note:** Redis port 6380 mentioned in some docs was incorrect. The actual Redis port is 6379. The base `docker-compose.yml` does not expose infrastructure ports to the host - use `docker-compose.override.yml` (auto-loaded) or `docker-compose.infra.yml` for host access.

---

## Development Workflows

We support three development workflows. Choose the one that fits your needs:

| Workflow | Use When | Hot Reload | Startup Time |
|----------|----------|------------|--------------|
| **Infrastructure + Native** | Active development, daily work | ✅ Fastest | ~10s |
| **Full Docker** | Testing Docker builds, CI debugging | ✅ Yes | ~60s |
| **Production** | Production deployment | ❌ No | ~30s |

---

## Workflow 1: Infrastructure + Native (Recommended)

This is the fastest workflow for daily development. Databases run in Docker while backend and frontend run natively with hot reload.

### 1. Start Infrastructure Services

```bash
# Start only Redis, Qdrant, and PostgreSQL
docker compose -f docker/docker-compose.infra.yml --env-file .env up -d

# Wait for health checks (~10 seconds)
docker compose -f docker/docker-compose.infra.yml --env-file .env ps
```

You should see `forensic_redis` and `forensic_postgres` as `healthy`.

### 2. Set Up Backend (Native)

```bash
cd backend

# Create virtual environment and install dependencies from lockfile
uv venv
uv sync --extra dev

# Initialize database schema (optional - auto-runs on first API startup)
uv run python scripts/init_db.py

# Start backend with hot reload
uv run uvicorn api.main:app --reload --port 8000
```

The backend will be available at http://localhost:8000

### 3. Set Up Frontend (Native)

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

The frontend will be available at http://localhost:3000

### Access Points

- 🌐 **Frontend:** http://localhost:3000
- 🔌 **Backend API:** http://localhost:8000
- 📚 **API Docs:** http://localhost:8000/docs

---

## Workflow 2: Full Docker (Development)

Use this when testing Docker builds or when you don't have Python/Node installed locally.

```bash
# Build and start all services (uses docker/docker-compose.yml)
# Note: docker-compose.override.yml is auto-loaded for dev port bindings
docker compose -f docker/docker-compose.yml --env-file .env up --build -d

# Wait for health checks (~30-60 seconds)
docker compose -f docker/docker-compose.yml --env-file .env ps

# Database schema is auto-initialized on first startup
# Only run manually to verify connectivity:
# docker compose -f docker/docker-compose.yml --env-file .env exec backend python scripts/init_db.py
```

### Access Points

- 🌐 **Frontend:** http://localhost:3000
- 🔌 **Backend API:** http://localhost:8000
- 📚 **API Docs:** http://localhost:8000/docs

---

## Workflow 3: Production

Use this for production deployments with pre-built images.

```bash
# Set required environment variables
export DOCKER_REGISTRY=ghcr.io/yourorg
export IMAGE_TAG=v1.0.0
export API_URL=https://api.yourdomain.com

# Start production stack
docker compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml --env-file .env up -d
```

---

## Docker Compose Files Reference

| File | Purpose | When It's Used |
|------|---------|----------------|
| `docker/docker-compose.yml` | Base service definitions | Always included |
| `docker/docker-compose.override.yml` | Development overrides (build contexts, ports, volumes) | Auto-loaded with base |
| `docker/docker-compose.infra.yml` | Infrastructure only (Redis, Qdrant, Postgres) | Explicit `-f` flag |
| `docker/docker-compose.prod.yml` | Production overrides (images, restart policies) | Explicit `-f` flag |

---

## Useful Commands

### Viewing Logs

```bash
# All services
docker compose -f docker/docker-compose.yml --env-file .env logs -f

# Specific service
docker compose -f docker/docker-compose.yml --env-file .env logs -f backend
docker compose -f docker/docker-compose.yml --env-file .env logs -f frontend
docker compose -f docker/docker-compose.infra.yml --env-file .env logs -f postgres
```

### Managing Services

```bash
# Restart a service
docker compose -f docker/docker-compose.yml --env-file .env restart backend

# Stop everything (keep volumes)
docker compose -f docker/docker-compose.yml --env-file .env down

# Stop infrastructure only
docker compose -f docker/docker-compose.infra.yml --env-file .env down

# Stop and remove all data (volumes)
docker compose -f docker/docker-compose.yml --env-file .env down -v
docker compose -f docker/docker-compose.infra.yml --env-file .env down -v
```

### Database Management

```bash
# Initialize schema (run once after fresh start)
docker compose -f docker/docker-compose.yml --env-file .env exec backend python scripts/init_db.py

# Or for native development
cd backend && uv run python scripts/init_db.py
```

### Health Checks

```bash
# Check all services
docker compose -f docker/docker-compose.yml --env-file .env ps

# Check specific service
docker compose -f docker/docker-compose.yml --env-file .env ps backend

# Test backend health endpoint
curl http://localhost:8000/health

# Test frontend
curl http://localhost:3000
```

---

## Troubleshooting

### Port Conflicts

If you see "port is already allocated" errors:

```bash
# Find what's using port 8000
lsof -i :8000

# Or use different ports in your .env
BACKEND_PORT=8001
FRONTEND_PORT=3002
```

### Database Connection Issues

```bash
# Reset database (WARNING: deletes all data)
docker compose -f docker/docker-compose.infra.yml --env-file .env down -v
docker compose -f docker/docker-compose.infra.yml --env-file .env up -d

# Re-initialize schema
cd backend && uv run python scripts/init_db.py
```

### Docker Build Cache Issues

```bash
# Clean build with no cache
docker compose -f docker/docker-compose.yml --env-file .env build --no-cache
docker compose -f docker/docker-compose.yml --env-file .env up -d
```

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
cp backend/.env.example backend/.env
```

**Critical variables:**
- `SIGNING_KEY` — 32-byte hex key for cryptographic signing
- `POSTGRES_PASSWORD` — Database password
- `CORS_ALLOWED_ORIGINS` — Frontend URLs

Generate a signing key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
