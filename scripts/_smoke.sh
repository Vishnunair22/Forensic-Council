#!/usr/bin/env bash
set -euo pipefail
echo "GET /health"; curl -fsS http://localhost:8000/health | head -c 400; echo
echo "GET /lb-health (caddy)"; curl -fsS http://localhost:80/lb-health
echo "GET / (frontend)";       curl -fsS -o /dev/null -w "%{http_code}\n" http://localhost:3000/
echo "POST /api/v1/auth/login (demo)"; \
  curl -fsS -X POST http://localhost:80/api/auth/demo -H 'Content-Type: application/json' -d '{}' | head -c 200; echo
