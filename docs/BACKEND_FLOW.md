# Backend Flow

## Backend Root

```text
apps/api
```

## Stack

- FastAPI
- Python 3.12
- Pydantic v2
- PostgreSQL
- Redis
- Qdrant
- Alembic
- Groq/Gemini clients
- Optional ML extras

---

## Backend Entry Point

**File:** `apps/api/api/main.py`

**Responsibilities:**

- create FastAPI app
- run lifespan startup/shutdown
- validate settings
- initialize persistence clients
- initialize monitoring
- validate production readiness
- configure CORS
- configure security headers
- register routers
- expose health endpoints

---

## Main Route Modules

- `apps/api/api/routes/auth.py`
- `apps/api/api/routes/investigation.py`
- `apps/api/api/routes/sessions.py`
- `apps/api/api/routes/hitl.py`
- `apps/api/api/routes/_websocket.py`
- `apps/api/api/routes/sse.py`
- `apps/api/api/routes/cases.py`
- `apps/api/api/routes/metrics.py`
- `apps/api/api/routes/webhooks.py`

---

## Main Investigation Flow

1. Frontend sends POST /api/v1/investigate.
2. Backend validates auth and request.
3. Backend validates case_id and investigator_id.
4. Backend validates file size.
5. Backend validates MIME type.
6. Backend verifies image integrity if applicable.
7. Backend computes evidence hash.
8. Backend stores uploaded evidence.
9. Backend creates a session.
10. Backend launches pipeline through queue or in-process task.
11. Backend returns session_id.
12. Frontend connects to WebSocket.
13. Pipeline emits live progress.
14. Specialist agents run initial analysis.
15. Pipeline may create HITL checkpoint.
16. User decision is submitted.
17. Pipeline resumes and may run deep analysis.
18. Arbiter combines findings.
19. Final report is generated and signed.
20. Report becomes available through session API.

---

## Investigation Intake

**Main file:** `apps/api/api/routes/investigation.py`

**Main route:** POST /api/v1/investigate

**Responsibilities:**

- validate request
- validate file
- validate MIME type
- validate image integrity where applicable
- generate or accept case/session metadata
- hash evidence
- store evidence
- create investigation session
- handle stale/duplicate sessions
- launch investigation job
- return session information

---

## Pipeline Execution

**Main files:**

- `apps/api/orchestration/pipeline.py`
- `apps/api/orchestration/pipeline_phases.py`
- `apps/api/orchestration/investigation_runner.py`

**Responsibilities:**

- create EvidenceArtifact
- initialize working memory
- select applicable agents
- run initial agent analysis
- broadcast live updates
- create HITL checkpoint if needed
- run deep analysis if approved/resumed
- run Arbiter
- persist final report
- broadcast completion

---

## Session Management

**Main file:** `apps/api/orchestration/session_manager.py`

**Session routes:** `apps/api/api/routes/sessions.py`

**Responsibilities:**

- track session status
- track checkpoints
- store/retrieve reports
- support session resume
- support quota fetch
- support report download/PDF endpoints

---

## Live Updates

### WebSocket route

**File:** `apps/api/api/routes/_websocket.py`

**Route:** WS /api/v1/sessions/{session_id}/live

### SSE route

**File:** `apps/api/api/routes/sse.py`

**Route:** GET /api/v1/sessions/{session_id}/progress

### Signal bus

**File:** `apps/api/orchestration/signal_bus.py`

**Responsibilities:**

- accept frontend live connection
- broadcast agent progress
- broadcast HITL checkpoint
- broadcast Arbiter progress
- broadcast report-ready events
- broadcast errors

---

## HITL Flow

**Main files:**

- `apps/api/api/routes/hitl.py`
- `apps/api/api/routes/sessions.py`
- `apps/api/orchestration/session_manager.py`

**Primary routes:**

- POST /api/v1/hitl/decision
- POST /api/v1/sessions/{session_id}/resume
- GET /api/v1/sessions/{session_id}/checkpoints

**Possible decision concepts:**

- approve
- redirect
- override
- terminate
- escalate

---

## Report Flow

**Main files:**

- `apps/api/agents/arbiter.py`
- `apps/api/agents/arbiter_verdict.py`
- `apps/api/agents/arbiter_narrative.py`
- `apps/api/core/signing.py`
- `apps/api/core/pdf_report_exporter.py`
- `apps/api/api/routes/sessions.py`

**Report routes:**

- GET /api/v1/sessions/{session_id}/report
- GET /api/v1/sessions/{session_id}/report/download
- GET /api/v1/sessions/{session_id}/report/pdf

**Responsibilities:**

- combine agent findings
- compute verdict
- generate narrative
- include confidence and uncertainty
- include custody metadata
- sign report
- export report

---

## Worker Mode

**Main files:**

- `apps/api/orchestration/investigation_queue.py`
- `apps/api/orchestration/worker.py`
- `apps/api/scripts/run_worker.py`

**Purpose:** Allow investigations to run outside the API process using Redis-backed queue semantics.

---

## Persistence Systems

### PostgreSQL

Used for structured persistent state.

**Important files:**

- `apps/api/core/persistence/postgres.py`
- `apps/api/alembic`

### Redis

Used for queues, session state, live update distribution, and/or transient coordination depending on config.

**Important files:**

- `apps/api/core/persistence/redis_client.py`
- `apps/api/orchestration/investigation_queue.py`

### Qdrant

Used for vector memory / forensic knowledge features.

**Important files:**

- `apps/api/core/persistence/qdrant_client.py`
- `apps/api/core/rag_forensic_knowledge.py`

### Evidence storage

**Important files:**

- `apps/api/core/persistence/evidence_store.py`
- `apps/api/storage/evidence/.gitkeep`

---

## Security-Critical Backend Systems

Do not bypass:

- `apps/api/core/auth.py`
- `apps/api/core/rate_limiting.py`
- `apps/api/core/quota_meter.py`
- `apps/api/core/custody_chain.py`
- `apps/api/core/custody_logger.py`
- `apps/api/core/signing.py`
- `apps/api/core/forensic_policy.py`
- `apps/api/core/mime_registry.py`

---

## Backend Verification Commands

```bash
cd apps/api
uv sync --extra dev --extra security --extra observability
uv run pytest
uv run python scripts/init_db.py
uv run python scripts/validate_ml_tools.py
uv run python scripts/verify_llm_keys.py
```

For ML-enabled local mode:

```bash
cd apps/api
uv sync --extra dev --extra security --extra observability --extra ml
uv run python scripts/model_pre_download.py --strict
```