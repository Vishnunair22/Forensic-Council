#!/usr/bin/env bash
set -euo pipefail

# Helper functions to generate random strings
assert_min_len() {
    local v="$1" min="$2" name="$3"
    [ "${#v}" -ge "$min" ] || { echo "FATAL: $name too short ($((${#v})) < $min)"; exit 1; }
}

hex64() {
    python3 -c 'import secrets; print(secrets.token_hex(32))'
}

alnum32() {
    python3 -c 'import secrets, string; a = string.ascii_letters + string.digits; print("".join(secrets.choice(a) for _ in range(32)))'
}

echo "Generating secure keys and passwords for production environment..."
echo "---------------------------------------------------------------"

SIGNING_KEY=$(hex64)
JWT_SECRET_KEY=$(hex64)
POSTGRES_PASSWORD=$(alnum32)
REDIS_PASSWORD=$(alnum32)
QDRANT_API_KEY=$(hex64)
BOOTSTRAP_ADMIN_PASSWORD=$(alnum32)
BOOTSTRAP_INVESTIGATOR_PASSWORD=$(alnum32)
DEMO_PASSWORD=${BOOTSTRAP_INVESTIGATOR_PASSWORD}   # MUST equal BOOTSTRAP_INVESTIGATOR_PASSWORD
METRICS_SCRAPE_TOKEN=$(hex64)

assert_min_len "$SIGNING_KEY" 32 SIGNING_KEY
assert_min_len "$JWT_SECRET_KEY" 32 JWT_SECRET_KEY
assert_min_len "$POSTGRES_PASSWORD" 16 POSTGRES_PASSWORD
assert_min_len "$REDIS_PASSWORD" 16 REDIS_PASSWORD
assert_min_len "$QDRANT_API_KEY" 32 QDRANT_API_KEY
assert_min_len "$BOOTSTRAP_ADMIN_PASSWORD" 16 BOOTSTRAP_ADMIN_PASSWORD
assert_min_len "$BOOTSTRAP_INVESTIGATOR_PASSWORD" 16 BOOTSTRAP_INVESTIGATOR_PASSWORD
assert_min_len "$METRICS_SCRAPE_TOKEN" 32 METRICS_SCRAPE_TOKEN

cat <<EOF
SIGNING_KEY=${SIGNING_KEY}
JWT_SECRET_KEY=${JWT_SECRET_KEY}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
REDIS_PASSWORD=${REDIS_PASSWORD}
QDRANT_API_KEY=${QDRANT_API_KEY}
BOOTSTRAP_ADMIN_PASSWORD=${BOOTSTRAP_ADMIN_PASSWORD}
BOOTSTRAP_INVESTIGATOR_PASSWORD=${BOOTSTRAP_INVESTIGATOR_PASSWORD}
DEMO_PASSWORD=${DEMO_PASSWORD}
METRICS_SCRAPE_TOKEN=${METRICS_SCRAPE_TOKEN}
EOF

echo "---------------------------------------------------------------"
echo "IMPORTANT: Save these variables to your .env file immediately."
echo "Do NOT share these keys or commit them to version control."
