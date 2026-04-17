# Forensic Council â€” Backend

FastAPI backend for the Forensic Council multi-agent forensic evidence analysis system.

**Version:** v1.4.0 | **Python:** 3.12 | **Framework:** FastAPI + asyncpg

---

## Architecture

```
api/main.py              â† FastAPI app, middleware stack, lifespan hooks
api/routes/
  auth.py                â† JWT login/logout/refresh, bcrypt, RBAC, brute-force guard
  investigation.py       â† Evidence upload, rate limiting, pipeline start, deep analysis
  sessions.py            â† Report retrieval, WebSocket stream, resume endpoint, HITL queries
  hitl.py                â† Human-in-the-loop decision endpoint
  metrics.py             â† Redis-backed operational counters

core/
  auth.py                â† JWT creation/validation, password hashing, UserRole, blacklisting
  config.py              â† Pydantic Settings, lru_cache singleton, production validators
  signing.py             â† ECDSA P-256 / SHA-256 report signing, deterministic key derivation
  react_loop.py          â† ReAct reasoning loop engine, task-decomposition driver
  working_memory.py      â† Per-session Redis scratchpad, task queue, 200ms heartbeat
  episodic_memory.py     â† Qdrant vector memory for historical finding correlation
  custody_logger.py      â† Immutable PostgreSQL audit trail, chain-of-custody signing
  calibration.py         â† Platt scaling confidence calibration per agent
  migrations.py          â† Async DB schema migrations (5 idempotent migrations)
  session_persistence.py â† PostgreSQL session/report persistence for restart resilience
  inter_agent_bus.py     â† Type-safe inter-agent communication (Agents 2/3/4 corroboration)
  adversarial.py         â† Adversarial robustness testing framework
  gemini_client.py       â† Google Gemini vision API client (httpx-direct, no SDK)
  llm_client.py          â† Groq / OpenAI / Anthropic LLM client (httpx-direct, no SDK)

agents/
  base_agent.py          â† Abstract agent with ReAct loop, self-reflection, episodic memory
  agent1_image.py        â† ELA, PRNU noise, copy-move, JPEG ghost, OCR, frequency domain
  agent2_audio.py        â† Wav2Vec2, speaker diarization, audio splice, codec fingerprint
  agent3_object.py       â† YOLOv8, CLIP, DeepFace, lighting consistency, contraband check
  agent4_video.py        â† Optical flow, face-swap, rolling shutter, deepfake frequency
  agent5_metadata.py     â† EXIF/XMP, GPS/timestamp, steganography, hex signature scan
  arbiter.py             â† Cross-modal synthesis, 5-tier verdict, Groq narrative, ECDSA sign

infra/
  redis_client.py        â† aioredis connection pool with asyncio.Lock singleton
  postgres_client.py     â† asyncpg connection pool with JSONB codec
  qdrant_client.py       â† Qdrant vector DB client with asyncio.Lock singleton
  evidence_store.py      â† Immutable SHA-256 file storage with custody logging
  storage.py             â† Local filesystem storage backend

orchestration/
  pipeline.py            â† Sequential 5-agent execution + WebSocket streaming, deep pass
  session_manager.py     â† Session lifecycle, HITL checkpoint state management

scripts/
  docker_entrypoint.sh   â† Cache status check + server start
  model_cache_check.py   â† Startup ML volume status reporter
  model_pre_download.py  â† First-run ML model pre-download
  init_db.py             â† Bootstrap admin/investigator users from env vars
  run_api.py             â† Uvicorn API server runner
  run_stress_test.py     â† Load testing script
  smoke_test.sh          â† End-to-end smoke test

tools/
  ml_tools/              â† Heavy ML subprocesses (run out-of-process via asyncio.create_subprocess_exec)
  image_tools.py         â† Image analysis tool implementations
  audio_tools.py         â† Audio analysis tool implementations
  video_tools.py         â† Video analysis tool implementations
  metadata_tools.py      â† Metadata extraction tool implementations
  ocr_tools.py           â† OCR tool implementations
  clip_utils.py          â† CLIP model utilities
  mediainfo_tools.py     â† Media container analysis
```

