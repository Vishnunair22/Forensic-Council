# ADR-004: CPU-Only PyTorch in Docker

## Status

Accepted

## Context

The backend uses PyTorch for:
- YOLOv8 object detection (Agent 3)
- CLIP zero-shot classification (Agent 3)
- Pyannote.audio speaker diarization (Agent 2)
- SpeechBrain anti-spoofing (Agent 2)

GPU inference would be faster (2-10x for YOLO, 5-20x for pyannote), but introduces significant infrastructure complexity.

## Decision

Use CPU-only PyTorch wheels in Docker, with ML inference offloaded to subprocesses to avoid blocking the event loop.

## Consequences

- Docker image is ~4 GB instead of ~12 GB (no CUDA runtime, no nvidia drivers).
- Runs on any x86_64 host without GPU requirements.
- ML subprocess isolation prevents GIL blocking and WebSocket disconnections.
- Cold-start model downloads on first run (~5-15 min) are mitigated by Docker named volumes.
- GPU support can be added later by changing the `pytorch-cpu` index to `pytorch-cu128` and installing nvidia-container-toolkit.

