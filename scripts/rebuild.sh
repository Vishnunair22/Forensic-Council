#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
MODE="${1:-dev}"           # dev | prod
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

echo "==> No-cache rebuild ${SVC:-all services} ($MODE)"
if [ -n "$SVC" ]; then
  docker compose "${FILES[@]}" --env-file .env build --no-cache "$SVC"
  docker compose "${FILES[@]}" --env-file .env up -d --no-deps "$SVC"
else
  docker compose "${FILES[@]}" --env-file .env build --no-cache
  docker compose "${FILES[@]}" --env-file .env up -d
fi