#!/usr/bin/env bash
# Forensic Council — Flush Persistent State
#
# Removes persistent Docker volumes (Redis cache, Postgres DB, Qdrant vectors).
# Use this when "old fixed bugs" resurface due to cached pipeline outputs.
#
# Usage:
#   bash scripts/flush_state.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

echo "=== Forensic Council — Flushing Persistent State ==="
echo "WARNING: This will destroy all investigation history and cached reports!"
echo "Press Ctrl+C to abort or wait 5 seconds..."
sleep 5

docker compose -f infra/docker-compose.yml down -v

echo "Volumes removed. Next 'docker compose up' will start with a completely fresh state."
