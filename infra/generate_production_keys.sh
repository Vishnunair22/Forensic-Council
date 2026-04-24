#!/usr/bin/env bash
# Generate production-ready secrets for the Forensic Council .env file.

set -euo pipefail

# Mandatory production-readiness: ensure script is run interactively
[[ -t 0 ]] || { echo "Interactive terminal required for production secret generation"; exit 1; }

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
echo "Store these in a password manager."
echo "If SIGNING_KEY is lost or rotated, old reports may no longer verify with the active key."
