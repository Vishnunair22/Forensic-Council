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
  local log_file="${SCRIPT_DIR}/.validate_log_${PASS_COUNT:-0}.tmp"
  if "$@" >"$log_file" 2>&1; then
    pass "$label"
  else
    fail "$label (see $log_file)"
  fi
}

# Auto-source .env if present (critical for production secret checks)
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

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
  run_check "Backend unit tests pass" cd apps/api && uv run pytest tests/unit -q --tb=short
else
  warn "uv not found; skipped backend unit tests"
fi

if command -v npm >/dev/null 2>&1; then
  run_check "Frontend tests pass" cd apps/web && npm test -- --watchAll=false --passWithNoTests
else
  warn "npm not found; skipped frontend tests"
fi

# Validate all compose overlays
if command -v docker >/dev/null 2>&1; then
  for overlay in dev test infra; do
    if docker compose -f infra/docker-compose.yml -f "infra/docker-compose.${overlay}.yml" config >/dev/null 2>&1; then
      pass "Compose ${overlay} overlay renders"
    else
      fail "Compose ${overlay} overlay failed to render"
    fi
  done
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

# Always validate secrets (not just in production mode)
# This check runs regardless of APP_ENV - operators MUST source .env before running
for var in SIGNING_KEY JWT_SECRET_KEY POSTGRES_PASSWORD REDIS_PASSWORD \
           METRICS_SCRAPE_TOKEN BOOTSTRAP_ADMIN_PASSWORD \
           BOOTSTRAP_INVESTIGATOR_PASSWORD DEMO_PASSWORD; do
  val="${!var:-}"
  if [ -n "$val" ] && ! printf '%s' "$val" | grep -q "REPLACE_ME"; then
    pass "$var is set"
  else
    fail "$var is missing or still a placeholder"
  fi
done

# Signing key must be ≥32 characters
sk_len="${#SIGNING_KEY}"
if [ -n "${SIGNING_KEY:-}" ] && [ "$sk_len" -ge 32 ]; then
  pass "SIGNING_KEY length OK (${sk_len} chars)"
else
  fail "SIGNING_KEY must be at least 32 characters (got ${sk_len})"
fi

jk_len="${#JWT_SECRET_KEY}"
if [ -n "${JWT_SECRET_KEY:-}" ] && [ "$jk_len" -ge 32 ]; then
  pass "JWT_SECRET_KEY length OK (${jk_len} chars)"
else
  fail "JWT_SECRET_KEY must be at least 32 characters (got ${jk_len})"
fi

# CORS must not contain wildcard in production
if [ "${APP_ENV:-}" = "production" ]; then
  if printf '%s' "${CORS_ALLOWED_ORIGINS:-}" | grep -q "\*"; then
    fail "CORS_ALLOWED_ORIGINS contains wildcard '*' — blocked in production"
  else
    pass "CORS_ALLOWED_ORIGINS has no wildcard"
  fi
else
  pass "CORS wildcard check skipped (not production)"
fi

# Redis password must be set
if [ -n "${REDIS_PASSWORD:-}" ] && ! printf '%s' "${REDIS_PASSWORD}" | grep -q "REPLACE_ME"; then
  pass "REDIS_PASSWORD is set"
else
  fail "REDIS_PASSWORD is missing or still a placeholder"
fi

# Demo password must not be the development default
if printf '%s' "${DEMO_PASSWORD:-}" | grep -qE "demo_dev_only|REPLACE_ME|changeme|password"; then
  fail "DEMO_PASSWORD is using an insecure default — set a strong value"
else
  pass "DEMO_PASSWORD is not a known insecure default"
fi

# Qdrant API key must be set in production
if [ "${APP_ENV:-}" = "production" ]; then
  if [ -n "${QDRANT_API_KEY:-}" ] && ! printf '%s' "${QDRANT_API_KEY}" | grep -q "REPLACE_ME"; then
    pass "QDRANT_API_KEY is set"
  else
    fail "QDRANT_API_KEY must be set in production (Qdrant has no auth without it)"
  fi
else
  pass "QDRANT_API_KEY check skipped (not production)"
fi

# MODEL_LICENSING.md must exist
if [ -f "docs/MODEL_LICENSING.md" ]; then
  pass "docs/MODEL_LICENSING.md exists"
else
  fail "docs/MODEL_LICENSING.md is missing — required for license compliance"
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
