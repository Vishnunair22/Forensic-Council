# Codebase Structure

**Analysis Date:** 2026-04-16

## Directory Layout

```
Forensic Council/                       # Project root (monorepo)
├── apps/
│   ├── api/                            # FastAPI Python backend
│   │   ├── agents/                     # 5 specialist agents + Arbiter + base class
│   │   ├── api/                        # FastAPI app, routes, schemas
│   │   │   └── routes/                 # Route modules (investigation, hitl, sessions, auth, sse, metrics)
│   │   ├── core/                       # Shared infrastructure and services
│   │   │   ├── forensics/              # Classical forensic algorithms (ELA, SIFT, noise, frequency, splicing)
│   │   │   ├── handlers/               # Tool handler wrappers per modality (image, audio, video, metadata, scene)
│   │   │   └── persistence/            # DB client wrappers (postgres, redis, qdrant, evidence_store, storage)
│   │   ├── orchestration/              # Pipeline, session manager, investigation queue
│   │   ├── reports/                    # Report generation utilities
│   │   ├── scripts/                    # One-time scripts (init_db.py, key generation)
│   │   ├── storage/                    # Local file storage (evidence files, calibration models, keys)
│   │   │   ├── calibration_models/     # Per-agent Platt scaling models (Agent1–5, deep variants)
│   │   │   ├── evidence/               # Ingested evidence files
│   │   │   └── keys/                   # Signing key storage
│   │   ├── tests/                      # Backend tests
│   │   │   ├── integration/            # Integration test suites
│   │   │   ├── security/               # Security-focused tests
│   │   │   └── unit/                   # Unit tests (core/, agents/)
│   │   ├── tools/                      # Domain-specific ML tool implementations
│   │   │   └── ml_tools/               # ML subprocess workers
│   │   ├── config/                     # Configuration directory
│   │   ├── pyproject.toml              # Python project + dependencies (uv)
│   │   ├── worker.py                   # Celery/background worker entry point
│   │   └── __init__.py
│   └── web/                            # Next.js 15 frontend
│       ├── src/
│       │   ├── app/                    # App Router pages
│       │   │   ├── api/
│       │   │   │   ├── auth/demo/      # Demo login API route
│       │   │   │   └── v1/[...path]/   # Catch-all proxy to FastAPI backend
│       │   │   ├── evidence/           # Evidence upload + real-time progress page
│       │   │   ├── result/             # Report result viewer page
│       │   │   └── session-expired/    # Session expired error page
│       │   ├── components/
│       │   │   ├── evidence/           # Evidence flow components (upload, agent cards, HITL modal, timeline)
│       │   │   ├── result/             # Report display components (layout, findings, charts, metrics)
│       │   │   └── ui/                 # Shared UI primitives (navbar, footer, toasts, modals, icons)
│       │   ├── hooks/                  # Custom React hooks
│       │   ├── lib/                    # Utilities, API client, storage abstraction
│       │   └── types/                  # Shared TypeScript type definitions
│       ├── tests/
│       │   ├── accessibility/          # Axe accessibility tests
│       │   ├── e2e/                    # Playwright E2E tests
│       │   ├── integration/            # Frontend integration tests
│       │   └── unit/                   # Unit tests for app/, components/, hooks/, lib/
│       └── public/                     # Static assets
├── docs/                               # Architecture and reference documentation
│   └── adr/                            # Architecture Decision Records
├── infra/                              # Infrastructure config
│   ├── docker-compose.yml              # Primary compose (all services)
│   ├── docker-compose.dev.yml          # Dev overrides
│   ├── docker-compose.prod.yml         # Production overrides
│   ├── docker-compose.infra.yml        # Infrastructure-only (postgres, redis, qdrant)
│   ├── docker-compose.test.yml         # Test environment
│   └── Caddyfile                       # Caddy reverse proxy config
├── tests/                              # Root-level integration/E2E tests
├── .env.example                        # Environment variable template
├── pytest.ini                          # Root pytest configuration
└── package.json                        # Root workspace package.json
```

## Directory Purposes

