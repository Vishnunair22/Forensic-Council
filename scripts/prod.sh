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

echo "⏳ Waiting for worker readiness (up to 5 min)..."
WORKER_OK=0
for i in $(seq 1 30); do
  if "${COMPOSE[@]}" exec -T worker python /app/scripts/worker_healthcheck.py > /dev/null 2>&1; then
    echo "✅ Worker healthy"
    WORKER_OK=1
    break
  fi
  sleep 10
done
if [[ "$WORKER_OK" -eq 0 ]]; then
  echo "⚠️  Worker did not report healthy. Check logs before accepting investigations."
  echo "   Run: docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml logs worker"
fi

echo "⏳ Verifying ML model cache..."
if "${COMPOSE[@]}" exec -T backend python scripts/model_cache_check.py > /dev/null 2>&1; then
  echo "✅ ML model cache verified."
else
  echo "⚠️  ML model cache check failed. First analysis may trigger a slow model download."
fi

echo ""
echo "════════════════════════════════════════"
echo "  Forensic Council — PRODUCTION running"
echo "  Web UI  → ${HEALTH_URL%/health}"
echo "  Health  → $HEALTH_URL"
echo "════════════════════════════════════════"
