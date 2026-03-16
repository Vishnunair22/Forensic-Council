# Agent Capabilities & Methodologies

> **Version:** v1.1.0 | **Last updated:** 2026-03-12
>
> **Production status:** ✅ All 40+ tools are real, algorithmic implementations.
> No tool returns random or stub data. Every finding carries `"court_defensible": true|false`
> and a `"caveat"` field where external database integration would strengthen the result.
>
> **v1.1.0 changes:** Groq + Gemini dual-AI integration. Groq (Llama 3.3 70B) drives all
> ReAct reasoning loops and Arbiter synthesis. Google Gemini 1.5 Flash provides multimodal
> vision analysis during the deep pass for Agents 1, 3, and 5.

The Forensic Council agents use a **dual-AI architecture**:

- **Groq (Llama 3.3 70B)** — drives the cognitive ReAct loop (orchestration, tool selection,
  deduction) and synthesises the Arbiter's executive summary and uncertainty statement.
  ~700 tok/s throughput; free tier sufficient for development.

- **Google Gemini 1.5 Flash** — performs multimodal vision analysis during the deep analysis
  pass for Agents 1, 3, and 5. Understands what a file visually IS, surfaces manipulation
  signals invisible to classical tools, and cross-validates visual content against metadata
  claims. Findings are tagged `analysis_source: gemini_vision` and compiled separately in
  the Arbiter report.

All agents run an **initial analysis** pass followed by a **deep analysis** pass for
ML-heavy tools and Gemini vision — both sets of findings are merged and signed into
the final report.

---

## Analysis Phases

Each agent produces two sets of findings:

| Phase | Description | Typical duration |
|-------|-------------|-----------------|
| **Initial** | Fast numpy/OpenCV/EXIF tools — ELA, hash checks, metadata extraction, frequency analysis | 15–25 s |
| **Deep** | Heavy ML inference — CLIP semantic classification, copy-move detection, adversarial robustness checks, OCR, cross-agent calls, **Gemini vision analysis** | 30–120 s |

Both phases run automatically for every investigation. The pipeline calls
`run_investigation()` → `run_deep_investigation()` sequentially per agent, then passes
combined findings to the Council Arbiter.

---

## AI Provider Roles

| Provider | Role | Config key |
|----------|------|-----------|
| **Groq** (Llama 3.3 70B) | ReAct loop reasoning, tool orchestration, Arbiter synthesis | `LLM_PROVIDER=groq`, `LLM_API_KEY` |
| **Google Gemini 1.5 Flash** | Deep vision analysis (Agents 1, 3, 5) — file content ID, manipulation signals, scene coherence, metadata cross-validation | `GEMINI_API_KEY` |

Both providers degrade gracefully: if a key is not set, the corresponding capability
is skipped and a clear caveat is recorded in the finding.

---

## File-Type Routing

Agents only run against evidence they can analyse. The pipeline skips agents whose
`supported_file_types` list does not match the uploaded MIME type and records a
`"File type not applicable"` finding instead of an error.

| Agent | Supported types | Gemini vision |
|-------|----------------|:---:|
| Agent 1 — Image | `image/*` | ✅ |
| Agent 2 — Audio | `audio/*`, `video/*` | — |
| Agent 3 — Object | `image/*` | ✅ |
| Agent 4 — Video | `video/*`, `audio/*` | — |
| Agent 5 — Metadata | All types (`*`) | ✅ (image/PDF) |

---

## Confidence Scoring

1. **Mathematical baseline** — ML subprocess scripts (IsolationForest, optical flow, etc.) return a raw anomaly score.
2. **Groq calibration** — The Groq-powered agent interprets the score against file context (e.g. high JPEG compression naturally produces ELA noise).
3. **Gemini corroboration** — Gemini vision findings at ≥ 0.6 confidence are treated as supportive evidence; lower-confidence Gemini findings carry a `"caveat"` requiring corroboration.
4. **Arbiter adjustment** — Contested findings may be demoted if a contradicting agent provides stronger evidence.

Final `calibrated_probability` is a 0.0–1.0 float. All findings also carry a `"court_defensible"` boolean and a `"caveat"` note where applicable.

---

## Agent 1 — Image Integrity

**Role:** Pixel-level manipulation, splicing, GAN/deepfake artifact detection + Gemini vision cross-validation.

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
| `gemini_identify_content` | Deep | **Gemini 1.5 Flash** — file content type identification, scene description, immediate visual anomalies |
| `gemini_cross_validate_manipulation` | Deep | **Gemini 1.5 Flash** — visual cross-validation of ELA/JPEG ghost preliminary flags |

**Can detect:** Photoshop splicing, copy-move cloning, GAN/diffusion images, JPEG double-compression artefacts, adversarial ELA evasion, sensor noise inconsistencies, visually obvious manipulation boundaries (via Gemini).

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

