# Forensic Council — Project Context

**Version:** v1.4.0 | **Audited:** 2026-04-12

---

## What This Project Does

Forensic Council is a **multi-agent AI forensic evidence analysis system**. Users upload digital media (images, audio, video), and five specialist AI agents independently analyze the file for signs of manipulation, deepfakery, metadata inconsistencies, and compositing artifacts. A Council Arbiter cross-references findings, escalates contradictions via Human-in-the-Loop (HITL), and produces a **cryptographically signed, tamper-evident forensic report** suitable for legal proceedings.

**Chain of custody:** Every step is ECDSA P-256 signed and stored immutably in PostgreSQL.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15, React 19, Tailwind 4, Framer Motion |
| Backend API | FastAPI, Pydantic v2, asyncpg |
| LLM Reasoning | Groq (Llama 3.3 70B primary), Gemini 2.5 Flash (vision, deep pass) |
| ML Models | YOLOv8, Wav2Vec2, CLIP, DeepFace, pyannote.audio, EasyOCR |
| Image Analysis | PIL, NumPy, SciPy, OpenCV, scikit-image |
| Audio Analysis | librosa, SpeechBrain, praat-parselmouth |
| Metadata | piexif, hachoir, exiftool |
| Cryptography | cryptography library (ECDSA P-256) |
| Databases | PostgreSQL 17 (custody chain), Redis 7 (cache/rate-limit), Qdrant (vector search) |
| Infra | Docker Compose v2+, Caddy 2 (auto TLS) |
| Testing | Pytest, Jest, Trivy |
| CI/CD | GitHub Actions |

---

## Repository Structure

```
d:/Forensic Council/
├── apps/api/
│   ├── agents/           # 5 specialist agents + arbiter
│   │   ├── base_agent.py        # Base class, self-reflection, memory
│   │   ├── agent1_image.py      # ELA, splice, PRNU, EXIF, frequency
│   │   ├── agent2_audio.py      # Diarization, deepfake, prosody, A/V sync
│   │   ├── agent3_object.py     # YOLOv8, lighting, context analysis
│   │   ├── agent4_video.py      # Temporal consistency, face-swap
│   │   ├── agent5_metadata.py   # EXIF, GPS, steganography, provenance
│   │   └── arbiter.py           # Deliberation, tribunal, report signing
│   ├── api/
│   │   ├── main.py              # App init, middleware, lifespan
│   │   ├── schemas.py           # Pydantic DTOs
│   │   └── routes/              # auth, investigation, sessions, hitl, metrics
│   ├── core/
│   │   ├── config.py            # Pydantic Settings, env var validation
│   │   ├── react_loop.py        # THOUGHT→ACTION→OBSERVATION engine + HITL
│   │   ├── llm_client.py        # Unified Groq/OpenAI/Anthropic client
│   │   ├── custody_logger.py    # Cryptographic custody chain (PostgreSQL)
│   │   ├── calibration.py       # Platt scaling confidence calibration
│   │   ├── working_memory.py    # Redis-backed task tracking
│   │   ├── episodic_memory.py   # Qdrant forensic signature storage
│   │   ├── inter_agent_bus.py   # Agent-to-agent communication
│   │   ├── tool_registry.py     # Dynamic tool discovery & execution
│   │   ├── signing.py           # ECDSA P-256 key gen & signing
│   │   ├── auth.py              # JWT, user model, password hashing
│   │   └── migrations.py        # DB schema initialization
│   ├── orchestration/
│   │   ├── pipeline.py          # End-to-end investigation orchestration
│   │   └── session_manager.py   # Session state, HITL checkpoints
│   ├── infra/
│   │   ├── postgres_client.py   # asyncpg pool
│   │   ├── redis_client.py      # Redis singleton
│   │   ├── qdrant_client.py     # Vector DB
│   │   └── evidence_store.py    # File storage, SHA-256 versioning
│   ├── tools/
│   │   ├── image_tools.py       # ELA, ROI, JPEG ghost, PRNU, CFA
│   │   ├── audio_tools.py       # Diarization, anti-spoofing, prosody
│   │   ├── metadata_tools.py    # EXIF, GPS, steganography, file structure
│   │   ├── video_tools.py       # Optical flow, rolling shutter
│   │   ├── ocr_tools.py         # EasyOCR text extraction
│   │   └── ml_tools/            # ELA anomaly, splicing, copy-move, deepfake freq, PRNU
│   └── reports/
│       └── report_renderer.py   # HTML/JSON serialization, signature verification
│
├── apps/web/src/
│   ├── app/                     # Next.js App Router
│   │   ├── page.tsx             # Landing page, file upload, agent showcase
│   │   ├── evidence/page.tsx    # Investigation progress, WebSocket stream
│   │   ├── result/page.tsx      # Report display, findings breakdown
│   │   └── layout.tsx, globals.css, error.tsx, not-found.tsx, session-expired/
│   ├── components/
│   │   ├── evidence/            # FileUploadSection, AgentProgressDisplay, HITLCheckpointModal
│   │   └── ui/                  # SurfaceCard, GlobalFooter, HistoryDrawer, PageTransition, GlassBackground
│   ├── hooks/                   # useForensicData, useSimulation, useSound
│   ├── lib/                     # api.ts (800 lines), schemas.ts, fmtTool.ts, verdict.ts, constants.ts
│   └── types/                   # index.ts (Report, AgentResult, etc.)
│
├── tests/                       # Pytest (unit, integration, security, connectivity, infra)
├── docs/                        # Docker configs, monitoring, runbooks
├── apps/api/tests/             # Backend-local pytest suite
└── .kilo/                       # Kilo agent config, plans
```

