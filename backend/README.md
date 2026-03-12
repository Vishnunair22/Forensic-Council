# Forensic Council — Backend

FastAPI backend for the Forensic Council multi-agent forensic evidence analysis system.

**Version:** v1.0.3 | **Python:** 3.12 | **Framework:** FastAPI + asyncpg

---

## Overview

The backend orchestrates five specialized AI agents that analyze digital media evidence, manages a cryptographic chain of custody, and exposes a REST + WebSocket API for the Next.js frontend.

---

## Architecture

```
api/main.py          ← FastAPI app, middleware, lifespan
api/routes/
  auth.py            ← JWT login/logout/refresh, bcrypt, RBAC
  investigation.py   ← Evidence upload, rate limiting, pipeline start
  sessions.py        ← Report retrieval, WebSocket live stream
  hitl.py            ← Human-in-the-loop decision endpoint
  metrics.py         ← Redis-backed operational counters

core/
  auth.py            ← JWT creation/validation, password hashing, UserRole
  config.py          ← Pydantic Settings, lru_cache singleton
  signing.py         ← ECDSA P-256 / SHA-256 report signing
  react_loop.py      ← ReAct reasoning loop engine
  working_memory.py  ← Per-session Redis scratchpad
  custody_logger.py  ← Immutable PostgreSQL audit trail
  calibration.py     ← Platt scaling confidence calibration
  migrations.py      ← Async DB schema migrations

agents/
  base_agent.py      ← Abstract agent with ReAct loop integration
  agent1_image.py    ← ELA, PRNU, splice detection
  agent2_audio.py    ← Wav2Vec2, speaker diarization, splice
  agent3_object.py   ← YOLOv8, CLIP, DeepFace
  agent4_video.py    ← Temporal analysis, face-swap detection
  agent5_metadata.py ← EXIF/XMP, GPS, timestamp validation
  arbiter.py         ← Cross-modal synthesis + HITL trigger

infra/
  redis_client.py    ← aioredis connection pool
  postgres_client.py ← asyncpg connection pool
  qdrant_client.py   ← Qdrant vector DB client
  evidence_store.py  ← Immutable SHA-256 file storage

orchestration/
  pipeline.py        ← Sequential 5-agent execution + WebSocket streaming
  session_manager.py ← Session lifecycle, Redis state management

scripts/
  ml_tools/          ← Heavy ML subprocesses (run out-of-process)
  docker_entrypoint.sh ← Cache check + server start
  model_cache_check.py ← Startup cache status reporter
```

---

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/auth/login` | — | Form-encoded credentials → JWT |
| `POST` | `/api/v1/auth/logout` | ✓ | Blacklist token in Redis |
| `GET` | `/api/v1/auth/me` | ✓ | Current user info |
| `POST` | `/api/v1/investigate` | ✓ | Upload evidence (multipart) + start pipeline |
| `WS` | `/api/v1/sessions/{id}/live` | ✓ | WebSocket cognitive trace stream |
| `GET` | `/api/v1/sessions/{id}/report` | ✓ | 202 while pending, 200 with signed report |
| `GET` | `/api/v1/sessions/{id}/checkpoints` | ✓ | HITL checkpoints awaiting decision |
| `GET` | `/api/v1/sessions/{id}/brief` | ✓ | Short status summary |
| `POST` | `/api/v1/hitl/decision` | ✓ | Submit APPROVE / REDIRECT / TERMINATE |
| `GET` | `/api/v1/metrics` | ✓ | Operational counters (Redis-backed) |
| `GET` | `/health` | — | Liveness + dependency health check |

---

## Environment Variables

All required variables are documented in `../.env.example`. Key ones:

| Variable | Default | Notes |
|----------|---------|-------|
| `APP_ENV` | `development` | `development` / `production` / `testing` |
| `SIGNING_KEY` | *(required)* | Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `POSTGRES_*` | see .env.example | Postgres connection params |
| `REDIS_PASSWORD` | *(required)* | Must match Redis service config |
| `LLM_PROVIDER` | `groq` | `groq` / `openai` / `anthropic` / `none` |
| `LLM_API_KEY` | *(required if not none)* | Provider API key |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Max 120 min recommended |
| `HF_TOKEN` | *(optional)* | Required for pyannote gated models (Agent 2) |

---

## Running Locally (without Docker)

```bash
cd backend

# Install uv (fast Python package manager)
pip install uv

# Install all dependencies including dev
uv sync

# Start infrastructure only
docker compose -f ../docs/docker/docker-compose.infra.yml --env-file ../.env up -d

# Run database migrations
python -c "import asyncio; from core.migrations import run_migrations; asyncio.run(run_migrations())"

# Start the API server (hot-reload)
uvicorn api.main:app --reload --port 8000
```

---

## Running Tests

```bash
# From project root
pytest tests/backend/ -v

# Specific categories
pytest tests/backend/unit/     -v  # JWT, config, signing, schemas
pytest tests/backend/integration/ -v  # All HTTP routes (mocked infra)
pytest tests/backend/security/    -v  # Auth bypass, injection, CORS

# With coverage
pytest tests/backend/ --cov=backend --cov-report=html
```

---

## Security Model

- **Authentication:** bcrypt password hashing (bcrypt work factor 12+), JWT HS256 with 60-min expiry
- **Authorization:** Role-based (admin / investigator) enforced per route
- **Token blacklisting:** Logout invalidates tokens via Redis TTL
- **Rate limiting:** Per-user Redis counter (5 investigations / 5-min window)
- **Evidence integrity:** SHA-256 hash locked at upload; re-verified before analysis
- **Report signing:** ECDSA P-256 + SHA-256 over the complete report payload
- **Container security:** `read_only: true` filesystem; writable paths via tmpfs

---

## ML Subprocesses

Heavy ML inference runs in separate processes (`scripts/ml_tools/`) to avoid blocking the async event loop:

| Script | Tool | Used By |
|--------|------|---------|
| `ela_anomaly_classifier.py` | Error Level Analysis | Agent 1 |
| `noise_fingerprint.py` | PRNU noise analysis | Agent 1 |
| `copy_move_detector.py` | Copy-move forgery | Agent 1 |
| `audio_splice_detector.py` | Audio splice detection | Agent 2 |
| `deepfake_frequency.py` | Frequency-domain deepfake | Agent 2 |
| `anomaly_classifier.py` | Isolation Forest | Agent 3 |
| `lighting_analyzer.py` | Lighting consistency | Agent 3 |
| `rolling_shutter_validator.py` | Temporal consistency | Agent 4 |
| `metadata_anomaly_scorer.py` | EXIF anomaly scoring | Agent 5 |
