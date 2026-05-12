# Project Handoff

> **Purpose:** This file is the single current-state summary for pasting/uploading to
> web AI tools so they know what changed locally since the last zip/repo snapshot.
>
> **AI Sync Instructions:** Before making or suggesting any changes, a web AI tool should:
> 1. Read `AGENTS.md`
> 2. Read this file
> 3. Check "What Changed Since Last AI/Remote Snapshot"
> 4. Check "Known Issues"
> 5. Check "Commands Run" for verification results
> 6. Do not assume tests pass unless this file shows they passed
> 7. Do not remove security, custody-chain, quota, HITL, or report-signing logic

---

## Last Updated

2026-05-12

## Snapshot Source

| Field | Value |
|-------|-------|
| Local branch | `phase-3-frontend-ui-workflow` (feature branch from `main`) |
| Local commit | `19095e4` (Phase 3.10) |
| Remote synced? | not verified in this session |

## Current Local Goal

Phase 3 frontend UI/workflow fixes — committed to `phase-3-frontend-ui-workflow` branch.

## What Changed Since Last AI/Remote Snapshot

### Phase 2 (completed, on `phase-2-startup-stability`)

15 startup/stability fixes across Phase 2.1–2.15:
- Docker `NEXT_PUBLIC_API_URL` same-origin default
- `_wait_healthy.sh` docker inspect fix
- Worker `start_period: 300s`
- Browser guard for `window.location.href`
- `sessionOnlyStorage` for auth token expiry
- WS reconnect state fix
- `receivedBootstrap` flag + `unreachable` status
- `unreachable` vs `not_found` branching
- `ANALYSIS_STARTUP_GRACE_MS = 30000`
- `/live` liveness endpoint
- `_settings_from_app()` helper for middleware
- `GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS` cap
- `logApiTargetDiagnostics()` dev-only
- 4 Playwright hard-refresh tests
- 7 pytest backend regression tests

### Phase 3 (in progress, on `phase-3-frontend-ui-workflow`)

#### Phase 3.1 — Upload modal PDF copy fix
- `apps/web/src/components/evidence/UploadModal.tsx`: "images, video, audio, PDF" → "images, video, or audio"; removed `pdf: ["application/pdf"]` from extension map; added TIFF/BMP to extension map
- `apps/web/src/lib/constants.ts`: (unchanged — already correct)
- Phase 3.2 also applied in same commit

#### Phase 3.2 — Audio preview moved to UploadSuccessModal
- `UploadModal.tsx`: removed `audioPreviewUrl` state, cleanup effect, preview creation block, and audio render block
- `UploadSuccessModal.tsx`: extended `file.type.startsWith("audio/")` to URL creation condition; added `isAudio` flag; added audio render block before fallback
- Phase 3.3 also applied in same commit

#### Phase 3.3 — Docker direct-frontend route proxy explicit
- `apps/web/src/app/api/v1/[...path]/route.ts`: `RUNNING_IN_DOCKER` → `DISABLE_NEXT_API_PROXY`; `dockerGuard()` → `proxyGuard()`; all 5 HTTP methods updated
- `infra/docker-compose.yml`: added `DISABLE_NEXT_API_PROXY=${DISABLE_NEXT_API_PROXY:-}` to frontend env

#### Phase 3.4 — sessionId wired into ActionDock for PDF export
- `apps/web/src/components/result/ResultLayout.tsx`: added `sessionId={rs.sessionId ?? undefined}` to `ActionDock`
- `apps/web/src/components/result/ActionDock.tsx`: removed dead `document.cookie` token lookup from `handleExport`; fetch now uses `credentials: "include"` only

#### Phase 3.5 — Session-scoped result metadata (Phase 3.6 combined)
- `apps/web/src/hooks/useInvestigation.ts`: writes scoped context `{sid}` alongside global context; thumbnail scoped by session
- `apps/web/src/hooks/useResult.ts`: `readSessionContext()` helper; `loadAgentTimelineForSession()`; all metadata state now mutable; `selectSession` updates all state fields
- `fileName`, `mimeType`, `pipelineStartAt`, `thumbnail`, `agentTimeline`, `isDeepPhase` all update on session change

#### Phase 3.7 — Navbar logo navigation separated from investigation reset
- `apps/web/src/components/ui/GlobalNavbar.tsx`: `handleLogoClick` no longer calls `resetActiveInvestigation`; separate `handleResetClick` added; red-dot indicator replaced with visible "Reset" button (only shown when `hasActiveSession && pathname !== "/"`)

