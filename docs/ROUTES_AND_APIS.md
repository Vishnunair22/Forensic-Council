# Routes and APIs

## Frontend Routes

| URL | File | Purpose |
|---|---|---|
| `/` | `apps/web/src/app/page.tsx` | Landing page and upload entry |
| `/evidence` | `apps/web/src/app/evidence/page.tsx` | Live investigation page |
| `/result` | `apps/web/src/app/result/page.tsx` | Redirect to latest result session |
| `/result/{sessionId}` | `apps/web/src/app/result/[sessionId]/page.tsx` | Result/report page |
| `/session-expired` | `apps/web/src/app/session-expired/page.tsx` | Expired session page |

---

## Frontend API Routes

| URL | File | Purpose |
|---|---|---|
| `/api/auth/demo` | `apps/web/src/app/api/auth/demo/route.ts` | Demo auth helper |
| `/api/v1/[...path]` | `apps/web/src/app/api/v1/[...path]/route.ts` | HTTP proxy to backend |

**Important:** The Next.js API proxy does not handle WebSocket upgrades. WebSocket routing must point to backend/Caddy or use correct WebSocket base URL config.

---

## Backend API Base

Backend API routes are registered under:

`/api/v1`

**Main backend app:** `apps/api/api/main.py`

---

## Auth API

**File:** `apps/api/api/routes/auth.py`

| Method | Path | Purpose |
|---|---|---|
| POST | /api/v1/auth/login | Login |
| GET | /api/v1/auth/me | Current user |
| POST | /api/v1/auth/refresh | Refresh token |
| POST | /api/v1/auth/logout | Logout |

---

## Investigation API

**File:** `apps/api/api/routes/investigation.py`

| Method | Path | Purpose |
|---|---|---|
| POST | /api/v1/investigate | Start evidence investigation |

**Expected request:** multipart/form-data
  - file
  - case_id
  - investigator_id

**Expected response includes:**
  - session_id
  - case_id
  - status
  - message

---

## Session API

**File:** `apps/api/api/routes/sessions.py`

| Method | Path | Purpose |
|---|---|---|
| GET | /api/v1/sessions | List sessions |
| DELETE | /api/v1/sessions/{session_id} | Delete session |
| GET | /api/v1/sessions/{session_id} | Get session |
| GET | /api/v1/sessions/{session_id}/arbiter-status | Get Arbiter status |
| GET | /api/v1/sessions/{session_id}/report | Get report |
| GET | /api/v1/sessions/{session_id}/report/download | Download report |
| GET | /api/v1/sessions/{session_id}/report/pdf | Download PDF report |
| GET | /api/v1/sessions/{session_id}/brief/{agent_id} | Get agent brief |
| GET | /api/v1/sessions/{session_id}/brief | Get session brief |
| GET | /api/v1/sessions/{session_id}/checkpoints | Get HITL checkpoints |
| POST | /api/v1/sessions/{session_id}/resume | Resume session |
| GET | /api/v1/sessions/{session_id}/quota | Get quota/cost state |

---

## HITL API

**File:** `apps/api/api/routes/hitl.py`

| Method | Path | Purpose |
|---|---|---|
| POST | /api/v1/hitl/decision | Submit HITL decision |

---

## Live Progress APIs

### WebSocket

**File:** `apps/api/api/routes/_websocket.py`

**Route:** WS /api/v1/sessions/{session_id}/live

### SSE

**File:** `apps/api/api/routes/sse.py`

**Route:** GET /api/v1/sessions/{session_id}/progress

---

## Metrics API

**File:** `apps/api/api/routes/metrics.py`

| Method | Path | Purpose |
|---|---|---|
| GET | /api/v1/metrics | App metrics |
| GET | /api/v1/metrics/prometheus | Prometheus metrics |
| GET | /api/v1/metrics/public | Public metrics |
| GET | /api/v1/metrics/raw | Raw metrics |
| GET | /api/v1/metrics/pool-status | Pool/process status |

---

## Cases API

**File:** `apps/api/api/routes/cases.py`

**Purpose:** Case-oriented API for creating cases, adding artifacts, analyzing cases, and retrieving case state.

---

## Webhooks API

**File:** `apps/api/api/routes/webhooks.py`

**Purpose:** Webhook registration/list/delete/delivery and investigation-complete webhook dispatch.

---

## Frontend API Client Ownership

**Main client:** `apps/web/src/lib/api/client.ts`

**API helpers:**
- `apps/web/src/lib/api/utils.ts`
- `apps/web/src/lib/api/types.ts`

The frontend should call the backend through this API layer rather than scattering fetch calls throughout components.

---

## Route Ownership Rules

### Frontend owns
- page layout
- upload interaction
- live progress display
- HITL modal display
- result rendering
- download buttons
- local browser state

### Backend owns
- auth validation
- file validation
- evidence hashing
- investigation sessions
- agent execution
- pipeline orchestration
- HITL decision processing
- report generation
- report signing
- report download/PDF

---

## Do not mix ownership

Do not move forensic truth generation into frontend components. The frontend should display backend-generated state.