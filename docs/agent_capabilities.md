# Agent Capabilities & Methodologies

> **Version:** v1.0.3 | **Last updated:** 2026-03-11
>
> **Production status:** ✅ All 40+ tools are real, algorithmic implementations.
> No tool returns random or stub data. Every finding carries `"court_defensible": true|false`
> and a `"caveat"` field where external database integration would strengthen the result.

The Forensic Council agents use a hybrid approach: the LLM drives the cognitive ReAct
loop (orchestration and deduction) while specialised ML scripts handle mathematical
anomaly detection. All agents run an **initial analysis** pass followed by a **deep
analysis** pass for ML-heavy tools — both sets of findings are merged and signed into
the final report.

---

## Analysis Phases

Each agent produces two sets of findings:

| Phase | Description | Typical duration |
|-------|-------------|-----------------|
| **Initial** | Fast numpy/OpenCV/EXIF tools — ELA, hash checks, metadata extraction, frequency analysis | 15–25 s |
| **Deep** | Heavy ML inference — CLIP semantic classification, copy-move detection, adversarial robustness checks, OCR, cross-agent calls | 30–90 s |

Both phases run automatically for every investigation. The pipeline calls
`run_investigation()` → `run_deep_investigation()` sequentially per agent, then passes
combined findings to the Council Arbiter.

---

## File-Type Routing

Agents only run against evidence they can analyse. The pipeline skips agents whose
`supported_file_types` list does not match the uploaded MIME type and records a
`"File type not applicable"` finding instead of an error.

| Agent | Supported types |
|-------|----------------|
| Agent 1 — Image | `image/*` |
| Agent 2 — Audio | `audio/*`, `video/*` |
| Agent 3 — Object | `image/*` |
| Agent 4 — Video | `video/*`, `audio/*` |
| Agent 5 — Metadata | All types (`*`) |

---

## Confidence Scoring

1. **Mathematical baseline** — ML subprocess scripts (IsolationForest, optical flow, etc.) return a raw anomaly score.
2. **LLM calibration** — The agent interprets the score against file context (e.g. high JPEG compression naturally produces ELA noise).
3. **Arbiter adjustment** — Contested findings may be demoted if a contradicting agent provides stronger evidence.

Final `calibrated_probability` is a 0.0–1.0 float. All findings also carry a `"court_defensible"` boolean and a `"caveat"` note where applicable.

---

## Agent 1 — Image Integrity

**Role:** Pixel-level manipulation, splicing, GAN/deepfake artifact detection.

### Tool Registry

| Tool | Phase | Implementation |
|------|-------|----------------|
| `ela_full_image` | Initial | Full-image Error Level Analysis (Pillow + numpy) |
| `ela_anomaly_classify` | Initial | IsolationForest ML model (subprocess `ela_anomaly_classifier.py`) |
| `jpeg_ghost_detect` | Initial | Multi-quality JPEG ghost detection |
| `frequency_domain_analysis` | Initial | FFT-based frequency domain analysis |
| `splicing_detect` | Initial | DCT quantisation inconsistency detection (subprocess `splicing_detector.py`) |
| `noise_fingerprint` | Initial | PRNU per-region block variance (subprocess `noise_fingerprint.py`) |
| `deepfake_frequency_check` | Initial | GAN frequency artifact detection (subprocess `deepfake_frequency.py`) |
| `file_hash_verify` | Initial | SHA-256 chain-of-custody verification |
| `perceptual_hash` | Initial | pHash (16×16) for near-duplicate detection |
| `roi_extract` | Initial | Region-of-interest crop from flagged coordinates |
| `analyze_image_content` | Deep | CLIP ViT-B-32 zero-shot semantic classification (shared model) |
| `copy_move_detect` | Deep | SIFT keypoint self-matching (subprocess `copy_move_detector.py`) |
| `adversarial_robustness_check` | Deep | ELA perturbation stability — Gaussian noise, double JPEG, colour jitter |
| `sensor_db_query` | Deep | PRNU residual heuristics + EXIF make/model cross-validation |
| `extract_evidence_text` | Deep | OCR pipeline: PyMuPDF (PDF) → EasyOCR → Tesseract fallback |

**Can detect:** Photoshop splicing, copy-move cloning, GAN/diffusion images, JPEG double-compression artefacts, adversarial ELA evasion, sensor noise inconsistencies.

**Limitations:** Images with SNR < 10 dB after print/rescan; extremely aggressive JPEG re-compression below quality 30; unknown GAN architectures not represented in frequency-domain training data.

