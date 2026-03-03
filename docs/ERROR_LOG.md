# Forensic Council — Error Log & Resolution Audit

**Date:** 2026-03-02
**Status:** All Critical/High Infrastructure Issues Resolved

This log tracks significant errors, architectural flaws, and their subsequent resolutions.

## 🏁 Full Infrastructure Audit — March 02, 2026

The following 10 issues were identified and resolved to stabilize the Docker-based deployment and improve build efficiency.

| ID | Issue | Severity | Status | Resolution Summary |
|:---|:---|:---:|:---:|:---|
| 1 | Docker Build Speed (uv Cache) | 🔴 Critical | **RESOLVED** | Implemented multi-stage build with official `uv` binary and cache mounts for `/root/.cache/uv`. |
| 2 | Frontend Connectivity | 🔴 Critical | **RESOLVED** | Updated `NEXT_PUBLIC_API_URL` to `localhost:8000` for client-side resolution. |
| 3 | DB Driver Scheme | 🔴 Critical | **RESOLVED** | Updated to `postgresql+asyncpg://` and renamed config property to `sqlalchemy_async_database_url`. |
| 4 | `uv run` Startup Overhead | 🟠 High | **RESOLVED** | Set `ENV PATH` to `.venv/bin` and changed `CMD` to run python directly. |
| 5 | Non-Reproducible Qdrant Image | 🟠 High | **RESOLVED** | Pinned `qdrant/qdrant` to version `v1.9.2`. |
| 6 | Missing Backend Healthcheck | 🟠 High | **RESOLVED** | Added `healthcheck` to `backend` service and `service_healthy` condition to `frontend`. |
| 7 | Docker Compose File Location | 🟠 High | **RESOLVED** | Moved `docker-compose.yml` to project root and updated all relative build contexts. |
| 8 | Build Bloat (gcc in Prod) | 🟡 Medium | **RESOLVED** | Multi-stage build now discards `gcc` and build tools after the builder stage. |
| 9 | Insecure `SIGNING_KEY` Default | 🟡 Medium | **RESOLVED** | Removed inline fallback; set to empty in `.env.example` with generation instructions. |
| 10 | Frontend Runtime Override | 🟡 Medium | **RESOLVED** | Implemented `env` mapping in `next.config.ts` for runtime configurability. |

---

## 🛠️ Security & Reliability Hardening — March 02, 2026

Following the initial audit, the system underwent deep hardening to address remaining session and memory issues.

| ID | Issue | Severity | Status | Resolution Summary |
|:---|:---|:---:|:---:|:---|
| 11 | Agent Key Persistence (SEC 1) | 🔴 Critical | **RESOLVED** | Keys are now derived deterministically from `SIGNING_KEY` via HMAC-SHA256. |
| 12 | Redis Memory Leaks (HIGH 1) | 🟠 High | **RESOLVED** | Added 24-hour TTL (`ex=86400`) to all working memory keys. |
| 13 | Upload Rate Limiting (SEC 2) | 🔴 Critical | **RESOLVED** | Implemented Redis-based sliding window (5 uploads/10min per investigator). |
| 14 | Input Validation (SEC 3) | 🟠 High | **RESOLVED** | Added regex validation for `case_id` and `investigator_id` in API routes. |
| 15 | Concurrent Agent Execution (BUG 7) | 🟠 High | **RESOLVED** | Refactored pipeline execution to run agents sequentially for frontend UX stability. |

---

## 🧩 Application Logic & Frontend Fixes — March 02, 2026

| ID | Issue | Severity | Status | Resolution Summary |
|:---|:---|:---:|:---:|:---|
| 16 | Missing `addReportToHistory` | 🔴 Critical | **RESOLVED** | Fixed `useForensicData` hook destructuring in `page.tsx` to use correct function names. |
| 17 | Broken Logging Interception | 🔴 Critical | **RESOLVED** | Refactored monkey-patching in `investigation.py` to use keyword arguments for reliability. |
| 18 | `EntryType` Enum Typo | 🔴 Critical | **RESOLVED** | Fixed `THought` -> `THOUGHT` typo in `custody_logger.py`. |
| 19 | Missing `case_id` in Response | 🔴 Critical | **RESOLVED** | Updated `api.ts` types and returned full `InvestigationResponse` to frontend. |
| 20 | Inconsistent File Limits | 🟠 High | **RESOLVED** | Aligned frontend and backend max file size to 50MB. |
| 21 | Random Investigator IDs | 🟡 Medium | **RESOLVED** | Persisted generated `investigatorId` to `sessionStorage` for consistency. |

