#!/usr/bin/env bash
# phase_guard.sh — DoD regression guard for all completed phases.
# Run before starting any new fix to confirm no regressions.
# Usage: bash scripts/phase_guard.sh
set -euo pipefail

API="${FORENSIC_API_URL:-http://localhost}"
PASS=0
FAIL=0

ok()   { echo "  [PASS] $*"; PASS=$((PASS + 1)); }
fail() { echo "  [FAIL] $*"; FAIL=$((FAIL + 1)); }

# ── helpers ──────────────────────────────────────────────────────────────────

wait_http() {
  local url="$1" label="${2:-$1}" retries="${3:-10}"
  for i in $(seq 1 "$retries"); do
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || echo "000")
    if [[ "$code" =~ ^[23] ]]; then
      ok "$label → HTTP $code"
      return 0
    fi
    sleep 2
  done
  fail "$label → no 2xx/3xx after $retries retries (last: $code)"
  return 1
}

# ── Phase 1: container health ─────────────────────────────────────────────────
echo "Phase 1 — Container health"
for svc in forensic_api forensic_worker forensic_ui forensic_caddy forensic_redis forensic_postgres; do
  STATUS=$(docker inspect --format '{{.State.Health.Status}}' "$svc" 2>/dev/null || echo "missing")
  if [[ "$STATUS" == "healthy" ]]; then
    ok "$svc is healthy"
  elif [[ "$STATUS" == "missing" ]]; then
    fail "$svc not found (is the stack running?)"
  else
    fail "$svc status=$STATUS (expected healthy)"
  fi
done

# ── Phase 2: backend live endpoint ───────────────────────────────────────────
echo ""
echo "Phase 2 — Backend API"
wait_http "$API/lb-health"     "Caddy lb-health"
wait_http "$API/api/v1/health" "Backend /api/v1/health"

# ── Phase 3: auto-login (demo route) ─────────────────────────────────────────
echo ""
echo "Phase 3 — Auto-login"
DEMO_RESP=$(curl -s -c /tmp/pg_cookies.txt \
  -X POST "$API/api/auth/demo" \
  -H "Content-Type: application/json" \
  -d '{}' \
  --max-time 10 2>/dev/null || echo "{}")
if echo "$DEMO_RESP" | grep -q "access_token\|already_authenticated\|token"; then
  ok "Demo auto-login returned token"
else
  fail "Demo auto-login failed: ${DEMO_RESP:0:200}"
fi

# ── Phase 4: CSRF cookie present ─────────────────────────────────────────────
echo ""
echo "Phase 4 — CSRF"
curl -s -c /tmp/pg_cookies.txt "$API/api/v1/health" > /dev/null 2>&1
if grep -q "csrf_token" /tmp/pg_cookies.txt 2>/dev/null; then
  ok "csrf_token cookie is set"
else
  fail "csrf_token cookie missing after GET /api/v1/health"
fi

# ── Phase 5: test upload → queued within 5s ──────────────────────────────────
echo ""
echo "Phase 5 — Upload → queued"
# Fresh cookie jar for upload test — login with admin credentials
LOGIN_PASS="${BOOTSTRAP_ADMIN_PASSWORD:-${BOOTSTRAP_INVESTIGATOR_PASSWORD:-}}"
curl -s -c /tmp/pg_up_cookies.txt "$API/api/v1/health" > /dev/null 2>&1
CSRF=$(grep csrf_token /tmp/pg_up_cookies.txt 2>/dev/null | awk '{print $NF}' || echo "")
if [[ -n "$LOGIN_PASS" && -n "$CSRF" ]]; then
  LOGIN_RESP=$(curl -s -c /tmp/pg_up_cookies.txt -b /tmp/pg_up_cookies.txt \
    -X POST "$API/api/v1/auth/login" \
    -H "X-CSRF-Token: $CSRF" \
    -F "username=admin" \
    -F "password=$LOGIN_PASS" 2>/dev/null || echo "{}")
  NEW_CSRF=$(echo "$LOGIN_RESP" | grep -o '"csrf_token":"[^"]*"' | cut -d'"' -f4 || echo "")
  [[ -n "$NEW_CSRF" ]] && CSRF="$NEW_CSRF"
else
  fail "Skipping upload test — BOOTSTRAP_ADMIN_PASSWORD not set or CSRF unavailable"
fi

# Run upload test from inside the API container using the smoke_upload.py script
# (double-slash prefix prevents Git Bash path mangling on Windows)
UPLOAD_RESP=$(docker exec -e "LOGIN_PASS=${LOGIN_PASS:-}" forensic_api \
  python3 //app/scripts/smoke_upload.py 2>/dev/null || echo "{}")

if echo "$UPLOAD_RESP" | grep -qE '"status":\s*"(queued|running|started)"'; then
  ok "Upload returned queued/running status"
  SESSION_ID=$(echo "$UPLOAD_RESP" | grep -o '"session_id":"[^"]*"' | cut -d'"' -f4)
  [[ -n "$SESSION_ID" ]] && ok "session_id: ${SESSION_ID:0:8}..." || true
else
  fail "Upload did not return queued/running: ${UPLOAD_RESP:0:200}"
fi

# ── Phase 6: worker pickup ────────────────────────────────────────────────────
echo ""
echo "Phase 6 — Worker pickup"
# Give worker a moment to pick up the smoke test task
sleep 3
if docker logs forensic_worker --since 90s 2>&1 | grep -qi "task\|celery\|pipeline\|forensic\|investigation\|session"; then
  ok "Worker shows recent task activity"
else
  # Non-fatal: if no investigation is running, the worker may be idle
  fail "Worker shows no recent activity (OK if no investigation is running)"
fi

# ── Phase 7: Postgres history ────────────────────────────────────────────────
echo ""
echo "Phase 7 — History (Postgres)"
DB_ROWS=$(docker exec forensic_postgres bash -c \
  "PGPASSWORD=\${POSTGRES_PASSWORD} psql -U \${POSTGRES_USER:-forensic_user} -d \${POSTGRES_DB:-forensic_council} -t -c 'SELECT COUNT(*) FROM investigation_state;'" \
  2>/dev/null | tr -d ' \n' || echo "-1")
if [[ "$DB_ROWS" =~ ^[0-9]+$ ]] && [[ "$DB_ROWS" -gt 0 ]]; then
  ok "investigation_state has $DB_ROWS row(s)"
elif [[ "$DB_ROWS" == "0" ]]; then
  fail "investigation_state is empty (0 rows) — history will not show past sessions"
else
  fail "Postgres query failed (result=$DB_ROWS)"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "────────────────────────────────"
echo "PASS: $PASS  FAIL: $FAIL"
if [[ $FAIL -gt 0 ]]; then
  echo "REGRESSION DETECTED — review failures above before starting new fixes."
  exit 1
else
  echo "All checks passed."
  exit 0
fi