**Role:** Scene-level object identification, lighting consistency, contextual incongruence + Gemini vision deep scene analysis.

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
| `contraband_database` | Initial | CLIP ViT-B-32 zero-shot semantic similarity — contextual analysis, NOT a weapons registry |
| `inter_agent_call` | Initial | Real inter-agent call via InterAgentBus → Agent 1 for lighting region confirmation |
| `adversarial_robustness_check` | Deep | YOLOv8 perturbation stability — Gaussian noise, brightness shift, salt-and-pepper noise |
| `gemini_object_scene_analysis` | Deep | **Gemini 1.5 Flash** — validated object list, weapon/contraband detection, scene coherence, compositing signals |

> **Caveat:** `contraband_database` uses CLIP semantic similarity to flag contextual weapon/contraband resemblance. It is NOT connected to FBI NIBIN or Interpol. All findings include `"court_defensible": true` and a `"method"` disclaimer. Integration with an authoritative registry would strengthen legal weight.
>
> Gemini weapon/contraband detection is AI-visual and requires corroboration with classical tools and expert review before use in legal proceedings.

**Can detect:** Object scale/perspective mismatches, lighting direction inconsistencies, contextually incongruous objects, CLIP-flagged weapon-like content, compositing boundary artifacts (Gemini visual), scene incoherence (Gemini).

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

**Role:** EXIF/XMP forensics, GPS-timestamp consistency, steganography, provenance + Gemini metadata-visual cross-validation.

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
| `gemini_metadata_visual_consistency` | Deep | **Gemini 1.5 Flash** — cross-validate EXIF claims (timestamp, GPS location, device) against visual content; detect screenshots, AI-generated images, and re-photographed screens |

> **Caveats:**
> - `astronomical_api` validates day/night consistency only. Precise sun elevation angle comparison requires a full NOAA/SunCalc API integration.
> - `reverse_image_search` searches the local evidence store only. Web provenance (TinEye/Google Images) requires an external API key.
> - `device_fingerprint_db` applies EXIF manufacturer heuristics + PRNU variance. A full CameraV PRNU database would provide definitive sensor attribution.
> - `gemini_metadata_visual_consistency` is AI-derived and requires corroboration with deterministic EXIF tools before use as primary legal evidence.

**Can detect:** Software signature rewrites (Photoshop/Premiere Pro in EXIF), GPS–timezone contradictions, LSB steganographic payloads, container structure anomalies, timestamp field inconsistencies, prior near-duplicate evidence, visual-metadata inconsistencies (Gemini), screenshot/AI-generation provenance flags (Gemini).

**Limitations:** Metadata stripped before upload; GPS spoofing with a correctly matching timezone; sophisticated steganography above LSB depth.

---

## Council Arbiter

**Role:** Cross-modal correlation, conflict resolution, HITL escalation, cryptographic signing, Groq-powered report synthesis.

| Capability | Implementation |
|-----------|---------------|
| Cross-modal correlation | Finds findings that corroborate or contradict across agents |
| Conflict resolution | Escalates contested high-confidence contradictions to HITL |
| Challenge loop | Can re-invoke individual agents with a `challenge_context` |
| Report synthesis | **Groq Llama 3.3 70B** generates `executive_summary` and `uncertainty_statement` from all findings including Gemini vision insights |
| Gemini findings compilation | Collects `gemini_vision_findings` from Agents 1, 3, 5 into a dedicated report section |
| Cryptographic signing | ECDSA P-256 + SHA-256 hash of full report JSON |

The Arbiter's `ForensicReport` schema now includes a `gemini_vision_findings` field containing
all Gemini-sourced findings compiled across agents. These findings are also present inside
`per_agent_findings` for full traceability.

---

## Optional Enhancements for Stronger Court Admissibility

These integrations are not required for operation but would elevate specific findings from "supportive evidence" to "primary evidence" in legal proceedings:

| Tool | Current capability | Potential enhancement |
|------|------------------|----------------------|
| `contraband_database` (Agent 3) | CLIP zero-shot semantic similarity | FBI NIBIN / Interpol registry API |
| `astronomical_api` (Agent 5) | Day/night consistency via `astral` | NOAA/SunCalc precise sun elevation angle |
| `reverse_image_search` (Agent 5) | Local PHash comparison | TinEye or Google Images API for web provenance |
| `device_fingerprint_db` (Agent 5) | EXIF heuristics + PRNU variance | CameraV full PRNU sensor database |
| Gemini vision (Agents 1, 3, 5) | AI-assisted visual analysis | Expert forensic examiner review + Gemini Pro upgrade |

All tools already return `"court_defensible": true` with `"caveat"` disclosures. The above upgrades are prioritised improvements, not blockers for production use.

> **Production status:** ✅ All 40+ tools are real, algorithmic implementations.
> No tool returns random or stub data. Every finding carries `"court_defensible": true|false`
> and a `"caveat"` field where external database integration would strengthen the result.
