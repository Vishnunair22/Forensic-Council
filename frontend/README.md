# Forensic Council — Frontend

Next.js 15 frontend for the Forensic Council multi-agent forensic evidence analysis system.

**Version:** v1.1.1 | **Framework:** Next.js 15 / React 19 | **Styling:** Tailwind CSS v4

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
│   │   ├── page.tsx                       ← Landing + file upload, hero, example report
│   │   ├── evidence/page.tsx              ← Live analysis orchestrator (WebSocket consumer)
│   │   ├── result/page.tsx                ← Signed report display with per-agent findings
│   │   ├── session-expired/page.tsx       ← Session timeout recovery
│   │   ├── test/page.tsx                  ← Three.js version diagnostic
│   │   ├── error.tsx                      ← Global Next.js error boundary
│   │   ├── not-found.tsx                  ← 404 page
│   │   ├── layout.tsx                     ← Root layout (Syne + JetBrains Mono, DevErrorProvider)
│   │   ├── globals.css                    ← Tailwind v4 theme, glass panels, button utilities
│   │   └── api/auth/demo/route.ts         ← Next.js server route for demo auto-login
│   ├── components/
│   │   ├── evidence/
│   │   │   ├── HeaderSection.tsx          ← Keyboard-accessible logo nav header
│   │   │   ├── FileUploadSection.tsx      ← Drag-and-drop file upload with MIME validation
│   │   │   ├── AgentProgressDisplay.tsx   ← 3×2 agent card grid, live thinking, decision buttons
│   │   │   ├── ErrorDisplay.tsx           ← Error state display with retry
│   │   │   ├── HITLCheckpointModal.tsx    ← Accessible human-review decision modal
│   │   │   └── index.ts                   ← Re-exports
│   │   ├── ui/
│   │   │   ├── AgentIcon.tsx              ← Per-agent Lucide icon resolver
│   │   │   ├── AgentResponseText.tsx      ← Expandable streaming text display
│   │   │   ├── GlobalFooter.tsx           ← Academic disclaimer footer
│   │   │   ├── HistoryDrawer.tsx          ← Sidebar session history
│   │   │   ├── PageTransition.tsx         ← Fade/slide page transition wrapper
│   │   │   ├── SurfaceCard.tsx            ← Reusable glass-panel card
│   │   │   ├── dialog.tsx                 ← Radix UI accessible dialog primitive
│   │   │   └── index.ts                   ← Re-exports
│   │   ├── lightswind/
│   │   │   ├── badge.tsx                  ← Status badge with dot/color variants
│   │   │   └── animated-wave.tsx          ← Three.js animated wave background
│   │   └── DevErrorOverlay.tsx            ← Dev-only error boundary overlay
│   ├── hooks/
│   │   ├── useSimulation.ts               ← WebSocket consumer: auth, message queue, resume
│   │   ├── useForensicData.ts             ← Session history, report mapping, sessionStorage
│   │   ├── useSound.ts                    ← Web Audio API subtle feedback sounds
│   │   ├── use-mobile.ts                  ← Mobile viewport detection
│   │   └── use-toast.ts                   ← Toast notification hook
│   ├── lib/
│   │   ├── api.ts                         ← Backend API client (fetch + WebSocket, retry logic)
│   │   ├── constants.ts                   ← Agent definitions, MIME allowlist
│   │   ├── schemas.ts                     ← Zod validation schemas
│   │   ├── utils.ts                       ← cn() Tailwind class merger (clsx + tailwind-merge)
│   │   └── logger.ts                      ← Dev-only structured logger
│   └── types/
│       └── index.ts                       ← AgentResult, Report types
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

**WebSocket auth** — Cookie-based (HttpOnly `access_token`). The `connected` promise resolves on either `CONNECTED` or the first `AGENT_UPDATE` message (race condition tolerance for slow connections). The WS upgrade goes through the same origin as the page (Next.js rewrite proxy), so the browser sends cookies automatically.

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

---

## Error Handling

### Rate Limiting (HTTP 429)
If `POST /api/v1/investigate` returns 429, the UI displays "Too many requests. Please try again in X seconds" with a countdown timer.

### Network Errors
WebSocket disconnections trigger automatic reconnection with exponential backoff (1s, 2s, 4s, max 30s). The UI shows a connection status indicator during reconnection.

### Session Loss
If the session is deleted server-side (TTL expiry or manual cleanup), the frontend redirects to `/session-expired` with options to start a new investigation.

### Upload Failures
File uploads that exceed 50MB are rejected client-side before the request is sent. Server-side validation returns 413 for oversized payloads.

### Agent Failures
If an individual agent fails, its card shows an error state with a retry button. Other agents continue unaffected. The arbiter marks failed agent findings as contested in the final report.
