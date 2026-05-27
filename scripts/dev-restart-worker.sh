#!/usr/bin/env bash
set -euo pipefail

# Forensic Council — Worker Quick Restart Script
# Bypasses the 300s stop grace period for instant code hot-reloading in dev.

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE=(docker compose -f "$ROOT/infra/docker-compose.yml" -f "$ROOT/infra/docker-compose.dev.yml" --env-file "$ROOT/.env")

echo "⚡ Force-killing and restarting the worker for development..."
"${COMPOSE[@]}" kill -s SIGKILL worker
"${COMPOSE[@]}" up -d worker
echo "✅ Worker restarted."
