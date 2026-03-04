# Forensic Council — Production-Ready Test Suite

> Full coverage plan: Unit → Integration → E2E → Performance → Security → Infrastructure

---

## Overview

| Suite | Scope | Tools | Priority |
|-------|-------|-------|----------|
| TS-01 | Unit — Backend Core | pytest, pytest-asyncio | 🔴 Critical |
| TS-02 | Unit — Agents | pytest, pytest-asyncio | 🔴 Critical |
| TS-03 | Unit — Tools | pytest | 🔴 Critical |
| TS-04 | Integration — API Routes | pytest + httpx (TestClient) | 🔴 Critical |
| TS-05 | Integration — Database (Postgres) | pytest + psycopg2 | 🔴 Critical |
| TS-06 | Integration — Redis | pytest + fakeredis | 🟠 High |
| TS-07 | Integration — Qdrant | pytest + qdrant-client | 🟠 High |
| TS-08 | Integration — WebSocket | pytest-asyncio + httpx-ws | 🔴 Critical |
| TS-09 | E2E — Full Pipeline | pytest + Docker Compose | 🔴 Critical |
| TS-10 | E2E — Frontend (UI) | Playwright | 🔴 Critical |
| TS-11 | E2E — Frontend ↔ Backend | Playwright + live server | 🔴 Critical |
| TS-12 | Contract — API Schema | schemathesis / openapi validator | 🟠 High |
| TS-13 | Performance & Load | Locust | 🟡 Medium |
| TS-14 | Security | pytest + bandit + OWASP ZAP | 🔴 Critical |
| TS-15 | Infrastructure — Docker | docker-compose + shell scripts | 🔴 Critical |
| TS-16 | Frontend — Unit/Component | Jest + React Testing Library | 🔴 Critical |
| TS-17 | Frontend — TypeScript | tsc --noEmit | 🔴 Critical |

---

## TS-01 — Unit: Backend Core

**Path:** `backend/tests/unit/core/`

### Config & Settings (`config.py`)
- [ ] All required env vars load correctly with defaults
- [ ] Missing `SIGNING_KEY` raises `ValidationError`
- [ ] Invalid `REDIS_PORT` (non-integer) raises error
- [ ] CORS origins parse correctly from JSON string

### ReAct Loop (`react_loop.py`)
- [ ] Loop terminates after max iterations guard
- [ ] `Reason → Act → Observe` step sequence is respected
- [ ] Tool call failure triggers `Observe` with error state, not crash
- [ ] Loop produces structured output at completion

### Working Memory (`working_memory.py`)
- [ ] Memory initializes empty per session
- [ ] Observations are appended in order
- [ ] Memory can be cleared between steps
- [ ] Serialization/deserialization roundtrip is lossless

### Tool Registry (`tool_registry.py`)
- [ ] Tool registration stores callable by name
- [ ] Dispatching unknown tool name raises `ToolNotFoundError`
- [ ] Duplicate tool registration raises or overwrites (document expected behavior)
- [ ] Tool dispatch passes arguments correctly

### Evidence Model (`evidence.py`)
- [ ] `EvidenceArtifact` validates accepted MIME types
- [ ] Rejected MIME type raises `ValidationError`
- [ ] File size limit is enforced
- [ ] `file_hash` is computed deterministically (SHA-256)

### Custody Logger (`custody_logger.py`)
- [ ] Entry is appended with correct timestamp
- [ ] Each log entry contains: session_id, action, actor, timestamp
- [ ] Log is immutable (no entry modification after write)
- [ ] Serialized log is verifiable

### Confidence Calibration (`calibration.py`)
- [ ] Scores in [0.0, 1.0] pass validation
- [ ] Score > 1.0 is clamped or rejected
- [ ] Score < 0.0 is clamped or rejected
- [ ] Calibration formula produces expected output for known input

### Cryptographic Signing (`signing.py`)
- [ ] `SIGNING_KEY` produces consistent signature for same payload
- [ ] Different payloads produce different signatures
- [ ] Signature verification returns `True` for valid pair
- [ ] Tampered payload fails verification
- [ ] Missing key raises `ConfigurationError`

