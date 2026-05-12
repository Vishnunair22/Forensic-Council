# Forensic Council Frontend

Next.js 15 / React 19 frontend for the Forensic Council multi-agent forensic evidence analysis system.

**Version:** v1.7.0

## Routes

| Route | Purpose |
| --- | --- |
| `/` | Landing and investigation entry point |
| `/evidence` | Evidence upload and live analysis |
| `/result` | Latest result view |
| `/result/[sessionId]` | Session-specific report view |
| `/session-expired` | Expired session recovery |
| `/api/v1/[...path]` | Server-side proxy to the FastAPI backend |
| `/api/auth/demo` | Server-side demo login helper |

## Setup

```bash
cd apps/web
npm ci
npm run dev
```

On Windows PowerShell, use `npm.cmd` if script execution policy blocks `npm.ps1`:
```powershell
npm.cmd ci
npm.cmd run dev
```

## Test

| Suite | Command |
|-------|---------|
| Jest (unit + component) | `npm test -- --runInBand` |
| Type check | `npm run type-check` |
| Lint | `npm run lint` |
| E2E fast (mocked) | `npm run test:e2e:journey` |
| E2E all | `npm run test:e2e` |
| E2E Chromium only | `npm run test:e2e:chromium` |
| Unit a11y (jest-axe) | `npm run test:a11y:unit` |
| E2E a11y (Playwright axe) | `npm run test:a11y:e2e` |
| Both a11y suites | `npm run test:a11y` |
| Coverage | `npm run test:coverage` |
| Production build | `npm run build` |

See [docs/TESTING.md](docs/TESTING.md) for full test commands and verification scripts.

## State Ownership

| State | Storage |
| --- | --- |
| Pending file | `pendingFileStore` (memory only) |
| Upload modal flag | `fc_open_upload_once` (sessionStorage) |
| Active session metadata | `investigationStorage` (sessionStorage) |
| forensic_history | `forensicHistoryStore` (localStorage) |
| Report/verdict | Backend (Postgres) — never fake in frontend |

See [docs/WORKFLOW_TRACE.md](docs/WORKFLOW_TRACE.md) for the canonical route/state flow.

## Environment

| Variable | Required | Description |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | No | Browser-visible backend URL. Empty means same-origin proxy via Next.js API route. Set to `http://localhost:8000` for host-only dev without Caddy. |
| `INTERNAL_API_URL` | No | Backend URL for Next.js server-side routes. Docker uses `http://backend:8000`. |

Do not use `NEXT_PUBLIC_DEMO_PASSWORD`; public variables are baked into client JavaScript.

## Structure

```text
apps/web/
  src/app/          Next.js App Router pages, layouts, and API routes
  src/components/   UI, evidence workflow, and result report components
  src/hooks/        Investigation, result, session storage, and UI hooks
  src/lib/          API client, schemas, storage, formatting, and utilities
  src/types/        Shared TypeScript declarations
  tests/            Jest, accessibility, integration, and Playwright tests
```

## Do Not Break

- Backend owns forensic truth — never fake results in frontend
- Chain-of-custody logging driven by backend events
- HITL checkpoint flow (pause/resume/deep analysis)
- WebSocket reconnect logic
- `pendingFileStore` in memory (not persisted)
- `fc_open_upload_once` consumed after single use
- `forensic_history` preserved across New Upload and Home navigation