---

## Agent 2 — Audio & Multimedia

**Role:** Audio deepfake detection, splice point analysis, prosody anomalies, AV sync.

### Tool Registry

| Tool | Phase | Implementation |
|------|-------|----------------|
| `speaker_diarization` | Initial | pyannote.audio 3.1 speaker diarisation |
| `anti_spoofing_detection` | Initial | SpeechBrain ECAPA-TDNN anti-spoofing model |
| `prosody_analysis` | Initial | Praat-Parselmouth F0/jitter/shimmer feature extraction |
| `audio_splice_detect` | Initial | ML splice point detection (subprocess `audio_splice_detector.py`) |
| `background_noise_analysis` | Initial | Librosa spectral shift-point detection |
| `codec_fingerprinting` | Initial | FFmpeg codec chain analysis |
| `audio_visual_sync` | Initial | Moviepy + librosa onset-correlation AV sync verification |
| `inter_agent_call` | Initial | Real inter-agent call via InterAgentBus → Agent 4 for timestamp correlation |
| `adversarial_robustness_check` | Deep | Spectral perturbation stability — low-pass filter, noise injection, time-stretch |

**Can detect:** Synthetic voices lacking natural respiratory micro-pauses, splice points via room-tone shift, re-encoding events via codec chain analysis, AV sync breaks.

**Limitations:** Human professional impersonators; audio with SNR below 10 dB; short clips under 3 seconds (insufficient for diarisation).

---

## Agent 3 — Object Detection

**Role:** Scene-level object identification, lighting consistency, contextual incongruence.

### Tool Registry

| Tool | Phase | Implementation |
|------|-------|----------------|
| `object_detection` | Initial | YOLOv8 full-scene detection |
| `secondary_classification` | Initial | CLIP secondary classification for low-confidence detections |
| `scale_validation` | Initial | OpenCV perspective-aware scale analysis using EXIF sensor size |
| `lighting_consistency` | Initial | Hough-transform shadow direction analysis (scikit-image) |
| `scene_incongruence` | Initial | OpenCV quadrant noise and colour temperature analysis |
| `image_splice_check` | Initial | DCT splicing detection (subprocess `splicing_detector.py`) |
| `noise_fingerprint` | Initial | PRNU block variance via ML subprocess |
| `contraband_database` | Initial | CLIP ViT-B-32 zero-shot semantic similarity (shared model) — contextual analysis, NOT a weapons registry |
| `inter_agent_call` | Initial | Real inter-agent call via InterAgentBus → Agent 1 for lighting region confirmation |
| `adversarial_robustness_check` | Deep | YOLOv8 perturbation stability — Gaussian noise, brightness shift, salt-and-pepper noise |

> **Caveat:** `contraband_database` uses CLIP semantic similarity to flag contextual weapon/contraband resemblance. It is NOT connected to FBI NIBIN or Interpol. All findings include `"court_defensible": true` and a `"method"` disclaimer. Integration with an authoritative registry would strengthen legal weight.

**Can detect:** Object scale/perspective mismatches, lighting direction inconsistencies, contextually incongruous objects, CLIP-flagged weapon-like content.

**Limitations:** Perfectly rendered 3D objects with matched HDRI lighting; objects outside YOLO's 80-class vocabulary without a CLIP match.

---

## Agent 4 — Temporal Video

**Role:** Frame-level edit detection, deepfake face-swap, optical flow anomalies, rolling shutter validation.

### Tool Registry

| Tool | Phase | Implementation |
|------|-------|----------------|
| `optical_flow_analysis` | Initial | Dense Farneback optical flow — temporal anomaly heatmap |
| `frame_extraction` | Initial | Frame window extraction at flagged timestamps |
| `frame_consistency_analysis` | Initial | SSIM + histogram frame-to-frame consistency |
| `face_swap_detection` | Initial | DeepFace embedding model face-swap detection |
| `video_metadata` | Initial | Video metadata extraction (fps, codec, bitrate, duration) |
| `mediainfo_profile` | Initial | Deep AV container profiling: VFR flag, encoding tool, forensic flags (pymediainfo) |
| `av_file_identity` | Initial | Lightweight AV pre-screen: format, codec, high-severity container flags |
| `anomaly_classification` | Initial | SSIM + motion-vector anomaly classification (subprocess `anomaly_classifier.py`) |
| `rolling_shutter_validation` | Initial | Optical flow scanline skew validation (subprocess `rolling_shutter_validator.py`) |
| `inter_agent_call` | Initial | Real inter-agent call via InterAgentBus → Agent 2 for AV sync cross-verification |
| `adversarial_robustness_check` | Deep | Optical flow perturbation stability — Gaussian noise, brightness shift |

