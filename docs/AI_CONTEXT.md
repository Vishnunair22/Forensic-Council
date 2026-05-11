# AI Context

## What This Project Is

Forensic Council is a forensic media-analysis platform. It accepts uploaded evidence, runs multiple specialist forensic agents, streams progress to the browser, supports human-in-the-loop checkpoints, and produces a signed forensic report.

The project has three major layers:

```text
Frontend UI
  -> FastAPI backend
  -> forensic pipeline
  -> specialist agents
  -> Arbiter
  -> signed report
```

The app is not a static frontend simulation. The frontend depends on backend-created sessions and backend-generated reports.

---

## Primary Architecture

### Main Runtime Flow

1. User opens landing page.
2. User selects an evidence file.
3. Frontend stores selected file in an in-memory pending file store.
4. Frontend navigates to /evidence.
5. Evidence page starts the investigation.
6. Frontend calls POST /api/v1/investigate.
7. Backend validates and stores the evidence.
8. Backend creates a session.
9. Backend launches forensic pipeline.
10. Frontend opens WebSocket live stream.
11. Backend streams agent progress.
12. HITL checkpoint may pause the pipeline.
13. User decision resumes or alters analysis.
14. Deep analysis runs if needed.
15. Arbiter computes final verdict.
16. Backend stores and signs report.
17. Frontend navigates to /result/{sessionId}.
18. Result page fetches and displays report.

---

## Important Conceptual Systems

### Evidence

Evidence is the uploaded media/file being analyzed.

**Important backend files:**

- `apps/api/core/evidence.py`
- `apps/api/core/forensics.py`
- `apps/api/core/mime_registry.py`
- `apps/api/core/media_kind.py`

### Session

A session represents one investigation run.

**Important backend files:**

- `apps/api/orchestration/session_manager.py`
- `apps/api/api/routes/sessions.py`

**Important frontend files:**

- `apps/web/src/lib/investigationStorage.ts`
- `apps/web/src/hooks/useInvestigation.ts`
- `apps/web/src/hooks/useResult.ts`

### Pipeline

The pipeline coordinates the whole forensic run.

**Important files:**

- `apps/api/orchestration/pipeline.py`
- `apps/api/orchestration/pipeline_phases.py`
- `apps/api/orchestration/investigation_runner.py`

### Agents

Agents perform specialist analysis.

**Important files:**

- `apps/api/agents/agent1_image.py`
- `apps/api/agents/agent2_audio.py`
- `apps/api/agents/agent3_object.py`
- `apps/api/agents/agent4_video.py`
- `apps/api/agents/agent5_metadata.py`

### Arbiter

The Arbiter combines findings and produces the final forensic verdict.

**Important files:**

- `apps/api/agents/arbiter.py`
- `apps/api/agents/arbiter_verdict.py`
- `apps/api/agents/arbiter_narrative.py`

### HITL

Human-in-the-loop checkpoints allow user decisions during analysis.

**Frontend:**

- `apps/web/src/components/evidence/HITLCheckpointModal.tsx`
- `apps/web/src/hooks/useSimulation.ts`

**Backend:**

- `apps/api/api/routes/hitl.py`
- `apps/api/api/routes/sessions.py`
- `apps/api/orchestration/session_manager.py`

### Live Updates

The frontend receives progress over WebSocket and may have SSE fallback support.

**Frontend:**

- `apps/web/src/hooks/useSimulation.ts`
- `apps/web/src/lib/api/client.ts`

**Backend:**

- `apps/api/api/routes/_websocket.py`
- `apps/api/api/routes/sse.py`
- `apps/api/orchestration/signal_bus.py`

---

## Frontend Mental Model

The frontend flow is stateful.

```text
Home page upload
  -> pendingFileStore
  -> evidence page
  -> useInvestigation
  -> useSimulation
  -> result page
  -> useResult
```

**Important:** The file handoff from the landing page to the evidence page is not done through URL params. It uses an in-memory pending file store.

---

## Backend Mental Model

The backend flow is session-based.

```text
investigate route
  -> validate evidence
  -> create session
  -> enqueue or start pipeline
  -> stream updates
  -> pause/resume through HITL if needed
  -> generate report
  -> expose report through session routes
```

---

## What AI Tools Should Avoid

Do not:

- replace backend forensic flow with frontend mocks
- remove security validation
- skip evidence hashing
- skip custody-chain signing
- remove quota checks
- hardcode successful reports
- remove HITL support
- weaken production config checks
- leak API keys to frontend

---

## Related Docs

- AGENTS.md
- PROJECT_HANDOFF.md
- docs/FRONTEND_FLOW.md
- docs/BACKEND_FLOW.md
- docs/ROUTES_AND_APIS.md
- docs/ML_AGENTS.md
- docs/PRODUCTION_CHECKLIST.md