---

## TS-02 — Unit: Agents

**Path:** `backend/tests/unit/agents/`

### Base Agent (`base_agent.py`)
- [ ] Agent initializes with correct specialty and tools
- [ ] `run()` calls ReAct loop and returns `AgentFinding`
- [ ] `AgentFinding` has: `agent_id`, `confidence`, `findings`, `evidence_refs`
- [ ] Agent respects working memory isolation (no cross-agent leakage)
- [ ] Agent handles empty/null evidence input gracefully

### Agent 1 — Image Forensics
- [ ] Accepts PNG, JPG, WEBP; rejects MP3
- [ ] ELA analysis returns anomaly score
- [ ] EXIF extraction returns dict (or empty dict if no EXIF)
- [ ] Splice detection returns regions list
- [ ] `AgentFinding.confidence` is within [0,1]

### Agent 2 — Audio Forensics
- [ ] Accepts MP3, WAV, FLAC; rejects JPEG
- [ ] Spectral analysis returns frequency data
- [ ] Voice anomaly detection returns boolean flag + confidence
- [ ] Handles corrupted audio file without crash (returns low-confidence finding)

### Agent 3 — Object Detection
- [ ] Returns list of detected objects with bounding boxes
- [ ] Scene consistency score is computed
- [ ] Empty scene (blank image) returns empty object list, not error
- [ ] Inconsistent context (e.g., car in ocean) produces anomaly flag

### Agent 4 — Video Forensics
- [ ] Accepts MP4, MOV, AVI; rejects PDF
- [ ] Frame extraction produces N frames from video
- [ ] Temporal consistency check returns per-segment scores
- [ ] Single-frame video is handled without crash

### Agent 5 — Metadata Forensics
- [ ] EXIF parsing returns structured metadata dict
- [ ] XMP parsing returns structured metadata dict
- [ ] Timestamp validation flags future timestamps
- [ ] GPS coordinates are validated (lat in [-90,90], lon in [-180,180])
- [ ] Missing metadata returns finding with low confidence, not error

### Council Arbiter (`arbiter.py`)
- [ ] Accepts exactly 5 `AgentFinding` objects
- [ ] Fewer than 5 findings still produces a report (with partial flag)
- [ ] Cross-modal correlation detects contradictions between agents
- [ ] Final verdict is one of: `AUTHENTIC`, `SUSPICIOUS`, `MANIPULATED`, `INCONCLUSIVE`
- [ ] Report is cryptographically signed
- [ ] All 5 agent findings are embedded in the final report

---

## TS-03 — Unit: Tools

**Path:** `backend/tests/unit/tools/`

### Image Tools (`image_tools.py`)
- [ ] `compute_ela` returns heatmap array for valid image
- [ ] `extract_exif` returns dict with known fields for test fixture
- [ ] Both tools raise `ToolError` on invalid file path (not generic Exception)

### Audio Tools (`audio_tools.py`)
- [ ] `spectral_analysis` returns expected shape for test WAV fixture
- [ ] `detect_voice_anomaly` returns `(bool, float)` tuple

### Video Tools (`video_tools.py`)
- [ ] `extract_frames` returns correct count for test MP4
- [ ] `check_temporal_consistency` returns list of per-segment scores

### Metadata Tools (`metadata_tools.py`)
- [ ] `parse_exif_xmp` returns correct fields for test JPEG with known metadata
- [ ] `validate_timestamps` flags timestamp 10 years in the future
- [ ] `check_gps` validates a known coordinate

---

## TS-04 — Integration: API Routes

**Path:** `backend/tests/integration/api/`
**Setup:** `TestClient(app)` + test Postgres + test Redis

### Health Check
- [ ] `GET /health` returns `200 OK` with `{"status": "ok"}`
- [ ] `GET /health` returns non-200 when Postgres is down