**Can detect:** Missing/duplicate frames, face-swap boundary artefacts, VFR manipulation, rolling shutter violations, container-level encoding tool fingerprints.

**Limitations:** Frame-level temporal analysis only (no sub-frame motion vectors); slow-motion tampering below 10 fps; heavily compressed video (CRF > 35).

---

## Agent 5 — Metadata & Context

**Role:** EXIF/XMP forensics, GPS-timestamp consistency, steganography, provenance.

### Tool Registry

| Tool | Phase | Implementation |
|------|-------|----------------|
| `exif_extract` | Initial | Full EXIF/XMP extraction (pyexiftool + hachoir binary parser) |
| `gps_timezone_validate` | Initial | GPS coordinate → timezone validation (timezonefinder + geopy) |
| `steganography_scan` | Initial | LSB steganography decode (stegano library) |
| `file_structure_analysis` | Initial | Hachoir binary container structure forensics |
| `hex_signature_scan` | Initial | File header magic byte validation |
| `timestamp_analysis` | Initial | Multi-field EXIF timestamp cross-correlation |
| `file_hash_verify` | Initial | SHA-256 chain-of-custody verification |
| `metadata_anomaly_score` | Initial | IsolationForest on EXIF field distributions (subprocess `metadata_anomaly_scorer.py`) |
| `astronomical_api` | Initial | Real astronomical validation using `astral` library — sunrise/sunset vs claimed GPS+timestamp |
| `extract_evidence_text` | Initial | OCR pipeline: PyMuPDF (PDF lossless) → EasyOCR → Tesseract fallback |
| `mediainfo_profile` | Initial | Deep AV container profiling (pymediainfo) |
| `av_file_identity` | Initial | Lightweight AV pre-screen |
| `reverse_image_search` | Deep | PHash (16×16) Hamming-distance comparison against all prior evidence in the local store |
| `device_fingerprint_db` | Deep | EXIF manufacturer signature rules + PRNU variance cross-validation |
| `adversarial_robustness_check` | Deep | EXIF field permutation stability analysis |

> **Caveats:**
> - `astronomical_api` validates day/night consistency only. Precise sun elevation angle comparison requires a full NOAA/SunCalc API integration.
> - `reverse_image_search` searches the local evidence store only. Web provenance (TinEye/Google Images) requires an external API key.
> - `device_fingerprint_db` applies EXIF manufacturer heuristics + PRNU variance. A full CameraV PRNU database would provide definitive sensor attribution.

**Can detect:** Software signature rewrites (Photoshop/Premiere Pro in EXIF), GPS–timezone contradictions, LSB steganographic payloads, container structure anomalies, timestamp field inconsistencies, prior near-duplicate evidence.

**Limitations:** Metadata stripped before upload; GPS spoofing with a correctly matching timezone; sophisticated steganography above LSB depth.

---

## Council Arbiter

**Role:** Cross-modal correlation, conflict resolution, HITL escalation, cryptographic signing.

| Capability | Implementation |
|-----------|---------------|
| Cross-modal correlation | Finds findings that corroborate or contradict across agents |
| Conflict resolution | Escalates contested high-confidence contradictions to HITL |
| Challenge loop | Can re-invoke individual agents with a `challenge_context` |
| Report synthesis | Produces `executive_summary`, `uncertainty_statement`, `per_agent_findings` |
| Cryptographic signing | ECDSA P-256 + SHA-256 hash of full report JSON |

---

## Optional Enhancements for Stronger Court Admissibility

These integrations are not required for operation but would elevate specific findings from "supportive evidence" to "primary evidence" in legal proceedings:

| Tool | Current capability | Potential enhancement |
|------|------------------|----------------------|
| `contraband_database` (Agent 3) | CLIP zero-shot semantic similarity | FBI NIBIN / Interpol registry API |
| `astronomical_api` (Agent 5) | Day/night consistency via `astral` | NOAA/SunCalc precise sun elevation angle |
| `reverse_image_search` (Agent 5) | Local PHash comparison | TinEye or Google Images API for web provenance |
| `device_fingerprint_db` (Agent 5) | EXIF heuristics + PRNU variance | CameraV full PRNU sensor database |

All four tools already return `"court_defensible": true` with `"caveat"` disclosures. The above upgrades are prioritised improvements, not blockers for production use.
