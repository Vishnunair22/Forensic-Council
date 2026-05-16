# API Contract — Forensic Council

**Version:** v1.7.0 | **Base URL:** `http://localhost:8000`

Application REST endpoints are prefixed with `/api/v1`; health/liveness probes
are also exposed at root-level aliases for container checks. Authentication uses
JWT Bearer tokens. Obtain a token via `POST /api/v1/auth/login`.

Source-of-truth routes: `apps/api/api/routes/` — schemas in `apps/api/api/schemas.py`.

---

## Auth Contract

### POST `/api/v1/auth/login`

Authenticate and receive a JWT access token.

**Content-Type:** `application/x-www-form-urlencoded`
**Body:** `username=<user>&password=<password>`

**Response 200:**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user_id": "inv-001",
  "role": "investigator"
}
```

**Errors:** `401` wrong credentials · `429` rate limited (5 failures / 5 min per IP)

### POST `/api/v1/auth/refresh`
Issue a fresh token with extended expiry. **Auth required.** Returns same shape as `/auth/login`.

### GET `/api/v1/auth/me`
Return current user info. **Auth required.**

**Response 200:** `{"user_id": "...", "username": "investigator", "role": "investigator"}`

### POST `/api/v1/auth/logout`
Blacklist the current token in Redis. **Auth required.**

**Response 200:** `{"status": "success", "message": "Successfully logged out"}`

---

## Investigation Start

### POST `/api/v1/investigate`

Upload evidence and start a forensic investigation. **Auth required.**

**Content-Type:** `multipart/form-data`

| Field | Type | Description |
|-------|------|-------------|
| `file` | File | Evidence file (max 50 MB) |
| `case_id` | string | **MUST start with `CASE-`** (server enforces). Full value must match `[A-Za-z0-9_.-]{1,128}`. |
| `investigator_id` | string | Alphanumeric + `-_.`, 1–128 chars. No prefix requirement. |

**Accepted MIME types:** `image/jpeg`, `image/png`, `image/tiff`, `image/webp`, `image/gif`, `image/bmp`, `video/mp4`, `video/quicktime`, `video/x-msvideo`, `audio/wav`, `audio/x-wav`, `audio/mpeg`, `audio/mp4`, `audio/flac`

**Response 200:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "case_id": "CASE-20260101-001",
  "status": "started",
  "message": "Investigation started for evidence.jpg"
}
```

**Duplicate 409:** If a session for the same file+user already exists, returns:
```json
{
  "detail": "Investigation already in progress",
  "session_id": "<existing_session_id>"
}
```
The frontend should catch `DuplicateInvestigationError` and reconnect to the existing session.

**Errors:** `400` invalid file type or size · `413` body too large (>55 MB) · `422` invalid case/investigator ID format · `429` rate limited (10 investigations / 5 min per user) · `503` MIME library unavailable

---

## WebSocket / SSE Live Progress

### WS `/api/v1/sessions/{session_id}/live`

Live WebSocket stream of agent cognitive updates. **Auth required.**

**Subprotocol:** `forensic-v1`

**Authentication sources, in order:** `fc_session`, `sessionid`, or `access_token`
cookie; `?token=` query param; `token.<jwt>` WebSocket subprotocol fallback. The
frontend avoids the subprotocol token path when an auth cookie is present.

**Connection sequence:**
1. Client opens WebSocket with `forensic-v1`
2. Server accepts, validates auth, and verifies session ownership
3. Server responds: `{"type": "CONNECTED", "session_id": "..."}`
4. Server pushes updates until investigation ends

**Message types from server:**

| Type | Description |
|------|-------------|
| `CONNECTED` | Auth accepted, stream open |
| `AGENT_UPDATE` | Agent thinking/progress update |
| `AGENT_COMPLETE` | Agent finished one phase |
| `PIPELINE_PAUSED` | Initial analysis done — awaiting resume |
| `PIPELINE_COMPLETE` | Full investigation complete |
| `HITL_CHECKPOINT` | Human decision required |
| `FINAL_REPORT` | Signed report ready |
| `ERROR` | Fatal error |

**SSE fallback:** `GET /api/v1/sessions/{session_id}/progress` yields the same event types.

**Close codes:** `4001` auth failure · `4003` forbidden · `4004` session not found · `4010` interrupted/non-resumable · `1011` server error · `1013` server busy

---

## Health

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Backend readiness probe |
| GET | `/api/v1/health` | Backend readiness probe under API prefix |
| GET | `/live` | Lightweight liveness probe |
| GET | `/api/v1/live` | Lightweight liveness probe under API prefix |
| GET | `/api/v1/health/ml-tools` | ML tool readiness summary |
| GET | `/api/v1/health/tools` | Tool registry readiness summary |

### GET `/api/v1/sessions/{session_id}/progress`

SSE stream alternative to WebSocket. **Auth required.**

---

## Sessions

### GET `/api/v1/sessions/{session_id}`

Get session metadata. **Auth required.**

Returns `{"session_id": "...", "case_id": "...", "status": "...", "created_at": "..."}`.

**Errors:** `400` invalid session ID format · `404` session not found

### GET `/api/v1/sessions`

List all sessions. **Auth required.** Non-admin users see only their own sessions.

### DELETE `/api/v1/sessions/{session_id}`

