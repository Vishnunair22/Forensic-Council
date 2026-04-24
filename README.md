# Forensic Council

Forensic Council is a multi-agent forensic analysis platform for digital media verification. It accepts evidence uploads, runs five specialist agents through an initial and deep analysis pipeline, and returns a cryptographically signed forensic report.

[![Version](https://img.shields.io/badge/version-v1.4.0-blue.svg)](#)
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
```powershell
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
```powershell
docker compose `
  -f infra/docker-compose.yml `
  -f infra/docker-compose.prod.yml `
  --env-file .env `
  up --build -d
```

### 5. Verify Readiness
Once the containers are healthy, run the production readiness check:
```bash
./infra/validate_production_readiness.sh
```

## Local Development (No Docker)

If you prefer to run services directly on your host machine:

### Backend
```powershell
cd apps/api
uv sync
uv run python scripts/run_api.py
```

### Frontend
```powershell
cd apps/web
npm install
npm run dev
```

## Common Commands

From the repository root:

```powershell
npm run dev        # backend and frontend development servers
npm run lint       # backend ruff + frontend eslint
npm run test       # backend pytest + frontend jest
npm run build:web  # frontend production build
npm run docker:dev  # full Docker stack
```

Backend-only:

```powershell
cd apps/api
uv run ruff check .
uv run pyright core/ agents/ api/ tools/
uv run pytest tests/ -v
```

Frontend-only:

```powershell
cd apps/web
npm run lint
npm run type-check
npm test
```

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

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [API Reference](docs/API.md)
- [Agent Capabilities](docs/agent_capabilities.md)
- [Chain of Custody](docs/CHAIN_OF_CUSTODY.md)
- [Security](docs/SECURITY.md)
- [Testing](docs/TESTING.md)
- [Runbook](docs/RUNBOOK.md)
- [Current State](docs/STATE.md)
- [Development Setup](docs/DEVELOPMENT_SETUP.md)

## Development Guardrails

- Keep verdict logic deterministic. LLMs may summarize findings, but they must not set verdicts.
- Be careful around Arbiter scoring and reliability weights.
- Use `core.*` backend imports rather than legacy `infra.*` imports.
- Use `@/lib/storage` for non-auth frontend storage.
- Keep auth tokens in session-scoped storage or HttpOnly cookies.
- Preserve chain-of-custody logging for significant forensic actions.

## License

Forensic Council is released under the [MIT License](LICENSE).
