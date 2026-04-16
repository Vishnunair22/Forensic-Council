# Architecture

**Analysis Date:** 2026-04-16

## Pattern Overview

**Overall:** Multi-agent forensic pipeline with event-driven coordination

**Key Characteristics:**
- Five specialized forensic agents run concurrently in a two-phase pipeline (Initial → Deep)
- A central `CouncilArbiter` deliberates findings, resolves contradictions via challenge loops and tribunal escalation, then signs the final report with ECDSA P-256
- All agent actions are logged to an immutable chain-of-custody ledger in PostgreSQL (signed, hash-linked entries)
- Human-in-the-Loop (HITL) checkpoints can pause any agent's ReAct loop for human review
- Real-time progress is streamed to the browser over WebSocket (`/api/v1/sessions/{id}/live`) and SSE (`/api/v1/sessions/{id}/sse`)

## Layers

**API Layer:**
- Purpose: HTTP/WebSocket ingress, auth, rate limiting, CSRF, CORS, middleware stack
- Location: `apps/api/api/`
- Contains: `main.py` (FastAPI app + lifespan), `routes/` (investigation, hitl, sessions, auth, sse, metrics), `schemas.py`
- Depends on: `core/`, `orchestration/`
- Used by: Browser frontend, external API consumers

**Orchestration Layer:**
- Purpose: Pipeline coordination, session lifecycle, investigation queueing
- Location: `apps/api/orchestration/`
- Contains: `pipeline.py` (`ForensicCouncilPipeline`, `AgentFactory`, `SignalBus`), `session_manager.py`, `investigation_queue.py`
- Depends on: `agents/`, `core/`
- Used by: `api/routes/investigation.py`

**Agent Layer:**
- Purpose: Specialist forensic analysis — each agent runs a two-phase ReAct loop
- Location: `apps/api/agents/`
- Contains: `base_agent.py` (`ForensicAgent` ABC), `agent1_image.py`, `agent2_audio.py`, `agent3_object.py`, `agent4_video.py`, `agent5_metadata.py`, `arbiter.py` (`CouncilArbiter`), `tool_handlers.py`
- Depends on: `core/`, `tools/`
- Used by: `orchestration/pipeline.py`

**Core Infrastructure Layer:**
- Purpose: Shared services — memory, logging, signing, ML, config
- Location: `apps/api/core/`
- Contains: ReAct engine (`react_loop.py`), persistence clients (`persistence/`), custody logger (`custody_logger.py`), episodic memory (`episodic_memory.py`), working memory (`working_memory.py`), inter-agent bus (`inter_agent_bus.py`), signing (`signing.py`), Gemini client (`gemini_client.py`), LLM client (`llm_client.py`), tool registry (`tool_registry.py`), calibration (`calibration.py`, `scoring.py`), handlers (`handlers/`), forensic algorithms (`forensics/`)
- Depends on: External services (Redis, PostgreSQL, Qdrant, Groq, Gemini)
- Used by: All layers above

**Tools Layer:**
- Purpose: Domain-specific ML tool implementations (image, audio, video, metadata, OCR)
- Location: `apps/api/tools/`
- Contains: `image_tools.py`, `audio_tools.py`, `video_tools.py`, `metadata_tools.py`, `ocr_tools.py`, `mediainfo_tools.py`, `clip_utils.py`, `ml_tools/`, `model_cache.py`
- Depends on: External ML libraries (PyTorch, YOLO, CLIP, etc.)
- Used by: `core/handlers/`

**Frontend Layer:**
- Purpose: Next.js 15 App Router SPA — evidence upload, real-time progress, report rendering
- Location: `apps/web/src/`
- Contains: `app/` pages, `components/`, `hooks/`, `lib/`
- Depends on: Backend API via relative-URL proxy rewrite (`apps/web/src/app/api/v1/[...path]/route.ts`)
- Used by: Browser

## Data Flow

**Forensic Investigation Flow:**

1. Browser POSTs `multipart/form-data` to `/api/v1/investigate` (evidence file + `case_id` + `investigator_id`)
2. `apps/api/api/routes/investigation.py` validates MIME type, file extension, size, dedup hash; stages file to `/tmp`
3. `ForensicCouncilPipeline.run_investigation()` is launched as a background `asyncio.Task`; `session_id` is returned immediately to the browser
4. Pipeline initializes infrastructure (Redis → WorkingMemory, Qdrant → EpisodicMemory, PostgreSQL → CustodyLogger, EvidenceStore)
5. Evidence is ingested into `EvidenceStore`; SHA-256 hash + metadata stored in PostgreSQL and local file storage
6. **Phase 1 (Initial Pass):** All 5 agents run `run_investigation()` concurrently via `asyncio.gather`
   - Each agent executes a task-decomposition-driven ReAct loop (THOUGHT → ACTION → OBSERVATION)
   - Tools are called via `ToolRegistry`; results logged to `CustodyLogger`
   - Agent 1 (Image) signals a `_gemini_signal_callback` when Gemini context is ready
