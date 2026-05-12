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
  VAL=$(grep "^${VAR}=" "$ROOT/.env" 2>/dev/null | cut -d= -f2- || echo "")
  if [[ -z "$VAL" || "$VAL" == *"REPLACE"* || "$VAL" == *"placeholder"* || "$VAL" == __PASTE_* ]]; then
    echo "  ❌ $VAR is missing or still a placeholder in .env"
    echo "     Run: ./infra/generate_production_keys.sh --update"
    echo "     Then add free-tier LLM/Gemini keys or set LLM_PROVIDER=none and GEMINI_API_KEY_POLICY_OK=false for local fallback mode."
    exit 1
  fi
done

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

echo "⏳ Waiting for API health through direct dev port (up to 120s)..."
for i in $(seq 1 24); do
  STATUS=$(curl -sf http://localhost:8000/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null || echo "")
  if [[ "$STATUS" == "ok" ]]; then
    echo "✅ API healthy on http://localhost:8000"
    break
  fi
  if [[ $i -eq 24 ]]; then
    echo "❌ API did not become healthy on localhost:8000."
    echo "   Run: docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env logs backend"
    exit 1
  fi
  echo "   Attempt $i/24 — waiting..."
  sleep 5
done
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