---

## The Five Agents

| Agent | Focus | Key Tools |
|-------|-------|-----------|
| **Agent1 (Image)** | Pixel-level tampering, splicing, anti-forensics evasion | ELA, JPEG ghost, frequency domain, PRNU, noise fingerprint, CFA, GAN detection, Gemini vision (deep) |
| **Agent2 (Audio)** | Deepfake voice, splice points, A/V sync, prosody | Speaker diarization (pyannote), anti-spoofing (ECAPA), praat prosody, codec fingerprinting |
| **Agent3 (Object)** | Scene context, lighting consistency, compositing | YOLOv8 detection, lighting consistency, scale validation, inter-agent calls to Agent1 |
| **Agent4 (Video)** | Temporal consistency, face-swap detection | Optical flow, rolling shutter, frame interpolation detection |
| **Agent5 (Metadata)** | EXIF, GPS-timestamp consistency, steganography, provenance | EXIF (pyexiftool), GPS-timezone validation, astronomical API, LSB/DCT steganography, C2PA |

---

## Two-Phase Investigation Pipeline

```
PHASE 1: Initial Analysis (~15-20s per agent, parallel)
  └─ Fast numpy/OpenCV tools only → broadcast to WebSocket → user sees results

[User decision: Accept (skip) or Request Deep Analysis]

PHASE 2: Deep Analysis (~2-5 min per agent, background)
  └─ Heavy ML models (Gemini, YOLOv8, Wav2Vec2)
  └─ Context injection: Agent1 Gemini results → Agents 3 & 5

→ Council Arbiter deliberation → signed report
```

---

## Investigation Data Flow

1. `POST /api/v1/investigate` — upload file, get `session_id`
2. WebSocket `/api/v1/sessions/{id}/live` — stream `AGENT_UPDATE`, `AGENT_COMPLETE`, `HITL_CHECKPOINT`, `PIPELINE_COMPLETE`
3. `POST /api/v1/sessions/{id}/resume` — submit phase decision (accept/deep)
4. `POST /api/v1/hitl/decision` — submit HITL decisions (APPROVE/REDIRECT/OVERRIDE/TERMINATE/ESCALATE)
5. `GET /api/v1/sessions/{id}/report` — fetch signed final report (202 if pending)

---

## API Surface

| Method | Path | Auth |
|--------|------|------|
| POST | `/api/v1/auth/login` | None |
| GET | `/api/v1/auth/me` | Bearer |
| POST | `/api/v1/auth/refresh` | Bearer |
| POST | `/api/v1/auth/logout` | Bearer |
| POST | `/api/v1/investigate` | Bearer |
| WS | `/api/v1/sessions/{id}/live` | Cookie |
| POST | `/api/v1/sessions/{id}/resume` | Bearer |
| GET | `/api/v1/sessions/{id}/report` | Bearer |
| GET | `/api/v1/sessions/{id}/arbiter-status` | Bearer |
| GET | `/api/v1/sessions/{id}/checkpoints` | Bearer |
| GET | `/api/v1/sessions/{id}/brief/{agent_id}` | Bearer |
| GET | `/api/v1/sessions` | Bearer |
| DELETE | `/api/v1/sessions/{id}` | Bearer |
| POST | `/api/v1/hitl/decision` | Bearer |
| GET | `/health` | None |
| GET | `/api/v1/metrics` | None |

---

## Key Data Models

### AgentFinding (react_loop.py)
```python
class AgentFinding(BaseModel):
    finding_id: uuid.UUID
    agent_id: str
    finding_type: str
    confidence_raw: float          # 0-1, pre-calibration
    calibrated_probability: float | None
    status: Literal["CONFIRMED", "CONTESTED", "INCONCLUSIVE", "INCOMPLETE"]
    robustness_caveat: bool
    reasoning_summary: str
    metadata: dict[str, Any]
```

