# Forensic Council — Backend

FastAPI backend for the Forensic Council multi-agent forensic evidence analysis system.

**Version:** v1.0.4 | **Python:** 3.12 | **Framework:** FastAPI + asyncpg

---

## Architecture

```
api/main.py              ← FastAPI app, middleware stack, lifespan hooks
api/routes/
  auth.py                ← JWT login/logout/refresh, bcrypt, RBAC, brute-force guard
  investigation.py       ← Evidence upload, rate limiting, pipeline start, deep analysis
  sessions.py            ← Report retrieval, WebSocket stream, resume endpoint, HITL queries
  hitl.py                ← Human-in-the-loop decision endpoint
  metrics.py             ← Redis-backed operational counters

core/
  auth.py                ← JWT creation/validation, password hashing, UserRole, blacklisting
  config.py              ← Pydantic Settings, lru_cache singleton, production validators
  signing.py             ← ECDSA P-256 / SHA-256 report signing, deterministic key derivation
  react_loop.py          ← ReAct reasoning loop engine, task-decomposition driver
  working_memory.py      ← Per-session Redis scratchpad, task queue, 200ms heartbeat
  episodic_memory.py     ← Qdrant vector memory for historical finding correlation
  custody_logger.py      ← Immutable PostgreSQL audit trail, chain-of-custody signing
  calibration.py         ← Platt scaling confidence calibration per agent
  migrations.py          ← Async DB schema migrations (5 idempotent migrations)
  session_persistence.py ← PostgreSQL session/report persistence for restart resilience
  inter_agent_bus.py     ← Type-safe inter-agent communication (Agents 2/3/4 corroboration)
  adversarial.py         ← Adversarial robustness testing framework
  gemini_client.py       ← Google Gemini vision API client (httpx-direct, no SDK)
  llm_client.py          ← Groq / OpenAI / Anthropic LLM client (httpx-direct, no SDK)

agents/
  base_agent.py          ← Abstract agent with ReAct loop, self-reflection, episodic memory
  agent1_image.py        ← ELA, PRNU noise, copy-move, JPEG ghost, OCR, frequency domain
  agent2_audio.py        ← Wav2Vec2, speaker diarization, audio splice, codec fingerprint
  agent3_object.py       ← YOLOv8, CLIP, DeepFace, lighting consistency, contraband check
  agent4_video.py        ← Optical flow, face-swap, rolling shutter, deepfake frequency
  agent5_metadata.py     ← EXIF/XMP, GPS/timestamp, steganography, hex signature scan
  arbiter.py             ← Cross-modal synthesis, 5-tier verdict, Groq narrative, ECDSA sign

infra/
  redis_client.py        ← aioredis connection pool with asyncio.Lock singleton
  postgres_client.py     ← asyncpg connection pool with JSONB codec
  qdrant_client.py       ← Qdrant vector DB client with asyncio.Lock singleton
  evidence_store.py      ← Immutable SHA-256 file storage with custody logging
  storage.py             ← Local filesystem storage backend

orchestration/
  pipeline.py            ← Sequential 5-agent execution + WebSocket streaming, deep pass
  session_manager.py     ← Session lifecycle, HITL checkpoint state management

scripts/
  ml_tools/              ← Heavy ML subprocesses (run out-of-process via asyncio.create_subprocess_exec)
  docker_entrypoint.sh   ← Cache status check + server start
  model_cache_check.py   ← Startup ML volume status reporter
  init_db.py             ← Bootstrap admin/investigator users from env vars
```

