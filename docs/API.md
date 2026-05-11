# Forensic Council — API Reference

**Version:** v1.7.0 | **Base URL:** `http://localhost:8000`

All REST endpoints are prefixed with `/api/v1`. Authentication uses JWT Bearer tokens. Obtain a token via `POST /api/v1/auth/login`.

---

## Authentication

### POST `/api/v1/auth/login`
Authenticate and receive a JWT access token.

**Content-Type:** `application/x-www-form-urlencoded`

**Body:**
```
username=investigator&password=CHANGE_ME_dev_only_password
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

**Accepted extensions:** `.jpg`, `.jpeg`, `.png`, `.tiff`, `.tif`, `.webp`, `.gif`, `.bmp`, `.mp4`, `.mov`, `.avi`, `.wav`, `.mp3`, `.m4a`, `.flac`

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
List all active sessions from Redis. **Auth required.**

**Response 200:** Array of `SessionInfo` objects.

---

### GET `/api/v1/sessions/{session_id}`
Get session metadata. **Auth required.**

Returns `{"session_id": "...", "case_id": "...", "status": "...", "created_at": "..."}`.

**Errors:** `400` invalid session ID format · `404` session not found

---

### GET `/api/v1/sessions/{session_id}/quota`
Get per-session API usage data (tokens, calls, cost estimate). **Auth required.**

**Response 200:**
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

### GET `/api/v1/sessions/{session_id}/report/download`
Download the report as a JSON file with `Content-Disposition: attachment` headers. **Auth required.**

Same resolution order as `/report`. Returns `202` if investigation still in progress.

---

### GET `/api/v1/sessions/{session_id}/report/pdf`
Download the report as a PDF (falls back to HTML if WeasyPrint unavailable). **Auth required.**

Returns `X-PDF-Fallback: true` header if HTML was served instead.

---

### GET `/api/v1/sessions/{session_id}/brief`
Get lightweight session metadata and brief. **Auth required.**

---

### GET `/api/v1/sessions/{session_id}/progress`
SSE (Server-Sent Events) stream alternative to WebSocket for agent progress updates. **Auth required.**

Yields the same event types as the WebSocket channel.

---

### DELETE `/api/v1/sessions/{session_id}`
Terminate a running session and close its WebSocket connections. **Auth required.**

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

## Health

### GET `/health`
Deep health check. Returns 200 only when all critical dependencies are healthy.

**Response 200:**
```json
{
  "status": "healthy",
  "checks": {
    "migrations": "ok",
    "postgres": "ok",
    "redis": "ok",
    "qdrant": "ok"
  }
}
```

**Response 503:** One or more dependencies degraded.

### GET `/api/v1/health/ml-tools`
ML tool warm-up status. Returns tools_present, tools_total, and per-tool presence status.

### GET `/api/v1/health/tools`
System tool availability (ffmpeg, exiftool, tesseract). Returns `{"status": "healthy" | "degraded"}`.

---

## Cases
Create a new multi-artifact case. **Auth required.**

**Content-Type:** `application/x-www-form-urlencoded`

**Body:** `label=Case+Description` (optional)

**Response 201:**
```json
{
  "case_id": "A1B2C3D4",
  "label": "Case Description",
  "status": "open",
  "artifacts_url": "/api/v1/cases/A1B2C3D4/artifacts",
  "analyze_url": "/api/v1/cases/A1B2C3D4/analyze"
}
```

---

### POST `/api/v1/cases/{case_id}/artifacts`
Add an evidence artifact (file) to a case. **Auth required.** Max 10 artifacts per case.

**Content-Type:** `multipart/form-data`

**Body:** `file` (binary, required)

**Response 201:**
```json
{
  "artifact_id": "uuid",
  "session_id": "uuid",
  "case_id": "A1B2C3D4",
  "filename": "evidence.jpg",
  "status": "pending"
}
```

**Errors:** `404` case not found · `409` case not in open state · `422` max artifacts reached

---

### POST `/api/v1/cases/{case_id}/analyze`
Start forensic analysis for all pending artifacts. **Auth required.**

**Response 200:**
```json
{
  "case_id": "A1B2C3D4",
  "status": "analyzing",
  "dispatched_artifacts": 2,
  "artifact_session_ids": ["uuid1", "uuid2"],
  "results_url": "/api/v1/cases/A1B2C3D4"
}
```

---

### GET `/api/v1/cases/{case_id}`
Get case status and aggregated results. **Auth required.**

Poll this endpoint after calling `/analyze`.

**Response 200:**
```json
{
  "case_id": "A1B2C3D4",
  "label": "...",
  "status": "completed",
  "combined_verdict": "SUSPICIOUS",
  "combined_manipulation_probability": 0.72,
  "artifacts": [...],
  "created_at": "2026-05-09T...",
  "completed_at": "2026-05-09T..."
}
```

---

## Webhooks

### POST `/api/v1/webhooks`
Register a webhook URL for investigation-complete callbacks. **Auth required.**

**Body:**
```json
{
  "url": "https://your-server.example.com/hook",
  "secret": "optional-hmac-secret",
  "events": ["investigation.complete"],
  "description": "Optional label"
}
```

**Response 201:** `{"webhook_id": "uuid", "status": "registered"}`

---

### GET `/api/v1/webhooks`
List all webhooks registered by the current user. **Auth required.**

**Response 200:** Array of webhook records (secrets never returned).

---

### DELETE `/api/v1/webhooks/{webhook_id}`
Delete a registered webhook. **Auth required.** Returns `204 No Content`.

**Errors:** `404` not found

---

## Metrics

### GET `/api/v1/metrics`
Operational counters (Redis-backed with in-process fallback). **Auth required (admin).**

**Response 200:**
```json
{
  "uptime_seconds": 3600.0,
  "requests_total": 142,
  "request_duration_avg_ms": 45.3,
  "errors_total": 2,
  "error_rate": 0.014,
  "active_sessions": 3,
  "investigations_started": 28,
  "investigations_completed": 25,
  "investigations_failed": 1,
  "success_rate": 0.96,
  "rate_limit_redis_bypasses": 0,
  "db_pool_size": 5,
  "db_pool_available": 3,
  "db_pool_in_use": 2,
  "db_pool_max": 10
}
```

---

### GET `/api/v1/metrics/prometheus`
Prometheus exposition format. **Auth required (admin).**

---

### GET `/api/v1/metrics/public`
Prometheus exposition for local smoke tests (no auth required in dev).

---

### GET `/api/v1/metrics/raw`
Prometheus scrape endpoint protected by static bearer token. Configure via `METRICS_SCRAPE_TOKEN`. Returns `503` if not configured, `401` if token mismatched.

---

### GET `/api/v1/metrics/pool-status`
Database connection pool statistics. **Auth required (admin).**

---

## Error Format

All errors return JSON:
```json
{
  "detail": "Human-readable error message"
}
```

In development (`APP_ENV=development`), errors also include a `message` field with the raw exception.