### Investigation Route (`/api/v1/investigate`)
- [ ] `POST` with valid evidence file returns `201` with `session_id`
- [ ] `POST` with no file returns `422`
- [ ] `POST` with oversized file returns `413`
- [ ] `POST` with unsupported MIME type returns `415`
- [ ] Duplicate upload to same session returns appropriate response

### Session Routes (`/api/v1/sessions`)
- [ ] `GET /sessions` returns list of active sessions
- [ ] `GET /sessions/{id}/report` returns full report for completed session
- [ ] `GET /sessions/{id}/report` returns `404` for unknown session
- [ ] `GET /sessions/{id}/brief/{agent}` returns agent-specific brief
- [ ] `GET /sessions/{id}/brief/agent99` returns `404`
- [ ] `GET /sessions/{id}/checkpoints` returns pending HITL items
- [ ] `DELETE /sessions/{id}` returns `200` and terminates session
- [ ] `DELETE /sessions/nonexistent` returns `404`

### HITL Route (`/api/v1/hitl/decision`)
- [ ] `POST` with valid decision payload returns `200`
- [ ] `POST` with invalid decision value returns `422`
- [ ] `POST` for already-resolved checkpoint returns `409`

### Input Validation (all routes)
- [ ] SQL injection strings in params are sanitized (no 500 error)
- [ ] XSS strings in text fields are sanitized
- [ ] Excessively long strings in fields return `422`

---

## TS-05 — Integration: Database (PostgreSQL)

**Path:** `backend/tests/integration/infra/`
**Setup:** Docker test Postgres or `pytest-postgresql`

### postgres_client.py
- [ ] Connection pool initializes successfully
- [ ] Query returns expected rows for seeded data
- [ ] Transaction rollback on error leaves DB unchanged
- [ ] Connection pool respects max connections setting

### Evidence Store (`evidence_store.py`)
- [ ] `save_evidence` persists artifact and returns ID
- [ ] `get_evidence` retrieves artifact by ID
- [ ] `delete_evidence` removes record and associated file reference
- [ ] `list_evidence_by_session` returns correct items for session

### Session Manager (DB-side)
- [ ] Session is created with `PENDING` status on investigation start
- [ ] Session status transitions: `PENDING → RUNNING → COMPLETE`
- [ ] Session status transitions: `RUNNING → FAILED` on pipeline error
- [ ] Orphaned sessions (no heartbeat) can be queried

---

## TS-06 — Integration: Redis

**Path:** `backend/tests/integration/infra/`
**Tool:** `fakeredis` for unit-level; real Redis container for integration

- [ ] `redis_client.py` connects successfully to Redis 7
- [ ] Cache set/get roundtrip works for session state
- [ ] TTL expiry removes key after configured time
- [ ] Redis failure causes graceful degradation (not hard crash)
- [ ] Pub/Sub channel for live updates publishes and receives messages

---

## TS-07 — Integration: Qdrant

**Path:** `backend/tests/integration/infra/`

- [ ] `qdrant_client.py` connects to Qdrant v1.9.2
- [ ] Collection is created on startup if not existing
- [ ] Vector upsert succeeds for a valid embedding
- [ ] Similarity search returns expected results for known vectors
- [ ] Search with zero results returns empty list (not error)

---

## TS-08 — Integration: WebSocket

**Path:** `backend/tests/integration/api/`
**Tool:** `pytest-asyncio` + `httpx-ws` or `websockets`

- [ ] `WS /api/v1/sessions/{id}/live` connects successfully for valid session
- [ ] Connection for invalid session receives error message then closes
- [ ] Agent status events are broadcast in real-time during investigation
- [ ] `AGENT_STARTED` event is received for each of 5 agents
- [ ] `AGENT_COMPLETE` event includes `AgentFinding` summary
- [ ] `INVESTIGATION_COMPLETE` event is received at end of pipeline
- [ ] `HITL_CHECKPOINT` event is received when HITL is triggered
- [ ] WebSocket closes gracefully after session deletion
- [ ] Reconnection to completed session receives final state replay

---

## TS-09 — E2E: Full Pipeline

