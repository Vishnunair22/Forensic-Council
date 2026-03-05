# Forensic Council

Upload digital evidence. Five AI agents analyze it concurrently. Get a cryptographically signed forensic report in seconds.

[![Status](https://img.shields.io/badge/status-beta-orange.svg)](#) [![Postgres](https://img.shields.io/badge/postgres-16-blue.svg)](#) [![License](https://img.shields.io/badge/license-MIT-green.svg)](#)

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
| Backend | Python 3.11+, FastAPI, LangGraph | High-performance async API with structured agentic graph orchestration. |
| Ledger | PostgreSQL 16 | ACID-compliant custody logging and final report storage. |
| Memory | Redis 7 | High-speed pub/sub for WebSocket event broadcasting and working memory. |
| Vector DB | Qdrant | Local-first dense vector similarity search; no managed cloud service required. |
| Signing | ECDSA (SHA-256) | Deterministic, auditable chain of custody without complex PKI infrastructure. |

## Quick Start

```bash
# Provide environment variables
cp .env.example .env
cp backend/.env.example backend/.env

# Start infrastructure (databases)
docker compose -f docker/docker-compose.infra.yml --env-file .env up -d

# Run backend natively (with hot reload)
cd backend && uv run uvicorn api.main:app --reload --port 8000

# Run frontend natively (in another terminal)
cd frontend && npm run dev
```
→ **Frontend (native dev):** http://localhost:3000
→ **Frontend (full Docker):** http://localhost:3000
→ **Backend:** http://localhost:8000

*For Docker-based development and production deployment, see [`STARTUP.md`](docs/STARTUP.md).*

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
└── docs/                # Comprehensive architectural, API, and process docs
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

Current development status, known limitations, and roadmap → [`docs/Development-Status.md`](docs/Development-Status.md)

## License

[MIT](LICENSE)
