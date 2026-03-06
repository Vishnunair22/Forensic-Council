# Testing Guide

The Forensic Council relies on `pytest` for the backend and `jest` for the frontend.

---

## 1. Running Tests Locally

### A. Spin Up Dependent Services

The backend needs Postgres, Redis, and Qdrant. Start only the data stores:
```bash
docker compose -f docker/docker-compose.infra.yml --env-file .env up -d
```

### B. Backend Tests (pytest)

```bash
cd backend
uv sync --extra dev

# Run all tests
uv run pytest

# Run tests with stdout output and debug logs
uv run pytest -s -v

# Run only a specific test file
uv run pytest tests/test_tools/test_image_tools.py

# Generate a coverage report
uv run pytest --cov=core --cov=agents --cov=orchestration --cov-report=html
```

Coverage report: open `backend/htmlcov/index.html` in your browser.

### C. Frontend Tests (jest)

```bash
cd frontend
npm install

# Run all tests
npm run test

# Run tests in watch mode
npm run test:watch
```

### D. CI Requirements

- ≥ **85% backend line coverage**
- All `@pytest.mark.asyncio` tests pass without hanging
- No frontend linting errors (`npm run lint`)

---

## 2. Test Suite Reference

> Full coverage plan: Unit → Integration → E2E → Performance → Security → Infrastructure

### Suite Overview

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

### TS-01 — Unit: Backend Core

**Path:** `backend/tests/unit/core/`

#### Config & Settings (`config.py`)
- [ ] All required env vars load correctly with defaults
- [ ] Missing `SIGNING_KEY` raises `ValidationError`
- [ ] Invalid `REDIS_PORT` (non-integer) raises error
- [ ] CORS origins parse correctly from JSON string

#### ReAct Loop (`react_loop.py`)
- [ ] Loop terminates after max iterations guard
- [ ] `Reason → Act → Observe` step sequence is respected
- [ ] Tool call failure triggers `Observe` with error state, not crash
- [ ] Loop produces structured output at completion

#### Working Memory (`working_memory.py`)
- [ ] Memory initializes empty per session
- [ ] Observations are appended in order
- [ ] Memory can be cleared between steps
- [ ] Serialization/deserialization roundtrip is lossless

#### Tool Registry (`tool_registry.py`)
- [ ] Tool registration stores callable by name
- [ ] Dispatching unknown tool name raises `ToolNotFoundError`
- [ ] Duplicate tool registration raises or overwrites (document expected behavior)
- [ ] Tool dispatch passes arguments correctly

#### Evidence Model (`evidence.py`)
- [ ] `EvidenceArtifact` validates accepted MIME types
- [ ] Rejected MIME type raises `ValidationError`
- [ ] File size limit is enforced
- [ ] `file_hash` is computed deterministically (SHA-256)

#### Custody Logger (`custody_logger.py`)
- [ ] Entry is appended with correct timestamp
- [ ] Each log entry contains: session_id, action, actor, timestamp
- [ ] Log is immutable (no entry modification after write)
- [ ] Serialized log is verifiable

#### Confidence Calibration (`calibration.py`)
- [ ] Scores in [0.0, 1.0] pass validation
- [ ] Score > 1.0 is clamped or rejected
- [ ] Score < 0.0 is clamped or rejected
- [ ] Calibration formula produces expected output for known input

#### Cryptographic Signing (`signing.py`)
- [ ] `SIGNING_KEY` produces consistent signature for same payload
- [ ] Different payloads produce different signatures
- [ ] Signature verification returns `True` for valid pair
- [ ] Tampered payload fails verification
- [ ] Missing key raises `ConfigurationError`

---

### TS-02 — Unit: Agents

**Path:** `backend/tests/unit/agents/`

#### Base Agent (`base_agent.py`)
- [ ] Agent initializes with correct specialty and tools
- [ ] `run()` calls ReAct loop and returns `AgentFinding`
- [ ] `AgentFinding` has: `agent_id`, `confidence`, `findings`, `evidence_refs`
- [ ] Agent respects working memory isolation (no cross-agent leakage)
- [ ] Agent handles empty/null evidence input gracefully

#### Agent 1 — Image Forensics
- [ ] Accepts PNG, JPG, WEBP; rejects MP3
- [ ] ELA analysis returns anomaly score
- [ ] EXIF extraction returns dict (or empty dict if no EXIF)
- [ ] Splice detection returns regions list
- [ ] `AgentFinding.confidence` is within [0,1]

