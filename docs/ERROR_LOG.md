# Forensic Council — Error Log

All production bugs and their resolutions, ordered chronologically.

---

## 2026-04-27 — Session 7: Identity Hardening & Infrastructure Audit

### Error: 0xFC_PIPELINE_HALT / 403 Forbidden on Investigation Start

**Symptom:** Every new investigation fails immediately with a "You do not have access to this investigation" error. WebSocket/SSE connections return 403 Forbidden.

**Root Cause:** Identity mismatch in `assert_session_access()`. The frontend was sending a case label (e.g., `REQ-123456`) as the `investigator_id`. The backend stored this label in Redis metadata but compared it against the actual Database User UUID from the JWT during auth checks. Since `REQ-123456` != `UUID`, access was denied.

**Fix:**
- **`investigation.py`**: Updated initial metadata write to store `current_user.user_id` (UUID) as `investigator_id` and preserved the frontend label in `case_investigator_label`.
- **`investigation.py`**: Updated the 409 Deduplication path to "re-claim" ownership by updating the `investigator_id` of the existing session to the current user's UUID.
- **`investigation_runner.py` & `worker.py`**: Updated completion and error handlers to read existing metadata and preserve the investigator UUID, preventing it from being overwritten by the label during the pipeline lifecycle.

---

### Error: WebSocket 1006 Disconnects / Handshake Failure

**Symptom:** WebSocket connections fail during the handshake or disconnect mid-investigation with code 1006 (Abnormal Closure).

**Root Cause:** Three compounding proxy bugs in the `Caddyfile`:
1. **Compression Corruption**: `encode zstd gzip` was being applied to WebSocket upgrades, corrupting the 101 Switching Protocols response.
2. **Missing Headers**: `Upgrade` and `Connection` headers were being stripped by Caddy before reaching Uvicorn.
3. **Timeouts**: `response_header_timeout` was set to 620s globally, causing Caddy to drop long-lived WebSocket streams that didn't send new headers.

**Fix:**
- Implemented path-based routing for WebSockets (`/api/v1/sessions/*/live`) with `response_header_timeout 0` and no compression.
- Removed manual `header_up Upgrade/Connection` (Caddy 2 handles these automatically; manual overrides interfered with the built-in tunnel).
- Moved `request_body max_size` and `encode` to the REST block (`/api/v1/*`) to keep the WebSocket pipe clean.

---

### Error: "Live update channel disconnected" after 30s of silence

**Symptom:** WebSocket or SSE connections die exactly ~30 seconds after starting an investigation, especially during slow model loading or deep analysis phases.

**Root Cause:** The `_redis_subscriber` coroutine was reusing the shared Redis singleton connection pool. This pool is configured with `socket_timeout=30.0` to prevent hanging REST commands. However, `pubsub.listen()` is a blocking operation; if no messages are received for 30 seconds, the socket times out and the connection is closed.

**Fix:**
- Updated `sessions.py` (WebSocket) and `sse.py` (SSE) to create a **dedicated Redis connection** specifically for the subscriber.
- Configured this dedicated connection with `socket_timeout=None` (infinite wait) and `socket_keepalive=True` to ensure stability during silent periods.
- Added proper cleanup in `finally` blocks to close the dedicated connection when the user disconnects.

---

### Error: Pipeline "Frozen" at 1/6 due to Custody Logging Serialization

**Symptom:** Forensic agents appear stuck at "1/6 tools" indefinitely. The pipeline progress bar never moves, although the worker is active.

**Root Cause:** A serialization bottleneck in the `CustodyLogger`. Every agent in the pipeline was sharing a single `asyncio.Lock` per `session_id` inside `log_entry`. Since tool calls generate multiple log entries (THOUGHT → ACTION → OBSERVATION) and each involves a blocking Postgres insert, the agents were deadlocking each other. Agent A would hold the lock waiting for a DB write while Agent B was blocked waiting for the lock to log its first observation.

**Fix:**
- **`custody_logger.py`**: Refactored the locking mechanism to be per-agent: `_session_chain_locks[(session_id, agent_id)]`. 
- **Per-Agent Hash Chains**: Updated the cryptographic linking to maintain separate hash chains for each agent. This allows all 5 agents to log simultaneously while preserving tamper-evident integrity for each investigator's timeline.
- **Verification Audit**: Updated `verify_chain` to correctly validate these parallel agent chains during forensic audits.

