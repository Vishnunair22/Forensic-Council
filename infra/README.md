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

Generate production-safe values with:

```bash
bash infra/generate_production_keys.sh
```

## Start The Stack

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

The base compose file pins the project name to `forensic-council`, so named volumes are stable across dev and production overrides.

Important volumes:

| Volume | Purpose |
| --- | --- |
| `postgres_data` | PostgreSQL data |
| `redis_data` | Redis persistence |
| `qdrant_data` | Qdrant vector storage |
| `evidence_data` | Uploaded evidence files |
| `signing_keys` | Signing key material |
| `hf_cache` | HuggingFace model cache |
| `torch_cache` | PyTorch model cache |
| `easyocr_cache` | EasyOCR cache |
| `yolo_cache` | Ultralytics/YOLO cache |
| `calibration_models_cache` | Calibration model storage |

Avoid `docker compose down -v` unless you intentionally want to delete all persisted data and model caches.

## Validation

Run:

```bash
bash infra/validate_production_readiness.sh
```

The script checks key repository files, Docker Compose rendering, basic syntax, tests when local tooling is available, and a small set of production security signals.

## Common Commands

```bash
# Render the effective compose config
docker compose -f infra/docker-compose.yml --env-file .env config

# Rebuild backend only
docker compose -f infra/docker-compose.yml --env-file .env build backend

# Restart backend without touching dependencies
docker compose -f infra/docker-compose.yml --env-file .env up -d --no-deps backend

# View logs
docker compose -f infra/docker-compose.yml --env-file .env logs -f

# Stop while keeping volumes
docker compose -f infra/docker-compose.yml --env-file .env down
```

## Production Notes

- Set `DOMAIN` in `.env` to a real public hostname before public deployment.
- Ensure ports 80 and 443 are open on the host.
- Keep `SIGNING_KEY` and `JWT_SECRET_KEY` separate.
- Store secrets in a password manager or secret manager.
- Rotate `METRICS_SCRAPE_TOKEN` if the Prometheus endpoint may have been exposed.
