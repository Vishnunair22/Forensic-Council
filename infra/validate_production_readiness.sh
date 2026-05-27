#!/usr/bin/env bash
set -euo pipefail

# Forensic Council - Production Readiness Validator
# This script ensures that the environment and configuration are ready for production.

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "--- Forensic Council: Production Readiness Check ($ROOT) ---"

# 0. Check for required binaries (hard requirement)
echo "[0/3] Verifying required tools..."
if ! command -v docker >/dev/null 2>&1; then
    echo "FAILED: docker is not installed or not in PATH."
    exit 1
fi
echo "OK: docker present."

if ! docker compose version >/dev/null 2>&1; then
    echo "FAILED: docker compose is not available."
    exit 1
fi

# Version check for docker compose >= 2.24
COMPOSE_VERSION=$(docker compose version --short 2>/dev/null || docker compose version | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1)
MAJOR=$(echo "$COMPOSE_VERSION" | cut -d. -f1)
MINOR=$(echo "$COMPOSE_VERSION" | cut -d. -f2)
if [ -z "$MAJOR" ] || [ -z "$MINOR" ]; then
    echo "FAILED: Could not parse docker compose version '$COMPOSE_VERSION'."
    exit 1
fi
if [ "$MAJOR" -lt 2 ] || { [ "$MAJOR" -eq 2 ] && [ "$MINOR" -lt 24 ]; }; then
    echo "FAILED: docker compose version must be >= 2.24. Got $COMPOSE_VERSION."
    exit 1
fi
echo "OK: docker compose present ($COMPOSE_VERSION >= 2.24)."

if ! docker info >/dev/null 2>&1; then
    echo "FAILED: Docker daemon is not reachable. Start Docker Desktop/Engine and rerun."
    exit 1
fi
echo "OK: docker daemon reachable."

# 1. Check for unreplaced placeholders in .env and production invariants
echo "[1/3] Checking for unreplaced placeholders in .env..."
if grep -E "(_REPLACE_ME|__PASTE_)" .env >/dev/null; then
    grep -E "(_REPLACE_ME|__PASTE_)" .env
    echo "FAILED: Found unreplaced placeholders."
    exit 1
fi
echo "OK"

echo "[1b/3] Validating production configuration invariants..."
for var in APP_ENV DOMAIN CADDY_SITE_ADDRESS CORS_ALLOWED_ORIGINS GEMINI_API_KEY_POLICY_OK; do
  v=$(grep "^${var}=" .env | cut -d= -f2-)
  case $var in
    APP_ENV)  [ "$v" = "production" ] || { echo "FAIL: APP_ENV must be production"; exit 1; };;
    DOMAIN)   [ "$v" != "localhost" ] || { echo "FAIL: DOMAIN is localhost"; exit 1; };;
    CADDY_SITE_ADDRESS)
      [ -n "$v" ] || { echo "FAIL: CADDY_SITE_ADDRESS must be set in production"; exit 1; }
      echo "$v" | grep -qw "localhost" && { echo "FAIL: CADDY_SITE_ADDRESS points at localhost"; exit 1; }
      echo "$v" | grep -qE "^https?://" || { echo "FAIL: CADDY_SITE_ADDRESS must start with http:// or https://"; exit 1; }
      ;;
    CORS_ALLOWED_ORIGINS) echo "$v" | grep -qw "localhost" && { echo "FAIL: CORS contains localhost"; exit 1; };;
    GEMINI_API_KEY_POLICY_OK) [ "$v" = "true" ] || { echo "FAIL: Gemini policy not acknowledged"; exit 1; };;
  esac
done
SIGN=$(grep SIGNING_KEY= .env | cut -d= -f2-); JWT=$(grep JWT_SECRET_KEY= .env | cut -d= -f2-)
[ "$SIGN" != "$JWT" ] || { echo "FAIL: SIGNING_KEY must differ from JWT_SECRET_KEY"; exit 1; }
[ ${#SIGN} -ge 32 ] || { echo "FAIL: SIGNING_KEY must be at least 32 characters"; exit 1; }

INVESTIGATOR_PWD=$(grep BOOTSTRAP_INVESTIGATOR_PASSWORD= .env | cut -d= -f2-)
DEMO_PWD=$(grep DEMO_PASSWORD= .env | cut -d= -f2-)
[ "$INVESTIGATOR_PWD" = "$DEMO_PWD" ] || { echo "FAIL: BOOTSTRAP_INVESTIGATOR_PASSWORD must equal DEMO_PASSWORD"; exit 1; }

# Research-only models must never run in production (non-commercial licences).
# (P3-DOCS-001 fix, audit v6→v7)
RESEARCH_MODELS=$(grep ENABLE_RESEARCH_MODELS= .env | cut -d= -f2-)
[ "$RESEARCH_MODELS" = "false" ] || [ -z "$RESEARCH_MODELS" ] || { echo "FAIL: ENABLE_RESEARCH_MODELS must be false in production"; exit 1; }

# Handle ARBITER_GEMINI_API_KEY placeholder validation
ARB_GEMINI_KEY=$(grep "^ARBITER_GEMINI_API_KEY=" .env | cut -d= -f2- || echo "")
if [ -n "$ARB_GEMINI_KEY" ]; then
  case "$ARB_GEMINI_KEY" in
    __REPLACE_ME*|__PASTE_*|*placeholder*|*Placeholder*|*PLACEHOLDER*|change-me|changeme|change_me)
      echo "FAIL: ARBITER_GEMINI_API_KEY has a placeholder value in .env"
      exit 1
      ;;
  esac
fi

echo "OK"

# 2. Validate Docker Compose configuration
echo "[2/3] Validating docker compose config..."
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file .env config -q
echo "OK"

echo "----------------------------------------------------"
echo "SUCCESS: Production readiness check passed!"
echo "----------------------------------------------------"
echo "  Tip: run ./infra/validate_repo_health.sh to also lint/test the codebase (CI step, not required for deployment)."