---

### Error: Lost Messages / "Stuck" UI due to Pub/Sub Race Condition

**Symptom:** After uploading a file, the UI remains stuck on "Preparing forensic agents..." even though the worker is running. No updates ever arrive at the frontend.

**Root Cause:** A race condition between the worker and the API's WebSocket subscriber. The worker often finishes the first 3-5 initialization steps (broadcasts) before the WebSocket subscriber has fully connected and subscribed to the Redis channel. Since Redis Pub/Sub is fire-and-forget, these early messages are lost forever to that connection.

**Fix:**
- **`_session_state.py`**: Implemented a **Replay Buffer** using a Redis List (`forensic:replay:{session_id}`). Every `broadcast_update` now simultaneously publishes to the live channel and pushes to this list (capped at 50 items).
- **`sessions.py` & `sse.py`**: Updated subscribers to perform a two-step "Catch Up":
    1. Subscribe to the live channel first (to capture all future messages).
    2. Drain the replay buffer via `LRANGE` to capture all messages published during the connection gap.
    3. Transition to listening to the live stream.

---

### Error: "Poisoned Session" Loop / 409 Deduplication Deadlock

**Symptom:** After a backend restart, retrying an analysis for the same file results in a "Duplicate detected" error (409), followed by an immediate connection failure or 403 Forbidden. The system gets stuck in a loop where retries always return a broken session.

**Root Cause:** 
1. **Stale Dedup**: Every backend restart marks all "running" sessions as "interrupted". However, the Redis deduplication keys (mapping file hash -> session ID) were not being cleared. 
2. **Infinite Reconnect**: When a user retried, the backend returned the ID of the "interrupted" session. The frontend would then connect to this dead session, receive an error (4010), and immediately attempt to reconnect, creating a loop.

**Fix:**
- **`investigation.py`**: Updated the deduplication handler to check the status of existing sessions. If a session is not "running" or "paused", the stale dedup key is deleted, and the current request proceeds as a fresh investigation.
- **`useSimulation.ts`**: Updated the WebSocket close handler to recognize terminal codes (`4001`, `4003`, `4004`, `4010`). For these codes, the frontend now clears its local `session_id` storage and stops all reconnection attempts, allowing the next retry to start clean.

---

### Error: Next.js 15.5 Startup Crash & Build Failure

**Symptom:** Frontend container fails to start with "unrecognized option --no-turbopack". Docker build fails on `package-lock.json` missing in monorepo sub-apps.

**Root Cause:** 
1. Next.js 15.5 removed the `--no-turbopack` flag (webpack is now the default unless `--turbo` is passed).
2. The `Dockerfile` required `package-lock.json` in the app directory, which doesn't exist in some monorepo structures where the lockfile is at the root.

**Fix:**
- Removed `--no-turbopack` from `infra/docker-compose.yml`.
- Made `package-lock.json` copy optional in `apps/web/Dockerfile` using a wildcard (`package-lock.jso[n]`).

---

### Config: CORS & API Connectivity Issues

**Symptom:** Backend is unreachable from the browser ("Failed to fetch") or backend fails to start with "validation error for Settings: cors_allowed_origins".

**Root Cause:** 
1. **Connectivity**: `NEXT_PUBLIC_API_URL` was pointing directly to `:8000`, bypassing the Caddy proxy and triggering CORS blocks or connection failures in restricted environments.
2. **Parsing**: Pydantic Settings attempts to `json.loads()` environment variables for `list[str]` types; comma-separated strings in `.env` were rejected.

**Fix:** 
- Cleared `NEXT_PUBLIC_API_URL` in `.env` and `.env.example` to force the browser to use the same-origin proxy (Caddy) for API calls.
- Changed `CORS_ALLOWED_ORIGINS` in `.env` to a valid JSON array format (e.g., `["http://localhost"]`).
- Added `http://localhost` (the Caddy origin) to the allowed origins list.

---

## 2026-04-27 — Session 6: WebSocket Error Handling & HMR Fix

### Error: Wrong Error Code for WebSocket Connection Failures

