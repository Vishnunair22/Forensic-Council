# Development Status

**Last updated:** 2026-03-05  
**Current version:** 0.8.0  
**Overall health:** 🟢 Production-Ready (Phase 2) — all agent stubs replaced, session expiry handled  
**Actively working on:** Phase 3 — LLM reasoning integration  
**Blocked on:** Nothing currently  

---

## Pipeline Health

Upload → [✅] → Evidence Store → [✅] → Agent Dispatch → [✅] → Council Arbiter → [✅] → Signing → [✅] → Report → [✅]

| Stage | Status | Notes |
|-------|--------|-------|
| Upload | ✅ | File validation, MIME type checking, size limits enforced |
| Evidence Store | ✅ | Immutable storage with SHA-256 integrity verification |
| Agent Dispatch | ✅ | Sequential execution working, concurrent optimization pending |
| Council Arbiter | ✅ | Signing complete, cross-modal correlation implemented |
| Signing | ✅ | ECDSA (P-256/SHA-256) signatures with deterministic key derivation |
| Report | ✅ | Multi-format rendering with custody chain verification |

---

## Component Status

### Agents (v0.8.0 — all stubs replaced)

| Agent | Implementation | Stubs Remaining | Notes |
|-------|----------------|-----------------|-------|
| Agent 1 — Image | ✅ Complete | **0** | ELA, GMM, PRNU, adversarial robustness all real |
| Agent 2 — Audio | ✅ Complete | **0** | librosa splice, adversarial spectral check |
| Agent 3 — Object | ✅ Complete | **0** | YOLO + CLIP secondary classification + adversarial |
| Agent 4 — Video | ✅ Complete | **0** | optical flow + adversarial robustness |
| Agent 5 — Metadata | ✅ Complete | **0** | EXIF/XMP + PHash provenance + device fingerprint |
| Council Arbiter | ✅ Complete | 0 | Signing + cross-modal correlation |

### Stub Replacement Summary (v0.8.0)

| Agent | Tool Replaced | Real Implementation |
|-------|--------------|---------------------|
| Agent 1 | `adversarial_robustness_check` | ELA perturbation stability (Gaussian noise, double JPEG, colour jitter) |
| Agent 1 | `sensor_db_query` | PRNU residual heuristics + EXIF make/model |
| Agent 2 | `adversarial_robustness_check` | Spectral perturbation stability (low-pass, noise injection, time-stretch) |
| Agent 3 | `secondary_classification` | CLIP ViT-B-32 zero-shot (shared singleton) |
| Agent 3 | `adversarial_robustness_check` | YOLO perturbation stability (blur, brightness, salt-and-pepper) |
| Agent 4 | `adversarial_robustness_check` | Optical flow perturbation stability (noise, brightness) |
| Agent 5 | `reverse_image_search` | PHash (16×16) comparison against local evidence store |
| Agent 5 | `device_fingerprint_db` | EXIF manufacturer signature rules + PRNU cross-validation |
| Agent 5 | `adversarial_robustness_check` | Metadata anomaly score perturbation stability |

### Frontend

| Page / Feature | Status | Notes |
|----------------|--------|-------|
| Landing page | ✅ Complete | 3D scene, Start Investigation CTA |
| Evidence upload | ✅ Complete | Drag-drop, file validation, preview |
| Live analysis view | ✅ Complete | Agent cards + WebSocket updates + HITL modal |
| Report page | ✅ Complete | Verdict badge, agent findings, signature verification |
| Error boundary | ✅ Complete | User-friendly fallback |
| HITL decision modal | ✅ Complete | APPROVE / REDIRECT / TERMINATE wired to backend |
| Session expiry handling | ✅ Complete | `/session-expired` page; API client redirects on auth failure |

---

## Known Issues

| # | Severity | Description | Workaround | Since |
|---|----------|-------------|------------|-------|
| 1 | 🟡 Medium | Redis memory can grow under heavy load despite TTL | `FLUSHDB` if OOM errors occur | v0.4 |
| 2 | 🟡 Medium | WebSocket subprocess timeouts occasionally fail to kill child processes | Restart `forensic_api` container | v0.5 |
| 3 | 🟢 Low | Agent 4 temporal analysis is frame-level only | Frame-level analysis only | v0.3 |
| 4 | 🟢 Low | PHash reverse search is local-only | TinEye API required for web provenance | v0.8 |

---

## New in v0.8.0

- All 9 agent stubs replaced with real implementations (see table above)
- `docker-compose.override.yml` added for development port bindings
- `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL` env vars added to Settings and docker-compose
- `HF_TOKEN` added to Settings (was env-only before)
- `/session-expired` page added; API client redirects on exhausted auth retries
- `Makefile` added at project root for common dev commands
- Stray root-level scripts moved to `backend/scripts/`
- `backend/.env.example` cleaned up (removed `DATABASE_URL` which is not used by the app)

---

## Maintenance Discipline

**Update this document before closing any task.**  
**Review Known Issues at the start of every session.**  
**When something is fixed, move it to ERROR_LOG.md immediately.**
