# Forensic OS (2026 Edition)

Upload digital evidence. Five specialized AI agents analyze it. Get a cryptographically signed forensic report verified by Gemini 3.1 Semantic Grounding.

[![Version](https://img.shields.io/badge/version-v1.3.0-blue.svg)](#) [![Status](https://img.shields.io/badge/status-stable-green.svg)](#) [![License](https://img.shields.io/badge/license-MIT-green.svg)](#) [![Python](https://img.shields.io/badge/python-3.12-blue.svg)](#) [![Next.js](https://img.shields.io/badge/next.js-15-black.svg)](#) [![Postgres](https://img.shields.io/badge/postgres-17-blue.svg)](#)

*A High-Fidelity Multi-Agent Forensic OS with Multimodal Semantic Grounding*

---

## What it does

Forensic OS (2026 Edition) is a premium, modular platform for digital media verification. Five autonomous AI agents perform a tiered **Initial vs Deep Analysis** pipeline. 

1. **Initial Pass**: High-recall screening using classical ML (ELA, JPEG Ghost, SIFT, CLIP).
2. **Deep Pass**: High-precision investigation using 2026-era detectors (Diffusion Artifacts, Inter-frame Forgery, C2PA JUMBF).
3. **Semantic Grounding**: Suspicious findings are "grounded" via **Gemini 3.1 Vision**, which cross-verifies ML anomalies against the visual scene context to confirm editing artifacts or generative hallmarks.

Every step — from initial telemetry to the multimodal verdict — is recorded in a court-defensible ECDSA-signed ledger.

---

## Architecture

```
Frontend (Next.js 15) → FastAPI Backend → 5 2026 Agents → Council Arbiter → Signed Report
                                        ↕         ↕          ↕
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
- **Google Gemini API key** (Vision/Grounding) — [aistudio.google.com](https://aistudio.google.com/apikey)
- 15 GB disk for ML model volumes (downloads once, persists permanently)

---

## Quick Start

```bash
# 1. Configure 2026 Standards
cp .env.example .env
# Edit .env: set GEMINI_MODEL=gemini-1.5-pro

# 2. Deploy
docker compose -f infra/docker-compose.yml --env-file .env up --build
```

---

## Changelog

**v1.3.0 (2026-04-07)** — "Forensic OS" Modernization & Semantic Grounding:
- **Core**: Implemented the **Initial vs Deep Analysis** pipeline across all agents for tiered forensic screening.
- **ML Tools**: Integrated 2026-era detectors: `diffusion_artifact_detector`, `interframe_forgery_detector`, and `c2pa_validator` (JUMBF).
- **Grounding**: Developed **Semantic Grounding (Flag & Verify)** — Gemini 3.1 now cross-validates suspicious ML findings using ROI coordinates.
- **Infrastructure**: Optimized Docker caching layer; added dedicated volumes for `calibration_models` and `numba_cache`.
- **Cleanup**: Removed legacy `DevErrorOverlay.tsx` and development-only error providers for production hardening.
- **Standardization**: Updated default models to **Gemini 3.1 Pro Preview** in configuration and documentation.

**v1.2.2 (2026-04-07)** — "Forensic OS" 2026 Edition & Infrastructure Audit:
- **Models**: Native support for **Gemini 3.1 Pro** and **Gemini 2.5 Pro**.
- **UI/UX**: Premium high-fidelity dashboard redesign with glassmorphism and performance-optimized `AnimatedWave`.
- **A11y**: Standardized WCAG 2.1 AA compliance with refined ARIA landmarks.

---

[MIT License](LICENSE)
