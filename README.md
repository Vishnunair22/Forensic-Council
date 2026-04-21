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
apps/
  api/      FastAPI backend, agents, orchestration, tools, tests
  web/      Next.js frontend, UI components, hooks, API client, tests
docs/       architecture, API, security, runbooks, project state
infra/      Docker Compose, Caddy, deployment and validation scripts
```

## Requirements

- Docker Desktop 23+ for full-stack local deployment.
- Python 3.12 for backend development.
- Node.js 22+ for frontend development.
- A Groq-compatible `LLM_API_KEY` when LLM reasoning or synthesis is enabled.
- A `GEMINI_API_KEY` for multimodal Gemini grounding.
- Enough disk space for ML model caches. A first full run can download many GB of model files.

## Quick Start

Create an environment file:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set at least:

```text
SIGNING_KEY=<strong unique value, 32+ chars>
JWT_SECRET_KEY=<strong unique value, 32+ chars>
POSTGRES_PASSWORD=<strong password>
REDIS_PASSWORD=<strong password>
LLM_API_KEY=<Groq API key or compatible provider key>
GEMINI_API_KEY=<Google Gemini API key>
```

Start the full stack:

```powershell
docker compose -f infra/docker-compose.yml --env-file .env up --build
```

For local development without Docker:

```powershell
# Backend
cd apps/api
uv sync
uv run python scripts/run_api.py

# Frontend, in another shell
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
npm run docker:up  # full Docker stack
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
