#!/usr/bin/env bash
set -euo pipefail

# ── Forensic Council — One-Command Production Boot ────────────────────────────
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
COMPOSE="docker compose -f $ROOT/infra/docker-compose.yml -f $ROOT/infra/docker-compose.prod.yml --env-file $ROOT/.env"

echo "🔍 Checking .env..."
[[ -f "$ROOT/.env" ]] || { echo "ERROR: .env not found. Run ./infra/generate_production_keys.sh"; exit 1; }

echo "🔐 Running production readiness validation..."
"$ROOT/infra/validate_production_readiness.sh"

echo "🐳 Building production images..."
$COMPOSE build --parallel

echo "🚀 Starting production services..."
$COMPOSE up -d

echo "⏳ Waiting for API health (up to 120s)..."
for i in $(seq 1 24); do
  STATUS=$(curl -sf http://localhost/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null || echo "")
  if [[ "$STATUS" == "ok" ]]; then
    echo "✅ API healthy"
    break
  fi
  if [[ $i -eq 24 ]]; then
    echo "❌ API did not become healthy in 120s."
    echo "   Run: docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml logs backend"
    exit 1
  fi
  echo "   Attempt $i/24 — waiting..."
  sleep 5
done

echo ""
echo "════════════════════════════════════════"
echo "  Forensic Council — PRODUCTION running"
echo "  Web UI  → https://$(grep '^DOMAIN=' "$ROOT/.env" | cut -d= -f2 || echo 'localhost')"
echo "  Health  → http://localhost/health"
echo "════════════════════════════════════════"
