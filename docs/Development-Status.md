# Development Status

**Last updated:** 2026-03-24
**Current version:** v1.0.4
**Overall health:** 🟢 Production-ready
**Actively working on:** — Done
**Blocked on:** None

---

## Pipeline Health

```
Upload → [✅] → Evidence Store → [✅] → Agent Dispatch → [✅] → Council Arbiter → [✅] → Signing → [✅] → Report
```

| Stage | Status | Notes |
|-------|--------|-------|
| File Upload | ✅ | MIME + extension allowlists, 50 MB limit, non-blocking async I/O |
| Evidence Store | ✅ | Immutable storage with SHA-256 integrity check |
| WebSocket Stream | ✅ | JWT auth on connect, CONNECTED/AGENT_UPDATE bootstrap, CancelledError re-raised |
| Agent Dispatch | ✅ | All 5 agents sequential; file-type validation per agent; heartbeat every 0.2s |
| Initial Analysis | ✅ | Tools run → Groq synthesises findings → PIPELINE_PAUSED → Accept/Deep buttons |
| Deep Analysis | ✅ | Agent1 Gemini runs first → context injected into Agent3+Agent5 → fresh deep cards |
| Council Arbiter | ✅ | Skipped agents filtered; deduplication; 5-tier verdict; per-agent Groq narrative |
| Report Signing | ✅ | ECDSA P-256 + SHA-256, PostgreSQL custody log |
| Result Page | ✅ | Pre-computed verdict, per-agent analysis, initial/deep split, client-side dedup |

---

## Complete Fix Log

### Session 4 (2026-03-16) — Infrastructure, Connectivity & Backend Audit

| # | File | Issue | Fix |
|---|------|-------|-----|
| S4-1 | `api/routes/sessions.py` | Resume endpoint missing at `/api/v1/sessions/{id}/resume` — frontend 404 on every "Accept Analysis" / "Deep Analysis" click | Added `POST /{session_id}/resume` to `sessions.py` router (prefix `/api/v1/sessions`) |
| S4-2 | `api/routes/sessions.py` (DB rebuild path) | `ReportDTO` constructed without 5 required fields: `per_agent_metrics`, `per_agent_analysis`, `overall_confidence`, `overall_error_rate`, `overall_verdict` — Pydantic validation error on every DB-loaded report | Added all 5 fields to `_RD(...)` constructor in DB rebuild path |
| S4-3 | `core/session_persistence.py` | `update_session_status` error path: `INSERT INTO session_reports` with empty `""` strings for `NOT NULL` columns `case_id` / `investigator_id` — PostgreSQL constraint violation when investigation fails | Changed to `UPDATE session_reports ... WHERE session_id = $1` |
| S4-4 | `infra/qdrant_client.py` | Singleton `get_qdrant_client()` had no `asyncio.Lock` — race condition under concurrent startup creates multiple QdrantClient instances (connection leak) | Added `asyncio.Lock` with double-checked locking; added missing `import asyncio` |
| S4-5 | `reports/report_renderer.py` | `render_html()` inserted raw user-controlled fields (`case_id`, `executive_summary`, etc.) into HTML without escaping — XSS vector | Added `from html import escape as _esc`; wrapped all user fields |
| S4-6 | `infra/postgres_client.py` | `TransactionContext.fetch()` and `fetch_one()` passed raw args without `json.dumps(dict)` conversion — inconsistency with all other methods | Added dict→JSON processing to both methods |
| S4-7 | `setup.cfg` (root) | Missing `pythonpath` setting — `from core.auth` raises `ImportError`; `from backend.core.config` raises `ModuleNotFoundError` | Added `pythonpath = . backend` |
| S4-8 | `backend/__init__.py` | Missing — `from backend.core.config` always raised `ModuleNotFoundError: No module named 'backend'` | Created empty `backend/__init__.py` |
| S4-9 | `.github/workflows/ci.yml` | `pytest tests/unit/` ran from `backend/` directory where only empty `__init__.py` stubs exist — tests never executed | Fixed to `pytest tests/backend/ tests/infrastructure/ tests/docker/` from project root |

