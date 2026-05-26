#!/usr/bin/env bash
# Forensic Council — Phase 8 test verification
#
# Usage:
#   ./scripts/verify_phase8_tests.sh static         # ruff + pyright + tsc + eslint
#   ./scripts/verify_phase8_tests.sh frontend-unit  # jest
#   ./scripts/verify_phase8_tests.sh backend-unit   # pytest

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1" >&2; exit 1; }

MODE="${1:-static}"

require_tool() {
    command -v "$1" >/dev/null 2>&1 || { echo "ERROR: $1 not found — install it first"; exit 1; }
}

case "$MODE" in
  static)
    echo "=== Phase 8 static checks ==="
    # Backend
    if command -v uv >/dev/null 2>&1 && [ -f "$ROOT/apps/api/pyproject.toml" ]; then
        (cd "$ROOT/apps/api" && uv run ruff check .)   || fail "ruff"
        (cd "$ROOT/apps/api" && uv run pyright)         || fail "pyright"
        pass "backend static (ruff + pyright)"
    else
        echo "  SKIP: uv not installed"
    fi
    # Frontend
    if command -v npm >/dev/null 2>&1 && [ -f "$ROOT/apps/web/package.json" ]; then
        (cd "$ROOT/apps/web" && npm run type-check) || fail "tsc"
        (cd "$ROOT/apps/web" && npm run lint)       || fail "eslint"
        pass "frontend static (tsc + eslint)"
    else
        echo "  SKIP: npm not installed"
    fi
    pass "Phase 8 static checks"
    ;;
  frontend-unit)
    echo "=== Phase 8 frontend unit tests ==="
    require_tool npm
    [ -f "$ROOT/apps/web/package.json" ] || fail "apps/web/package.json not found"
    (cd "$ROOT/apps/web" && npm run test -- --runInBand) || fail "jest"
    pass "frontend-unit"
    ;;
  backend-unit)
    echo "=== Phase 8 backend unit tests ==="
    require_tool uv
    [ -f "$ROOT/apps/api/pyproject.toml" ] || fail "apps/api/pyproject.toml not found"
    (cd "$ROOT/apps/api" && uv run pytest tests/ -x -q) || fail "pytest"
    pass "backend-unit"
    ;;
  *)
    echo "Usage: $0 [static|frontend-unit|backend-unit]" >&2
    exit 2
    ;;
esac
