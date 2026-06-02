#!/usr/bin/env bash
set -euo pipefail

# ── Load Utilities ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/_platform_detect.sh"
source "$SCRIPT_DIR/_path_utils.sh"
source "$SCRIPT_DIR/_docker_utils.sh"

# ── Setup ─────────────────────────────────────────────────────────────────────
ROOT=$(get_project_root)
cd "$ROOT"

PLATFORM=$(detect_platform)
DOCKER_CONTEXT=$(get_docker_context)

echo "  Platform: $PLATFORM (Docker: $DOCKER_CONTEXT)"

# ── Pre-flight Checks ─────────────────────────────────────────────────────────
bash "$SCRIPT_DIR/_pre_build_validation.sh" dev || exit 1

# ── Compose Command Array ─────────────────────────────────────────────────────
COMPOSE=(docker compose -f "$ROOT/infra/docker-compose.yml" -f "$ROOT/infra/docker-compose.dev.yml" --env-file "$ROOT/.env")

# ── Port Conflict Check ───────────────────────────────────────────────────────
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
    return 0
  fi

  if command -v docker >/dev/null 2>&1; then
    local mapped
    mapped=$(docker ps --filter "label=com.docker.compose.project=forensic-council" --format "{{.Ports}}" 2>/dev/null | grep -E "(:$port->|0\.0\.0\.0:$port->)" || echo "")
    if [[ -n "$mapped" ]]; then
      return 0
    fi
  fi
  return 1
}

REQUIRED_PORTS=(80 443 3000 5432 6379 8000)
PORT_CONFLICTS=()
for PORT in "${REQUIRED_PORTS[@]}"; do
  if ! check_port "$PORT"; then
    PORT_CONFLICTS+=("$PORT")
  fi
done

if [ ${#PORT_CONFLICTS[@]} -ne 0 ]; then
  echo "  Port conflict detected! The following ports are already in use on the host: ${PORT_CONFLICTS[*]}"
  echo "     Please stop any services running on these ports and re-run."
  exit 1
fi
echo "  Ports are free."

# ── Validate Environment ──────────────────────────────────────────────────────
source "$SCRIPT_DIR/_validate_env.sh"
validate_env "$ROOT/.env" "dev" || exit 1

# ── Build & Start ─────────────────────────────────────────────────────────────
echo "  Building images..."
"${COMPOSE[@]}" build --parallel

echo "  Starting services..."
"${COMPOSE[@]}" up -d

# ── Wait for API Health ───────────────────────────────────────────────────────
echo "  Waiting for API health through direct dev port 8000 (up to 45 min on first run)..."
TIMEOUT_SEC=2700
SLEEP_SEC=10
ELAPSED=0
DOWNLOAD_NOTED=0
STATUS=""
while [ $ELAPSED -lt $TIMEOUT_SEC ]; do
  STATUS=$(curl -sf http://localhost:8000/health 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null || echo "")
  if [[ "$STATUS" == "ok" ]]; then
    echo "  API healthy on http://localhost:8000 (after ${ELAPSED}s)"
    break
  fi
  if [ "$DOWNLOAD_NOTED" -eq 0 ] && "${COMPOSE[@]}" logs --tail 50 backend 2>/dev/null | grep -q "ML cache incomplete - downloading models"; then
    echo "  Backend is downloading ML models on first run — this can take 15-40 min."
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
  echo "  API did not become healthy in ${TIMEOUT_SEC}s."
  echo "   Run: ${COMPOSE[*]} logs backend"
  exit 1
fi

# ── Wait for Worker ───────────────────────────────────────────────────────────
echo "  Waiting for worker readiness (up to 5 min)..."
WORKER_OK=0
for i in $(seq 1 30); do
  if "${COMPOSE[@]}" exec -T worker python /app/scripts/worker_healthcheck.py > /dev/null 2>&1; then
    echo "  Worker healthy (after $((i * 10))s)"
    WORKER_OK=1
    break
  fi
  sleep 10
done
if [[ "$WORKER_OK" -eq 0 ]]; then
  echo "  Worker did not report healthy. Investigations will queue but may not process."
  echo "   Run: ${COMPOSE[*]} logs worker"
fi

# ── Verify ML Cache ───────────────────────────────────────────────────────────
echo "  Verifying ML model cache..."
if "${COMPOSE[@]}" exec -T backend python scripts/model_cache_check.py > /dev/null 2>&1; then
  echo "  ML model cache verified."
else
  echo "  ML model cache check failed or models still loading. First analysis may be slow."
fi

# ── Wait for Caddy Health ─────────────────────────────────────────────────────
echo "  Waiting for Caddy health route..."
for i in $(seq 1 12); do
  if curl -sf http://localhost/health > /dev/null 2>&1; then
    echo "  Caddy -> backend health route healthy"
    break
  fi
  if [[ $i -eq 12 ]]; then
    echo "  Caddy /health is not ready yet. Direct dev backend is healthy."
  fi
  sleep 5
done

# ── Wait for Frontend ─────────────────────────────────────────────────────────
echo "  Waiting for web (up to 60s)..."
for i in $(seq 1 12); do
  if curl -sf http://localhost:3000 > /dev/null 2>&1; then
    echo "  Web healthy"
    break
  fi
  [[ $i -eq 12 ]] && echo "  Web not yet responding (may still be building)"
  sleep 5
done

echo ""
echo "════════════════════════════════════════════════════════════════════════════"
echo "  Forensic Council — DEV running"
echo "  Web UI   -> http://localhost:3000"
echo "  API      -> http://localhost:8000"
echo "  API Docs -> http://localhost:8000/docs"
echo "  Health   -> http://localhost:8000/health"
echo "════════════════════════════════════════════════════════════════════════════"
echo "    Dev Tips:"
echo "     - Changing .env? Run: docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env up -d --force-recreate"
echo "     - Changing Worker code? Run: bash scripts/dev-restart-worker.sh (instantly restarts worker)"
echo "════════════════════════════════════════════════════════════════════════════"
