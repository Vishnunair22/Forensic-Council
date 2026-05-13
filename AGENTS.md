# AGENTS.md

## Project Name

Forensic Council

## Purpose

Forensic Council is a forensic media-analysis platform. It allows a user to upload evidence, runs that evidence through multiple specialist forensic agents, optionally pauses for human-in-the-loop review, and produces a signed forensic report.

The application is structured as a monorepo with a Next.js frontend and a FastAPI backend.

---

## Tech Stack

### Frontend

- Next.js 15 App Router
- React 19
- TypeScript
- Tailwind CSS
- TanStack Query
- Framer Motion
- Radix UI Dialog
- Jest
- Playwright

Frontend root:

```text
apps/web
```

### Backend

- FastAPI
- Python 3.12
- Pydantic v2
- PostgreSQL
- Redis
- Qdrant
- Alembic
- Groq/Gemini LLM integrations
- Optional ML extras including torch, torchvision, torchaudio, ultralytics, transformers, open-clip, speechbrain

Backend root:

```text
apps/api
```

### Infrastructure

- Docker Compose
- Caddy
- Prometheus
- Jaeger
- Redis
- PostgreSQL
- Qdrant

Infra root:

```text
infra
```

---

## Repository Layout

```text
.
├── apps
│   ├── api
│   │   ├── agents
│   │   ├── api
│   │   ├── core
│   │   ├── orchestration
│   │   ├── scripts
│   │   ├── tests
│   │   └── tools
│   └── web
│       ├── src
│       │   ├── app
│       │   ├── components
│       │   ├── hooks
│       │   └── lib
│       └── tests
├── docs
├── infra
└── scripts
```

---

## Main User Flow

1. Landing page
2. -> user selects evidence
3. -> frontend stores pending File in memory
4. -> user is routed to /evidence
5. -> frontend authenticates demo/investigator session if required
6. -> frontend sends POST /api/v1/investigate
7. -> backend validates file and creates investigation session
8. -> backend runs forensic pipeline
9. -> frontend receives live WebSocket updates
10. -> optional HITL checkpoint appears
11. -> backend runs deep analysis after resume/decision
12. -> Council Arbiter finalizes verdict
13. -> signed report is saved
14. -> frontend routes to /result/{sessionId}

---

## Critical Frontend Files

### App routes

- `apps/web/src/app/page.tsx`
- `apps/web/src/app/evidence/page.tsx`
- `apps/web/src/app/result/page.tsx`
- `apps/web/src/app/result/[sessionId]/page.tsx`
- `apps/web/src/app/session-expired/page.tsx`

### Frontend API layer

- `apps/web/src/lib/api/client.ts`
- `apps/web/src/lib/api/utils.ts`
- `apps/web/src/lib/api/types.ts`

### Main frontend hooks

- `apps/web/src/hooks/useInvestigation.ts`
- `apps/web/src/hooks/useSimulation.ts`
- `apps/web/src/hooks/useResult.ts`
- `apps/web/src/hooks/useForensicData.ts`

### Frontend storage helpers

- `apps/web/src/lib/pendingFileStore.ts`
- `apps/web/src/lib/investigationStorage.ts`
- `apps/web/src/lib/storage.ts`

### Main evidence UI

- `apps/web/src/components/evidence/AgentProgressDisplay.tsx`
- `apps/web/src/components/evidence/AgentStatusCard.tsx`
- `apps/web/src/components/evidence/HITLCheckpointModal.tsx`
- `apps/web/src/components/evidence/ArbiterDeliberationOverlay.tsx`
- `apps/web/src/components/evidence/QuotaMeter.tsx`

### Main result UI

- `apps/web/src/components/result/ResultLayout.tsx`
- `apps/web/src/components/result/ResultHeader.tsx`
- `apps/web/src/components/result/VerdictGauge.tsx`
- `apps/web/src/components/result/AgentAnalysisTab.tsx`
- `apps/web/src/components/result/TimelineTab.tsx`
- `apps/web/src/components/result/ActionDock.tsx`

---

## Critical Backend Files

### API app and route registration

- `apps/api/api/main.py`

### API routes

- `apps/api/api/routes/auth.py`
- `apps/api/api/routes/investigation.py`
- `apps/api/api/routes/sessions.py`
- `apps/api/api/routes/hitl.py`
- `apps/api/api/routes/_websocket.py`
- `apps/api/api/routes/sse.py`
- `apps/api/api/routes/cases.py`
- `apps/api/api/routes/metrics.py`
- `apps/api/api/routes/webhooks.py`

### Pipeline orchestration

- `apps/api/orchestration/pipeline.py`
- `apps/api/orchestration/pipeline_phases.py`
- `apps/api/orchestration/investigation_runner.py`
- `apps/api/orchestration/investigation_queue.py`
- `apps/api/orchestration/session_manager.py`
- `apps/api/orchestration/signal_bus.py`
- `apps/api/orchestration/worker.py`

### Agents

- `apps/api/agents/agent1_image.py`
- `apps/api/agents/agent2_audio.py`
- `apps/api/agents/agent3_object.py`
- `apps/api/agents/agent4_video.py`
- `apps/api/agents/agent5_metadata.py`
- `apps/api/agents/arbiter.py`
- `apps/api/agents/arbiter_verdict.py`
- `apps/api/agents/arbiter_narrative.py`

### Core backend systems

