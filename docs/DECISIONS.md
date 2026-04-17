# Architecture Decision Records (ADRs)

> **Superseded by** [`adr/`](./adr/) — new ADRs should be filed there.
> This file is retained for historical reference only.

## ADR 1: Custom AsyncIO ReAct Loop over LangGraph

- **Date:** 2026-02-15 (revised 2026-03-16)
- **Context:** Building a stable multi-agent ReAct loop with real-time WebSocket streaming.
- **Decision:** Implement a custom asyncio-based ReAct loop (`core/react_loop.py`).
- **Rationale:** We initially evaluated LangGraph but found it introduced significant overhead that conflicted with our streaming requirements. The key issues: LangGraph's state graph checkpointing blocked the asyncio event loop during state serialisation, causing WebSocket heartbeat drops at exactly the moments investigators need real-time feedback. Our custom `ReActLoopEngine` uses a simple task-decomposition driver (no LLM required) with optional Groq integration, and feeds live `WorkingMemory` state directly to the WebSocket heartbeat loop every 200ms. This gives investigators readable, linear streaming output rather than LangGraph's graph-traversal output structure.

---

## ADR 2: Qdrant over Pinecone/Milvus for Vector Search

- **Date:** 2026-02-18 (revised 2026-03-16)
- **Context:** Need a vector database for historical similarity matching (episodic memory).
- **Decision:** Use Qdrant locally, pinned to `==1.16.2`.
- **Rationale:** The Forensic Council handles highly sensitive, potentially classified media. Cloud dependencies (Pinecone) violate data-residency constraints — evidence cannot leave the deployment environment. Compared to Milvus, Qdrant relies on Rust, is significantly lighter to deploy via Docker Compose, and doesn't require complex distributed dependencies (etcd/MinIO) for a single-node deployment. Qdrant's REST + gRPC dual API also integrates cleanly with our asyncio Python stack via `AsyncQdrantClient`.
- **Version pin rationale:** `qdrant-client==1.16.2` is the last pre-1.17 release. Versions 1.14.1–1.16.1 add a `numpy>=2.1.0` constraint on Python 3.13+, which conflicts with the `numpy<2.0` bound required by moviepy 1.x. Version 1.16.2 shifts this constraint to Python 3.14+ only, making it safe on our Python 3.11/3.12 target. `requires-python = ">=3.11,<3.13"` in `pyproject.toml` enforces this ceiling so `uv lock` never attempts resolution on Python 3.13+.

---

## ADR 3: Subprocess ML over Native Python Threads

- **Date:** 2026-02-22
- **Context:** Integrating heavy ML (IsolationForest, GaussianMixtures, Fourier transforms, CLIP, YOLOv8) into the FastAPI backend.
- **Decision:** Decouple all heavy ML inference to CLI subprocesses via `asyncio.create_subprocess_exec`.
- **Rationale:** Python's GIL and event-loop blocking model mean that running a 30-second `librosa` audio calculation natively starves the FastAPI server, dropping all active WebSocket connections. Spawning isolated subprocesses ensures the main web server remains responsive at all times. OS-level memory is freed immediately when the subprocess terminates (no Python GC lag), and a crashed subprocess cannot corrupt the parent process state.

---

## ADR 4: Sequential Agent Execution

- **Date:** 2026-02-28 (revised 2026-03-16)
- **Context:** Processing a single evidence file through 5 specialist agents.
- **Decision:** Enforce sequential (not parallel) agent execution per phase.
- **Rationale:** Parallelising 5 agents simultaneously on typical analyst hardware (16 GB RAM) caused severe OOM crashes — loading YOLO + Wav2Vec2 + librosa simultaneously peaks at 12–18 GB RAM. Parallel agents also produced disjointed WebSocket streams (all 5 agents update simultaneously — unreadable UX). Sequential execution trades total wall-clock time for predictable memory usage, stable WebSocket streaming, and a linear readable cognitive trace. The deep analysis phase runs Agent 1 (Gemini) first, then Agents 2–5 concurrently — a deliberate exception when Gemini context injection is needed.
- **Related:** ADR 8 covers the asyncio.Lock singleton protection required to make concurrent deep-phase clients safe — sequential execution at the agent level does not eliminate concurrent client initialisation at the infrastructure level.

---

## ADR 5: GitHub Actions for CI/CD