---

## Historical Logs

### [2026-03-03] - Custody Logger NoneType Error - COMPREHENSIVE FIX

#### Issue: `'NoneType' object has no attribute 'log_entry'`
- **Error:** Backend crashes during investigation with `'NoneType' object has no attribute 'log_entry'`
- **Affected Operations:**
  - File upload and investigation pipeline startup
  - HITL decision resolution
  - Report finalization and signing
  - All agent operations requiring custody logging
  - Evidence store operations
  - Inter-agent bus communication
  - Tool registry execution
  - ReAct loop execution
- **Root Cause:** Race condition when infrastructure (Qdrant/PostgreSQL) fails to initialize:
  1. **Infrastructure startup failure:** When Qdrant/PostgreSQL are unavailable, `custody_logger` remains `None`
  2. **Incomplete null guards:** Only `pipeline.py` had null guards added in initial fix; 6 other files were still calling `log_entry()` without checking if `custody_logger` was `None`
- **Comprehensive Resolution:**
  1. Added null checks (`if custody_logger:`) before ALL `custody_logger.log_entry()` calls across the codebase
  2. This enables graceful degradation - the investigation pipeline continues even if custody logging is unavailable
- **Fix Locations (18 total call sites fixed):**
  - `backend/agents/base_agent.py` (7 locations): Session start, tool availability, self-reflection, episodic memory read/write, HITL checkpoint, inter-agent calls
  - `backend/core/react_loop.py` (3 locations): HITL checkpoint, human intervention, ReAct step logging
  - `backend/infra/evidence_store.py` (2 locations): Artifact ingestion, derivative creation
  - `backend/core/inter_agent_bus.py` (2 locations): Outgoing/incoming inter-agent call logging
  - `backend/core/tool_registry.py` (3 locations): Tool unavailable (not found), tool unavailable (marked), tool execution
  - `backend/api/routes/investigation.py` (1 location): Logger instrumentation hook

### [2026-03-03] - Custody Logger NoneType Error & Qdrant Healthcheck (Initial Fix)

#### Issue: `'NoneType' object has no attribute 'log_entry'`
- **Error:** Backend crashes during investigation with `'NoneType' object has no attribute 'log_entry'`
- **Root Cause:**
  1. **Qdrant startup race condition:** The backend service starts before Qdrant is fully ready
  2. **Missing null guards:** The pipeline code called `await self.custody_logger.log_entry()` without checking if `custody_logger` was initialized
- **Initial Resolution:**
  1. Added proper healthcheck to Qdrant service in docker-compose.yml
  2. Changed backend `depends_on` from `service_started` to `service_healthy` for Qdrant
  3. Added null checks in pipeline.py
- **Note:** This was an incomplete fix. See "COMPREHENSIVE FIX" entry above for the full resolution covering all 17 call sites.

### [2026-03-03] - Qdrant Query API Version Incompatibility

#### Issue: Qdrant query_points API 404 Error
- **Error:** `UnexpectedResponse: Unexpected Response: 404 (Not Found)` when calling `query_points()`
- **Affected Tests:**
  - `tests/test_infra/test_qdrant.py::test_upsert_and_query`
  - `tests/test_infra/test_qdrant.py::test_batch_upsert`
  - `tests/test_infra/test_qdrant.py::test_query_with_filter`
  - `tests/test_core/test_episodic_memory.py` (6 query-related tests)
- **Root Cause:** Qdrant server v1.9.2 does not support the `query_points` API which was introduced in v1.10.0. The client v1.17.0 uses this API by default for vector similarity search.
- **Resolution:** Upgraded Qdrant server from v1.9.2 to v1.11.0 in `docker-compose.yml`. Also added `check_compatibility=False` to the client initialization to suppress version mismatch warnings.
- **Fix Locations:**
  - `docker-compose.yml` line 17: Changed image to `qdrant/qdrant:v1.11.0`
  - `backend/infra/qdrant_client.py` line 92: Added `check_compatibility=False` parameter

### [2026-03-03] - Test Suite Fixes - Config & Signing

#### Issue 1: Config.py DEBUG validation error
- **Error:** `debug Input should be a valid boolean, unable to interpret input [type=bool_parsing, input_value='release']`
- **Root Cause:** System environment variable `DEBUG=release` was not recognized as a valid boolean value.
- **Resolution:** Added `parse_debug` field validator in `core/config.py` to handle string representations like 'true', 'false', '1', '0', 'yes', 'no', 'on', 'off', and 'release'.
- **Fix Location:** `backend/core/config.py` lines 36-44

