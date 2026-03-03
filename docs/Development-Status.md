# Development Status

**Last updated:** 2026-03-03  
**Current version:** 0.6.0  
**Overall health:** 🟡 Beta — pipeline functional, HITL incomplete, auth absent  
**Actively working on:** Qdrant integration stability  
**Blocked on:** Nothing currently  

---

## Pipeline Health

Upload → [✅] → Evidence Store → [✅] → Agent Dispatch → [🟡] → Council Arbiter → [🟡] → Signing → [✅] → Report → [✅]

| Stage | Status | Notes |
|-------|--------|-------|
| Upload | ✅ | File validation, MIME type checking, size limits enforced |
| Evidence Store | ✅ | Immutable storage with SHA-256 integrity verification |
| Agent Dispatch | 🟡 | Sequential execution working, concurrent optimization pending |
| Council Arbiter | 🟡 | Signing complete, cross-modal correlation WIP |
| Signing | ✅ | HMAC-SHA256 signatures with key derivation from SIGNING_KEY |
| Report | ✅ | Multi-format rendering with custody chain verification |

**Supporting Systems:**
- HITL Checkpoint injection: [🟡 Backend complete, 🔴 UI incomplete]
- WebSocket event stream: [✅ All 5 agent events + completion event]
- Custody logging: [✅ Immutable append-only chain verified]
- Session management: [🔴 No auth — all sessions publicly accessible]

---

## Component Status

### Infrastructure

| Component | Status | Notes |
|-----------|--------|-------|
| PostgreSQL 16 | ✅ Production | Schema stable, migrations tracked |
| Redis 7 | ✅ Production | Pub/Sub confirmed working for WS events, 24h TTL on working memory |
| Qdrant v1.11.0 | ✅ Production | Upgraded from v1.9.2, query_points API functional |
| Docker Compose | ✅ Production | Multi-stage build with `uv`, healthchecks passing |
| Evidence Store | ✅ Production | Upload, retrieval, integrity checks confirmed |

### Agents

| Agent | Implementation | ReAct Loop | Finding Quality | Test Coverage |
|-------|----------------|------------|-----------------|---------------|
| Agent 1 — Image | ✅ Complete | ✅ Working | 🟢 High — ELA & GMM reliable | 87% |
| Agent 2 — Audio | ✅ Complete | ✅ Working | 🟢 High — librosa splice detection | 71% |
| Agent 3 — Object | 🟡 Partial | ✅ Working | 🔴 Low — spatial heuristics only, no ML model | 45% |
| Agent 4 — Video | 🟡 Partial | ✅ Working | 🟡 Medium — frequency frame extraction only | 38% |
| Agent 5 — Metadata | ✅ Complete | ✅ Working | 🟢 High — EXIF/XMP anomaly scoring | 83% |
| Council Arbiter | 🟡 Partial | ✅ Working | 🟡 Signing done, cross-modal correlation WIP | 52% |

### Backend Services

| Service | Status | Notes |
|---------|--------|-------|
| FastAPI application | ✅ Production | Health checks, CORS, rate limiting implemented |
| Investigation pipeline | 🟡 Functional | Sequential dispatch working, error recovery partial |
| HITL checkpoint system | 🟡 Partial | Backend logic complete, frontend modal pending |
| WebSocket live events | ✅ Production | AGENT_STARTED, AGENT_COMPLETE, INVESTIGATION_COMPLETE, HITL_CHECKPOINT |
| Cryptographic signing | ✅ Production | HMAC-SHA256, deterministic key derivation, verified roundtrip |
| Custody logger | ✅ Production | Immutable append-only chain with verification |
| Session management | 🔴 Incomplete | No auth — sessions publicly accessible |
| Confidence calibration | 🟡 Partial | Formula implemented, not validated against ground truth |
| Rate limiting | ✅ Production | 5 uploads/10min per investigator via Redis sliding window |

### Frontend

| Page / Feature | Status | Notes |
|----------------|--------|-------|
| Landing page (Three.js) | ✅ Complete | 3D scene, "Start Investigation" CTA working |
| Evidence upload | ✅ Complete | Drag-drop, file validation, preview for images |
| Live analysis view | 🟡 Partial | Agent cards + WebSocket updates work, HITL modal missing |
| Report page | ✅ Complete | Verdict badge, agent findings, signature verification displayed |
| Error boundary | ✅ Complete | User-friendly fallback, no stack traces in production |
| HITL decision modal | 🔴 Not started | Backend ready and waiting since v0.3 |
| Session expiry handling | 🔴 Not started | Currently shows blank page on invalid session |

---

## Known Issues