- **Date:** 2026-03-11
- **Context:** No automated gate existed; tests were never run on push.
- **Decision:** Add `.github/workflows/ci.yml` with backend + frontend lint/type-check/build/test jobs, dependency audits, and an integration smoke test gated to `main` pushes.
- **Rationale:** Forensic evidence tooling has a high correctness bar. Catching regressions in the signing pipeline, resume URL routing, or auth layer before merge is non-negotiable. The smoke test runs the full Docker stack against a live backend to verify `/health` and auth rejection without requiring real ML models (`LLM_PROVIDER=none`). CI runs from the project root using `cd apps/api && uv run pytest tests && pytest ../../tests/infra ../../tests/docker` — not from `apps/api/` where only empty stubs exist.

---

## ADR 6: Redis-Backed Rate Limiting with In-Process Fallback

- **Date:** 2026-03-11
- **Context:** A single authenticated user could submit unlimited investigation jobs, exhausting memory and CPU.
- **Decision:** Redis `INCR`/`EXPIRE` counters for per-user investigation rate limits (10/5-min) and per-IP login attempt tracking (5 failures → 15-min lockout). In-process dict as fallback when Redis is unreachable.
- **Rationale:** Pure in-process counters reset on restart and are incorrect across replicas. Pure Redis counters fail if Redis is momentarily unavailable. The dual-layer approach gives correct multi-replica behaviour in steady state while degrading gracefully to single-node accuracy during Redis outages rather than blocking all requests.

---

## ADR 7: Fail-Secure Token Blacklisting

- **Date:** 2026-03-16
- **Context:** The `is_token_blacklisted()` function in `core/auth.py` returns `True` (denies access) when Redis is unavailable.
- **Decision:** Maintain fail-secure behaviour — treat Redis unavailability as "all tokens unverifiable" and deny access.
- **Rationale:** This is an intentional security/availability tradeoff. For a forensic evidence system handling potentially classified or evidentiary material, a temporarily locked-out investigator is a recoverable situation; a stolen token granted access during a Redis outage is not. The cost is that investigators cannot log in during Redis downtime; the benefit is that logged-out tokens cannot be replayed. The `blacklist_token()` function is best-effort (warns on failure without crashing logout).
- **Session 4 verification (2026-03-16):** Confirmed that blacklist keys use the JWT `jti` claim (not the raw token string), with TTL equal to remaining token validity. This means entries expire automatically and carry no unbounded memory risk. The fail-secure path was also confirmed to be exercised by `test_security.py` via a mocked Redis timeout. See `SECURITY.md` — *Token blacklisting* section for the full audit note.

---

## ADR 8: asyncio.Lock Singletons for Infrastructure Clients

- **Date:** 2026-03-16
- **Context:** The Qdrant client singleton had no concurrency protection, unlike Redis and Postgres.
- **Decision:** All three infrastructure singletons (Redis, Postgres, Qdrant) use `asyncio.Lock` with double-checked locking for singleton initialisation.
- **Rationale:** Under concurrent startup (multiple FastAPI lifespan coroutines or parallel request handlers hitting `get_qdrant_client()` before the first connection resolves), a race condition creates multiple client instances. Only the last one is stored; the others leak open connections. The double-checked lock pattern (check → lock → check again) prevents this while still being fast on the hot path (unlocked `is not None` check).
- **Related:** ADR 4 explains why agent execution is sequential; this ADR covers the orthogonal concern that infrastructure client initialisation can still be concurrent even when agents run sequentially (e.g., multiple simultaneous investigation sessions or server startup race conditions).

---

## ADR 9: Fail-Correct DB Error Reporting

- **Date:** 2026-03-16
- **Context:** When an investigation fails, `update_session_status()` attempted `INSERT INTO session_reports` with empty strings for `case_id` and `investigator_id` (both `NOT NULL`). The error handler itself crashed with a PostgreSQL constraint violation.
- **Decision:** Change the error path to `UPDATE session_reports ... WHERE session_id = $1` — only update if a row already exists; never insert.
- **Rationale:** The `session_reports` row is created by `save_report()` at investigation completion. If the investigation never completed, no row exists, and there is nothing to update — which is the correct behaviour. Attempting to insert a row with empty required fields was both logically wrong and operationally dangerous (it crashed the error handler, preventing the failure from being persisted at all).


