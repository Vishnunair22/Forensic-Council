# Codebase Concerns

**Analysis Date:** 2026-04-16

---

## Tech Debt

### Monolithic Route Handler: investigation.py
- Issue: `apps/api/api/routes/investigation.py` is 2,526 lines and contains the investigation endpoint, the `run_investigation_task` coroutine, all WebSocket heartbeat logic, agent orchestration glue, MIME mapping, task humaniser phrase tables, and the `instrumented_run` closure. Several unrelated module-level constants are also defined after the `start_investigation` route function body.
- Files: `apps/api/api/routes/investigation.py`
- Impact: Any change to WebSocket broadcasting, heartbeat intervals, or MIME validation requires editing the same file as the route handler. The closure-heavy `instrumented_run` function (lines ~624–1400) is difficult to unit test in isolation and relies heavily on nonlocal state.
- Fix approach: Extract `run_investigation_task` and `instrumented_run` into `orchestration/investigation_runner.py`. Move MIME maps and phrase tables to `core/constants.py` or a dedicated `api/constants.py`.

### Monolithic ReAct Loop: react_loop.py
- Issue: `apps/api/core/react_loop.py` is 2,617 lines. It combines the HITL checkpoint system, the `ReActLoopEngine` class, tool interpretation lambdas for every tool in the codebase (500+ lines of inline lambdas starting at line ~1200), and the task-decomposition driver.
- Files: `apps/api/core/react_loop.py`
- Impact: Tool interpreters are untested standalone and changes to any single tool observation format require editing the mega-dict inside this file.
- Fix approach: Extract the `_TOOL_INTERPRETERS` dict into `core/tool_interpreters.py`. Extract HITL logic into `core/hitl.py`.

### Monolithic Arbiter: arbiter.py
- Issue: `apps/api/agents/arbiter.py` is 2,352 lines combining verdict computation, challenge loop, tribunal escalation, LLM narrative synthesis, cross-modal fusion, per-agent metrics, and report generation.
- Files: `apps/api/agents/arbiter.py`
- Impact: The `deliberate()` method is ~400 lines and has multiple responsibilities; testing a change to the manipulation probability formula requires loading the entire arbiter.
- Fix approach: Split into `agents/arbiter_verdict.py` (deterministic scoring), `agents/arbiter_narrative.py` (LLM synthesis), and keep `arbiter.py` as a thin coordinator.

### `base_agent.py` Size
- Issue: `apps/api/agents/base_agent.py` is 1,601 lines. Contains the full self-reflection system, LLM reasoning attachment, memory integration, and the abstract `investigate()` interface.
- Files: `apps/api/agents/base_agent.py`
- Impact: Long onboarding time; reflection logic is entangled with core agent lifecycle.
- Fix approach: Extract `SelfReflectionReport` and `_attach_llm_reasoning_to_findings` into `agents/reflection.py`.

### JWT `aud` Claim Not Validated
- Issue: `apps/api/core/auth.py` line 166 explicitly sets `options={"verify_aud": False}` with a comment: "aud not set on existing tokens; enable after migration." This means tokens issued by a different service with the same secret can be accepted.
- Files: `apps/api/core/auth.py`
- Impact: Cross-service token reuse is possible in multi-service deployments.
- Fix approach: Add `aud` claim to `create_access_token()`, update `decode_token()` to pass `audience="forensic-council"`, and remove the `verify_aud: False` override.

### JWT Uses HS256 (Symmetric)
- Issue: `apps/api/core/config.py` line 232 defaults `jwt_algorithm` to `"HS256"`. The signing secret is symmetric, meaning any service holding the secret can forge tokens.
- Files: `apps/api/core/config.py`
- Impact: If the `JWT_SECRET_KEY` leaks (misconfigured env, log scraping), all tokens can be forged indefinitely until key rotation.
- Fix approach: Migrate to RS256 with a generated RSA key pair. Public key for verification, private key held server-side only. Add to migration plan.

---

## Known Bugs

### `_EXACT_MIME_EXT_MAP` Defined After Its First Usage
- Symptoms: `_EXACT_MIME_EXT_MAP` is referenced at line ~284 inside `start_investigation` but is defined at line ~426 (after the function ends and after the `# ── Task humaniser phrase map` comment block). Python resolves this at call time (not import time) so it works, but the out-of-order layout is a maintenance trap.
- Files: `apps/api/api/routes/investigation.py` (lines 284 and 426)
- Trigger: Any developer adding code between line 270 and 426 that references the constant at module import time will hit a `NameError`.
- Workaround: None needed currently; fix by moving the constant above `start_investigation`.