#### Phase 3.8 — Stale REPORT_TABS constants removed
- `apps/web/src/lib/constants.ts`: removed `REPORT_TABS`, `ReportTab`, `TAB_ICONS`; removed unused `FileImage`, `FileText`, `FileAudio`, `FileVideo` imports; `ARBITER_POLL_INTERVAL_MS` and `ARBITER_POLL_MAX_ATTEMPTS` preserved (still used by `useResult` and `useInvestigation`)

#### Phase 3.9 — Live arbiter progress text surfaced on result page
- `apps/web/src/components/result/ResultLayout.tsx`: arbiter body placeholder now uses `rs.arbiterMsg` instead of hardcoded "Arbiter is compiling agent findings..."

#### Phase 3.10 — Route-flow integration tests added
- `apps/web/tests/integration/page_flows.test.tsx`: new "Session-scoped metadata" describe block with 3 tests covering scoped context storage and history fileName per session

## Exact Files Changed

```
Phase 2 (on phase-2-startup-stability):
 apps/api/api/main.py                       — _live, _settings_from_app, GRACEFUL_SHUTDOWN cap
 apps/api/tests/integration/test_api_routes.py  — 3 /live tests
 apps/api/tests/unit/test_config_validation.py  — 2 config exit tests
 apps/api/tests/unit/test_investigation_queue_unit.py — 2 worker heartbeat tests
 apps/web/src/hooks/useSimulation.ts     — sessionStorage auth expiry, reconnect state
 apps/web/src/hooks/useInvestigation.ts — unreachable branching, grace timeout
 apps/web/src/lib/api/client.ts          — window.location.href guard, receivedBootstrap, unreachable
 apps/web/src/lib/api/types.ts           — ArbiterStatusResponse "unreachable"
 apps/web/src/lib/api/utils.ts           — logApiTargetDiagnostics
 apps/web/src/lib/constants.ts           — ANALYSIS_STARTUP_GRACE_MS
 apps/web/src/components/ui/RouteExperience.tsx — logApiTargetDiagnostics call
 apps/web/tests/e2e/browser_journey.spec.ts    — 4 startup stability tests
 infra/docker-compose.yml                — /live healthcheck, GRACEFUL_SHUTDOWN env, YAML indent fix
 scripts/_wait_healthy.sh               — docker inspect for missing/exited containers

Phase 3 (on phase-3-frontend-ui-workflow):
 apps/web/src/app/api/v1/[...path]/route.ts         — DISABLE_NEXT_API_PROXY
 apps/web/src/components/evidence/UploadModal.tsx   — PDF copy fix, audio preview removed, TIFF/BMP added
 apps/web/src/components/evidence/UploadSuccessModal.tsx — audio preview added
 apps/web/src/components/result/ActionDock.tsx      — sessionId wired, cookie token removed
 apps/web/src/components/result/ResultLayout.tsx    — sessionId prop, live arbiter text
 apps/web/src/components/ui/GlobalNavbar.tsx      — logo/nav separation, explicit reset button
 apps/web/src/lib/constants.ts                    — removed REPORT_TABS, TAB_ICONS, unused imports
 apps/web/src/hooks/useResult.ts                  — session-scoped metadata, mutable state, timeline refresh
 apps/web/src/hooks/useInvestigation.ts           — scoped context writes, thumbnail scoped
 apps/web/tests/integration/page_flows.test.tsx    — session-scoped metadata tests
 infra/docker-compose.yml                           — DISABLE_NEXT_API_PROXY env
```

## Important Local Decisions

| Decision | Reason | Related Files | Status |
|----------|--------|---------------|--------|
| Phase 3 committed in 3 batches | 3.1+3.2+3.3, 3.4, then 3.5-3.10 combined | various | resolved |
| `DISABLE_NEXT_API_PROXY` for prod Docker | Explicit vs implicit; dev keeps proxy enabled | route.ts | resolved |
| Audio preview in UploadSuccessModal | Unreachable in UploadModal (parent closes it on selection) | UploadModal.tsx, UploadSuccessModal.tsx | resolved |
| PDF not added to supported types | Phase 3 is frontend-only; backend and agent routing unchanged | constants.ts | resolved |
| sessionId via `credentials: "include"` | httpOnly cookie set by backend; document.cookie cannot read it | ActionDock.tsx | resolved |
| Scoped metadata with global fallback | Backward compat for direct result page loads; scoped for history navigation | useResult.ts, useInvestigation.ts | resolved |
| Navbar logo navigates, reset is explicit | Prevent accidental session wipe when clicking logo mid-analysis | GlobalNavbar.tsx | resolved |
| `fileName` mutable state | Enables history session switching to update header filename | useResult.ts | resolved |
| `ARBITER_POLL_INTERVAL_MS` / `MAX_ATTEMPTS` preserved | Still used by useResult and useInvestigation; not part of Phase 3.8 scope | constants.ts | resolved |

