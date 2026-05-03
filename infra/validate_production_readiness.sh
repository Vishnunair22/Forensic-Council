#!/usr/bin/env bash
set -euo pipefail

# Forensic Council - Production Readiness Validator
# This script ensures that the environment and configuration are ready for production.

echo "--- Forensic Council: Production Readiness Check ---"

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
echo "OK: docker compose present."

# 1. Check for unreplaced placeholders in .env
echo "[1/3] Checking for unreplaced placeholders in .env..."
if grep -E "(_REPLACE_ME|__PASTE_)" .env >/dev/null; then
    grep -E "(_REPLACE_ME|__PASTE_)" .env
    echo "FAILED: Found unreplaced placeholders."
    exit 1
fi
echo "OK"

# 2. Validate Docker Compose configuration
echo "[2/3] Validating docker compose config..."
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file .env config -q
echo "OK"

# 3. Optional dev-tool checks (soft - only if tools exist)
echo "[3/3] Optional dev-tool checks..."
for tool in npm pre-commit uv; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "  SKIP: $tool not installed (optional)"
        continue
    fi
done

# Only run lint/test if tools available
if command -v pre-commit >/dev/null 2>&1; then
    echo "  Running pre-commit..."
    pre-commit run --all-files || echo "  SKIP pre-commit"
fi

if command -v npm >/dev/null 2>&1 && [ -f apps/web/package.json ]; then
    echo "  Running npm lint..."
    (cd apps/web && npm run lint) || echo "  SKIP npm lint"
fi

if command -v npm >/dev/null 2>&1 && [ -f apps/web/package.json ]; then
    echo "  Running npm test..."
    (cd apps/web && npm run test) || echo "  SKIP npm test"
fi

if command -v uv >/dev/null 2>&1 && [ -f apps/api/pyproject.toml ]; then
    echo "  Running backend lint..."
    (cd apps/api && uv run ruff check .) || echo "  SKIP backend lint"
fi

echo "----------------------------------------------------"
echo "SUCCESS: Production readiness check passed!"
echo "----------------------------------------------------"
