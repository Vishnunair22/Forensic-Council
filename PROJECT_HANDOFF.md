# Project Handoff

## Project

Forensic Council

## Last Updated

YYYY-MM-DD

## Current Branch

```text
unknown
```

## Current Stage

Initial documentation handoff created. No production code changes recorded in this file yet.

## Current Goal

Prepare the project for production-readiness improvements while preserving the existing forensic workflow.

---

## Current App Status

### Overall

| Status | Reason |
| --- | --- |
| unknown | This handoff file has just been created. Local build/test status should be filled in after running commands. |

### Frontend

| Area | Status | Notes |
| --- | --- | --- |
| Landing page | unknown | Main file: apps/web/src/app/page.tsx |
| Upload modal | unknown | Main file: apps/web/src/components/evidence/UploadModal.tsx |
| Evidence page | unknown | Main file: apps/web/src/app/evidence/page.tsx |
| Live progress UI | unknown | Main files: useInvestigation.ts, useSimulation.ts |
| HITL modal | unknown | Main file: apps/web/src/components/evidence/HITLCheckpointModal.tsx |
| Result page | unknown | Main file: apps/web/src/app/result/[sessionId]/page.tsx |
| Report download UI | unknown | Main file: apps/web/src/components/result/ActionDock.tsx |

### Backend

| Area | Status | Notes |
| --- | --- | --- |
| API startup | unknown | Main file: apps/api/api/main.py |
| Auth | unknown | Main file: apps/api/api/routes/auth.py |
| Investigation upload | unknown | Main file: apps/api/api/routes/investigation.py |
| Session API | unknown | Main file: apps/api/api/routes/sessions.py |
| WebSocket progress | unknown | Main file: apps/api/api/routes/_websocket.py |
| HITL decision | unknown | Main file: apps/api/api/routes/hitl.py |
| Pipeline execution | unknown | Main file: apps/api/orchestration/pipeline.py |
| Worker mode | unknown | Main file: apps/api/orchestration/worker.py |
| Report generation | unknown | Main files: arbiter.py, pdf_report_exporter.py, signing.py |

### ML and Agents

| Agent | Status | Main file |
| --- | --- | --- |
| Agent 1 Image Forensics | unknown | apps/api/agents/agent1_image.py |
| Agent 2 Audio Forensics | unknown | apps/api/agents/agent2_audio.py |
| Agent 3 Object/Scene Context | unknown | apps/api/agents/agent3_object.py |
| Agent 4 Video Forensics | unknown | apps/api/agents/agent4_video.py |
| Agent 5 Metadata/Provenance | unknown | apps/api/agents/agent5_metadata.py |
| Agent 6 Council Arbiter | unknown | apps/api/agents/arbiter.py |

---

## Recent Changes

### Change 001

**Date:**

YYYY-MM-DD

**Summary:**

Created project handoff documentation.

**Files touched:**

- AGENTS.md
- PROJECT_HANDOFF.md
- docs/AI_CONTEXT.md
- docs/FRONTEND_FLOW.md
- docs/BACKEND_FLOW.md
- docs/ROUTES_AND_APIS.md
- docs/ML_AGENTS.md
- docs/PRODUCTION_CHECKLIST.md

**Reason:**

Make the project easier for AI tools and contributors to understand without re-auditing the full codebase every time.

**Status:**

documentation-only

---

## Commands Run

Update this section after every local change.

# Example:
```bash
cd apps/web && npm run type-check
cd apps/web && npm run lint
cd apps/web && npm run test
cd apps/web && npm run build

cd apps/api && uv run pytest
cd apps/api && uv run python scripts/validate_ml_tools.py

cd infra && docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

---

## Latest Command Results

| Command | Result | Notes |
| --- | --- | --- |
| cd apps/web && npm run type-check | not run | |
| cd apps/web && npm run lint | not run | |
| cd apps/web && npm run test | not run | |
| cd apps/web && npm run build | not run | |
| cd apps/api && uv run pytest | not run | |
| Docker dev build | not run | |
| Docker production build | not run | |

---

## Known Issues

Use this section to track confirmed problems only.

No confirmed local issues recorded yet.

---

## Open Questions

Use this section for unclear areas that need verification.

1. Confirm current local frontend build status.
2. Confirm current local backend test status.
3. Confirm Docker dev startup status.
4. Confirm Docker production-style startup status.
5. Confirm which ML models should be enabled in production.

---

## Current Environment

Fill this in locally.

- OS:
- Node version:
- Python version:
- Docker version:
- Docker Compose version:
- Package manager:
- Backend package manager:

---

## Environment Files Present

| File | Present locally? | Notes |
| --- | --- | --- |
| .env | unknown | Do not commit secrets |
| .env.local | unknown | Do not commit secrets |
| .env.example | yes | Template only |
| .env.local.example | yes | Template only |

---

## Next Recommended Action

Run frontend and backend verification commands, then update this handoff with exact pass/fail results.

---

## Handoff Instructions for AI Tools

Before suggesting or making any changes:

1. Read AGENTS.md.
2. Read this file.
3. Check the latest "Recent Changes" entry.
4. Check "Known Issues."
5. Check "Latest Command Results."
6. Do not assume tests pass unless this file says they were run and passed.
7. Do not remove security, custody-chain, quota, HITL, or report-signing logic.