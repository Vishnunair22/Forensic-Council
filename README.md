# Forensic Council

Upload digital evidence. Five AI agents analyze it concurrently. Get a cryptographically signed forensic report in seconds.

[![Version](https://img.shields.io/badge/version-v1.0.0-blue.svg)](#) [![Status](https://img.shields.io/badge/status-stable-green.svg)](#) [![Postgres](https://img.shields.io/badge/postgres-17-blue.svg)](#) [![License](https://img.shields.io/badge/license-MIT-green.svg)](#)

*A Multi-Agent Forensic Evidence Analysis System*

## What it does

Forensic Council provides an automated, auditable pipeline for determining the authenticity of digital media. It solves the bottleneck of manual forensic review by orchestrating five specialized AI agents that independently analyze images, audio, video, objects, and metadata for signs of tampering or deepfakery. A Council Arbiter synthesizes their findings into a cohesive, cryptographically signed report, establishing a secure chain of custody from the moment of upload.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Frontend (Next.js 15)              │
│  Landing → Evidence Upload → Live Analysis → Report │
│             WebSocket Live Updates                  │
└─────────────────┬───────────────────────────────────┘
                  │ HTTP + WS
┌─────────────────▼───────────────────────────────────┐
│               FastAPI Backend                       │
│  ┌────────────────────────────────────────────┐     │
│  │         Orchestration Pipeline              │     │
│  │  ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐       │     │
│  │  │ A1 │ │ A2 │ │ A3 │ │ A4 │ │ A5 │       │     │
│  │  │Img │ │Aud │ │Obj │ │Vid │ │Meta│       │     │
│  │  └──┬─┘ └──┬─┘ └──┬─┘ └──┬─┘ └──┬─┘       │     │
│  │     └──────┴──────┴──────┴──────┘         │     │
│  │              Council Arbiter               │     │
│  └────────────────────────────────────────────┘     │
│  ReAct Loop │ Working Memory │ Custody Logger       │
└──────┬──────────────┬───────────────┬───────────────┘
       │              │               │
   ┌───▼──┐      ┌────▼───┐     ┌────▼───┐
   │Redis │      │Postgres│     │ Qdrant │
   └──────┘      └────────┘     └────────┘
```

The system is triggered via the frontend, uploading evidence to the FastAPI backend. A Redis session stores the real-time reasoning (ReAct loop state) of the five distinct agents executing sequentially (Image → Audio → Object → Video → Metadata). Agents utilize LangGraph and specialized mathematical subprocesses (out of the event loop) for heavy anomaly detection. The Council Arbiter cross-references their findings, generates an ECDSA-signed report, and logs the outcome immutably in PostgreSQL, while the UI receives live step-by-step updates via WebSockets.

## The Agents

| Agent | Specialty | Focus |
|-------|-----------|-------|
| **Agent 1** — Image Forensics | ELA, EXIF analysis, splice detection | Detects pixel-level manipulation, splicing, and generative artifacts. |
| **Agent 2** — Audio Forensics | Spectral analysis, voice anomaly detection | Identifies audio deepfakes, synthetic voices, and audio splicing. |
| **Agent 3** — Object Detection | Scene consistency, object context analysis | Validates scale, lighting direction, and spatial compositing. |
| **Agent 4** — Video Forensics | Frame analysis, temporal consistency checks | Analyzes temporal inconsistencies and deepfake face-swapping. |
| **Agent 5** — Metadata Forensics | EXIF/XMP parsing, timestamp/GPS validation | Correlates container metadata structures against visual evidence. |
| **Council Arbiter** | Cross-modal correlation & cryptographic signing | Synthesizes agent findings, resolves conflicts via HITL, and produces the final immutable report. |

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Frontend | Next.js 15, React 19 | Responsive UI, fluid animations via Framer Motion & Tailwind v4. |
| Backend | Python 3.12+, FastAPI, LangGraph | High-performance async API with structured agentic graph orchestration. |
| Ledger | PostgreSQL 17 | ACID-compliant custody logging and final report storage. |
| Memory | Redis 7 | High-speed pub/sub for WebSocket event broadcasting and working memory. |
| Vector DB | Qdrant | Local-first dense vector similarity search; no managed cloud service required. |
| Signing | ECDSA (SHA-256) | Deterministic, auditable chain of custody without complex PKI infrastructure. |

## Quick Start

### Method 1: Using the PowerShell Manager (Recommended)
```bash
# 1. Copy environment template (required)
cp .env.example .env

# 2. Start full Docker stack (builds images + starts services)
.\manage.ps1 up
```

### Method 2: Raw Docker Compose (Fallback)
If execution policies block the script, you can run the raw command:
```bash
docker compose -f docs/docker/docker-compose.yml --env-file .env up -d --build
```

**→ For detailed build and caching strategies, see [`docs/docker/DOCKER_BUILD.md`](docs/docker/DOCKER_BUILD.md).**

## 🚀 Development Mode (Hot Reload)

Run the full stack with hot-reload enabled for both Backend and Frontend:

```bash
# From project root using the manager:
.\manage.ps1 dev

# OR using raw Docker commands:
docker compose -f docs/docker/docker-compose.yml -f docs/docker/docker-compose.dev.yml --env-file .env up -d --build
```

### What's Enabled:

| Service | Hot Reload | Port |
|---------|-------------|------|
| **Backend** (Python/Uvicorn) | ✅ Auto-restart on file save | 8000 |
| **Frontend** (Next.js) | ✅ Fast Refresh | 3000 |
| **PostgreSQL** | - | 5432 |
| **Redis** | - | 6379 |
| **Qdrant** | - | 6333 |

### Common Commands:

| Action | Manager Command | Raw Docker Equivalent |
|:-------|:----------------|:----------------------|
| **Start Production** | `.\manage.ps1 prod` | `docker compose -f docs/docker/docker-compose.yml -f docs/docker/docker-compose.prod.yml --env-file .env up -d --build` |
| **Stop all services** | `.\manage.ps1 down` | `docker compose -f docs/docker/docker-compose.yml --env-file .env down` |
| **Smart Rebuild Backend** | `.\manage.ps1 rebuild-backend` | `docker compose -f docs/docker/docker-compose.yml --env-file .env build backend && docker compose -f docs/docker/docker-compose.yml --env-file .env up -d --no-deps backend` |
| **View logs** | `.\manage.ps1 logs` | `docker compose -f docs/docker/docker-compose.yml --env-file .env logs -f` |

### Native Development (without Docker):

```bash
# Start required databases natively via Docker first
.\manage.ps1 infra
# (Fallback: docker compose -f docs/docker/docker-compose.infra.yml --env-file .env up -d)

# Run backend natively
cd backend && uv sync --extra ml
uv run uvicorn api.main:app --reload --port 8000

# Run frontend natively (in another terminal)
cd frontend && npm install
npm run dev
```

→ **Frontend:** http://localhost:3000
→ **Backend:** http://localhost:8000

## Project Structure

```
Forensic-Council/
├── backend/
│   ├── agents/          # Agent specialized logic and Arbiter synthesis
│   ├── api/             # FastAPI entrypoints, routers, and WebSocket managers
│   ├── core/            # ReAct Loop, Working Memory, Custody, and Calibration
│   ├── infra/           # Postgres, Redis, and Qdrant connector singletons
│   ├── orchestration/   # Evidence pipeline flow and multi-agent coordination
│   ├── tools/           # Custom analytical integrations for agents
│   └── scripts/         # Standalone ML subprocesses (out-of-loop execution)
├── frontend/            # Next.js web application
├── docs/                # Documentation, Docker configs, and operational guides
│   ├── docker/          # Docker Compose files (base, dev, prod, infra)
│   ├── test/            # Testing guides and checklists
│   └── status/          # Development status and error logs
└── manage.ps1           # PowerShell manager (.\manage.ps1 up / dev / down)
```

## API Summary

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/investigate` | Upload evidence and start investigation |
| `WS` | `/api/v1/sessions/{id}/live` | Live WebSocket cognitive updates |
| `POST` | `/api/v1/hitl/decision` | Submit Human-in-the-Loop decision |
| `GET` | `/api/v1/sessions/{id}/report` | Get cryptographically signed final report |

*Full endpoint reference with payloads → [`docs/API.md`](docs/API.md)*

## Development Status

Current development status, known limitations, and roadmap → [`docs/status/Development-Status.md`](docs/status/Development-Status.md)

## License

[MIT](LICENSE)
