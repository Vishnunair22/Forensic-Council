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
| `/session-expired` | Expired-session recovery |
| `/api/v1/[...path]` | Server-side proxy to the FastAPI backend |
| `/api/auth/demo` | Server-side demo login helper |

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

## Environment

| Variable | Required | Description |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | No | Browser-visible backend URL. Empty means same-origin proxy. |
| `INTERNAL_API_URL` | No | Backend URL for Next.js server-side routes. Docker uses `http://backend:8000`. |
| `DEMO_PASSWORD` | No | Server-side demo login password for `/api/auth/demo`. |

Do not use `NEXT_PUBLIC_DEMO_PASSWORD`; public variables are baked into client JavaScript.

## Local Development

From `apps/web`:

```bash
npm ci
npm run dev
```

Run the backend separately from `apps/api`, or use the Docker stack from the repository root:

```bash
docker compose -f infra/docker-compose.yml --env-file .env up -d
```

## Checks

```bash
npm run lint
npm run type-check
npm test
npm run build
```

## Docker

The frontend Dockerfile is written for the repository root build context:

```bash
docker build -f apps/web/Dockerfile -t forensic-council-frontend .
```

Compose already uses this context through `infra/docker-compose.yml`.
