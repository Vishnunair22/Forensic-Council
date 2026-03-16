# Forensic Council — Test Suite

## Structure

```
tests/
├── frontend/
│   ├── unit/
│   │   ├── lib/
│   │   │   ├── api.test.ts                  # API client, token management, WebSocket, polling
│   │   │   └── schemas_utils.test.ts        # Zod schemas, cn() utility
│   │   ├── hooks/
│   │   │   └── useForensicData.test.ts      # mapReportDtoToReport, hook state, file validation
│   │   └── components/
│   │       └── components.test.tsx          # FileUploadSection, AgentProgressDisplay rendering
│   ├── accessibility/
│   │   └── accessibility.test.tsx           # WCAG 2.1 AA — keyboard nav, ARIA, focus management
│   ├── integration/
│   │   └── page_flows.test.tsx              # Session flow, dedup fix, auth lifecycle
│   └── e2e/
│       └── websocket_flow.test.ts           # Full WS lifecycle, arbiter fix, deep analysis flow
│
├── backend/
│   ├── conftest.py                          # Shared fixtures: mocked Redis/Postgres/Qdrant, auth helpers
│   ├── unit/core/
│   │   ├── test_auth.py                     # JWT, bcrypt, RBAC, UserRole
│   │   └── test_config_signing_schemas.py   # Config loading, ECDSA signing, Pydantic DTOs
│   ├── integration/
│   │   └── test_api_routes.py               # All HTTP endpoints (TestClient, mocked infra)
│   └── security/
│       └── test_security.py                 # Auth bypass, injection, CORS, rate limits, crypto
│
├── infrastructure/
│   └── test_infrastructure.py               # docker-compose structure, Dockerfiles, env vars, CI
├── docker/
│   └── test_docker.py                       # Service config, ports, volumes, healthchecks
└── connectivity/
    └── test_connectivity.py                 # Live service pings (requires running stack)
```

---

## Running Tests

### Frontend (Jest — from `frontend/`)

```bash
cd frontend
npm test                      # Watch mode
npm test -- --watchAll=false  # One-shot (CI)
npm run test:coverage         # With coverage
```

### Backend + Infrastructure (pytest — from project root)

```bash
# Install test dependencies (one-time)
pip install pytest pytest-asyncio httpx pyyaml

# All backend tests
pytest tests/backend/ -v --tb=short

# All tests except connectivity (for CI / offline)
pytest tests/ --ignore=tests/frontend --ignore=tests/connectivity -v

# Specific categories
pytest tests/backend/unit/      -v   # Unit: JWT, config, signing, schemas
pytest tests/backend/integration/ -v # Routes: all HTTP endpoints (mocked infra)
pytest tests/backend/security/   -v  # Security: auth bypass, injection, CORS

# Infrastructure static analysis
pytest tests/infrastructure/ tests/docker/ -v

# With coverage
pytest tests/backend/ --cov=backend --cov-report=html
```

> **Important:** Run pytest from the **project root** directory, not from `backend/`. The root `pytest.ini` sets `pythonpath = . backend` so both `from core.auth` (direct) and `from backend.core.config` (prefixed) import styles resolve correctly.

### Connectivity Tests (requires running Docker stack)

```bash
./manage.sh up
# Wait for stack to be healthy, then:
pytest tests/connectivity/ -v
```

---

## Bug Fixes Covered by Tests

| Fix | Test Location |
|-----|---------------|
| Docker HOSTNAME=0.0.0.0 | `infrastructure/test_infrastructure.py::TestFrontendDockerfile` |
| Arbiter awaited before navigation | `frontend/e2e/websocket_flow.test.ts` |
| isNavigating double-click guard | `frontend/e2e/websocket_flow.test.ts` |
| Error resets isNavigating for retry | `frontend/e2e/websocket_flow.test.ts` |
| Duplicate findings deduplication | `frontend/integration/page_flows.test.tsx` |
| JWT 60-min expiry (was 7 days) | `backend/security/test_security.py` |
| Per-user rate limiting | `backend/security/test_security.py` |
| Bcrypt credential security | `backend/unit/core/test_auth.py` |
| ECDSA tamper detection | `backend/unit/core/test_config_signing_schemas.py` |
| Resume endpoint at correct URL | `backend/integration/test_api_routes.py` |
