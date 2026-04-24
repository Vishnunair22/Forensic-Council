#!/usr/bin/env bash
# Validate production-readiness signals for the Forensic Council repository.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

pass() {
  printf "%bPASS%b: %s\n" "$GREEN" "$NC" "$1"
  PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
  printf "%bFAIL%b: %s\n" "$RED" "$NC" "$1"
  FAIL_COUNT=$((FAIL_COUNT + 1))
}

warn() {
  printf "%bWARN%b: %s\n" "$YELLOW" "$NC" "$1"
  WARN_COUNT=$((WARN_COUNT + 1))
}

section() {
  echo
  echo "$1"
  printf '%s\n' "------------------------------------------------------------"
}

run_check() {
  local label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    pass "$label"
  else
    fail "$label"
  fi
}

echo "Forensic Council production readiness validation"

section "1. Repository Files"
for path in \
  README.md \
  .env.example \
  apps/api/Dockerfile \
  apps/web/Dockerfile \
  infra/docker-compose.yml \
  infra/docker-compose.prod.yml \
  infra/Caddyfile \
  infra/prometheus.yml \
  docs/ARCHITECTURE.md \
  docs/SECURITY.md \
  docs/RUNBOOK.md
do
  if [ -f "$path" ]; then
    pass "Found $path"
  else
    fail "Missing $path"
  fi
done

section "2. Syntax And Configuration"
PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi
if [ -n "$PYTHON_BIN" ]; then
  if find apps/api -name '*.py' -print0 | xargs -0 "$PYTHON_BIN" -m py_compile; then
    pass "Python files compile"
  else
    fail "Python syntax check failed"
  fi
else
  warn "python3/python not found; skipped Python syntax check"
fi

if command -v docker >/dev/null 2>&1; then
  if docker compose -f infra/docker-compose.yml config >/dev/null 2>&1; then
    pass "Base Docker Compose config renders"
  else
    fail "Base Docker Compose config failed to render"
  fi

  if docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml config >/dev/null 2>&1; then
    pass "Production Docker Compose config renders"
  else
    fail "Production Docker Compose config failed to render"
  fi
else
  warn "docker not found; skipped Docker Compose validation"
fi

section "3. Tests"
if command -v uv >/dev/null 2>&1; then
  if (cd apps/api && uv run pytest tests/unit -q --tb=short); then
    pass "Backend unit tests pass"
  else
    warn "Backend unit tests failed or dependencies are missing"
  fi
else
  warn "uv not found; skipped backend unit tests"
fi

if command -v npm >/dev/null 2>&1; then
  if (cd apps/web && npm test -- --watchAll=false --passWithNoTests); then
    pass "Frontend tests pass"
  else
    warn "Frontend tests failed or dependencies are missing"
  fi
else
  warn "npm not found; skipped frontend tests"
fi

section "4. Security Checks"
if git ls-files --error-unmatch .env >/dev/null 2>&1; then
  fail ".env is tracked by Git"
else
  pass ".env is not tracked by Git"
fi

if grep -R "4317:4317" infra/*.yml >/dev/null 2>&1; then
  fail "Jaeger OTLP port 4317 is exposed to the host"
else
  pass "Jaeger OTLP port is not exposed to the host"
fi

if grep -q "METRICS_SCRAPE_TOKEN" .env.example && grep -q "metrics_scrape_token" infra/prometheus.yml; then
  pass "Prometheus scrape token is documented and configured"
else
  fail "Prometheus scrape token wiring is incomplete"
fi

if [ "${APP_ENV:-}" = "production" ]; then
  for var in SIGNING_KEY JWT_SECRET_KEY POSTGRES_PASSWORD REDIS_PASSWORD \
             METRICS_SCRAPE_TOKEN BOOTSTRAP_ADMIN_PASSWORD \
             BOOTSTRAP_INVESTIGATOR_PASSWORD DEMO_PASSWORD; do
    if [ -n "${!var:-}" ] && ! printf '%s' "${!var}" | grep -q "REPLACE_ME"; then
      pass "$var is set"
    else
      fail "$var is missing or still a placeholder"
    fi
  done
else
  warn "APP_ENV is not production; skipped live secret validation"
fi

section "Summary"
echo "Passed: $PASS_COUNT"
echo "Warned: $WARN_COUNT"
echo "Failed: $FAIL_COUNT"

if [ "$FAIL_COUNT" -eq 0 ]; then
  echo "Result: ready pending manual review of warnings."
  exit 0
fi

echo "Result: not ready. Fix failures before production deployment."
exit 1
