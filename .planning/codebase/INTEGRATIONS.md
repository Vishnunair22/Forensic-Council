# External Integrations

**Analysis Date:** 2026-04-16

## APIs & External Services

**LLM / Reasoning (configurable provider):**
- Groq API - Llama 3.3 70B inference for ReAct agent reasoning loops
  - SDK/Client: `groq >=0.28` + custom `httpx` client in `apps/api/core/llm_client.py`
  - Auth: `LLM_API_KEY` env var (provider selected via `LLM_PROVIDER=groq`)
  - Model: `LLM_MODEL=llama-3.3-70b-versatile` (~700 tok/s, free tier)
  - Endpoint: Groq API (standard SDK)
  - Alternative providers: `openai`, `anthropic` (same `LLMClient` interface); set `LLM_PROVIDER` accordingly
  - Default when not configured: `none` (task-decomposition driver, no LLM calls)

**Vision / Multimodal Analysis:**
- Google Gemini API - Deep forensic vision analysis for Agents 1, 3, and 5
  - SDK/Client: `google-generativeai >=0.8` + direct `httpx` calls to `https://generativelanguage.googleapis.com/v1beta` in `apps/api/core/gemini_client.py`
  - Auth: `GEMINI_API_KEY` env var
  - Primary model: `GEMINI_MODEL=gemini-2.5-flash` (1M context, best free-tier)
  - Fallback chain: `GEMINI_FALLBACK_MODELS=gemini-2.0-flash,gemini-2.0-flash-lite` (auto-cascade on 404/429)
  - Concurrency limit: `GEMINI_MAX_CONCURRENT=2` (prevents free-tier quota exhaustion across 5 parallel agents)
  - Timeout: `GEMINI_TIMEOUT=55.0` seconds
  - Policy gate: `GEMINI_API_KEY_POLICY_OK=true` (set false to disable Gemini globally)
  - Agents using Gemini: Agent 1 (Image Integrity), Agent 3 (Object/Weapon), Agent 5 (Metadata/Context)
  - Input types: base64-encoded images (JPEG/PNG/WEBP/GIF/BMP), PDFs (first page), video frames (thumbnails), audio spectrograms

**ML Model Registries (download-on-first-use):**
- HuggingFace Hub - transformers and SpeechBrain models
  - Env: `HF_HOME=/app/cache/huggingface`
  - Models: `google/siglip-base-patch16-224` (vision-language), `speechbrain/anti-spoof-aasist` (voice clone detection)
  - Docker volume: `hf_cache`
- PyTorch Hub (CPU-only index: `https://download.pytorch.org/whl/cpu`) - torch/torchvision/torchaudio
  - Env: `TORCH_HOME=/app/cache/torch`
  - Docker volume: `torch_cache`
- Ultralytics / YOLO model registry - object detection
  - Model: `yolo11m.pt` (configurable via `YOLO_MODEL_NAME`)
  - Env: `YOLO_MODEL_DIR=/app/cache/ultralytics`
  - Docker volume: `yolo_cache`
- EasyOCR model registry - neural OCR models
  - Env: `EASYOCR_MODEL_DIR=/app/cache/easyocr`
  - Docker volume: `easyocr_cache`
- Offline mode: set `OFFLINE_MODE=true` to force all ML libraries to use local cache only (fails if models are absent)

**TLS Certificate Authority:**
- Let's Encrypt (ACME) - automatic TLS provisioning via Caddy 2
  - Configured in `infra/Caddyfile` via `{$DOMAIN}` env var
  - Development: self-signed cert when `DOMAIN=localhost`
  - Production: automatic cert when `DOMAIN=forensic.yourdomain.com`
  - Optional: `ACME_EMAIL` for expiry notifications

## Data Storage

**Databases:**
- PostgreSQL 17 (Alpine) - custody ledger, session reports, users, audit logs
  - Docker image: `postgres:17-alpine`
  - Connection env vars: `POSTGRES_HOST`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
  - Client: `asyncpg >=0.30` via `apps/api/core/persistence/postgres_client.py`
  - Pool: `POSTGRES_MIN_POOL_SIZE=2`, `POSTGRES_MAX_POOL_SIZE=10`
  - Schema managed by: `apps/api/core/migrations.py` (version-controlled, idempotent)
  - Migration runner: `migration` Docker service (one-shot, runs `scripts/init_db.py`)
  - Docker volume: `postgres_data`
  - Key tables: `session_reports`, `schema_migrations`, chain-of-custody entries