Terminate a running session. Cancels active task, aborts pipeline, clears Redis metadata/replay/resume/task-hash/queue entries, closes all WebSocket connections, broadcasts termination event, updates DB status to `interrupted`. **Auth required.**

**Response 200:** `{"status": "terminated", "session_id": "..."}`

### GET `/api/v1/sessions/{session_id}/arbiter-status`

Lightweight poll to track arbiter deliberation after `PIPELINE_COMPLETE`. **Auth required.**

Returns one of:
- `{"status": "running", "message": "..."}`
- `{"status": "paused", "awaiting_decision": true}` — exposed only if a checkpoint is pending
- `{"status": "unreachable"}` — backend is reachable via WS even when REST polling fails; frontend reconnects on `unreachable`
- `{"status": "complete", "report_id": "..."}`
- `{"status": "error", "message": "..."}`
- `{"status": "not_found"}`

---

## Resume / HITL

### POST `/api/v1/sessions/{session_id}/resume`

Resume the pipeline after initial analysis pause. **Auth required.**

**Body:** `{"deep_analysis": true}` or `{"deep_analysis": false}`

**Response 200:**
```json
{
  "status": "resumed",
  "session_id": "...",
  "deep_analysis": true,
  "message": "Deep analysis started"
}
```

Idempotent — if pipeline was already resumed, returns `{"status": "already_resumed", ...}`.

**Errors:** `404` session not found · `400` pipeline not in paused state · `503` idempotency token already processed (fail-closed)

### POST `/api/v1/hitl/decision`

Submit a Human-in-the-Loop decision. **Auth required.**

**Body:**
```json
{
  "session_id": "...",
  "checkpoint_id": "7f3c...",
  "agent_id": "Agent3",
  "decision": "APPROVE",
  "note": "Confirmed — lighting analysis is accurate.",
  "override_finding": null
}
```

**Response 200:** `{"status": "decision_recorded", "checkpoint_id": "..."}`

**Errors:** `404` session/checkpoint not found · `503` idempotency failure (already processed)

### GET `/api/v1/sessions/{session_id}/checkpoints`

List pending HITL checkpoints. **Auth required.** Returns array or `[]` if none pending.

---

## Report

### GET `/api/v1/sessions/{session_id}/report`

Fetch the final signed report. **Auth required.**

**Response 200:** Full `ReportDTO` (schema in `apps/api/api/schemas.py`).

**Response 202:** Investigation still in progress `{"status": "in_progress", "phase": "..."}`

**Errors:** `404` session not found · `500` investigation failed · `503` DB temporarily unavailable

### GET `/api/v1/sessions/{session_id}/report/download`

Download report as a JSON file with `Content-Disposition: attachment` headers. **Auth required.**

Same resolution order as `/report`. Returns `202` if still in progress.

### GET `/api/v1/sessions/{session_id}/report/pdf`

Download report as PDF (falls back to JSON with `X-PDF-Fallback: true` header if WeasyPrint unavailable). **Auth required.**

The PDF fallback behavior returns JSON with `Content-Type: application/json` and `X-PDF-Fallback: true` on PDF export error (Phase 5.13). The JSON still contains full report data.

---

## Other Session Endpoints

### GET `/api/v1/sessions/{session_id}/brief/{agent_id}`

Get the most recent thinking brief for a specific agent. **Auth required.**

### GET `/api/v1/sessions/{session_id}/brief`

Get session brief and metadata. **Auth required.**

### GET `/api/v1/sessions/{session_id}/quota`

Get per-session API usage data. **Auth required.**

```json
{
  "tokens_used": 42000,
  "tokens_limit": 100000,
  "cost_estimate_usd": 0.0525,
  "calls_total": 12,
  "degraded": false
}
```

---

## Metrics

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/metrics` | App metrics |
| GET | `/api/v1/metrics/prometheus` | Prometheus format |
| GET | `/api/v1/metrics/public` | Public summary |
| GET | `/api/v1/metrics/raw` | Raw metrics (requires `METRICS_SCRAPE_TOKEN` bearer) |
| GET | `/api/v1/metrics/pool-status` | Connection pool status |

---

## Cases API

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/cases` | Create a multi-artifact case |
| POST | `/api/v1/cases/{case_id}/artifacts` | Add evidence artifact |
| POST | `/api/v1/cases/{case_id}/analyze` | Start analysis of all pending artifacts |
| GET | `/api/v1/cases/{case_id}` | Get case status and aggregated results |

Usage: create case → add artifacts (repeat) → analyze → poll results.

---

## Webhooks API

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/webhooks` | Register webhook URL |
| GET | `/api/v1/webhooks` | List webhooks for current user |
| DELETE | `/api/v1/webhooks/{webhook_id}` | Delete a webhook |

Delivery: `investigation.complete` event with session_id, verdict, manipulation_probability, optional `X-FC-Signature` HMAC-SHA256 header.

---

## Frontend Route Ownership

| Route | Owns |
|-------|------|
| `/` | Landing, upload entry |
| `/evidence` | Live investigation display |
| `/result` | Latest result redirect |
| `/result/{sessionId}` | Report display |
| `/session-expired` | Expired session recovery |

**Rule:** Backend owns forensic truth. Frontend owns display and local state. Never fake results in frontend.