---

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/auth/login` | â€” | Form credentials â†’ JWT |
| `GET` | `/api/v1/auth/me` | âœ“ | Current user info |
| `POST` | `/api/v1/auth/refresh` | âœ“ | Refresh access token |
| `POST` | `/api/v1/auth/logout` | âœ“ | Blacklist token in Redis |
| `POST` | `/api/v1/investigate` | âœ“ | Upload evidence (multipart) + start pipeline |
| `WS` | `/api/v1/sessions/{id}/live` | JWT-on-connect | WebSocket cognitive trace stream |
| `POST` | `/api/v1/sessions/{id}/resume` | âœ“ | Resume after initial analysis (Accept/Deep) |
| `GET` | `/api/v1/sessions/{id}/report` | âœ“ | 202 while pending; 200 with signed ReportDTO |
| `GET` | `/api/v1/sessions/{id}/arbiter-status` | âœ“ | Lightweight poll: running/complete/error |
| `GET` | `/api/v1/sessions/{id}/checkpoints` | âœ“ | HITL checkpoints awaiting decision |
| `GET` | `/api/v1/sessions/{id}/brief/{agent_id}` | âœ“ | Current agent thinking text |
| `GET` | `/api/v1/sessions` | âœ“ | List active in-memory sessions |
| `DELETE` | `/api/v1/sessions/{id}` | âœ“ | Terminate session + cancel task |
| `POST` | `/api/v1/hitl/decision` | âœ“ | Submit APPROVE / REDIRECT / OVERRIDE / TERMINATE / ESCALATE |
| `GET` | `/api/v1/metrics` | âœ“ admin | Operational counters (Redis-backed) |
| `GET` | `/health` | â€” | Deep health check (Postgres + Redis + Qdrant) |
| `GET` | `/` | â€” | Root: version + status |

Full reference â†’ [`../docs/API.md`](../docs/API.md)

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

---

## Running Locally (without Docker)

```bash
cd apps/api

# Install uv (fast Python package manager)
pip install uv

# Install all dependencies including dev
uv sync --all-extras

# Start infrastructure only (Postgres, Redis, Qdrant)
docker compose -f ../infra/docker-compose.yml \
               -f ../infra/docker-compose.infra.yml \
               --env-file ../.env up -d

# Run database migrations
python -c "import asyncio; from core.migrations import run_migrations; asyncio.run(run_migrations())"

# Start the API server (hot-reload)
uvicorn api.main:app --reload --port 8000
```

---

## Running Tests

```bash
# From apps/api
uv run pytest tests -v

# Specific categories
uv run pytest tests/unit -v        # JWT, config, signing, schemas
uv run pytest tests/integration -v # All HTTP routes (mocked infra)
uv run pytest tests/security -v   # Auth bypass, injection, CORS

# With coverage
uv run pytest tests --cov=. --cov-report=html
```

> **Note:** Run backend tests from `apps/api` so the local package layout and test configuration resolve consistently.

---

## Security Model

| Layer | Mechanism |
|-------|-----------|
| Passwords | bcrypt (work factor â‰¥ 12), truncated to 72 bytes |
| JWTs | HS256, 60-min expiry, Redis blacklist on logout |
| Brute-force | Per-IP Redis counter: 5 failures â†’ 15-min lockout |
| Rate limiting | Per-user investigation counter: 10 / 5-min window |
| File safety | MIME + extension allowlist, 50 MB limit, SHA-256 integrity lock |
| Report signing | ECDSA P-256 + SHA-256, key derived deterministically from SIGNING_KEY |
| Container | `read_only: true` filesystem; writable paths via named volumes only |

---

## Storage Directories

| Path | Purpose | Notes |
|------|---------|-------|
| `apps/api/storage/evidence/` | Uploaded evidence files | Container-mounted volume; gitignored except `.gitkeep` |
| `apps/api/storage/keys/` | ECDSA signing keys | Auto-generated on first run; gitignored except `.gitkeep` |
| `apps/api/storage/calibration_models/` | Confidence calibration models | Shared via Docker volume |


**Key distinction:** `apps/api/storage/` is the application's internal storage root and the only storage tree that should be documented in this monorepo layout.

---

## ML Subprocesses

Heavy ML inference runs out-of-process via `asyncio.create_subprocess_exec` to prevent blocking the event loop and dropping WebSocket connections.

| Script | Tool | Agent |
|--------|------|-------|
| `tools/ml_tools/ela_anomaly_classifier.py` | IsolationForest ELA blocks | Agent 1 |
| `tools/ml_tools/noise_fingerprint.py` | PRNU camera noise fingerprint | Agent 1 |
| `tools/ml_tools/copy_move_detector.py` | SIFT copy-move forgery | Agent 1 |
| `tools/ml_tools/splicing_detector.py` | SRM noise residual splicing | Agent 1, 3 |
| `tools/ml_tools/audio_splice_detector.py` | Spectral splice detection | Agent 2 |
| `tools/ml_tools/deepfake_frequency.py` | DCT frequency deepfake | Agent 2, 4 |
| `tools/ml_tools/anomaly_classifier.py` | IsolationForest scene anomaly | Agent 3 |
| `tools/ml_tools/lighting_analyzer.py` | Shadow/highlight consistency | Agent 3 |
| `tools/ml_tools/rolling_shutter_validator.py` | Temporal rolling shutter | Agent 4 |
| `tools/ml_tools/metadata_anomaly_scorer.py` | EXIF entropy scoring | Agent 5 |











