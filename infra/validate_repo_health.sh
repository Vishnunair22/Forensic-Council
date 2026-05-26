#!/usr/bin/env bash
set -euo pipefail

# Forensic Council — Repo Health Validator (CI / developer workstation only)
#
# Runs lint, type-check, tests, and pre-commit on the codebase.
# Requires: npm, uv, pre-commit installed on the host.
#
# NOT a deployment gate. prod.sh calls validate_production_readiness.sh instead.
# Call this from CI pipelines or before opening a PR.
#
# Usage:
#   ./infra/validate_repo_health.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "--- Forensic Council: Repo Health Check ($ROOT) ---"

PASS=0
FAIL=0
SKIP=0

run_check() {
    LABEL="$1"
    shift
    if "$@"; then
        echo "  OK: $LABEL"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $LABEL"
        FAIL=$((FAIL + 1))
    fi
}

# pre-commit
if command -v pre-commit >/dev/null 2>&1; then
    echo "[pre-commit] Running pre-commit checks..."
    run_check "pre-commit" pre-commit run --all-files
else
    echo "  SKIP: pre-commit not installed"
    SKIP=$((SKIP + 1))
fi

# Frontend
if command -v npm >/dev/null 2>&1 && [ -f "$ROOT/apps/web/package.json" ]; then
    echo "[frontend] Installing dependencies..."
    (cd "$ROOT/apps/web" && npm ci --prefer-offline --no-audit --no-fund)
    run_check "frontend type-check" sh -c "cd '$ROOT/apps/web' && npm run type-check"
    run_check "frontend lint"       sh -c "cd '$ROOT/apps/web' && npm run lint"
    run_check "frontend tests"      sh -c "cd '$ROOT/apps/web' && npm run test -- --runInBand"
    run_check "frontend build"      sh -c "cd '$ROOT/apps/web' && npm run build"
else
    echo "  SKIP: npm not installed or apps/web/package.json missing"
    SKIP=$((SKIP + 1))
fi

# Backend
if command -v uv >/dev/null 2>&1 && [ -f "$ROOT/apps/api/pyproject.toml" ]; then
    echo "[backend] Running backend checks..."
    run_check "backend ruff"    sh -c "cd '$ROOT/apps/api' && uv run ruff check ."
    run_check "backend pyright" sh -c "cd '$ROOT/apps/api' && uv run pyright"
else
    echo "  SKIP: uv not installed or apps/api/pyproject.toml missing"
    SKIP=$((SKIP + 1))
fi

echo "----------------------------------------------------"
echo "Repo health: PASS=$PASS  FAIL=$FAIL  SKIP=$SKIP"
echo "----------------------------------------------------"
[ "$FAIL" -eq 0 ] || { echo "One or more checks failed."; exit 1; }
echo "SUCCESS: All repo health checks passed."
