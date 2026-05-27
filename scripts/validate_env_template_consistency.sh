#!/usr/bin/env bash
set -euo pipefail

# Forensic Council — Env Template Consistency Check
#
# Verifies that .env.example (Docker) and .env.host.example (host-run) declare
# the same set of keys, so new variables are not silently missing from one template.
#
# Usage:
#   ./infra/validate_env_template_consistency.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DOCKER_TMPL="$ROOT/.env.example"
HOST_TMPL="$ROOT/.env.host.example"

if [[ ! -f "$DOCKER_TMPL" ]]; then
    echo "ERROR: $DOCKER_TMPL not found"
    exit 1
fi
if [[ ! -f "$HOST_TMPL" ]]; then
    echo "ERROR: $HOST_TMPL not found"
    exit 1
fi

# Extract KEY names (lines matching KEY=..., skip blank lines and comments).
extract_keys() {
    grep -E '^[A-Z_][A-Z0-9_]*=' "$1" | cut -d= -f1 | sort -u
}

DOCKER_KEYS=$(extract_keys "$DOCKER_TMPL")
HOST_KEYS=$(extract_keys "$HOST_TMPL")

# Keys in Docker template but missing from host template.
ONLY_IN_DOCKER=$(comm -23 <(echo "$DOCKER_KEYS") <(echo "$HOST_KEYS"))
# Keys in host template but missing from Docker template.
ONLY_IN_HOST=$(comm -13 <(echo "$DOCKER_KEYS") <(echo "$HOST_KEYS"))

# Keys that are infrastructure-topology-specific are expected to differ:
# POSTGRES_HOST (postgres vs localhost), REDIS_HOST, QDRANT_HOST, etc.
# The check below flags *unexpected* asymmetries — keys that should be in both
# but were added to only one template.
FAIL=0

if [[ -n "$ONLY_IN_DOCKER" ]]; then
    echo "Keys in .env.example but NOT in .env.host.example:"
    echo "$ONLY_IN_DOCKER" | sed 's/^/  /'
    FAIL=1
fi

if [[ -n "$ONLY_IN_HOST" ]]; then
    echo "Keys in .env.host.example but NOT in .env.example:"
    echo "$ONLY_IN_HOST" | sed 's/^/  /'
    FAIL=1
fi

if [[ "$FAIL" -eq 0 ]]; then
    echo "OK: .env.example and .env.host.example declare the same set of keys."
    exit 0
else
    echo ""
    echo "FAILED: Template key mismatch. Add missing keys to the appropriate template."
    exit 1
fi
