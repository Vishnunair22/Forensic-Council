#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/_path_utils.sh"
source "$SCRIPT_DIR/_docker_utils.sh"

ROOT=$(get_project_root)
cd "$ROOT"

MODE="${1:-dev}"
SVC="${2:-}"
FILES=(-f infra/docker-compose.yml)

case "$MODE" in
  dev)
    FILES+=(-f infra/docker-compose.dev.yml)
    ;;
  prod)
    FILES+=(-f infra/docker-compose.prod.yml)
    ;;
  *)
    echo "Usage: $0 [dev|prod] [service]" >&2
    exit 2
    ;;
esac

check_docker_available || exit 1

echo "==> Cleaning stale artifacts to prevent ghost bytecode regressions..."
bash "$SCRIPT_DIR/clean_project.sh"

echo "==> No-cache rebuild ${SVC:-all services} ($MODE)"
if [ -n "$SVC" ]; then
  docker compose "${FILES[@]}" --env-file .env build --no-cache "$SVC"
  docker compose "${FILES[@]}" --env-file .env up -d --no-deps "$SVC"
else
  docker compose "${FILES[@]}" --env-file .env build --no-cache
  docker compose "${FILES[@]}" --env-file .env up -d
fi