### ForensicReport (arbiter.py)
```python
class ForensicReport(BaseModel):
    report_id: UUID
    session_id: UUID
    case_id: str
    executive_summary: str
    per_agent_findings: dict[str, list[dict]]
    per_agent_metrics: dict[str, Any]
    per_agent_analysis: dict[str, str]   # Groq-synthesized narratives
    overall_verdict: str                  # CERTAIN / LIKELY / UNCERTAIN / INCONCLUSIVE / MANIPULATION DETECTED
    cross_modal_confirmed: list[dict]
    contested_findings: list[dict]
    tribunal_resolved: list[TribunalCase]
    cryptographic_signature: str          # ECDSA P-256
    report_hash: str                      # SHA-256
    signed_utc: datetime
```

### ChainEntry (custody_logger.py)
```python
@dataclass
class ChainEntry:
    entry_id: UUID
    entry_type: EntryType    # THOUGHT, ACTION, OBSERVATION, TOOL_CALL, etc.
    agent_id: str
    session_id: UUID
    timestamp_utc: datetime
    content: dict[str, Any]
    content_hash: str        # SHA-256
    signature: str           # ECDSA P-256
    prior_entry_ref: str | None  # Linked list — ensures chain integrity
```

---

## ReAct Loop (core/react_loop.py)

Pattern: `THOUGHT → ACTION → OBSERVATION` (driven by Groq LLM or hardcoded task decomposition)

**HITL Checkpoints trigger at:**
- Iteration 50% of ceiling (early pause)
- Contested findings (agent contradictions)
- Severity threshold breach (CRITICAL findings)
- Tool unavailable
- Tribunal escalation

---

## Security Architecture

- **JWT:** 60-min expiry, HttpOnly cookies, sessionStorage fallback
- **Token blacklist:** Redis (on logout)
- **Rate limiting:** Auth: 5 failures/5-min → 15-min lockout; Investigations: 50/user/5-min
- **Signing key:** ECDSA P-256; dev placeholder fatal-errors in production
- **Insecure defaults blocked** in production (config.py validates at startup)
- **Headers:** CSP, HSTS, X-Frame-Options, Referrer-Policy, Permissions-Policy
- **CORS:** Restricted to configured origins

---

## Authentication Roles

| Role | Permissions |
|------|------------|
| `admin` | User management, system config |
| `investigator` | Upload evidence, review investigations, submit HITL decisions |

---

## Frontend Design System (v1.1.1)

- **Aesthetic:** Premium Indigo/Slate minimalist (transitioned from CyberNoir neon in v1.1.1)
- **Fonts:** Syne (display), JetBrains Mono (monospace)
- **Primary color:** Indigo-600 | Background: Slate-50/Slate-950
- **Borders:** Slate-200 (light) / Slate-800 (dark)
- **Agent badges:** Transparent background (not solid fills)
- **Key components:** SurfaceCard, GlobalFooter, HistoryDrawer, PageTransition, GlassBackground (new)

---

## Frontend State Management

**`useForensicData` hook** manages:
- Session history (SessionStorage)
- Current active report
- Analysis state (isAnalyzing, errors)
- File validation (MIME allowlist, 50MB max, safe case_id)

---

## Environment Variables (Key Ones)

| Variable | Purpose |
|----------|---------|
| `APP_ENV` | `development` / `production` |
| `SIGNING_KEY` | ECDSA seed — 32-char hex (fatal error if dev placeholder in prod) |
| `LLM_PROVIDER` | `groq` / `openai` / `anthropic` / `none` |
| `LLM_API_KEY` | Groq key from console.groq.com/keys |
| `LLM_MODEL` | `llama-3.3-70b-versatile` (Groq default) |
| `GEMINI_API_KEY` | Enables vision analysis (Agents 1, 3, 5 deep pass) |
| `GEMINI_MODEL` | `gemini-2.5-flash` (fallbacks: `gemini-2.0-flash`, `gemini-2.0-flash-lite`) |
| `BOOTSTRAP_ADMIN_PASSWORD` | Initial admin password (must set before prod deploy) |
| `NEXT_PUBLIC_API_URL` | Browser-reachable backend URL |
| `DOMAIN` | DNS domain for Caddy auto-TLS |

---

## Test Structure

```
tests/
├── apps/api/
│   ├── conftest.py                 # DB, Redis, config fixtures
│   ├── unit/core/                  # JWT, config, signing tests
│   ├── integration/                # API routes, e2e pipeline
│   └── security/                   # CSP headers, CORS, auth validation
├── connectivity/                   # Live stack tests (requires containers)
├── infra/test_infra_standards.py   # Infrastructure compliance
└── test_forensic_system.py         # System-level tests
```

Run: `pytest tests/ --ignore=tests/connectivity -v`

---

## Deployment (Quick Reference)

**Local dev:**
```bash
docker compose -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env up --build
# Frontend: http://localhost:3000  |  API: http://localhost:8000/docs
```

**Production:** Set `APP_ENV=production`, strong passwords, real `SIGNING_KEY`, `DOMAIN` for Caddy TLS.

ML models download on first run (~10-15 GB, 15-60 min). Subsequent starts use Docker named volume cache.


