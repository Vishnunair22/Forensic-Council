# ML Models Documentation

This document covers model pinning, licensing, and caching for the Forensic Council system.

> **Note:** This document supersedes `MODEL_LICENSING.md`. All licensing information is now consolidated here.

---

## Model Pinning

Pins specific commits/hashes for reproducibility.

| Category | Model | Version/Commit | Notes |
|----------|-------|----------------|-------|
| **Vision** | DETR object detector | `facebook/detr-resnet-50` | Default object detector; Apache-2.0 |
| **Vision** | YOLO (Ultralytics) | `8.3.x` | Optional: `yolo11n.pt` when `ENABLE_AGPL_MODELS=true` |
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
| DETR (`facebook/detr-resnet-50`) | **Apache-2.0** | None |
| YOLO (Ultralytics, opt-in) | **AGPL-3.0** | HIGH — requires source disclosure for SaaS |
| OpenCLIP (ViT-L-14) | **MIT** | None |
| TruFor (splicing) | **CC BY-NC 4.0** | MEDIUM — non-commercial |
| BusterNet, F3-Net | **Research-only** | HIGH — not cleared for production |

### Audio Models

| Model | License | Risk |
|-------|---------|------|
| Vansh180/deepfake-audio-wav2vec2 | **Apache-2.0** | None |
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

The system uses persistent Docker volumes to cache ML models across container
restarts. Docker builds can also bake a seed cache into the backend/worker
image with `PRELOAD_MODELS=1`; the entrypoint copies that seed into empty named
volumes on first start.

### Cache Directories

| Directory | Contents | Size |
|-----------|----------|------|
| `/app/cache/huggingface/` | OpenCLIP/SigLIP, SpeechBrain, audio deepfake, DETR | several GB |
| `/app/cache/ultralytics/` | YOLO weights when AGPL mode is enabled | ~6 MB |
| `/app/cache/easyocr/` | OCR models | ~200 MB |
| `/app/cache/torch/` | PyTorch hub | ~98 MB |
| `/app/cache/calibration_models/` | JSON calibration files | ~1.5 MB |

### First Run vs Subsequent Runs

**First Run (5-20 min download if image seed is absent):**
- Entrypoint seeds calibration models
- `model_pre_download.py --strict` runs before the API/worker accepts traffic unless `SKIP_MODEL_DOWNLOAD=1`
- Named volumes are populated and reused by later rebuilds

**Subsequent Runs (30-60s):**
- Cache detected, download skipped
- Models loaded from cache into memory
- First investigation: <5s

### Monitoring

```bash
# Check warm-up status
curl http://localhost:8000/api/v1/health/ml-tools

# Strict cache and per-model verification
docker exec forensic_api python scripts/model_cache_check.py --strict
docker exec forensic_api python scripts/model_pre_download.py --check --strict

# Check cache size
docker exec forensic_api du -sh /app/cache/*
```

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `HF_HOME` | `/app/cache/huggingface` | HuggingFace cache |
| `YOLO_CONFIG_DIR` | `/app/cache/ultralytics` | YOLO weights |
| `TORCH_HOME` | `/app/cache/torch` | PyTorch hub |
| `PRELOAD_MODELS` | `1` | Bake model seed cache into Docker images at build time |
| `SKIP_MODEL_DOWNLOAD` | `0` | Set to `1` only for CI/offline smoke builds |

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

---

## Feature Flags — AGPL and Research Models

The following table documents which models are gated by each feature flag.
Both flags default to `false` (commercial-safe). Never enable `ENABLE_RESEARCH_MODELS`
in production — `infra/validate_production_readiness.sh` asserts this.
(P3-DOCS-001 fix, audit v6→v7)

| Flag | Default | Models enabled when `true` | Production allowed? |
|------|---------|---------------------------|---------------------|
| `ENABLE_AGPL_MODELS` | `false` | Ultralytics YOLO (`yolo11n.pt`) — AGPL-3.0 | Yes, if open-source distribution obligations are met |
| `ENABLE_RESEARCH_MODELS` | `false` | BusterNet, F3-Net, ManTra-Net, TruFor (CC BY-NC), AASIST (research-only) | **No** — non-commercial/research licences only |

### Production assertion

`infra/validate_production_readiness.sh` includes:

```bash
[ "${ENABLE_RESEARCH_MODELS}" = "false" ] || { echo "FAIL: ENABLE_RESEARCH_MODELS must be false in production"; exit 1; }
```

This prevents accidentally shipping research-only models to users.
