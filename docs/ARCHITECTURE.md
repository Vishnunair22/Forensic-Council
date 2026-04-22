# System Architecture â€” Forensic Council

**Version:** v1.4.0

---

## High-Level Data Flow

```
Browser
  â”‚
  â”œâ”€ POST /api/v1/investigate (multipart evidence file)
  â”‚       â”‚
  â”‚       â–¼
  â”‚   FastAPI (uvicorn)
  â”‚       â”‚
  â”‚       â”œâ”€ SHA-256 hash + evidence ingestion â†’ PostgreSQL + LocalStore
  â”‚       â”‚
  â”‚       â”œâ”€ ForensicCouncilPipeline.run_investigation()
  â”‚       â”‚       â”‚
  â”‚       â”‚       â”œâ”€ Phase 1: Initial pass (Sequential)
  â”‚       â”‚       â”‚   Agent 1 â†’ Agent 2 â†’ Agent 3 â†’ Agent 4 â†’ Agent 5
  â”‚       â”‚       â”‚
  â”‚       â”‚       â”œâ”€ PIPELINE_PAUSED â†’ WebSocket broadcast
  â”‚       â”‚       â”‚   (wait for POST /api/v1/sessions/{id}/resume)
  â”‚       â”‚       â”‚
  â”‚       â”‚       â”œâ”€ Phase 2: Deep Analysis (Hybrid Parallel)
  â”‚       â”‚       â”‚   Agent 1 runs first â†’ Signals concurrent start for 2, 3, 4, 5
  â”‚       â”‚       â”‚   (Agent 1 injects Gemini context into Agent 3 + Agent 5)
  â”‚       â”‚       â”‚
  â”‚       â”‚       â””â”€ CouncilArbiter.deliberate()
  â”‚       â”‚               â”œâ”€ Finding deduplication + cross-modal comparison
  â”‚       â”‚               â”œâ”€ Verdict (5-tier) + per-agent Groq narrative
  â”‚       â”‚               â””â”€ ECDSA P-256 signing â†’ PIPELINE_COMPLETE broadcast
  â”‚       â”‚
  â”‚       â””â”€ Persist report â†’ PostgreSQL
  â”‚
  â”œâ”€ WS /api/v1/sessions/{id}/live (JWT auth on connect)
  â”‚       Real-time cognitive trace stream (200ms heartbeat)
  â”‚
  â””â”€ GET /api/v1/sessions/{id}/report
          Returns signed ReportDTO (200) or in-progress (202)
```

---

## Infrastructure Components

### Redis â€” Working Memory & Rate Control
- **Purpose:** Ultra-low-latency reads/writes for per-session agent scratchpad
- **Usage:**
  - Per-agent `WorkingMemory` state (task queue, iteration counter)
  - Token blacklist (`blacklist:{token}`) for logout invalidation
  - IP-based rate limiting (sliding window via Lua)
  - Token-hashed rate limiting for authenticated users
- **TTL:** 24-hour automatic expiry on all session keys

### PostgreSQL 17 â€” The Forensic Ledger
- **Purpose:** ACID-compliant immutable custody record
- **Tables:**
  - `investigation_state` â€” active session pipeline state
  - `session_reports` â€” completed report JSON blobs
  - `chain_of_custody` â€” every signed agent action entry
  - `evidence_artifacts` â€” ingested file metadata + hashes
  - `hitl_checkpoints` â€” Human-in-the-Loop decision history
  - `users`, `user_sessions`, `audit_log` â€” auth & audit trail
  - `calibration_models` â€” Platt scaling model params
  - `forensic_reports` â€” final signed report archive
- **Migrations:** Version-controlled via `core/migrations.py` (5 migrations, idempotent)

### Qdrant â€” Episodic Memory (Vector Similarity)
- **Purpose:** Historical finding correlation for episodic memory
- **Usage:** Agents query for similar past findings to calibrate confidence and detect recurring patterns
- **Collection:** `forensic_episodes` (512-dim cosine similarity â€” CLIP ViT-B-32)
- **Note:** Non-critical â€” system degrades gracefully to local storage if Qdrant is unreachable

---

## Agent Architecture

All 5 specialist agents extend `ForensicAgent` (abstract base class) and share:

1. **ReAct loop** (`core/react_loop.py`) â€” Reason â†’ Act â†’ Observe cycle
   - Task-decomposition driver (default, no LLM needed)
   - Optional Groq LLM driver for richer reasoning traces
2. **Working memory** â€” Redis-backed task queue with 200ms heartbeat to frontend
3. **Self-reflection pass** â€” Quality check after tool execution
4. **Episodic memory** â€” Historical context from Qdrant
5. **Chain-of-custody logging** â€” Every signed entry to PostgreSQL
6. **Post-synthesis** â€” Optional Groq call to generate court-admissible narrative

