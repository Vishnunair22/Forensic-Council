# Forensic Council — API Reference

**Version:** v1.0.4 | **Base URL:** `http://localhost:8000`

All REST endpoints are prefixed with `/api/v1`. Authentication uses JWT Bearer tokens. Obtain a token via `POST /api/v1/auth/login`.

---

## Authentication

### POST `/api/v1/auth/login`
Authenticate and receive a JWT access token.

**Content-Type:** `application/x-www-form-urlencoded`

**Body:**
```
username=investigator&password=inv123!
```

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

---

### POST `/api/v1/auth/logout`
Blacklist the current token in Redis. **Auth required.**

**Response 200:** `{"status": "success", "message": "Successfully logged out"}`

---

### GET `/api/v1/auth/me`
Return current user info. **Auth required.**

**Response 200:** `{"user_id": "...", "username": "investigator", "role": "investigator"}`

---

### POST `/api/v1/auth/refresh`
Issue a fresh token with extended expiry. **Auth required.**

**Response 200:** Same shape as `/auth/login`.

---

## Investigation

### POST `/api/v1/investigate`
Upload evidence and start a forensic investigation. **Auth required.**

**Content-Type:** `multipart/form-data`

| Field | Type | Description |
|-------|------|-------------|
| `file` | File | Evidence file (max 50 MB) |
| `case_id` | string | Case identifier (alphanumeric + `-_.`, 1–128 chars) |
| `investigator_id` | string | Investigator ID (same constraints) |

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

**Errors:** `400` invalid file type or size · `413` body too large (>55 MB) · `422` invalid case/investigator ID format · `429` rate limited (10 investigations / 5 min per user)

---

### POST `/api/v1/sessions/{session_id}/resume`
Resume the pipeline after the initial analysis pause. **Auth required.**

The pipeline pauses after initial agent analysis and sends `PIPELINE_PAUSED` over the WebSocket. The frontend calls this endpoint when the user clicks **Accept Analysis** or **Deep Analysis**.

**Body:**
```json
{ "deep_analysis": true }
```

**Response 200:**
```json
{
  "status": "resumed",
  "session_id": "550e8400-...",
  "deep_analysis": true,
  "message": "Deep analysis started"
}
```

Idempotent — if the pipeline was already resumed returns `{"status": "already_resumed", ...}`.

**Errors:** `404` session not found · `400` pipeline not in paused state

---

## Sessions

### WebSocket `/api/v1/sessions/{session_id}/live`
Live WebSocket stream of agent cognitive updates. **Auth via first message.**

**Subprotocol:** `forensic-v1`

**Connection sequence:**
1. Client opens WebSocket
2. Client immediately sends: `{"type": "AUTH", "token": "<jwt>"}`
3. Server responds: `{"type": "CONNECTED", ...}`
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
| `ERROR` | Fatal error |

**Close codes:** `4001` auth failure · `4004` session not found

---

### GET `/api/v1/sessions/{session_id}/report`
Fetch the final signed report. **Auth required.**

**Response 200:** Full `ReportDTO` (see `docs/SCHEMAS.md`)

**Response 202:** Investigation still in progress `{"status": "in_progress", ...}`

**Errors:** `404` session not found · `500` investigation failed · `503` DB temporarily unavailable

---

### GET `/api/v1/sessions/{session_id}/arbiter-status`
Lightweight poll to track arbiter deliberation after `PIPELINE_COMPLETE`. **Auth required.**

Returns one of:
- `{"status": "running", "message": "..."}`
- `{"status": "complete", "report_id": "..."}`
- `{"status": "error", "message": "..."}`
- `{"status": "not_found"}`

---

### GET `/api/v1/sessions/{session_id}/checkpoints`
List pending HITL checkpoints. **Auth required.**

**Response 200:** Array of checkpoint objects, or `[]` if none pending.

---

### GET `/api/v1/sessions/{session_id}/brief/{agent_id}`
Get the most recent thinking brief for a specific agent. **Auth required.**

**Response 200:** `{"brief": "Running ELA analysis on full image..."}`

---

### GET `/api/v1/sessions`
List all active in-memory sessions. **Auth required.**

**Response 200:** Array of `SessionInfo` objects.

---

### DELETE `/api/v1/sessions/{session_id}`
Terminate a running session and cancel its background task. **Auth required.**

**Response 200:** `{"status": "terminated", "session_id": "..."}`

---

## HITL

### POST `/api/v1/hitl/decision`
Submit a Human-in-the-Loop decision for an active checkpoint. **Auth required.**

**Body:**
```json
{
  "session_id": "550e8400-...",
  "checkpoint_id": "7f3c...",
  "agent_id": "Agent3",
  "decision": "APPROVE",
  "note": "Confirmed — lighting analysis is accurate.",
  "override_finding": null
}
```

**Decision values:** `APPROVE` · `REDIRECT` · `OVERRIDE` · `TERMINATE` · `ESCALATE`

**Response 200:** `{"status": "processed", "message": "...", "session_id": "..."}`

---

## Monitoring

### GET `/health`
Deep health check. Returns 200 only when all critical dependencies are healthy.

**Response 200:**
```json
{
  "status": "healthy",
  "environment": "development",
  "active_sessions": 0,
  "checks": {
    "postgres": "ok",
    "redis": "ok",
    "qdrant": "ok"
  }
}
```

**Response 503:** One or more dependencies degraded.

---

### GET `/api/v1/metrics`
Operational counters (Redis-backed, falls back to in-process). **Auth required (admin).**

**Response 200:** JSON with `request_count`, `error_count`, `active_sessions`, `investigations_started`, `investigations_completed`, `investigations_failed`, `uptime_seconds`.

---

## Error Format

All errors return JSON:
```json
{
  "detail": "Human-readable error message"
}
```

In development (`APP_ENV=development`), errors also include a `message` field with the raw exception.
