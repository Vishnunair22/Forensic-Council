#!/usr/bin/env bash
# =============================================================================
# Forensic Council — Shell Manager (Linux / macOS)
#
# Usage:
#   ./manage.sh <command>
#
# Commands:
#   up               Build and start all services (detached)
#   dev              Start with hot-reload (mounts source into containers)
#   build            Build images without starting
#   down             Stop services, keep volumes
#   down-clean       Stop services AND wipe all volumes  ⚠️ destructive
#   logs             Follow logs from all services (Ctrl-C to exit)
#   prod             Start in production mode
#   infra            Start infrastructure services only (DB, Redis, Qdrant)
#   rebuild-backend  Rebuild and restart only the backend container
#   cache-status     List ML-model cache volumes
#   shell-backend    Open an interactive shell in the backend container
#   shell-frontend   Open an interactive shell in the frontend container
#   migrate          Run database migrations manually
#   init-db          Run the full database initialisation script
#   health           Query the /health endpoint (requires curl)
# =============================================================================

set -euo pipefail

COMPOSE_FILE="docs/docker/docker-compose.yml"
DEV_OVERRIDE="docs/docker/docker-compose.dev.yml"
PROD_OVERRIDE="docs/docker/docker-compose.prod.yml"
INFRA_COMPOSE="docs/docker/docker-compose.infra.yml"
ENV_FILE=".env"

# ── Helpers ──────────────────────────────────────────────────────────────────

_red()   { printf '\033[0;31m%s\033[0m\n' "$*"; }
_green() { printf '\033[0;32m%s\033[0m\n' "$*"; }
_cyan()  { printf '\033[0;36m%s\033[0m\n' "$*"; }
_yellow(){ printf '\033[0;33m%s\033[0m\n' "$*"; }

_require_env() {
    if [[ ! -f "$ENV_FILE" ]]; then
        _red "Missing $ENV_FILE file."
        echo "  Copy the template and configure it:"
        echo "    cp .env.example .env"
        exit 1
    fi
}

_compose() {
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
}

_compose_dev() {
    docker compose -f "$COMPOSE_FILE" -f "$DEV_OVERRIDE" --env-file "$ENV_FILE" "$@"
}

_compose_prod() {
    docker compose -f "$COMPOSE_FILE" -f "$PROD_OVERRIDE" --env-file "$ENV_FILE" "$@"
}

# ── Commands ─────────────────────────────────────────────────────────────────

cmd_up() {
    _require_env
    _cyan "Starting all services..."
    _compose up -d --build
}

cmd_dev() {
    _require_env
    _cyan "Starting with hot-reload enabled..."
    _compose_dev up -d --build
}

cmd_build() {
    _require_env
    _cyan "Building images..."
    _compose build
}

cmd_down() {
    _require_env
    _yellow "Stopping services (keeping volumes)..."
    _compose down
}

cmd_down_clean() {
    _require_env
    _red "Stopping services and wiping ALL volumes — this cannot be undone!"
    read -r -p "Are you sure? [y/N] " confirm
    if [[ "${confirm,,}" != "y" ]]; then
        echo "Aborted."
        exit 0
    fi
    _compose down -v
}

cmd_logs() {
    _require_env
    _cyan "Following logs (Ctrl-C to exit)..."
    _compose logs -f
}

cmd_prod() {
    _require_env
    _cyan "Starting production mode..."
    _compose_prod up -d --build
}

cmd_infra() {
    _require_env
    _cyan "Starting infrastructure services only (postgres, redis, qdrant)..."
    docker compose -f "$COMPOSE_FILE" -f "$INFRA_COMPOSE" --env-file "$ENV_FILE" up -d
}

cmd_rebuild_backend() {
    _require_env
    _yellow "Rebuilding backend only..."
    _compose build backend
    _compose up -d --no-deps backend
}

cmd_cache_status() {
    _cyan "ML Model Cache Volumes:"
    docker volume ls --filter "name=forensic-council"
}

cmd_shell_backend() {
    _require_env
    _cyan "Opening shell in backend container..."
    _compose exec backend bash
}

cmd_shell_frontend() {
    _require_env
    _cyan "Opening shell in frontend container..."
    _compose exec frontend sh
}

cmd_migrate() {
    _require_env
    _cyan "Running database migrations..."
    _compose exec backend python -m core.migrations
}

cmd_init_db() {
    _require_env
    _cyan "Running database initialisation..."
    _compose exec backend python scripts/init_db.py
}

cmd_health() {
    local port="${API_PORT:-8000}"
    _cyan "Querying health endpoint on port $port..."
    curl -sf "http://localhost:${port}/health" | python3 -m json.tool || {
        _red "Health check failed — is the API running?"
        exit 1
    }
}

# ── Entry-point ──────────────────────────────────────────────────────────────

COMMAND="${1:-}"

case "$COMMAND" in
    up)              cmd_up ;;
    dev)             cmd_dev ;;
    build)           cmd_build ;;
    down)            cmd_down ;;
    down-clean)      cmd_down_clean ;;
    logs)            cmd_logs ;;
    prod)            cmd_prod ;;
    infra)           cmd_infra ;;
    rebuild-backend) cmd_rebuild_backend ;;
    cache-status)    cmd_cache_status ;;
    shell-backend)   cmd_shell_backend ;;
    shell-frontend)  cmd_shell_frontend ;;
    migrate)         cmd_migrate ;;
    init-db)         cmd_init_db ;;
    health)          cmd_health ;;
    "")
        _red "No command specified."
        echo ""
        echo "Usage: ./manage.sh <command>"
        echo ""
        echo "Commands:"
        echo "  up               Build and start all services"
        echo "  dev              Start with hot-reload"
        echo "  build            Build images"
        echo "  down             Stop services (keep volumes)"
        echo "  down-clean       Stop services and wipe volumes  ⚠️"
        echo "  logs             Follow logs"
        echo "  prod             Start in production mode"
        echo "  infra            Start infrastructure only"
        echo "  rebuild-backend  Rebuild backend container"
        echo "  cache-status     List ML-model cache volumes"
        echo "  shell-backend    Shell into backend container"
        echo "  shell-frontend   Shell into frontend container"
        echo "  migrate          Run database migrations"
        echo "  init-db          Run database initialisation"
        echo "  health           Query /health endpoint"
        exit 1
        ;;
    *)
        _red "Unknown command: '$COMMAND'"
        echo "Run './manage.sh' with no arguments to see available commands."
        exit 1
        ;;
esac
