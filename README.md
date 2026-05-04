# Forensic Council

Forensic Council is a multi-agent forensic analysis platform for digital media verification. It accepts evidence uploads, runs five specialist agents through an initial and deep analysis pipeline, and returns a cryptographically signed forensic report.

[![Version](https://img.shields.io/badge/version-v1.7.0-blue.svg)](#)
[![Status](https://img.shields.io/badge/status-production_hardening-yellow.svg)](#)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](#)
[![Next.js](https://img.shields.io/badge/next.js-15-black.svg)](#)

## What It Does

The system helps investigators assess whether an image, audio clip, video, or related media artifact appears authentic, manipulated, AI-generated, or inconclusive.

The investigation flow is:

```text
Browser upload
  -> FastAPI evidence ingestion
  -> SHA-256 hashing and custody logging
  -> five specialist forensic agents
  -> optional human-in-the-loop checkpoint
  -> deep multimodal analysis
  -> Council Arbiter verdict
  -> ECDSA-signed forensic report
```

Every significant action is written to the chain-of-custody ledger, and final verdicts are computed deterministically from structured findings rather than being assigned by an LLM.

## Architecture

```text
Next.js frontend
  -> FastAPI backend
  -> ForensicCouncilPipeline
  -> Image, Audio, Object, Video, and Metadata agents
  -> Council Arbiter
  -> Signed report

Supporting services:
  Redis      working memory, rate limiting, live state
  Postgres   evidence ledger, reports, custody records
  Qdrant     episodic vector memory
  Caddy      production TLS/reverse proxy
```

The pipeline uses two analysis phases:

1. **Initial Pass**: fast, high-recall screening with classical and lightweight ML tools.
2. **Deep Pass**: heavier forensic checks, multimodal Gemini grounding, and cross-agent context sharing.

Agent 1 performs image and vision grounding first during deep analysis, then injects context into the object and metadata agents before the remaining deep checks complete.

## Agents

| Agent | Focus | Examples |
| --- | --- | --- |
| Image | visual manipulation and generation signals | ELA, splicing, diffusion artifacts, noise residuals |
| Audio | speech and signal integrity | diarization, splice detection, voice synthesis signals |
| Object | scene and physical consistency | YOLO detection, lighting, object coherence |
| Video | temporal integrity | frame consistency, rolling shutter, inter-frame forgery |
| Metadata | provenance and container evidence | EXIF, GPS, C2PA/JUMBF, container metadata |

The Council Arbiter deduplicates findings, weighs evidence reliability, computes `manipulation_probability`, selects the verdict, and signs the report.

## Repository Layout

```text
Forensic Council
├── apps/
│   ├── api/                 # FastAPI backend
│   │   ├── agents/          # 5 specialized forensic agents + Arbiter
│   │   ├── api/             # API routes, schemas, and main entrypoint
│   │   ├── core/            # Infrastructure: LLM, persistence, auth
│   │   ├── orchestration/   # Pipeline and worker logic
│   │   ├── tools/           # Domain-specific forensic analysis tools
│   │   └── tests/           # Unit and integration test suite
│   └── web/                 # Next.js 15 frontend
│       ├── src/
│       │   ├── app/         # Next.js App Router (pages & layouts)
│       │   ├── components/  # React UI components
│       │   ├── hooks/       # Custom React hooks
│       │   └── lib/         # API client, storage, and utilities
│       └── tests/           # Jest and Playwright tests
├── docs/                    # Architectural and API documentation
├── infra/                   # Docker, Caddy, and orchestration config
└── .env.example             # Template for environment variables
```

## Production Docker Setup

For a full-scale, production-ready deployment, follow these steps. For more granular details on build targets and caching, see [infra/DOCKER_BUILD.md](infra/DOCKER_BUILD.md).

### 1. Initialize Environment
Copy the example environment file to create your local `.env`:

```bash
# bash / zsh
cp .env.example .env
```
```powershell
# PowerShell
Copy-Item .env.example .env
```

### 2. Generate Secure Secrets
Run the provided script to generate high-entropy keys for forensic signing, JWT sessions, and database passwords:
```bash
./infra/generate_production_keys.sh
```
**Important**: Manually paste the output values for `SIGNING_KEY`, `JWT_SECRET_KEY`, `POSTGRES_PASSWORD`, etc., into your `.env` file.

### 3. Configure External APIs
Edit `.env` and provide your API keys for the analysis engines:
- `LLM_API_KEY`: Groq API key for agent reasoning.
- `GEMINI_API_KEY`: Google Gemini key for multimodal grounding.

### 4. Deploy the Stack
Start the production stack using the primary and production override files. This ensures build-time optimizations and security hardening are applied:

```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.prod.yml \
  --env-file .env \
  up --build -d
```
```powershell
docker compose `
  -f infra/docker-compose.yml `
  -f infra/docker-compose.prod.yml `
  --env-file .env `
  up --build -d
```

> **Warning:** Without the `-f infra/docker-compose.prod.yml` overlay, `docker compose up` builds the `development` stage (line 258 of docker-compose.yml), which includes debug tooling and hot-reload. Always include the prod overlay for production deployments.

### 5. Verify Readiness
Once the containers are healthy, run the production readiness check:
```bash
./infra/validate_production_readiness.sh
```

## Local Development (No Docker App Processes)

If you prefer to run the API and frontend directly on your host machine, use
Docker only for Postgres, Redis, and Qdrant.

### Prerequisites
- Node.js >= 20.10.0
- Python 3.12
- uv (install: `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Docker Desktop/Engine for the local infrastructure services

### 1. Start Infrastructure
```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env up -d postgres redis qdrant
```

The dev override exposes host ports for direct app runs: Postgres `5432`, Redis
`6379`, Qdrant `6333/6334`. The base and production stacks keep those
infrastructure services internal.

### 2. Backend
Run from `apps/api`. Override infrastructure hosts to `localhost` for this
shell so you do not have to rewrite `.env`, which Docker still expects to use
service names such as `postgres` and `redis`.

```bash
# bash / zsh
cd apps/api
uv sync --all-extras --extra dev

# One-time: initialize the database schema and bootstrap users
POSTGRES_HOST=localhost REDIS_HOST=localhost QDRANT_HOST=localhost USE_REDIS_WORKER=false uv run python scripts/init_db.py

POSTGRES_HOST=localhost REDIS_HOST=localhost QDRANT_HOST=localhost USE_REDIS_WORKER=false uv run python scripts/run_api.py
```
```powershell
# PowerShell
cd apps/api
uv sync --all-extras --extra dev

# One-time: initialize the database schema and bootstrap users
$env:POSTGRES_HOST="localhost"; $env:REDIS_HOST="localhost"; $env:QDRANT_HOST="localhost"; $env:USE_REDIS_WORKER="false"
uv run python scripts/init_db.py
uv run python scripts/run_api.py
```

> **Note:** The `model_pre_download.py --strict` step downloads all ML models (~2-4 GB) so the first investigation doesn't block for 5-20 minutes. Skip this step for CI/local testing without model downloads.

### 3. Frontend
```bash
# bash / zsh
cd apps/web
npm ci
npm run dev
```
```powershell
# PowerShell
cd apps/web
npm.cmd ci
npm.cmd run dev
```

> **Note:** When running the frontend on `http://localhost:3000` directly (without Caddy reverse proxy), API calls to `/api/*` are automatically proxied by the Next.js dev server to the backend at port 8000. This works via `apps/web/src/app/api/v1/[...path]/route.ts`. No `NEXT_PUBLIC_API_URL` configuration is needed for local development without Docker.

### Local Checks
There is no root workspace package. Run backend checks from `apps/api` and frontend checks from `apps/web`. See [apps/api/README.md](apps/api/README.md) and [apps/web/README.md](apps/web/README.md) for per-package development instructions.

## Common Commands

Backend and frontend are in separate directories. Run backend commands from `apps/api/` and frontend commands from `apps/web/`:

```powershell
# Backend (from apps/api/)
cd apps/api
uv run ruff check .
uv run ruff format .
uv run pyright core/ agents/ api/ tools/ orchestration/
uv run pytest tests/ -q --tb=short --basetemp .pytest_tmp_run
uv run uvicorn api.main:app --reload --port 8000

# Frontend (from apps/web/)
cd apps/web
npm.cmd run dev
npm.cmd run lint
npm.cmd run type-check
npm.cmd test -- --runInBand
npm.cmd run build

# Full Docker stack
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file .env up -d
```

PowerShell may block `npm.ps1` on some Windows systems. Use `npm.cmd` when that
happens.

## Configuration

The canonical environment template is [.env.example](.env.example). Important variables include:

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | Runtime mode, commonly `production`, `development`, or `testing` |
| `SIGNING_KEY` | Root secret used for forensic signing key derivation |
| `JWT_SECRET_KEY` | Separate secret for JWT/session signing |
| `POSTGRES_PASSWORD` | PostgreSQL password used by the Docker stack |
| `REDIS_PASSWORD` | Redis password required in production |
| `LLM_PROVIDER` | LLM provider name, defaulting to `groq` |
| `LLM_API_KEY` | API key for Groq or the configured LLM provider |
| `GEMINI_API_KEY` | API key for Gemini multimodal analysis |
| `GEMINI_MODEL` | Gemini model name, defaulting to `gemini-2.5-flash` |
| `GEMINI_FALLBACK_MODELS` | ordered Gemini fallback cascade for deep analysis |
| `NEXT_PUBLIC_API_URL` | Browser-visible backend API URL |
| `INTERNAL_API_URL` | Container/server-side backend API URL |
| `CORS_ALLOWED_ORIGINS` | Explicit browser origins allowed to call the API |

Never commit `.env` or real secrets.

## Common Issues

### `ModuleNotFoundError` on backend start
Run `uv sync --all-extras` from the `apps/api/` directory. The virtualenv is managed by uv.

### Frontend `EACCES` permission error
Delete `node_modules` and reinstall: `rm -rf node_modules && npm install`

### Docker port conflict (5432/6379)
Another Postgres or Redis instance is running. Stop it or change ports in `.env`.

### `GEMINI_API_KEY not set` warning
This is normal for local development. Agents 1, 3, 5 will use local fallback analysis. Set the key in `.env` to enable Gemini vision.

### bcrypt version compatibility
`pyproject.toml` pins `bcrypt>=3.2,<4.1`. While passlib 1.7.4 has known incompatibilities with bcrypt 4.x, the codebase includes `_bcrypt_shim.py` to handle this. If you encounter auth issues after upgrading dependencies, check the shim is loaded.

## Beyond docker compose

Kubernetes and Swarm manifests are out of scope for v1.7.x. Track production K8s adoption in [docs/RUNBOOK.md#future-k8s-path].

For horizontal scaling with the current docker compose setup, consider:
- Running multiple backend replicas behind Caddy (configure via `backend` service `deploy.replicas` in docker-compose.prod.yml)
- Using Redis cluster for pub/sub across replicas
- Externalized PostgreSQL with connection pooling

> **Note:** The Docker Swarm configuration example in Option 1 above is provided as a reference for future implementation but is not currently maintained.

Generate secrets from `.env` for future K8s migration:
```bash
kubectl create secret generic forensic-secrets \
  --from-literal=POSTGRES_PASSWORD="$(grep POSTGRES_PASSWORD .env | cut -d= -f2)" \
  --from-literal=JWT_SECRET_KEY="$(grep JWT_SECRET_KEY .env | cut -d= -f2)" \
  --from-literal=SIGNING_KEY="$(grep SIGNING_KEY .env | cut -d= -f2)"
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [API Reference](docs/API.md)
- [Agent Capabilities](docs/AGENT_CAPABILITIES.md)
- [Chain of Custody](docs/CHAIN_OF_CUSTODY.md)
- [Security](docs/SECURITY.md)
- [Testing](docs/TESTING.md)
- [Runbook](docs/RUNBOOK.md)

## Development Guardrails

- Keep verdict logic deterministic. LLMs may summarize findings, but they must not set verdicts.
- Be careful around Arbiter scoring and reliability weights.
- Use `core.*` backend imports rather than legacy `infra.*` imports.
- Use `@/lib/storage` for non-auth frontend storage.
- Keep auth tokens in session-scoped storage or HttpOnly cookies.
- Preserve chain-of-custody logging for significant forensic actions.

## License

Forensic Council is released under the [MIT License](LICENSE).
