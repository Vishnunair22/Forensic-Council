# Forensic Council Infrastructure

This folder contains the Docker Compose, Caddy, Prometheus, and deployment helper files for the Forensic Council stack.

## Files

| File | Purpose |
| --- | --- |
| `docker-compose.yml` | Base stack: API, worker, frontend, Postgres, Redis, Qdrant, Caddy, Jaeger, Prometheus |
| `docker-compose.dev.yml` | Development override with hot reload and larger frontend dev resources |
| `docker-compose.prod.yml` | Production override with optimized build targets, log rotation, and reduced direct host ports |
| `docker-compose.infra.yml` | Infrastructure-only override for Postgres, Redis, and Qdrant |
| `docker-compose.test.yml` | Lightweight integration test services |
| `Caddyfile` | Reverse proxy, TLS, security headers, API routing, upload limits |
| `prometheus.yml` | Prometheus scrape configuration |
| `generate_production_keys.sh` | Generates strong `.env` secrets |
| `validate_production_readiness.sh` | Runs repository and infrastructure readiness checks |
| `DOCKER_BUILD.md` | Docker build and cache reference |

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
```

### Generating secrets

Run the key generation script to produce cryptographically strong values for all local secrets:

```bash
bash infra/generate_production_keys.sh
```

The script outputs the following variables — paste them into your `.env`:

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
>   -f infra/docker-compose.dev.yml `
>   --env-file .env `
>   up --build
> ```
> Git Bash and WSL2 bash both accept the Unix `\` syntax without modification.

Development:

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

Infrastructure only:

```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.infra.yml \
  --env-file .env \
  up -d
```

Test services:

```bash
docker compose -f infra/docker-compose.test.yml up -d
```

## Ports

Base/development stack:

| Service | Host Port | Notes |
| --- | --- | --- |
| Caddy | 80, 443 | Public reverse proxy |
| Frontend | 3000 | Direct local access |
| Backend | 8000 | Direct local API access |
| Jaeger | 16686 | Local tracing UI |
| Prometheus | 9090 | Local metrics UI |

Production override:

- Backend and frontend direct host ports are removed.
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
| `yolo_cache` | Ultralytics/YOLO weights | Re-downloads on next start |
| `numba_cache` | Numba JIT-compiled kernels | Recompiled on next start (slow first run) |
| `calibration_models_cache` | Platt scaling calibration files | Must be retrained via `scripts/train_calibration.py` |

### Development-only volumes

| Volume | Contents | Scope |
| --- | --- | --- |
| `nextjs_cache` | Next.js webpack compiler cache | Dev overlay only; prevents 120s recompilation on restart |

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

All examples below show the development overlay. For production, replace
`-f infra/docker-compose.dev.yml` with `-f infra/docker-compose.prod.yml`.

```bash
# Render the effective merged compose config (useful for debugging)
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env config

# Rebuild and restart a single service without touching dependencies
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env build backend

docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env up -d --no-deps backend

# Tail logs for all services
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env logs -f

# Tail logs for a single service
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env logs -f backend

# Stop the stack, keep volumes intact
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env down

# Full reset — destroys all data and model caches
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env down -v
```

## Network Segmentation

The stack uses three bridge networks to enforce least-privilege service-to-service access.

              ┌─────────────┐
              │    Caddy    │ (frontend_net + backend_net)
              └──────┬──────┘
         ┌───────────┼───────────┐
         ▼           │           ▼
  frontend_net   backend_net   backend_net
         │           │           │
    ┌────┴────┐  ┌───┴────┐     │
    │Frontend │  │Backend │◄────┘
    └─────────┘  │Worker  │
                 └────┬───┘
                      │ infra_net
          ┌───────────┼───────────┐
          ▼           ▼           ▼
       Redis       Postgres    Qdrant

| Network | Members | Purpose |
| --- | --- | --- |
| `infra_net` | backend, worker, migration, redis, postgres, qdrant, jaeger, prometheus | Backend ↔ infrastructure communication |
| `backend_net` | backend, caddy, frontend | Caddy and frontend reach the backend API |
| `frontend_net` | frontend, caddy | Caddy proxies to the Next.js server |

**Key isolation guarantees:**
- The frontend container cannot reach Redis, Postgres, or Qdrant directly.
- Caddy cannot reach Redis, Postgres, or Qdrant directly.
- Infrastructure services are not exposed to the frontend network.

When adding a new service, explicitly assign it to only the networks it requires.
Do not attach new services to `infra_net` unless they genuinely need database access.

## Production Notes

- Set `DOMAIN` in `.env` to a real public hostname before public deployment.
- Ensure ports 80 and 443 are open on the host.
- Keep `SIGNING_KEY` and `JWT_SECRET_KEY` separate.
- Store secrets in a password manager or secret manager.
- Rotate `METRICS_SCRAPE_TOKEN` if the Prometheus endpoint may have been exposed.
