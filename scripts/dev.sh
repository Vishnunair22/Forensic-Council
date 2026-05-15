#!/usr/bin/env bash
set -euo pipefail

# ── Forensic Council — One-Command Dev Boot ───────────────────────────────────
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
COMPOSE="docker compose -f $ROOT/infra/docker-compose.yml -f $ROOT/infra/docker-compose.dev.yml --env-file $ROOT/.env"

echo "🔍 Checking .env..."
if [[ ! -f "$ROOT/.env" ]]; then
  echo "  .env not found — copying from .env.example..."
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "  ⚠️  Please edit .env and fill in your API keys before continuing."
  echo "  Then re-run: ./scripts/dev.sh"
  exit 1
fi

# Fail-fast check for required local environment variables
REQUIRED_DEV_VARS=(
  SIGNING_KEY
  JWT_SECRET_KEY
  POSTGRES_PASSWORD
  REDIS_PASSWORD
  BOOTSTRAP_ADMIN_PASSWORD
  BOOTSTRAP_INVESTIGATOR_PASSWORD
  DEMO_PASSWORD
  METRICS_SCRAPE_TOKEN
  GEMINI_API_KEY_POLICY_OK
)

for VAR in "${REQUIRED_DEV_VARS[@]}"; do
  VAL=$(grep "^$VAR=" "$ROOT/.env" | cut -d= -f2- || echo "")
  if [[ -z "$VAL" || "$VAL" == __REPLACE_ME* || "$VAL" == __PASTE_* ]]; then
    echo "  ❌ $VAR is missing or still a placeholder in .env"
    exit 1
  fi
done

# GEMINI_API_KEY_POLICY_OK must be exactly 'true' or 'false'. Docker compose
# enforces presence via :? but not shape — fail here with a clear message.
POLICY_VAL=$(grep "^GEMINI_API_KEY_POLICY_OK=" "$ROOT/.env" | cut -d= -f2- || echo "")
case "$POLICY_VAL" in
  true|false) ;;
  *)
    echo "  ❌ GEMINI_API_KEY_POLICY_OK must be exactly 'true' or 'false' (got: '$POLICY_VAL')"
    echo "     See .env.example — set to 'true' only after reading https://ai.google.dev/terms."
    exit 1
    ;;
esac

LLM_PROVIDER_VALUE=$(grep "^LLM_PROVIDER=" "$ROOT/.env" | cut -d= -f2- || echo "groq")
LLM_KEY_VALUE=$(grep "^LLM_API_KEY=" "$ROOT/.env" | cut -d= -f2- || echo "")
if [[ "$LLM_PROVIDER_VALUE" != "none" && ( -z "$LLM_KEY_VALUE" || "$LLM_KEY_VALUE" == __PASTE_* ) ]]; then
  echo "  ❌ LLM_PROVIDER=$LLM_PROVIDER_VALUE but LLM_API_KEY is not set"
  echo "     Set LLM_API_KEY in .env, or set LLM_PROVIDER=none for local fallback mode."
  exit 1
fi

echo "✅ .env validation passed."

echo "🐳 Building images..."
$COMPOSE build --parallel

echo "🚀 Starting services..."
$COMPOSE up -d

# PRELOAD_MODELS=1 (default) bakes models into the image. When the build
# cache is cold or volumes are empty, first-start can download several GB.
# Default budget is 30 min; we surface a banner if download is detected.
echo "⏳ Waiting for API health through direct dev port (up to 30 min on first run)..."
TIMEOUT_SEC=1800
SLEEP_SEC=10
ELAPSED=0
DOWNLOAD_NOTED=0
STATUS=""
while [ $ELAPSED -lt $TIMEOUT_SEC ]; do
  STATUS=$(curl -sf http://localhost:8000/health 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null || echo "")
  if [[ "$STATUS" == "ok" ]]; then
    echo "✅ API healthy on http://localhost:8000 (after ${ELAPSED}s)"
    break
  fi
  if [ "$DOWNLOAD_NOTED" -eq 0 ] && $COMPOSE logs --tail 50 backend 2>/dev/null | grep -q "ML cache incomplete - downloading models"; then
    echo "ℹ  Backend is downloading ML models on first run — this can take 15–40 min."
    DOWNLOAD_NOTED=1
  fi
  ELAPSED=$((ELAPSED + SLEEP_SEC))
  if [ $((ELAPSED % 60)) -eq 0 ]; then
    echo "   …waited ${ELAPSED}s; still not healthy."
  fi
  sleep $SLEEP_SEC
done
if [[ "$STATUS" != "ok" ]]; then
  echo "❌ API did not become healthy in ${TIMEOUT_SEC}s."
  echo "   Run: $COMPOSE logs backend"
  exit 1
fi
echo "⏳ Waiting for Caddy health route..."
for i in $(seq 1 12); do
  if curl -sf http://localhost/health > /dev/null 2>&1; then
    echo "✅ Caddy -> backend health route healthy"
    break
  fi
  if [[ $i -eq 12 ]]; then
    echo "⚠️  Caddy /health is not ready yet. Direct dev backend is healthy."
  fi
  sleep 5
done

echo "⏳ Waiting for web (up to 60s)..."
for i in $(seq 1 12); do
  if curl -sf http://localhost:3000 > /dev/null 2>&1; then
    echo "✅ Web healthy"
    break
  fi
  [[ $i -eq 12 ]] && echo "⚠️  Web not yet responding (may still be building)"
  sleep 5
done

echo ""
echo "════════════════════════════════════════"
echo "  Forensic Council — DEV running"
echo "  Web UI   → http://localhost:3000"
echo "  API      → http://localhost:8000"
echo "  API Docs → http://localhost:8000/docs"
echo "  Health   → http://localhost:8000/health"
echo "════════════════════════════════════════"