- Redis 7 (Alpine) - working memory, task queue, custody WAL
  - Docker image: `redis:7-alpine`
  - Connection env vars: `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD` (required in production)
  - Client: `redis.asyncio` (built into `redis >=5.3`) via `apps/api/core/persistence/redis_client.py`
  - Uses: agent task tracking (`apps/api/core/working_memory.py`), investigation queue (when `USE_REDIS_WORKER=true`), custody WAL (`forensic:custody:wal`)
  - Docker volume: `redis_data`
  - Memory limit: 512 MB

- Qdrant v1.13.6 - episodic memory / vector storage for forensic signatures
  - Docker image: `qdrant/qdrant:v1.13.6`
  - Connection env vars: `QDRANT_HOST`, `QDRANT_PORT=6333`, `QDRANT_GRPC_PORT=6334`, `QDRANT_API_KEY` (optional)
  - Client: `qdrant-client ==1.16.2` (AsyncQdrantClient) via `apps/api/core/persistence/qdrant_client.py`
  - Collection: `forensic_episodes` (default vector size: 512)
  - Uses: stores forensic signature entries per agent/case/session (`apps/api/core/episodic_memory.py`)
  - Docker volume: `qdrant_data`
  - Memory limit: 1 GB

**File Storage:**
- Local filesystem (Docker volume) - evidence files
  - Path: `/app/storage/evidence` (env: `EVIDENCE_STORAGE_PATH`)
  - Docker volume: `evidence_data` (shared between `backend` and `worker` containers)
  - Retention: `EVIDENCE_RETENTION_DAYS=7` (automated purging)

**Caching:**
- Redis (working memory + task queue, described above)
- Docker named volumes for ML model caches: `hf_cache`, `torch_cache`, `easyocr_cache`, `numba_cache`, `yolo_cache`
- Calibration models: `calibration_models_cache` volume at `/app/storage/calibration_models`

## Authentication & Identity

**Auth Provider:**
- Custom JWT-based authentication (no third-party auth provider)
  - Implementation: `apps/api/core/auth.py`
  - JWT library: `python-jose[cryptography] >=3.5`
  - Algorithm: `HS256` (configurable via `JWT_ALGORITHM`)
  - Token expiry: `JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60`
  - Password hashing: bcrypt (12 rounds) via `passlib[bcrypt]`
  - Token secret: `JWT_SECRET_KEY` env var (must be ≥32 chars in production)
  - Transport: HttpOnly cookies (primary) + HTTP Bearer token (Swagger UI)
  - Roles: `investigator`, `admin`, `auditor` (enum in `apps/api/core/auth.py`)
  - Bootstrap users: `BOOTSTRAP_ADMIN_PASSWORD`, `BOOTSTRAP_INVESTIGATOR_PASSWORD` (first-run only)

**Demo Auth:**
- Next.js API route at `/api/auth/demo` (`apps/web/src/app/api/auth/demo/`)
  - Server-side only password via `DEMO_PASSWORD` env var
  - Never exposed as `NEXT_PUBLIC_*` to prevent client bundle baking

**Cryptographic Signing:**
- ECDSA P-256 chain-of-custody signing - `apps/api/core/signing.py`
  - Each agent gets an independent key pair stored encrypted in PostgreSQL
  - Fernet encryption of private keys using `SIGNING_KEY` as the Fernet key
  - Fallback: HMAC-SHA256 deterministic derivation from `SIGNING_KEY` when Postgres unavailable
  - Key rotation supported via `rotate_agent_key(agent_id)`

## Monitoring & Observability

**Distributed Tracing:**
- Jaeger v1.62.0 - distributed tracing backend
  - Docker image: `jaegertracing/all-in-one:1.62.0`
  - UI port: `16686`
  - Collector: OTLP gRPC on port `4317`
  - Toggle: `OTEL_ENABLED=false` (disabled by default; Jaeger always starts but export is optional)
  - Exporter: `opentelemetry-exporter-otlp-proto-grpc` → `http://jaeger:4317`
  - Instrumented: FastAPI, Redis, SQLAlchemy (`apps/api/core/observability.py`)
  - Service names: `forensic_api`, `forensic_worker`