### Evidence Cleanup Only Runs in Worker Mode
- Symptoms: The periodic `cleanup_evidence()` loop runs in `apps/api/worker.py` only when an external Redis worker process is started (`USE_REDIS_WORKER=true`). When running in the default in-process API mode, no cleanup is scheduled — evidence files accumulate in `./storage/evidence` indefinitely.
- Files: `apps/api/worker.py` (lines 72–90), `apps/api/scripts/cleanup_storage.py`
- Trigger: Production deployments that do not launch the separate worker process.
- Workaround: Run `python scripts/cleanup_storage.py` as a cron job, or set `USE_REDIS_WORKER=true`.

### `_parse_report_dto` Silently Falls Back to Unvalidated Data
- Symptoms: `apps/web/src/lib/api.ts` line 12–17 catches Zod schema validation failures and returns the raw untyped data cast as `ReportDTO`. The UI then renders with potentially malformed data rather than surfacing a parse error.
- Files: `apps/web/src/lib/api.ts` (lines 10–18)
- Trigger: Any schema mismatch between backend `ReportDTO` and frontend `ReportDTOSchema`.
- Workaround: The fallback prevents blank screens but suppresses signal about schema drift.

---

## Security Considerations

### No Proxy-Level Rate Limiting
- Risk: The Caddyfile (`infra/Caddyfile`) configures security headers and body size limits but contains no `rate_limit` directives. Application-level rate limiting exists in `apps/api/api/routes/_rate_limiting.py` but it is Redis-backed per user. An unauthenticated IP can hammer the login or health endpoints without restriction.
- Files: `infra/Caddyfile`
- Current mitigation: Application-layer per-user rate limiting once authenticated. Body size limit of 55 MB enforced by Caddy.
- Recommendations: Add Caddy `rate_limit` module (e.g. `mholt/caddy-ratelimit`) or use a WAF in front. At minimum, add IP-based rate limiting on `/api/v1/auth/token` to prevent credential stuffing.

### CSP `style-src 'unsafe-inline'`
- Risk: The Content Security Policy in `infra/Caddyfile` line 92 allows `style-src 'self' 'unsafe-inline'`. Framer Motion and TailwindCSS use inline styles at runtime, but `unsafe-inline` in `style-src` bypasses CSS-injection protections.
- Files: `infra/Caddyfile` (line 92)
- Current mitigation: `script-src 'self'` is strict (no unsafe-inline or eval). Style injection is lower severity than script injection.
- Recommendations: Investigate adopting a nonce-based approach or switching to `style-src 'nonce-{nonce}'` if Framer Motion supports it. As a minimum, document this as an intentional exception.

### ECDSA Private Keys Stored Unencrypted in Fallback Mode
- Risk: When PostgreSQL is unavailable, `apps/api/core/signing.py` falls back to deterministic key derivation from `SIGNING_KEY`. All six agent keys are derived from the same master secret via HMAC-SHA256. A single `SIGNING_KEY` compromise compromises all agent signing keys simultaneously.
- Files: `apps/api/core/signing.py` (lines 210–217, module docstring)
- Current mitigation: Production deployments with PostgreSQL available use isolated per-agent keys encrypted with Fernet. The fallback is documented and logged at CRITICAL level.
- Recommendations: Add a startup check that refuses to start if `SIGNING_KEY` is used in fallback mode in production. Consider pre-populating keys at init time so the fallback is never silently active.

### SQLite Token Blacklist as Durable Fallback
- Risk: `apps/api/core/auth.py` uses a SQLite file (under `/tmp` or `settings.storage_dir`) as a durable fallback for the JWT blacklist. In container environments, `/tmp` is ephemeral and `storage_dir` is a local path — neither survives container replacement. A revoked token can become valid again after a container restart if Redis is also unavailable at that moment.
- Files: `apps/api/core/auth.py` (lines 212–220)
- Current mitigation: Redis is the primary blacklist authority. SQLite is only used when both Redis and the in-memory cache miss.
- Recommendations: Mount `storage_dir` as a persistent Docker volume, or document that token revocation is non-durable across container replacements.