---

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/auth/login` | — | Form credentials → JWT |
| `GET` | `/api/v1/auth/me` | ✓ | Current user info |
| `POST` | `/api/v1/auth/refresh` | ✓ | Refresh access token |
| `POST` | `/api/v1/auth/logout` | ✓ | Blacklist token in Redis |
| `POST` | `/api/v1/investigate` | ✓ | Upload evidence (multipart) + start pipeline |
| `WS` | `/api/v1/sessions/{id}/live` | JWT-on-connect | WebSocket cognitive trace stream |
| `POST` | `/api/v1/sessions/{id}/resume` | ✓ | Resume after initial analysis (Accept/Deep) |
| `GET` | `/api/v1/sessions/{id}/report` | ✓ | 202 while pending; 200 with signed ReportDTO |
| `GET` | `/api/v1/sessions/{id}/arbiter-status` | ✓ | Lightweight poll: running/complete/error |
| `GET` | `/api/v1/sessions/{id}/checkpoints` | ✓ | HITL checkpoints awaiting decision |
| `GET` | `/api/v1/sessions/{id}/brief/{agent_id}` | ✓ | Current agent thinking text |
| `GET` | `/api/v1/sessions` | ✓ | List active in-memory sessions |
| `DELETE` | `/api/v1/sessions/{id}` | ✓ | Terminate session + cancel task |
| `POST` | `/api/v1/hitl/decision` | ✓ | Submit APPROVE / REDIRECT / OVERRIDE / TERMINATE / ESCALATE |
| `GET` | `/api/v1/metrics` | ✓ admin | Operational counters (Redis-backed) |
| `GET` | `/health` | — | Deep health check (Postgres + Redis + Qdrant) |
| `GET` | `/` | — | Root: version + status |

Full reference → [`../docs/API.md`](../docs/API.md)

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
| `GEMINI_API_KEY` | *(optional)* | Enables Gemini vision for Agents 1, 3, 5 deep pass |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Max 120 min recommended |
| `HF_TOKEN` | *(optional)* | Required for pyannote gated models (Agent 2 diarization) |

---

## Running Locally (without Docker)

```bash
cd backend

# Install uv (fast Python package manager)
pip install uv

# Install all dependencies including dev
uv sync --all-extras

# Start infrastructure only (Postgres, Redis, Qdrant)
docker compose -f ../docs/docker/docker-compose.yml \
               -f ../docs/docker/docker-compose.infra.yml \
               --env-file ../.env up -d

# Run database migrations
python -c "import asyncio; from core.migrations import run_migrations; asyncio.run(run_migrations())"

# Start the API server (hot-reload)
uvicorn api.main:app --reload --port 8000
```

---

## Running Tests

```bash
# From project root (correct working directory for import resolution)
pytest tests/backend/ -v

# Specific categories
pytest tests/backend/unit/      -v   # JWT, config, signing, schemas
pytest tests/backend/integration/ -v # All HTTP routes (mocked infra)
pytest tests/backend/security/   -v  # Auth bypass, injection, CORS

# With coverage
pytest tests/backend/ --cov=backend --cov-report=html
```

> **Note:** Tests must be run from the **project root** (not from `backend/`). The root `pytest.ini` sets `pythonpath = . backend` so both `from core.auth` and `from backend.core.config` import styles work correctly.

---

## Security Model

| Layer | Mechanism |
|-------|-----------|
| Passwords | bcrypt (work factor ≥ 12), truncated to 72 bytes |
| JWTs | HS256, 60-min expiry, Redis blacklist on logout |
| Brute-force | Per-IP Redis counter: 5 failures → 15-min lockout |
| Rate limiting | Per-user investigation counter: 10 / 5-min window |
| File safety | MIME + extension allowlist, 50 MB limit, SHA-256 integrity lock |
| Report signing | ECDSA P-256 + SHA-256, key derived deterministically from SIGNING_KEY |
| Container | `read_only: true` filesystem; writable paths via named volumes only |

---

## ML Subprocesses

Heavy ML inference runs out-of-process via `asyncio.create_subprocess_exec` to prevent blocking the event loop and dropping WebSocket connections.

| Script | Tool | Agent |
|--------|------|-------|
| `ela_anomaly_classifier.py` | IsolationForest ELA blocks | Agent 1 |
| `noise_fingerprint.py` | PRNU camera noise fingerprint | Agent 1 |
| `copy_move_detector.py` | SIFT copy-move forgery | Agent 1 |
| `splicing_detector.py` | SRM noise residual splicing | Agent 1, 3 |
| `audio_splice_detector.py` | Spectral splice detection | Agent 2 |
| `deepfake_frequency.py` | DCT frequency deepfake | Agent 2, 4 |
| `anomaly_classifier.py` | IsolationForest scene anomaly | Agent 3 |
| `lighting_analyzer.py` | Shadow/highlight consistency | Agent 3 |
| `rolling_shutter_validator.py` | Temporal rolling shutter | Agent 4 |
| `metadata_anomaly_scorer.py` | EXIF entropy scoring | Agent 5 |