### Session 3 (2026-03-16) — Full Infrastructure & Connectivity Audit

| # | File | Issue | Fix |
|---|------|-------|-----|
| S3-1 | `api/routes/sessions.py` | DB report rebuild missing 5 required `ReportDTO` fields (all new fields) | Added `per_agent_metrics`, `per_agent_analysis`, `overall_confidence`, `overall_error_rate`, `overall_verdict` |

### Session 2 (2026-03-16) — Docker Fixes

| # | File | Issue | Fix |
|---|------|-------|-----|
| S2-1 | `docs/docker/docker-compose.yml` | Caddy `ports:` key missing — YAML dangled port entries under `restart:` — entire stack refused to start | Added `ports:` key before port list |
| S2-2 | `docs/docker/README.md` (line 221) | "Starting Infrastructure Only" showed wrong standalone command for infra-only | Corrected to proper compose overlay command |
| S2-3 | `docs/docker/README.md` (line 362) | Management table had same wrong infra command | Same fix |
| S2-4 | `docs/docker/README.md` (line 415–417) | Troubleshooting showed non-existent tmpfs path `/app/storage/temp` | Replaced with actual compose paths |

### Session 1 (2026-03-16) — Frontend Audit

| # | File | Issue | Fix |
|---|------|-------|-----|
| S1-1 | `result/page.tsx` | Duplicate `PageTransition` and `GlobalFooter` imports — compile error | Removed duplicates |
| S1-2 | `result/page.tsx` | Orphaned `</PageTransition>` and `<GlobalFooter />` JSX tags inside `ArbiterOverlay` — compile error | Removed stray tags |
| S1-3 | `result/page.tsx` | `AgentSection` metrics prop typed as `as any` | Imported `AgentMetricsDTO`; typed props and filter correctly |
| S1-4 | `result/page.tsx` | Unused `Eye` import from lucide-react — ESLint error | Removed |
| S1-5 | `useSimulation.ts` | Resume URL wrong: `/api/v1/${targetId}/resume` (missing `/sessions/`) — 404 on every resume | Fixed to `/api/v1/sessions/${targetId}/resume` |
| S1-6 | `evidence/page.tsx` | Double cast `investigatorIdRef.current as unknown as string` on already-string ref | Removed double cast |
| S1-7 | `useSimulation.ts` | `update.data as any` in AGENT_COMPLETE handler | Replaced with `Record<string, unknown>` + runtime type guards |
| S1-8 | `useSimulation.ts` | `newUpdate as any` for legacy callback | Changed to `newUpdate as AgentResult` |
| S1-9 | `components/evidence/HeaderSection.tsx` | Logo `<div onClick>` keyboard-inaccessible | Added `role="button"`, `tabIndex={0}`, `onKeyDown`, `aria-label` |
| S1-10 | `components/evidence/HITLCheckpointModal.tsx` | `<label>` not associated with `<textarea>` | Added matching `id` / `htmlFor` |
| S1-11 | `frontend/package.json` | `jest-util@^30.2.0` incompatible with `jest@29` | Removed |
| S1-12 | `evidence/page.tsx`, `result/page.tsx` | Bare `console.error` in production paths | Added dev-only `dbg` logger |
| S1-13 | Test fixtures (4 files) | `ReportDTO` missing 5 required fields in test fixtures | Added all fields to all fixtures |

---

## Known Limitations

| Area | Limitation |
|------|------------|
| Agent execution | Sequential within each phase (not parallel) to maintain stable WebSocket streaming and predictable memory usage |
| LLM inference | No fallback LLM if Groq/Gemini API is unavailable during analysis — investigation degrades to tool-only mode |
| Video analysis | Frame extraction is CPU-intensive; files >200 MB may timeout on slow machines (per-agent 180s limit) |
| Deep analysis timing | Agent1 Gemini runs sequentially before Agent3/Agent5 to enable context sharing (~30–90s additional) |
| Token blacklisting | Redis unavailability causes all tokens to be treated as revoked (fail-secure design — intentional) |
