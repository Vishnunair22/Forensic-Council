# Forensic Council

Forensic Council is a multi-agent forensic analysis platform for digital media verification. It accepts evidence uploads, runs five specialist agents through an initial and deep analysis pipeline, and returns a cryptographically signed forensic report.

[![Version](https://img.shields.io/badge/version-v1.7.0-blue.svg)](#)
[![Status](https://img.shields.io/badge/status-production_hardening-yellow.svg)](#)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](#) Python 3.12 (tested/recommended); `pyproject.toml` supports 3.11–3.14
[![Next.js](https://img.shields.io/badge/next.js-15-black.svg)](#)

## What this project is

Forensic Council is a multi-agent forensic analysis platform for digital media verification. It accepts evidence uploads, runs five specialist agents through an initial and deep analysis pipeline with optional human-in-the-loop review, and returns a cryptographically signed forensic report.

Every significant action is written to the chain-of-custody ledger, and final verdicts are computed deterministically from structured findings rather than being assigned by an LLM.

## Monorepo structure

```text
apps/web       Next.js 15 frontend (React 19, Tailwind CSS, TanStack Query, Playwright, Jest)
apps/api       FastAPI backend (Python 3.12, Pydantic v2, Redis, PostgreSQL, Qdrant)
infra          Docker Compose, Caddy reverse proxy, Prometheus, Jaeger
docs           source-of-truth documentation
scripts        verification and utility scripts
```

## Core workflow

See [docs/WORKFLOW_TRACE.md](docs/WORKFLOW_TRACE.md) for the canonical route/state flow.

## Fast start

### Docker — development (one command)

```bash
[ -f .env ] || cp .env.example .env
bash infra/generate_production_keys.sh --update
# Add LLM_API_KEY and GEMINI_API_KEY to .env, then:
bash scripts/dev.sh
```

`scripts/dev.sh` validates `.env`, builds all images in parallel, starts the stack, and polls health before returning.

#### Development Hot-Reloading & Workflow Tips

- **Backend & Frontend Hot-Reloading**: Backend API code changes are automatically reloaded by Uvicorn within the container. Frontend Next.js changes are hot-reloaded in the browser via Turbopack HMR.
- **Worker Code Changes**: Background workers do not auto-reload. To pick up code changes in agents, tools, or orchestration instantly without waiting for the 300s stop grace period, run:
  ```bash
  bash scripts/dev-restart-worker.sh
  ```
- **Dependency Changes**: If you modify `pyproject.toml` or `uv.lock`, rebuild the python containers:
  ```bash
  docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env build backend worker
  ```
- **Environment Changes**: If you update `.env`, recreate the containers to apply the changes:
  ```bash
  docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env up -d --force-recreate
  ```

### Docker — production (one command)

```bash
bash scripts/prod.sh
```

`scripts/prod.sh` runs `validate_production_readiness.sh` first (gates on failures), then builds and starts.

### Host app development with Docker infrastructure

```bash
# Start infrastructure services only
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env up -d postgres redis qdrant

# Backend
cd apps/api && uv sync --extra dev --extra security --extra observability --extra ml
POSTGRES_HOST=localhost REDIS_HOST=localhost QDRANT_HOST=localhost USE_REDIS_WORKER=false uv run python scripts/init_db.py
POSTGRES_HOST=localhost REDIS_HOST=localhost QDRANT_HOST=localhost USE_REDIS_WORKER=false uv run python scripts/run_api.py

# Frontend (separate terminal)
cd apps/web && npm ci && npm run dev
```

### Fully non-Docker development

For a fully non-Docker run, install and run these services on the host:

- PostgreSQL 17+
- Redis 7+
- Qdrant 1.16.x
- Python 3.12
- Node.js 22
- uv
- ffmpeg
- tesseract
- exiftool
- libmagic
- mediainfo

Then create a local env file (use `.env.host.example` for host-run development; `.env.example` is reserved for Docker):

```bash
[ -f .env ] || cp .env.host.example .env
```

> If `.env` already exists, neither command overwrites it. Delete `.env` first if you intentionally want to reset.

Start backend:

```bash
cd apps/api
uv sync --locked --extra dev --extra security --extra observability --extra ml

POSTGRES_HOST=localhost \
REDIS_HOST=localhost \
QDRANT_HOST=localhost \
USE_REDIS_WORKER=false \
uv run python scripts/init_db.py

POSTGRES_HOST=localhost \
REDIS_HOST=localhost \
QDRANT_HOST=localhost \
USE_REDIS_WORKER=false \
uv run python scripts/run_api.py
```

Start frontend in a second terminal:

```bash
cd apps/web
npm ci
NEXT_PUBLIC_API_URL=http://localhost:8000 \
INTERNAL_API_URL=http://localhost:8000 \
npm run dev
```

> [!IMPORTANT]
> When compiling for production using `npm run build` (rather than running in dev via `npm run dev`), Next.js bakes `NEXT_PUBLIC_API_URL` statically into the client-side JavaScript bundle. You must supply this environment variable during the `npm run build` compilation step, otherwise frontend client actions will fail to route to the API.

> [!IMPORTANT]
> **Host-Run Limitations**: Running in host-run mode (using `USE_REDIS_WORKER=false`) executes all investigations in-process within the backend API server. This mode does not use the background worker service, meaning worker graceful shutdown, stop grace periods, and task drain behaviors are not exercised. Use Docker mode (dev or prod) to test full pipeline worker lifecycle and drain behavior.

Verify:

```bash
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:3000/
```

## Testing

| Suite | Command |
|-------|---------|
| All static checks | `./scripts/verify_project.sh static` |
| Backend unit/integration | `./scripts/verify_project.sh backend` |
| Frontend unit/build | `./scripts/verify_project.sh frontend` |
| Frontend E2E (fast, mocked) | `cd apps/web && npm run test:e2e:journey` |
| Test hygiene | `python scripts/check_test_hygiene.py` |
| Docs consistency | `python scripts/check_docs.py` |

See [docs/TESTING.md](docs/TESTING.md) for full test commands and coverage targets.

## Operations

- [docs/OPERATIONAL_RUNBOOK.md](docs/OPERATIONAL_RUNBOOK.md) — incident triage, common failures, recovery commands
- [docs/PRODUCTION_CHECKLIST.md](docs/PRODUCTION_CHECKLIST.md) — production deployment gates
- [infra/README.md](infra/README.md) — Docker/infra quickstart and commands

## Security

See [docs/SECURITY.md](docs/SECURITY.md) for authentication, authorization, upload validation, chain-of-custody, secrets management, and rate limiting.

## Model / provider registry

See [docs/MODEL_REGISTRY.md](docs/MODEL_REGISTRY.md) for Groq/Gemini free-tier setup, model pinning, licensing, and verification.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for system runtime topology, agent flow, infrastructure components, and security architecture.

## API contract

See [docs/API_CONTRACT.md](docs/API_CONTRACT.md) for complete backend/frontend API contract including auth, investigation, WebSocket/SSE, HITL, report, and termination endpoints.

## Contributor Handoff

See [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md) — read this before editing the repo. It contains the current phase, changed files, verification commands, and local contributor rules.

## License

Forensic Council is released under the [MIT License](LICENSE).
