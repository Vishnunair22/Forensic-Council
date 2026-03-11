# Forensic Council

Upload digital evidence. Five AI agents analyze it concurrently. Get a cryptographically signed forensic report in seconds.

[![Version](https://img.shields.io/badge/version-v1.0.0-blue.svg)](#) [![Status](https://img.shields.io/badge/status-stable-green.svg)](#) [![Postgres](https://img.shields.io/badge/postgres-17-blue.svg)](#) [![License](https://img.shields.io/badge/license-MIT-green.svg)](#)

*A Multi-Agent Forensic Evidence Analysis System*

## What it does

Forensic Council provides an automated, auditable pipeline for determining the authenticity of digital media. It solves the bottleneck of manual forensic review by orchestrating five specialized AI agents that independently analyze images, audio, video, objects, and metadata for signs of tampering or deepfakery. A Council Arbiter synthesizes their findings into a cohesive, cryptographically signed report, establishing a secure chain of custody from the moment of upload.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Frontend (Next.js 16)              │
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

### 1. Environment Setup
Copy the template and configure your keys (at minimum `LLM_API_KEY` or set `LLM_PROVIDER=none` in `.env`).
```powershell
Copy-Item .env.example .env
```

### 2. Choose Your Mode

| Mode | Command | Description |
|:---|:---|:---|
| **Development** | `.\manage.ps1 dev` | **Hot-Reload enabled.** Mounts source code volumes and enables Uvicorn/Next.js watch modes. |
| **Production** | `.\manage.ps1 prod` | Optimized build using multi-stage `runner` targets. No hot-reload. |
| **Infrastructure**| `.\manage.ps1 infra`| Starts only databases (Postgres, Redis, Qdrant). Use for native local dev. |

---

## 🏗️ Docker Caching Strategy

The system uses a three-tier caching system to ensure builds and startups are near-instant after the first run.

### 1. Docker Layer Cache (OS & Deps)
Layers are ordered so that code changes (most frequent) happen last.
- **Fast Path:** Changing a `.py` or `.tsx` file only rebuilds the final layer (~30s).
- **Dependency Path:** Adding a package triggers a `uv sync` or `npm ci` but reuses the global package cache.

### 2. BuildKit Cache Mounts (Deep Package Caching)
Specified in `Dockerfile` via `--mount=type=cache`. These persist even if you delete your images.
- **Backend:** `uv` HTTP cache at `/root/.cache/uv`.
- **Frontend:** `npm` cache at `/root/.npm` and Next.js compiler cache at `/app/.next/cache`.
- *To wipe:* `docker builder prune -f`

### 3. ML Model Volumes (The "Heavy" Cache)
ML models (PyTorch, Transformers, YOLO, etc.) are stored in **Named Volumes**. They are shared between `dev` and `prod` modes because both use the project name `forensic-council`.
- **Volumes:** `hf_cache`, `torch_cache`, `easyocr_cache`, `yolo_cache`, `deepface_cache`.
- **Persistence:** These are **NOT** deleted during `docker compose down` or image rebuilds.
- **Wipe:** `docker volume rm forensic-council_hf_cache` (force re-download).

---

## 🛠️ Troubleshooting & Maintenance

### Rebuilding with Model Cache
If you changed dependencies or code and want a clean refresh without losing models:
```bash
# Force rebuild without layer cache, but keeping ML models
docker compose -f docs/docker/docker-compose.yml build --no-cache
.\manage.ps1 up
```

### When Caching Fails (Stale Builds)
1. **Old Frontend UI:** `NEXT_PUBLIC_*` variables are baked at build time. If you changed them in `.env`, you **must** rebuild the frontend: `docker compose build frontend`.
2. **Corrupted Packages:** If `uv` or `npm` fails mysteriously, wipe the BuildKit cache: `docker builder prune --all -f`.
3. **Empty Models:** If analysis is slow, check `.\manage.ps1 logs`. On first run, it will say `⚠ EMPTY` and download ~10GB of models. This is normal.
4. **Nuclear Reset:** `.\manage.ps1 down-clean` (Deletes everything, including databases and models).

## 📂 Key Docker Files
- [docker-compose.yml](docs/docker/docker-compose.yml) — Base services & infra.
- [docker-compose.dev.yml](docs/docker/docker-compose.dev.yml) — Dev overrides (mounts, reload).
- [DOCKER_BUILD.md](docs/docker/DOCKER_BUILD.md) — The definitive deep-dive on caching logic.
- [manage.ps1](manage.ps1) — Unified entry point script.

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
