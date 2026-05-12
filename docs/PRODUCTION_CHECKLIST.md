# Production Checklist

## Purpose

This checklist tracks whether Forensic Council is ready for production deployment.

This file is documentation only. It does not prove production readiness by itself. Update it after running real local, CI, Docker, and deployment checks.

---

## Current Status

```text
Not yet verified.
```

---

## 1. Build Verification

### Frontend non-Docker build

**Command:**

```bash
cd apps/web
npm ci
npm run type-check
npm run lint
npm run test
npm run build
```

**Status:** not run

### Backend non-Docker verification

**Command:**

```bash
cd apps/api
uv sync --extra dev --extra security --extra observability
uv run pytest
```

**Status:** not run

### Backend ML verification

**Command:**

```bash
cd apps/api
uv sync --extra dev --extra security --extra observability --extra ml
uv run python scripts/model_pre_download.py --strict
uv run python scripts/validate_ml_tools.py
```

**Status:** not run

### Docker development build

**Command:**

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env up --build
```

**Status:** not run

### Docker production-style build

**Command:**

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file .env up --build
```

**Status:** not run

---

## 2. Frontend Production Readiness

| Check | Status | Notes |
|---|---|---|
| Landing page loads | not verified | |
| Upload modal works | not verified | |
| Evidence route works | not verified | |
| Investigation starts | not verified | |
| WebSocket progress works | not verified | |
| HITL modal works | not verified | |
| Result route works | not verified | |
| Report download works | not verified | |
| Error boundaries work | not verified | |
| Accessibility tests pass | not verified | |
| No frontend secrets exposed | not verified | |

---

## 3. Backend Production Readiness

| Check | Status | Notes |
|---|---|---|
| API starts successfully | not verified | |
| Health endpoint works | not verified | |
| Auth works | not verified | |
| JWT production settings configured | not verified | |
| CORS production settings configured | not verified | |
| Upload validation works | not verified | |
| MIME validation works | not verified | |
| File hashing works | not verified | |
| Evidence storage works | not verified | |
| Investigation pipeline works | not verified | |
| Worker mode works | not verified | |
| WebSocket live updates work | not verified | |
| SSE fallback works | not verified | |
| HITL works | not verified | |
| Report generation works | not verified | |
| PDF export works | not verified | |
| Report signing works | not verified | |
| Custody chain works | not verified | |
| Rate limiting works | not verified | |
| Quota meter works | not verified | |
| Metrics work | not verified | |
| Webhooks work if enabled | not verified | |

---

## 4. ML and Agent Readiness

| Check | Status | Notes |
|---|---|---|
| Model cache directory exists | not verified | |
| Model predownload script works | not verified | |
| ML validation script works | not verified | |
| Agent 1 image works | not verified | |
| Agent 2 audio works | not verified | |
| Agent 3 object works | not verified | |
| Agent 4 video works | not verified | |
| Agent 5 metadata works | not verified | |
| Arbiter works | not verified | |
| Degraded mode is visible | not verified | |
| Research model gate works | not verified | |
| AGPL model gate works | not verified | |

---

## 5. Security Readiness

| Check | Status | Notes |
|---|---|---|
| Production secrets generated | not verified | |
| JWT secret is strong | not verified | |
| Signing keys generated | not verified | |
| Secrets are not committed | not verified | |
| CORS is restricted | not verified | |
| Rate limiting enabled | not verified | |
| Upload size limits enforced | not verified | |
| MIME allowlist enforced | not verified | |
| Path traversal prevented | not verified | |
| Security headers present | not verified | |
| Auth brute-force protection works | not verified | |
| Token refresh/logout works | not verified | |
| Report signing verified | not verified | |

---

## 6. Data and Persistence Readiness

| Check | Status | Notes |
|---|---|---|
| PostgreSQL starts | not verified | |
| Redis starts | not verified | |
| Qdrant starts | not verified | |
| Alembic migrations run | not verified | |
| Evidence storage persists | not verified | |
| Reports persist | not verified | |
| Retention cleanup works | not verified | |
| Backup script works | not verified | |
| WAL cleanup works | not verified | |

---

## 7. Observability Readiness

| Check | Status | Notes |
|---|---|---|
| Prometheus metrics exposed | not verified | |
| Jaeger tracing works | not verified | |
| Structured logs present | not verified | |
| Request IDs present | not verified | |
| Pipeline errors observable | not verified | |
| Worker healthcheck works | not verified | |
| ML degradation observable | not verified | |

---

## 8. Documentation Readiness

| Check | Status | Notes |
|---|---|---|
| AGENTS.md exists | not verified | |
| PROJECT_HANDOFF.md exists | not verified | |
| docs/AI_CONTEXT.md exists | not verified | |
| docs/FRONTEND_FLOW.md exists | not verified | |
| docs/BACKEND_FLOW.md exists | not verified | |
| docs/ROUTES_AND_APIS.md exists | not verified | |
| docs/ML_AGENTS.md exists | not verified | |
| README is current | not verified | |
| API docs are current | not verified | |
| Architecture docs are current | not verified | |
| Security docs are current | not verified | |
| Runbook is current | not verified | |

---

## 9. Release Gate

Before marking production-ready, all of the following should be true:

- [ ] frontend type-check passes
- [ ] frontend lint passes
- [ ] frontend tests pass
- [ ] frontend production build passes
- [ ] backend tests pass
- [ ] backend API starts
- [ ] database migrations pass
- [ ] Docker dev stack starts
- [ ] Docker production-style stack starts
- [ ] investigation happy path works
- [ ] report generation works
- [ ] report PDF/download works
- [ ] WebSocket live updates work
- [ ] HITL flow works
- [ ] security validation passes
- [ ] production readiness script passes
- [ ] secrets are not committed

---

## 10. Production Readiness Script

**Script:** `infra/validate_production_readiness.sh`

**Command:**

```bash
./infra/validate_production_readiness.sh
```

**Status:** not run

---

## 11. Key Production Files

- `infra/docker-compose.yml`
- `infra/docker-compose.prod.yml`
- `infra/Caddyfile`
- `infra/prometheus.yml`
- `infra/generate_production_keys.sh`
- `infra/validate_production_readiness.sh`
- `apps/api/Dockerfile`
- `apps/web/Dockerfile`
- `apps/api/core/config.py`
- `apps/web/next.config.ts`

---

## 12. Final Signoff

| Area | Owner | Status | Date |
|---|---|---|---|
| Frontend | | not signed off | |
| Backend | | not signed off | |
| ML/Agents | | not signed off | |
| Security | | not signed off | |
| Infrastructure | | not signed off | |
| Documentation | | not signed off | |