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
echo "  Running pre-flight checks..."

bash "$SCRIPT_DIR/_pre_build_validation.sh" prod || exit 1

# ── Compose Command Array ─────────────────────────────────────────────────────
COMPOSE=(docker compose -f "$ROOT/infra/docker-compose.yml" -f "$ROOT/infra/docker-compose.prod.yml" --env-file "$ROOT/.env")

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

echo "  Checking for port conflicts..."
REQUIRED_PORTS=(80 443)
PORT_CONFLICTS=()
for PORT in "${REQUIRED_PORTS[@]}"; do
  if ! check_port "$PORT"; then
    PORT_CONFLICTS+=("$PORT")
  fi
done

if [ ${#PORT_CONFLICTS[@]} -ne 0 ]; then
  echo "  Port conflict detected! The following ports are already in use: ${PORT_CONFLICTS[*]}"
  exit 1
fi
echo "  Ports are free."

# ── Validate Environment ──────────────────────────────────────────────────────
source "$SCRIPT_DIR/_validate_env.sh"
validate_env "$ROOT/.env" "prod" || exit 1

echo "  Running production readiness validation..."
"$ROOT/infra/validate_production_readiness.sh"

# ── Warn about PRELOAD_MODELS ────────────────────────────────────────────────
PRELOAD_VAL=$(grep "^PRELOAD_MODELS=" "$ROOT/.env" 2>/dev/null | cut -d= -f2- || true)
# Compose's prod overlay defaults PRELOAD_MODELS to 1 when unset — mirror that
# here so an absent key still triggers the large-build warning.
[[ -z "$PRELOAD_VAL" ]] && PRELOAD_VAL="1"
if [[ "$PRELOAD_VAL" == "1" ]]; then
  echo "  WARNING: PRELOAD_MODELS=1 is enabled in .env."
  echo "   This will bake all ML models (YOLO, CLIP, EasyOCR, ECAPA, etc.) into the Docker image."
  echo "   The build size will be extremely large (15-40 GB) and can take 20-40 minutes on first run."
  echo "   Please ensure you have sufficient disk space and network bandwidth."
  echo "----------------------------------------------------------------------------------"
fi

# ── Build & Start ─────────────────────────────────────────────────────────────
echo "  Building production images..."
"${COMPOSE[@]}" build --parallel

echo "  Starting production services..."
"${COMPOSE[@]}" up -d

# ── Wait for API Health ───────────────────────────────────────────────────────
DOMAIN_VALUE="$(grep '^DOMAIN=' "$ROOT/.env" | cut -d= -f2- || echo 'localhost')"
CADDY_SITE_ADDRESS_VALUE="$(grep '^CADDY_SITE_ADDRESS=' "$ROOT/.env" | cut -d= -f2- || true)"

if [[ -n "$CADDY_SITE_ADDRESS_VALUE" ]]; then
  HEALTH_URL="${CADDY_SITE_ADDRESS_VALUE%/}/health"
elif [[ "$DOMAIN_VALUE" == "localhost" ]]; then
  HEALTH_URL="http://localhost/health"
else
  HEALTH_URL="https://${DOMAIN_VALUE}/health"
fi

echo "  Waiting for API health (up to 600s)..."
for i in $(seq 1 120); do
  # Parse with grep, not python3 — Git Bash on Windows (a documented supported
  # shell) ships neither python3 nor jq.
  if curl -sf "$HEALTH_URL" 2>/dev/null | grep -qE '"status"[[:space:]]*:[[:space:]]*"ok"'; then
    STATUS="ok"
  else
    STATUS=""
  fi
  if [[ "$STATUS" == "ok" ]]; then
    echo "  API healthy"
    break
  fi
  if [[ $i -eq 120 ]]; then
    echo "  API did not become healthy in 600s."
    echo "   Run: ${COMPOSE[*]} logs backend"
    exit 1
  fi
  echo "   Attempt $i/120 — waiting..."
  sleep 5
done

# ── Wait for Worker ───────────────────────────────────────────────────────────
echo "  Waiting for worker readiness (up to 5 min)..."
WORKER_OK=0
for i in $(seq 1 30); do
  if "${COMPOSE[@]}" exec -T worker python /app/scripts/worker_healthcheck.py > /dev/null 2>&1; then
    echo "  Worker healthy"
    WORKER_OK=1
    break
  fi
  sleep 10
done
if [[ "$WORKER_OK" -eq 0 ]]; then
  echo "  Worker did not report healthy. Check logs before accepting investigations."
  echo "   Run: ${COMPOSE[*]} logs worker"
fi

# ── Verify ML Cache ───────────────────────────────────────────────────────────
echo "  Verifying ML model cache..."
if "${COMPOSE[@]}" exec -T backend python scripts/model_cache_check.py > /dev/null 2>&1; then
  echo "  ML model cache verified."
else
  echo "  ML model cache check failed. First analysis may trigger a slow model download."
fi

# ── TLS Verification ──────────────────────────────────────────────────────────
if [[ "$DOMAIN_VALUE" != "localhost" && "$HEALTH_URL" == https://* ]]; then
  echo "  Verifying TLS certificate for $DOMAIN_VALUE..."
  TLS_READY=0
  for i in $(seq 1 30); do
    if curl -s -I "$HEALTH_URL" > /dev/null 2>&1; then
      echo "  TLS certificate verified (valid CA-signed certificate active)."
      TLS_READY=1
      break
    fi
    echo "   TLS provisioning in progress (Caddy is acquiring ACME cert)..."
    sleep 5
  done
  if [[ "$TLS_READY" -eq 0 ]]; then
    echo "  WARNING: Caddy is still provisioning the Let's Encrypt TLS certificate."
    echo "   Browsers may show a security warning until ACME issuance completes."
  fi
fi

echo ""
echo "════════════════════════════════════════"
echo "  Forensic Council — PRODUCTION running"
echo "  Web UI  -> ${HEALTH_URL%/health}"
echo "  Health  -> $HEALTH_URL"
echo "════════════════════════════════════════"
echo "  CAUTION: Running 'docker compose down -v' will permanently destroy the"
echo "     database volume, deleting the ECDSA signing keys and making all historical"
echo "     forensic report signatures unverifiable. See docs/OPERATIONAL_RUNBOOK.md"
echo "     for backup and restore runbooks."
echo "════════════════════════════════════════"