#### Issue 2: Signing.py cryptography API incompatibility
- **Error:** `AttributeError: 'SECP256R1' object has no attribute 'order'`
- **Root Cause:** In newer versions of cryptography library (46+), the curve object no longer exposes the `order` attribute directly.
- **Resolution:** Changed the key derivation logic to use `curve.key_size` to compute the order (`1 << curve.key_size`) instead of accessing the deprecated `order` attribute.
- **Fix Location:** `backend/core/signing.py` lines 84-96

### [2026-03-02] - Next.js Build Failure
- **Error:** Missing module '@types/node' or 'process' reference in specialized config.
- **Root Cause:** Environment variable handling in TypeScript without full Node types installed in dev container.
- **Resolution:** Updated `next.config.ts` with standard `env` field providing safe fallbacks.

### [2026-03-01] - ML Subprocess Memory Leak
- **Error:** API unresponsive after 10+ concurrent scans.
- **Root Cause:** ML logic was heavily coupled to the FastAPI event loop.
- **Resolution:** Decoupled into `ml_subprocess.py` standalone scripts with strict timeout controls.

### [2026-03-03] - Frontend 401 Unauthorized Error on Investigation

#### Issue: `/api/v1/investigate` returning 401 Unauthorized
- **Error:** `Failed to load resource: the server responded with a status of 401 (Unauthorized)` / `Error: Not authenticated`
- **Affected Operations:**
  - Starting forensic investigation via `startInvestigation()`
  - All subsequent API calls that require authentication
- **Root Cause:** The backend `/api/v1/investigate` endpoint requires JWT authentication (`current_user: User = Depends(get_current_user)`), but the frontend was not including an `Authorization` header with a valid JWT token in API requests.
- **Resolution:**
  1. Added token management functions (`getAuthToken`, `setAuthToken`, `clearAuthToken`) to store JWT in localStorage
  2. Added authentication functions (`login`, `autoLoginAsInvestigator`, `ensureAuthenticated`) to handle authentication flow
  3. Updated all API functions (`startInvestigation`, `getReport`, `getBrief`, `getCheckpoints`, `submitHITLDecision`) to include `Authorization: Bearer <token>` header
  4. Updated `createLiveSocket` to include token as query parameter for WebSocket authentication
  5. Implemented auto-login as demo investigator when no token exists, enabling seamless UX for demo environment
- **Fix Location:** `frontend/src/lib/api.ts` - Complete rewrite with authentication support

---

## 🏗️ Production Readiness & Architecture Fixes — March 02, 2026 

Following a comprehensive Tier 1/2/3 audit, these final issues preventing a stable Docker deployment and operational workflow were resolved.

| ID | Issue | Severity | Status | Resolution Summary |
|:---|:---|:---:|:---:|:---|
| 22 | HITL `HumanDecision` Schema Crash | 🔴 Critical | **RESOLVED** | Renamed `decision` -> `decision_type` and `note` -> `notes` to fix `ValidationError` on every HITL dispatch. |
| 23 | Pipeline Checkpoint Resolver Crash | 🔴 Critical | **RESOLVED** | Fixed attribute access errors `.decision.value` -> `.decision_type.value` and `.modified_content` -> `.override_finding` in `handle_hitl_decision`. |
| 24 | TRIBUNAL Enum Desync | 🔴 Critical | **RESOLVED** | Aligned legacy `TRIBUNAL` strings to unified `ESCALATE` constant across frontend app, api layers, and backend schemas. |
| 25 | Result Page Deadlock | 🔴 Critical | **RESOLVED** | Removed invalid `caseId` strict dependency from `getReport` dispatch. Reports now load correctly using just the valid `sessionId`. |
| 26 | Backend Database Initialization | 🔴 Critical | **RESOLVED** | Hardwired `init_database()` safely into the `main.py` app `lifespan` handler. Deployments no longer crash when schema is missing. |
| 27 | Compose Port Collision | 🟠 High | **RESOLVED** | Migrated `docker-compose.yml` frontend map natively to `"3001:3000"` preventing local development server blocks. |
| 28 | CORS Origin Blocks | 🟠 High | **RESOLVED** | Injected `CORS_ALLOWED_ORIGINS=["http://localhost:3001","http://localhost:3000"]` securely within the docker-compose environment vars. |
| 29 | submitHITLDecision Argument Layout | 🔴 Critical | **RESOLVED** | Replaced 4 positional string arguments with a single dictionary object aligning with the frontend hook signature. |
