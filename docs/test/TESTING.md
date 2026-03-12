# Testing Guide — Forensic Council

**Version:** v1.0.3 | Complete testing reference for all project areas.

All tests live in the top-level `tests/` directory, structured by area.

---

## Test Structure

```
tests/
├── README.md                        ← Quick reference (this file is the full guide)
├── frontend/
│   ├── unit/
│   │   ├── lib/api.test.ts          ← API client: tokens, auth, investigation, WS, polling
│   │   ├── lib/schemas_utils.test.ts← Zod schemas, cn() utility
│   │   ├── hooks/useForensicData.test.ts ← Hook + mapReportDtoToReport
│   │   └── components/components.test.tsx ← FileUploadSection, AgentProgressDisplay
│   ├── accessibility/
│   │   └── accessibility.test.tsx   ← WCAG 2.1 AA: keyboard, ARIA, focus, errors
│   ├── integration/
│   │   └── page_flows.test.tsx      ← Session flow, dedup, WS message types, auth lifecycle
│   └── e2e/
│       └── websocket_flow.test.ts   ← Full WS lifecycle, arbiter fix, deep analysis flow
├── backend/
│   ├── conftest.py                  ← Shared fixtures: mocked Redis/Postgres/Qdrant, auth
│   ├── unit/core/
│   │   ├── test_auth.py             ← bcrypt, JWT creation/validation, RBAC
│   │   └── test_config_signing_schemas.py ← Config loading, ECDSA signing, Pydantic DTOs
│   ├── integration/
│   │   └── test_api_routes.py       ← All HTTP endpoints (TestClient, mocked infra)
│   └── security/
│       └── test_security.py         ← Auth bypass, injection, CORS, rate limit, crypto
├── infrastructure/
│   └── test_infrastructure.py       ← docker-compose structure, Dockerfiles, env vars, CI
├── docker/
│   └── test_docker.py               ← Service config, port exposure, volumes, healthchecks
└── connectivity/
    └── test_connectivity.py         ← Live service pings (requires running stack)
```

---

## Running Tests

### Frontend — Jest

```bash
cd frontend

# All tests (watch mode — default)
npm test

# One-shot (CI mode)
npm test -- --watchAll=false

# Specific test file
npm test -- tests/frontend/unit/lib/api.test.ts --watchAll=false

# With coverage
npm run test:coverage

# By pattern
npm test -- --testPathPattern="accessibility" --watchAll=false
```

**Coverage targets:**
- Statements: ≥ 60%
- Functions: ≥ 60%
- Branches: ≥ 50%
- Lines: ≥ 60%

### Backend + Infrastructure — pytest

```bash
# Install test dependencies (one-time)
pip install pytest pytest-asyncio httpx pyyaml

# Run all non-connectivity tests
pytest tests/ --ignore=tests/connectivity -v

# Individual categories
pytest tests/backend/unit/     -v        # Unit tests (no infra needed)
pytest tests/backend/integration/ -v     # API routes (mocked infra)
pytest tests/backend/security/    -v     # Security checks
pytest tests/infrastructure/      -v     # Static config analysis
pytest tests/docker/               -v    # Docker Compose validation

# With coverage
pip install pytest-cov
pytest tests/backend/ --cov=backend --cov-report=html
```

### Connectivity Tests (requires running stack)

```bash
# Start the stack first
.\manage.ps1 up
# or:
docker compose -f docs/docker/docker-compose.yml --env-file .env up -d

# Run connectivity tests
pytest tests/connectivity/ -v

# Skip Docker tests in CI
pytest tests/ --ignore=tests/connectivity -m "not requires_docker" -v
```

---

## What Each Test Category Covers

### Frontend Unit Tests

