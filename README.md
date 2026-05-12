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

### Docker (all services)

```bash
cp .env.example .env
bash infra/generate_production_keys.sh --update
# Add LLM_API_KEY and GEMINI_API_KEY to .env
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env up --build -d
# Verify: curl http://localhost:8000/health
```

### No Docker (infra only, app on host)

```bash
# Start infrastructure services
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env up -d postgres redis qdrant

# Backend
cd apps/api && uv sync --extra dev --extra security --extra observability
POSTGRES_HOST=localhost REDIS_HOST=localhost QDRANT_HOST=localhost USE_REDIS_WORKER=false uv run python scripts/init_db.py
POSTGRES_HOST=localhost REDIS_HOST=localhost QDRANT_HOST=localhost USE_REDIS_WORKER=false uv run python scripts/run_api.py

# Frontend
cd apps/web && npm ci && npm run dev
```

## Testing

| Suite | Command |
|-------|---------|
| All static checks | `./scripts/verify_project.sh static` |
| Backend unit/integration | `./scripts/verify_phase8_tests.sh backend-unit && ./scripts/verify_phase8_tests.sh backend-integration` |
| Frontend unit/build | `./scripts/verify_phase8_tests.sh frontend-unit` |
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

## Local AI / handoff

See [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md) — read this before editing the repo. It contains the current phase, changed files, verification commands, and rules for local AI behavior.

## License

Forensic Council is released under the [MIT License](LICENSE).
