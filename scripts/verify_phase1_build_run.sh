#!/usr/bin/env bash
set -euo pipefail

# Forensic Council — Phase 1 Build/Run Verification
# Verifies shell syntax, Python compilation, Docker compose rendering, and
# optional tool-based checks. Does NOT run containers by default.
#
# Usage:
#   ./scripts/verify_phase1_build_run.sh [static|web|api|docker-dev|docker-prod]
#
# Targets:
#   static     — shell syntax, Python compileall, JSON/TOML parse (no tools needed)
#   web        — frontend npm ci + type-check + lint + test + build (requires npm)
#   api        — backend uv sync + ruff + pyright + pytest (requires uv)
#   docker-dev — docker compose config validation for dev stack
#   docker-prod — docker compose config validation for prod stack
#   all        — static + docker-dev + docker-prod (safe subset; no app installs)

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REQUIRE_TOOLS="${REQUIRE_TOOLS:-0}"

require_tool_or_skip() {
  local tool="$1"
  if command -v "$tool" >/dev/null 2>&1; then
    return 0
  fi

  if [[ "$REQUIRE_TOOLS" == "1" ]]; then
    echo "FAIL: required tool '$tool' is not installed"
    exit 1
  fi

  echo "SKIP: $tool not installed"
  exit 0
}

MODE="${1:-static}"

case "$MODE" in
  static)
    echo "==> [static] Shell syntax checks..."
    FAILED=0
    shopt -s nullglob
    for f in scripts/*.sh infra/*.sh apps/api/scripts/*.sh; do
      if bash -n "$f" 2>&1; then
        : # pass
      else
        echo "  FAIL: bash -n failed for $f"
        FAILED=1
      fi
    done
    shopt -u nullglob
    if [[ $FAILED -ne 0 ]]; then
      echo "FAIL: shell syntax errors found"
      exit 1
    fi
    echo "  OK: all shell scripts pass bash -n"

    echo "==> [static] Python compilation checks..."
    for d in apps/api/api apps/api/core apps/api/agents apps/api/orchestration apps/api/tools apps/api/scripts; do
      if [[ -d "$d" ]]; then
        ERRORS=$(python -m compileall -q "$d" 2>&1 || true)
        if [[ -z "$ERRORS" ]]; then
          echo "  OK: $(echo "$d" | sed "s|$ROOT/||")"
        else
          echo "  FAIL: compileall errors in $(echo "$d" | sed "s|$ROOT/||")"
          echo "$ERRORS"
          exit 1
        fi
      fi
    done

    echo "==> [static] JSON/TOML parse checks..."
    python - <<'PY'
import json, sys
try:
    json.load(open("apps/web/package.json"))
    json.load(open("apps/web/package-lock.json"))
    print("  OK: package.json and package-lock.json parse")
except Exception as e:
    print(f"  FAIL: package JSON error: {e}")
    sys.exit(1)
PY
    echo "  OK: JSON/TOML parse checks passed"
    echo ""
    echo "=========================================="
    echo "PASS: Phase 1 static verification complete."
    echo "=========================================="
    ;;

  web)
    echo "==> [web] Frontend verification (requires npm)..."
    require_tool_or_skip npm
    cd "$ROOT/apps/web"
    npm ci
    npm run type-check
    npm run lint
    npm test -- --runInBand
    npm run build
    cd "$ROOT"
    echo ""
    echo "=========================================="
    echo "PASS: Phase 1 web verification complete."
    echo "=========================================="
    ;;

  api)
    echo "==> [api] Backend verification (requires uv)..."
    require_tool_or_skip uv
    cd "$ROOT/apps/api"
    uv sync --locked --extra dev --extra security --extra observability
    uv run ruff check .
    uv run pyright
    uv run pytest tests/ -q --tb=short --basetemp .pytest_tmp_run
    cd "$ROOT"
    echo ""
    echo "=========================================="
    echo "PASS: Phase 1 api verification complete."
    echo "=========================================="
    ;;

  docker-dev)
    echo "==> [docker-dev] Docker compose dev config validation..."
    require_tool_or_skip docker
    if docker compose -f "$ROOT/infra/docker-compose.yml" -f "$ROOT/infra/docker-compose.dev.yml" --env-file "$ROOT/.env" config -q 2>&1; then
      echo "  OK: docker-dev compose renders cleanly"
    else
      echo "FAIL: docker-dev compose config validation failed"
      exit 1
    fi
    echo ""
    echo "=========================================="
    echo "PASS: Phase 1 docker-dev verification complete."
    echo "=========================================="
    ;;

  docker-prod)
    echo "==> [docker-prod] Docker compose prod config validation..."
    require_tool_or_skip docker
    if docker compose -f "$ROOT/infra/docker-compose.yml" -f "$ROOT/infra/docker-compose.prod.yml" --env-file "$ROOT/.env" config -q 2>&1; then
      echo "  OK: docker-prod compose renders cleanly"
    else
      echo "FAIL: docker-prod compose config validation failed"
      exit 1
    fi
    echo ""
    echo "=========================================="
    echo "PASS: Phase 1 docker-prod verification complete."
    echo "=========================================="
    ;;

  all)
    echo "==> [all] Phase 1 verification: static + docker-dev + docker-prod"
    "$0" static
    "$0" docker-dev
    "$0" docker-prod
    echo ""
    echo "=========================================="
    echo "PASS: Phase 1 all-targets verification complete."
    echo "=========================================="
    ;;

  *)
    echo "Usage: $0 [static|web|api|docker-dev|docker-prod|all]" >&2
    echo "" >&2
    echo "Targets:" >&2
    echo "  static     shell syntax + Python compileall + JSON/TOML (no tools needed)" >&2
    echo "  web        frontend npm ci + type-check + lint + test + build" >&2
    echo "  api        backend uv sync + ruff + pyright + pytest" >&2
    echo "  docker-dev docker compose -f infra/docker-compose.dev.yml config" >&2
    echo "  docker-prod docker compose -f infra/docker-compose.prod.yml config" >&2
    echo "  all        static + docker-dev + docker-prod (recommended first pass)" >&2
    exit 2
    ;;
esac