**`api.test.ts`** — 50+ tests covering:
- `setAuthToken`, `getAuthToken`, `clearAuthToken`, `isAuthenticated` — token storage and expiry
- `login()` — form encoding, success, 401/500 error handling
- `logout()` — token cleared even on network error
- `autoLoginAsInvestigator()` — demo auth endpoint
- `ensureAuthenticated()` — token reuse vs auto-login
- `startInvestigation()` — case ID/investigator ID validation, FormData, error details
- `getReport()` — 202→in_progress, 200→complete, 404→throw
- `getBrief()`, `getCheckpoints()`, `submitHITLDecision()`
- `createLiveSocket()` — AUTH message, CONNECTED resolve, race condition, error/close rejection
- `pollForReport()` — immediate resolve, onProgress callback, timeout rejection

**`schemas_utils.test.ts`** — 40+ tests:
- `AgentResultSchema` — all fields, optional fields, boundary confidence values, type rejection
- `ReportSchema` — single/multiple agents, empty arrays, nested validation
- `HistorySchema` — empty, valid, non-array rejection, invalid entries
- `cn()` — class merge, conditionals, Tailwind conflict resolution, clsx syntax

**`useForensicData.test.ts`** — 35+ tests:
- `mapReportDtoToReport()` — all field mappings, court_statement vs reasoning_summary, calibration fallback, multi-agent, signed_utc fallback, phase metadata handling, dedup
- Hook initial state, sessionStorage load, malformed data graceful handling
- `addToHistory`, `deleteFromHistory`, `clearHistory`, `saveCurrentReport`
- `startAnalysis`, error propagation
- `validateFile` — size limit, all allowed MIME types, rejected types

**`components.test.tsx`** — 30+ tests:
- `FileUploadSection` — render, file display, upload/clear callbacks, uploading state, validation errors, drag state
- `AgentProgressDisplay` — progress text, decision buttons, isNavigating guard, deep phase label, completed agents, sound prop

### Accessibility Tests

**`accessibility.test.tsx`** — 20+ tests verifying WCAG 2.1 AA:
- Keyboard navigation (Tab focus, Enter/Space activation)
- No focus trap
- All buttons have accessible names (text or aria-label)
- Disabled buttons use native `disabled` attribute
- Error messages conveyed as text (not color alone)
- Error state announces on prop change
- Loading states provide text feedback beyond spinners
- isNavigating disables buttons with `disabled` attribute + text

### Integration Tests

**`page_flows.test.tsx`** — 25+ tests:
- Complex multi-agent report mapping (10 findings, phase metadata, dedup)
- Session ID stored in sessionStorage
- Report persisted after poll completes
- History deduplication
- WebSocket message type structure (all 8 types)
- Auth token set/expire/clear lifecycle

### E2E Tests

**`websocket_flow.test.ts`** — 25+ tests:
- WS URL construction, AUTH message on open
- CONNECTED message resolves `connected` promise
- AGENT_UPDATE also resolves (race condition fix)
- Error / close rejection with reason
- No-token rejection
- Full 5-agent sequence (15 messages)
- PIPELINE_PAUSED message handling
- **Arbiter fix** — `isNavigating` prevents double-call
- **Arbiter fix** — error resets `isNavigating` for retry
- **Arbiter fix** — `resumeInvestigation` awaited before `router.push`
- Deep analysis second WS connection
- Phase metadata in deep AGENT_COMPLETE

### Backend Unit Tests

**`test_auth.py`** — Tests for `core/auth.py`:
- bcrypt hash format, correct/wrong/empty verify, salted uniqueness, 72-byte limit
- JWT: format, sub/role/exp fields, 60-min limit (v1.0.3 fix), custom expiry
- JWT validation: valid accept, expired/invalid/none-alg/tampered rejection
- RBAC: UserRole enum, require_role, is_user_active

**`test_config_signing_schemas.py`** — Tests for `core/config.py`, `core/signing.py`, `api/schemas.py`:
- Config loads, JWT ≤ 120 min, CORS is list, debug is bool, singleton cache
- ECDSA signing: produces entry, hash deterministic, tamper detection, timestamp UTC, complex nested data
- Pydantic DTOs: InvestigationRequest, AgentFindingDTO, HITLDecisionRequest validation

