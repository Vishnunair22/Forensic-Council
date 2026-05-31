# Complete Application Flow

> Version: 1.0 — Covers all layers: Frontend → Backend API → Orchestration → Agents → Arbiter → ML → Worker Queue → Infrastructure

---

## Table of Contents

1. [User Authentication & Session Flow](#1-user-authentication--session-flow)
2. [Evidence Upload & Ingestion Flow](#2-evidence-upload--ingestion-flow)
3. [Investigation Pipeline Flow (Agent Execution)](#3-investigation-pipeline-flow)
4. [Arbiter & Verdict Flow](#4-arbiter--verdict-flow)
5. [Human-in-the-Loop (HITL) Flow](#5-human-in-the-loop-hitl-flow)
6. [Report Generation & Signing Flow](#6-report-generation--signing-flow)
7. [WebSocket/SSE Streaming Flow](#7-websocketsse-streaming-flow)
8. [Worker Queue Flow (Background Processing)](#8-worker-queue-flow)
9. [ML Model Inference Flow](#9-ml-model-inference-flow)
10. [Chain of Custody Flow](#10-chain-of-custody-flow)
11. [Infrastructure & Networking Flow](#11-infrastructure--networking-flow)
12. [Security & Rate Limiting Flow](#12-security--rate-limiting-flow)

---

## 1. User Authentication & Session Flow

### 1.1 Firebase Authentication

```
apps/web/src/contexts/auth-context.tsx    ← React Context provider
apps/web/src/lib/firebase-auth.ts          ← Firebase SDK initialization & helpers
apps/web/src/components/withAuth.tsx       ← HOC wrapper for protected routes
apps/api/api/routers/auth.py               ← Backend auth endpoints
apps/api/core/security/authentication.py   ← Token verification & session creation
```

**Sequence:**

1. User opens frontend at `/` (Next.js App Router)
2. `auth-context.tsx` mounts, calls `onAuthStateChanged()` Firebase listener
3. If no token → redirect to FirebaseUI login page at `/`
4. After Firebase login, ID token is obtained client-side
5. Frontend POSTs token to `/api/v1/auth/login`
6. Backend `authentication.py` verifies Firebase token, creates server-side session:
   - Generates session ID (UUID)
   - Stores `session_id → { user_id, email, role, created_at }` in Redis (`core/session/session_manager.py`)
   - Returns signed session cookie + session_id in response body
7. Frontend stores session_id in React Query cache and localStorage
8. All subsequent API calls include `X-Session-ID` header (set in `apps/web/src/lib/api-client.ts`)

### 1.2 Session Validation & Expiry

```
apps/api/core/session/session_manager.py        ← Redis session CRUD + expiry
apps/api/api/routers/sessions.py                ← Session status, refresh, revoke
apps/web/src/app/session-expired/page.tsx        ← Session expiry UI
```

- Sessions TTL: 24 hours (configurable via `SESSION_TTL_MINUTES` env var)
- Every API call hits `middleware/session_middleware.py` which:
  1. Extracts `X-Session-ID` header
  2. Looks up session in Redis
  3. If expired/missing → returns 401 with `session_expired: true`
  4. Extends TTL by sliding window (reset on every valid request)
- Frontend `api-client.ts` interceptor catches 401 `session_expired`:
  1. Clears local session cache
  2. Redirects to `/session-expired`
  3. User can click "Sign In Again" to restart Firebase flow
- Admin sessions (`role == "admin"`) bypass some rate limits

---

## 2. Evidence Upload & Ingestion Flow

### 2.1 Upload Pipeline

```
apps/web/src/components/UploadModal.tsx           ← Drag-and-drop upload UI
apps/web/src/app/evidence/page.tsx                ← Evidence management page
apps/api/api/routers/investigations.py            ← POST /investigations/upload
apps/api/core/evidence/                           ← Evidence processing modules
  storage.py                                      ←   MinIO file storage
  validation.py                                   ←   MIME/type/size validation
  extraction.py                                   ←   Metadata extraction
  thumbnail.py                                    ←   Thumbnail generation
```

**Sequence:**

1. User clicks "Upload Evidence" from `/evidence` page
2. `UploadModal.tsx` opens with drag-and-drop zone
3. Client-side validation:
   - File size ≤ 500MB (configurable, `MAX_UPLOAD_SIZE_MB`)
   - File type in allowed list (image/*, audio/*, video/*, application/pdf)
   - Antivirus check via browser File API (basic mime sniffing)
4. User selects files, clicks "Upload"
5. Frontend creates `FormData` and POSTs to `/api/v1/investigations/upload`
6. Backend `upload_file()` in `investigations.py`:
   1. Receives multipart upload
   2. Runs `upload_size_middleware.py` check (content-length validation)
   3. Generates `evidence_id` (UUIDv4)
   4. Streams file to MinIO bucket: `{tenant_id}/evidence/{evidence_id}/{original_filename}`
   5. Records metadata in PostgreSQL `evidence` table
   6. Runs async ingestion:
      - `extraction.py`: EXIF, file headers, hash (SHA-256), file type detection
      - `validation.py`: Deep file-type validation (magic bytes, not just extension)
      - `thumbnail.py`: Generates thumbnail (images/video keyframes) → stores in MinIO
   7. Returns `evidence_id`, `file_url` (presigned MinIO URL, TTL 1hr), `metadata`
7. Frontend displays uploaded evidence in grid/list view at `/evidence`
8. User can select multiple evidence items and click "Start Investigation"

### 2.2 Evidence Lifecycle States

`evidence.status` transitions:

```
UPLOADING → PENDING → PROCESSING → READY | FAILED
                             ↓
                        (deleted on user request)

UPLOADING:   File streaming to MinIO
PENDING:     Awaiting user action (select for investigation)
PROCESSING:  Ingestion pipeline active (extraction, validation, thumbnail)
READY:       Fully ingested, available for investigation
FAILED:      Ingestion error (corrupt file, unsupported codec, etc.)
```

---

## 3. Investigation Pipeline Flow

### 3.1 Pipeline Initialization

```
apps/api/orchestration/pipeline.py               ← ForensicCouncilPipeline (main orchestrator)
apps/api/orchestration/pipeline_phases.py         ← Individual phase implementations (1386 lines)
apps/api/orchestration/investigation_queue.py     ← Queue management (enqueue/dequeue)
apps/api/orchestration/worker.py                  ← Background worker pool
apps/api/orchestration/session_manager.py         ← Investigation session CRUD
apps/api/api/routers/investigations.py            ← POST /investigations/start
```

**Sequence:**

1. User selects evidence items and clicks "Start Investigation"
2. Frontend POSTs to `/api/v1/investigations/start` with:
   ```json
   { "evidence_ids": ["id1", "id2"], "settings": { "deep_scan": true, "modality": "all" } }
   ```
3. Backend `start_investigation()`:
   1. Validates all evidence_ids exist and are in `READY` state
   2. Generates `investigation_id` (UUIDv4)
   3. Creates investigation record in PostgreSQL (`investigations` table)
   4. Creates session in Redis via `session_manager.py`
   5. Enqueues job to Redis queue: `queue:investigations`
   6. Returns `investigation_id` immediately (202 Accepted)

### 3.2 Worker Dequeue & Pipeline Execution

```
apps/api/orchestration/worker.py                  ← Worker.main_loop()
apps/api/orchestration/pipeline.py                ← Pipeline.run_investigation()
```

4. `worker.py` main loop (runs in background process):
   - BL pops from `queue:investigations` (blocking Redis BRPOP)
   - Calls `pipeline.run_investigation(investigation_id, settings)`

5. `run_investigation()` — 4-phase execution:

   **Phase 0: Infrastructure Initialization**
   ```
   pipeline_phases.py → Phase0InfraInitializer
   ```
   - Loads evidence files from MinIO to local workspace
   - Initializes model cache (`tools/model_cache/`)
   - Spawns ML subprocess pool (if not already running)
   - Creates investigation workspace directory
   - Updates status: `INITIALIZING`

   **Phase 1: Agent Dispatch**
   ```
   pipeline_phases.py → Phase1AgentDispatcher
   ```
   - Determines which agents to run based on evidence modality:
     - Images (JPEG, PNG, WEBP) → ImageAgent, MetadataAgent, ObjectDetectionAgent
     - Audio (WAV, MP3, FLAC) → AudioAgent
     - Video (MP4, AVI, MOV) → VideoAgent, AudioAgent, ImageAgent (frame extraction)
     - Documents (PDF) → MetadataAgent, ObjectDetectionAgent
   - Dispatches agents in parallel via `asyncio.gather()` (up to 3 concurrent)
   - Each agent runs its own ReAct loop (see [3.3](#33-agent-react-loop))
   - Updates status: `AGENTS_RUNNING`

   **Phase 2: Arbiter Processing**
   ```
   pipeline_phases.py → Phase2ArbiterProcessor
   pipeline.py → run_arbiter()
   ```
   - See [Arbiter Flow](#4-arbiter--verdict-flow)
   - Updates status: `ARBITER_DELIBERATING`

   **Phase 3: Finalization**
   ```
   pipeline_phases.py → Phase3Finalizer
   ```
   - Generates final report (see [Report Flow](#6-report-generation--signing-flow))
   - Records chain of custody (see [CoC Flow](#10-chain-of-custody-flow))
   - Cleans up workspace files
   - Updates status: `COMPLETED`
   - Pushes final results to Redis for SSE broadcast

### 3.3 Agent ReAct Loop

```
apps/api/agents/                                   ← Agent base classes & implementations
  base_agent.py                                    ←   Abstract base with ReAct loop
  image_agent.py                                   ←   Image forensics agent
  audio_agent.py                                   ←   Audio forensics agent
  object_detection_agent.py                        ←   Object Detection agent
  video_agent.py                                   ←   Video forensics agent
  metadata_agent.py                                ←   Metadata forensics agent
apps/api/core/react_loop/                          ← ReAct loop engine
  engine.py                                        ←   Main loop (thought → action → observation)
  parser.py                                        ←   Action/observation parsing
  schema.py                                        ←   ReAct input/output schemas
  config.py                                        ←   Max iterations, timeout configs
apps/api/core/llm/                                 ← LLM client layer
  client.py                                        ←   LiteLLM wrapper
  tokenizer.py                                     ←   Token counting & truncation
  callbacks.py                                     ←   Streaming callbacks
apps/api/tools/                                    ← 50 tool implementations (3 directories)
  image_tools/                                     ←   Image analysis tools
  video_tools/                                     ←   Video analysis tools
  audio_tools/                                     ←   Audio analysis tools
  ocr_tools/                                       ←   OCR/text extraction tools
  ml_tools/                                        ←   ML inference gateway tools
  metadata_tools/                                  ←   File metadata tools
```

**Each agent runs the following loop:**

```
                    ┌──────────────────────────────────┐
                    │        ReAct Loop Engine          │
                    │  (max 15 iterations default)      │
                    └──────────────────────────────────┘
                              │
               ┌──────────────┴──────────────┐
               │         THOUGHT              │
               │  (LLM reasons about next     │
               │   action based on context)    │
               └──────────────┬──────────────┘
                              │
               ┌──────────────┴──────────────┐
               │         ACTION               │
               │  (Agent selects + calls a    │
               │   tool from tool registry)   │
               └──────────────┬──────────────┘
                              │
               ┌──────────────┴──────────────┐
               │       OBSERVATION            │
               │  (Tool returns result,       │
               │   stored in context memory)  │
               └──────────────┬──────────────┘
                              │
               ┌──────────────┴──────────────┐
               │   FINAL ANSWER CHECK         │
               │  (LLM decides if sufficient  │
               │   evidence gathered)         │
               └──────────────┬──────────────┘
                              │
                    ┌─────────┴─────────┐
                    │ YES              NO │
                    ▼                    ▼
               Return Result      Continue Loop
```

**Agent Mixins (shared across agents):**

```
apps/api/agents/mixins/
  context_mixin.py        ← Builds & manages ReAct context window
  memory_mixin.py         ← Short-term + long-term memory for agent state
  investigation_mixin.py  ← Investigation-specific methods
  synthesis_mixin.py      ← Synthesizes findings into structured output
  reflection_mixin.py     ← Self-reflection & correction on errors
```

**Tool Call Architecture:**

Each tool call goes through `ml_tools/gateway.py` which:
1. Checks if ML model inference is needed
2. Routes to tool-specific handler
3. If ML required → spawns subprocess (see [ML Flow](#9-ml-model-inference-flow))
4. Returns structured observation

### 3.4 Agent Result Schema

Each agent returns:
```python
{
    "agent_id": "image_agent",
    "status": "completed" | "partial" | "error",
    "findings": {
        "manipulation_detected": bool,
        "confidence": 0.0-1.0,
        "techniques_used": ["ela", "noise_analysis", "clone_detection"],
        "regions_of_interest": [{"bbox": [x1,y1,x2,y2], "score": 0.95}],
        "summaries": ["..."],
        "raw_data": {...}
    },
    "tool_calls": [
        {"tool": "analyze_ela", "duration_ms": 1234, "success": true}
    ],
    "errors": [],
    "token_usage": {"prompt": 1500, "completion": 800}
}
```

---

## 4. Arbiter & Verdict Flow

```
apps/api/agents/arbiter.py               ← Main arbiter agent (928 lines)
apps/api/agents/arbiter_prompts.py        ← Arbiter prompt templates (2404 lines)
apps/api/agents/arbiter_utils.py          ← Arbiter utility functions (538 lines)
apps/api/orchestration/pipeline.py        ← run_arbiter() orchestrator
```

### 4.1 Three-Stage Arbiter Process

**Stage 1: Deliberation** (`arbiter.py → deliberate()`)

1. Collects all agent results from Phase 1
2. Groups findings by evidence item
3. Runs LLM deliberation with structured prompt:
   - Input: All agent reports + evidence metadata + investigation settings
   - Prompt: Analyzes contradictions, corroborations, gaps
   - Output: Deliberation JSON with `{ agreements, contradictions, confidence_scores }`
4. If `deep_scan` enabled → runs second deliberation pass focusing on low-confidence areas

**Stage 2: Verdict Computation** (`arbiter.py → compute_verdict()`)

1. Weighs agent confidence scores (ImageAgent weight: 0.30, AudioAgent: 0.25, VideoAgent: 0.20, ObjectDetection: 0.15, Metadata: 0.10)
2. Computes aggregate manipulation probability per evidence item
3. Assigns verdict per item:
   ```
   score ≥ 0.80  → MANIPULATED
   score 0.50-0.79  → SUSPICIOUS
   score 0.20-0.49  → INCONCLUSIVE
   score < 0.20   → AUTHENTIC
   ```
4. Computes overall investigation verdict (weighted average across items)

**Stage 3: Narrative Compilation** (`arbiter.py → compile_narrative()`)

1. Generates human-readable explanation for each verdict
2. Produces markdown report sections:
   - Executive Summary
   - Per-Evidence Analysis
   - Methodology & Techniques Used
   - Confidence & Limitations
   - Recommendations

### 4.2 HITL Integration Points

Throughout the arbiter process, HITL checkpoints may be inserted:
- **Pre-deliberation**: If settings include `hitl_before_deliberation: true`, pipeline pauses after Phase 1 and waits for human input before arbiter starts
- **Post-deliberation**: If settings include `hitl_before_verdict: true`, pipeline pauses after deliberation and presents preliminary findings to user
- **Pre-finalization**: If settings include `hitl_before_report: true`, user can review/edit narrative before final report generation

See [HITL Flow](#5-human-in-the-loop-hitl-flow) for details.

---

## 5. Human-in-the-Loop (HITL) Flow

```
apps/api/api/routers/hitl.py                       ← HITL API endpoints
apps/api/orchestration/pipeline_phases.py           ← HITL checkpoint integration
apps/web/src/components/HITLCheckpointModal.tsx     ← HITL review UI
apps/web/src/components/ArbiterCard.tsx             ← Arbiter findings display
```

### 5.1 HITL Checkpoint Lifecycle

```
Pipeline Phase 1 Complete
        │
        ▼
┌─────────────────────────────┐
│  HITL Checkpoint Triggered  │
│  (if enabled in settings)   │
│                             │
│  Status: AWAITING_HITL      │
│  Pushes to Redis SSE:       │
│  hitl_checkpoint_required   │
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│  Frontend receives SSE      │
│  event: hitl_required       │
│                             │
│  Shows HITLCheckpointModal  │
│  with preliminary findings  │
└────────────┬────────────────┘
             │
    ┌────────┴────────┐
    │                 │
    ▼                 ▼
┌──────────┐   ┌──────────┐
│ Approve  │   │ Request  │
│ Continue │   │ Changes  │
└────┬─────┘   └────┬─────┘
     │              │
     ▼              ▼
POST to         POST to
/hitl/approve  /hitl/feedback
{session_id,   {session_id,
 checkpoint_id, checkpoint_id,
 approved: true} feedback: "..."}
     │              │
     ▼              ▼
Pipeline      Arbiter re-runs
Resumes       deliberation with
              human feedback
```

### 5.2 HITL Endpoints

```
POST /api/v1/hitl/checkpoint      ← Create checkpoint (internal, called by pipeline)
POST /api/v1/hitl/approve         ← Approve and continue
POST /api/v1/hitl/feedback        ← Submit feedback with changes
POST /api/v1/hitl/reject          ← Reject and abort investigation
GET  /api/v1/hitl/status/{id}     ← Get checkpoint status
GET  /api/v1/hitl/pending         ← List pending HITL checkpoints for user
```

---

## 6. Report Generation & Signing Flow

```
apps/api/core/report/                               ← Report generation modules
  generator.py                                      ←   Markdown report builder
  templates.py                                      ←   Report templates
  renderer.py                                       ←   PDF/HTML rendering
apps/api/core/signing.py                            ← Digital signature & timestamping
apps/api/agents/arbiter.py                          ← Narrative compilation
apps/api/api/routers/investigations.py              ← GET /investigations/{id}/report
```

### 6.1 Report Generation Pipeline

1. Arbiter produces narrative JSON (see Stage 3 above)
2. `report/generator.py` assembles report:
   - Header: Case name, investigation ID, timestamp, investigator info
   - Section 1: Executive Summary (1-2 paragraphs)
   - Section 2: Evidence Inventory (table with file names, hashes, sizes, types)
   - Section 3: Per-Evidence Analysis (detailed findings from each agent)
   - Section 4: Arbiter Verdict (overall + per-item verdicts with confidence scores)
   - Section 5: Methodology (agents used, tools called, ML models)
   - Section 6: Chain of Custody (timeline of every operation)
   - Section 7: Limitations & Caveats
   - Appendix: Raw tool outputs (truncated)
3. `report/renderer.py` converts markdown to PDF (via WeasyPrint) and HTML
4. `signing.py` applies digital signature:
   - Creates SHA-256 hash of PDF
   - Signs hash with investigator's private key (PKCS#7)
   - Optionally queries RFC 3161 TSA server for trusted timestamp
   - Embeds signature + timestamp into PDF metadata
5. Final report stored in MinIO: `{tenant_id}/reports/{investigation_id}/`
6. Chain of custody entry recorded with report fingerprint

### 6.2 Report Access

```
GET  /api/v1/investigations/{id}/report          ← Get report metadata
GET  /api/v1/investigations/{id}/report/pdf      ← Download signed PDF
GET  /api/v1/investigations/{id}/report/verify   ← Verify signature
```

---

## 7. WebSocket/SSE Streaming Flow

```
apps/api/api/routers/websocket.py                 ← WebSocket endpoint
apps/api/api/routers/sse.py                       ← SSE endpoint
apps/web/src/hooks/useInvestigationStream.ts      ← React hook for SSE
apps/web/src/components/AgentProgressDisplay.tsx  ← Real-time progress UI
apps/web/src/components/LiveFindingsPanel.tsx     ← Live findings stream
```

### 7.1 SSE vs WebSocket Decision

| Feature | SSE | WebSocket |
|---------|-----|-----------|
| Direction | Server → Client only | Bidirectional |
| Reconnection | Built-in (EventSource API) | Manual |
| Payload | Text only | Text + Binary |
| Use Case | Progress updates, status changes | HITL interactive sessions |
| Endpoint | `GET /api/v1/stream/{session_id}` | `WS /api/v1/ws/{session_id}` |

### 7.2 SSE Event Stream

Frontend connects via:
```typescript
// apps/web/src/hooks/useInvestigationStream.ts
const source = new EventSource(`/api/v1/stream/${sessionId}`);
```

**Event types pushed from backend:**

| Event Name | Payload | When |
|---|---|---|
| `status` | `{ status: "INITIALIZING" }` | Phase 0 start |
| `agent_started` | `{ agent_id, evidence_id }` | Agent begins |
| `agent_progress` | `{ agent_id, progress: 0.0-1.0, message }` | During agent ReAct loop |
| `agent_completed` | `{ agent_id, summary }` | Agent finishes |
| `tool_call` | `{ agent_id, tool, duration_ms }` | Every tool call |
| `hitl_required` | `{ checkpoint_id, type }` | HITL checkpoint |
| `arbiter_started` | `{}` | Arbiter deliberation begins |
| `arbiter_progress` | `{ stage, message }` | Arbiter stages |
| `verdict` | `{ evidence_id, verdict, confidence }` | Per-item verdict |
| `report_ready` | `{ investigation_id }` | Report generated |
| `error` | `{ message, code }` | Any error |
| `completed` | `{ investigation_id }` | Pipeline done |

### 7.3 Backend SSE Implementation

```
apps/api/api/routers/sse.py
```

- Uses `asyncio.Queue` per connected client
- Pipeline pushes events to Redis pub/sub channel: `investigation:{id}:events`
- SSE endpoint subscribes to Redis pub/sub and forwards to EventSource
- Heartbeat every 30 seconds (comment: `event: ping`)
- Client disconnect detected via `asyncio.CancelledError` (cleanup subscriber)

### 7.4 Frontend State Machine

```
useInvestigationStream.ts:

IDLE → CONNECTING → CONNECTED → RECONNECTING → DISCONNECTED
                         ↓
                   (events update React Query cache)
                         ↓
              AgentProgressDisplay re-renders
              LiveFindingsPanel appends findings
              ArbiterCard updates on verdict events
              HITLCheckpointModal appears on hitl_required
```

---

## 8. Worker Queue Flow

```
apps/api/orchestration/investigation_queue.py     ← Queue abstraction (Redis)
apps/api/orchestration/worker.py                  ← Worker process pool
apps/api/core/config.py                           ← Queue configuration
```

### 8.1 Queue Architecture

```
                    ┌─────────────────────────┐
                    │     Redis (Queue Backend)│
                    │                         │
                    │  queue:investigations   │
                    │  [job_1, job_2, ...]    │
                    │                         │
                    │  queue:results          │
                    │  [result_1, ...]        │
                    │                         │
                    │  queue:dead-letter      │
                    │  [failed_job_1, ...]    │
                    └───────────┬─────────────┘
                                │
                    ┌───────────┴─────────────┐
                    │     Worker Pool (3 procs)│
                    │                         │
                    │  ┌─────────────────────┐│
                    │  │ Worker Process 1    ││
                    │  └─────────────────────┘│
                    │  ┌─────────────────────┐│
                    │  │ Worker Process 2    ││
                    │  └─────────────────────┘│
                    │  ┌─────────────────────┐│
                    │  │ Worker Process 3    ││
                    │  └─────────────────────┘│
                    └─────────────────────────┘
```

### 8.2 Job Lifecycle

1. **Enqueue**: `investigation_queue.py:enqueue(investigation_id)`
   - Pushes `{ investigation_id, settings, created_at }` to `queue:investigations`
   - Sets `investigation:{id}:status = QUEUED` in Redis

2. **Dequeue**: `worker.py:main_loop()`
   - Each worker calls `BRPOP queue:investigations 0` (blocking, infinite wait)
   - On dequeue: sets status to `RUNNING`

3. **Processing**: Worker calls `pipeline.run_investigation()`
   - Status updated at each phase via Redis pub/sub

4. **Completion/Error**:
   - Success: pushes result to `queue:results`, sets status `COMPLETED`
   - Failure (after 3 retries): pushes to `queue:dead-letter`, sets status `FAILED`

5. **ACK**: Investigation result persisted to PostgreSQL; Redis entry TTL'd (7 days)

### 8.3 Worker Configuration

```python
# apps/api/core/config.py
WORKER_CONCURRENCY = 3        # Number of parallel worker processes
MAX_RETRIES = 3               # Max retries per job
QUEUE_BLOCK_TIMEOUT = 0       # BRPOP timeout (0 = infinite)
JOB_TIMEOUT = 3600            # 1 hour max per investigation
```

---

## 9. ML Model Inference Flow

```
apps/api/tools/ml_tools/                           ← ML tool gateway
  gateway.py                                       ←   Routes inference requests
  model_cache.py                                   ←   Model cache manager
apps/api/core/ml/                                  ← ML subprocess management
  subprocess_manager.py                            ←   Spawns/manages ML processes
  inference_protocol.py                            ←   IPC protocol for inference
models/                                            ← Model storage
  clip/                                            ←   CLIP embeddings
  vit/                                             ←   Vision Transformer
  trufor/                                          ←   TruFor forgery detection
  noiseprint/                                      ←   Noiseprint++ noise pattern
  buster_net/                                      ←   BusterNet splicing detection
  f3_net/                                          ←   F3-Net deepfake detection
  ecapa/                                           ←   ECAPA speaker verification
  aasist/                                          ←   AASIST audio anti-spoofing
  yolo/                                            ←   YOLO object detection
  easyocr/                                         ←   EasyOCR text extraction
  siglip2/                                         ←   SigLIP2 vision-language
  faiss/                                           ←   FAISS vector index
```

### 9.1 Inference Pipeline

```
Agent Tool Call
      │
      ▼
ml_tools/gateway.py
      │
      ├── Check model cache (model_cache.py)
      │     ├── Cache HIT → return cached result
      │     └── Cache MISS → continue
      │
      ├── Request model load (if not loaded):
      │     subprocess_manager.py:
      │       └── Spawn ML subprocess (or reuse from pool)
      │             └── Load model weights from models/{model_name}/
      │
      ├── Send inference request via IPC:
      │     inference_protocol.py:
      │       └── { "model": "trufor", "input": image_path, "params": {...} }
      │
      ├── ML subprocess:
      │     1. Preprocess input (resize, normalize, tensor conversion)
      │     2. Run inference (PyTorch model)
      │     3. Postprocess output (softmax, threshold, bounding boxes)
      │     4. Return structured result via stdout/pipe
      │
      ├── Cache result (TTL based on model type)
      │
      └── Return structured observation to agent
```

### 9.2 Model Cache Strategy

```python
# apps/api/tools/ml_tools/model_cache.py
CACHE_TTL = {
    "clip": 3600,          # 1 hour (embedding results)
    "trufor": 300,         # 5 minutes (per-image forgery)
    "noiseprint": 300,
    "yolo": 60,            # 1 minute (detection results)
    "ecapa": 3600,
    "aasist": 3600,
    "faiss": 86400,        # 24 hours (vector index)
}
```

### 9.3 Model Storage

```
models/
  download_models.sh        ← Download all models (called by Dockerfile)
  model_list.json           ← Model manifest (URLs, hashes, sizes)
  clip/                     ~ 2.5GB
  vit/                      ~ 1.5GB
  trufor/                   ~ 800MB
  noiseprint/               ~ 600MB
  buster_net/               ~ 400MB
  f3_net/                   ~ 500MB
  ecapa/                    ~ 300MB
  aasist/                   ~ 200MB
  yolo/                     ~ 250MB
  easyocr/                  ~ 200MB
  siglip2/                  ~ 2GB
  faiss/                    depends on index size
```

---

## 10. Chain of Custody Flow

```
apps/api/core/chain_of_custody.py                  ← CoC creation & verification
apps/api/orchestration/pipeline.py                 ← CoC recording points
apps/api/agents/mixins/investigation_mixin.py      ← Agent-level CoC entries
```

### 10.1 Recording Points

Every operation that touches evidence is recorded:

| Event | Data Recorded | By Whom |
|---|---|---|
| File Upload | Timestamp, user_id, file hash (SHA-256), file size | Upload handler |
| File Access | Timestamp, agent_id, operation type | agent mixin |
| Tool Execution | Tool name, params, duration, result summary | ReAct loop |
| ML Inference | Model name, input hash, confidence | ml_tools/gateway.py |
| Agent Decision | Agent ID, verdict, confidence | Agent.finalize() |
| Arbiter Deliberation | Arbiter ID, input hash, output hash | arbiter.py |
| Report Generation | Report hash, signing key ID | signing.py |
| Report Download | Timestamp, user_id, IP | Report endpoint |

### 10.2 CoC Structure

```python
# chain_of_custody.py
ChainOfCustodyEntry = {
    "event_id": "uuid",
    "timestamp": "ISO 8601",
    "actor": "user:{id}" | "agent:{name}" | "system",
    "action": "upload" | "access" | "analyze" | "infer" | "decide" | "sign" | "download",
    "evidence_id": "uuid" | null,
    "evidence_hash": "sha256" | null,
    "details": {...},
    "previous_event_hash": "sha256",  # ← linked list chain
    "event_hash": "sha256"             # ← hash(this_entry + prev_hash)
}
```

### 10.3 Verification

```
GET /api/v1/investigations/{id}/chain-of-custody   ← Retrieve full chain
GET /api/v1/investigations/{id}/chain-of-custody/verify ← Verify integrity
```

Verification recomputes all hashes and checks the chain integrity (tamper detection).

---

## 11. Infrastructure & Networking Flow

```
infra/docker-compose.yml                 ← 10 services, 4 networks, 637 lines
infra/caddy/                             ← Caddy reverse proxy config
infra/prometheus/                        ← Prometheus config
  prometheus.yml
infra/prometheus/alertmanager/           ← Alertmanager config
infra/prometheus/grafana/dashboards/     ← Grafana dashboards (7 JSON files)
infra/prometheus/grafana/provisioning/   ← Grafana provisioning
infra/postgres/                          ← PostgreSQL init scripts
  init.sql                               ←   Schema initialization
  extensions.sql                         ←   Extensions setup
```

### 11.1 Network Topology

```
                    ┌──────────────┐
                    │   INTERNET   │
                    └──────┬───────┘
                           │ :80 / :443
                    ┌──────▼───────┐
                    │   CADDY      │ ← Reverse proxy, TLS termination
                    │  infra_net   │
                    └──────┬───────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                   │
        ▼                  ▼                   ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│  frontend_net │  │  backend_net  │  │  external_net  │
│               │  │               │  │                │
│  nextjs:3000  │  │  api:8000     │  │  postgres:5432 │
│               │  │  worker:*     │  │  redis:6379    │
│               │  │               │  │  minio:9000    │
│               │  │               │  │                │
│               │  │               │  │  n8n:5678      │
└───────────────┘  └───────────────┘  └────────────────┘
                           │
                           ▼
                    ┌───────────────┐
                    │   infra_net   │
                    │               │
                    │  prometheus   │
                    │  grafana      │
                    │  alertmanager │
                    └───────────────┘
```

### 11.2 Service-to-Service Communication

| From | To | Protocol | Network |
|---|---|---|---|
| Caddy | Next.js | HTTP | frontend_net |
| Caddy | FastAPI | HTTP | backend_net |
| Next.js | FastAPI | HTTP (API proxy) | backend_net |
| FastAPI | PostgreSQL | TCP (psycopg2) | external_net |
| FastAPI | Redis | TCP (redis-py) | external_net |
| FastAPI | MinIO | HTTP (S3 API) | external_net |
| Worker | Redis | TCP (redis-py) | external_net |
| Worker | MinIO | HTTP (S3 API) | external_net |
| N8N | FastAPI | HTTP (webhook) | backend_net |
| Caddy | Prometheus | HTTP | infra_net |
| Grafana | Prometheus | HTTP | infra_net |

### 11.3 Monitoring Stack

```
prometheus/
  prometheus.yml                ← Scrape config for all services
  alertmanager/
    config.yml                  ← Alert routing (email, slack, pager)
  grafana/dashboards/
    infrastructure_monitoring.json
    application_metrics.json
    model_performance.json
    api_performance.json
    database_metrics.json
    business_metrics.json
    docker_container_monitoring.json
```

**Metrics collected:**
- API: request count, latency (p50/p95/p99), error rate, status codes
- Pipeline: investigation duration (per phase), agent duration, tool call metrics
- ML: inference latency, model cache hit/miss rate, GPU utilization
- System: CPU, memory, disk I/O, network I/O
- Queue: queue depth, processing time, retry/failure rate

### 11.4 Docker Compose Service Dependencies

```
caddy:        depends_on: [nextjs, api]
nextjs:       depends_on: [api]
api:          depends_on: [redis, postgres, minio]
worker:       depends_on: [redis, postgres, minio, api]
redis:        (no depends)
postgres:     (no depends)
minio:        (no depends)
n8n:          depends_on: [postgres]
prometheus:   depends_on: [cadvisor]
grafana:      depends_on: [prometheus]
alertmanager: depends_on: [prometheus]
```

### 11.5 Health Check Chain

```
Caddy (port 80/443)
  └── Next.js (port 3000 /health)
        └── FastAPI (port 8000 /api/v1/health)
              ├── Redis (PING)
              ├── PostgreSQL (SELECT 1)
              ├── MinIO (list buckets)
              └── ML Subprocess (status check)
```

---

## 12. Security & Rate Limiting Flow

```
apps/api/api/middleware/                           ← Middleware directory
  cors_middleware.py                               ←   CORS headers
  csrf_middleware.py                               ←   CSRF token validation
  rate_limit_middleware.py                         ←   Rate limiting
  upload_size_middleware.py                        ←   Upload size enforcement
  metrics_middleware.py                            ←   Request metrics
  correlation_id_middleware.py                     ←   Request tracing
apps/api/core/security/                            ← Security modules
  authentication.py                                ←   Firebase token verification
  authorization.py                                 ←   Role-based access control
  encryption.py                                    ←   Data encryption at rest
  audit.py                                         ←   Audit logging
```

### 12.1 Middleware Stack Order

```python
# api/main.py — middleware order (first = outermost)
1. CorrelationIDMiddleware    ← Adds X-Correlation-ID to every request
2. MetricsMiddleware          ← Records request metrics (counter, latency)
3. CORSMiddleware             ← Sets CORS headers for frontend origin
4. CSRFMiddleware             ← Validates CSRF token on state-changing requests
5. RateLimitMiddleware        ← Enforces per-session/per-IP rate limits
6. UploadSizeMiddleware       ← Rejects oversized uploads early
```

### 12.2 Rate Limits

| Endpoint Group | Limit | Window | Scope |
|---|---|---|---|
| `/api/v1/auth/*` | 10 req | 1 minute | Per IP |
| `/api/v1/investigations/upload` | 50 MB/min | 1 minute | Per session |
| `/api/v1/investigations/start` | 5 req | 10 minutes | Per session |
| `/api/v1/hitl/*` | 30 req | 1 minute | Per session |
| `/api/v1/stream/*` | 1 connection | concurrent | Per session |
| `/api/v1/ws/*` | 1 connection | concurrent | Per session |
| General API | 100 req | 1 minute | Per session |
| Admin API | 500 req | 1 minute | Per IP |

### 12.3 Authentication Flow

```
Request → CorrelationIDMiddleware
         → MetricsMiddleware
         → CORSMiddleware (validates origin)
         → CSRFMiddleware (if state-changing: validates token)
         → RateLimitMiddleware (checks Redis counter)
         → SessionMiddleware (validates X-Session-ID against Redis)
              → AuthenticationMiddleware (verifies Firebase token on auth endpoints)
              → AuthorizationMiddleware (checks role for admin endpoints)
         → Route Handler
```

### 12.4 Audit Logging

```python
# core/security/audit.py
audit_log = {
    "timestamp": "ISO 8601",
    "correlation_id": "uuid",
    "user_id": "uuid",
    "session_id": "uuid",
    "action": "investigation.start" | "evidence.upload" | "report.download",
    "resource_id": "uuid",
    "ip_address": "x.x.x.x",
    "user_agent": "Mozilla/...",
    "success": true,
    "details": {...}
}
```

Audit logs are written to:
1. PostgreSQL `audit_logs` table (immediate)
2. ZincObserve (via Promtail) for long-term retention
3. Application log file (structured JSON)

---

## End-to-End Flow Summary

```
USER                    FRONTEND                  BACKEND API              ORCHESTRATOR            AGENTS/ML                  INFRA
 │                         │                          │                        │                     │                          │
 │──Login─────────────────►│                          │                        │                     │                          │
 │                         │──POST /auth/login───────►│                        │                     │                          │
 │                         │◄──session_token──────────│                        │                     │                          │
 │                         │                          │                        │                     │                          │
 │──Upload Evidence───────►│                          │                        │                     │                          │
 │                         │──POST /upload───────────►│                        │                     │                          │
 │                         │                          │──store→MinIO───────────├─────────────────────│──────────────────────────►│
 │                         │                          │──extract metadata──────│                     │                          │
 │                         │◄──evidence_id────────────│                        │                     │                          │
 │                         │                          │                        │                     │                          │
 │──Start Investigation───►│                          │                        │                     │                          │
 │                         │──POST /investigations────│                        │                     │                          │
 │                         │                          │──enqueue→Redis────────►│                     │                          │
 │                         │◄──investigation_id───────│                        │                     │                          │
 │                         │                          │                        │                     │                          │
 │                         │──connect SSE────────────►│◄──────────────────────│──dequeue from Redis  │                          │
 │                         │                          │                        │                     │                          │
 │                         │◄──SSE: status────────────│◄───pub/sub events──────│                     │                          │
 │                         │                          │                        │──Phase 0: Init──────►│                          │
 │                         │                          │                        │──Phase 1: Agents────►│                          │
 │                         │◄──SSE: agent_progress────│◄──────────────────────│                     │──ReAct Loop─────────────►│
 │                         │                          │                        │                     │──Tool Calls─────────────►│
 │                         │                          │                        │                     │──ML Inference───────────►│
 │                         │                          │                        │──Phase 2: Arbiter───│                          │
 │                         │                          │                        │                     │──Deliberation───────────►│
 │                         │                          │                        │                     │──Verdict────────────────│
 │                         │◄──SSE: verdict───────────│◄──────────────────────│                     │                          │
 │                         │                          │                        │──Phase 3: Finalize──│                          │
 │                         │                          │                        │──Generate Report────│                          │
 │                         │                          │                        │──Sign Report────────│                          │
 │                         │◄──SSE: report_ready──────│◄──────────────────────│                     │                          │
 │                         │                          │                        │                     │                          │
 │──View Results──────────►│                          │                        │                     │                          │
 │                         │──GET /investigations/id─►│                        │                     │                          │
 │                         │◄──full_results───────────│                        │                     │                          │
 │                         │──GET /report/pdf────────►│                        │                     │                          │
 │                         │◄──signed_pdf─────────────│                        │                     │                          │
```

---

## File Reference Index

### Frontend (`apps/web/src/`)
| File | Purpose |
|---|---|
| `app/page.tsx` | Home page / login |
| `app/evidence/page.tsx` | Evidence upload & management |
| `app/result/[sessionId]/page.tsx` | Investigation results view |
| `app/session-expired/page.tsx` | Session expiry notification |
| `app/api/v1/[...path]/route.ts` | API proxy (Next.js → FastAPI) |
| `components/UploadModal.tsx` | Drag-and-drop upload UI |
| `components/AgentProgressDisplay.tsx` | Real-time agent progress |
| `components/ArbiterCard.tsx` | Arbiter findings display |
| `components/HITLCheckpointModal.tsx` | HITL review modal |
| `components/LiveFindingsPanel.tsx` | Live streaming findings |
| `components/SessionExpired.tsx` | Session expiry banner |
| `contexts/auth-context.tsx` | Auth state provider |
| `hooks/useInvestigationStream.ts` | SSE connection hook |
| `lib/api-client.ts` | HTTP client with auth/session headers |
| `lib/firebase-auth.ts` | Firebase SDK initialization |

### Backend API (`apps/api/`)
| File | Purpose |
|---|---|
| `api/main.py` | FastAPI app entry, router mounts, middleware |
| `api/routers/auth.py` | Authentication endpoints |
| `api/routers/investigations.py` | Investigation CRUD + upload + start |
| `api/routers/sessions.py` | Session management |
| `api/routers/hitl.py` | HITL checkpoint endpoints |
| `api/routers/websocket.py` | WebSocket endpoint |
| `api/routers/sse.py` | SSE streaming endpoint |
| `api/routers/metrics.py` | Prometheus metrics endpoint |
| `api/routers/webhooks.py` | N8N webhook receiver |
| `api/routers/cases.py` | Case management |
| `api/middleware/*.py` | 6 middleware modules |
| `core/config.py` | Application configuration |
| `core/evidence/storage.py` | MinIO evidence storage |
| `core/evidence/validation.py` | File validation |
| `core/evidence/extraction.py` | Metadata extraction |
| `core/evidence/thumbnail.py` | Thumbnail generation |
| `core/session/session_manager.py` | Redis session management |
| `core/security/authentication.py` | Firebase token verification |
| `core/security/authorization.py` | Role-based access control |
| `core/security/encryption.py` | Data encryption |
| `core/security/audit.py` | Audit logging |
| `core/react_loop/engine.py` | ReAct loop engine |
| `core/react_loop/parser.py` | Action parsing |
| `core/react_loop/schema.py` | I/O schemas |
| `core/llm/client.py` | LiteLLM client wrapper |
| `core/ml/subprocess_manager.py` | ML subprocess management |
| `core/ml/inference_protocol.py` | ML IPC protocol |
| `core/report/generator.py` | Report builder |
| `core/report/templates.py` | Report templates |
| `core/report/renderer.py` | PDF/HTML rendering |
| `core/signing.py` | Digital signature |
| `core/chain_of_custody.py` | Chain of custody |

### Agents (`apps/api/agents/`)
| File | Purpose |
|---|---|
| `base_agent.py` | Abstract base with ReAct loop |
| `image_agent.py` | Image forensics |
| `audio_agent.py` | Audio forensics |
| `object_detection_agent.py` | Object detection |
| `video_agent.py` | Video forensics |
| `metadata_agent.py` | Metadata forensics |
| `arbiter.py` | Arbiter deliberation + verdict |
| `arbiter_prompts.py` | Arbiter prompt templates |
| `arbiter_utils.py` | Arbiter utilities |
| `mixins/context_mixin.py` | Context management |
| `mixins/memory_mixin.py` | Memory management |
| `mixins/investigation_mixin.py` | Investigation utilities |
| `mixins/synthesis_mixin.py` | Result synthesis |
| `mixins/reflection_mixin.py` | Self-reflection |

### Orchestration (`apps/api/orchestration/`)
| File | Purpose |
|---|---|
| `pipeline.py` | Main orchestrator (4 phases) |
| `pipeline_phases.py` | Phase implementations |
| `investigation_queue.py` | Redis queue management |
| `worker.py` | Background worker pool |
| `session_manager.py` | Investigation session CRUD |

### Tools (`apps/api/tools/`)
| Directory | Contents |
|---|---|
| `image_tools/` | ELA, noise analysis, clone detection, etc. |
| `video_tools/` | Frame extraction, motion analysis, etc. |
| `audio_tools/` | Spectrogram analysis, voice comparison, etc. |
| `ocr_tools/` | Text detection, extraction |
| `ml_tools/` | ML inference gateway, model cache |
| `metadata_tools/` | EXIF, file headers, hash computation |

### Infrastructure (`infra/`)
| File | Purpose |
|---|---|
| `docker-compose.yml` | 10 services, 4 networks |
| `caddy/Caddyfile` | Reverse proxy config |
| `prometheus/prometheus.yml` | Metrics scrape config |
| `prometheus/alertmanager/config.yml` | Alert routing |
| `prometheus/grafana/dashboards/*.json` | 7 dashboards |
| `postgres/init.sql` | Database initialization |
| `postgres/extensions.sql` | PostgreSQL extensions |

### Scripts
| File | Purpose |
|---|---|
| `scripts/dev.sh` | Development environment startup |
| `scripts/prod.sh` | Production deployment |
| `scripts/rebuild.sh` | Full rebuild |
| `scripts/dev-restart-worker.sh` | Worker restart |
| `scripts/clean_project.sh` | Cleanup |
| `scripts/_platform_detect.sh` | OS detection (Linux/macOS/WSL) |
| `scripts/_path_utils.sh` | Path normalization |
| `scripts/_docker_utils.sh` | Docker compose helpers |
| `scripts/_validate_env.sh` | Environment validation |
| `scripts/_config.sh` | Centralized configuration |
| `scripts/_pre_build_validation.sh` | Pre-build checks |
| `scripts/model_download_with_retry.sh` | Model download with retry |
| `scripts/validate_production_readiness.sh` | Production readiness check |
| `scripts/troubleshoot.sh` | Troubleshooting |
| `Dockerfile` | API build (8-stage) |
| `docker_entrypoint.sh` | Container entrypoint |

---

## Environment Variables

```
# Core
ENVIRONMENT=development|production
LOG_LEVEL=DEBUG|INFO|WARNING|ERROR
SECRET_KEY=<auto-generated>
SESSION_TTL_MINUTES=1440

# Database
DATABASE_URL=postgresql://...
POSTGRES_DB=forensic_council
POSTGRES_USER=...
POSTGRES_PASSWORD=...

# Redis
REDIS_URL=redis://redis:6379/0

# MinIO
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=...
MINIO_SECRET_KEY=...
MINIO_BUCKET_EVIDENCE=evidence
MINIO_BUCKET_REPORTS=reports

# Firebase
FIREBASE_PROJECT_ID=...
FIREBASE_PRIVATE_KEY=...
FIREBASE_CLIENT_EMAIL=...

# LLM
LLM_PROVIDER=openai|anthropic|azure|ollama
LLM_API_KEY=...
LLM_MODEL=gpt-4o|claude-3-opus
LLM_MAX_TOKENS=128000
LLM_TEMPERATURE=0.1

# ML
ML_MODEL_DIR=/app/models
ML_SUBPROCESS_TIMEOUT=120
ML_CACHE_ENABLED=true
ML_CACHE_TTL=300

# Queue
WORKER_CONCURRENCY=3
MAX_RETRIES=3
JOB_TIMEOUT=3600

# Rate Limits
RATE_LIMIT_GENERAL=100
RATE_LIMIT_UPLOAD=50
RATE_LIMIT_INVESTIGATION=5

# Caddy
CADDY_DOMAIN=localhost
CADDY_EMAIL=admin@example.com
CADDY_ACME_CA=https://acme-staging-v02.api.letsencrypt.org/directory

# Monitoring
PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus
METRICS_ENABLED=true
```

---

## Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0 | 2026-05-30 | Forensic Council Team | Initial comprehensive flow documentation |
