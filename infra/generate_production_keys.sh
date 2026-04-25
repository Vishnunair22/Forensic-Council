#!/usr/bin/env bash
# Generate production-ready secrets for the Forensic Council .env file.

set -euo pipefail

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "ERROR: Python is required to generate secrets." >&2
  exit 1
fi

secret() {
  "$PYTHON_BIN" - "$1" <<'PY'
import secrets
import string
import sys

length = int(sys.argv[1])
# Dotenv- and Docker-Compose-friendly characters. Avoid shell metacharacters.
alphabet = string.ascii_letters + string.digits + "_-"
print("".join(secrets.choice(alphabet) for _ in range(length)))
PY
}

hex_secret() {
  "$PYTHON_BIN" - "$1" <<'PY'
import secrets
import sys

print(secrets.token_hex(int(sys.argv[1])))
PY
}

echo "Forensic Council production secrets"
echo "Paste these values into your repo-root .env file."
echo

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-}"

add_or_update_env() {
  local key="$1"
  local value="$2"
  local file="${3:-.env}"
  
  if [ -f "$file" ]; then
    # Remove existing key and add new value
    grep -v "^${key}=" "$file" 2>/dev/null || true
  fi
  echo "${key}=${value}"
}

# If --write flag is provided, update .env directly
if [ "${1:-}" = "--write" ]; then
  TARGET="${2:-.env}"
  BACKUP="${TARGET}.bak.$(date +%s)"
  
  if [ -f "$TARGET" ]; then
    echo "Backing up existing .env to $BACKUP"
    cp "$TARGET" "$BACKUP"
  fi
  
  {
    grep -v -E '^(SIGNING_KEY|JWT_SECRET_KEY|POSTGRES_PASSWORD|REDIS_PASSWORD|BOOTSTRAP_ADMIN_PASSWORD|BOOTSTRAP_INVESTIGATOR_PASSWORD|DEMO_PASSWORD|METRICS_SCRAPE_TOKEN)=' "$TARGET" 2>/dev/null || true
    echo "SIGNING_KEY=$(hex_secret 32)"
    echo "JWT_SECRET_KEY=$(hex_secret 32)"
    echo "POSTGRES_PASSWORD=$(secret 32)"
    echo "REDIS_PASSWORD=$(secret 32)"
    echo "BOOTSTRAP_ADMIN_PASSWORD=$(secret 32)"
    echo "BOOTSTRAP_INVESTIGATOR_PASSWORD=$(secret 32)"
    echo "DEMO_PASSWORD=$(secret 32)"
    echo "METRICS_SCRAPE_TOKEN=$(hex_secret 32)"
  } > "${TARGET}.tmp" && mv "${TARGET}.tmp" "$TARGET"
  
  echo "Wrote new secrets to $TARGET (backup at $BACKUP)"
  exit 0
fi

# Default: output to stdout for manual pasting
cat <<EOF
SIGNING_KEY=$(hex_secret 32)
JWT_SECRET_KEY=$(hex_secret 32)

POSTGRES_PASSWORD=$(secret 32)
REDIS_PASSWORD=$(secret 32)

BOOTSTRAP_ADMIN_PASSWORD=$(secret 32)
BOOTSTRAP_INVESTIGATOR_PASSWORD=$(secret 32)
DEMO_PASSWORD=$(secret 32)

METRICS_SCRAPE_TOKEN=$(hex_secret 32)
EOF

echo
echo "Remember: LLM_API_KEY (Groq) and GEMINI_API_KEY are NOT generated."
echo "Get them from console.groq.com and aistudio.google.com."
echo
echo "Store these in a password manager."
echo "If SIGNING_KEY is lost or rotated, old reports may no longer verify with the active key."
echo
echo "To write directly to .env, run: $SCRIPT_DIR/generate_production_keys.sh --write [.env]"