**`apps/api/agents/`:**
- Purpose: All 5 forensic specialist agents and the Council Arbiter
- Contains: `base_agent.py` (abstract `ForensicAgent`), `agent1_image.py` through `agent5_metadata.py`, `arbiter.py` (`CouncilArbiter` + `ForensicReport`), `tool_handlers.py`
- Key files: `apps/api/agents/base_agent.py`, `apps/api/agents/arbiter.py`

**`apps/api/api/routes/`:**
- Purpose: FastAPI route handlers
- Contains: `investigation.py` (start/status), `hitl.py` (HITL decisions), `sessions.py` (session CRUD), `auth.py` (login/logout/refresh), `sse.py` (SSE stream), `metrics.py` (Prometheus-style metrics), `_session_state.py` (shared WebSocket registry), `_rate_limiting.py` (per-user rate limit helpers)
- Key files: `apps/api/api/routes/investigation.py`, `apps/api/api/routes/_session_state.py`

**`apps/api/core/`:**
- Purpose: All shared backend infrastructure
- Contains: `react_loop.py`, `custody_logger.py`, `working_memory.py`, `episodic_memory.py`, `inter_agent_bus.py`, `signing.py`, `agent_registry.py`, `tool_registry.py`, `gemini_client.py`, `llm_client.py`, `inference_client.py`, `ml_subprocess.py`, `calibration.py`, `scoring.py`, `synthesis.py`, `grounding.py`, `cross_modal_fusion.py`, `severity.py`, `auth.py`, `config.py`, `observability.py`, `structured_logging.py`, `session_persistence.py`, `circuit_breaker.py`, `retry.py`
- Key files: `apps/api/core/react_loop.py`, `apps/api/core/custody_logger.py`, `apps/api/core/agent_registry.py`

**`apps/api/core/forensics/`:**
- Purpose: Classical forensic analysis algorithms (pure Python/NumPy/OpenCV)
- Contains: `ela.py` (Error Level Analysis), `frequency.py` (FFT frequency bands), `noise.py` (noise consistency), `sift.py` (SIFT keypoint matching), `splicing.py`
- Key files: `apps/api/core/forensics/ela.py`

**`apps/api/core/handlers/`:**
- Purpose: Modality-specific tool handler wrappers; register tools into `ToolRegistry`
- Contains: `base.py`, `image.py`, `audio.py`, `video.py`, `metadata.py`, `scene.py`
- Key files: `apps/api/core/handlers/image.py`

**`apps/api/core/persistence/`:**
- Purpose: Async database client wrappers (singleton pattern)
- Contains: `postgres_client.py`, `redis_client.py`, `qdrant_client.py`, `evidence_store.py`, `storage.py` (local file storage backend)
- Key files: `apps/api/core/persistence/evidence_store.py`, `apps/api/core/persistence/postgres_client.py`

**`apps/api/orchestration/`:**
- Purpose: End-to-end pipeline coordination
- Contains: `pipeline.py` (`ForensicCouncilPipeline`, `AgentFactory`, `SignalBus`, `AgentLoopResult`), `session_manager.py` (`SessionManager`, `SessionStatus`), `investigation_queue.py` (Redis-backed task queue)
- Key files: `apps/api/orchestration/pipeline.py`

**`apps/api/tools/`:**
- Purpose: ML model execution — wraps heavyweight libraries (PyTorch, YOLO, CLIP, EasyOCR, MediaInfo)
- Contains: `image_tools.py`, `audio_tools.py`, `video_tools.py`, `metadata_tools.py`, `ocr_tools.py`, `mediainfo_tools.py`, `clip_utils.py`, `model_cache.py`
- Key files: `apps/api/tools/image_tools.py`

**`apps/web/src/app/`:**
- Purpose: Next.js 15 App Router page tree
- Contains: `layout.tsx` (root layout, fonts, global providers), `page.tsx` (landing/hero), `evidence/page.tsx` (investigation UI), `result/page.tsx` (report viewer), `session-expired/page.tsx`, `api/v1/[...path]/route.ts` (backend proxy), `api/auth/demo/route.ts` (demo login)
- Key files: `apps/web/src/app/layout.tsx`, `apps/web/src/app/evidence/page.tsx`, `apps/web/src/app/api/v1/[...path]/route.ts`

