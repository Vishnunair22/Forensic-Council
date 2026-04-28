# ML Models Documentation

This document covers model pinning, licensing, and caching for the Forensic Council system.

---

## Model Pinning

Pins specific commits/hashes for reproducibility.

| Category | Model | Version/Commit | Notes |
|----------|-------|----------------|-------|
| **Vision** | YOLO (Ultralytics) | `8.3.0` | Default: `yolo11n.pt` |
| **Vision** | OpenCLIP (SigLIP) | latest | `ViT-B-32` default |
| **Audio** | Vansh180 deepfake | `main` | Default: `Vansh180/deepfake-audio-wav2vec2` |
| **Audio** | AST Anti-Spoofing | - | Alternative: `MattyB95/AST-anti-spoofing` |
| **Object** | Grounding DINO | - | Alternative: `IDEA-Research/grounding-dino-tiny` |

---

## Model Licensing

> Last updated: 2026-04-25 | Status: v1.7.0

### Risk Summary

| Risk tier | Action required |
|-----------|-----------------|
| **AGPL-3.0** | Distribution of modified binaries requires source disclosure |
| **Research-only** | Cannot be used in commercial products without written permission |
| **Apache-2.0 / MIT** | No restrictions beyond attribution |

### Image Models

| Model | License | Risk |
|-------|---------|------|
| YOLO (Ultralytics) | **AGPL-3.0** | HIGH — requires source disclosure for SaaS |
| OpenCLIP (ViT-L-14) | **MIT** | None |
| TruFor (splicing) | **CC BY-NC 4.0** | MEDIUM — non-commercial |
| BusterNet, F3-Net | **Research-only** | HIGH — not cleared for production |

### Audio Models

| Model | License | Risk |
|-------|---------|------|
| MattyB95/AST-anti-spoofing | **Apache-2.0** | None |
| AASIST (opt-in) | **Research-only** | HIGH |
| pyannote diarization | **MIT** | LOW — requires HF acceptance |

### Language Models

| Provider | Model | License | Risk |
|----------|-------|---------|------|
| Google | Gemini 2.5 Flash | API ToS | Review data retention policy |
| Groq/Meta | Llama 3.3 70B | Meta Llama 3 | LOW under 700M MAU |

### Required Actions Before Production

- [ ] **Legal sign-off on AGPL** (YOLO) — confirm deployment doesn't constitute distribution
- [ ] **Remove research-only models** if commercial/forensic use
- [ ] **Confirm Gemini API data handling** compatible with evidence obligations
- [ ] **Accept pyannote terms** via HuggingFace account

---

## Model Caching Architecture

### Overview

The system uses persistent Docker volumes to cache ML models (~1.2 GB total) across container restarts.

### Cache Directories

| Directory | Contents | Size |
|-----------|----------|------|
| `/app/cache/huggingface/` | OpenCLIP, SpeechBrain | ~578 MB |
| `/app/cache/ultralytics/` | YOLO weights | ~6 MB |
| `/app/cache/easyocr/` | OCR models | ~200 MB |
| `/app/cache/torch/` | PyTorch hub | ~98 MB |
| `/app/cache/calibration_models/` | JSON calibration files | ~1.5 MB |

### First Run vs Subsequent Runs

**First Run (5-10 min download):**
- Entrypoint seeds calibration models
- `model_pre_download.py` runs in background
- API starts in ~30s (during download)
- First investigation: 30-60s cold start

**Subsequent Runs (30-60s):**
- Cache detected, download skipped
- Models loaded from cache into memory
- First investigation: <5s

### Monitoring

```bash
# Check warm-up status
curl http://localhost:8000/api/v1/health/ml-tools

# Check cache size
docker exec forensic_api du -sh /app/cache/*
```

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `HF_HOME` | `/app/cache/huggingface` | HuggingFace cache |
| `YOLO_CONFIG_DIR` | `/app/cache/ultralytics` | YOLO weights |
| `TORCH_HOME` | `/app/cache/torch` | PyTorch hub |
| `SKIP_MODEL_DOWNLOAD` | `0` | Skip pre-download |

---

## Troubleshooting

### Models Not Downloading

```bash
docker exec forensic_api ps aux | grep model_pre_download
docker exec forensic_api cat /tmp/model_download.log
```

### Cache Detection Failing

```bash
docker exec forensic_api find /app/cache/huggingface/hub -type d -name "models--*"
docker exec forensic_api find /app/cache/ultralytics -name "*.pt"
```

### Warm-Up Taking Too Long

```bash
curl http://localhost:8000/api/v1/health/ml-tools
docker compose restart backend
```