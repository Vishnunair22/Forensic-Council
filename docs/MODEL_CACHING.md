# Model Caching Architecture

## Overview

The Forensic Council system uses persistent Docker volumes to cache ML models across container restarts. This eliminates the need to re-download ~1.2 GB of models on every deployment.

## Cache Directories

### HuggingFace Cache (`/app/cache/huggingface/`)
- **OpenCLIP**: `hub/models--timm--vit_base_patch32_clip_224.openai/blobs/` (~578 MB)
  - Used by: Agents 1, 3 for zero-shot image classification
- **SpeechBrain**: `hub/models--speechbrain--spkrec-ecapa-voxceleb/blobs/` (~80 MB)
  - Used by: Agent 2 for speaker verification
### YOLO Cache (`/app/cache/ultralytics/`)
- `yolov8n.pt` (~6 MB)
  - Used by: Agent 3 for object detection

### EasyOCR Cache (`/app/cache/easyocr/`)
- English detection and recognition models (~200 MB)
  - Used by: Agent 5 for text extraction from images

### PyTorch Cache (`/app/cache/torch/hub/checkpoints/`)
- `resnet50-11ad3fa6.pth` (~98 MB)
  - Used by: Agent 1 for frequency domain analysis

### Calibration Models (`/app/cache/calibration_models/`)
- JSON files for confidence calibration
  - Used by: All agents for calibrated confidence scores

## First Run Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ FIRST CONTAINER START (volumes empty)                           │
├─────────────────────────────────────────────────────────────────┤
│ 1. docker_entrypoint.sh                                         │
│    ├─ Seeds calibration models into volume                       │
│    ├─ Checks if HF_FILES & YOLO_FILES exist                      │
│    ├─ If NOT: spawns model_pre_download.py in background         │
│    └─ model_cache_check.py reports cache status (~1s)           │
│ 2. model_pre_download.py (background)                           │
│    ├─ YOLO (YOLOv8n weights) → /app/cache/ultralytics           │
│    ├─ EasyOCR (English models) → /app/cache/easyocr             │
│    ├─ OpenCLIP (ViT-B-32) → /app/cache/huggingface              │
│    ├─ ResNet50 → /app/cache/torch                               │
│    ├─ SpeechBrain (ECAPA-TDNN) → /app/cache/huggingface         │
│    └─ pyannote (speaker diarization) → /app/cache/huggingface   │
│ 3. run_api.py starts immediately (during download)              │
│    ├─ Configures cache paths from core/config.py               │
│    ├─ warmup_all_tools() on startup (lifespan)                 │
│    └─ Each tool warmed up in parallel                           │
│ 4. ML tools run with persistent workers                         │
│    ├─ First call: load model from cache                         │
│    └─ Subsequent calls: reuse in-process worker pool            │
└─────────────────────────────────────────────────────────────────┘
```

**Total Download Size**: ~1.2 GB (first run only)  
**Download Time**: 5-10 minutes on residential internet  
**API Startup**: ~30 seconds (parallel with download)  
**First Investigation**: 30-60 seconds cold start (models loading into memory)

## Subsequent Runs Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ SUBSEQUENT STARTS (volumes populated)                           │
├─────────────────────────────────────────────────────────────────┤
│ 1. docker_entrypoint.sh                                         │
│    ├─ Checks HF_HUBS & YOLO_WEIGHTS ✓ (found)                   │
│    ├─ Skips model_pre_download.py                                │
│    └─ model_cache_check.py reports cache ready (~<1s)           │
│ 2. run_api.py starts                                            │
│    ├─ warmup_all_tools() ← LOADS MODELS FROM CACHE              │
│    └─ 30-60s for all models to load into memory                 │
│ 3. ML tools use persistent workers                              │
│    ├─ Models already loaded                                     │
│    └─ Tool calls complete in <1-5s                              │
└─────────────────────────────────────────────────────────────────┘
```

**Startup Time**: 30-60 seconds (warm-up)  
**First Investigation**: <5 seconds (models in memory)

## Monitoring

### Check Warm-Up Status

```bash
# Detailed ML tools status
curl http://localhost:8000/api/v1/health/ml-tools

# Response example:
{
  "status": "ready",
  "tools_ready": 10,
  "tools_total": 10,
  "warmup_percentage": 100.0,
  "details": {
    "ela_anomaly_classifier.py": true,
    "copy_move_detector.py": true,
    ...
  },
  "cache_dirs": {
    "huggingface": "/app/cache/huggingface",
    "torch": "/app/cache/torch",
    "yolo": "/app/cache/ultralytics",
    "easyocr": "/app/cache/easyocr"
  }
}
```

### View Download Progress

```bash
# Monitor background download
tail -f /tmp/model_download.log
```

### Check Cache Size

```bash
# Inside container
docker exec forensic_api du -sh /app/cache/*

# Expected output:
# 578M  /app/cache/huggingface
# 6.0M  /app/cache/ultralytics
# 200M  /app/cache/easyocr
# 98M   /app/cache/torch
# 1.5M  /app/cache/calibration_models
```

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `HF_HOME` | HuggingFace cache directory | `/app/cache/huggingface` |
| `YOLO_CONFIG_DIR` | YOLO weights directory | `/app/cache/ultralytics` |
| `TORCH_HOME` | PyTorch hub cache | `/app/cache/torch` |
| `EASYOCR_MODEL_DIR` | EasyOCR models | `/app/cache/easyocr` |
| `SKIP_MODEL_DOWNLOAD` | Skip pre-download (for testing) | `0` |
| `SKIP_CACHE_CHECK` | Skip cache verification | `0` |

## Docker Volumes

Named volumes ensure cache persistence across container rebuilds:

```yaml
volumes:
  hf_cache:              # HuggingFace models
  torch_cache:           # PyTorch hub
  easyocr_cache:         # EasyOCR models
  yolo_cache:            # YOLO weights
  calibration_models_cache:  # Calibration JSON files
```

All volumes mount to the `forensic-council` project, ensuring consistency across dev/prod.

## Troubleshooting

### Models Not Downloading

```bash
# Check if download is running
docker exec forensic_api ps aux | grep model_pre_download

# View download log
docker exec forensic_api cat /tmp/model_download.log

# Force re-download
docker exec forensic_api python probes/model_pre_download.py
```

### Cache Detection Failing

The entrypoint checks for:
- At least 2 HuggingFace model hubs (OpenCLIP + SpeechBrain/pyannote)
- At least 1 YOLO weight file (.pt)

```bash
# Verify cache contents
docker exec forensic_api find /app/cache/huggingface/hub -type d -name "models--*"
docker exec forensic_api find /app/cache/ultralytics -name "*.pt"
```

### Warm-Up Taking Too Long

```bash
# Check warm-up status
curl http://localhost:8000/api/v1/health/ml-tools

# If stuck, restart the API
docker compose restart backend
```

## Performance Characteristics

| Scenario | Time | Notes |
|----------|------|-------|
| First container start | 5-10 min download | API ready in 30s, models download in background |
| First investigation (during download) | 30-60s | Cold start - models loading into memory |
| Subsequent container starts | 30-60s | Warm-up loads models from cache |
| First investigation (after warm-up) | <5s | Models in memory |
| Subsequent investigations | <1-5s | Worker pool reuse |

## Best Practices

1. **Pre-download models in CI/CD**: Run `model_pre_download.py` during image build to avoid runtime downloads
2. **Monitor warm-up status**: Check `/api/v1/health/ml-tools` before accepting traffic
3. **Don't clear cache volumes**: `docker volume rm` will force re-download
4. **Use SKIP_MODEL_DOWNLOAD=1**: For testing without model downloads

