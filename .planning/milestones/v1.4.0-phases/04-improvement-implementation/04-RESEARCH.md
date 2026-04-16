# Phase 4 Research: Improvement Audit & Implementation

## 1. Async Stall Detection (IMPV-03)
**Concern:** Forensic tools performing heavy I/O or CPU work without yielding can "freeze" the WebSocket heartbeat, causing client disconnections.

### Recommended Implementation: Heartbeat Sentinel
Instead of using `loop.set_debug(True)` (which is too verbose for production), we will implement a lightweight sentinel task:

```python
async def loop_heartbeat_monitor(interval=0.05, threshold=0.1):
    while True:
        start = loop.time()
        await asyncio.sleep(interval)
        latency = loop.time() - start - interval
        if latency > threshold:
            logger.warning(f"Event loop stall detected: {latency*1000:.2f}ms")
```

## 2. Redis Tiered TTL Policy (IMPV-01)
**Concern:** Redis memory usage grows indefinitely as every investigation session remains stored.

### Proposed TTL Assignments:
| Category | Key Pattern | TTL | Rationale |
| :--- | :--- | :--- | :--- |
| **Session Meta** | `session:{id}:*` | 4 Hours | Covers a standard investigation window + buffer. |
| **Heartbeats** | `hb:{id}` | 2 Minutes | Temporary presence signal. |
| **Final Reports** | `report:{id}` | 7 Days | Sufficient for immediate forensic review and export. |
| **Rate Limits** | `rl:{ip}` | 1 Hour | Standard abuse protection window. |

## 3. Database N+1 Pruning (IMPV-02)
**Concern:** Listing investigations or artifacts often triggers one query per row to fetch metadata or findings.

### Strategy:
- **Relational Batching:** Update `EvidenceArtifact` retrieval logic to use `JOIN` or `IN (...)` queries in `EvidenceStore.get_all_for_investigation()`.
- **Pre-fetching:** Inject metadata into the initial artifact query using `JSONB` aggregation in Postgres.

## 4. Managed Concurrency (IMPV-03)
**Concern:** CPU-bound forensic checks (ELA, FFT) share the default thread pool with API I/O.

### Implementation:
- **ForensicProcessPool:** Initialize a `ProcessPoolExecutor` in the FastAPI `lifespan` handler.
- **Explicit Dispatch:** All tool handlers in `apps/api/tools/` must use this executor for analysis to keep the main I/O loop free.

## 5. Structured Tracing Schema (IMPV-05)
**Concern:** No machine-readable trace of *why* an agent reached a particular verdict.

### Proposed Schema:
```sql
CREATE TABLE pipeline_traces (
    trace_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id    UUID NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    parent_id     UUID, -- For hierarchical task decomposition
    agent_id      VARCHAR(64) NOT NULL,
    task_name     VARCHAR(255) NOT NULL,
    status        VARCHAR(32) NOT NULL, -- 'pending', 'running', 'success', 'failed'
    start_time    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    end_time      TIMESTAMPTZ,
    duration_ms   INTEGER,
    findings_count INTEGER DEFAULT 0,
    metadata      JSONB NOT NULL DEFAULT '{}' -- Stores specific tool results/influence
);
CREATE INDEX idx_trace_session ON pipeline_traces(session_id);
```

## 6. Frontend Optimization (IMPV-04)
**Concern:** Large charting and frame-extraction libraries bloat the initial dashboard load.

### Strategy:
- **Dynamic Imports:** Use `next/dynamic` for `FrameExtractor.tsx` and `ForensicReport.tsx`.
- **Skeleton States:** Implement `Suspense` boundaries to show UI structure while forensic data stream loads.
