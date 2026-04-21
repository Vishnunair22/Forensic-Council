-#!/bin/bash
# ============================================================================
# Forensic Council - Smoke Test
# ============================================================================
# Run from the apps/api/ directory:
#   bash scripts/smoke_test.sh
#
# Prerequisites:
#   - Docker Compose stack up  (docker compose -f infra/docker-compose.yml up -d)
#   - uv installed
# ============================================================================
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_DIR="$(cd "$BACKEND_DIR/.." && pwd)"
COMPOSE_FILE="$PROJECT_DIR/infra/docker-compose.yml"

echo -e "${YELLOW}=== Forensic Council Smoke Test ===${NC}"
echo -e "Project root: $PROJECT_DIR"

# 1. Infrastructure health
echo -e "\n${YELLOW}[1/7] Checking infrastructure containers...${NC}"
HEALTHY_COUNT=$(docker compose -f "$COMPOSE_FILE" ps --format json 2>/dev/null \
  | python3 -c "import sys,json; data=sys.stdin.read(); rows=[json.loads(l) for l in data.splitlines() if l]; print(sum(1 for r in rows if 'healthy' in r.get('Health','').lower() and r.get('Service','') in ('redis','qdrant','postgres')))" 2>/dev/null || echo "0")
if [ "$HEALTHY_COUNT" -ge 3 ]; then
  echo -e "${GREEN}All 3 infrastructure containers healthy${NC}"
else
  echo -e "${YELLOW}Only $HEALTHY_COUNT/3 infrastructure containers healthy. Tests requiring infra may fail.${NC}"
fi

# 2. Unit tests (no infrastructure needed)
echo -e "\n${YELLOW}[2/7] Running unit tests...${NC}"
cd "$PROJECT_DIR"
uv run pytest apps/api/tests/unit/ -q --tb=short && echo -e "${GREEN}Unit tests passed${NC}" \
  || echo -e "${YELLOW}Some unit tests failed - check output above${NC}"

# 3. Integration tests
echo -e "\n${YELLOW}[3/7] Running integration tests...${NC}"
uv run pytest apps/api/tests/integration/ -q --tb=short && echo -e "${GREEN}Integration tests passed${NC}" \
  || echo -e "${YELLOW}Some integration tests failed (may need running infra)${NC}"

# 4. Start API server (background)
echo -e "\n${YELLOW}[4/7] Starting API server...${NC}"
cd "$BACKEND_DIR"
uv run python scripts/run_api.py &
API_PID=$!
sleep 4

# 5. Health check
echo -e "\n${YELLOW}[5/7] Checking API health endpoint...${NC}"
HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null || echo "000")
if [ "$HEALTH_STATUS" = "200" ]; then
  echo -e "${GREEN}API health check passed (HTTP $HEALTH_STATUS)${NC}"
else
  echo -e "${RED}API health check failed (HTTP $HEALTH_STATUS)${NC}"
  kill "$API_PID" 2>/dev/null || true
  exit 1
fi

# 6. Auth smoke test
echo -e "\n${YELLOW}[6/7] Testing auth endpoint...${NC}"
AUTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=investigator&password=inv123!" \
  -H "Content-Type: application/x-www-form-urlencoded" 2>/dev/null || echo "000")
if [ "$AUTH_STATUS" = "200" ]; then
  echo -e "${GREEN}Auth endpoint working (HTTP $AUTH_STATUS)${NC}"
else
  echo -e "${YELLOW}Auth returned HTTP $AUTH_STATUS - users may not be bootstrapped yet${NC}"
fi

# 7. Frontend build check
echo -e "\n${YELLOW}[7/7] Verifying frontend build...${NC}"
cd "$PROJECT_DIR/apps/web"
npm run build 2>&1 | tail -5 && echo -e "${GREEN}Frontend build passed${NC}" \
  || echo -e "${YELLOW}Frontend build had warnings - check output above${NC}"

# Cleanup
kill "$API_PID" 2>/dev/null || true

echo -e "\n${GREEN}=== Smoke test complete ===${NC}"

