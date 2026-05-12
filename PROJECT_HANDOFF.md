# Project Handoff — Forensic Council

## Purpose

This document is the canonical handoff for local AI/code assistants. Read it before editing the repo.

AI Sync Instructions: Before making or suggesting any changes:
1. Read `AGENTS.md`
2. Read this file
3. Check "Phase Inventory" for current phase and what changed
4. Check "Do Not Break" rules
5. Run the appropriate verification command before claiming changes work
6. Do not remove security, custody-chain, quota, HITL, or report-signing logic

---

## Current Architecture

- `apps/web`: Next.js 15 frontend (React 19, Tailwind CSS, TanStack Query, Playwright, Jest)
- `apps/api`: FastAPI backend (Python 3.12, Pydantic v2, Redis, PostgreSQL, Qdrant)
- `infra`: Docker Compose, Caddy reverse proxy, Prometheus, Jaeger
- `docs`: Source-of-truth documentation
- `scripts`: Verification and utility scripts

---

## Current Workflow

See `docs/WORKFLOW_TRACE.md` for the canonical route/state flow.

---

## Phase Inventory

### Phase 9 (committed, `phase-9-docs-refinement`, commits `525f4d0` + `b18dde4`)

Project documentation refinement. All items complete:

| Item | Status |
|------|--------|
| Documentation inventory | ✅ |
| Project handoff refinement | ✅ |
| README streamlining | ✅ |
| Architecture update | ✅ (no changes needed — already current) |
| API contract update | ✅ (new: docs/API_CONTRACT.md) |
| Testing guide update | ✅ (no changes needed — already current) |
| Model registry update | ✅ (new: docs/MODEL_REGISTRY.md) |
| Security doc update | ✅ (no changes needed — already current) |
| Operational runbook update | ✅ (new: docs/OPERATIONAL_RUNBOOK.md) |
| App README updates | ✅ |
| Docs consistency checker | ✅ (new: scripts/check_docs.py) |
| Cleanup script | ✅ (new: scripts/clean_project.sh) |
| Verify project script | ✅ (new: scripts/verify_project.sh) |
| .gitignore/.dockerignore audit | ✅ (updated .dockerignore) |
| Dead code scan | ✅ |
| Phase 9 cleanup (post-merge fixes) | ✅ (commit `b18dde4`) |
| Verify project script | 🔄 pending |
| .gitignore / .dockerignore audit | 🔄 pending |
| Dead code scan | 🔄 pending |

### Phase 8 (committed, branch `phase-8-test-suite-refinement`, commit `bd5433d`)

Test suite audit and refinement. Key changes:
- Fast mocked `full_journey.spec.ts` + opt-in `full_journey.live.spec.ts`
- `npx wait-on` replaced with inline Node wait loop in CI
- Backend pytest marker alignment (`requires_ml`, `requires_network`, `requires_docker`)
- System test unconditional skips → opt-in `skipif` with `RUN_SYSTEM_ML_TESTS=1`
- `useInvestigation.test.ts` replaced placeholder with 8 real tests
- All `mock_queue.enqueue` → `mock_queue.submit` in contract tests
- `scripts/check_test_hygiene.py` — stale test pattern checker
- `scripts/verify_phase8_tests.sh` — verification script
- `scripts/check_critical_coverage.py` — backend coverage enforcement
- `jest.config.ts` — per-module coverage thresholds for workflow-critical modules

### Phase 7 (committed, branch `phase-7-workflow-state-fixes`)

Workflow and state fixes. Key changes:
- `docs/WORKFLOW_TRACE.md`: route/state ownership map, Effect A/B behavior, storage keys, edge cases
- `useInvestigation.ts`: expired handoff → `?upload=1`; 409 reconnect; `unreachable` route; `fc_report_ready` bridge; `resumeInFlightRef` guards
- `useResult.ts` + `investigationStorage.ts`: forensic_history preservation across New Upload/Home
- `full_journey_phase7.spec.ts`: Playwright tests for Phase 7 edge cases
- `test_api_contracts.py`: Phase 7 contract test classes

### Phase 6 (committed, branch `phase-6-agents-models-api-config`, commit `1276405`)