**File:** `apps/web/src/app/evidence/page.tsx`, `apps/web/src/hooks/useInvestigation.ts`

**Symptom:** After a WebSocket connection failure, the error modal shows `0xFC_VALIDATION_FAIL` and the error message "WebSocket connection error". `0xFC_VALIDATION_FAIL` is the code reserved for file-format validation errors (wrong MIME type, file too large), not connection failures. Clicking "Retry Analysis" re-uploaded the file instead of reconnecting to the existing session.

**Root Cause:** In `useInvestigation.ts`, the `.catch` block of `connectWebSocket()` stored WS errors in `setValidationError` — the same state used for file validation errors. The modal's `errorCode` selection (`errorMessage ? "0xFC_PIPELINE_HALT" : "0xFC_VALIDATION_FAIL"`) had no branch for WS connection failures.

**Fix:**
- Added `wsConnectionError` state in `useInvestigation` dedicated to WebSocket connection failures.
- Added `lastSessionIdRef` to remember the session ID that was accepted by the backend even after `resetSimulation()` clears it.
- Added `retryWsConnection` callback that reconnects to the existing session ID rather than re-uploading the file.
- Updated `evidence/page.tsx` modal: `0xFC_CONN_FAIL` for WS errors, `0xFC_PIPELINE_HALT` for pipeline errors, `0xFC_VALIDATION_FAIL` only for file validation errors. Retry action is context-aware.

---

### Error: HMR Not Working in Docker Development (Windows Bind Mount)

**File:** `infra/docker-compose.yml`

**Symptom:** Editing frontend source files on the Windows host does not trigger hot-module replacement (HMR) inside the running Docker container. The browser never reflects code changes without a full container restart.

**Root Cause:** Next.js 15.3+ changed `next dev` to use Turbopack by default. Turbopack uses the OS-native file watcher (inotify on Linux), which receives no events from Windows host bind mounts because WSL2 does not forward inotify events across the filesystem boundary. The existing `watchOptions.poll: 500` fix in `next.config.ts` only applies to webpack, not Turbopack.

**Fix:** Added `command: ["npm", "run", "dev", "--", "--no-turbopack"]` to the `frontend` service in `docker-compose.yml`. This forces Next.js to use webpack, which applies the 500 ms filesystem polling configured in `next.config.ts` and restores HMR on Windows Docker bind mounts.

---

## 2026-03-16 — Session 5: Full Runtime Audit (v1.0.4)

### Error: Report 404 After Investigation Completes (Race Window)

**Symptom:** Result page polls `/arbiter-status` → gets `"complete"` → fetches `/report` → 404. Intermittent — depends on timing.

**Root Cause:** `run_investigation_task()` set `pipeline._final_report = report` but the `finally` block immediately removed the pipeline from `_active_pipelines`. The in-memory `_final_reports` cache was never populated, so between pipeline eviction and DB persistence completing, the report endpoint had no source to read from.

**Fix:** Cache report in `_final_reports[session_id]` immediately after setting `pipeline._final_report`, before the `finally` block executes.

---

### Error: AttributeError: `_custody_logger` in Inter-Agent Calls

**Symptom:** Agents 2, 3, and 4 crash when making collaborative inter-agent calls (e.g. Agent2 → Agent4 for A/V sync).

**Root Cause:** Inter-agent call handlers referenced `self._custody_logger` (underscore prefix), but `ForensicAgent.__init__()` stores the logger as `self.custody_logger` (no underscore).

**Fix:** Changed `self._custody_logger` → `self.custody_logger` in `agent2_audio.py`, `agent3_object.py`, `agent4_video.py`.

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

**Fix:** Changed `LLM_MODEL=${LLM_MODEL:-gpt-4o}` → `LLM_MODEL=${LLM_MODEL:-llama-3.3-70b-versatile}` in `docker-compose.yml`.

---

### Config: .env.example GEMINI_TIMEOUT Mismatch

**Symptom:** Default GEMINI_TIMEOUT was 30.0s in .env.example but 55.0s in config.py. Deep forensic analysis needs the longer timeout.

**Fix:** Updated .env.example to `GEMINI_TIMEOUT=55.0`.

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

