# Forensic Council — AI Context Reference
<!-- This file is intended for AI agents to quickly understand the project architecture and common failure points. -->

## 1. High-Level Architecture
The **Forensic Council** is a multi-agent system for forensic evidence analysis. It uses a coordinator-agent pattern where a central pipeline orchestrates specialist agents and an arbiter synthesises the final verdict.

- **Frontend**: Next.js 15 (Standalone mode), Tailwind CSS, Framer Motion.
- **Backend API**: FastAPI, asynchronous orchestration.
- **Storage**: PostgreSQL (Reports/Custody), Redis (Pub/Sub & Working Memory), Qdrant (Episodic Memory & Case Linking).
- **ML/AI**: Groq (Llama 3.3 70B for reasoning), Google Gemini 1.5 Flash (Vision deep-pass).

## 2. Core Components & File Map

### Orchestration Layer
- `backend/api/routes/investigation.py`: Core API entry point. Instruments the pipeline with WebSocket broadcasts and handles the two-phase (initial/deep) pass.
- `backend/orchestration/pipeline.py`: Pure orchestration logic. Manages AgentFactory and Arbiter coordination.
- `backend/agents/arbiter.py`: synthesises all agent findings into a signed `ForensicReport`.

### Specialist Agents (`backend/agents/`)
- `Agent1`: Image Integrity (ELA, Ghosting, Noise, Gemini Vision).
- `Agent2`: Audio Forensics (Diarization, Prosody, Spoofing, AV sync).
- `Agent3`: Object/Weapon Detection (YOLO, CLIP, Gemini Vision).
- `Agent4`: Video Analysis (Codec profiling, frame-rate consistency).
- `Agent5`: Metadata & Provenance (EXIF, GPS, C2PA, Steganography).

### Infrastructure (`backend/infra/`)
- `postgres_client.py`, `redis_client.py`, `qdrant_client.py`: Singleton connection pools.
- `evidence_store.py`: Handles file ingestion and hashing (SHA-256).

## 3. Data Flow (Lifecycle of an Investigation)
1. **Upload**: User uploads file via `frontend`.
2. **Ingestion**: Backend hashes the file, stores it, and creates an `EvidenceArtifact`.
3. **Phase 1 (Initial)**: All 5 agents run concurrently. They perform fast static analysis and tool-based checks.
4. **Pause**: Pipeline broadcasts `PIPELINE_PAUSED`. User decides between "Accept Analysis" or "Deep Analysis".
5. **Phase 2 (Deep)**: (Optional) Agents run heavy ML passes (Gemini Vision, spectral analysis). Agent 1 findings are injected into Agent 3/5 for cross-validation.
6. **Deliberation**: `CouncilArbiter` receives all findings and uses Groq to synthesise a narrative report.
7. **Persistence**: The report is signed cryptographically and saved to PostgreSQL.

## 4. Common Failure Points & Debugging

### WebSocket Connection
- **Issue**: Client misses early broadcasts.
- **Fix**: The frontend waits for a `{"type": "CONNECTED"}` response from the backend BEFORE resolving the `connected` promise. The backend waits up to 5s for this registration.

### ML Model Cache
- **Issue**: Models re-downloading on every restart.
- **Fix**: Ensure `docker-compose.yml` volumes (`hf_cache`, `torch_cache`) are correctly mounted. Do NOT run `docker compose down -v`.

### Agent Errors
- **AttributeError: '_custody_logger'**: Fixed. Ensure every agent `__init__` calls `super().__init__`.
- **403 Forbidden**: Usually means JWT token expired. Frontend handles this via `/session-expired` redirect.
- **500 Internal Error**: Check `docker compose logs -f backend`. Common causes: Database connection timeout or Groq API rate limits.

## 5. Deployment & Build
- **Local Dev**: Use `./manage.ps1 start` (Windows) or `docker compose up`.
- **Production Build**: Uses `production` target in `backend/Dockerfile` and `runner` in `frontend/Dockerfile`.
- **Caddy**: Acts as the entry point, handling TLS and API rewrites to avoid CORS.

## 6. Testing (Modernized)
- **Infrastructure**: `pytest tests/infra/` — Validates Docker security, env consistency, and project standards.
- **Backend E2E**: `pytest tests/backend/integration/` — Logic-first pipeline orchestration tests.
- **Accessibility**: `npm test -- tests/accessibility/` — WCAG 2.1 AA compliance (ARIA, keyboard, text-based states).
- **External APIs**: Verified via `gemini-flash-latest` (Gemini) and `groq` (LLM).

## 7. Configuration Notes
- **Gemini**: Key provided requires `gemini-flash-latest` or `gemini-2.0-flash` (if quota allows). Defaulted to `flash-latest` in `.env`.
- **Groq**: Primary reasoning engine. Ensure `.env` has a valid `gsk_...` key.
