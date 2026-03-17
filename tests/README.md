# Forensic Council — Test Suite Quick Reference

**Version:** v1.0.4

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
│   ├── conftest.py
│   ├── unit/core/      test_auth.py, test_config_signing_schemas.py
│   ├── integration/    test_api_routes.py
│   └── security/       test_security.py
├── infrastructure/     test_infrastructure.py
├── docker/             test_docker.py
└── connectivity/       test_connectivity.py  (requires running stack)
```

---

## Running Tests

### Frontend (from `frontend/`)

```bash
cd frontend
npm test -- --watchAll=false      # CI mode (one-shot)
npm test                          # Watch mode (development)
npm run test:coverage             # With coverage report
```

### Backend (from **project root**)

```bash
pip install pytest pytest-asyncio httpx pyyaml

# All non-connectivity tests
pytest tests/ --ignore=tests/frontend --ignore=tests/connectivity -v

# Backend only
pytest tests/backend/ -v

# With coverage
pytest tests/backend/ --cov=backend --cov-report=html
```

### Connectivity (requires running Docker stack)

```bash
./manage.sh up
pytest tests/connectivity/ -v
```

---

## Coverage by Area

| Area | Files | What's Validated |
|------|-------|-----------------|
| **Frontend Unit** | 3 | Token auth, Zod schemas, hooks, component rendering |
| **Frontend A11y** | 1 | WCAG 2.1 AA: keyboard nav, ARIA, focus, error announcements |
| **Frontend Integration** | 1 | Session flow, dedup fix, report mapping |
| **Frontend E2E** | 1 | WebSocket full lifecycle, arbiter fix, polling |
| **Backend Unit** | 2 | JWT, bcrypt, RBAC, config, ECDSA signing, Pydantic schemas |
| **Backend Integration** | 1 | All HTTP endpoints, security headers, request validation |
| **Backend Security** | 1 | Auth bypass, injection, CORS, rate limits, JWT forgery |
| **Infrastructure** | 1 | docker-compose structure, Dockerfiles, env vars, CI |
| **Docker** | 1 | Compose service config, healthchecks, volumes, resource limits |
| **Connectivity** | 1 | Live Redis/Postgres/Qdrant ping, API health, WebSocket handshake |

---

## Bug Fixes Covered by Tests

| Fix | Test |
|-----|------|
| Docker HOSTNAME=0.0.0.0 | `infrastructure/test_infrastructure.py` |
| Frontend healthcheck uses wget | `docker/test_docker.py` |
| Arbiter awaited before router.push | `frontend/e2e/websocket_flow.test.ts` |
| isNavigating double-click guard | `frontend/e2e/websocket_flow.test.ts` |
| Error resets isNavigating for retry | `frontend/e2e/websocket_flow.test.ts` |
| Duplicate findings deduplication | `frontend/integration/page_flows.test.tsx` |
| JWT 60-min expiry (was 7 days) | `backend/security/test_security.py` |
| Per-user rate limiting | `backend/security/test_security.py` |
| Bcrypt credential security | `backend/unit/core/test_auth.py` |
| ECDSA tamper detection | `backend/unit/core/test_config_signing_schemas.py` |
| Resume endpoint correct URL | `backend/integration/test_api_routes.py` |

Full documentation → [`../docs/test/TESTING.md`](../docs/test/TESTING.md)
