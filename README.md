# Forensic Council

Upload digital evidence. Five specialized AI agents analyze it. Get a cryptographically signed forensic report.

[![Version](https://img.shields.io/badge/version-v1.2.0-blue.svg)](#) [![Status](https://img.shields.io/badge/status-stable-green.svg)](#) [![License](https://img.shields.io/badge/license-MIT-green.svg)](#) [![Python](https://img.shields.io/badge/python-3.12-blue.svg)](#) [![Next.js](https://img.shields.io/badge/next.js-15-black.svg)](#) [![Postgres](https://img.shields.io/badge/postgres-17-blue.svg)](#)

*A Multi-Agent Forensic Evidence Analysis System with cryptographic chain of custody*

---

## What it does

Forensic Council automates the analysis of digital media evidence. Five independent AI agents examine an uploaded file for signs of manipulation, deepfakery, metadata inconsistencies, and compositing artifacts. A Council Arbiter cross-references their findings, flags conflicts for human review (HITL), and produces a tamper-evident report signed with ECDSA P-256.

Every step from upload to final verdict is logged in PostgreSQL and independently verifiable.

---

## Architecture

```
Frontend (Next.js 15) → FastAPI Backend → 5 AI Agents → Arbiter → Signed Report
                                        ↕         ↕          ↕
                                     Redis    Postgres    Qdrant
```

**Infrastructure:**
- **Redis** — working memory, WebSocket pub/sub, rate limiting, token blacklisting
- **PostgreSQL 17** — ACID custody ledger for immutable investigation records
- **Qdrant** — vector similarity for historical finding correlation
- **Caddy 2** — automatic TLS via Let's Encrypt

---

## The Agents

| Agent | Focus | Key ML Tools |
|-------|-------|-------------|
| Image Forensics | ELA, splice, PRNU, EXIF | EasyOCR, PIL, ELA classifier |
| Audio Forensics | Deepfake voice, splice, A/V sync | Wav2Vec2, pyannote.audio |
| Object Detection | Scene context, lighting, compositing | YOLOv8, CLIP, DeepFace |
| Video Forensics | Temporal consistency, face-swap | Optical flow, rolling shutter |
| Metadata Forensics | EXIF/XMP, GPS/timestamp | ExifTool, solar positioning |
| Council Arbiter | Cross-modal synthesis, signing | ECDSA P-256, Platt scaling |

---

## Prerequisites

- Docker Desktop 23+ (or Docker Engine + Compose v2 with BuildKit)
- **Groq API key** (required) — drives ReAct reasoning loops and Arbiter synthesis. Free at [console.groq.com/keys](https://console.groq.com/keys)
- **Google Gemini API key** (recommended) — enables vision deep analysis for Agents 1, 3, and 5. Free at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
- 10–15 GB disk for ML model caches (downloaded once, cached permanently)

---

## Quick Start

```bash
# 1. Configure
cp .env.example .env
# Edit .env: set LLM_API_KEY (Groq, required) and GEMINI_API_KEY (recommended)

# 2. Start
docker compose -f infra/docker-compose.yml --env-file .env up --build
```

**Access:**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs (dev): http://localhost:8000/docs

Login: username `investigator`, password = `DEMO_PASSWORD` from `.env` (default: `CHANGE_ME_dev_only_password`)

> **First run:** ML models download automatically in the background (15–60 min). The API starts immediately and serves requests while models cache. Subsequent starts are instant.

---

## Management

| Command | Action |
|---------|--------|
| `docker compose up` | Standard start |
| `docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up` | Development start (hot-reload) |
| `docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml up` | Production build |
| `docker compose -f infra/docker-compose.yml -f infra/docker-compose.infra.yml up` | Postgres + Redis + Qdrant only |
| `docker compose logs -f` | Tail all logs |
| `docker compose logs -f backend worker` | Tail backend + worker logs |
| `docker compose down` | Stop (keep volumes) |
| `docker compose down -v` | Stop + delete all volumes (**deletes ML models**) |
| `docker system df -v` | Check ML cache volumes |
| `python backend/scripts/init_db.py` | Re-run database migrations |
| `python backend/scripts/cleanup_storage.py` | Purge expired evidence |

---

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/auth/login` | Get JWT |
| `GET`  | `/api/v1/auth/me` | Current user info |
| `POST` | `/api/v1/auth/refresh` | Refresh access token |
| `POST` | `/api/v1/auth/logout` | Invalidate JWT (blacklisted in Redis) |
| `POST` | `/api/v1/investigate` | Upload evidence + start investigation |
| `WS`   | `/api/v1/sessions/{id}/live` | Live WebSocket cognitive stream |
| `POST` | `/api/v1/sessions/{id}/resume` | Resume after initial analysis (Accept/Deep) |
| `GET`  | `/api/v1/sessions/{id}/report` | Signed final report (202 while pending) |
| `GET`  | `/api/v1/sessions/{id}/arbiter-status` | Lightweight arbiter poll |
| `GET`  | `/api/v1/sessions/{id}/checkpoints` | HITL checkpoints |
| `GET`  | `/api/v1/sessions/{id}/brief/{agent_id}` | Agent thinking text |
| `GET`  | `/api/v1/sessions` | List all sessions for current user |
| `DELETE` | `/api/v1/sessions/{id}` | Delete a session and its report |
| `POST` | `/api/v1/hitl/decision` | Submit HITL decision |
| `GET`  | `/health` | Deep health check (Postgres + Redis + Qdrant) |
| `GET`  | `/api/v1/metrics` | Prometheus-format backend metrics |

Full reference → [`docs/API.md`](docs/API.md)

---

## Tests

```bash
# Frontend (from frontend/)
npm test -- --watchAll=false

# Backend + infrastructure (from project root)
pytest tests/ --ignore=tests/connectivity -v

# Live connectivity tests (requires running stack)
pytest tests/connectivity/ -v
```

See [`tests/README.md`](tests/README.md) for complete documentation.

---

## Docker & Caching

Three-tier cache keeps rebuilds fast:
1. **Docker layer cache** — OS + deps layers; reused unless dependencies change
2. **BuildKit cache mounts** — `uv`/`npm`/Next.js compiler; persists across rebuilds
3. **Named ML volumes** — Model weights; never deleted by `--no-cache`

> `docker compose down -v` deletes all ML models. Avoid unless intentional.

Full caching guide → [`infra/README.md`](infra/README.md)

---

## Project Structure

```
Forensic Council/
├── .github/workflows/   # CI pipeline
├── backend/
│   ├── agents/          # 5 specialist agents + Council Arbiter
│   ├── api/             # FastAPI routes, schemas, middleware
│   ├── config/          # Settings, constants
│   ├── core/            # Auth, signing, calibration, memory, ReAct loop
│   ├── infra/           # PostgreSQL, Redis, Qdrant clients
│   ├── orchestration/   # Pipeline, session manager, investigation queue
│   ├── tools/           # Forensic analysis tools (ELA, OCR, YOLO, etc.)
│   ├── reports/         # Report template generation
│   ├── scripts/         # Utility scripts
│   ├── storage/         # Evidence store, key management
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── app/         # Next.js pages (landing, investigate, result)
│   │   ├── components/  # UI components (evidence, result, lightswind)
│   │   ├── hooks/       # React hooks (WebSocket, sound, forensic data)
│   │   ├── lib/         # API client, constants, utilities
│   │   └── types/       # TypeScript definitions
│   └── package.json
├── infra/
│   ├── docker-compose*.yml
│   └── Caddyfile
├── docs/
│   ├── agent-context/   # Agent memory, rules, project context
│   └── *.md             # Architecture, API, security, testing, runbooks
├── tests/
│   ├── backend/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── security/
│   ├── frontend/
│   │   ├── unit/
│   │   ├── integration/
│   │   ├── e2e/
│   │   └── accessibility/
│   ├── connectivity/    # Live stack tests
│   ├── fixtures/        # Test data
│   └── infra/           # Infrastructure tests
├── storage/
│   └── calibration_models/  # Platt scaling calibration data (gitignored)
├── .env
├── .env.example
├── .gitignore
├── .dockerignore
├── setup.cfg
├── LICENSE
└── README.md
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| CORS errors | Check `NEXT_PUBLIC_API_URL` in `.env` matches browser-reachable URL |
| ML models re-downloading | `down -v` was run; models will re-cache automatically (check `/tmp/model_download.log`) |
| `SIGNING_KEY` error | `python -c "import secrets; print(secrets.token_hex(32))"` — set in `.env` |
| `JWT_SECRET_KEY` error | `python -c "import secrets; print(secrets.token_hex(32))"` — must be 32+ chars with mixed case |
| Old UI after `.env` change | `NEXT_PUBLIC_*` bakes at build time: `docker compose build frontend` |
| Audio agent failures | Set `HF_TOKEN` for pyannote gated models (free at hf.co/settings/tokens) |
| WebSocket disconnects | Check Caddy `flush_interval -1` in Caddyfile; verify network segmentation |
| Database migration failures | Check `docker compose logs migration`; verify `POSTGRES_PASSWORD` matches |

---

## Changelog

**v1.2.1 (2026-04-06)** — Full repository structure cleanup and backend/frontend optimizations:
- **Audit**: Comprehensive automated auditing of frontend ESLint and backend Python styles using Ruff.
- **Backend Clean**: Resolved 422 linting warnings (mostly empty/unused imports and spacing) optimizing backend flow.
- **Frontend Clean**: Addressed unused arguments, purged orphaned variables, and removed invalid duplicated code blocks in the App Router UI layout rendering.
- **Docs**: Removed duplicated table entries and synced architectural changes.

**v1.2.0 (2026-04-02)** — Full codebase audit, deep analysis UI, production hardening:
- **Audit**: Aligned all version strings to 1.2.0 across `pyproject.toml`, `package.json`, `api/main.py`.
- **Audit**: Added missing `import asyncio` in `api/main.py` (would crash ML warmup in production).
- **Audit**: Added `"use client"` directive to `not-found.tsx` (framer-motion SSR crash fix).
- **Audit**: Cleaned 86 stale `.pyc` files and `__pycache__` directories from tracked paths.
- **UI**: Deep Analysis result page — 3 new specialized components: Deep Model Telemetry, Tribunal Consensus Matrix, Cross-Modal Evidence Graph.
- **UI**: History panel — file preview thumbnails, dismiss button, clear all, improved layout.
- **UI**: Result page — section reordering (Agent Analysis before Timeline), Verdict banner, tab graphics.

**v1.1.2 (2026-04-02)** — Project cleanup, bug fixes, result page redesign:
- **Cleanup**: Removed `nul` file, `__pycache__` directories, `.pytest_cache` from root. Consolidated `claude/` into `docs/agent-context/`. Updated `.gitignore`.
- **Bug fix**: `metadata_tools.py` — `file_created` now uses `st_birthtime` (cross-platform creation time) instead of `st_ctime` (which is metadata-change-time on Unix).
- **Bug fix**: Chain-of-custody — JSON double-encoding in `PostgresClient._process_args` removed. The JSONB codec now handles serialization without pre-stringification, fixing signature verification failures.
- **Bug fix**: Gemini vision findings — `analysis_source` flattened to top-level in agent handler return dicts so the arbiter can correctly detect Gemini findings.
- **Observability**: Added `get_custody_metrics()` to `CustodyLogger` for monitoring write-failure and retry-queue-size counters.
- **UI**: Result page redesigned with tab structure (Current Analysis / History), analysis timeline waterfall, metrics grid, and pill-shaped navigation.
- **UI**: Agent progress display redesigned with per-tool cards showing elapsed time, findings with expand, and metrics grid.

**v1.1.1 (2026-03-29)** — UI Refinements, Bug Fixes & Project Cleanup:
- **UI**: Agent card grid changed to 3×2 layout on large screens.
- **UI**: Status badges use transparent/opaque backgrounds.
- **File preview fix**: Upload success modal renders image previews correctly.
- **Auth delay fix**: Evidence page no longer fires redundant `autoLoginAsInvestigator()`.
- **Progress text fix**: Backend thinking text no longer resets on empty string.
- **Security**: Removed exposed API keys file.

**v1.1.0 (2026-03-24)** — Comprehensive Minimalist Redesign & Robustness Audit.

**v1.0.4 (2026-03-16)** — Full production hardening across all layers.

Full changelog → [`docs/Development-Status.md`](docs/Development-Status.md)

---

[MIT License](LICENSE)