#### Agent 2 — Audio Forensics
- [ ] Accepts MP3, WAV, FLAC; rejects JPEG
- [ ] Spectral analysis returns frequency data
- [ ] Voice anomaly detection returns boolean flag + confidence
- [ ] Handles corrupted audio file without crash (returns low-confidence finding)

#### Agent 3 — Object Detection
- [ ] Returns list of detected objects with bounding boxes
- [ ] Scene consistency score is computed
- [ ] Empty scene (blank image) returns empty object list, not error
- [ ] Inconsistent context (e.g., car in ocean) produces anomaly flag

#### Agent 4 — Video Forensics
- [ ] Accepts MP4, MOV, AVI; rejects PDF
- [ ] Frame extraction produces N frames from video
- [ ] Temporal consistency check returns per-segment scores
- [ ] Single-frame video is handled without crash

#### Agent 5 — Metadata Forensics
- [ ] EXIF parsing returns structured metadata dict
- [ ] XMP parsing returns structured metadata dict
- [ ] Timestamp validation flags future timestamps
- [ ] GPS coordinates are validated (lat in [-90,90], lon in [-180,180])
- [ ] Missing metadata returns finding with low confidence, not error

#### Council Arbiter (`arbiter.py`)
- [ ] Accepts exactly 5 `AgentFinding` objects
- [ ] Fewer than 5 findings still produces a report (with partial flag)
- [ ] Cross-modal correlation detects contradictions between agents
- [ ] Final verdict is one of: `AUTHENTIC`, `SUSPICIOUS`, `MANIPULATED`, `INCONCLUSIVE`
- [ ] Report is cryptographically signed
- [ ] All 5 agent findings are embedded in the final report

---

### TS-03 — Unit: Tools

**Path:** `backend/tests/unit/tools/`

- [ ] `compute_ela` returns heatmap array for valid image
- [ ] `extract_exif` returns dict with known fields for test fixture
- [ ] `spectral_analysis` returns expected shape for test WAV fixture
- [ ] `detect_voice_anomaly` returns `(bool, float)` tuple
- [ ] `extract_frames` returns correct count for test MP4
- [ ] `check_temporal_consistency` returns list of per-segment scores
- [ ] `parse_exif_xmp` returns correct fields for test JPEG with known metadata
- [ ] `validate_timestamps` flags timestamp 10 years in the future

---

### TS-04 to TS-08 — Integration Tests

**Path:** `backend/tests/integration/`

Covers API routes (health, investigate, sessions, HITL), database connectivity,
Redis caching, Qdrant vector search, and WebSocket live events. See the test files
in `backend/tests/` for full implementation.

---

### TS-09 — E2E: Full Pipeline (Implemented ✅)

**Path:** `backend/tests/test_integration/test_e2e.py`

All E2E pipeline tests pass. See `test_e2e.py` for the full list of 45+ test cases covering:
- Pipeline → signed report generation
- Chain-of-custody logging
- Cryptographic integrity
- Session management
- API contracts
- Config validation
- Evidence fixtures

---

### TS-10 to TS-17 — Frontend & Advanced Testing

See `backend/tests/` and `frontend/src/__tests__/` for existing tests.
Remaining suites (Playwright E2E, load testing, security scanning) are documented
as checklists above for future implementation.

---

## 3. Test Data & Fixtures

Maintained in `backend/tests/fixtures/`:

| File | Purpose |
|------|---------|
| `authentic.jpg` | Real, unmodified JPEG with valid EXIF |
| `ela_spliced.jpg` | JPEG with known ELA-detectable splice |
| `no_exif.png` | PNG with no metadata |
| `authentic.wav` | Clean WAV, no anomalies |
| `authentic.mp4` | Short, clean MP4 |
| `corrupt.jpg` | Intentionally corrupted file header |
| `oversized.bin` | File exceeding the size limit |

---

## 4. CI/CD Integration

```yaml
# Suggested GitHub Actions pipeline
jobs:
  unit:          # TS-01, TS-02, TS-03, TS-16, TS-17
  integration:   # TS-04, TS-05, TS-06, TS-07, TS-08
  e2e:           # TS-09, TS-10, TS-11
  security:      # TS-14
  load:          # TS-13 (merge to main only)
```

| Metric | Target |
|--------|--------|
| Backend line coverage | ≥ 85% |
| Frontend line coverage | ≥ 80% |
| Critical E2E tests | 100% passing |
| Security scan | 0 HIGH/CRITICAL |
| TypeScript errors | 0 |
| p95 upload latency | < 500ms |
