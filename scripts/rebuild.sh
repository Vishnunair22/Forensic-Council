#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
MODE="${1:-dev}"           # dev | prod
SVC="${2:-}"
FILES=(-f infra/docker-compose.yml)
[ "$MODE" = "prod" ] && FILES+=(-f infra/docker-compose.prod.yml)
echo "==> No-cache rebuild $SVC ($MODE)"
if [ -n "$SVC" ]; then
  docker compose "${FILES[@]}" --env-file .env build --no-cache "$SVC"
  docker compose "${FILES[@]}" --env-file .env up -d --no-deps "$SVC"
else
  docker compose "${FILES[@]}" --env-file .env build --no-cache
  docker compose "${FILES[@]}" --env-file .env up -d
fi
