"""
Common constants, MIME maps, and phrase tables for the Forensic Council API.
"""

# ── Exact MIME → valid-extension map ──────────────────
# Maps each accepted magic-detected MIME type to the file extensions that are
# legitimately associated with it.
_EXACT_MIME_EXT_MAP: dict[str, frozenset] = {
    "image/jpeg": frozenset({".jpg", ".jpeg"}),
    "image/png": frozenset({".png"}),
    "image/gif": frozenset({".gif"}),
    "image/webp": frozenset({".webp"}),
    "image/bmp": frozenset({".bmp"}),
    "image/tiff": frozenset({".tif", ".tiff"}),
    "video/mp4": frozenset({".mp4"}),
    "video/quicktime": frozenset({".mov"}),
    "video/x-msvideo": frozenset({".avi"}),
    "audio/wav": frozenset({".wav"}),
    "audio/x-wav": frozenset({".wav"}),
    "audio/mpeg": frozenset({".mp3"}),
    "audio/mp4": frozenset({".m4a"}),
    "audio/flac": frozenset({".flac"}),
}

# ── Task humaniser phrase map ──────────────────────────
# Maps working-memory task description substrings → user-friendly broadcast text.
_PIPELINE_TASK_PHRASES: dict[str, str] = {
    # Agent 1 – Image Integrity
    "ela": "🔬 Running Error Level Analysis across full image…",
    "ela anomaly block": "🧩 Classifying ELA anomaly blocks in flagged regions…",
    "jpeg ghost": "👻 Detecting JPEG ghost artifacts in suspicious regions…",
    "frequency domain analysis": "📡 Running frequency-domain analysis on contested regions…",
    "frequency-domain gan": "📡 Scanning frequency domain for GAN generation artifacts…",
    "file hash": "🔑 Verifying file hash against ingestion record…",
    "perceptual hash": "🔑 Computing perceptual hash for similarity detection…",
    "roi": "🎯 Re-analysing flagged ROIs with noise footprint…",
    "copy-move": "🔍 Checking for copy-move cloning artifacts…",
    "semantic image": "🧠 Identifying what this image actually depicts…",
    "ocr": "📄 Extracting all visible text via OCR…",
    "visible text": "📄 Extracting all visible text from image…",
    "adversarial robustness": "🛡️ Testing robustness against anti-forensics evasion…",
    "neural_ela": "🔬 Running ViT-based Neural Error Level Analysis…",
    "neural_splicing": "🧩 Mapping pixel trustworthiness with TruFor ViT…",
    "neural_copy_move": "🔍 Detecting region clones with BusterNet-V2…",
    "neural_fingerprint": "🔑 Generating neural perceptual fingerprint…",
    "f3_net_frequency": "📡 Scanning frequency domain for AI-GAN artifacts…",
    "anomaly_tracer": "🕵️ Tracing universal anomalies with ManTra-Net…",
    "gemini": "🤖 Asking Gemini AI for deep visual forensic analysis…",
    # Agent 2 – Audio
    "speaker diarization": "🎙️ Establishing voice-count baseline with diarization…",
    "anti-spoofing": "🔊 Running anti-spoofing detection on speaker segments…",
    "prosody": "🎵 Analysing prosody and rhythm across full audio track…",
    "splice point": "✂️ Detecting ML splice points in audio segments…",
    "background noise": "🌊 Checking background noise consistency for edit points…",
    "codec fingerprint": "🔐 Fingerprinting codec chain for re-encoding events…",
    "audio-visual sync": "⏱️ Verifying audio-visual sync against video timestamps…",
    "collaborative call": "🤝 Issuing inter-agent call to Agent 4 for corroboration…",
    "cross-agent collaboration": "🤝 Running cross-agent collaboration with Agent 4…",
    "spectral perturbation": "📊 Running spectral perturbation adversarial check…",
    "codec chain": "🔐 Running advanced codec chain analysis…",
    # Agent 3 – Object/Weapon
    "full-scene primary object": "👁️ Running YOLO primary object detection on full scene…",
    "secondary classification": "🔎 Re-classifying low-confidence detections…",
    "scale and proportion": "📐 Validating object scale and proportion geometry…",
    "lighting and shadow": "💡 Checking per-object lighting and shadow consistency…",
    "contraband": "⚠️ Cross-referencing objects against contraband database…",
    "scene-level contextual": "🧠 Analysing scene for contextual incongruences…",
    "image splicing": "✂️ Running ML-based image splicing detection…",
    "camera noise fingerprint": "📷 Checking camera noise fingerprint for region consistency…",
    "inter-agent call": "🤝 Issuing inter-agent call to Agent 1 for lighting check…",
    "object detection evasion": "🛡️ Testing against object detection evasion techniques…",
    # Agent 4 – Video
    "optical flow": "🎬 Running optical flow analysis — building anomaly heatmap…",
    "frame-to-frame": "🖼️ Extracting frames and checking inter-frame consistency…",
    "explainable": "🏷️ Classifying anomalies as EXPLAINABLE or SUSPICIOUS…",
    "face-swap": "🧑‍💻 Running face-swap detection on human faces…",
    "face swap": "🧑‍💻 Running face-swap detection on human faces…",
    "rolling shutter": "📷 Validating rolling shutter behaviour vs device metadata…",
    "deepfake frequency": "📡 Running deepfake frequency analysis across full video…",
    "audio-visual timestamp": "⏱️ Correlating audio-visual timestamps with Agent 2…",
    # Agent 5 – Metadata
    "exif": "📋 Extracting all EXIF fields — logging absent mandatory fields…",
    "gps coordinates": "🌍 Cross-validating GPS coordinates against timestamp timezone…",
    "steganography": "🕵️ Scanning for hidden steganographic payload…",
    "file structure": "🗂️ Running file structure forensic analysis…",
    "hexadecimal": "🗂️ Running hex scan for software signature anomalies…",
    "cross-field consistency": "📊 Synthesising cross-field metadata consistency verdict…",
    "ml metadata anomaly": "🤖 Running ML metadata anomaly scoring…",
    "astronomical": "🔭 Running astronomical API check for GPS/timestamp validation…",
    "reverse image search": "🌐 Running reverse image search for prior online appearances…",
    "device fingerprint": "🔐 Querying device fingerprint database for claimed device…",
    "metadata spoofing": "🛡️ Testing against metadata spoofing evasion techniques…",
    # Agent 1 — deep tools
    "prnu camera sensor": "📷 Running PRNU sensor fingerprint — cross-region source check…",
    "prnu": "📷 Analysing PRNU noise residual across image blocks…",
    "cfa demosaicing": "🌈 Checking CFA Bayer pattern consistency for splice regions…",
    "cfa": "🌈 Running CFA demosaicing pattern analysis…",
    # Agent 2 — deep tools
    "voice clone": "🤖 Detecting AI voice clone and TTS synthesis artifacts…",
    "ai speech synthesis": "🤖 Analysing spectral flatness for TTS synthesis markers…",
    "enf": "⚡ Tracking Electrical Network Frequency for splice detection…",
    "electrical network": "⚡ Running ENF analysis — verifying recording timestamp…",
    # Agent 3 — deep tools
    "object text ocr": "📄 Running OCR on detected object regions — extracting text…",
    "ocr on detected": "📄 Extracting license plates, IDs, and signs via OCR…",
    "document authenticity": "📑 Checking document font consistency and forgery artifacts…",
    # Agent 5 — deep tools
    "c2pa": "🔏 Verifying C2PA Content Credentials and provenance chain…",
    "content credentials": "🔏 Checking for C2PA/XMP provenance markers…",
    "thumbnail mismatch": "🖼️ Comparing embedded thumbnail to main image — edit check…",
    "embedded thumbnail": "🖼️ Extracting EXIF thumbnail for post-capture edit detection…",
    # Generic
    "self-reflection": "🪞 Running self-reflection quality check on findings…",
    "submit": "📤 Submitting calibrated findings to Council Arbiter…",
    "finaliz": "✅ Finalising and packaging findings…",
}
