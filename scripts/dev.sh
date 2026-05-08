#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || cp .env.example .env
echo "==> Building & starting DEV stack"
docker compose -f infra/docker-compose.yml --env-file .env up --build -d
echo "==> Waiting for health…"
./scripts/_wait_healthy.sh
echo "==> Running endpoint smoke checks"
./scripts/_smoke.sh
echo "==> DEV stack ready: http://localhost:80  (frontend), http://localhost:8000/health (api)"
