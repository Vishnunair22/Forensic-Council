# Forensic Council

Upload digital evidence. Five AI agents analyze it concurrently. Get a cryptographically signed forensic report.

[![Version](https://img.shields.io/badge/version-v1.0.3-blue.svg)](#) [![Status](https://img.shields.io/badge/status-stable-green.svg)](#) [![Postgres](https://img.shields.io/badge/postgres-17-blue.svg)](#) [![License](https://img.shields.io/badge/license-MIT-green.svg)](#) [![Python](https://img.shields.io/badge/python-3.12-blue.svg)](#) [![Next.js](https://img.shields.io/badge/next.js-16-black.svg)](#)

*A Multi-Agent Forensic Evidence Analysis System*

---

## What it does

Forensic Council provides an automated, auditable pipeline for determining the authenticity of digital media. It solves the bottleneck of manual forensic review by orchestrating five specialized AI agents that independently analyze images, audio, video, objects, and metadata for signs of tampering or deepfakery. A Council Arbiter synthesizes their findings into a cohesive, cryptographically signed (ECDSA P-256) report, establishing a secure chain of custody from the moment of upload.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Frontend (Next.js 16)               │
│  Landing → Evidence Upload → Live Analysis → Report  │
│             WebSocket Live Updates                   │
└─────────────────┬───────────────────────────────────┘
                  │ HTTP + WS
┌─────────────────▼───────────────────────────────────┐
│               FastAPI Backend (Python 3.12)          │
│  ┌────────────────────────────────────────────┐      │
│  │         Orchestration Pipeline              │      │
│  │  ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐       │      │
│  │  │ A1 │ │ A2 │ │ A3 │ │ A4 │ │ A5 │       │      │
│  │  │Img │ │Aud │ │Obj │ │Vid │ │Meta│       │      │
│  │  └──┬─┘ └──┬─┘ └──┬─┘ └──┬─┘ └──┬─┘       │      │
│  │     └──────┴──────┴──────┴──────┘          │      │
│  │              Council Arbiter                │      │
│  └────────────────────────────────────────────┘      │
│  ReAct Loop │ Working Memory │ Custody Logger        │
└──────┬──────────────┬───────────────┬────────────────┘
       │              │               │
   ┌───▼──┐      ┌────▼───┐     ┌────▼───┐
   │Redis │      │Postgres│     │ Qdrant │
   └──────┘      └────────┘     └────────┘
```

---

## The Agents

| Agent | Specialty | Focus |
|-------|-----------|-------|
| **Agent 1** — Image Forensics | ELA, EXIF analysis, splice detection | Detects pixel-level manipulation, splicing, and generative artifacts |
| **Agent 2** — Audio Forensics | Spectral analysis, voice anomaly detection | Identifies audio deepfakes, synthetic voices, and audio splicing |
| **Agent 3** — Object Detection | Scene consistency, object context analysis | Validates scale, lighting direction, and spatial compositing |
| **Agent 4** — Video Forensics | Frame analysis, temporal consistency checks | Analyzes temporal inconsistencies and deepfake face-swapping |
| **Agent 5** — Metadata Forensics | EXIF/XMP parsing, timestamp/GPS validation | Correlates container metadata structures against visual evidence |
| **Council Arbiter** | Cross-modal correlation & cryptographic signing | Synthesizes agent findings, resolves conflicts via HITL, and produces the final immutable report |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, Tailwind v4, Framer Motion |
| Backend | Python 3.12, FastAPI, LangGraph, asyncpg |
| Ledger | PostgreSQL 17 (ACID custody logging) |
| Cache / Pub-Sub | Redis 7 (WebSocket events, rate limiting, token blacklisting) |
| Vector DB | Qdrant (local-first, no cloud dependency) |
| Signing | ECDSA P-256 / SHA-256 (deterministic chain of custody) |
| Proxy | Caddy 2 (automatic TLS via Let's Encrypt) |
| Package mgmt | uv (Python), npm (Node) |

---

## Quick Start

### Prerequisites
- Docker Desktop 23+ (or Docker Engine + Compose v2 with BuildKit)
- An LLM API key — **Groq is recommended** (free tier: [console.groq.com](https://console.groq.com/keys))

### 1. Configure environment
```bash
# Linux / macOS
cp .env.example .env

# Windows (PowerShell)
Copy-Item .env.example .env
```

Open `.env` and fill in at minimum:
```dotenv
LLM_PROVIDER=groq
LLM_API_KEY=gsk_your_groq_key_here   # free at console.groq.com/keys
```

To run without an LLM (tool-only mode), set `LLM_PROVIDER=none`.

### 2. Start the stack

| Mode | Command | Description |
|:---|:---|:---|
| **Development** (hot-reload) | `.\manage.ps1 dev` | Source volumes mounted; Uvicorn + Next.js watch mode |
| **Production** | `.\manage.ps1 prod` | Optimised multi-stage build, non-root containers |
| **Infrastructure only** | `.\manage.ps1 infra` | Postgres + Redis + Qdrant only, for native dev |
| **Logs** | `.\manage.ps1 logs` | Tail all container logs |
| **Stop** | `.\manage.ps1 down` | Stop containers (keeps volumes / ML models) |
| **Full reset** | `.\manage.ps1 down-clean` | Stop + delete all volumes including ML models |

**Linux / macOS** — use `docker compose` directly:
```bash
# Development
docker compose -f docs/docker/docker-compose.yml \
               -f docs/docker/docker-compose.dev.yml \
               --env-file .env up --build

# Production
docker compose -f docs/docker/docker-compose.yml \
               -f docs/docker/docker-compose.prod.yml \
               --env-file .env up --build -d
```

### 3. Open the app

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs *(development only)* |

Default login credentials are set by `NEXT_PUBLIC_DEMO_PASSWORD` in `.env` (default: `inv123!`).

---

## Docker Caching Strategy

The build uses a three-tier caching system so rebuilds after the first are near-instant.

### 1. Docker Layer Cache (OS & Deps)
Layers are ordered so that code changes (most frequent) happen last.
- **Code-only change:** Rebuilds only the final layer (~10–30 s).
- **New dependency:** Triggers `uv sync` / `npm ci` but reuses the global package HTTP cache.

### 2. BuildKit Cache Mounts (Package Cache)
Specified via `--mount=type=cache` in both Dockerfiles. These persist across image rebuilds.
- **Backend:** `uv` HTTP cache at `/root/.cache/uv`.
- **Frontend:** `npm` cache at `/root/.npm` and Next.js compiler cache at `/app/.next/cache`.
- *Wipe:* `docker builder prune -f`

### 3. ML Model Volumes (Heavy Cache)
ML models (PyTorch, Transformers, YOLO, DeepFace, etc.) live in **named Docker volumes** shared between dev and prod because both use `COMPOSE_PROJECT_NAME=forensic-council`.
- **Volumes:** `hf_cache`, `torch_cache`, `easyocr_cache`, `yolo_cache`, `deepface_cache`
- **First run:** Models download (~10–15 GB total). Expected startup time: 20–60 min depending on internet speed. Subsequent starts: instant.
- **Wipe single model:** `docker volume rm forensic-council_hf_cache`

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `npm ci` fails on `eslint-config-next` version mismatch | ESLint runs separately (`npm run lint`) — it is intentionally disabled during `next build`. Run `npm run lint` locally to check. |
| `uv sync` fails during backend build | Ensure BuildKit is enabled: prefix with `DOCKER_BUILDKIT=1`. Also check network access to PyPI. |
| Frontend shows CORS errors | Check `NEXT_PUBLIC_API_URL` in `.env` is reachable from your browser. The Next.js proxy rewrites `/api/v1/*` server-side, so browser requests are same-origin. |
| `SIGNING_KEY` validation error at startup | Generate a secure key: `python -c "import secrets; print(secrets.token_hex(32))"` |
| ML model downloads fail | Check `HF_TOKEN` is set if using gated models (pyannote speaker diarization). Get a free token at [hf.co/settings/tokens](https://hf.co/settings/tokens). |
| Backend `read_only: true` permission errors | Check that all writable paths are covered by volume mounts or the `/tmp` tmpfs. |
| Old frontend after `.env` change | `NEXT_PUBLIC_*` vars are baked at build time. Rebuild: `docker compose build frontend`. |
| Corrupted packages | `docker builder prune --all -f` wipes the BuildKit cache. |

---

## Key Files

```
Forensic-Council/
├── backend/
│   ├── agents/           # Five forensic agents + Council Arbiter
│   ├── api/              # FastAPI routes, WebSocket managers, schemas
│   ├── core/             # ReAct loop, working memory, custody logger, signing
│   ├── infra/            # Postgres, Redis, Qdrant client singletons
│   ├── orchestration/    # Evidence pipeline + session management
│   ├── tools/            # Analytical tools (ELA, audio, video, metadata)
│   └── scripts/          # ML subprocesses, DB init, entrypoint
├── frontend/
│   ├── src/app/          # Next.js app router pages
│   ├── src/components/   # Evidence, result, and UI components
│   ├── src/hooks/        # useSimulation, useForensicData, useSound
│   └── src/lib/          # API client, Zod schemas, constants
└── docs/
    ├── docker/           # Compose files (base, dev, prod, infra) + Caddyfile
    ├── API.md            # Full endpoint reference
    ├── ARCHITECTURE.md   # System design deep-dive
    └── SECURITY.md       # Security model and threat model
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/auth/login` | Authenticate and get JWT |
| `POST` | `/api/v1/auth/logout` | Invalidate JWT (token blacklist) |
| `POST` | `/api/v1/investigate` | Upload evidence and start investigation |
| `WS` | `/api/v1/sessions/{id}/live` | Live WebSocket cognitive updates |
| `POST` | `/api/v1/hitl/decision` | Submit Human-in-the-Loop decision |
| `GET` | `/api/v1/sessions/{id}/report` | Get cryptographically signed final report |
| `GET` | `/health` | Health check (used by Docker + Caddy) |

Full endpoint reference with request/response payloads → [`docs/API.md`](docs/API.md)

---

## Development Status

Current status, known limitations, and roadmap → [`docs/status/Development-Status.md`](docs/status/Development-Status.md)

---

## License

[MIT](LICENSE)
