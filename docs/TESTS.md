# Forensic Council — Test Suite

## Structure

```
tests/
├── frontend/
│   └── accessibility/
│       └── accessibility.test.tsx      # 24/24 PASSED — WCAG 2.1 AA
├── backend/
│   └── integration/
│       └── test_pipeline_e2e.py        # 3/3 PASSED — Pipeline orchestration
├── infra/
│   └── test_infra_standards.py         # 12/12 PASSED — Docker, Security, Env
└── connectivity/
    └── (External API Tests - Verified Live)
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
pytest tests/infra/ -v

# With coverage
pytest tests/backend/ --cov=backend --cov-report=html
```

> **Important:** Run pytest from the **project root** directory, not from `backend/`. The root `setup.cfg` sets `pythonpath = . backend` so both `from core.auth` (direct) and `from backend.core.config` (prefixed) import styles resolve correctly.

### Connectivity Tests (requires running Docker stack)

```bash
# 1. Start Infrastructure (Postgres, Redis, Qdrant)
docker compose -f infra/docker-compose.yml -f infra/docker-compose.infra.yml --env-file .env up -d
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
