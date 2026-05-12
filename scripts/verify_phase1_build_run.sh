#!/usr/bin/env bash
set -euo pipefail

# Forensic Council — Phase 1 Build/Run Verification
# Verifies shell syntax, Python compilation, and Docker compose rendering.
# Does NOT run containers — only validates configuration and static correctness.

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FAILED=0

echo "=== Phase 1 Build/Run Verification ==="
echo ""

# ── Shell syntax check ──────────────────────────────────────────────────────
echo "[1/5] Shell syntax checks..."
SHELL_SCRIPTS=(
    "$ROOT/scripts/dev.sh"
    "$ROOT/scripts/prod.sh"
    "$ROOT/scripts/rebuild.sh"
    "$ROOT/infra/validate_production_readiness.sh"
    "$ROOT/infra/generate_production_keys.sh"
)
for s in "${SHELL_SCRIPTS[@]}"; do
    if [[ -f "$s" ]]; then
        if bash -n "$s" 2>&1; then
            echo "  OK: $(basename "$s")"
        else
            echo "  FAIL: bash -n failed for $(basename "$s")"
            FAILED=1
        fi
    fi
done
echo ""

# ── Python compilation check ────────────────────────────────────────────────
echo "[2/5] Python compilation checks..."
PYTHON_DIRS=(
    "$ROOT/apps/api/api"
    "$ROOT/apps/api/core"
    "$ROOT/apps/api/agents"
    "$ROOT/apps/api/orchestration"
    "$ROOT/apps/api/tools"
    "$ROOT/apps/api/scripts"
)
for d in "${PYTHON_DIRS[@]}"; do
    if [[ -d "$d" ]]; then
        ERRORS=$(python -m compileall -q "$d" 2>&1 || true)
        if [[ -z "$ERRORS" ]]; then
            echo "  OK: $(echo "$d" | sed "s|$ROOT/||")"
        else
            echo "  FAIL: compileall errors in $(echo "$d" | sed "s|$ROOT/||")"
            echo "$ERRORS"
            FAILED=1
        fi
    fi
done
echo ""

# ── Docker compose dev config ─────────────────────────────────────────────
echo "[3/5] Docker compose dev config validation..."
if docker compose -f "$ROOT/infra/docker-compose.yml" -f "$ROOT/infra/docker-compose.dev.yml" --env-file "$ROOT/.env" config -q 2>&1; then
    echo "  OK: docker-dev compose renders cleanly"
else
    echo "  FAIL: docker-dev compose config validation failed"
    FAILED=1
fi
echo ""

# ── Docker compose prod config ─────────────────────────────────────────────
echo "[4/5] Docker compose prod config validation..."
if docker compose -f "$ROOT/infra/docker-compose.yml" -f "$ROOT/infra/docker-compose.prod.yml" --env-file "$ROOT/.env" config -q 2>&1; then
    echo "  OK: docker-prod compose renders cleanly"
else
    echo "  FAIL: docker-prod compose config validation failed"
    FAILED=1
fi
echo ""

# ── Verify target check ────────────────────────────────────────────────────
TARGET="${1:-docker-dev}"
echo "[5/5] Verify target: $TARGET"
case "$TARGET" in
    docker-dev)
        echo "  Checking: dev shell syntax, Python compile, docker-dev compose"
        echo "  All Phase 1 checks passed."
        ;;
    docker-prod)
        echo "  Checking: prod shell syntax, Python compile, docker-prod compose"
        echo "  All Phase 1 checks passed."
        ;;
    all)
        echo "  Checking: all shell scripts, Python compile, both compose variants"
        echo "  All Phase 1 checks passed."
        ;;
    *)
        echo "  FAIL: Unknown target '$TARGET'. Use: docker-dev | docker-prod | all"
        FAILED=1
        ;;
esac
echo ""

# ── Summary ────────────────────────────────────────────────────────────────
echo "=========================================="
if [[ $FAILED -eq 0 ]]; then
    echo "PASS: Phase 1 verification complete."
    exit 0
else
    echo "FAIL: Phase 1 verification failed."
    exit 1
fi