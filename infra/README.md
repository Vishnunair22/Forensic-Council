# Forensic Council Infrastructure

This folder contains the Docker Compose, Caddy, Prometheus, and deployment helper files for the Forensic Council stack.

## Files

| File | Purpose |
| --- | --- |
| `docker-compose.yml` | Development/base stack: API, worker, frontend, Postgres, Redis, Qdrant, Caddy, Jaeger, Prometheus |
| `docker-compose.dev.yml` | Host-run development override that exposes Postgres, Redis, and Qdrant to localhost |
| `docker-compose.prod.yml` | Production override with optimized build targets, log rotation, and reduced direct host ports |
| `Caddyfile` | Reverse proxy, TLS, security headers, API routing, upload limits |
| `prometheus.yml` | Prometheus scrape configuration |
| `generate_production_keys.sh` | Generates strong `.env` secrets |
| `validate_production_readiness.sh` | Runs repository and infrastructure readiness checks |
| `DOCKER_BUILD.md` | Docker build and cache reference |

## Universal Quickstart (Zero to Running)

```bash
# 1. Clone and enter the repo
git clone https://github.com/Vishnunair22/Forensic-Council.git && cd Forensic-Council

# 2. Generate the .env from the template
cp .env.example .env

# 3. Generate strong secrets and update .env automatically
bash infra/generate_production_keys.sh --update

# 4. Add LLM keys to .env
#    LLM_API_KEY=<groq key from https://console.groq.com/keys>
#    GEMINI_API_KEY=<gemini key from https://aistudio.google.com/apikey>

# 5. Start (one command — validates .env, builds, starts, polls health)
bash scripts/dev.sh

# 6. Open the app
#    Frontend (via Caddy):  http://localhost
#    Frontend (direct):     http://localhost:3000
#    API docs (via Caddy):  http://localhost/docs
#    API docs (direct):     http://localhost:8000/docs  (dev overlay exposes 8000)
```

### Production (one command)

```bash
# Validates .env invariants and compose config BEFORE building, then boots
bash scripts/prod.sh
```

### Manual docker compose (if you need fine-grained control)

```bash
# Development — validate, build, start
bash infra/validate_production_readiness.sh   # optional pre-flight for dev
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env \
  up --build -d

# Production — ALWAYS validate BEFORE building/starting
bash infra/validate_production_readiness.sh
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.prod.yml \
  --env-file .env \
  up --build -d
```

## Required Environment

Create `.env` at the repository root from `.env.example`:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

At minimum, set:

```dotenv
SIGNING_KEY=<strong 32+ char secret>
JWT_SECRET_KEY=<strong 32+ char secret>
POSTGRES_PASSWORD=<strong password>
REDIS_PASSWORD=<strong password>
LLM_API_KEY=<provider key, or leave blank with LLM_PROVIDER=none>
GEMINI_API_KEY=<Gemini key, optional for tool-only local runs>
METRICS_SCRAPE_TOKEN=<strong scrape token>
CADDY_SITE_ADDRESS=http://localhost
USE_REDIS_WORKER=false          # direct host API mode
DOCKER_USE_REDIS_WORKER=true    # Docker API + worker mode
```

### Generating secrets

Run the key generation script to produce cryptographically strong values and update your `.env` file automatically:

```bash
bash infra/generate_production_keys.sh --update
```

The script updates `SIGNING_KEY`, `JWT_SECRET_KEY`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `QDRANT_API_KEY`, `BOOTSTRAP_ADMIN_PASSWORD`, `BOOTSTRAP_INVESTIGATOR_PASSWORD`, `DEMO_PASSWORD`, and `METRICS_SCRAPE_TOKEN` directly.

| Variable | Format | Used for |
| --- | --- | --- |
| `SIGNING_KEY` | 64-char hex | ECDSA P-256 report signing |
| `JWT_SECRET_KEY` | 64-char hex | JWT token signing |
| `POSTGRES_PASSWORD` | 32-char alphanumeric | Database authentication |
| `REDIS_PASSWORD` | 32-char alphanumeric | Redis authentication |
| `BOOTSTRAP_ADMIN_PASSWORD` | 32-char alphanumeric | Initial admin user seed |
| `BOOTSTRAP_INVESTIGATOR_PASSWORD` | 32-char alphanumeric | Initial investigator user seed |
| `DEMO_PASSWORD` | 32-char alphanumeric | Demo login (dev/staging only) |
| `METRICS_SCRAPE_TOKEN` | 64-char hex | Prometheus bearer token |