### Demo Password Route
- Risk: `apps/web/src/app/api/auth/demo/route.ts` (109 lines) provides a demo login endpoint. Its password is read from `DEMO_PASSWORD` server-side, which is sound, but the route's existence in production creates an additional authentication surface.
- Files: `apps/web/src/app/api/auth/demo/route.ts`
- Current mitigation: Password gated by server-side env var. CI build intentionally does not bake `NEXT_PUBLIC_DEMO_PASSWORD` into the bundle.
- Recommendations: Gate the route with a compile-time or runtime flag (`DEMO_ENABLED=true`) so it is entirely absent in production builds.

---

## Performance Bottlenecks

### ML Tool Worker Pool: No Concurrency Limit Per Tool
- Problem: `apps/api/core/ml_subprocess.py` maintains one persistent worker process per ML tool script. When multiple investigations run concurrently, each investigation's agent can call the same ML tool worker simultaneously. Workers process one request at a time (stdin/stdout JSON protocol), so concurrent calls queue behind each other without timeout escalation.
- Files: `apps/api/core/ml_subprocess.py`
- Cause: The worker pool is a `dict[str, asyncio.subprocess.Process]` with no semaphore limiting concurrent in-flight calls per worker.
- Improvement path: Add a per-tool `asyncio.Semaphore` (configurable, default 3) so investigations can proceed in parallel up to the concurrency budget without saturating a single worker.

### ML Model Warmup on First Investigation (Dev Mode)
- Problem: In development mode, `apps/api/api/main.py` starts ML warmup as a non-blocking background task. The first investigation that arrives before warmup completes pays the full 30–60s cold-start cost per ML tool.
- Files: `apps/api/api/main.py` (lines 234–251)
- Cause: Intentional for dev convenience but can surprise developers seeing slow first runs.
- Improvement path: Add a `/api/v1/ready` endpoint that returns 503 until warmup completes, distinct from `/api/v1/health`.

### PostgreSQL Pool Size Too Small for Concurrent Investigations
- Problem: `apps/api/core/config.py` defaults `postgres_max_pool_size` to 10. Each investigation can open multiple concurrent DB connections (custody logger, session persistence, evidence store, signing key store). Under 5 concurrent investigations, the pool saturates and subsequent DB calls queue.
- Files: `apps/api/core/config.py` (line 125), `apps/api/core/persistence/postgres_client.py`
- Cause: Default pool size was set for single-investigation workloads.
- Improvement path: Increase default to 20 or document scaling: `POSTGRES_MAX_POOL_SIZE = (max_concurrent_investigations × 3) + 5`.

### `run_in_executor` Uses Default Thread Pool
- Problem: `apps/api/core/handlers/image.py` and `apps/api/core/handlers/audio.py` use `loop.run_in_executor(None, ...)` with the default executor. Under concurrent investigations, CPU-bound forensic operations (ELA, FFT, noise analysis) compete on a shared `ThreadPoolExecutor` with FastAPI's I/O-bound tasks.
- Files: `apps/api/core/handlers/image.py`, `apps/api/core/handlers/audio.py`
- Cause: `None` executor = default `ThreadPoolExecutor`. CPU-bound work should use a `ProcessPoolExecutor`.
- Improvement path: Create a dedicated `ProcessPoolExecutor` at startup and pass it explicitly to CPU-heavy `run_in_executor` calls.

---

## Fragile Areas

### WebSocket Session State in Module-Level Dicts
- Files: `apps/api/api/routes/_session_state.py`, `apps/api/api/routes/investigation.py`
- Why fragile: `_active_pipelines`, `_final_reports`, and WebSocket registries are module-level dicts. They are process-local — horizontal scaling (multiple API workers) loses session state across processes. A `uvicorn --workers 4` deployment would route WebSocket connections to a different process from where the pipeline dict was populated.
- Safe modification: These are intentionally single-process. Do not scale to multiple workers without migrating session state to Redis.
- Test coverage: No tests cover multi-process session state.

