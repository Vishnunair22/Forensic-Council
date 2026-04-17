# Forensic Council â€” Error Log

All production bugs and their resolutions, ordered chronologically.

---

## 2026-03-16 â€” Session 5: Full Runtime Audit (v1.0.4)

### Error: Report 404 After Investigation Completes (Race Window)

**Symptom:** Result page polls `/arbiter-status` â†’ gets `"complete"` â†’ fetches `/report` â†’ 404. Intermittent â€” depends on timing.

**Root Cause:** `run_investigation_task()` set `pipeline._final_report = report` but the `finally` block immediately removed the pipeline from `_active_pipelines`. The in-memory `_final_reports` cache was never populated, so between pipeline eviction and DB persistence completing, the report endpoint had no source to read from.

**Fix:** Cache report in `_final_reports[session_id]` immediately after setting `pipeline._final_report`, before the `finally` block executes.

---

### Error: AttributeError: `_custody_logger` in Inter-Agent Calls

**Symptom:** Agents 2, 3, and 4 crash when making collaborative inter-agent calls (e.g. Agent2 â†’ Agent4 for A/V sync).

**Root Cause:** Inter-agent call handlers referenced `self._custody_logger` (underscore prefix), but `ForensicAgent.__init__()` stores the logger as `self.custody_logger` (no underscore).

**Fix:** Changed `self._custody_logger` â†’ `self.custody_logger` in `agent2_audio.py`, `agent3_object.py`, `agent4_video.py`.

---

### Error: WorkingMemory Crashes When Redis Has Transient Blip

**Symptom:** During Redis reconnection (e.g. container restart), every agent crashes with `ValueError`. Heartbeat loop generates error storms (200ms polling).

**Root Cause:** `get_state()` raised `ValueError` when Redis was `None` or returned an error, with no fallback path.

**Fix:** Added `_local_cache` in-memory dict. All write operations persist to both Redis and local cache. `get_state()` falls back to local cache on Redis failure.

---

### Error: CustodyLogger DB Error Kills Entire Investigation

**Symptom:** Single PostgreSQL timeout during chain-of-custody logging crashes the entire pipeline.

**Root Cause:** The `INSERT INTO chain_of_custody` was not wrapped in try/except. Each agent generates dozens of custody entries per investigation.

**Fix:** Wrapped DB insert in try/except. On failure, logs error and returns entry_id so callers continue.

---

### Error: Frontend Hangs Waiting for Unsupported Agents

**Symptom:** When uploading audio files, UI hangs on "Gathering findings..." because `allAgentsDone` never becomes true.

**Root Cause:** Backend sends `"Not applicable for audio files"` but frontend only matched `"not supported"` and `"Format not supported"`.

**Fix:** Added `"Not applicable"`, `"not applicable"`, and `"Skipping"` to frontend unsupported-agent filter.

---

### Config: Docker-compose LLM_MODEL Default Mismatch

**Symptom:** Fresh Docker deployment with no LLM_MODEL in .env defaults to `gpt-4o` instead of `llama-3.3-70b-versatile`.

**Fix:** Changed `LLM_MODEL=${LLM_MODEL:-gpt-4o}` â†’ `LLM_MODEL=${LLM_MODEL:-llama-3.3-70b-versatile}` in `docker-compose.yml`.

---

### Config: .env.example GEMINI_TIMEOUT Mismatch

**Symptom:** Default GEMINI_TIMEOUT was 30.0s in .env.example but 55.0s in config.py. Deep forensic analysis needs the longer timeout.

**Fix:** Updated .env.example to `GEMINI_TIMEOUT=55.0`.

---

## 2026-03-16 â€” Session 4: Backend Deep Audit

### Error: 404 on Every Resume (Accept/Deep Analysis Buttons Non-Functional)

**Symptom:** Frontend calls `POST /api/v1/sessions/{id}/resume` after `PIPELINE_PAUSED` message. Every call returns 404. Neither "Accept Analysis" nor "Deep Analysis" works â€” pipeline never progresses.

**Root Cause:** The resume endpoint lived in `investigation.py` (router prefix `/api/v1`) at route `/{session_id}/resume`, making its full path `POST /api/v1/{session_id}/resume`. The frontend called `/api/v1/sessions/{session_id}/resume`. These never matched.

**Fix:** Added `POST /{session_id}/resume` to `sessions.py` (router prefix `/api/v1/sessions`), making the full path `POST /api/v1/sessions/{session_id}/resume` â€” matching the frontend exactly.

---

### Error: Pydantic ValidationError on DB-loaded Reports After Restart

**Symptom:** After backend restart, loading any completed report returns a 503 with a Pydantic validation error. Reports loaded from memory (same process) work fine.

**Root Cause:** The DB report rebuild path in `sessions.py` constructed a `ReportDTO` without 5 required fields that were added in v1.0.3: `per_agent_metrics`, `per_agent_analysis`, `overall_confidence`, `overall_error_rate`, `overall_verdict`.

**Fix:** Added all 5 fields to the `_RD(...)` constructor in `get_session_report()` DB path.