**`apps/web/src/components/evidence/`:**
- Purpose: Components for the evidence upload and investigation progress UI
- Contains: `FileUploadSection.tsx`, `AgentProgressDisplay.tsx`, `AgentStatusCard.tsx`, `HITLCheckpointModal.tsx`, `ForensicTimeline.tsx`, `UploadModal.tsx`, `UploadSuccessModal.tsx`, `ErrorDisplay.tsx`, `index.ts`
- Key files: `apps/web/src/components/evidence/HITLCheckpointModal.tsx`, `apps/web/src/components/evidence/AgentProgressDisplay.tsx`

**`apps/web/src/components/result/`:**
- Purpose: Components for the final forensic report viewer
- Contains: `ResultLayout.tsx`, `ResultHeader.tsx`, `ResultStateView.tsx`, `AgentAnalysisTab.tsx`, `AgentFindingSubComponents.tsx`, `MetricsPanel.tsx`, `TribunalMatrix.tsx`, `TimelineTab.tsx`, `IntelligenceBrief.tsx`, `DeepModelTelemetry.tsx`, `DegradationBanner.tsx`, `ArcGauge.tsx`, `HistoryPanel.tsx`, `EvidenceThumbnail.tsx`, `ReportFooter.tsx`, `ActionDock.tsx`
- Key files: `apps/web/src/components/result/ResultLayout.tsx`

**`apps/web/src/hooks/`:**
- Purpose: Custom React hooks encapsulating business logic
- Contains: `useInvestigation.ts` (primary investigation state machine), `useResult.ts`, `useForensicData.ts`, `useSimulation.ts`, `useSound.ts`, `useForensicSfx.ts`, `useSessionStorage.ts`, `useReducedMotion.ts`, `use-toast.tsx`, `use-mobile.tsx`
- Key files: `apps/web/src/hooks/useInvestigation.ts`

**`apps/web/src/lib/`:**
- Purpose: Pure utilities and API communication
- Contains: `api.ts` (all backend API calls, WebSocket management), `storage.ts` (`localStorage`/`sessionStorage` abstraction), `schemas.ts` (Zod schema for report DTO), `constants.ts`, `backendTargets.ts` (multi-backend URL routing), `verdict.ts`, `utils.ts`, `fmtTool.ts`, `tool-icons.ts`, `design-tokens.ts`, `logger.ts`, `pendingFileStore.ts`, `types.ts`
- Key files: `apps/web/src/lib/api.ts`, `apps/web/src/lib/storage.ts`

## Key File Locations

**Entry Points:**
- `apps/api/api/main.py`: FastAPI app creation, lifespan, all middleware
- `apps/web/src/app/layout.tsx`: Next.js root layout
- `apps/web/src/app/page.tsx`: Landing page
- `infra/docker-compose.yml`: Full-stack Docker entry point

**Configuration:**
- `apps/api/core/config.py`: Pydantic `Settings` (reads from env vars); `get_settings()` singleton
- `apps/web/next.config.ts`: Next.js config (proxy rewrites, build settings)
- `infra/Caddyfile`: Reverse proxy routing rules

**Core Logic:**
- `apps/api/orchestration/pipeline.py`: End-to-end investigation pipeline
- `apps/api/agents/base_agent.py`: ForensicAgent abstract base
- `apps/api/agents/arbiter.py`: CouncilArbiter deliberation and report signing
- `apps/api/core/react_loop.py`: ReAct THOUGHT→ACTION→OBSERVATION engine
- `apps/api/core/custody_logger.py`: Chain-of-custody tamper-evident logging
- `apps/api/core/agent_registry.py`: Agent ID → class singleton registry
- `apps/api/api/routes/investigation.py`: `/api/v1/investigate` route handler
- `apps/web/src/hooks/useInvestigation.ts`: Frontend investigation state machine

**Testing:**
- `apps/api/tests/unit/`: Agent and core unit tests
- `apps/api/tests/integration/`: Pipeline integration tests
- `apps/api/tests/security/`: Auth and security tests
- `apps/web/tests/unit/`: Component and hook unit tests
- `apps/web/tests/e2e/`: Playwright E2E tests
- `pytest.ini`: Root pytest config (applies to `apps/api/`)

