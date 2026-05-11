# Frontend Flow

## Frontend Root

```text
apps/web
```

## Stack

- Next.js 15
- React 19
- TypeScript
- Tailwind CSS
- TanStack Query
- Framer Motion
- Radix Dialog
- Jest
- Playwright

---

## Main Routes

### Landing page

**File:** `apps/web/src/app/page.tsx`

**URL:** `/`

**Purpose:** Introduces the product and starts evidence upload.

**Important components:**

- `apps/web/src/components/ui/HeroAuthActions.tsx`
- `apps/web/src/components/ui/HowWorksSection.tsx`
- `apps/web/src/components/ui/AgentsSection.tsx`
- `apps/web/src/components/ui/LandingBackground.tsx`
- `apps/web/src/components/ui/GlobalNavbar.tsx`
- `apps/web/src/components/ui/GlobalFooter.tsx`

### Evidence page

**File:** `apps/web/src/app/evidence/page.tsx`

**URL:** `/evidence`

**Purpose:** Runs and displays the forensic investigation after the user selects a file.

**Important components:**

- `apps/web/src/components/evidence/AgentProgressDisplay.tsx`
- `apps/web/src/components/evidence/AgentStatusCard.tsx`
- `apps/web/src/components/evidence/AgentStatusSummary.tsx`
- `apps/web/src/components/evidence/ArbiterCard.tsx`
- `apps/web/src/components/evidence/ArbiterDeliberationOverlay.tsx`
- `apps/web/src/components/evidence/HITLCheckpointModal.tsx`
- `apps/web/src/components/evidence/QuotaMeter.tsx`
- `apps/web/src/components/evidence/ErrorDisplay.tsx`

**Important hooks:**

- `apps/web/src/hooks/useInvestigation.ts`
- `apps/web/src/hooks/useSimulation.ts`

### Result redirect page

**File:** `apps/web/src/app/result/page.tsx`

**URL:** `/result`

**Purpose:** Redirects to the most recent result session if available.

### Result details page

**File:** `apps/web/src/app/result/[sessionId]/page.tsx`

**URL:** `/result/{sessionId}`

**Purpose:** Displays the completed or in-progress forensic report.

**Important components:**

- `apps/web/src/components/result/ResultLayout.tsx`
- `apps/web/src/components/result/ResultHeader.tsx`
- `apps/web/src/components/result/VerdictGauge.tsx`
- `apps/web/src/components/result/ArcGauge.tsx`
- `apps/web/src/components/result/IntelligenceBrief.tsx`
- `apps/web/src/components/result/AgentAnalysisTab.tsx`
- `apps/web/src/components/result/TimelineTab.tsx`
- `apps/web/src/components/result/ActionDock.tsx`
- `apps/web/src/components/result/ReportFooter.tsx`
- `apps/web/src/components/result/HistoryPanel.tsx`
- `apps/web/src/components/result/DeepModelTelemetry.tsx`
- `apps/web/src/components/result/DegradationBanner.tsx`

**Important hook:**

- `apps/web/src/hooks/useResult.ts`

### Session expired page

**File:** `apps/web/src/app/session-expired/page.tsx`

**URL:** `/session-expired`

**Purpose:** Shown when the current forensic session or auth state is no longer valid.

---

## Frontend API Routes

### Demo auth helper

**File:** `apps/web/src/app/api/auth/demo/route.ts`

**Purpose:** Frontend-side route used for demo authentication handoff.

### API proxy

**File:** `apps/web/src/app/api/v1/[...path]/route.ts`

**Purpose:** Proxies normal HTTP API calls to the FastAPI backend in local/development setups.

**Important note:** WebSocket upgrade is not handled by this Next.js proxy route. WebSockets need direct backend/Caddy routing or correct WebSocket base URL configuration.

---

## Main Frontend Workflow

1. User opens `/`.
2. User interacts with `HeroAuthActions`.
3. User selects a file in `UploadModal`.
4. File is stored in `pendingFileStore`.
5. Frontend routes to `/evidence`.
6. `useInvestigation` reads pending file.
7. `useInvestigation` prepares auth/session state.
8. `startInvestigation` calls backend.
9. Backend returns `session_id`.
10. Frontend stores session id.
11. `useSimulation` opens WebSocket.
12. Evidence components render live agent progress.
13. HITL modal appears if backend emits checkpoint.
14. Frontend sends HITL decision if user acts.
15. Backend resumes/finalizes pipeline.
16. Frontend receives report-ready event.
17. Frontend routes to `/result/{sessionId}`.
18. `useResult` fetches report.
19. Result components render final report.

---

## Important Frontend State

### Pending file handoff

**File:** `apps/web/src/lib/pendingFileStore.ts`

Used to move a selected File from the landing page to the evidence page without serializing it.

### Investigation/session storage

- `apps/web/src/lib/investigationStorage.ts`
- `apps/web/src/lib/storage.ts`
- `apps/web/src/hooks/useSessionStorage.ts`

Used to preserve current session, result routing, and browser state.

### API auth/token helpers

**File:** `apps/web/src/lib/api/utils.ts`

Used by API client calls.

---

## Main API Client

**File:** `apps/web/src/lib/api/client.ts`

**Responsibilities:**

- login/demo auth
- start investigation
- fetch report
- fetch session
- send HITL decision
- resume session
- fetch quota
- create WebSocket connection
- logout

---

## Live Progress Hook

**File:** `apps/web/src/hooks/useSimulation.ts`

Handles WebSocket message types including:

- CONNECTED
- AGENT_UPDATE
- AGENT_COMPLETE
- HITL_CHECKPOINT
- PIPELINE_PAUSED
- PIPELINE_QUARANTINED
- ARBITER_UPDATE
- REPORT_READY
- PIPELINE_COMPLETE
- ERROR

---

## Evidence Page Components

### AgentProgressDisplay.tsx

Main evidence dashboard during live analysis.

### AgentStatusCard.tsx

Displays one agent's state, findings, status, and confidence.

### AgentStatusSummary.tsx

Displays summary state across agents.

### ArbiterCard.tsx

Displays Arbiter state.

### ArbiterDeliberationOverlay.tsx

Displays overlay while Arbiter is deliberating.

### HITLCheckpointModal.tsx

Displays human-in-the-loop checkpoint options.

### QuotaMeter.tsx

Displays quota/cost status for the current session.

### UploadModal.tsx

Handles file selection.

### UploadSuccessModal.tsx

Displays upload success transition.

---

## Result Page Components

### ResultLayout.tsx

Main result page shell.

### ResultHeader.tsx

Displays verdict, session, hash, and main report metadata.

### VerdictGauge.tsx

Verdict confidence/probability visualization.

### AgentAnalysisTab.tsx

Per-agent findings and details.

### TimelineTab.tsx

Report timeline.

### ActionDock.tsx

Report download/export actions.

### HistoryPanel.tsx

Local report history UI.

### DeepModelTelemetry.tsx

Displays deep model and degradation telemetry.

### DegradationBanner.tsx

Displays degraded-analysis warnings.

---

## Frontend Safety Rules

Do not:

- hardcode final forensic reports
- replace backend result fetch with fake data
- remove WebSocket/HITL handling
- store secrets in frontend code
- skip MIME restrictions only on frontend
- assume frontend validation is enough

---

## Frontend Verification Commands

```bash
cd apps/web
npm run type-check
npm run lint
npm run test
npm run build
```