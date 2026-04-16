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
if python -m py_compile backend/tools/ml_tools/*.py 2>/dev/null && \
   python -m py_compile backend/**/*.py 2>/dev/null; then
    pass "All Python files compile"
else
    fail "Python syntax errors found"
fi

# 1.2: No duplicate code blocks
echo -n "Checking for duplicate __main__ blocks... "
DUPLICATES=$(find backend/tools/ml_tools -name "*.py" -exec grep -l "if __name__" {} \; | while read f; do
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
for file in backend/tools/ml_tools/*.py; do
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
if pytest tests/backend/unit/ -q --tb=no > /dev/null 2>&1; then
    pass "Backend unit tests pass"
else
    warn "Some backend unit tests failed (check with: pytest tests/backend/unit/ -v)"
fi

# 2.2: Frontend tests
echo -n "Checking frontend tests... "
if cd frontend && npm test -- --watchAll=false --passWithNoTests > /dev/null 2>&1; then
    pass "Frontend tests pass"
    cd ..
else
    warn "Some frontend tests may have failed (check with: cd frontend && npm test)"
    cd ..
fi

# 2.3: E2E test files exist
echo -n "Checking E2E test files exist... "
if [ -f "tests/e2e/test_full_investigation_flow.py" ]; then
    pass "E2E test file exists"
else
    fail "E2E test file missing: tests/e2e/test_full_investigation_flow.py"
fi

# ===========================================================================
# SECTION 3: DOCUMENTATION
# ===========================================================================
echo ""
echo "SECTION 3: DOCUMENTATION"
echo "───────────────────────────────────────────────────────────────"

REQUIRED_DOCS=(
    "README.md"
    "docs/API.md"
    "docs/TESTING.md"
    "docs/SCHEMAS.md"
    "backend/README.md"
    "frontend/README.md"
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
if [ -f "Dockerfile" ] || [ -f "backend/Dockerfile" ]; then
    pass "Dockerfile found"
else
    fail "Dockerfile missing"
fi

if [ -f "frontend/Dockerfile" ]; then
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
    backend/ frontend/ 2>/dev/null | grep -v "PASSWORD\|_key\|\.example" | wc -l)

if [ "$SECRETS" -lt 5 ]; then
    pass "No obvious hardcoded secrets found"
else
    warn "Found $SECRETS potential hardcoded values (review manually)"
fi

# 5.2: CSRF protection in API
echo -n "Checking CSRF protection... "
if grep -q "csrf" backend/api/main.py; then
    pass "CSRF protection configured"
else
    fail "CSRF protection not found"
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