### HITL Checkpoint Resume Race Condition
- Files: `apps/web/src/hooks/useSimulation.ts` (line 70), `apps/api/core/react_loop.py`
- Why fragile: `expectingPipelineCompleteRef` is used to prevent `PIPELINE_COMPLETE` events from being dropped while a POST `/resume` is in flight. However, the frontend reconstructs HITL state from `localStorage` on page refresh (`useSimulation.ts` line 556). If the browser crashes between the POST `/resume` and the `PIPELINE_COMPLETE` WebSocket event, the frontend re-enters `awaiting_decision` state while the backend has already advanced past the checkpoint.
- Safe modification: Adding HITL state changes requires updating both `useSimulation.ts` and `apps/api/core/react_loop.py` atomically.
- Test coverage: `tests/unit/test_react_loop.py` covers the engine but not the frontend-backend state synchronisation edge case.

### Evidence File Path Stored in Redis Metadata
- Files: `apps/api/api/routes/investigation.py` (line 380: `"file_path": str(tmp_path)`)
- Why fragile: The temporary file path (e.g. `/tmp/{session_id}.jpg`) is stored in Redis session metadata. If the pipeline task is cancelled or crashes before the `finally` block at line 2501, the temp file survives but the path is also still in Redis. The stored path is an OS temp path that may be reused by the OS for a different file.
- Safe modification: Do not trust the Redis-stored `file_path` for security decisions. The file should be treated as deleted once the pipeline completes.
- Test coverage: Not tested.

### Gemini Vision Client Model Cascade Caches Unavailability
- Files: `apps/api/core/gemini_client.py`
- Why fragile: Model availability is validated at startup via `validate_model_availability()` and the result is cached. If a model becomes unavailable after startup (quota exhaustion, API deprecation), the cached cascade does not update until the next restart. The cascade skips 404/429 at runtime, but a model that starts returning 500s will retry with full backoff instead of cascading.
- Safe modification: Changes to model names in `GEMINI_MODEL` and `GEMINI_FALLBACK_MODELS` require a server restart to take effect.
- Test coverage: `tests/unit/test_gemini_client.py` mocks the HTTP layer; no test covers runtime cascade invalidation.

### Signing Key Fallback is Silent in Degraded State
- Files: `apps/api/core/signing.py` (lines 223–300)
- Why fragile: When PostgreSQL is unavailable during startup, the signing `KeyStore` silently falls back to deterministic key derivation after 3 retries. The fallback is logged at CRITICAL level but does not prevent the server from starting. Forensic reports signed in fallback mode use weaker single-key security without any client-visible indicator.
- Safe modification: Adding a new signing path must account for both the DB-backed and deterministic fallback modes.
- Test coverage: `tests/unit/test_signing.py` covers the fallback path but not the silent transition in the context of a full investigation.

---

## Scaling Limits

### In-Memory Rate Limit Fallback (10,000 Users Max)
- Current capacity: `_MEM_RATE_MAX_USERS = 10_000` and `_MEM_COST_MAX_USERS = 10_000` in `apps/api/api/routes/_rate_limiting.py`.
- Limit: Beyond 10,000 unique users without Redis, the oldest entries are evicted FIFO, effectively removing rate limit enforcement for the evicted users.
- Scaling path: Ensure Redis is always available in production (the code already fails CLOSED when Redis is absent in production mode).

### Final Reports Dict Unbounded Between Eviction Cycles
- Current capacity: `_final_reports` in `apps/api/api/routes/_session_state.py` accumulates completed reports in-process. Eviction runs once per completed investigation (O(n) scan). Under high throughput (100+ completions/minute), the eviction scan takes measurable time on the event loop.
- Scaling path: Replace with a Redis-backed TTL cache so `_final_reports` does not grow in-process.

### WebSocket Connections Per Process
- Current capacity: Each WebSocket connection is tracked in a module-level dict. No connection limit is enforced per session or globally.
- Limit: A slow client that never closes its WebSocket keeps its entry alive indefinitely.
- Scaling path: Add a maximum WebSocket connections per session (e.g. 5) and a global maximum per process.

---

## Dependencies at Risk

### `python-jose` for JWT
- Risk: `python-jose` has had historical CVEs and is less actively maintained than `PyJWT`. The project uses `from jose import JWTError, jwt` in `apps/api/core/auth.py`.
- Files: `apps/api/core/auth.py` (line 19)
- Impact: If a vulnerability is found in `python-jose`, token validation is compromised.
- Migration plan: Replace with `PyJWT` (more actively maintained, first-party OIDC support). API surface is similar; main changes are in `encode`/`decode` signatures.