---

### Error: PostgreSQL NOT NULL Constraint Violation on Investigation Error

**Symptom:** When an investigation fails, the error-handling callback crashes with `asyncpg.exceptions.NotNullViolationError` for `case_id` and `investigator_id`. The error status is never persisted.

**Root Cause:** `update_session_status()` in `session_persistence.py` ran `INSERT INTO session_reports` with empty strings `""` for `case_id` and `investigator_id` (both `NOT NULL`).

**Fix:** Changed to `UPDATE session_reports ... WHERE session_id = $1` â€” updates only if a row already exists (created by `save_report()` at investigation start).

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

**Root Cause:** The CI `backend-test` job ran `pytest tests/unit/` from `working-directory: backend`. The `apps/api/tests/` directory contains only empty `__init__.py` stubs; the actual test files with substance are at `tests/apps/api/` in the project root.

**Fix:** Changed CI to run from project root: `pytest tests/apps/api/ tests/infrastructure/ tests/docker/`.

---

### Error: `ImportError: No module named 'core'` / `ModuleNotFoundError: No module named 'backend'`

**Symptom:** Running `pytest tests/apps/api/` from project root fails immediately. `test_auth.py` crashes with `ImportError: No module named 'core'`. `test_config_signing_schemas.py` crashes with `ModuleNotFoundError: No module named 'backend'`.

**Root Cause:** Two issues:
1. Root `setup.cfg` lacked `pythonpath` â€” Python couldn't find `core`, `infra`, etc.
2. `apps/api/` had no `__init__.py` â€” `from backend.core.config import ...` always failed.

**Fix:** Added `pythonpath = . backend` to root `setup.cfg` and created `apps/api/__init__.py`.

---

## 2026-03-16 â€” Session 1: Frontend Audit

### Error: TypeError â€” `visibleAgents[0].id` on Empty Array

**File:** `apps/web/src/components/evidence/AgentProgressDisplay.tsx`

**Root Cause:** `visibleAgents[0].id` accessed without null check when `visibleAgents` was empty.

**Fix:** Added optional chaining: `const firstVisibleAgent = visibleAgents[0]; const firstVisibleId = firstVisibleAgent ? firstVisibleAgent.id : null;`

---

### Error: `as unknown as string` Double Cast

**File:** `apps/web/src/app/evidence/page.tsx`

**Root Cause:** `investigatorIdRef.current as unknown as string` â€” the ref was already typed `useRef<string>`.

**Fix:** Removed the unnecessary double cast.

---

### Error: Jest Fails to Install â€” `jest-util@^30.2.0` Incompatible

**Symptom:** `npm install` fails; `jest-util@^30.x` is incompatible with `jest@29.x`.

**Fix:** Removed `jest-util` from `package.json` devDependencies entirely.

---

### Error: WCAG 2.1 â€” Logo Not Keyboard Navigable

**File:** `apps/web/src/components/evidence/HeaderSection.tsx`

**Root Cause:** Logo rendered as a plain `<div onClick>` â€” not focusable, no keyboard handler, no ARIA role.

**Fix:** Added `role="button"`, `tabIndex={0}`, `onKeyDown` (Enter/Space), `aria-label="Return to Forensic Council home"`.

---

### Error: WCAG 2.1 â€” Textarea Missing Label Association

**File:** `apps/web/src/components/evidence/HITLCheckpointModal.tsx`

**Root Cause:** `<label>` and `<textarea>` had no linking `id`/`htmlFor` attributes.

**Fix:** Added `id="hitl-notes"` to textarea and `htmlFor="hitl-notes"` to label.

---

---

## 2026-04-11 â€” Forensic OS 2026 Hardening (v1.3.0)

### Audit: Documentation & Root Hygiene
- **Verified**: Full audit of `docs/` directory completed. All architectural specs, API references, and security policies synchronized with v1.3.0 code.
- **Improved**: Relocated `apps/api/test_initial_analysis.py` to `tests/integration/` to maintain root cleanliness.
- **Improved**: Consolidated agent diagnostic tools into `docs/agent_capabilities.md` with "Court Defensible" status verification.

### Hardening: Multi-Agent Parallelism & Grounding
- **Verified**: Hybrid sequential/concurrent agent execution flow correctly handles Agent 1 (Initial) â†’ Agent 3/5 (Deep) context injection.
- **Verified**: ECDSA P-256 deterministic key derivation (HMAC-SHA-256) robustly separate agent-level signing authorities.
- **Updated**: Metadata Agent (Agent 5) now includes **C2PA JUMBF Validation** and hardware provenance cross-correlation.

### Infrastructure & Resilience
- **Hardened**: Redis-backed rate limiter and session state store confirmed to handle OOM degradation gracefully via Lua atomicity.
- **Hardened**: PostgreSQL immutable forensic ledger verified for tamper-evident sequential hashing.
- **Warning**: Added hardware peak load warnings (15GB RAM) to `ARCHITECTURE.md` to prevent deployment OOMs in Deep Analysis phase.

