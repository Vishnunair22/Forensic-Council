#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/_path_utils.sh"
source "$SCRIPT_DIR/_docker_utils.sh"

ROOT=$(get_project_root)
cd "$ROOT"

COMPOSE=(docker compose -f "$ROOT/infra/docker-compose.yml" -f "$ROOT/infra/docker-compose.dev.yml" --env-file "$ROOT/.env")

check_docker_available || exit 1

echo "  Force-killing and restarting the worker for development..."
"${COMPOSE[@]}" kill -s SIGKILL worker
"${COMPOSE[@]}" up -d worker
echo "  Worker restarted."
