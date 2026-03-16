# Forensic Council — Error Log

All production bugs and their resolutions, ordered chronologically.

---

## 2026-03-16 — Session 4: Backend Deep Audit

### Error: 404 on Every Resume (Accept/Deep Analysis Buttons Non-Functional)

**Symptom:** Frontend calls `POST /api/v1/sessions/{id}/resume` after `PIPELINE_PAUSED` message. Every call returns 404. Neither "Accept Analysis" nor "Deep Analysis" works — pipeline never progresses.

**Root Cause:** The resume endpoint lived in `investigation.py` (router prefix `/api/v1`) at route `/{session_id}/resume`, making its full path `POST /api/v1/{session_id}/resume`. The frontend called `/api/v1/sessions/{session_id}/resume`. These never matched.

**Fix:** Added `POST /{session_id}/resume` to `sessions.py` (router prefix `/api/v1/sessions`), making the full path `POST /api/v1/sessions/{session_id}/resume` — matching the frontend exactly.

---

### Error: Pydantic ValidationError on DB-loaded Reports After Restart

**Symptom:** After backend restart, loading any completed report returns a 503 with a Pydantic validation error. Reports loaded from memory (same process) work fine.

**Root Cause:** The DB report rebuild path in `sessions.py` constructed a `ReportDTO` without 5 required fields that were added in v1.0.3: `per_agent_metrics`, `per_agent_analysis`, `overall_confidence`, `overall_error_rate`, `overall_verdict`.

**Fix:** Added all 5 fields to the `_RD(...)` constructor in `get_session_report()` DB path.

---

### Error: PostgreSQL NOT NULL Constraint Violation on Investigation Error

**Symptom:** When an investigation fails, the error-handling callback crashes with `asyncpg.exceptions.NotNullViolationError` for `case_id` and `investigator_id`. The error status is never persisted.

**Root Cause:** `update_session_status()` in `session_persistence.py` ran `INSERT INTO session_reports` with empty strings `""` for `case_id` and `investigator_id` (both `NOT NULL`).

**Fix:** Changed to `UPDATE session_reports ... WHERE session_id = $1` — updates only if a row already exists (created by `save_report()` at investigation start).

---

### Error: Qdrant Connection Leak on Concurrent Startup

**Symptom:** Under concurrent startup (multiple coroutines calling `get_qdrant_client()` before the first connection resolves), multiple `QdrantClient` instances were created. Only the last one was stored in the singleton; the others leaked open gRPC connections.

**Root Cause:** `get_qdrant_client()` in `infra/qdrant_client.py` had no `asyncio.Lock`, unlike the Redis and Postgres singletons.

**Fix:** Added `asyncio.Lock` with double-checked locking pattern. Added missing `import asyncio`.

---

### Error: XSS via Report HTML Renderer

**Symptom:** A case ID containing `<script>alert(1)</script>` would execute JavaScript in any browser that viewed the HTML export of a report.

**Root Cause:** `render_html()` in `reports/report_renderer.py` inserted raw user-controlled fields (`case_id`, `executive_summary`, `uncertainty_statement`, agent IDs, finding types, report hash, cryptographic signature) directly into HTML f-strings without escaping.

**Fix:** Added `from html import escape as _esc` and wrapped every user-controlled field with `_esc()`.

---

### Error: Backend Tests Never Ran in CI

**Symptom:** CI showed green but no backend tests were actually executed. All test jobs passed with "no tests ran" or only collected from empty stubs.

**Root Cause:** The CI `backend-test` job ran `pytest tests/unit/` from `working-directory: backend`. The `backend/tests/` directory contains only empty `__init__.py` stubs; the actual test files with substance are at `tests/backend/` in the project root.

**Fix:** Changed CI to run from project root: `pytest tests/backend/ tests/infrastructure/ tests/docker/`.

---

### Error: `ImportError: No module named 'core'` / `ModuleNotFoundError: No module named 'backend'`

**Symptom:** Running `pytest tests/backend/` from project root fails immediately. `test_auth.py` crashes with `ImportError: No module named 'core'`. `test_config_signing_schemas.py` crashes with `ModuleNotFoundError: No module named 'backend'`.

**Root Cause:** Two issues:
1. Root `pytest.ini` lacked `pythonpath` — Python couldn't find `core`, `infra`, etc.
2. `backend/` had no `__init__.py` — `from backend.core.config import ...` always failed.

**Fix:** Added `pythonpath = . backend` to `pytest.ini` and created `backend/__init__.py`.

---

## 2026-03-16 — Session 1: Frontend Audit

### Error: TypeError — `visibleAgents[0].id` on Empty Array

**File:** `frontend/src/components/evidence/AgentProgressDisplay.tsx`

**Root Cause:** `visibleAgents[0].id` accessed without null check when `visibleAgents` was empty.

**Fix:** Added optional chaining: `const firstVisibleAgent = visibleAgents[0]; const firstVisibleId = firstVisibleAgent ? firstVisibleAgent.id : null;`

---

### Error: `as unknown as string` Double Cast

**File:** `frontend/src/app/evidence/page.tsx`

**Root Cause:** `investigatorIdRef.current as unknown as string` — the ref was already typed `useRef<string>`.

**Fix:** Removed the unnecessary double cast.

---

### Error: Jest Fails to Install — `jest-util@^30.2.0` Incompatible

**Symptom:** `npm install` fails; `jest-util@^30.x` is incompatible with `jest@29.x`.

**Fix:** Removed `jest-util` from `package.json` devDependencies entirely.

---

### Error: WCAG 2.1 — Logo Not Keyboard Navigable

**File:** `frontend/src/components/evidence/HeaderSection.tsx`

**Root Cause:** Logo rendered as a plain `<div onClick>` — not focusable, no keyboard handler, no ARIA role.

**Fix:** Added `role="button"`, `tabIndex={0}`, `onKeyDown` (Enter/Space), `aria-label="Return to Forensic Council home"`.

---

### Error: WCAG 2.1 — Textarea Missing Label Association

**File:** `frontend/src/components/evidence/HITLCheckpointModal.tsx`

**Root Cause:** `<label>` and `<textarea>` had no linking `id`/`htmlFor` attributes.

**Fix:** Added `id="hitl-notes"` to textarea and `htmlFor="hitl-notes"` to label.