### Integration Tests

**`test_api_routes.py`** — TestClient with fully mocked infrastructure:
- Root `200 + status=running`, health `200 + checks field`
- Security headers: X-Content-Type-Options, X-Frame-Options, Referrer-Policy
- Auth: login exists, protected routes reject without token, wrong password 401
- Investigate: missing file 422, invalid case ID 400/422, oversized 413
- Sessions: nonexistent 404, checkpoints/brief endpoints exist
- HITL: auth required, invalid body 422
- Metrics: endpoint exists
- 404 returns JSON, OPTIONS handled

### Security Tests

**`test_security.py`** — Adversarial tests:
- No token / malformed / wrong-secret / expired token rejection
- `alg=none` JWT attack rejected
- Role escalation via forged JWT rejected
- JWT 60-min expiry check (v1.0.3 regression guard)
- SQL injection in case_id caught by Pydantic
- Path traversal strings are invalid UUIDs
- Unicode null bytes don't crash
- Oversized JSON body rejected
- CORS: allowed origin reflects, evil origin not reflected, wildcard + credentials violation check
- Rate limit function exists + raises 429 when exceeded
- ECDSA tamper detection
- SHA-256 hash length = 64
- /health and / endpoints don't leak passwords/keys

### Infrastructure Tests

**`test_infrastructure.py`** — Static analysis:
- docker-compose: all 6 services, project name, ML volumes defined, depends_on + service_healthy, restart policies, security hardening (read_only, tmpfs, requirepass, memory limits, no 'latest' tags)
- Frontend Dockerfile: node-alpine, multi-stage, HOSTNAME=0.0.0.0, wget healthcheck, standalone
- Backend Dockerfile: python 3.12, multi-stage, dev+prod targets, uv, BuildKit cache mounts, port 8000
- `.env.example`: all required vars, COMPOSE_PROJECT_NAME, JWT 60-min, Groq docs, HF_TOKEN, DOMAIN
- CI/CD: jobs, push/PR triggers, backend+frontend+docker jobs
- pyproject.toml, package.json, jest.config.ts

### Docker Tests

**`test_docker.py`** — Compose validation:
- All required services defined
- Port mappings correct (3000, 8000, 80/443)
- Postgres/Redis/Qdrant ports NOT exposed to host
- Env var guards (`:?`) for required secrets
- ML volumes mounted to backend
- Evidence/Postgres/Redis/Qdrant/Caddy volumes present
- All named volumes declared at top level
- Healthcheck commands correct (pg_isready, PING, /health, wget)
- Dev compose uses `target: development`
- Prod compose uses `target: production`
- Caddyfile proxies frontend + backend + API routes

### Connectivity Tests

**`test_connectivity.py`** — Live integration (requires running stack):
- Backend: root 200, health 200 + healthy status, security headers, login endpoint responds, protected route 401
- Frontend: home page 200, HTML content-type, API proxy
- Postgres: accepts connections, has investigation_sessions/users/reports tables
- Redis: PING, set/get/delete, password required check
- Qdrant: health endpoint, collections endpoint, JSON response
- WebSocket: endpoint reachable, AUTH message handled
- E2E auth: login → token → /auth/me → 200, token works on protected routes, logout invalidates token

---

## CI Integration

Tests run automatically on push and pull requests via `.github/workflows/ci.yml`:

```
backend-lint    → ruff + mypy type checking
backend-test    → pytest tests/backend/ + tests/infrastructure/ + tests/docker/
frontend-build  → npm ci + npm run build
frontend-test   → npm test -- --watchAll=false
docker-build    → docker compose build (smoke test)
dep-audit       → pip-audit + npm audit
```

Connectivity tests are excluded from CI (require a running stack).
