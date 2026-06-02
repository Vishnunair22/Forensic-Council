# Helper Scripts

Operational and developer scripts for Forensic Council. Build/run scripts are
Bash and expect to be invoked from the repository root.

> **Running on Windows:** these `.sh` scripts require a POSIX shell — use **Git Bash**
> or **WSL2**. The underlying `docker compose ...` commands they wrap are themselves
> cross-platform and can be run directly from PowerShell or `cmd` if you prefer (see
> [infra/DOCKER_BUILD.md](../infra/DOCKER_BUILD.md)). `.py` scripts run anywhere Python 3.12 is available.

## Lifecycle / build scripts

| Script | Usage | Purpose |
|--------|-------|---------|
| `dev.sh` | `bash scripts/dev.sh` | One-command **development** boot: pre-flight checks, port-conflict scan, env validation, parallel build, `up -d`, then waits for API / worker / Caddy / frontend health. Uses `docker-compose.yml` + `docker-compose.dev.yml`. |
| `prod.sh` | `bash scripts/prod.sh` | One-command **production** boot: runs `infra/validate_production_readiness.sh`, builds with `docker-compose.prod.yml`, waits for health, and verifies TLS when `DOMAIN` is a real domain. |
| `rebuild.sh` | `bash scripts/rebuild.sh <dev\|prod> [service]` | Rebuild and recreate one service (or the whole stack) without a full teardown. |
| `dev-restart-worker.sh` | `bash scripts/dev-restart-worker.sh` | Force-kill and restart only the `worker` container (dev) to pick up code changes instantly. |
| `clean_project.sh` | `bash scripts/clean_project.sh [--deep]` | Remove generated artifacts (caches, build outputs, temp dirs). `--deep` is more aggressive. Never touches tracked source. |
| `troubleshoot.sh` | `bash scripts/troubleshoot.sh` | Print a diagnostic bundle: docker/compose versions, container status, and tailed logs for unhealthy containers. |

## Verification / CI scripts

| Script | Usage | Purpose |
|--------|-------|---------|
| `verify_project.sh` | `./scripts/verify_project.sh <static\|backend\|frontend>` | All-phase verification entry point (lint, type-check, tests) used by CI and locally. |
| `validate_env_template_consistency.sh` | `bash scripts/validate_env_template_consistency.sh` | Assert `.env.example` and `.env.host.example` declare the same key set so neither template drifts. |
| `check_docs.py` | `python scripts/check_docs.py` | Documentation consistency checks. |
| `check_test_hygiene.py` | `python scripts/check_test_hygiene.py` | Test-suite hygiene checks (no skipped/oversized fixtures, etc.). |

## Host (non-Docker) runtime

Run from `apps/api` with `uv` (see the root [README](../README.md#host-app-development-with-docker-infrastructure)):

| Script | Purpose |
|--------|---------|
| `apps/api/scripts/init_db.py` | Create schema (Alembic) and seed bootstrap users. |
| `apps/api/scripts/run_api.py` | Start the FastAPI server in-process. |
| `apps/api/scripts/run_worker.py` | Start the forensic worker (Redis queue consumer). |

## Internal helpers (sourced, not run directly)

Prefixed with `_`; sourced by the lifecycle scripts above.

| Script | Purpose |
|--------|---------|
| `_config.sh` | Centralized timeouts and minimum version/resource thresholds. |
| `_platform_detect.sh` | Detect OS (linux/macos/windows), WSL2, and Docker Desktop context. |
| `_path_utils.sh` | Resolve project root and normalize host paths for Docker bind mounts. |
| `_docker_utils.sh` | Docker/Compose/BuildKit availability, version, disk, and memory checks. |
| `_validate_env.sh` | Unified `.env` validation (placeholders, required keys, invariants). |
| `_pre_build_validation.sh` | Aggregates the checks above into a single pre-build gate. |
| `_wait_healthy.sh` | Poll compose service health until ready (or timeout). |
| `_smoke.sh` | Curl `/lb-health`, `/health`, and the frontend through Caddy. |

## Related infra scripts

Live in [`infra/`](../infra/), not here:

| Script | Purpose |
|--------|---------|
| `infra/generate_production_keys.sh` | Generate high-entropy secrets; `--update` writes them into `.env`. |
| `infra/validate_production_readiness.sh` | Gate production deploys: tools, resources, `.env` invariants, compose config. |
| `infra/validate_repo_health.sh` | Repo health (lint/test) for CI / developer workstations — not required for deployment. |
