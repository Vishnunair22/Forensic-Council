# Forensic OS (2026 Edition)

Upload digital evidence. Five specialized AI agents analyze it. Get a cryptographically signed forensic report verified by **Gemini 2.5 Pro/Flash Semantic Grounding**.

[![Version](https://img.shields.io/badge/version-v1.4.0-blue.svg)](#) [![Status](https://img.shields.io/badge/status-stable-green.svg)](#) [![License](https://img.shields.io/badge/license-MIT-green.svg)](#) [![Python](https://img.shields.io/badge/python-3.12-blue.svg)](#) [![Next.js](https://img.shields.io/badge/next.js-15-black.svg)](#)

*A High-Fidelity Multi-Agent Forensic OS with Multimodal Semantic Grounding via Gemini 2.0 SOTA*

---

## Documentation Index
- 🏗️ **[Architecture](docs/ARCHITECTURE.md)** — Hybrid pipeline, memory systems, and hardware requirements.
- 🔌 **[API Reference](docs/API.md)** — Authentication, investigation endpoints, and WebSocket events.
- 🤖 **[Agent Capabilities](docs/agent_capabilities.md)** — Definitive tool list for all 5 forensic agents.
- 🔐 **[Security Policy](docs/SECURITY.md)** — Cryptographic signing, chain-of-custody, and legal admissibility.
- 🛠️ **[Maintenance Guide](docs/MAINTENANCE.md)** — Cleanup services, log rotation, and ML tool warming.
- 🚀 **[Development Setup](docs/DEVELOPMENT_SETUP.md)** — Prerequisites and local environment configuration.

## Project Management
- 📊 **[Current State](docs/STATE.md)** — Active tasks, logic fixes, and sprint progress.
- 🗺️ **[Roadmap](docs/ROADMAP.md)** — Phase 5 goals and long-term vision.
- 📝 **[Project Overview](docs/PROJECT.md)** — Tech stack and forensic guardrails.
- 📜 **[Changelog](docs/CHANGELOG.md)** — Version history and audit logs.
- ⚖️ **[AI Context](docs/AI_ASSISTANT_CONTEXT.md)** — Specialized guidelines for AI pair programming.
---

## What it does

Forensic OS (2026 Edition) is a premium, modular platform for digital media verification. Five autonomous AI agents perform a tiered **Initial vs Deep Analysis** pipeline. 

1. **Initial Pass**: High-recall screening using classical ML (ELA, JPEG Ghost, SIFT, CLIP).
2. **Deep Pass**: High-precision investigation using 2026-era detectors (Diffusion Artifacts, Inter-frame Forgery, C2PA JUMBF).
3. **Semantic Grounding**: Suspicious findings are "grounded" via **Gemini 2.5 Vision**, which cross-verifies ML anomalies against the visual scene context to confirm editing artifacts or generative hallmarks.

Every step — from initial telemetry to the multimodal verdict — is recorded in a court-defensible ECDSA-signed ledger.

---

## Architecture

```
Frontend (Next.js 15) → FastAPI Backend → 5 2026 Agents → Council Arbiter → Signed Report
                                        ↳         ↳          ↳
                                     Redis    Postgres    Qdrant
```

**Infrastructure:**
- **Redis** — Working memory, task queue, and WebSocket pub/sub.
- **PostgreSQL 17** — Immutable Evidence Ledger (ACID).
- **Qdrant** — Vector storage for forensic pattern correlation.
- **Caddy 2** — Zero-config TLS/HTTPS.
- **ML Cache** — Dedicated Docker volumes for HuggingFace, Torch, and YOLO weights.

---

## The Agents (2026 Spec)

| Agent | Pass 1: Classical | Pass 2: 2026 Forensic | Semantic Grounding |
|-------|------------------|----------------------|--------------------|
| **Image** | ELA, Splicing | **Diffusion Artifacts** | ROI-aware Vision |
| **Audio** | Speaker Diarization | **Voice Synthesis Det.** | Contextual Intent |
| **Object** | YOLO Detection | **Scene Coherence** | Physical Consistency |
| **Video** | Frame consistency | **Inter-frame Forgery** | Temporal Flow |
| **Metadata** | EXIF/GPS | **C2PA JUMBF (2026)** | Hardware Provenance |

---

## Prerequisites

- Docker Desktop 23+ (BuildKit enabled)
- **Groq API key** (Arbiter/Reasoning) — [console.groq.com](https://console.groq.com/keys)
- **Google Gemini API key** (Vision/Grounding) — [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
- 15 GB disk for ML model volumes (downloads once, persists permanently)

---

## Configuration Reference

### Docker Volumes

| Volume Name | Purpose |
|-------------|---------|
| `fc_postgres_data` | PostgreSQL 17 database files |
| `fc_redis_data` | Redis working memory state |
| `fc_qdrant_data` | Qdrant vector store for episodic memory |
| `fc_evidence` | Uploaded evidence files |
| `fc_storage` | General application storage |
| `fc_ml_cache` | HuggingFace/Torch model cache |
| `fc_calibration_models` | Agent calibration models |
| `fc_numba_cache` | Numba JIT compilation cache |
| `fc_yolo_weights` | YOLOv8 object detection weights |
| `fc_clip_model` | CLIP vision-language model |
| `fc_transformers` | HuggingFace transformers cache |
| `fc_speechbrain` | SpeechBrain audio models |
| `fc_torch_cache` | PyTorch model cache |
| `fc_logs` | Application logs |
| `fc_caddy_data` | Caddy reverse proxy data |
| `fc_caddy_config` | Caddy configuration |

### Docker Networks

| Network | Purpose |
|---------|---------|
| `fc_internal` | Internal communication between services |
| `fc_frontend` | Frontend to backend communication |
| `fc_monitoring` | Monitoring and observability |

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `REDIS_URL` | Yes | Redis connection string |
| `QDRANT_URL` | Yes | Qdrant server URL |
| `GROQ_API_KEY` | Yes | Groq API for LLM synthesis |
| `GEMINI_API_KEY` | Yes | Google Gemini for vision analysis |
| `GEMINI_MODEL` | No | Gemini model version (default: gemini-2.5-flash) |
| `SECRET_KEY` | Yes | Application secret for signing |
| `LLM_PROVIDER` | No | LLM provider (default: groq) |
| `LLM_MODEL` | No | LLM model name |
| `LLM_ENABLE_REACT_REASONING` | No | Enable LLM reasoning in ReAct loop |
| `LLM_ENABLE_POST_SYNTHESIS` | No | Enable post-analysis LLM synthesis |
| `INTERNAL_API_URL` | No | Backend API URL for server-side |
| `NEXT_PUBLIC_API_URL` | No | Public API URL for frontend |
| `NEXT_PUBLIC_WS_URL` | No | WebSocket URL |

For production key generation, see `infra/generate_production_keys.sh`.

---

## Quick Start

```bash
# 1. Configure 2026 Standards
copy .env.example .env
# Edit .env: set GEMINI_MODEL=gemini-2.5-flash

# 2. Deploy
docker compose -f infra/docker-compose.yml --env-file .env up --build
```

---

## Changelog

**v1.4.0 (2026-04-14)** — Multi-Agent Tribunal Audit & Structural Hardening:
- **Orchestration**: Finalized the 5-Agent Tribunal sequentially (Project Orchestrator, Frontend Designer, Backend/AI, Testing/DevOps, Runner Up).
- **Backend/AI**: Hardened the 24-hour "Dead Man's Switch" (TTL) in WorkingMemory for GDPR/Privacy compliance.
- **Backend/AI**: Implemented high-fidelity SignalBus synchronization in the Council Arbiter to prevent premature report synthesis.
- **Frontend**: Standardized UI typography for forensic Title Case; implemented procedurally generated SVG grain for premium aesthetics.
- **Frontend**: Migrated investigation state from `sessionStorage` to `localStorage` for cross-tab persistence and crash recovery.
- **DevOps**: Hardened WebSocket connection logic for developer environment stability (localhost context-awareness).
- **Quality**: Verified 2026 SOTA model configuration (Gemini 2.0 Flash) across the entire monorepo.

**v1.3.0 (2026-04-09)** — Production Hardening & Structural Cleanup:
- **Bug fix**: Corrected `from infra.logging import get_logger` → `from core.structured_logging import get_logger` in `Agent2Audio` and `Agent4Video` (caused `ImportError` at runtime).
- **Bug fix**: Initialized `redis = None` before the try block in `hitl.py` to prevent `NameError` on Redis failure.
- **Infra**: Fixed `CALIBRATION_MODELS_PATH` in docker-compose — now correctly points to `/app/storage/calibration_models` (COPYd path) instead of the empty named volume.
- **Storage**: Merged all 8 agent calibration models into `apps/api/storage/calibration_models/` (deep agent models were missing). Removed redundant root-level `storage/` directory.
- **Cleanup**: Relocated `AGENTS.md` to `docs/` and version files to sub-folders. Purged all AI tool metadata (`.cursor`, `.claude`, `.agent`) from the root directory.
- **Configuration**: Synchronized `.env.example` with modern variables and optimized CI/CD workflow to use file-based versioning.
- **Frontend**: Removed redundant Google Fonts `@import url(...)` from `globals.css` (fonts loaded via `next/font/google` in `layout.tsx`).
- **Version**: Bumped `pyproject.toml`, `package.json`, and FastAPI app version to v1.3.0.

**v1.3.0 (2026-04-07)** — "Forensic OS" Modernization & Semantic Grounding:
- **Core**: Implemented the **Initial vs Deep Analysis** pipeline across all agents for tiered forensic screening.
- **ML Tools**: Integrated 2026-era detectors: `diffusion_artifact_detector`, `interframe_forgery_detector`, and `c2pa_validator` (JUMBF).
- **Grounding**: Developed **Semantic Grounding (Flag & Verify)** — Gemini 2.5 now cross-validates suspicious ML findings using ROI coordinates.
- **Infrastructure**: Optimized Docker caching layer; added dedicated volumes for `calibration_models` and `numba_cache`.
- **Cleanup**: Removed legacy `DevErrorOverlay.tsx` and development-only error providers for production hardening.
- **Standardization**: Updated default models to **Gemini 2.5 Pro Preview** in configuration and documentation.

**v1.2.2 (2026-04-07)** — "Forensic OS" 2026 Edition & Infrastructure Audit:
- **Models**: Native support for **Gemini 2.5 Pro** and **Gemini 2.5 Flash**.
- **UI/UX**: Premium high-fidelity dashboard redesign with glassmorphism and performance-optimized `AnimatedWave`.
- **A11y**: Standardized WCAG 2.1 AA compliance with refined ARIA landmarks.

---

[MIT License](LICENSE)

