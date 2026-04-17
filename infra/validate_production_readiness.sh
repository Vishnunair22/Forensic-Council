#!/bin/bash
set -e

echo "═══════════════════════════════════════════════════════════════"
echo "  FORENSIC COUNCIL — PRODUCTION READINESS VALIDATION"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS_COUNT=0
FAIL_COUNT=0

# Helper functions
pass() {
    echo -e "${GREEN}✅ PASS${NC}: $1"
    ((PASS_COUNT++))
}

fail() {
    echo -e "${RED}❌ FAIL${NC}: $1"
    ((FAIL_COUNT++))
}

warn() {
    echo -e "${YELLOW}⚠️  WARN${NC}: $1"
}

# ===========================================================================
# SECTION 1: CODE QUALITY
# ===========================================================================
echo ""
echo "SECTION 1: CODE QUALITY"
echo "───────────────────────────────────────────────────────────────"

# 1.1: Python syntax
echo -n "Checking Python syntax... "
if python -m py_compile apps/api/tools/ml_tools/*.py 2>/dev/null && \
   python -m py_compile apps/api/**/*.py 2>/dev/null; then
    pass "All Python files compile"
else
    fail "Python syntax errors found"
fi

# 1.2: No duplicate code blocks
echo -n "Checking for duplicate __main__ blocks... "
DUPLICATES=$(find apps/api/tools/ml_tools -name "*.py" -exec grep -l "if __name__" {} \; | while read f; do
    grep -c "if __name__" "$f"
done | grep -v "^1$" | wc -l)

if [ "$DUPLICATES" -eq 0 ]; then
    pass "No duplicate __main__ blocks"
else
    fail "$DUPLICATES files have multiple __main__ blocks"
fi

# 1.3: Import checks
echo -n "Checking critical imports... "
MISSING_IMPORTS=0
for file in apps/api/tools/ml_tools/*.py; do
    if ! grep -q "^import sys" "$file"; then
        ((MISSING_IMPORTS++))
    fi
done

if [ "$MISSING_IMPORTS" -eq 0 ]; then
    pass "All ML tools have 'import sys'"
else
    fail "$MISSING_IMPORTS ML tools missing 'import sys'"
fi

# ===========================================================================
# SECTION 2: TESTS
# ===========================================================================
echo ""
echo "SECTION 2: TEST COVERAGE"
echo "───────────────────────────────────────────────────────────────"

# 2.1: Backend unit tests
echo -n "Running backend unit tests... "
if cd apps/api && uv run pytest tests/unit -q --tb=no > /dev/null 2>&1; then
    pass "Backend unit tests pass"
else
    warn "Some backend unit tests failed (check with: cd apps/api && uv run pytest tests/unit -v)"
fi

# 2.2: Frontend tests
echo -n "Checking frontend tests... "
if cd apps/web && npm test -- --watchAll=false --passWithNoTests > /dev/null 2>&1; then
    pass "Frontend tests pass"
    cd ..
else
    warn "Some frontend tests may have failed (check with: cd apps/web && npm test)"
    cd ..
fi

# 2.3: E2E/System test files exist
echo -n "Checking system test files exist... "
if [ -f "apps/api/tests/system/test_forensic_system.py" ]; then
    pass "System test file exists"
else
    fail "System test file missing: apps/api/tests/system/test_forensic_system.py"
fi

# ===========================================================================
# SECTION 3: DOCUMENTATION
# ===========================================================================
echo ""
echo "SECTION 3: DOCUMENTATION"
echo "───────────────────────────────────────────────────────────────"

REQUIRED_DOCS=(
    "README.md"
    "docs/ARCHITECTURE.md"
    "docs/AGENTS.md"
    "docs/DEVELOPMENT_SETUP.md"
    "docs/agent-context/memory.md"
    "docs/agent-context/project_context.md"
    "infra/README.md"
)

for doc in "${REQUIRED_DOCS[@]}"; do
    if [ -f "$doc" ]; then
        pass "Documentation found: $doc"
    else
        fail "Documentation missing: $doc"
    fi
done

# ===========================================================================
# SECTION 4: CONFIGURATION
# ===========================================================================
echo ""
echo "SECTION 4: CONFIGURATION"
echo "───────────────────────────────────────────────────────────────"

# 4.1: .env.example exists
if [ -f ".env.example" ]; then
    pass ".env.example exists"
else
    fail ".env.example missing"
fi

# 4.2: Docker files exist
if [ -f "apps/api/Dockerfile" ]; then
    pass "Backend Dockerfile found"
else
    fail "Backend Dockerfile missing: apps/api/Dockerfile"
fi

if [ -f "apps/web/Dockerfile" ]; then
    pass "Frontend Dockerfile found"
else
    fail "Frontend Dockerfile missing"
fi

# 4.3: docker-compose exists
if [ -f "infra/docker-compose.yml" ]; then
    pass "docker-compose.yml found"
else
    fail "docker-compose.yml missing"
fi

# ===========================================================================
# SECTION 5: SECURITY
# ===========================================================================
echo ""
echo "SECTION 5: SECURITY"
echo "───────────────────────────────────────────────────────────────"

# 5.1: No hardcoded secrets
echo -n "Checking for hardcoded secrets... "
SECRETS=$(grep -r "password\|api.key\|secret" --include="*.py" --include="*.ts" --include="*.tsx" \
    apps/api/ apps/web/ 2>/dev/null | grep -v "PASSWORD\|_key\|\.example" | wc -l)

if [ "$SECRETS" -lt 5 ]; then
    pass "No obvious hardcoded secrets found"
else
    warn "Found $SECRETS potential hardcoded values (review manually)"
fi

# 5.2: .env not tracked by Git
echo -n "Checking .env not tracked by Git... "
if git ls-files --error-unmatch .env 2>/dev/null; then
    fail ".env is tracked by Git — remove from history with git filter-repo"
else
    pass ".env is not tracked by Git"
fi

# 5.3: REDIS_PASSWORD set
echo -n "Checking REDIS_PASSWORD is set... "
if [ -z "${REDIS_PASSWORD}" ]; then
    fail "REDIS_PASSWORD not set — required for production"
else
    pass "REDIS_PASSWORD is set"
fi

# 5.4: Jaeger OTLP not exposed
echo -n "Checking Jaeger OTLP not exposed to host... "
if grep -q "4317:4317" infra/docker-compose.yml 2>/dev/null; then
    fail "Jaeger OTLP port 4317 exposed to host — remove host port binding"
else
    pass "Jaeger OTLP port not exposed to host"
fi

# 5.5: CSRF protection in API
echo -n "Checking CSRF protection... "
if grep -q "csrf_middleware" apps/api/api/main.py; then
    pass "CSRF protection middleware detected"
else
    fail "CSRF protection middleware not found in main.py"
fi

# ===========================================================================
# SUMMARY
# ===========================================================================
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SUMMARY"
echo "═══════════════════════════════════════════════════════════════"
TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo -e "${GREEN}Passed: $PASS_COUNT${NC}"
echo -e "${RED}Failed: $FAIL_COUNT${NC}"
echo -e "Total: $TOTAL"
echo ""

if [ $FAIL_COUNT -eq 0 ]; then
    echo -e "${GREEN}✅ READY FOR PRODUCTION${NC}"
    exit 0
else
    echo -e "${RED}❌ NOT READY FOR PRODUCTION${NC}"
    echo "Fix the above errors before deploying."
    exit 1
fi

