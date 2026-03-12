# Forensic Council

Upload digital evidence. Five specialized AI agents analyze it. Get a cryptographically signed forensic report.

[![Version](https://img.shields.io/badge/version-v1.0.3-blue.svg)](#) [![Status](https://img.shields.io/badge/status-stable-green.svg)](#) [![License](https://img.shields.io/badge/license-MIT-green.svg)](#) [![Python](https://img.shields.io/badge/python-3.12-blue.svg)](#) [![Next.js](https://img.shields.io/badge/next.js-16-black.svg)](#) [![Postgres](https://img.shields.io/badge/postgres-17-blue.svg)](#)

*A Multi-Agent Forensic Evidence Analysis System with cryptographic chain of custody*

---

## What it does

Forensic Council automates the analysis of digital media evidence. Five independent AI agents examine an uploaded file for signs of manipulation, deepfakery, metadata inconsistencies, and compositing artifacts. A Council Arbiter cross-references their findings, flags conflicts for human review (HITL), and produces a tamper-evident report signed with ECDSA P-256.

Every step from upload to final verdict is logged in PostgreSQL and independently verifiable.

---

## Architecture

```
Frontend (Next.js 16) → FastAPI Backend → 5 AI Agents → Arbiter → Signed Report
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

# 2. Start (Windows PowerShell)
.\manage.ps1 dev       # development with hot-reload
.\manage.ps1 prod      # production optimised build

# 2. Start (Linux / macOS)
docker compose -f docs/docker/docker-compose.yml \
               -f docs/docker/docker-compose.dev.yml \
               --env-file .env up --build
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
| `.\manage.ps1 up` | Production start |
| `.\manage.ps1 dev` | Development start (hot-reload) |
| `.\manage.ps1 prod` | Production-optimised build |
| `.\manage.ps1 infra` | Postgres + Redis + Qdrant only |
| `.\manage.ps1 logs` | Tail all logs |
| `.\manage.ps1 down` | Stop (keep volumes) |
| `.\manage.ps1 down-clean` | Stop + delete all volumes |
| `.\manage.ps1 cache-status` | Show ML volume sizes |

---

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/auth/login` | Get JWT |
| `POST` | `/api/v1/auth/logout` | Invalidate JWT |
| `POST` | `/api/v1/investigate` | Upload evidence + start investigation |
| `WS` | `/api/v1/sessions/{id}/live` | Live WebSocket cognitive stream |
| `GET` | `/api/v1/sessions/{id}/report` | Signed final report |
| `POST` | `/api/v1/hitl/decision` | Submit HITL decision |
| `GET` | `/health` | Health check |

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

**v1.0.3** — Arbiter navigation race condition fixed · isNavigating double-click guard · JWT 60-min expiry (was 7 days) · Rate limiting · Bootstrap credentials from env vars · Docker binding fixes

Full changelog → [`docs/status/Development-Status.md`](docs/status/Development-Status.md)

---

[MIT License](LICENSE)
