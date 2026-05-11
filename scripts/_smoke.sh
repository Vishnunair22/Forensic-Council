#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-dev}"

echo "Smoke mode: $MODE"
echo ""
echo "GET /lb-health through Caddy"
curl -fsS http://localhost/lb-health
echo
echo ""
echo "GET /health through Caddy"
curl -fsS http://localhost/health | head -c 500
echo
echo ""
echo "GET / frontend through Caddy"
curl -fsS -o /dev/null -w "%{http_code}\n" http://localhost/

if [[ "$MODE" == "dev" ]]; then
  echo ""
  echo "GET /health through direct dev backend"
  curl -fsS http://localhost:8000/health | head -c 500
  echo
  echo ""
  echo "GET / frontend through direct dev Next server"
  curl -fsS -o /dev/null -w "%{http_code}\n" http://localhost:3000/
fi

echo ""
echo "POST /api/auth/demo through frontend/Caddy"
curl -fsS \
  -X POST http://localhost/api/auth/demo \
  -H 'Content-Type: application/json' \
  -d '{}' | head -c 500
echo