Agents, models, LLM client, API config cleanup. Key changes:
- `free_tier_mode` setting blocks OpenAI/Anthropic
- `GeminiApiKeyPolicyOk` flag required before Gemini calls
- `ProviderQuotaGuard` module for RPM/RPD enforcement
- Groq fallback key uses `self.api_key` not `config.llm_api_key`
- `_call_groq` simplified to single model (outer loop handles iteration)
- `verify_llm_keys.py` uses `/models` endpoints only (no quota burn)
- Local forensic fallback has confidence=0.55, court_defensible=True

### Phase 5 (committed, branch `phase-5-backend-core-logic`, commit `c423b5d`)

Backend core logic fixes. Key changes:
- Session persistence registration before pipeline dispatch
- Full session termination (cancel task, abort pipeline, clear Redis, close WS)
- DB fallback in `assert_session_access` for Redis-cache-miss
- Atomic Redis pipeline in `InvestigationQueue.submit`
- Atomic error report persistence (INSERT ON CONFLICT DO UPDATE)
- Exception hiding in upload route (no raw internal messages to client)
- Robust MIME detection with fallback
- Session finalization centralized in `session_finalization.py`
- HITL idempotency fail-closed (503)

---

## Phase-Complete Invariants

### Phase 1 — Build/Run
- `docker compose config` renders without error
- `scripts/verify_phase1_build_run.sh static` passes
- Backend `uv run python scripts/run_api.py` starts (needs Docker infra)

### Phase 2 — Startup/Stability
- Backend starts with `USE_REDIS_WORKER=false` on host
- WebSocket reconnect logic handles transient disconnect
- Worker cold-start heartbeat tolerance (no premature task abort)

### Phase 3 — Frontend Workflow
- Upload → evidence → result → history journey works
- `pendingFileStore` in memory, `fc_open_upload_once` in sessionStorage
- Demo auto-login works when `BOOTSTRAP_INVESTIGATOR_PASSWORD=DEMO_PASSWORD`

### Phase 4 — Accessibility
- WCAG 2.1 AA automated checks pass
- `npm run test:a11y` passes (both unit and e2e)

### Phase 5 — Backend Lifecycle
- Session creation → pipeline dispatch → finalization → report retrieval
- `terminate_session` cancels task, clears Redis, closes WS, updates DB
- HITL pause/resume with idempotent `already_resumed` response

### Phase 6 — Model/Provider
- `gemini_api_key_policy_ok=false` disables Gemini (safe default)
- `free_tier_mode=true` blocks OpenAI/Anthropic providers
- `verify_llm_keys.py --json` shows all keys as valid or placeholder
- Groq agent uses `llama-3.1-8b-instant`; Arbiter uses `llama-3.3-70b-versatile`

### Phase 7 — End-to-End Workflow
- Expired handoff → home with `?upload=1` reopens upload modal once
- Duplicate investigation returns 409 with existing session ID
- Reconnect on `not_found`/`unreachable` restores session and reconnects WS
- Accept Analysis sets `fc_report_ready=1` before navigating to result
- `resumeInFlightRef` prevents double-call of accept/deep decisions
- forensic_history preserved across New Upload and Home navigation

### Phase 8 — Test Suite
- Hygiene checker: `python scripts/check_test_hygiene.py` passes
- Static verification: `python scripts/verify_phase8_tests.sh static` passes
- Backend unit/integration: `python scripts/verify_phase8_tests.sh backend-unit` + `backend-integration`
- Frontend: `npm run type-check` + `npm run lint` + `npm test` + `npm run build`
- `mock_queue.enqueue` replaced with `mock_queue.submit` throughout

---

## Allowed Local AI Behavior

- Inspect before edit (read the file, understand conventions)
- Use phase-specific guardrails (this document, AGENTS.md)
- Keep changes surgical (one phase, one concern per commit)
- Run exact verification command before claiming changes work
- Commit per phase/change group
- Update this file after every phase

---

## Files Not to Touch Casually

