# Forensic Council — Frontend

Next.js 15 frontend for the Forensic Council multi-agent forensic evidence analysis system.

**Version:** v1.0.4 | **Framework:** Next.js 15 / React 19 | **Styling:** Tailwind CSS v4

---

## Overview

Real-time investigation UI: upload evidence, watch five AI agents analyze it via live WebSocket streams, review Human-in-the-Loop checkpoints, and read the final cryptographically signed forensic report.

---

## Pages

| Route | Purpose |
|-------|---------|
| `/` | Landing page — file upload, case ID entry, investigation start |
| `/evidence` | Live analysis — WebSocket agent updates, HITL decision panel, deep analysis trigger |
| `/result` | Final signed report — per-agent findings, confidence scores, verdict, cryptographic proof |
| `/session-expired` | Session timeout recovery |

---

## Project Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── page.tsx                    ← Landing + file upload (MicroscopeScanner, EnvelopeCTA)
│   │   ├── evidence/page.tsx           ← Live analysis orchestrator (WebSocket consumer)
│   │   ├── result/page.tsx             ← Signed report display with per-agent analysis
│   │   ├── session-expired/page.tsx    ← Session timeout recovery
│   │   ├── error.tsx                   ← Global Next.js error boundary
│   │   ├── layout.tsx                  ← Root layout (Syne + JetBrains Mono fonts)
│   │   ├── globals.css                 ← Tailwind v4 theme, btn utility classes, cursor:pointer
│   │   └── api/auth/demo/route.ts      ← Next.js server route for demo auto-login
│   ├── components/
│   │   ├── evidence/
│   │   │   ├── FileUploadSection.tsx   ← Drag-and-drop file upload with MIME validation
│   │   │   ├── AgentProgressDisplay.tsx ← Glass agent cards, decision buttons, deep phase
│   │   │   ├── CompletionBanner.tsx    ← Analysis complete banner
│   │   │   ├── ErrorDisplay.tsx        ← Error state display
│   │   │   ├── HITLCheckpointModal.tsx ← Accessible human-review modal
│   │   │   ├── HeaderSection.tsx       ← Keyboard-accessible logo nav header
│   │   │   └── index.ts                ← Re-exports
│   │   └── ui/
│   │       ├── AgentIcon.tsx           ← Per-agent animated Lucide icon
│   │       ├── AgentResponseText.tsx   ← Streaming thinking text display
│   │       ├── GlobalFooter.tsx        ← Academic disclaimer footer (all pages)
│   │       ├── PageTransition.tsx      ← Framer-style fade/slide page transitions
│   │       └── dialog.tsx              ← Radix UI accessible dialog primitive
│   ├── hooks/
│   │   ├── useForensicData.ts          ← Core hook: session history, file validation, mapping
│   │   ├── useSimulation.ts            ← WebSocket consumer: auth, reconnect, resume
│   │   └── useSound.ts                 ← Web Audio API subtle feedback sounds
│   └── lib/
│       ├── api.ts                      ← Backend API client (fetch + WebSocket)
│       ├── schemas.ts                  ← Zod validation schemas
│       ├── constants.ts                ← Agent definitions, MIME allowlist
│       └── utils.ts                    ← cn() Tailwind class merger (clsx + tailwind-merge)
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_API_URL` | Yes | Backend URL reachable from user's browser (e.g. `http://localhost:8000`) |
| `NEXT_PUBLIC_DEMO_PASSWORD` | Yes | Password for auto-login demo investigator account |
| `INTERNAL_API_URL` | No | Backend URL for Next.js server-side requests (e.g. `http://forensic_api:8000` in Docker) |

> `NEXT_PUBLIC_*` variables are baked into the JS bundle at build time. After changing them, you must rebuild: `docker compose build frontend`.

---

## Local Development (without Docker)