7. **Phase 2 (Deep Pass):** All 5 agents run `run_deep_investigation()` concurrently
   - Agent 1's Gemini vision output is injected into Agent 3 and Agent 5 via `inject_agent1_context()` as soon as it is available (early signal broadcast via `context_event`)
   - Agents 2 and 4 communicate via `InterAgentBus` for audio/video cross-validation
8. `CouncilArbiter.deliberate()` compares findings across agents (cross-modal fusion, finding comparison, contradiction detection)
   - Contradictions trigger **challenge loops**: the challenged agent is re-invoked via `AgentFactory.reinvoke_agent()`
   - Unresolved contradictions escalate to the **Tribunal** (`TribunalCase`)
9. Arbiter computes `manipulation_probability` (reliability-weighted signal averaging), verdict (7-tier: `AUTHENTIC` → `MANIPULATED` → `ABSTAIN`), and per-agent Groq narratives
10. Final `ForensicReport` is ECDSA P-256 signed and persisted to PostgreSQL
11. `PIPELINE_COMPLETE` event is broadcast via WebSocket to all connected browser clients

**WebSocket Real-Time Events:**

1. Browser opens `ws://.../api/v1/sessions/{id}/live` after receiving `session_id`
2. `broadcast_update()` in `apps/api/api/routes/_session_state.py` fans out to all WebSocket connections for that session
3. Event types include: `AGENT_STARTED`, `AGENT_COMPLETE`, `TOOL_CALLED`, `HITL_CHECKPOINT`, `PIPELINE_PAUSED`, `PIPELINE_COMPLETE`, `ARBITER_UPDATE`
4. SSE endpoint at `/api/v1/sessions/{id}/sse` (`apps/api/api/routes/sse.py`) acts as a proxy consumer of the same broadcast channel for clients that cannot use WebSocket

**HITL (Human-in-the-Loop) Flow:**

1. An agent's `ReActLoopEngine` triggers a `HITLCheckpointState` when: iteration ceiling is 50% reached, a contested finding occurs, severity threshold breach, or tribunal escalation
2. `HITL_CHECKPOINT` event is broadcast; pipeline sets `_awaiting_user_decision = True`
3. Browser renders `HITLCheckpointModal` (`apps/web/src/components/evidence/HITLCheckpointModal.tsx`)
4. User submits decision via `POST /api/v1/hitl/decision`
5. `apps/api/api/routes/hitl.py` routes decision to `pipeline.handle_hitl_decision()` → `session_manager.resolve_checkpoint()`
6. Decision is logged to `CustodyLogger` as `EntryType.HITL_DECISION`; agent loop resumes

**State Management (Frontend):**

1. `useInvestigation` hook (`apps/web/src/hooks/useInvestigation.ts`) manages all upload, WebSocket, HITL, and polling state
2. Report data is polled from `GET /api/v1/sessions/{id}/report` once WebSocket signals completion
3. Persistent cross-tab state uses `storage` abstraction (`apps/web/src/lib/storage.ts`) wrapping `localStorage` with `CustomEvent` dispatch
4. Auth tokens use `sessionStorage` via `apps/web/src/lib/api.ts` (intentional — JWT expires with session)

## Key Abstractions

**ForensicAgent (Base Class):**
- Purpose: Abstract base for all 5 specialist agents; provides ReAct loop, self-reflection, HITL, episodic memory integration
- Examples: `apps/api/agents/base_agent.py`, `apps/api/agents/agent1_image.py`
- Pattern: Abstract class with `task_decomposition` and `deep_task_decomposition` properties; `run_investigation()` and `run_deep_investigation()` drive the ReAct engine

**ReActLoopEngine:**
- Purpose: THOUGHT → ACTION → OBSERVATION reasoning loop with HITL checkpoint injection
- Examples: `apps/api/core/react_loop.py`
- Pattern: Iterative async loop; each step is a `ReActStep` Pydantic model stored in `_react_chain`

