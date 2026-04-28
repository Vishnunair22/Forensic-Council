# Model Licensing Matrix

Last updated: 2026-04-25
Status: v1.7.0

This document lists every ML weight loaded by Forensic Council, its license, and any restrictions
that affect commercial use, distribution, or forensic/expert-witness deployment.

---

## Summary

| Risk tier | Action required |
|-----------|-----------------|
| **AGPL-3.0** | Distribution of modified binaries requires source disclosure; confirm legal review for SaaS deployment |
| **Research-only** | Cannot be used in commercial products without written permission from the author/organization |
| **Apache-2.0 / MIT** | No restrictions beyond attribution; safe for commercial and forensic use |

---

## Image Models

### YOLO (Ultralytics)

| Property | Value |
|----------|-------|
| Model | `yolo11n.pt` (default) / `yolo11m.pt` (high-precision) |
| Source | `ultralytics/assets` via Ultralytics Hub |
| License | **AGPL-3.0** |
| Config key | `YOLO_MODEL_NAME` |
| Risk | **HIGH** — AGPL requires any derivative SaaS to open-source the application |
| Mitigation | Replace with `facebook/detr-resnet-50` (Apache-2.0) for permissive deployments; set `YOLO_MODEL_NAME=detr-resnet-50` |

### OpenCLIP (vision-language embeddings)

| Property | Value |
|----------|-------|
| Model | `ViT-B-32` (default) / `ViT-L-14` (opt-in high-precision) |
| Source | `mlfoundations/open_clip` |
| License | **MIT** |
| Config key | `SIGLIP_MODEL_NAME` |
| Risk | None — permissive |

### TruFor (splicing detection)

| Property | Value |
|----------|-------|
| Source | `grip-unina/TruFor` |
| License | **CC BY-NC 4.0 (Non-Commercial)** |
| Risk | **MEDIUM** — non-commercial; requires license for forensic-for-hire use |

### BusterNet (copy-move detection)

| Property | Value |
|----------|-------|
| Source | Research checkpoint; hosted internally |
| License | **Research-only** |
| Risk | **HIGH** — not cleared for commercial or legal-production use without permission |

### F3-Net (frequency-domain forgery)

| Property | Value |
|----------|-------|
| Source | Research checkpoint |
| License | **Research-only** |
| Risk | **HIGH** — same as BusterNet |

### ManTra-Net (anomaly tracing)

| Property | Value |
|----------|-------|
| Source | Research checkpoint |
| License | **Research-only** |
| Risk | **HIGH** |

### SwinV2 / ViT-based classifiers (optional)

| Property | Value |
|----------|-------|
| Model | `microsoft/swinv2-tiny-patch4-window8-256` |
| License | **MIT** |
| Risk | None |

---

## Audio Models

### AST Anti-Spoofing (primary)

| Property | Value |
|----------|-------|
| Model | `MattyB95/AST-anti-spoofing` |
| Source | HuggingFace Hub |
| License | **Apache-2.0** |
| Config key | `AASIST_MODEL_NAME` (default) |
| Risk | None — permissive |

### AASIST (opt-in fallback)

| Property | Value |
|----------|-------|
| Model | `clovaai/AASIST` |
| Source | HuggingFace Hub |
| License | **Research-only** (CLOVA AI proprietary) |
| Config key | Set `AASIST_MODEL_NAME=clovaai/AASIST` to enable |
| Risk | **HIGH** — research-only; not licensed for commercial forensic use |
| Mitigation | Default is now `MattyB95/AST-anti-spoofing`; AASIST is opt-in only |

### pyannote Speaker Diarization

| Property | Value |
|----------|-------|
| Model | `pyannote/speaker-diarization-3.1` |
| License | **MIT** (model weights) + HuggingFace user agreement |
| Risk | **LOW** — requires HF account acceptance of pyannote terms |

---

## Language / Multimodal Models

### Gemini (Google)

| Property | Value |
|----------|-------|
| Model | `gemini-2.5-flash`, `gemini-2.0-flash` (cascade) |
| Source | Google AI Studio API |
| License | **Google API Terms of Service** |
| Config key | `GEMINI_API_KEY`, `GEMINI_MODEL` |
| Risk | API ToS — review data retention and confidentiality clauses before submitting sensitive evidence |

### Groq / Llama (LLM reasoning)

| Property | Value |
|----------|-------|
| Model | `llama-3.3-70b-versatile` (via Groq) |
| License | **Meta Llama 3 Community License** (permissive above 700M MAU) |
| Config key | `LLM_API_KEY`, `LLM_MODEL` |
| Risk | **LOW** for deployments under Meta's 700M MAU threshold |

---

## Required Actions Before Production

- [ ] **Legal sign-off on AGPL exposure** from YOLO (Ultralytics). Confirm whether your deployment constitutes "distribution" under AGPL-3.0, or replace with DETR (Apache-2.0).
- [ ] **Remove or gate research-only models** (TruFor CC-NC, BusterNet, F3-Net, ManTra-Net) if the deployment is commercial or expert-witness grade. These weights must not be included in a court-submitted analysis without license clearance.
- [ ] **Confirm Gemini API data handling** policy is compatible with your evidence handling obligations (e.g., GDPR, chain of custody).
- [ ] **Pyannote acceptance**: Ensure all deployment environments have accepted the pyannote HuggingFace model agreement via a logged-in HF token.

---

## Revision History

| Date | Change |
|------|--------|
| 2026-04-25 | Initial matrix created (v1.7.0) |
| 2026-04-25 | Default AASIST → MattyB95/AST-anti-spoofing (Apache-2.0); CLIP ViT-L-14 → ViT-B-32 |
