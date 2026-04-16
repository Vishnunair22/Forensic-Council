# Phase 4 Context: Improvement Audit & Implementation

## Phase Goal
Identify and implement improvement opportunities across performance, observability, and resource management to stabilize the Forensic Council v1.4.0 release.

## Decisions Log
The following implementation choices are locked for Phase 4:

### 1. Redis Resource Management (IMPV-01)
- **Policy:** Tiered TTL approach to prevent memory exhaustion.
- **Transients:** Session metadata and heartbeats will have a **4-hour TTL**.
- **Results:** Final investigation reports will have a **7-day TTL** (configurable via `REPORT_CACHE_TTL`).
- **Counters:** Rate limit buckets will have a **1-hour rolling window**.

### 2. Database Optimization (IMPV-02)
- **Priority:** Harden the Artifact listing path (`GET /investigations/{id}/artifacts`).
- **Mechanism:** Replace N+1 lazy loading with SQLAlchemy `selectinload` or `joinedload` for forensic findings and metadata.
- **Audit Logs:** Transition forensic audit logs from linear string appends to batch-inserts for better indexing.

### 3. Async & CPU Concurrency (IMPV-03)
- **Monitoring:** Implement an event loop "Stall Watcher" that logs `WARNING` if the loop is blocked > 100ms.
- **Isolation:** Create a global `ProcessPoolExecutor` (size: `min(32, os.cpu_count())`) dedicated to CPU-bound forensic handlers (ELA, Noise, FFT).
- **Enforcement:** No forensic analysis functions should run in the main thread pool executor.

### 4. Structured Tracing (IMPV-05)
- **Format:** Custom Structured JSON traces with parent-task hierarchy (`trace_id`, `parent_id`, `task_type`, `meta`).
- **Storage:** Persist traces in a dedicated `pipeline_traces` Postgres table rather than volatile Redis memory.
- **Depth:** Every agent tool invocation must produce a trace entry with timestamp, duration, and verdict-influence score.

### 5. Frontend Bundle Optimization (IMPV-04)
- **Code Splitting:** Route-based splitting using standard Next.js directory patterns.
- **Lazy Loading:** The "Heavy" Report Viewer and Frame Extraction UI components will use `next/dynamic` with skeleton loaders.

## Technical Nuances
- **ProcessPool Lifecycle:** The executor must be initialized in the FastAPI `lifespan` and closed gracefully.
- **Fail-Secure:** TTL policies must not delete evidence artifacts from disk; they only manage Redis metadata records.
- **Stall Watcher:** Use `loop.set_debug(True)` in development mode, but use a custom `asyncio` task for production stall warnings to avoid debug-log bloat.

## Success Criteria
- [ ] No module-level dicts used for unbounded session state (everything in Redis with TTL).
- [ ] Pytest integration tests confirm N+1 queries are reduced to O(1) or O(depth).
- [ ] Agent pipeline produces a valid, queryable JSON trace for a multi-artifact investigation.
- [ ] Main event loop latency remains under 50ms even during heavy image analysis.
- [ ] `npm run build` reports reduced initial chunk size for the main dashboard.