**CustodyLogger:**
- Purpose: Tamper-evident log of every agent action; entries are ECDSA-signed and hash-linked
- Examples: `apps/api/core/custody_logger.py`
- Pattern: Each `log_entry()` call produces a `ChainEntry` persisted to PostgreSQL `chain_of_custody` table; WAL queue in Redis for retry on DB unavailability

**WorkingMemory:**
- Purpose: Redis-backed per-session, per-agent scratchpad for task queues and iteration state
- Examples: `apps/api/core/working_memory.py`
- Pattern: Keys prefixed `forensic:wm:{session_id}:{agent_id}`; falls back to in-process dict if Redis is down

**EpisodicMemory:**
- Purpose: Qdrant-backed vector store of historical forensic signatures for cross-case pattern detection
- Examples: `apps/api/core/episodic_memory.py`
- Pattern: Each `EpisodicEntry` is embedded (CLIP ViT-B-32, 512-dim) and upserted to `forensic_episodes` collection

**InterAgentBus:**
- Purpose: Structured async communication between agents (collaborative calls and challenge calls)
- Examples: `apps/api/core/inter_agent_bus.py`
- Pattern: DAG-enforced permitted callees per agent (from `AgentRegistry` metadata); circular calls raise `CircularCallError`

**AgentRegistry:**
- Purpose: Singleton registry mapping agent IDs to classes and permitted-callee DAG
- Examples: `apps/api/core/agent_registry.py`
- Pattern: Singleton with `_register_core_agents()` on first instantiation; used by pipeline and inter-agent bus

**ToolRegistry:**
- Purpose: Per-agent registry of callable forensic tools with graceful degradation
- Examples: `apps/api/core/tool_registry.py`
- Pattern: Tools are registered as async callables; unavailable tools return `ToolResult(unavailable=True)` instead of raising

## Entry Points

**Backend API Server:**
- Location: `apps/api/api/main.py`
- Triggers: `uvicorn api.main:app` (dev) or Docker container (prod)
- Responsibilities: FastAPI app creation, middleware stack, router registration, lifespan (DB init, ML warmup, orphan session recovery)

**Frontend Dev Server:**
- Location: `apps/web/src/app/layout.tsx` (root layout), `apps/web/src/app/page.tsx` (landing)
- Triggers: `npm run dev` (Next.js dev server)
- Responsibilities: Global layout (navbar, footer, fonts), App Router page tree

**API Proxy Route (Frontend → Backend):**
- Location: `apps/web/src/app/api/v1/[...path]/route.ts`
- Triggers: Any browser fetch to `/api/v1/...`
- Responsibilities: Forwards all HTTP methods to FastAPI backend; rewrites cross-origin to same-origin to avoid CORS and preserve HttpOnly cookies

**Docker Compose:**
- Location: `infra/docker-compose.yml`
- Triggers: `docker compose -f infra/docker-compose.yml up --build`
- Responsibilities: Orchestrates all services (api, web, postgres, redis, qdrant, caddy)

## Error Handling

**Strategy:** Layered fallback with degradation flags

**Patterns:**
- Infrastructure failures (Redis down, Qdrant down, PostgreSQL down) cause graceful fallback to in-memory or local alternatives; `_degradation_flags` are appended to the final report
- Agent errors produce `AgentLoopResult(error=...)` with an `ERROR` finding rather than crashing the pipeline
- Arbiter `deliberate()` has a 90-second timeout; on timeout it retries with `use_llm=False` (template-based synthesis)
- Orphaned sessions from crashes are detected on startup and marked `interrupted`
- Global exception handler in `apps/api/api/main.py` preserves HTTPException status codes and hides stack traces in production

## Cross-Cutting Concerns

**Logging:** Structured logging via `core/structured_logging.py` (`get_logger(__name__)`); all log calls use keyword args; request-ID injected via `correlation_id_middleware`

**Validation:** Pydantic models throughout the backend; `ReportDTOSchema` (Zod) on the frontend in `apps/web/src/lib/schemas.ts`

**Authentication:** JWT (HttpOnly cookie + Bearer token) via `core/auth.py`; CSRF double-submit cookie pattern in `apps/api/api/main.py`; rate limiting via Redis Lua sliding-window

**Signing:** ECDSA P-256 per-agent key pairs in `core/signing.py`; keys stored in PostgreSQL encrypted with Fernet; deterministic HMAC-SHA256 fallback when DB is unavailable

---

*Architecture analysis: 2026-04-16*
