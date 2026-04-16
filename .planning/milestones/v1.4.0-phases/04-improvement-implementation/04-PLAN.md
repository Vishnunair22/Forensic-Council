# Phase 4 Plan: Improvement Audit & Implementation

## Phase Goal
Hardware-efficient resource management and forensic-grade observability for the v1.4.0 release.

## Track 1: Infrastructure Performance & Stability

### Plan 04-01: Resource Hardening
**Core Objective:** Implement automated pruning and concurrency isolation.

| Wave | Task | Files Modified | Autonomous |
| :--- | :--- | :--- | :--- |
| 1 | **[BLOCKING] Event Loop Sentinel** | `api/main.py`, `core/monitoring.py` | True |
| 1 | **Redis Tiered TTLs** | `orchestration/session_manager.py`, `api/routes/_rate_limiting.py` | True |
| 2 | **Managed Forensic ProcessPool** | `api/main.py`, `tools/*.py` | True |
| 2 | **Postgres N+1 Pruning** | `core/persistence/evidence_store.py` | True |

#### Task 1.1: Event Loop Sentinel
- **Action:** Create `core/monitoring.py` with a `HeartbeatMonitor` task as researched.
- **Verification:** Log check for `loop stall` after simulating a `time.sleep(1)` in a mock route.

#### Task 1.2: Redis Tiered TTLs
- **Action:** Inject `ex=settings.session_ttl` into Redis `set` calls in `SessionManager`. 
- **Action:** Update rate limiter to use a rolling 1-hour expiration.

#### Task 1.3: Managed Forensic ProcessPool
- **Action:** Initialize `ProcessPoolExecutor` in FastAPI lifespan. 
- **Action:** Update `image.py`, `audio.py`, and `video_tools.py` to use this global executor.

#### Task 1.4: Postgres N+1 Pruning
- **Action:** Optimize `EvidenceStore.get_version_tree` and `get_artifacts_for_session` using `JOIN` optimization.

---

## Track 2: Forensic Observability & DX

### Plan 04-02: Structured Tracing & Frontend
**Core Objective:** Complete the forensic audit trail and optimize user experience.

| Wave | Task | Files Modified | Autonomous |
| :--- | :--- | :--- | :--- |
| 3 | **[BLOCKING] Trace Schema Migration** | `core/persistence/migrations.py` | True |
| 3 | **Agent Trace Instrumentation** | `agents/base_agent.py`, `orchestration/pipeline.py` | True |
| 4 | **Frontend Dynamic Imports** | `apps/web/src/components/*.tsx` | True |
| 4 | **Developer Setup Script** | `scripts/setup_dev.py` | True |

#### Task 2.1: Trace Schema Migration
- **Action:** Create `pipeline_traces` table as designed in research.

#### Task 2.2: Agent Trace Instrumentation
- **Action:** Add `trace_step(task_name, metadata)` hook to `BaseAgent`.
- **Action:** Ensure every tool call records `start_time` and `duration_ms` to the trace table.

#### Task 2.3: Frontend Dynamic Imports
- **Action:** Wrap `ReportViewer` and `FrameExtractor` in `next/dynamic` to reduce bundle size.

#### Task 2.4: Developer Setup Script
- **Action:** Consolidate `init_db.py`, `warmup`, and env validation into a single `python scripts/setup.py` command.

---

## Verification Criteria
1. **Resource Pruning:** Redis `info keyspace` shows decreasing key counts after session expiry simulated.
2. **Concurrency:** `pytest` verifies that API responses remain < 100ms even while an ML tool is saturating a separate process.
3. **Observability:** `SELECT * FROM pipeline_traces` returns a complete hierarchical trail for a new investigation.
4. **Build Size:** `npm run build` output shows a significant reduction in the main `_app.js` bundle size.
