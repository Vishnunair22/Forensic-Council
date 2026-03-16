# Forensic Council — Test Suite

## Structure

```
tests/frontend/
├── accessibility/
│   └── accessibility.test.tsx         # WCAG 2.1 AA — keyboard nav, ARIA, focus management
├── unit/
│   ├── lib/
│   │   ├── api.test.ts                 # Token management, login/logout, WebSocket, polling
│   │   └── schemas_utils.test.ts       # Zod schemas, cn() utility
│   ├── hooks/
│   │   └── useForensicData.test.ts     # mapReportDtoToReport, state, CRUD, file validation
│   └── components/
│       └── components.test.tsx         # FileUploadSection, AgentProgressDisplay, AgentIcon
├── integration/
│   └── page_flows.test.tsx             # Session flow, deduplication fix, auth lifecycle
└── e2e/
    └── websocket_flow.test.ts          # Full WS lifecycle, arbiter fix, report polling

backend/tests/
├── conftest.py                         # Shared fixtures
├── unit/core/
│   ├── test_auth.py                    # JWT, bcrypt, RBAC
│   ├── test_config.py                  # Settings, env validation
│   └── test_signing_and_schemas.py     # ECDSA signing, Pydantic schemas
├── integration/
│   └── test_api_routes.py              # HTTP routes, security headers, auth
├── security/
│   └── test_security.py               # Injection, JWT bypass, CORS, rate limits
├── infrastructure/
│   └── test_infrastructure.py          # Docker Compose, Dockerfiles, env vars, CI
└── performance/
    └── test_performance.py             # Response times, crypto perf, concurrency
```

## Running Tests

### Frontend
```bash
cd frontend
npm test                    # All tests
npm run test:coverage       # With coverage
```

### Backend
```bash
cd backend
pip install pytest pytest-asyncio httpx pyyaml
pytest tests/ -v                         # All tests
pytest tests/unit/ -v                    # Unit only
pytest tests/security/ -v               # Security only
pytest tests/infrastructure/ -v         # Docker/infra only
pytest tests/performance/ -v            # Performance only
pytest tests/ --cov=. --cov-report=html # With coverage
```

## Key Bug Fixes Validated

| Fix | Test Location |
|-----|---------------|
| Docker HOSTNAME=0.0.0.0 | `infrastructure/test_infrastructure.py::TestFrontendDockerfile` |
| Arbiter awaited before navigation | `e2e/websocket_flow.test.ts::TestNavigationAfterArbiiterFix` |
| Double-click guard on accept | `e2e/websocket_flow.test.ts` — isNavigating guard test |
| Duplicate findings dedup | `integration/page_flows.test.tsx::TestReportDeduplication` |
| isNavigating disables buttons | `unit/components/components.test.tsx::AgentProgressDisplay` |