**Path:** `backend/tests/test_integration/test_e2e.py`
**Setup:** Full Docker Compose stack running, or unit tests with mocked infrastructure

### TestFullPipeline — Full Pipeline Tests
- [x] `test_full_pipeline_produces_signed_report` — Pipeline produces signed report with hash matching content
- [x] `test_chain_of_custody_log_not_empty` — Chain-of-custody log has at least one entry
- [x] `test_chain_of_custody_entries_are_non_null` — All custody log entries are non-null
- [x] `test_evidence_version_tree_has_derivative_artifacts` — Evidence version tree contains at least 1 node
- [x] `test_report_uncertainty_statement_present` — Report includes non-empty uncertainty statement
- [x] `test_no_finding_silently_merged_contested` — Report exposes contested_findings field
- [x] `test_executive_summary_present_and_non_empty` — Report includes non-empty executive summary
- [x] `test_report_has_per_agent_findings` — Per_agent_findings populated with at least one agent
- [x] `test_report_ids_unique_across_runs` — Two separate runs produce distinct report_ids
- [x] `test_pipeline_with_nonexistent_file_raises` — Nonexistent file path raises exception
- [x] `test_signed_utc_is_iso8601_parseable` — Report signed_utc is valid ISO-8601 datetime
- [x] `test_authentic_image_no_high_confidence_manipulation` — Unmodified image doesn't produce high-confidence MANIPULATION
- [x] `test_report_case_id_matches_input` — Report case_id exactly matches input

### TestSessionManager — Session Management Tests
- [x] `test_create_session` — Session returns INITIALIZING status with all agent slots
- [x] `test_add_and_resolve_checkpoint` — Resolving PENDING checkpoint removes from active list
- [x] `test_session_ids_are_unique` — Two create_session calls produce distinct session_ids
- [x] `test_get_session_returns_created_session` — get_session returns same session as created
- [x] `test_get_nonexistent_session_returns_none` — Fetching never-created session returns None
- [x] `test_multiple_checkpoints_resolved_independently` — Resolving cp1 leaves cp2 still active
- [x] `test_session_stores_correct_investigator_id` — Session preserves investigator_id at creation

### TestPipelineComponents — Pipeline Component Tests
- [x] `test_pipeline_initialization` — Pipeline initializes with non-None config
- [x] `test_mime_type_detection` — Common image extensions map to correct MIME types
- [x] `test_mime_type_image_formats` — .jpg, .jpeg, .png, .webp, .tiff map correctly
- [x] `test_mime_type_av_formats` — .mp4, .mov, .wav, .mp3, .flac, .mkv map correctly
- [x] `test_mime_type_unknown_fallback` — Unknown extensions fall back to application/octet-stream
- [x] `test_config_has_required_fields` — Config exposes iteration_ceiling and investigation_timeout

### TestAPIContracts — API Contract Tests
- [x] `test_root_returns_name_and_version` — GET / returns name and version
- [x] `test_health_returns_healthy` — GET /health returns healthy status
- [x] `test_health_has_environment_field` — Health response includes environment field
- [x] `test_health_has_active_sessions_count` — Health includes active_sessions count (int)
- [x] `test_investigate_invalid_mime_returns_422` — Invalid MIME type returns 422
- [x] `test_investigate_oversized_file_returns_413` — Oversized file returns 413
- [x] `test_get_report_unknown_session_returns_404` — Unknown session report returns 404
- [x] `test_security_headers_present` — X-content-type-options and X-frame-options headers present
- [x] `test_unknown_route_returns_404` — Unknown route returns 404
- [x] `test_cors_header_present_for_allowed_origin` — CORS allow-origin header present
- [x] `test_options_preflight_returns_200` — CORS preflight OPTIONS returns 200/204
- [x] `test_investigate_missing_case_id_returns_422` — Missing case_id returns 401 or 422

