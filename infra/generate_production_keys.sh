#!/bin/bash
# ============================================================================
# Forensic Council — Production Key Generator
# ============================================================================
# This script generates high-entropy, unique secrets for your .env file
# to ensure compliance with production hardening requirements.
# ============================================================================

set -e

# Colors for output
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${BOLD}${CYAN}━━━  Forensic Council: Key Generation  ━━━${NC}\n"

generate_secret() {
    python3 -c "import secrets; import string; chars = string.ascii_letters + string.digits + '!@#$%^&*()_+-=[]{}|;:,.<>?'; print(''.join(secrets.choice(chars) for _ in range($1)))" 2>/dev/null || \
    python -c "import secrets; import string; chars = string.ascii_letters + string.digits + '!@#$%^&*()_+-=[]{}|;:,.<>?'; print(''.join(secrets.choice(chars) for _ in range($1)))"
}

generate_hex() {
    python3 -c "import secrets; print(secrets.token_hex($1))" 2>/dev/null || \
    python -c "import secrets; print(secrets.token_hex($1))"
}

echo -e "${YELLOW}Generating unique production secrets...${NC}"

S_KEY=$(generate_hex 32)
J_KEY=$(generate_hex 32)
P_PASS=$(generate_secret 24)
R_PASS=$(generate_secret 24)
A_PASS=$(generate_secret 24)
I_PASS=$(generate_secret 24)

echo -e "\n${BOLD}Paste these into your .env file:${NC}"
echo -e "──────────────────────────────────────────────────────"
echo -e "${GREEN}SIGNING_KEY=${NC}${S_KEY}"
echo -e "${GREEN}JWT_SECRET_KEY=${NC}${J_KEY}"
echo -e ""
echo -e "${GREEN}POSTGRES_PASSWORD=${NC}${P_PASS}"
echo -e "${GREEN}REDIS_PASSWORD=${NC}${R_PASS}"
echo -e ""
echo -e "${GREEN}BOOTSTRAP_ADMIN_PASSWORD=${NC}${A_PASS}"
echo -e "${GREEN}BOOTSTRAP_INVESTIGATOR_PASSWORD=${NC}${I_PASS}"
echo -e "──────────────────────────────────────────────────────"

echo -e "\n${YELLOW}Note: Store these safely in a password manager. If you lose the${NC}"
echo -e "${YELLOW}SIGNING_KEY, you will not be able to verify existing reports.${NC}\n"