## Commands Run

### Verification Results

| Verify | Result | Time | Notes |
|--------|--------|------|-------|
| Python compileall (api/api, core, orchestration, scripts) | passed | 2026-05-12 | No compile errors |
| Docker compose YAML syntax | passes | 2026-05-12 | Requires env vars for full validation |
| `RUNNING_IN_DOCKER` in route.ts | 0 occurrences | 2026-05-12 | Replaced with `DISABLE_NEXT_API_PROXY` |
| `document.cookie` token in ActionDock | removed | 2026-05-12 | Replaced with `credentials: "include"` |
| `audioPreviewUrl` state in UploadModal | removed | 2026-05-12 | Audio preview now in UploadSuccessModal |
| `pdf` extension in UploadModal EXTENSION_MIME_MAP | removed | 2026-05-12 | TIFF/BMP added instead |
| `REPORT_TABS` / `TAB_ICONS` in constants.ts | removed | 2026-05-12 | FileImage/FileText/FileAudio/FileVideo imports also removed |
| `ARBITER_POLL_INTERVAL_MS` in constants.ts | preserved | 2026-05-12 | Still imported by useResult and useInvestigation |
| Scoped storage keys in useInvestigation.ts | all 5 scoped writes added | 2026-05-12 | forensic_investigation_ctx:{sid}, file_name:{sid}, mime_type:{sid}, pipeline_start:{sid}, thumbnail:{sid} |
| `resetActiveInvestigation` in GlobalNavbar handleLogoClick | removed | 2026-05-12 | Replaced with router.push; explicit handleResetClick added |
| rs.arbiterMsg in ResultLayout arbiter body | added | 2026-05-12 | Replaced hardcoded "Arbiter is compiling..." placeholder |

### Build/Test Status

| Command | Result | Time | Notes |
|---------|--------|------|-------|
| Python compileall backend | passed | 2026-05-12 | All .py files compile cleanly |
| Docker compose config (with env) | passes syntax | 2026-05-12 | Env variable warnings are expected |
| TypeScript type-check frontend | not run in this environment | — | WSL2 not available |
| Jest unit tests | not run in this environment | — | WSL2 not available |
| Playwright tests | not run in this environment | — | WSL2 not available |
| pytest backend tests | not run in this environment | — | WSL2 not available |

## Known Issues

| Issue | Severity | Notes |
|-------|----------|-------|
| Cannot run Docker/npm/pytest in this environment (WSL2 not available) | medium | All verification is static (compileall, compose config, grep) |
| Phase 2.14/2.15 tests not run | — | Test files modified but execution blocked by environment |
| Phase 3.5-3.10 tests not run | — | Test files modified but execution blocked by environment |
| `forensic_is_deep` not scoped by session | Deep phase flag shared across sessions | Could be addressed in future session scoping pass |

## Known Bugs (Non-Doc)

(None currently — all Phase 2 and Phase 3 issues resolved)

## Open Questions

(None)

## Next Best Action for AI

1. Run `npm run type-check && npm run lint` in `apps/web`
2. Run `uv run pytest tests/integration/test_api_routes.py tests/unit/test_config_validation.py tests/unit/test_investigation_queue_unit.py -q` in `apps/api`
3. Run `npm test -- tests/integration/page_flows.test.tsx --runInBand` in `apps/web`
4. Run `npm run test:e2e -- tests/e2e/browser_journey.spec.ts tests/e2e/upload-route-flow.spec.ts` in `apps/web`
5. Run Docker: `docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env up --build -d`
6. Run `./scripts/_wait_healthy.sh dev && ./scripts/_smoke.sh dev`
7. Tag both branches after all tests pass: `phase-2-startup-stability-clean` and `phase-3-frontend-ui-workflow-clean`

## Do Not Break

- authentication (JWT validation, Redis blacklist)
- evidence hashing (SHA-256 on upload)
- chain-of-custody logging (every significant forensic action)
- report signing (ECDSA key derivation)
- HITL checkpoint flow (pause/resume/deep analysis)
- quota and rate limiting
- backend-generated forensic truth (never fake results in frontend)
- same-origin Caddy proxy mode (Docker default)
- WebSocket reconnect logic (Phase 2)
- Worker cold-start heartbeat tolerance (Phase 2)
- PDF as unsupported (Phase 3 — backend not ready for PDF support)
- Scoped metadata backward compat (global fallback still works for direct result loads)

---

## Handoff Update Script

Run `python scripts/update_handoff.py` (or `bash scripts/update_handoff.sh`) to refresh this
file with current git state.