## Naming Conventions

**Files (Backend Python):**
- Agent modules: `agent{N}_{modality}.py` (e.g., `agent1_image.py`, `agent3_object.py`)
- Core modules: `snake_case.py` noun-first (e.g., `custody_logger.py`, `working_memory.py`)
- Route modules: `snake_case.py` (e.g., `investigation.py`, `_session_state.py`)
- Private/extracted helpers: prefixed with `_` (e.g., `_rate_limiting.py`, `_session_state.py`)

**Files (Frontend TypeScript):**
- Pages: `page.tsx` (Next.js convention)
- Components: `PascalCase.tsx` (e.g., `HITLCheckpointModal.tsx`, `AgentProgressDisplay.tsx`)
- Hooks: `use{PascalCase}.ts` (e.g., `useInvestigation.ts`, `useForensicData.ts`)
- Utilities: `camelCase.ts` (e.g., `api.ts`, `storage.ts`, `verdicts.ts`)

**Directories:**
- Backend: lowercase singular (e.g., `agents/`, `core/`, `tools/`)
- Frontend: camelCase components groupings (e.g., `evidence/`, `result/`, `ui/`)

## Where to Add New Code

**New Forensic Agent:**
- Implementation: `apps/api/agents/agent{N}_{modality}.py` (extend `ForensicAgent`)
- Register in: `apps/api/core/agent_registry.py` → `_register_core_agents()`
- Tests: `apps/api/tests/unit/` and `apps/api/tests/integration/`

**New API Endpoint:**
- Implementation: `apps/api/api/routes/{feature}.py`
- Register in: `apps/api/api/main.py` → `app.include_router(...)`
- Schema: `apps/api/api/schemas.py`

**New Forensic Algorithm (classical):**
- Implementation: `apps/api/core/forensics/{algorithm}.py`
- Wire up: `apps/api/core/handlers/{modality}.py`

**New ML Tool:**
- Implementation: `apps/api/tools/{modality}_tools.py`
- Register as tool: `apps/api/core/handlers/{modality}.py` → `ToolRegistry.register()`

**New Frontend Page:**
- Implementation: `apps/web/src/app/{feature}/page.tsx`
- Use `"use client"` directive if the page needs browser APIs or React hooks

**New Frontend Component:**
- Shared UI primitive: `apps/web/src/components/ui/{ComponentName}.tsx`
- Evidence-flow specific: `apps/web/src/components/evidence/{ComponentName}.tsx`
- Result-specific: `apps/web/src/components/result/{ComponentName}.tsx`
- Export via `index.ts` barrel in the same directory

**New Custom Hook:**
- Location: `apps/web/src/hooks/use{FeatureName}.ts`
- Add `"use client"` if using browser APIs

**Utilities:**
- Shared frontend helpers: `apps/web/src/lib/{feature}.ts`
- Shared backend helpers: `apps/api/core/{feature}.py`

## Special Directories

**`apps/api/storage/`:**
- Purpose: Runtime file storage (evidence files, calibration model `.pkl` files, signing keys)
- Generated: Yes (at runtime by the API)
- Committed: No (`.gitignore` excludes evidence files; calibration models may be committed as initial state)

**`apps/api/cache/`:**
- Purpose: ML model weight caches (HuggingFace, Torch, YOLO, EasyOCR, Numba, Ultralytics)
- Generated: Yes (downloaded at first run or during Docker build)
- Committed: No

**`apps/api/.venv/`:**
- Purpose: Python virtual environment managed by `uv`
- Generated: Yes
- Committed: No

**`apps/web/.next/`:**
- Purpose: Next.js build cache and compiled output
- Generated: Yes
- Committed: No

**`apps/web/coverage/`:**
- Purpose: Jest test coverage reports
- Generated: Yes
- Committed: No

**`docs/adr/`:**
- Purpose: Architecture Decision Records
- Generated: No
- Committed: Yes

---

*Structure analysis: 2026-04-16*