```bash
cd frontend

# Install dependencies
npm ci

# Create local env file
cp ../.env.example .env.local
# Edit .env.local: set NEXT_PUBLIC_API_URL=http://localhost:8000

# Start dev server with hot-reload
npm run dev
# Open http://localhost:3000
```

The backend must be running. Start infrastructure only with: `./manage.sh infra` (starts Postgres, Redis, Qdrant), then run the backend natively.

---

## Running Tests

Tests live in `tests/frontend/` at the project root.

```bash
cd frontend

# All tests (CI mode — no watch)
npm test -- --watchAll=false

# Watch mode (development)
npm test

# Specific file
npm test -- tests/frontend/unit/lib/api.test.ts --watchAll=false

# With coverage report
npm run test:coverage

# By pattern
npm test -- --testPathPattern="accessibility" --watchAll=false
```

### Test categories

| Directory | What's tested |
|-----------|--------------| 
| `tests/frontend/unit/lib/` | API client, token management, Zod schemas, `cn()` utility |
| `tests/frontend/unit/hooks/` | `useForensicData`, `mapReportDtoToReport`, file validation |
| `tests/frontend/unit/components/` | `FileUploadSection`, `AgentProgressDisplay` rendering |
| `tests/frontend/accessibility/` | WCAG 2.1 AA: keyboard nav, ARIA labels, focus management |
| `tests/frontend/integration/` | Session data flow, report deduplication, auth lifecycle |
| `tests/frontend/e2e/` | WebSocket full lifecycle, arbiter race fix, deep analysis flow |

---

## Key Behaviors

**File validation** — Client-side before upload: max 50 MB, allowed MIME types match backend allowlist (`image/jpeg`, `image/png`, `image/tiff`, `image/webp`, `image/gif`, `image/bmp`, `video/mp4`, `video/quicktime`, `video/x-msvideo`, `audio/wav`, `audio/x-wav`, `audio/mpeg`, `audio/mp4`, `audio/flac`).

**WebSocket auth** — On WS open, immediately sends `{"type":"AUTH","token":"<jwt>"}`. The `connected` promise resolves on either `CONNECTED` or the first `AGENT_UPDATE` message (race condition tolerance for slow connections).

**Two-phase investigation** — After initial analysis, the pipeline sends `PIPELINE_PAUSED`. The frontend shows Accept / Deep Analysis / New Upload buttons. The chosen action calls `POST /api/v1/sessions/{id}/resume` with `{"deep_analysis": true/false}`.

**Deep analysis phase** — `clearCompletedAgents()` is called on deep analysis start to reset agent cards. Agent cards reappear fresh as each agent completes its deep pass. Stale initial-phase thinking text is cleared.

**HITL checkpoint** — When `HITL_CHECKPOINT` is received, a decision modal appears. The investigator submits one of: `APPROVE`, `REDIRECT`, `OVERRIDE`, `TERMINATE`, `ESCALATE`.

**Arbiter navigation guard** — `resumeInvestigation()` is fully awaited before `router.push('/result')`. The `isNavigating` flag prevents double-submission and disables buttons during navigation.

**Report deduplication** — `mapReportDtoToReport()` deduplicates findings by `finding_type`. Findings tagged `metadata.analysis_phase = "deep"` are always preserved as separate entries from their initial counterparts.

---

## Build

```bash
npm run build    # Production Next.js build (standalone output)
npm run lint     # ESLint (does not run during next build — explicitly separate)
npm run start    # Serve production build locally (after build)
```

The Docker image uses `output: 'standalone'` for minimal production images (~80 MB). Caddy serves as the reverse proxy in the Docker stack.

---

## Accessibility (WCAG 2.1 AA)

All interactive elements are keyboard accessible. Key compliance points:
- Logo nav link: `role="button"`, `tabIndex={0}`, `onKeyDown` Enter/Space
- HITL textarea: associated `<label>` via `htmlFor` / `id`
- Decision buttons: native `disabled` attribute during `isNavigating`
- Error states: text announcements (not color alone)
- Loading states: `aria-busy` and text feedback