**Metrics:**
- Custom Prometheus-compatible endpoint: `GET /api/v1/metrics/raw`
  - Protected by `METRICS_SCRAPE_TOKEN` Bearer token; returns 503 if not set
  - Route: `apps/api/api/routes/metrics.py`

**Logs:**
- Structured JSON logging via `apps/api/core/structured_logging.py`
- `get_logger(__name__)` throughout the backend
- `LOG_LEVEL` env var (DEBUG/INFO/WARNING/ERROR/CRITICAL)
- Caddy access logs: JSON format, rolling 10 MB files in `/var/log/caddy/access.log`

**Error Tracking:**
- None (no Sentry or similar external error tracking configured)

## CI/CD & Deployment

**Hosting:**
- Docker Compose on self-hosted infrastructure (no cloud-managed services detected)
- Reverse proxy: Caddy 2 Alpine on ports 80 / 443

**CI Pipeline:**
- GitHub Actions (`.github/workflows/ci.yml`)
  - Triggers: push/PR to `main` and `develop` branches
  - Jobs: `backend-lint` (ruff + pyright), `backend-test` (pytest with Postgres+Redis services), `frontend-lint` (eslint + tsc), `frontend-test` (jest)
  - Python version: from `apps/api/.python-version`
  - Node version: from `apps/web/.node-version`
  - ML extras excluded from CI to avoid 3 GB download

## Webhooks & Callbacks

**Incoming:**
- None (no webhook endpoints detected)

**Outgoing:**
- None (no outbound webhook calls detected)

## Real-Time Communication

**WebSocket:**
- FastAPI WebSocket endpoint for live investigation updates (`apps/api/api/routes/` - websocket handler)
- Frontend connects via `apps/web/src/lib/api.ts` using `new WebSocket(wsUrl)`
- Same-origin constraint enforced: WS must go through same host as page (Caddy proxies upgrade requests with Cookie headers forwarded)
- Dev fallback: frontend on port 3000 connects directly to `ws://localhost:8000`

**Server-Sent Events (SSE):**
- SSE endpoint for investigation progress streaming (`apps/api/api/routes/sse.py`)
- Route: `GET /api/v1/...`

## Environment Configuration

**Required environment variables:**
- `SIGNING_KEY` - ECDSA audit signing key (≥32 chars, high entropy)
- `JWT_SECRET_KEY` - JWT session signing key (≥32 chars, high entropy)
- `POSTGRES_PASSWORD` - PostgreSQL password (≥16 chars in production)
- `REDIS_PASSWORD` - Redis auth password (required in production)
- `BOOTSTRAP_ADMIN_PASSWORD` - Initial admin user password (first run only)
- `BOOTSTRAP_INVESTIGATOR_PASSWORD` - Initial investigator password (first run only)
- `LLM_API_KEY` - Groq/OpenAI/Anthropic key (required when `LLM_PROVIDER != none`)
- `GEMINI_API_KEY` - Google Gemini key (optional; agents degrade gracefully without it)

**Optional / operational:**
- `DOMAIN` - Public domain for Caddy TLS (`localhost` default)
- `OTEL_ENABLED` - Enable OpenTelemetry export to Jaeger (`false` default)
- `METRICS_SCRAPE_TOKEN` - Token for Prometheus scrape endpoint
- `DAILY_COST_QUOTA_USD` / `DAILY_COST_QUOTA_ADMIN_USD` - LLM cost budget gates
- `RATE_LIMIT_AUTHENTICATED` / `RATE_LIMIT_ANONYMOUS` / `RATE_LIMIT_INVESTIGATION_PER_5MIN`
- `NUMBA_DISABLE_JIT=1` - Disables Numba JIT (recommended for CPU-only containers)
- `OFFLINE_MODE=true` - Forces ML libraries to use local cache only

**Secrets location:**
- `.env` file at monorepo root (never committed; generated via `infra/generate_production_keys.sh`)
- Docker secrets passed via `environment:` blocks in `infra/docker-compose.yml`
- Private keys for ECDSA signing: `signing_keys` Docker volume at `/app/storage/keys`

---

*Integration audit: 2026-04-16*