**Root Cause:** The CI `backend-test` job ran `pytest tests/unit/` from `working-directory: backend`. The `apps/api/tests/` directory contains only empty `__init__.py` stubs; the actual test files with substance are at `tests/apps/api/` in the project root.

**Fix:** Changed CI to run from project root: `pytest tests/apps/api/ tests/infrastructure/ tests/docker/`.

---

### Error: `ImportError: No module named 'core'` / `ModuleNotFoundError: No module named 'backend'`

**Symptom:** Running `pytest tests/apps/api/` from project root fails immediately. `test_auth.py` crashes with `ImportError: No module named 'core'`. `test_config_signing_schemas.py` crashes with `ModuleNotFoundError: No module named 'backend'`.

**Root Cause:** Two issues:
1. Root `setup.cfg` lacked `pythonpath` — Python couldn't find `core`, `infra`, etc.
2. `apps/api/` had no `__init__.py` — `from backend.core.config import ...` always failed.

**Fix:** Added `pythonpath = . backend` to root `setup.cfg` and created `apps/api/__init__.py`.

---

## 2026-03-16 — Session 1: Frontend Audit

### Error: TypeError — `visibleAgents[0].id` on Empty Array

**File:** `apps/web/src/components/evidence/AgentProgressDisplay.tsx`

**Root Cause:** `visibleAgents[0].id` accessed without null check when `visibleAgents` was empty.

**Fix:** Added optional chaining: `const firstVisibleAgent = visibleAgents[0]; const firstVisibleId = firstVisibleAgent ? firstVisibleAgent.id : null;`

---

### Error: `as unknown as string` Double Cast

**File:** `apps/web/src/app/evidence/page.tsx`

**Root Cause:** `investigatorIdRef.current as unknown as string` — the ref was already typed `useRef<string>`.

**Fix:** Removed the unnecessary double cast.

---

### Error: Jest Fails to Install — `jest-util@^30.2.0` Incompatible

**Symptom:** `npm install` fails; `jest-util@^30.x` is incompatible with `jest@29.x`.

**Fix:** Removed `jest-util` from `package.json` devDependencies entirely.

---

### Error: WCAG 2.1 — Logo Not Keyboard Navigable

**File:** `apps/web/src/components/evidence/HeaderSection.tsx`

**Root Cause:** Logo rendered as a plain `<div onClick>` — not focusable, no keyboard handler, no ARIA role.

**Fix:** Added `role="button"`, `tabIndex={0}`, `onKeyDown` (Enter/Space), `aria-label="Return to Forensic Council home"`.

---

### Error: WCAG 2.1 — Textarea Missing Label Association

**File:** `apps/web/src/components/evidence/HITLCheckpointModal.tsx`

**Root Cause:** `<label>` and `<textarea>` had no linking `id`/`htmlFor` attributes.

**Fix:** Added `id="hitl-notes"` to textarea and `htmlFor="hitl-notes"` to label.

---

---

## 2026-04-11 — Forensic OS 2026 Hardening (v1.4.0)

### Audit: Documentation & Root Hygiene
- **Verified**: Full audit of `docs/` directory completed. All architectural specs, API references, and security policies synchronized with v1.4.0 code.
- **Improved**: Relocated `apps/api/test_initial_analysis.py` to `tests/integration/` to maintain root cleanliness.
- **Improved**: Consolidated agent diagnostic tools into `docs/agent_capabilities.md` with "Court Defensible" status verification.

### Hardening: Multi-Agent Parallelism & Grounding
- **Verified**: Hybrid sequential/concurrent agent execution flow correctly handles Agent 1 (Initial) → Agent 3/5 (Deep) context injection.
- **Verified**: ECDSA P-256 deterministic key derivation (HMAC-SHA-256) robustly separate agent-level signing authorities.
- **Updated**: Metadata Agent (Agent 5) now includes **C2PA JUMBF Validation** and hardware provenance cross-correlation.

### Infrastructure & Resilience
- **Hardened**: Redis-backed rate limiter and session state store confirmed to handle OOM degradation gracefully via Lua atomicity.
- **Hardened**: PostgreSQL immutable forensic ledger verified for tamper-evident sequential hashing.
- **Warning**: Added hardware peak load warnings (15GB RAM) to `ARCHITECTURE.md` to prevent deployment OOMs in Deep Analysis phase.