### Two-Phase Execution

**Initial pass:** Classical ML tools (ELA, optical flow, EXIF extraction, etc.)

**Deep pass (user-triggered):**
- Agent 1 (Image Forensics) â†’ Gemini vision multimodal analysis runs first
- Agent 1 injects its Gemini context into Agents 3 and 5 via class-level `inject_agent1_context()`
- Agents 2, 3, 4, 5 run concurrently (Agent 3 and 5 benefit from injected context)

---

## Security Architecture

| Layer | Mechanism |
|-------|-----------|
| Transport | TLS via Caddy + Let's Encrypt (production) |
| Authentication | JWT HS256, 60-min expiry, Redis blacklist |
| Passwords | bcrypt (work factor â‰¥ 12), 72-byte truncation |
| Authorization | Role-based (admin / investigator) per route |
| Rate limiting | Redis INCR/EXPIRE; in-process dict fallback |
| File safety | MIME + extension allowlist, 50 MB limit, SHA-256 hash lock |
| Report integrity | ECDSA P-256 + SHA-256, deterministic key derivation from SIGNING_KEY |
| Container | `read_only: true`; writable paths via named volumes only |
| CORS | Explicit origin allowlist (no wildcard) |

---

## Communication Patterns

- **REST** â€” Synchronous commands: upload, resume, fetch report, HITL decision
- **WebSocket** â€” Unidirectional backendâ†’frontend: agent cognitive traces, phase transitions
  - Protocol: client sends `{"type":"AUTH","token":"..."}` â†’ server sends `CONNECTED`
  - Then: server pushes `AGENT_UPDATE`, `AGENT_COMPLETE`, `PIPELINE_PAUSED`, `PIPELINE_COMPLETE`
  - Subprotocol: `forensic-v1`

---

## ML Subprocess Architecture

Heavy ML inference runs in isolated subprocesses (`apps/api/tools/ml_tools/`) via `asyncio.create_subprocess_exec`. This prevents the Python GIL and long-running CPU operations from blocking the async event loop and dropping WebSocket connections.

| Script | Tool | Agent |
|--------|------|-------|
| `ela_anomaly_classifier.py` | IsolationForest ELA | Agent 1 |
| `noise_fingerprint.py` | PRNU camera noise | Agent 1 |
| `copy_move_detector.py` | SIFT copy-move detection | Agent 1 |
| `audio_splice_detector.py` | Spectral splice detection | Agent 2 |
| `deepfake_frequency.py` | DCT frequency analysis | Agent 2, 4 |
| `anomaly_classifier.py` | IsolationForest scene | Agent 3 |
| `lighting_analyzer.py` | Shadow/highlight consistency | Agent 3 |
| `rolling_shutter_validator.py` | Temporal consistency | Agent 4 |
| `metadata_anomaly_scorer.py` | EXIF entropy scoring | Agent 5 |
| `splicing_detector.py` | SRM noise residual | Agent 1, 3 |

---

## Why Sequential Agent Execution

Parallelising all 5 agents simultaneously on typical analyst hardware causes:
- OOM crashes from concurrent YOLO + Wav2Vec2 + librosa loads (~8â€“15 GB RAM peak)
- Disjointed WebSocket streams (all 5 agents update simultaneously â€” unreadable)
- Unstable heartbeat timing

Sequential execution trades total wall-clock time for predictable memory usage, linear readable output, and stable streaming.

---

---

## Hardware Requirements

The Forensic Council runs heavy ML models (YOLO, CLIP, Wav2Vec2, EfficientNet) in parallel during the Deep Analysis phase.

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **CPU** | 4 Cores (x86_64) | 8+ Cores |
| **RAM** | 12 GB | 32 GB |
| **GPU** | 4 GB VRAM (CUDA) | 8+ GB VRAM |
| **Storage** | 20 GB (SSD) | 100 GB (NVMe) |

> [!WARNING]
> **RAM Spikes**: Peak memory usage during Deep Analysis can hit **15 GB**. Running on hardware with <12 GB RAM may trigger OOM (Out of Memory) kills, causing investigations to fail silently.

---

## Infrastructure Services

### Evidence Cleanup (`scripts/cleanup_storage.py`)
A background service (invoked by `worker.py`) that purges original evidence files and derivative artifacts 24 hours after their last modification. This ensures compliance with evidence retention policies and prevents disk exhaustion.

### ML Tool Warming (`core/ml_subprocess.py`)
On startup, the API server pre-warms critical ML models. This eliminates the 30-60s "cold start" latency on the first investigation of a session.

---

## Frontend Implementation Details

For extremely detailed breakdowns of the Next.js component hierarchy, props, and custom hooks, refer to the **[Component Guide](COMPONENTS.md)**.

