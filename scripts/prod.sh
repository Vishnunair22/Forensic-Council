#!/usr/bin/env bash
set -euo pipefail

# ── Forensic Council — One-Command Production Boot ────────────────────────────
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
COMPOSE=(docker compose -f "$ROOT/infra/docker-compose.yml" -f "$ROOT/infra/docker-compose.prod.yml" --env-file "$ROOT/.env")

echo "🔍 Checking .env..."
[[ -f "$ROOT/.env" ]] || { echo "ERROR: .env not found. Run ./infra/generate_production_keys.sh"; exit 1; }

echo "🔐 Running production readiness validation..."
"$ROOT/infra/validate_production_readiness.sh"

echo "🐳 Building production images..."
"${COMPOSE[@]}" build --parallel

echo "🚀 Starting production services..."
"${COMPOSE[@]}" up -d

DOMAIN_VALUE="$(grep '^DOMAIN=' "$ROOT/.env" | cut -d= -f2- || echo 'localhost')"
CADDY_SITE_ADDRESS_VALUE="$(grep '^CADDY_SITE_ADDRESS=' "$ROOT/.env" | cut -d= -f2- || true)"

if [[ -n "$CADDY_SITE_ADDRESS_VALUE" ]]; then
  HEALTH_URL="${CADDY_SITE_ADDRESS_VALUE%/}/health"
elif [[ "$DOMAIN_VALUE" == "localhost" ]]; then
  HEALTH_URL="http://localhost/health"
else
  HEALTH_URL="https://${DOMAIN_VALUE}/health"
fi

echo "⏳ Waiting for API health (up to 600s)..."
for i in $(seq 1 120); do
  STATUS=$(curl -sf "$HEALTH_URL" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null || echo "")
  if [[ "$STATUS" == "ok" ]]; then
    echo "✅ API healthy"
    break
  fi
  if [[ $i -eq 120 ]]; then
    echo "❌ API did not become healthy in 600s."
    echo "   Run: docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml logs backend"
    exit 1
  fi
  echo "   Attempt $i/120 — waiting..."
  sleep 5
done

echo ""
echo "════════════════════════════════════════"
echo "  Forensic Council — PRODUCTION running"
echo "  Web UI  → ${HEALTH_URL%/health}"
echo "  Health  → $HEALTH_URL"
echo "════════════════════════════════════════"
