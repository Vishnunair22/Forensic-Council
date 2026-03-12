# Forensic Council — Test Suite

**Version:** v1.0.3 | **Coverage target:** ≥ 80% frontend, ≥ 75% backend

---

## Structure

```
tests/
├── frontend/
│   ├── unit/
│   │   ├── lib/        api.test.ts, schemas_utils.test.ts
│   │   ├── hooks/      useForensicData.test.ts
│   │   └── components/ components.test.tsx
│   ├── accessibility/  accessibility.test.tsx
│   ├── integration/    page_flows.test.tsx
│   └── e2e/            websocket_flow.test.ts
├── backend/
│   ├── unit/core/      test_auth.py, test_config.py, test_signing_schemas.py
│   ├── integration/    test_api_routes.py
│   └── security/       test_security.py
├── infrastructure/     test_infrastructure.py
├── docker/             test_docker.py
├── connectivity/       test_connectivity.py
└── README.md           (this file)
```

---

## Running Tests

### Frontend (Jest — from `frontend/`)

```bash
cd frontend
npm test                          # All tests (watches by default)
npm test -- --watchAll=false      # Run once
npm run test:coverage             # With coverage report
```

Jest is configured in `frontend/jest.config.ts` to find test files in `tests/frontend/**`.

### Backend (pytest — from project root or `backend/`)

```bash
# Install test dependencies first (one-time)
pip install pytest pytest-asyncio httpx pyyaml

# Run all test categories
pytest tests/backend/   -v --tb=short        # Backend unit + integration + security
pytest tests/infrastructure/ -v --tb=short   # Docker Compose / Dockerfile static checks
pytest tests/docker/    -v --tb=short        # Docker runtime & config checks
pytest tests/connectivity/ -v --tb=short     # Service connectivity (requires running stack)

# Run everything
pytest tests/ -v --ignore=tests/frontend --tb=short

# With coverage
pytest tests/backend/ --cov=backend --cov-report=html
```

### Connectivity Tests (requires running Docker stack)

```bash
# Start the stack first
./manage.sh up   # or: docker compose -f docs/docker/docker-compose.yml --env-file .env up -d

# Run connectivity tests
pytest tests/connectivity/ -v
```

---

## Coverage by Area

| Area | Tests | What's Validated |
|---|---|---|
| **Frontend Unit** | 3 files | Token auth, Zod schemas, hooks, component rendering |
| **Frontend A11y** | 1 file | WCAG 2.1 AA: keyboard nav, ARIA, focus, error announcements |
| **Frontend Integration** | 1 file | Session flow, dedup fix, report mapping |
| **Frontend E2E** | 1 file | WebSocket full lifecycle, arbiter fix, polling |
| **Backend Unit** | 3 files | JWT, bcrypt, RBAC, config, ECDSA signing, Pydantic schemas |
| **Backend Integration** | 1 file | All HTTP endpoints, security headers, request validation |
| **Backend Security** | 1 file | Auth bypass, injection, CORS, rate limits, JWT forgery |
| **Infrastructure** | 1 file | docker-compose structure, Dockerfiles, env vars, CI |
| **Docker** | 1 file | Compose service config, healthchecks, volumes, resource limits |
| **Connectivity** | 1 file | Live Redis/Postgres/Qdrant ping, API health, WebSocket handshake |

---

## Bug Fixes Covered by Tests

| Fix | Test |
|---|---|
| Docker HOSTNAME=0.0.0.0 binding | `docker/test_docker.py::TestFrontendDockerfile` |
| Frontend healthcheck uses wget | `docker/test_docker.py::TestFrontendDockerfile` |
| Arbiter awaited before router.push | `frontend/e2e/websocket_flow.test.ts` |
| isNavigating double-click guard | `frontend/e2e/websocket_flow.test.ts` |
| Error resets isNavigating | `frontend/e2e/websocket_flow.test.ts` |
| Duplicate findings deduplication | `frontend/integration/page_flows.test.tsx` |
| Sound effects subtle redesign | `frontend/unit/components/components.test.tsx` |
| JWT 60-min expiry (was 7 days) | `backend/security/test_security.py` |
| Per-user rate limiting | `backend/security/test_security.py` |
| Bcrypt credential security | `backend/unit/core/test_auth.py` |
