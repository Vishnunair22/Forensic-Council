#!/usr/bin/env bash
set -euo pipefail

# Forensic Council - Production Readiness Validator
# This script ensures that the environment and configuration are ready for production.

echo "--- Forensic Council: Production Readiness Check ---"

# 0. Check for required binaries
echo "[0/5] Verifying required tools..."
for tool in docker npm pre-commit uv; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "FAILED: $tool is not installed or not in PATH."
        exit 1
    fi
done
echo "OK: All tools present."

# 1. Check for unreplaced placeholders in .env
echo "[1/5] Checking for unreplaced placeholders in .env..."
if grep -E "(_REPLACE_ME|__PASTE_)" .env; then
    echo "FAILED: Found unreplaced placeholder values in .env file (shown above)."
    exit 1
fi
echo "OK: No placeholders found."

# 2. Validate Docker Compose configuration
echo "[2/5] Validating Docker Compose configuration (prod)..."
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file .env config -q
echo "OK: Docker configuration is valid."

# 3. Run pre-commit hooks on all files
echo "[3/5] Running pre-commit hooks..."
if ! pre-commit run --all-files; then
    echo "FAILED: Pre-commit hooks failed. Fix the issues before proceeding."
    exit 1
fi
echo "OK: Pre-commit hooks passed."

# 4. Run linting
echo "[4/5] Running linting (root)..."
if ! npm run lint; then
    echo "FAILED: Linting failed."
    exit 1
fi
echo "OK: Linting passed."

# 5. Run tests
echo "[5/5] Running tests (root)..."
if ! npm run test; then
    echo "FAILED: Tests failed."
    exit 1
fi
echo "OK: All tests passed."

echo "----------------------------------------------------"
echo "SUCCESS: Production readiness check passed!"
echo "----------------------------------------------------"
