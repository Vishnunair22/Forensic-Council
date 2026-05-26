#!/usr/bin/env bash
# Forensic Council — Phase 1 build/run verification
#
# Usage:
#   ./scripts/verify_phase1_build_run.sh docker-dev   # build + smoke dev stack
#   ./scripts/verify_phase1_build_run.sh docker-prod  # build + smoke prod stack

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1" >&2; exit 1; }

MODE="${1:-docker-dev}"

# Shared smoke: wait for API health, worker health, and model cache.
smoke_stack() {
    COMPOSE_FILES=("$@")

    echo "  Building images..."
    docker compose "${COMPOSE_FILES[@]}" build --parallel || fail "Image build failed"

    echo "  Starting services..."
    docker compose "${COMPOSE_FILES[@]}" up -d || fail "docker compose up failed"

    echo "  Waiting for API health (up to 300s)..."
    for i in $(seq 1 60); do
        STATUS=$(docker compose "${COMPOSE_FILES[@]}" exec -T backend \
            wget -qO- http://localhost:8000/live 2>/dev/null | head -1 || echo "")
        [[ "$STATUS" == "ok" ]] && break
        [[ $i -eq 60 ]] && fail "API not healthy after 300s"
        sleep 5
    done
    pass "API health"

    echo "  Checking worker health..."
    docker compose "${COMPOSE_FILES[@]}" exec -T worker \
        python /app/scripts/worker_healthcheck.py || fail "Worker healthcheck failed"
    pass "Worker health"

    echo "  Verifying ML model cache..."
    docker compose "${COMPOSE_FILES[@]}" exec -T backend \
        python scripts/model_cache_check.py || fail "ML model cache check failed"
    pass "ML model cache"

    echo "  Tearing down..."
    docker compose "${COMPOSE_FILES[@]}" down
}

case "$MODE" in
  docker-dev)
    echo "=== Phase 1 docker-dev build/run ==="
    [[ -f "$ROOT/.env" ]] || fail ".env not found — run cp .env.example .env and fill secrets"
    smoke_stack \
        -f "$ROOT/infra/docker-compose.yml" \
        -f "$ROOT/infra/docker-compose.dev.yml" \
        --env-file "$ROOT/.env"
    pass "docker-dev"
    ;;
  docker-prod)
    echo "=== Phase 1 docker-prod build/run ==="
    [[ -f "$ROOT/.env" ]] || fail ".env not found"
    "$ROOT/infra/validate_production_readiness.sh"
    smoke_stack \
        -f "$ROOT/infra/docker-compose.yml" \
        -f "$ROOT/infra/docker-compose.prod.yml" \
        --env-file "$ROOT/.env"
    pass "docker-prod"
    ;;
  *)
    echo "Usage: $0 [docker-dev|docker-prod]" >&2
    exit 2
    ;;
esac