| # | Severity | Description | Workaround | Since |
|---|----------|-------------|------------|-------|
| 1 | 🔴 High | Session auth absent — any session ID accessible by anyone | Dev only — do not expose publicly | v0.1 |
| 2 | 🔴 High | Agent 3 (Object Detection) uses heuristics only — high false positive rate | Treat findings as indicative only | v0.2 |
| 3 | 🟡 Medium | Redis memory can grow under heavy load despite TTL | `FLUSHDB` if OOM errors occur | v0.4 |
| 4 | 🟡 Medium | WebSocket subprocess timeouts occasionally fail to kill child processes | Restart `forensic_api` container | v0.5 |
| 5 | 🟡 Medium | Arbiter cross-modal correlation not yet implemented | Findings listed but not correlated | v0.4 |
| 6 | 🟢 Low | Agent 4 (Video) temporal analysis is shallow | Frame-level only, no scene-level | v0.3 |

---

## Production-Ready vs. Prototype

### Trust in production
These components have been tested against real inputs, edge cases handled, and findings are reliable:
- Evidence upload, storage, and retrieval with integrity verification
- Agent 1 (Image) — ELA anomaly detection and EXIF analysis
- Agent 2 (Audio) — spectral analysis and splice detection
- Agent 5 (Metadata) — all parsing and validation with GPS/timestamp checks
- Cryptographic signing and verification
- WebSocket event broadcasting
- Custody logging with tamper detection
- Rate limiting and input validation

### Functional but not production-trustworthy
These work correctly but haven't been validated against ground truth data, have known edge case failures, or lack sufficient test coverage:
- Agent 3 (Object Detection) — spatial heuristics only, high false positive rate
- Agent 4 (Video) — frame extraction works, temporal analysis is shallow
- Confidence calibration — formula correct, not validated empirically
- Council Arbiter correlation — sequential fallback, not true cross-modal analysis

### Not production-safe
Do not deploy publicly while these are incomplete:
- Session authentication — sessions are unauthenticated and public
- HITL UI — decisions cannot be submitted from the frontend

---

## Current Focus

**Qdrant Integration Stability**

Fixed version incompatibility between Qdrant client (v1.17.0) and server (v1.9.2). The `query_points` API required server v1.10+, causing 404 errors on all vector similarity searches. Upgraded server to v1.11.0 and added `check_compatibility=False` to client initialization.

Target: Ensure episodic memory and all Qdrant-dependent tests pass consistently.  
Status: ✅ Complete — all 23 Qdrant-related tests now passing.

## Next Up

1. **HITL modal — frontend** — Backend has been ready since v0.3, this is the last piece needed for the full HITL flow to work end-to-end
2. **Session authentication** — JWT or API key, must be done before any non-local deployment
3. **Agent 3 ML model integration** — Replace heuristics with a real object detection model (YOLO or equivalent)

---

## Deliberate Omissions

These were considered and consciously excluded. Do not re-open without a strong reason.

**Multi-user real-time collaboration**  
Would require a full presence/locking system on top of the session model. Forensic analysis is a single-analyst workflow. Descoped at v0.2.

**GPU inference natively in backend**  
Starves the ASGI event loop. All heavy ML relies on CPU subprocess bounds (IsolationForests, Fast Fourier Transforms) over deep neural networks to maintain portability. Cloud API is fast enough for current evidence sizes (< 100MB).

**PDF report export**  
The report page is the report. Adding PDF generation (WeasyPrint/Puppeteer) adds a dependency and a maintenance surface for formatting. Deferred to v1.0 if users request it. Currently can be printed natively.

**Streaming agent results to Qdrant in real-time**  
Considered for enabling similarity search across past investigations. Descoped because investigation corpus is too small to benefit from vector similarity at current scale. Architecture supports adding it later.

**Advanced video deepfake detection**  
Requires significant compute resources and specialized models. Current frame consistency analysis provides basic temporal anomaly detection. Full deepfake detection descoped to v2.0.

---

## Version Dependencies

| Dependency | Required | Reason |
|------------|----------|--------|
| Python | 3.11+ | `asyncio.TaskGroup`, structural pattern matching, `tomllib` stdlib |
| Node.js | 20+ | Native `fetch()` support in Next.js Server Actions |
| Next.js | 16.1.6 | Specific App Router behavior required for WebSocket proxying |
| Qdrant | v1.11.0 | `query_points` API required for episodic memory search |
| PostgreSQL | 16 | `pg_isready` flags used in healthchecks |
| Redis | 7 | Pub/Sub improvements used for WS broadcasting |
| uv | 0.5+ | Fast Python package management and virtual env |
| LangGraph | 0.2.70 | Pinned — breaking changes between minor versions |

---

## Maintenance Discipline

**Update this document before closing any task.** Not after, not in a batch at the end of the week — before. The 30 seconds it takes to change a row from 🟡 to ✅ is also the moment you're most aware of *why* it's now complete and what caveats exist.

**Review Known Issues at the start of every session.** Read the list before writing any code. Either you're about to fix something on the list (update it), or you're about to add a feature that touches something broken (you need to know).

**When something is fixed, move it to ERROR_LOG.md immediately.** Known issues that are resolved but not documented create confusion about what's still active.
