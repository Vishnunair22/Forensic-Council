# Forensic Council — ML Model Pinning
# ===========================================
# Pins specific commits/hashes for reproducibility.
# Update these when upgrading models.

# OpenCLIP (SigLIP)
# Pin to specific version for reproducibility
siglip_commit: str = ""  # Leave empty = use latest

# YOLO (Ultralytics)
# Pin to specific version
yolo_version: str = "8.3.0"  #Ultralytics YOLO v8.3.0

# Audio Deepfake Detection (Vansh180)
# Using HuggingFace - no commit pin supported
audio_deepfake_model: str = "Vansh180/deepfake-audio-wav2vec2"
audio_deepfake_revision: str = "main"

# Alternative audio anti-spoofing (Apache-2.0)
audio_spoof_alternative: str = "MattyB95/AST-anti-spoofing"

# Alternative object detection ( permissive)
object_detection_alternative: str = "IDEA-Research/grounding-dino-tiny"

# License notes:
# - yolo11n.pt: AGPL-3.0 (Ultralytics) - commercial use requires paid license
# - ViT-L-14 (OpenCLIP): MIT
# - Vansh180/deepfake-audio-wav2vec2: Custom (check HF page)
# - MattyB95/AST-anti-spoofing: Apache-2.0