### `passlib` bcrypt Warning
- Risk: `apps/api/core/auth.py` line 27 suppresses a UserWarning: "error reading bcrypt version". This is a known `passlib` issue with `bcrypt >= 4.0`. The warning is suppressed with `warnings.filterwarnings("ignore", ...)`.
- Files: `apps/api/core/auth.py` (line 27)
- Impact: `passlib` is no longer actively maintained. The bcrypt version mismatch warning is suppressed rather than fixed.
- Migration plan: Replace `passlib` with `bcrypt` directly or use `argon2-cffi` (Argon2id, more modern). Update `verify_password` and `get_password_hash`.

---

## Missing Critical Features

### No Proxy-Level Rate Limiting
- Problem: No `rate_limit` directive in `infra/Caddyfile`. The Caddy `caddy-ratelimit` module is not installed or configured.
- Blocks: DDoS/abuse protection at the network edge. All rate limiting is application-layer and Redis-dependent.

### E2E Tests Not Included in CI
- Problem: `apps/web/tests/e2e/browser_journey.spec.ts` uses Playwright but neither the `frontend-lint` nor `frontend-build` CI jobs in `.github/workflows/ci.yml` run Playwright tests. The `npm test` command runs Jest only (jest config in `package.json` uses `jest` runner, not Playwright). The `test:e2e` script is absent from `package.json`.
- Blocks: Browser-level regressions (upload flow, WebSocket connection, HITL modal) are not caught in CI.
- Fix: Add a `frontend-e2e` CI job that installs Playwright browsers (`npx playwright install --with-deps chromium`) and runs `npx playwright test tests/e2e/`.

### No Scheduled Cleanup When Running in API-Only Mode
- Problem: `apps/api/scripts/cleanup_storage.py` contains `cleanup_evidence()` but it is only scheduled in `apps/api/worker.py`. The default deployment does not start the worker, so `/storage/evidence` grows without bound.
- Blocks: Storage exhaustion in long-running production deployments not using the Redis worker.
- Fix: Add `asyncio.create_task(periodic_cleanup_task())` in the FastAPI lifespan function in `apps/api/api/main.py`, or document the worker requirement more prominently.

---

## Test Coverage Gaps

### Frontend WebSocket/Real-Time Flow
- What's not tested: The WebSocket reconnection logic, exponential backoff, and `HITL_CHECKPOINT` message handling in `useSimulation.ts` are not covered by Jest unit tests. `tests/e2e/websocket_flow.test.ts` exists but is not in CI.
- Files: `apps/web/src/hooks/useSimulation.ts`, `apps/web/tests/e2e/websocket_flow.test.ts`
- Risk: WebSocket reconnection regressions go undetected until manual QA.
- Priority: High

### Evidence Cleanup Under Failure Conditions
- What's not tested: No test covers the case where the pipeline `finally` block at `apps/api/api/routes/investigation.py:2501` fails to delete the temp file (e.g. permission error, file already deleted by OS). The temp path is still stored in Redis metadata after failure.
- Files: `apps/api/api/routes/investigation.py` (lines 2500–2510)
- Risk: Silent temp file leaks under rare OS-level errors.
- Priority: Low

### Arbiter Manipulation Probability with Zero Findings
- What's not tested: `apps/api/agents/arbiter.py` `_calculate_manipulation_probability()` has a documented special case for zero active findings (returns 0.0, verdict ABSTAIN). The ABSTAIN path has test coverage in `tests/unit/test_arbiter_smoke.py` but the edge case of exactly one finding from a low-reliability tool (bottom of `_TOOL_RELIABILITY_TIERS`) is not covered.
- Files: `apps/api/agents/arbiter.py`, `apps/api/tests/unit/test_arbiter_smoke.py`
- Risk: An unexpected probability value could produce a wrong verdict for edge-case evidence.
- Priority: Medium

### Multi-Agent Context Injection (Agent1 → Agent3/5)
- What's not tested: `inject_agent1_context()` and the `agent1_complete` signal path are referenced in CLAUDE.md as a critical dependency. No isolated test validates that Agent3 and Agent5 correctly receive and use Agent1 Gemini context.
- Files: `apps/api/agents/agent3_object.py`, `apps/api/agents/agent5_metadata.py`
- Risk: Silent context injection failure causes Agent3/5 to run without Gemini grounding, potentially producing less accurate verdicts.
- Priority: Medium

---

*Concerns audit: 2026-04-16*
