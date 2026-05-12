# Forensic Council Backend

FastAPI backend for the Forensic Council multi-agent forensic evidence analysis system.

**Version:** v1.7.0

## What Lives Here

```text
api/              FastAPI app, schemas, and route modules
agents/           Five specialist forensic agents plus the Council Arbiter
config/           task/tool override configuration
core/             auth, config, custody, signing, memory, orchestration helpers
orchestration/    investigation queue, session manager, pipeline, and worker
scripts/          startup, migration, verification, cache, and utility scripts
storage/          local storage roots and key placeholders
tests/            unit, integration, security, infra, and system tests
tools/            image, audio, video, metadata, OCR, and ML subprocess tools
```

## Setup

```bash
cd apps/api
uv sync --extra dev --extra security --extra observability

# One-time: initialize database schema and bootstrap users
POSTGRES_HOST=localhost REDIS_HOST=localhost QDRANT_HOST=localhost USE_REDIS_WORKER=false \
  uv run python scripts/init_db.py
```

## Run

```bash
# Development (in-process, no worker)
POSTGRES_HOST=localhost REDIS_HOST=localhost QDRANT_HOST=localhost USE_REDIS_WORKER=false \
  uv run python scripts/run_api.py

# Verify health
curl -fsS http://localhost:8000/health
```

For Docker worker mode, start infrastructure from the repo root:
```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env up -d postgres redis qdrant
```

The dev override exposes Postgres `5432`, Redis `6379`, and Qdrant `6333/6334` for host-run development.

## Test

| Suite | Command |
|-------|---------|
| Unit + security + infra | `uv run pytest tests/unit tests/security tests/infra -q --tb=short` |
| Contracts + integration | `uv run pytest tests/contracts tests/integration -q --tb=short` |
| All (temp dir) | `uv run pytest tests/ -q --tb=short --basetemp .pytest_tmp_run` |
| With ML extras | `uv sync --extra ml` then run tests |
| Live provider (opt-in) | `RUN_LIVE_PROVIDER_TESTS=1 uv run pytest tests/` |
| ML/system (opt-in) | `RUN_SYSTEM_ML_TESTS=1 uv run pytest tests/system/` |

See [docs/TESTING.md](docs/TESTING.md) for full test commands and verification scripts.

## Config

Key `.env` variables for free-tier provider setup:

| Variable | Purpose |
| --- | --- |
| `FREE_TIER_MODE` | `true` blocks OpenAI/Anthropic, enforces quota limits |
| `LLM_API_KEY` | Groq key — agent uses `llama-3.1-8b-instant`, Arbiter `llama-3.3-70b-versatile` |
| `GEMINI_API_KEY` | Gemini key for Agent 1/3/5 deep analysis |
| `GEMINI_API_KEY_POLICY_OK` | Must be `true` before Gemini calls (safety flag) |
| `GEMINI_RPM_LIMIT` / `GEMINI_RPD_LIMIT` / `GROQ_RPM_LIMIT` | Per-provider quota limits |

See [docs/MODEL_REGISTRY.md](docs/MODEL_REGISTRY.md) for full model/provider setup and verification.

## Architecture

| Module | Purpose |
| --- | --- |
| `api/main.py` | FastAPI app, lifespan hooks, middleware, health checks |
| `api/routes/investigation.py` | Evidence upload and investigation start |
| `api/routes/sessions.py` | Report retrieval, live stream, resume, session state |
| `api/routes/hitl.py` | Human-in-the-loop decisions |
| `api/routes/metrics.py` | Operational and Prometheus metrics |
| `core/config.py` | Pydantic settings and production validation |
| `core/auth.py` | JWT, password hashing, role checks, blacklist |
| `core/signing.py` | ECDSA P-256 signing and verification |
| `core/custody_logger.py` | Chain-of-custody logging |
| `core/working_memory.py` | Redis-backed working memory with fallback |
| `core/episodic_memory.py` | Qdrant-backed historical finding memory |
| `core/react_loop.py` | ReAct/task-decomposition execution engine |
| `core/provider_quota_guard.py` | Per-provider RPM/RPD sliding window enforcement |
| `orchestration/pipeline.py` | Two-phase investigation pipeline |
| `orchestration/investigation_queue.py` | Redis queue and worker integration |
| `scripts/verify_llm_keys.py` | Provider key verification (uses /models endpoints, no quota burn) |

## Agents

| Agent | File | Focus |
| --- | --- | --- |
| Image | `agents/agent1_image.py` | ELA, noise, copy-move, splicing, vision grounding |
| Audio | `agents/agent2_audio.py` | diarization, splice, voice synthesis, audio anomalies |
| Object | `agents/agent3_object.py` | object detection, scene coherence, lighting consistency |
| Video | `agents/agent4_video.py` | temporal consistency, rolling shutter, inter-frame forgery |
| Metadata | `agents/agent5_metadata.py` | EXIF, GPS, C2PA/JUMBF, provenance |
| Arbiter | `agents/arbiter.py` | finding synthesis, deterministic verdict, report signing |

## Security Guardrails

- Verdicts are deterministic and must be computed from structured findings.
- LLMs may summarize or enrich narrative, but they must not set verdicts.
- Preserve custody logging for significant forensic actions.
- Keep `SIGNING_KEY` and `JWT_SECRET_KEY` separate.
- Do not log raw bearer tokens, API keys, or evidence contents.
- Use `core.*` imports for backend infrastructure.

## Do Not Edit Casually

- `apps/api/core/migrations.py` — schema migration logic
- `apps/api/config/models.lock.json` — model config; update via documented process only
- Auth/session routes (`apps/api/api/routes/auth.py`, `apps/api/api/routes/_authz.py`) — security-critical
- Agent verdict logic (`apps/api/agents/arbiter.py`) — deterministic, no LLM verdict assignment