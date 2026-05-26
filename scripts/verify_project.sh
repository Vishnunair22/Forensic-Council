#!/usr/bin/env bash
# Forensic Council — final all-phase verification script
#
# Usage:
#   ./scripts/verify_project.sh static      # docs, hygiene, compile, shell syntax
#   ./scripts/verify_project.sh frontend    # npm ci, type-check, lint, jest, build
#   ./scripts/verify_project.sh backend      # ruff, pyright, pytest unit/security/infra, contracts/integration
#   ./scripts/verify_project.sh workflow    # Phase 7 workflow checks
#   ./scripts/verify_project.sh tests       # Phase 8 test suite checks
#   ./scripts/verify_project.sh docker-dev  # Docker dev stack validation
#   ./scripts/verify_project.sh docker-prod # Docker prod stack validation
#   ./scripts/verify_project.sh all         # static + backend + frontend (skip docker)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:-static}"

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1" >&2; exit 1; }

case "$MODE" in

  static)
    echo "=== Static checks ==="
    python scripts/check_docs.py || fail "docs check failed"
    pass "docs consistency"

    python scripts/check_test_hygiene.py || fail "test hygiene failed"
    pass "test hygiene"

    python -m compileall -q apps/api/api apps/api/core apps/api/agents apps/api/orchestration apps/api/tools apps/api/scripts apps/api/tests scripts 2>/dev/null || fail "Python compile failed"
    pass "Python compile"

    for sh in scripts/*.sh infra/*.sh apps/api/scripts/*.sh; do
      if [[ -f "$sh" ]]; then
        bash -n "$sh" || fail "shell syntax failed: $sh"
      fi
    done
    pass "shell syntax"
    echo "Project verification passed: static"
    ;;

  frontend)
    echo "=== Frontend checks ==="
    cd apps/web
    npm ci --prefer-offline 2>&1 | tail -5 || fail "npm ci failed"
    pass "npm ci"

    npm run type-check 2>&1 | tail -5 || fail "type-check failed"
    pass "type-check"

    npm run lint 2>&1 | tail -5 || fail "lint failed"
    pass "lint"

    npm test -- --runInBand --passWithNoTests 2>&1 | tail -10 || fail "Jest failed"
    pass "Jest"

    npm run build 2>&1 | tail -10 || fail "Next.js build failed"
    pass "Next.js build"
    cd "$ROOT"
    echo "Project verification passed: frontend"
    ;;

  backend)
    echo "=== Backend checks ==="
    cd apps/api

    uv run ruff check . 2>&1 | tail -10 || fail "ruff check failed"
    pass "ruff"

    if uv run pyright --version >/dev/null 2>&1; then
      uv run pyright 2>&1 | tail -10 || fail "pyright failed"
      pass "pyright"
    else
      echo "SKIP: pyright not installed (run: uv sync --extra dev)"
    fi

    uv run pytest tests/unit tests/security tests/infra -q --tb=short 2>&1 | tail -10 || fail "pytest unit/security/infra failed"
    pass "pytest unit/security/infra"

    uv run pytest tests/contracts tests/integration -q --tb=short 2>&1 | tail -10 || fail "pytest contracts/integration failed"
    pass "pytest contracts/integration"

    cd "$ROOT"
    echo "Project verification passed: backend"
    ;;

  workflow)
    echo "=== Workflow checks ==="
    python scripts/check_docs.py || fail "docs check failed"
    pass "docs consistency"
    python scripts/check_test_hygiene.py || fail "test hygiene failed"
    pass "test hygiene"
    echo "Project verification passed: workflow"
    ;;

  tests)
    echo "=== Test suite checks ==="
    ./scripts/verify_phase8_tests.sh static || fail "test static failed"
    pass "test static"

    ./scripts/verify_phase8_tests.sh frontend-unit || fail "test frontend-unit failed"
    pass "test frontend-unit"

    ./scripts/verify_phase8_tests.sh backend-unit || fail "test backend-unit failed"
    pass "test backend-unit"

    echo "Project verification passed: tests"
    ;;

  docker-dev)
    echo "=== Docker dev checks ==="
    if [[ -f scripts/verify_phase1_build_run.sh ]]; then
      ./scripts/verify_phase1_build_run.sh docker-dev 2>&1 | tail -10 || fail "docker-dev failed"
      pass "docker-dev"
    else
      echo "SKIP: verify_phase1_build_run.sh not found"
    fi
    echo "Project verification passed: docker-dev"
    ;;

  docker-prod)
    echo "=== Docker prod checks ==="
    if [[ -f scripts/verify_phase1_build_run.sh ]]; then
      ./scripts/verify_phase1_build_run.sh docker-prod 2>&1 | tail -10 || fail "docker-prod failed"
      pass "docker-prod"
    else
      echo "SKIP: verify_phase1_build_run.sh not found"
    fi
    echo "Project verification passed: docker-prod"
    ;;

  all)
    echo "=== Full project verification ==="
    "$0" static || fail "static failed"
    "$0" backend || fail "backend failed"
    "$0" frontend || fail "frontend failed"
    echo "Project verification passed: all"
    ;;

  *)
    echo "Usage: $0 [static|frontend|backend|workflow|tests|docker-dev|docker-prod|all]" >&2
    echo "  static      — docs, hygiene, compile, shell syntax"
    echo "  frontend    — npm ci, type-check, lint, jest, build"
    echo "  backend     — ruff, pyright, pytest"
    echo "  workflow    — Phase 7 workflow checks"
    echo "  tests       — Phase 8 test suite checks"
    echo "  docker-dev  — Docker dev stack validation"
    echo "  docker-prod — Docker prod stack validation"
    echo "  all         — static + backend + frontend"
    exit 2
    ;;

esac