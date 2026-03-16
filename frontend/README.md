# Forensic Council — Frontend

Next.js 15 frontend for the Forensic Council multi-agent forensic evidence analysis system.

**Version:** v1.0.3 | **Framework:** Next.js 15 / React 19 | **Styling:** Tailwind v4

---

## Overview

The frontend provides an animated, real-time UI for uploading evidence, watching agents analyze it via live WebSocket streams, reviewing HITL checkpoints, and viewing the final cryptographically signed forensic report.

---

## Pages

| Route | Purpose |
|-------|---------|
| `/` | Landing page — file upload, validation, investigation start |
| `/evidence` | Live analysis view — WebSocket agent updates, HITL decision panel |
| `/result` | Final signed report with agent findings and confidence scores |
| `/session-expired` | Session timeout recovery |

---

## Project Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── page.tsx              ← Landing + file upload
│   │   ├── evidence/page.tsx     ← Live analysis (WebSocket consumer)
│   │   ├── result/page.tsx       ← Signed report display
│   │   ├── session-expired/      ← Session timeout page
│   │   └── api/auth/demo/        ← Next.js route for demo auto-login
│   ├── components/
│   │   ├── evidence/
│   │   │   ├── FileUploadSection.tsx    ← Drag-drop file upload
│   │   │   ├── AgentProgressDisplay.tsx ← Live agent cards + decision buttons
│   │   │   ├── CompletionBanner.tsx     ← Analysis complete banner
│   │   │   ├── ErrorDisplay.tsx         ← Error state display
│   │   │   ├── HITLCheckpointModal.tsx  ← Human review modal
│   │   │   └── HeaderSection.tsx        ← Page header
│   │   └── ui/
│   │       ├── AgentIcon.tsx     ← Per-agent animated icon
│   │       ├── AgentResponseText.tsx ← Streaming text display
│   │       └── dialog.tsx        ← Accessible dialog primitive
│   ├── hooks/
│   │   ├── useForensicData.ts    ← Core data hook: history, session, validation
│   │   ├── useSimulation.ts      ← Demo mode simulation hook
│   │   └── useSound.ts           ← Subtle audio feedback
│   └── lib/
│       ├── api.ts                ← Backend API client (fetch + WebSocket)
│       ├── schemas.ts            ← Zod validation schemas
│       ├── constants.ts          ← Agent definitions, MIME allowlist
│       └── utils.ts              ← cn() Tailwind class merger
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_API_URL` | Yes | Backend URL reachable from user's browser (e.g. `http://localhost:8000`) |
| `NEXT_PUBLIC_DEMO_PASSWORD` | Yes | Password for auto-login demo investigator account |
| `INTERNAL_API_URL` | No | Backend URL for server-side Next.js requests (e.g. `http://backend:8000`) |

---

## Local Development (without Docker)

```bash
cd frontend

# Install dependencies
npm ci

# Create env file
cp ../.env.example .env.local
# Edit .env.local — set NEXT_PUBLIC_API_URL=http://localhost:8000

# Start dev server
npm run dev
# Open http://localhost:3000
```

The backend must be running at `NEXT_PUBLIC_API_URL`. Use `.\manage.ps1 infra` (or `docker compose -f docs/docker/docker-compose.infra.yml up`) to start just Postgres, Redis, and Qdrant, then run the backend natively.

---

## Running Tests

Tests live in `tests/frontend/` at the project root.

```bash
cd frontend

# Run all tests (watch mode)
npm test

# Run once (CI mode)
npm test -- --watchAll=false

# Run specific test file
npm test -- tests/frontend/unit/lib/api.test.ts

# With coverage
npm run test:coverage
```

### Test categories

| Directory | What's tested |
|-----------|--------------|
| `tests/frontend/unit/lib/` | API client, Zod schemas, utility functions |
| `tests/frontend/unit/hooks/` | useForensicData hook, mapReportDtoToReport |
| `tests/frontend/unit/components/` | FileUploadSection, AgentProgressDisplay rendering |
| `tests/frontend/accessibility/` | WCAG 2.1 AA: keyboard nav, ARIA, focus management |
| `tests/frontend/integration/` | Session data flow, deduplication, auth lifecycle |
| `tests/frontend/e2e/` | WebSocket full lifecycle, arbiter race condition fix |

---

## Key Behaviors

**File validation** — Validated client-side before upload: max 50MB, allowed MIME types match backend allowlist (`image/jpeg`, `image/png`, `image/tiff`, `image/webp`, `image/gif`, `image/bmp`, `video/mp4`, `video/quicktime`, `video/x-msvideo`, `audio/wav`, `audio/x-wav`, `audio/mpeg`, `audio/mp4`, `audio/flac`).

**WebSocket auth** — On WS open, immediately sends `{"type":"AUTH","token":"<jwt>"}`. The `connected` promise resolves on either `CONNECTED` or the first `AGENT_UPDATE` message (race condition tolerance).

**HITL checkpoint** — When the pipeline pauses (`PIPELINE_PAUSED` message), a decision modal appears. The user chooses Accept, Deep Analysis, or New Upload. The decision button guard (`isNavigating=true`) prevents double-submission.

**Arbiter navigation fix** — `resumeInvestigation()` is fully awaited before `router.push('/result')`. This prevents the result page from loading before the report is finalized.

**Report deduplication** — Findings with the same `finding_type` and no `analysis_phase` metadata are deduplicated to prevent duplicate cards in the report view. Findings with `metadata.analysis_phase = "deep"` are always preserved separately.

---

## Build

```bash
npm run build    # Production Next.js build (standalone output)
npm run lint     # ESLint (separate from build — ESLint disabled during next build)
npm run start    # Start production server (after build)
```

The Docker build uses `output: standalone` for minimal production images.
