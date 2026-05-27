#!/usr/bin/env bash
set -euo pipefail

# ── Forensic Council — One-Command Dev Boot ───────────────────────────────────
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
COMPOSE=(docker compose -f "$ROOT/infra/docker-compose.yml" -f "$ROOT/infra/docker-compose.dev.yml" --env-file "$ROOT/.env")

# Pre-flight port check
check_port() {
  local port="$1"
  local in_use=0
  if (echo > /dev/tcp/127.0.0.1/"$port") 2>/dev/null; then
    in_use=1
  elif command -v lsof >/dev/null 2>&1; then
    lsof -i :"$port" >/dev/null 2>&1 && in_use=1
  elif command -v netstat >/dev/null 2>&1; then
    netstat -an | grep -qE "[\.:]$port " >/dev/null 2>&1 && in_use=1
  fi

  if [ "$in_use" -eq 0 ]; then
    return 0 # Free
  fi

  # Check if owned by our own containers
  if command -v docker >/dev/null 2>&1; then
    local mapped
    mapped=$(docker ps --filter "label=com.docker.compose.project=forensic-council" --format "{{.Ports}}" 2>/dev/null | grep -E "(:$port->|0\.0\.0\.0:$port->)" || echo "")
    if [[ -n "$mapped" ]]; then
      return 0 # Occupied by our own project
    fi
  fi
  return 1 # Occupied by something else
}

echo "🔍 Checking for port conflicts..."
REQUIRED_PORTS=(80 443 3000 5432 6379 8000)
PORT_CONFLICTS=()
for PORT in "${REQUIRED_PORTS[@]}"; do
  if ! check_port "$PORT"; then
    PORT_CONFLICTS+=("$PORT")
  fi
done

if [ ${#PORT_CONFLICTS[@]} -ne 0 ]; then
  echo "  ❌ Port conflict detected! The following ports are already in use on the host: ${PORT_CONFLICTS[*]}"
  echo "     Please stop any services running on these ports and re-run."
  exit 1
fi
echo "✅ Ports are free."

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
  QDRANT_API_KEY
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

# Validate that DEMO_PASSWORD matches BOOTSTRAP_INVESTIGATOR_PASSWORD
INVESTIGATOR_PWD=$(grep "^BOOTSTRAP_INVESTIGATOR_PASSWORD=" "$ROOT/.env" | cut -d= -f2-)
DEMO_PWD=$(grep "^DEMO_PASSWORD=" "$ROOT/.env" | cut -d= -f2-)
if [[ "$INVESTIGATOR_PWD" != "$DEMO_PWD" ]]; then
  echo "  ❌ BOOTSTRAP_INVESTIGATOR_PASSWORD must exactly match DEMO_PASSWORD in .env"
  echo "     (For local development, 'Begin Analysis' auto-login relies on this match)"
  exit 1
fi

echo "✅ .env validation passed."

echo "🐳 Building images..."
"${COMPOSE[@]}" build --parallel

echo "🚀 Starting services..."
"${COMPOSE[@]}" up -d

# PRELOAD_MODELS=1 (default) bakes models into the image. When the build
# cache is cold or volumes are empty, first-start can download several GB.
# Default budget is 30 min; we surface a banner if download is detected.
# NOTE: Port 8000 is exposed only when the development overlay (docker-compose.dev.yml) is used.
# Since dev.sh always includes the dev overlay, this direct port check works.
echo "⏳ Waiting for API health through direct dev port 8000 (up to 45 min on first run)..."
TIMEOUT_SEC=2700
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
  if [ "$DOWNLOAD_NOTED" -eq 0 ] && "${COMPOSE[@]}" logs --tail 50 backend 2>/dev/null | grep -q "ML cache incomplete - downloading models"; then
    echo "ℹ  Backend is downloading ML models on first run — this can take 15–40 min."
    DOWNLOAD_NOTED=1
  fi
  ELAPSED=$((ELAPSED + SLEEP_SEC))
  if [ $((ELAPSED % 60)) -eq 0 ]; then
    echo "   …waited ${ELAPSED}s; still not healthy."
    echo "   --- Recent backend logs ---"
    "${COMPOSE[@]}" logs --tail 5 backend 2>/dev/null || true
    echo "   --------------------------"
  fi
  sleep $SLEEP_SEC
done
if [[ "$STATUS" != "ok" ]]; then
  echo "❌ API did not become healthy in ${TIMEOUT_SEC}s."
  echo "   Run: docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml logs backend"
  exit 1
fi

echo "⏳ Waiting for worker readiness (up to 5 min)..."
WORKER_OK=0
for i in $(seq 1 30); do
  if "${COMPOSE[@]}" exec -T worker python /app/scripts/worker_healthcheck.py > /dev/null 2>&1; then
    echo "✅ Worker healthy (after $((i * 10))s)"
    WORKER_OK=1
    break
  fi
  sleep 10
done
if [[ "$WORKER_OK" -eq 0 ]]; then
  echo "⚠️  Worker did not report healthy. Investigations will queue but may not process."
  echo "   Run: docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml logs worker"
fi

echo "⏳ Verifying ML model cache..."
if "${COMPOSE[@]}" exec -T backend python scripts/model_cache_check.py > /dev/null 2>&1; then
  echo "✅ ML model cache verified."
else
  echo "⚠️  ML model cache check failed or models still loading. First analysis may be slow."
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
echo "════════════════════════════════════════════════════════════════════════════"
echo "  Forensic Council — DEV running"
echo "  Web UI   → http://localhost:3000"
echo "  API      → http://localhost:8000"
echo "  API Docs → http://localhost:8000/docs"
echo "  Health   → http://localhost:8000/health"
echo "════════════════════════════════════════════════════════════════════════════"
echo "  💡 Dev Tips:"
echo "     - Changing .env? Run: docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env up -d --force-recreate"
echo "     - Changing Worker code? Run: bash scripts/dev-restart-worker.sh (instantly restarts worker)"
echo "════════════════════════════════════════════════════════════════════════════"