- `package-lock.json`, `uv.lock` — managed by package managers
- `apps/api/core/migrations.py` — schema migration logic
- `apps/api/config/models.lock.json` — model config; update via documented process only
- Auth/session routes (`apps/api/api/routes/auth.py`, `apps/api/api/routes/_authz.py`)
- Security invariants (custody chain, report signing, quota guard)
- Agent verdict logic (`apps/api/agents/arbiter.py`) — deterministic, no LLM verdict assignment

---

## Required Verification Matrix

| Command | What It Checks |
|---------|---------------|
| `python scripts/check_docs.py` | All docs exist, no broken links, no stale patterns |
| `python scripts/check_test_hygiene.py` | No stale test patterns, no undeclared npx |
| `./scripts/verify_phase8_tests.sh static` | Python compile, shell syntax, static checks |
| `./scripts/verify_phase8_tests.sh frontend-unit` | npm ci, type-check, lint, Jest, build |
| `./scripts/verify_phase8_tests.sh backend-unit` | ruff, pyright, pytest unit/security/infra |
| `./scripts/verify_phase8_tests.sh backend-integration` | pytest contracts/integration |
| `./scripts/verify_project.sh static` | All static project checks |
| `cd apps/web && npm run build` | Next.js production build |
| `cd apps/api && uv run ruff check .` | Backend lint |

---

## Current Free-Tier Provider Setup

- **Groq** (agent logic + Arbiter synthesis): `LLM_API_KEY` → `llama-3.1-8b-instant` (agent) / `llama-3.3-70b-versatile` (Arbiter)
- **Gemini** (vision deep analysis): `GEMINI_API_KEY` → `gemini-2.5-flash` (primary) / `gemini-2.5-flash-lite` (fallback)
- **Policy flag**: `GEMINI_API_KEY_POLICY_OK=true` required before Gemini calls are made
- **Free tier limits** (conservative defaults): Groq RPM=30, Gemini RPM=10, Gemini RPD=1500
- **No paid defaults** — OpenAI/Anthropic blocked when `FREE_TIER_MODE=true`
- **Verification**: `cd apps/api && uv run python scripts/verify_llm_keys.py --json`
- **Fallback**: No keys → local agent findings with deterministic Arbiter report

---

## Next Best Action

Phase 9 complete (both `525f4d0` and cleanup `b18dde4`). All phases 1–9 on `main`.

**Verification gates now passing:**
- `python scripts/check_docs.py` → passed ✅
- `python scripts/check_test_hygiene.py` → passed ✅
- `python -m compileall` → no errors ✅
- `scripts/verify_phase1_build_run.sh static` → shell syntax fixed (`shopt -s nullglob`) ✅
- `scripts/verify_phase8_tests.sh` → fail-on-failure, skip-only-when-missing ✅
- `npm run test:a11y` → now runs both unit and e2e ✅

**Deferred items (Phase 6 remaining):**
- Add unit tests for `ProviderQuotaGuard`
- Fix pre-existing test failures in `test_auth_unit.py` and `test_config_validation.py`

**Deferred items (Phase 8):**
- Phase 8.13 — Deterministic media fixtures
- Phase 8.14 — Shared test helpers

---

## Do Not Break

- authentication (JWT validation, Redis blacklist)
- evidence hashing (SHA-256 on upload)
- chain-of-custody logging (every significant forensic action)
- report signing (ECDSA key derivation)
- HITL checkpoint flow (pause/resume/deep analysis)
- quota and rate limiting
- backend-generated forensic truth (never fake results in frontend)
- same-origin Caddy proxy mode (Docker default)
- WebSocket reconnect logic
- Worker cold-start heartbeat tolerance
- PDF as unsupported (Phase 3 — backend not ready)
- Scoped metadata backward compat
- Agent1 context timeout with asyncio.shield
- Gemini policy flag requirement (intentional safety measure)
- Session finalization centralized (prevents duplicate finalization)
- Groq arbiter key routing (uses `self.api_key`, not `config.llm_api_key`)

---

## Handoff Update Rule

Every time architecture, routing, model config, or verification commands change:
1. Update this file (Phase Inventory, Phase-Complete Invariants, Verification Matrix)
2. Update the relevant source-of-truth doc in `docs/`
3. Update `docs/DOCUMENTATION_INVENTORY.md` if doc structure changes