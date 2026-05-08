#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "FATAL: .env missing. Run infra/generate_production_keys.sh"; exit 1; }
./infra/validate_production_readiness.sh
echo "==> Building & starting PROD stack"
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file .env up --build -d
./scripts/_wait_healthy.sh
./scripts/_smoke.sh
echo "==> PROD stack ready"