- `apps/api/core/config.py`
- `apps/api/core/auth.py`
- `apps/api/core/evidence.py`
- `apps/api/core/forensics.py`
- `apps/api/core/custody_chain.py`
- `apps/api/core/custody_logger.py`
- `apps/api/core/signing.py`
- `apps/api/core/pdf_report_exporter.py`
- `apps/api/core/quota_meter.py`
- `apps/api/core/rate_limiting.py`
- `apps/api/core/llm_client.py`
- `apps/api/core/gemini_client.py`
- `apps/api/core/tool_registry.py`
- `apps/api/core/task_router.py`

---

## Backend Route Map

### Auth

- POST /api/v1/auth/login
- GET  /api/v1/auth/me
- POST /api/v1/auth/refresh
- POST /api/v1/auth/logout

### Investigation

- POST /api/v1/investigate

### Sessions

- GET    /api/v1/sessions
- DELETE /api/v1/sessions/{session_id}
- GET    /api/v1/sessions/{session_id}
- GET    /api/v1/sessions/{session_id}/arbiter-status
- GET    /api/v1/sessions/{session_id}/report
- GET    /api/v1/sessions/{session_id}/report/download
- GET    /api/v1/sessions/{session_id}/report/pdf
- GET    /api/v1/sessions/{session_id}/brief/{agent_id}
- GET    /api/v1/sessions/{session_id}/brief
- GET    /api/v1/sessions/{session_id}/checkpoints
- POST   /api/v1/sessions/{session_id}/resume
- GET    /api/v1/sessions/{session_id}/quota

### HITL

- POST /api/v1/hitl/decision

### Live progress

- WS  /api/v1/sessions/{session_id}/live
- GET /api/v1/sessions/{session_id}/progress

### Metrics

- GET /api/v1/metrics
- GET /api/v1/metrics/prometheus
- GET /api/v1/metrics/public
- GET /api/v1/metrics/raw
- GET /api/v1/metrics/pool-status

---

## Specialist Agents

The application uses five specialist forensic agents and one Council Arbiter.

- Agent 1: Image Forensics
- Agent 2: Audio Forensics
- Agent 3: Object Detection / Scene Context
- Agent 4: Video Forensics
- Agent 5: Metadata / Provenance
- Agent 6: Council Arbiter

### Agent files

- `apps/api/agents/agent1_image.py`
- `apps/api/agents/agent2_audio.py`
- `apps/api/agents/agent3_object.py`
- `apps/api/agents/agent4_video.py`
- `apps/api/agents/agent5_metadata.py`
- `apps/api/agents/arbiter.py`

---

## Rules for AI Tools and Contributors

### Do not bypass these systems

Do not bypass or remove:

- authentication
- MIME validation
- file size validation
- evidence hashing
- chain-of-custody logging
- report signing
- quota checks
- rate limiting
- HITL checkpoint logic
- WebSocket/SSE progress logic
- Arbiter finalization

### Do not fake forensic results

Do not introduce frontend-only fake reports or hardcoded verdicts. The result page should display backend-generated report data.

### Do not weaken security for convenience

Avoid:

- disabling JWT checks in production
- allowing arbitrary file types
- allowing unsafe paths
- skipping evidence hashing
- skipping custody entries
- logging secrets
- leaking API keys to frontend
- using wildcard CORS in production

### Preserve frontend flow

The frontend upload flow depends on:

- pendingFileStore
- /evidence route
- useInvestigation
- startInvestigation
- connectWebSocket
- /result/{sessionId}

Be careful when changing any of these files:

- `apps/web/src/lib/pendingFileStore.ts`
- `apps/web/src/hooks/useInvestigation.ts`
- `apps/web/src/hooks/useSimulation.ts`
- `apps/web/src/lib/api/client.ts`
- `apps/web/src/app/evidence/page.tsx`

### Preserve backend flow

The backend investigation flow depends on:

- POST /api/v1/investigate
- session creation
- pipeline launch
- agent execution
- HITL pause/resume
- Arbiter finalization
- report persistence
- report fetch

Be careful when changing:

- `apps/api/api/routes/investigation.py`
- `apps/api/orchestration/pipeline.py`
- `apps/api/orchestration/pipeline_phases.py`
- `apps/api/orchestration/investigation_runner.py`
- `apps/api/orchestration/session_manager.py`
- `apps/api/api/routes/sessions.py`

---

## Local Development Commands

### Frontend

```bash
cd apps/web
npm ci
npm run dev
npm run type-check
npm run lint
npm run test
npm run build
```

### Backend

```bash
cd apps/api
uv sync --extra dev --extra security --extra observability
uv run python scripts/init_db.py
uv run python scripts/run_api.py
uv run pytest
```

### Backend with ML extras

```bash
cd apps/api
uv sync --extra dev --extra security --extra observability --extra ml
uv run python scripts/model_pre_download.py --strict
uv run python scripts/validate_ml_tools.py
```

### Docker development

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env up --build
```

### Docker production-style

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file .env up --build
```

---

## Important Documentation Files

- README.md
- docs/ARCHITECTURE.md
- docs/WORKFLOW_TRACE.md
- docs/API_CONTRACT.md
- docs/OPERATIONAL_RUNBOOK.md
- docs/MODEL_REGISTRY.md
- docs/SECURITY.md
- docs/TESTING.md
- docs/PRODUCTION_CHECKLIST.md
- docs/MODEL_LICENSING.md
- PROJECT_HANDOFF.md

---

## Handoff Rule

After every meaningful local change, update:

**PROJECT_HANDOFF.md**

This file should describe:

- what changed
- which files were touched
- what works
- what is still broken
- which tests were run
- which commands failed
- what the next action is

AI tools should read AGENTS.md first and PROJECT_HANDOFF.md second before making or suggesting changes.