### TestCryptographicIntegrity — Crypto Tests
- [x] `test_sha256_hash_is_64_char_lowercase_hex` — SHA-256 hash is 64 char lowercase hex
- [x] `test_tampered_content_produces_different_hash` — Tampered content produces different hash
- [x] `test_hash_is_deterministic` — Hash is deterministic for same input
- [x] `test_agent_signer_sign_and_verify_roundtrip` — AgentSigner signs and verifies same content
- [x] `test_agent_signer_detects_tampered_content` — Modifying signed content causes verify() to return False

### TestConfigValidation — Configuration Tests
- [x] `test_default_app_env_is_development` — Default app_env is development
- [x] `test_invalid_log_level_raises` — Invalid log level raises ValidationError
- [x] `test_invalid_app_env_raises` — Invalid app_env raises ValidationError
- [x] `test_redis_url_includes_host_and_port` — Redis URL includes host and port
- [x] `test_database_url_includes_all_components` — Database URL includes all components
- [x] `test_debug_parsed_from_string_true` — Debug parsed from string "true"
- [x] `test_debug_parsed_from_string_false` — Debug parsed from string "false"
- [x] `test_effective_jwt_secret_falls_back_to_signing_key` — JWT secret falls back to signing_key

### TestEvidenceFixtures — Fixture Tests
- [x] `test_spliced_jpeg_is_readable` — Splice fixture is readable JPEG with correct dimensions
- [x] `test_authentic_jpeg_has_software_exif_tag` — Authentic image has Software EXIF tag
- [x] `test_audio_wav_has_correct_params` — WAV fixture has correct channel, sample rate, frames
- [x] `test_splice_jpeg_has_no_software_exif_tag` — Splice fixture has no Software tag
- [x] `test_authentic_jpeg_dimensions` — Authentic JPEG has expected dimensions
- [x] `test_audio_wav_is_silence` — WAV fixture frames are all null bytes

> **Note:** Tests marked [x] pass without infrastructure (mocked or unit). Full pipeline tests require Docker services (Redis, Qdrant, PostgreSQL).

---

## TS-10 — E2E: Frontend (UI)

**Path:** `frontend/tests/e2e/`
**Tool:** Playwright

### Landing Page (`/`)
- [ ] Page loads without console errors
- [ ] Three.js scene renders (canvas element exists and is non-empty)
- [ ] "Start Investigation" CTA button is visible and clickable
- [ ] Clicking CTA navigates to `/evidence`

### Evidence Upload Page (`/evidence`)
- [ ] Drag-and-drop zone is visible
- [ ] File input accepts image, audio, and video files
- [ ] Rejected file type shows user-facing error message
- [ ] Oversized file shows size limit error
- [ ] Accepted file shows filename and preview (for images)
- [ ] "Analyze" button is disabled until file is uploaded
- [ ] Clicking "Analyze" with valid file calls `POST /api/v1/investigate`

### Live Analysis Page (`/evidence` — post-submit)
- [ ] 5 agent cards are rendered
- [ ] WebSocket connection is established after upload
- [ ] Agent cards update status: `IDLE → RUNNING → COMPLETE`
- [ ] Agent confidence score renders correctly per card
- [ ] Progress indicator advances as agents complete
- [ ] Error state renders if WebSocket disconnects unexpectedly
- [ ] "View Report" button appears after `INVESTIGATION_COMPLETE` event

### Report Page (`/result`)
- [ ] Report page loads with correct `session_id`
- [ ] Verdict badge renders with correct label and color
- [ ] All 5 agent findings are displayed
- [ ] Cryptographic signature section is visible
- [ ] "Download Report" button triggers file download
- [ ] Invalid `session_id` shows 404 error state

### Error Boundary (`error.tsx`)
- [ ] Intentional JS error triggers error boundary
- [ ] Error boundary shows user-friendly fallback UI
- [ ] Error boundary does not show raw stack trace in production

---

## TS-11 — E2E: Frontend ↔ Backend Integration

**Setup:** Full Docker Compose stack + Playwright against `http://localhost:3001`

