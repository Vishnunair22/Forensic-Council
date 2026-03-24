# Forensic Council

Upload digital evidence. Five specialized AI agents analyze it. Get a cryptographically signed forensic report.

[![Version](https://img.shields.io/badge/version-v1.0.4-blue.svg)](#) [![Status](https://img.shields.io/badge/status-stable-green.svg)](#) [![License](https://img.shields.io/badge/license-MIT-green.svg)](#) [![Python](https://img.shields.io/badge/python-3.12-blue.svg)](#) [![Next.js](https://img.shields.io/badge/next.js-15-black.svg)](#) [![Postgres](https://img.shields.io/badge/postgres-17-blue.svg)](#)

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

# 2. Start (Development)
docker compose -f docs/docker/docker-compose.yml -f docs/docker/docker-compose.dev.yml --env-file .env up --build

# 2. Start (Production)
docker compose -f docs/docker/docker-compose.yml -f docs/docker/docker-compose.prod.yml --env-file .env up -d --build
```

**Access:**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs (dev): http://localhost:8000/docs

Login: username `investigator`, password = `NEXT_PUBLIC_DEMO_PASSWORD` from `.env` (default: `inv123!`)

> **First run:** ML models download automatically (15–60 min). Subsequent starts are instant.

---

## Management

| Command | Action |
|---------|--------|
| `docker compose ... up` | Standard start |
| `docker compose -f ... -f ...dev.yml ... up` | Development start (hot-reload) |
| `docker compose -f ... -f ...prod.yml ... up` | Production build |
| `docker compose -f ... -f ...infra.yml ... up` | Postgres + Redis + Qdrant only |
| `docker compose ... logs -f` | Tail all logs |
| `docker compose ... down` | Stop (keep volumes) |
| `docker compose ... down -v` | Stop + delete all volumes |
| `docker system df -v` | Check ML cache volumes |

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

> ⚠️ `docker compose down -v` deletes all ML models. Avoid unless intentional.

Full caching guide → [`docs/docker/README.md`](docs/docker/README.md)

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| CORS errors | Check `NEXT_PUBLIC_API_URL` in `.env` matches browser-reachable URL |
| ML models re-downloading | `down -v` was run; models will re-cache automatically |
| `SIGNING_KEY` error | `python -c "import secrets; print(secrets.token_hex(32))"` |
| Old UI after `.env` change | `NEXT_PUBLIC_*` bakes at build time: `docker compose build frontend` |
| Audio agent failures | Set `HF_TOKEN` for pyannote gated models (free at hf.co/settings/tokens) |

---

## Changelog

**v1.0.4 (2026-03-16)** — Full production hardening across all layers:
- **Session 5 runtime audit**: Report race-window fix (report cached before pipeline eviction) · `AttributeError: _custody_logger` in Agents 2/3/4 inter-agent calls · Pipeline `_final_report`/`_error` now initialized on `__init__` · WorkingMemory in-memory fallback survives Redis outages · CustodyLogger DB write wrapped in try/except (never crashes pipeline) · Frontend unsupported-agent detection matches backend `"Not applicable"` strings · Docker-compose `LLM_MODEL` default corrected to `llama-3.3-70b-versatile` · `.env.example` `GEMINI_TIMEOUT` corrected to `55.0`
- **Session 4 backend audit**: Resume endpoint URL mismatch fixed (was 404 on every Accept/Deep click) · DB report rebuild missing 5 fields · `update_session_status` NOT NULL violation · Qdrant singleton race condition · HTML injection in report renderer · `TransactionContext.fetch` dict args · pytest path and `backend/__init__.py` · CI test job fixed
- **Session 3 connectivity**: All frontend↔backend URL mappings verified · Docker CORS origins confirmed · WebSocket subprotocol match · MIME type allowlists identical
- **Critical bug fixes**: `useRef` lazy-init fixed (was breaking every POST), `react_loop` `update_state` missing `agent_id`, deep pass returning combined findings (duplication), stale `agentUpdates` on deep phase start
- **Deep analysis**: Agent1 Gemini runs first → context injected into Agents 3 & 5 · Phase-aware Groq synthesis (deep pass compares vs initial) · Active-agent-only deep queue
- **Arbiter**: 5-tier verdict (CERTAIN/LIKELY/UNCERTAIN/INCONCLUSIVE/MANIPULATION DETECTED) · Per-agent Groq narrative · `AgentMetrics` with confidence + error rate · Finding deduplication
- **UI**: Syne + JetBrains Mono fonts · `MicroscopeScanner` + `EnvelopeCTA` + `GlassCard` · Glass agent cards with skeleton loading · `GlobalFooter` on all pages · `PageTransition` · `cursor: pointer` globally
- **Audit fixes (v1.0.2–v1.0.4)**: JWT 60-min expiry · Rate limiting · Bootstrap credentials from env vars · Redis/PostgreSQL production hardening · ECDSA signing · numpy<2.0 bound · Test file correct imports

Full changelog → [`docs/status/Development-Status.md`](docs/status/Development-Status.md)

---

[MIT License](LICENSE)
