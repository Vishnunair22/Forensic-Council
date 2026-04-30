# Forensic Council Backend

FastAPI backend for the Forensic Council multi-agent forensic evidence analysis system.

## What Lives Here

```text
api/              FastAPI app, schemas, and route modules
agents/           five specialist forensic agents plus the Council Arbiter
config/           task/tool override configuration
core/             auth, config, custody, signing, memory, orchestration helpers
orchestration/    investigation queue, session manager, and pipeline
reports/          report rendering helpers
scripts/          startup, migration, verification, cache, and utility scripts
storage/          local storage roots and key placeholders
tests/            unit, integration, security, infra, and system tests
tools/            image, audio, video, metadata, OCR, and ML subprocess tools
worker.py         Redis-backed investigation worker entry point
```

## Runtime Flow

```text
FastAPI route
  -> evidence ingestion and SHA-256 hashing
  -> session state and custody logging
  -> ForensicCouncilPipeline
  -> specialist agents
  -> Council Arbiter
  -> signed report persistence
```

The backend supports both in-process investigation execution and external worker execution through the Redis-backed investigation queue.

## Key Modules

| Module | Purpose |
| --- | --- |
| `api/main.py` | FastAPI app, lifespan hooks, middleware, health checks |
| `api/routes/investigation.py` | Evidence upload and investigation start flow |
| `api/routes/sessions.py` | report retrieval, live stream, resume, session state |
| `api/routes/hitl.py` | Human-in-the-loop decisions |
| `api/routes/metrics.py` | Operational and Prometheus metrics |
| `core/config.py` | Pydantic settings and production validation |
| `core/auth.py` | JWT, password hashing, role checks, blacklist support |
| `core/signing.py` | ECDSA P-256 signing and verification |
| `core/custody_logger.py` | Chain-of-custody logging |
| `core/working_memory.py` | Redis-backed working memory with fallback |
| `core/episodic_memory.py` | Qdrant-backed historical finding memory |
| `core/react_loop.py` | ReAct/task-decomposition execution engine |
| `orchestration/pipeline.py` | two-phase investigation pipeline |
| `orchestration/investigation_queue.py` | Redis queue and worker integration |

## Agents

| Agent | File | Focus |
| --- | --- | --- |
| Image | `agents/agent1_image.py` | ELA, noise, copy-move, splicing, vision grounding |
| Audio | `agents/agent2_audio.py` | diarization, splice, voice synthesis, audio anomalies |
| Object | `agents/agent3_object.py` | object detection, scene coherence, lighting consistency |
| Video | `agents/agent4_video.py` | temporal consistency, rolling shutter, inter-frame forgery |
| Metadata | `agents/agent5_metadata.py` | EXIF, GPS, C2PA/JUMBF, provenance |
| Arbiter | `agents/arbiter.py` | finding synthesis, deterministic verdict, signing |

## Local Development

From `apps/api`:

```powershell
uv sync --extra dev
uv run python scripts/run_api.py
```

To start only infrastructure from the repository root:

```powershell
docker compose -f infra/docker-compose.yml -f infra/docker-compose.infra.yml --env-file .env up -d
```

## Tests And Checks

From `apps/api`:

```powershell
uv run ruff check .
uv run pyright core/ agents/ api/ tools/
uv run pytest tests/ -v
```

Focused test groups:

```powershell
uv run pytest tests/unit -v
uv run pytest tests/integration -v
uv run pytest tests/security -v
uv run pytest tests/infra -v
```

## Environment

Canonical configuration is the repository-root `.env.example`.

Important backend variables:

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | `development`, `testing`, or `production` |
| `SIGNING_KEY` | root secret for report and custody signing derivation |
| `JWT_SECRET_KEY` | separate JWT/session signing secret |
| `POSTGRES_*` | PostgreSQL connection settings |
| `REDIS_*` | Redis connection settings |
| `QDRANT_*` | Qdrant connection settings |
| `LLM_PROVIDER` | LLM provider, commonly `groq` or `none` |
| `LLM_API_KEY` | provider API key |
| `GEMINI_API_KEY` | Gemini multimodal analysis key |
| `LLM_MODEL` | primary reasoning/synthesis model |
| `LLM_FALLBACK_MODELS` | ordered fallback models for primary LLM failures |
| `GEMINI_MODEL` | primary multimodal forensic grounding model |
| `GEMINI_FALLBACK_MODELS` | ordered Gemini fallback cascade for deep analysis |
| `METRICS_SCRAPE_TOKEN` | bearer token for `/api/v1/metrics/raw` |

## Security Guardrails

- Verdicts are deterministic and must be computed from structured findings.
- LLMs may summarize or enrich narrative, but they must not set verdicts.
- Preserve custody logging for significant forensic actions.
- Keep `SIGNING_KEY` and `JWT_SECRET_KEY` separate.
- Do not log raw bearer tokens, API keys, or evidence contents.
- Use `core.*` imports for backend infrastructure.

## Storage

| Path | Purpose |
| --- | --- |
| `storage/evidence/` | uploaded evidence files in local/container mode |
| `storage/keys/` | signing key material |
| `storage/calibration_models/` | calibration model files |

Runtime storage and model cache paths are mounted through Docker volumes in `infra/docker-compose.yml`.

## ML Subprocesses

Heavy ML tools run in subprocesses under `tools/ml_tools/` to avoid blocking the async API event loop. The pipeline treats these tools as isolated workers and records results through the normal finding and custody paths.