- [ ] Full upload-to-report journey completes without manual intervention
- [ ] Live WebSocket updates appear on the analysis page in real time
- [ ] All 5 agent status cards update correctly during live run
- [ ] Final report page shows data fetched from backend API (not mock data)
- [ ] HITL checkpoint modal appears on frontend when backend triggers HITL
- [ ] Approving HITL from UI sends correct payload to `POST /hitl/decision`
- [ ] Session deleted from backend causes frontend to show expired session page
- [ ] API error (5xx) shows user-facing error toast, not blank screen
- [ ] Page refresh mid-investigation restores analysis state from backend

---

## TS-12 — Contract: API Schema Validation

**Tool:** `schemathesis` against the live FastAPI `/openapi.json`

- [ ] All documented routes match the OpenAPI schema
- [ ] `POST /investigate` request body matches schema
- [ ] `AgentFinding` response shape matches documented schema
- [ ] `InvestigationReport` response shape matches documented schema
- [ ] Schemathesis fuzz test finds no 500 errors from malformed inputs
- [ ] All error responses (4xx) include `detail` field

---

## TS-13 — Performance & Load

**Tool:** Locust (`backend/tests/load/`)

### Baseline (single user)
- [ ] `POST /investigate` p95 response time < 500ms (upload, before pipeline)
- [ ] `GET /health` p99 < 50ms

### Concurrent Investigations
- [ ] 10 concurrent sessions run without OOM or deadlock
- [ ] Redis pub/sub handles 10 concurrent WebSocket clients
- [ ] Postgres connection pool does not exhaust under 10 concurrent sessions

### Stress Test
- [ ] 50 concurrent uploads — system returns 503 gracefully, not 500
- [ ] System recovers after spike (no stuck sessions after load subsides)

---

## TS-14 — Security

### Static Analysis
- [ ] `bandit -r backend/` passes with no HIGH severity issues
- [ ] `safety check` finds no known vulnerable dependencies
- [ ] `npm audit --audit-level=high` finds no high/critical frontend vulnerabilities

### Authentication & Authorization
- [ ] `/api/v1/sessions/{id}` for another user's session returns `403` (if auth is implemented)
- [ ] `SIGNING_KEY` is never logged or returned in any API response
- [ ] `.env` file is not served as a static asset

### Input Security
- [ ] File upload endpoint rejects `.exe`, `.sh`, `.php` with `415`
- [ ] MIME type sniffing bypass (e.g., JPEG header + malicious body) is handled
- [ ] Path traversal in filename (`../../etc/passwd`) is sanitized
- [ ] Maximum file upload size is enforced at API level (not just frontend)

### Headers & CORS
- [ ] CORS allows only `http://localhost:3001` and `http://localhost:3000` in dev
- [ ] `Content-Security-Policy` header is present in frontend responses
- [ ] `X-Frame-Options` prevents iframe embedding
- [ ] Sensitive headers (`Server`, `X-Powered-By`) are stripped

### Cryptographic Report Integrity
- [ ] Report signature verification fails if any field is modified post-signing
- [ ] `SIGNING_KEY` rotation invalidates old signatures (by design)

---

## TS-15 — Infrastructure: Docker

**Path:** `tests/infra/` (shell scripts + docker-compose assertions)

### Service Health
- [ ] `docker compose -f docker/docker-compose.yml --env-file .env up -d` starts all 5 services without error
- [ ] `forensic_redis` health check passes within 30s
- [ ] `forensic_postgres` health check passes within 30s
- [ ] `forensic_qdrant` is reachable at `localhost:6333`
- [ ] `forensic_api` health check (`/health`) passes within 60s
- [ ] `forensic_ui` responds at `localhost:3001` within 90s

### Dependency Ordering
- [ ] Backend does not start until Postgres + Redis are healthy (depends_on condition)
- [ ] Frontend does not start until backend health check passes

### Persistence
- [ ] Data written to Postgres persists across `docker compose -f docker/docker-compose.yml --env-file .env restart`
- [ ] Data written to Qdrant persists across `docker compose -f docker/docker-compose.yml --env-file .env restart`
- [ ] Data written to Redis persists across `docker compose -f docker/docker-compose.yml --env-file .env restart` (AOF/RDB enabled)