The script does **not** generate `LLM_API_KEY` or `GEMINI_API_KEY` — obtain those from
[Groq](https://console.groq.com) and [Google AI Studio](https://aistudio.google.com) respectively.

> **Warning:** `SIGNING_KEY` is used to produce ECDSA signatures on forensic reports.
> If rotated or lost, previously signed reports will fail signature verification.
> Store it in a password manager or secret management system (e.g., HashiCorp Vault, AWS Secrets Manager).

## Start The Stack

> **Shell compatibility:** The examples below use Unix-style `\` line continuation (bash/zsh).
> On Windows PowerShell, replace each `\` with a backtick `` ` ``.
> Example:
> ```powershell
> docker compose `
>   -f infra/docker-compose.yml `
>   --env-file .env `
>   up --build
> ```
> Git Bash and WSL2 bash both accept the Unix `\` syntax without modification.

Development (use dev overlay for direct host ports 5432, 6379, 6333, 8000):

```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env \
  up --build
```

Production-style local run:

```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.prod.yml \
  --env-file .env \
  up --build -d
```

Fast Dockerfile smoke build without model preloading:

```bash
PRELOAD_MODELS=0 SKIP_MODEL_DOWNLOAD=1 docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.prod.yml \
  --env-file .env \
  build migration backend worker frontend
```

Use this for CI or Dockerfile validation. For a runnable stack with empty model
volumes, leave `SKIP_MODEL_DOWNLOAD` unset so the entrypoint can populate any
missing caches. Use the default `PRELOAD_MODELS=1` for production image builds
so clean model volumes start warm.

CI and local tests use the same base compose file unless a test-specific override is added later.

## Ports

Base/development stack (via Caddy only — no direct host ports):

| Service | Host Port | Notes |
| --- | --- | --- |
| Caddy | 80, 443 | Public reverse proxy (recommended entry point) |
| Frontend | 3000 | Direct local access (dev overlay not required) |
| Backend | — | Not exposed directly in base stack; route through Caddy at port 80 |
| Jaeger | 16686 | Local tracing UI |
| Prometheus | 9090 | Local metrics UI |

Host-run development override (`-f infra/docker-compose.dev.yml`) adds direct host ports:

| Service | Host Port | Notes |
| --- | --- | --- |
| Backend | 8000 | Direct backend API access |
| Postgres | 5432 | Enables `uv run` API on host |
| Redis | 6379 | Enables `uv run` API on host |
| Qdrant | 6333, 6334 | Enables `uv run` API on host |

Production override:

- Backend and frontend direct host ports are removed.
- Postgres, Redis, and Qdrant are internal unless you add the dev override.
- Jaeger and Prometheus direct host ports are removed.
- Public traffic should enter through Caddy on ports 80/443.

## Routing

Caddy routes:

- `/api/v1/*` to the FastAPI backend.
- Everything else to the Next.js frontend.

Do not widen the backend matcher to `/api/*`; the frontend owns server-side routes such as `/api/auth/demo`.

## Metrics

The backend exposes Prometheus metrics at:

```text
/api/v1/metrics/raw
```

That endpoint requires:

```text
Authorization: Bearer <METRICS_SCRAPE_TOKEN>
```

The compose stack wires this in two places:

- Backend receives `METRICS_SCRAPE_TOKEN` as an environment variable.
- Prometheus receives the same value as the `metrics_scrape_token` secret and reads it from `/run/secrets/metrics_scrape_token`.

## Volumes

The base compose file pins the project name to `forensic-council`, so named volumes are
stable across dev and production overrides.

### Data volumes — do not delete casually

| Volume | Purpose | Consequence of deletion |
| --- | --- | --- |
| `postgres_data` | PostgreSQL data directory | All investigation records lost |
| `redis_data` | Redis AOF/RDB persistence | Session state and rate-limit counters reset |
| `qdrant_data` | Qdrant vector storage | Episodic memory lost; re-indexes on next run |
| `evidence_data` | Uploaded evidence files | All evidence files lost |
| `signing_keys` | ECDSA P-256 signing key material | Old report signatures become unverifiable |
| `prometheus_data` | Prometheus TSDB (15-day retention) | Metrics history lost |
| `caddy_data` | Let's Encrypt certificates | Forces re-issuance; rate-limited to 5/week/domain |
| `caddy_config` | Caddy configuration cache | Rebuilt automatically on restart |
| `caddy_logs` | Caddy structured access logs | Log history lost |

### Model / cache volumes — expensive to rebuild

| Volume | Contents | Consequence of deletion |
| --- | --- | --- |
| `hf_cache` | HuggingFace model weights | Re-downloads on next start (~several GB) |
| `torch_cache` | PyTorch checkpoints | Re-downloads on next start |
| `easyocr_cache` | EasyOCR model files | Re-downloads on next start |
| `yolo_cache` | DETR (Apache-2.0, default) or Ultralytics YOLO (AGPL, when `ENABLE_AGPL_MODELS=true`) weights | Re-downloads on next start |
| `numba_cache` | Numba JIT-compiled kernels | Recompiled on next start (slow first run) |
| `calibration_models_cache` | Platt scaling calibration files | Must be retrained via `scripts/train_calibration.py` |

Avoid `docker compose down -v` unless you intentionally want to delete all persisted data
and model caches. To stop the stack while preserving volumes:

```bash
docker compose -f infra/docker-compose.yml --env-file .env down
```

## Validation

Run:

```bash
bash infra/validate_production_readiness.sh
```

The script checks key repository files, Docker Compose rendering, basic syntax, tests when local tooling is available, and a small set of production security signals.

## Common Commands

```bash
# Render the effective merged compose config (useful for debugging)
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env config

# No-cache rebuild and restart a single service (dev or prod)
bash scripts/rebuild.sh dev backend
bash scripts/rebuild.sh prod backend

# Rebuild all services from scratch
bash scripts/rebuild.sh dev
bash scripts/rebuild.sh prod

# Tail logs for all services
docker compose \
  -f infra/docker-compose.yml \
  --env-file .env logs -f

# Tail logs for a single service
docker compose \
  -f infra/docker-compose.yml \
  --env-file .env logs -f backend

# Stop the stack, keep volumes intact
docker compose \
  -f infra/docker-compose.yml \
  --env-file .env down

# Full reset — destroys all data and model caches
docker compose \
  -f infra/docker-compose.yml \
  --env-file .env down -v
```

## Network Segmentation

The stack uses four bridge networks to enforce least-privilege service-to-service access.

              ┌─────────────┐
              │    Caddy    │ (frontend_net + backend_net)
              └──────┬──────┘
         ┌───────────┼───────────┐
         ▼           │           ▼
  frontend_net   backend_net   backend_net
         │           │           │
    ┌────┴────┐  ┌───┴────┐     │
    │Frontend │  │Backend │◄────┘ ← also on external_net
    └─────────┘  │Worker  │   ← also on external_net
                 └────┬───┘
                      │ infra_net
          ┌───────────┼───────────┐
          ▼           ▼           ▼
       Redis       Postgres    Qdrant
                  (+ jaeger, migration)

| Network | Members | Internal? | Purpose |
| --- | --- | --- | --- |
| `infra_net` | redis, postgres, qdrant, jaeger, migration, backend, worker | yes (no internet) | Backend ↔ infrastructure communication. `internal: true` so infra services have no outbound. |
| `external_net` | backend, worker | no | Outbound internet for Groq, Gemini, and HuggingFace model downloads. |
| `backend_net` | backend, caddy, frontend, prometheus | no | Caddy and frontend reach the backend API. Prometheus scrapes `backend:8000/api/v1/metrics/raw`. |
| `frontend_net` | frontend, caddy | no | Caddy proxies to the Next.js server. |

Do not attach new services to `infra_net` unless they genuinely need database access.
New services that need outbound internet (e.g. additional LLM providers) must be attached to `external_net` rather than relying on `infra_net` egress, which is disabled.

## Production Notes

- Set `DOMAIN` in `.env` to a real public hostname before public deployment.
- Ensure ports 80 and 443 are open on the host.
- Keep `SIGNING_KEY` and `JWT_SECRET_KEY` separate.
- Store secrets in a password manager or secret manager.
- Rotate `METRICS_SCRAPE_TOKEN` if the Prometheus endpoint may have been exposed.