### Environment Variables
- [ ] `POSTGRES_USER` and `POSTGRES_PASSWORD` are read from env (not hardcoded)
- [ ] `SIGNING_KEY` is required and container fails fast if absent
- [ ] `NEXT_PUBLIC_API_URL` build arg is correctly injected into frontend image

### Failure Scenarios
- [ ] Killing `forensic_postgres` causes backend to return `503`, not `500`
- [ ] Killing `forensic_redis` causes backend to return `503`, not crash
- [ ] Containers restart automatically (`restart: unless-stopped`)

---

## TS-16 — Frontend: Unit & Component Tests

**Path:** `frontend/tests/unit/`
**Tool:** Jest + React Testing Library

### API Client (`lib/api.ts`)
- [ ] `startInvestigation` sends `POST /api/v1/investigate` with FormData
- [ ] `getReport` sends `GET /api/v1/sessions/{id}/report`
- [ ] Network error surfaces as rejected Promise (not silent failure)
- [ ] 4xx response throws typed error with status code

### `useSimulation` Hook
- [ ] Initializes with all 5 agents in `IDLE` state
- [ ] WebSocket `AGENT_STARTED` message transitions correct agent to `RUNNING`
- [ ] WebSocket `AGENT_COMPLETE` message transitions correct agent to `COMPLETE`
- [ ] `INVESTIGATION_COMPLETE` triggers navigation readiness
- [ ] WebSocket error sets error state

### `useForensicData` Hook
- [ ] Fetches report from API on mount for given session ID
- [ ] Loading state is `true` during fetch, `false` after
- [ ] Report data is correctly typed against `InvestigationReport`
- [ ] 404 response sets `notFound` state

### Components (React Testing Library)
- [ ] `AgentCard` renders correct name and status badge for each agent
- [ ] `AgentCard` shows confidence score when status is `COMPLETE`
- [ ] `VerdictBadge` renders green for `AUTHENTIC`, red for `MANIPULATED`
- [ ] `FileDropZone` calls `onFileSelected` with correct File object
- [ ] `FileDropZone` rejects invalid types and calls `onError`

---

## TS-17 — Frontend: TypeScript

- [ ] `npx tsc --noEmit` exits 0 (zero type errors)
- [ ] `npm run lint` exits 0 (zero ESLint errors)
- [ ] All API response types in `types/index.ts` match backend Pydantic schemas

---

## Test Data & Fixtures

Maintain a `backend/tests/fixtures/` directory with:

| File | Purpose |
|------|---------|
| `authentic.jpg` | Real, unmodified JPEG with valid EXIF |
| `ela_spliced.jpg` | JPEG with known ELA-detectable splice |
| `no_exif.png` | PNG with no metadata |
| `authentic.wav` | Clean WAV, no anomalies |
| `anomaly.wav` | WAV with injected voice anomaly |
| `authentic.mp4` | Short, clean MP4 |
| `corrupt.jpg` | Intentionally corrupted file header |
| `oversized.bin` | File exceeding the size limit |

---

## CI/CD Integration

```yaml
# Suggested GitHub Actions pipeline
jobs:
  unit:          # TS-01, TS-02, TS-03, TS-16, TS-17
  integration:   # TS-04, TS-05, TS-06, TS-07, TS-08 (via docker-compose test services)
  e2e:           # TS-09, TS-10, TS-11 (full stack spin-up)
  security:      # TS-14 (bandit, safety, npm audit)
  load:          # TS-13 (run on merge to main only, not every PR)
```

**Recommended thresholds for production readiness:**

| Metric | Target |
|--------|--------|
| Unit test coverage (backend) | ≥ 85% |
| Unit test coverage (frontend) | ≥ 80% |
| All critical E2E tests | 100% passing |
| Security scan | 0 HIGH/CRITICAL |
| TypeScript errors | 0 |
| p95 upload latency | < 500ms |
