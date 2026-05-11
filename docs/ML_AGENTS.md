# ML Agents

## Overview

Forensic Council uses five specialist forensic agents plus one Council Arbiter.

```text
Agent 1: Image Forensics
Agent 2: Audio Forensics
Agent 3: Object Detection / Scene Context
Agent 4: Video Forensics
Agent 5: Metadata / Provenance
Agent 6: Council Arbiter
```

## Agent Files

- `apps/api/agents/agent1_image.py`
- `apps/api/agents/agent2_audio.py`
- `apps/api/agents/agent3_object.py`
- `apps/api/agents/agent4_video.py`
- `apps/api/agents/agent5_metadata.py`
- `apps/api/agents/arbiter.py`
- `apps/api/agents/arbiter_verdict.py`
- `apps/api/agents/arbiter_narrative.py`

---

## Agent 1: Image Forensics

**File:** `apps/api/agents/agent1_image.py`

**Primary media:** image/*

**Typical initial tasks:**
- file_hash_verify
- extract_text_from_image
- analyze_image_content
- frequency_domain_analysis
- neural_ela

**Typical deep tasks:**
- diffusion_artifact_detector
- synthid_watermark_detect
- f3_net_frequency
- gemini_deep_forensic
- adversarial_robustness_check

**Related tools:**
- `apps/api/tools/image_tools.py`
- `apps/api/tools/ocr_tools.py`
- `apps/api/tools/clip_utils.py`
- `apps/api/tools/ml_tools`

---

## Agent 2: Audio Forensics

**File:** `apps/api/agents/agent2_audio.py`

**Primary media:** audio/*, video/*

**Typical initial tasks:**
- speaker_diarize
- neural_prosody
- audio_gen_signature
- voice_clone_detect
- anti_spoofing_detect
- codec_fingerprinting

**Typical deep tasks:**
- prosody_analyze
- audio_splice_detect
- enf_analysis
- background_noise_analysis
- voice_clone_deep_ensemble
- anti_spoofing_deep_ensemble
- gemini_deep_forensic

**Related tools:**
- `apps/api/tools/audio_tools.py`
- `apps/api/tools/audio/diarization.py`
- `apps/api/tools/audio/prosody.py`
- `apps/api/tools/audio/spectral.py`
- `apps/api/tools/audio/splice.py`
- `apps/api/tools/audio/synthesis.py`

---

## Agent 3: Object Detection / Scene Context

**File:** `apps/api/agents/agent3_object.py`

**Primary media:** image/*, video/*

**Typical physical-scene tasks:**
- object_detection
- scene_incongruence
- lighting_consistency
- contraband_database

**Typical screenshot/digital-capture tasks:**
- screenshot_scene_applicability
- screenshot_layout_forensics

**Typical deep tasks:**
- secondary_classification
- scale_validation
- adversarial_robustness_check
- lighting_consistency
- gemini_deep_forensic

**Related tools:**
- `apps/api/tools/image_tools.py`
- `apps/api/tools/ml_tools`

---

## Agent 4: Video Forensics

**File:** `apps/api/agents/agent4_video.py`

**Primary media:** video/*

**Typical initial tasks:**
- video_metadata
- vfi_error_map
- thumbnail_coherence
- frame_consistency_analysis

**Typical deep tasks:**
- optical_flow_analysis
- interframe_forgery_detector
- frame_extraction
- face_swap_detection
- deepfake_frequency_check
- rolling_shutter_validation
- compression_artifact_analysis
- adversarial_robustness_check
- gemini_deep_forensic

**Related tools:**
- `apps/api/tools/video_tools.py`
- `apps/api/tools/mediainfo_tools.py`

---

## Agent 5: Metadata / Provenance

**File:** `apps/api/agents/agent5_metadata.py`

**Primary media:** all supported files

**Typical tasks:**
- file_hash_verify
- exif_extract
- file_structure_analysis
- hex_signature_scan
- compression_risk_audit
- timestamp_analysis
- metadata_anomaly_score
- provenance_chain_verify
- camera_profile_match
- gps_timezone_validate
- astro_grounding
- gemini_deep_forensic

**Related tools:**
- `apps/api/tools/metadata_tools.py`
- `apps/api/tools/metadata`
- `apps/api/tools/mediainfo_tools.py`

---

## Agent 6: Council Arbiter

**Files:**
- `apps/api/agents/arbiter.py`
- `apps/api/agents/arbiter_verdict.py`
- `apps/api/agents/arbiter_narrative.py`

**Responsibilities:**
- deduplicate findings
- compare agent findings
- compute per-agent metrics
- compute manipulation probability
- apply compression penalty
- challenge cross-agent inconsistencies
- generate executive summary
- generate uncertainty statement
- generate final verdict
- sign final report

---

## Model Configuration Files

### Model lock file

**File:** `apps/api/config/models.lock.json`

**Purpose:** Pins expected model identities and model metadata.

### Task/tool overrides

**File:** `apps/api/config/task_tool_overrides.yaml`

**Purpose:** Controls task-to-tool routing behavior.

### Backend settings

**File:** `apps/api/core/config.py`

**Purpose:** Central settings for ML, LLM, model cache, licensing gates, quotas, auth, storage, and runtime behavior.

---

## Model Download Script

**File:** `apps/api/scripts/model_pre_download.py`

**Use:**

```bash
cd apps/api
uv run python scripts/model_pre_download.py --strict
```

**With ML extras:**

```bash
cd apps/api
uv sync --extra dev --extra security --extra observability --extra ml
uv run python scripts/model_pre_download.py --strict
```

---

## Model Cache Check

**File:** `apps/api/scripts/model_cache_check.py`

**Use:**

```bash
cd apps/api
uv run python scripts/model_cache_check.py
```

---

## ML Tool Validation

**File:** `apps/api/scripts/validate_ml_tools.py`

**Use:**

```bash
cd apps/api
uv run python scripts/validate_ml_tools.py
```

---

## Important Model/Cache Environment Variables

- HF_HOME
- TRANSFORMERS_CACHE
- TORCH_HOME
- EASYOCR_MODEL_DIR
- YOLO_MODEL_DIR
- YOLO_CONFIG_DIR
- NUMBA_CACHE_DIR
- CALIBRATION_MODELS_PATH

---

## Important LLM/Gemini Settings

### General LLM

- LLM_PROVIDER
- LLM_API_KEY
- LLM_MODEL
- LLM_FALLBACK_MODELS
- LLM_ENABLE_REACT_REASONING
- LLM_ENABLE_POST_SYNTHESIS

### Gemini

- GEMINI_API_KEY
- GEMINI_MODEL
- GEMINI_FALLBACK_MODELS
- GEMINI_TIMEOUT
- GEMINI_MAX_CONCURRENT
- GEMINI_RPM_LIMIT
- GEMINI_RPD_LIMIT
- GEMINI_API_KEY_POLICY_OK

### Arbiter LLM

- ARBITER_LLM_PROVIDER
- ARBITER_LLM_API_KEY
- ARBITER_PRIMARY_MODEL
- ARBITER_FALLBACK_MODELS
- ARBITER_GEMINI_API_KEY

---

## Licensing Gates

The backend has production gating for model licensing.

**Important settings:**
- enable_agpl_models
- enable_research_models

**Production rule:** Do not enable AGPL or research-only models in production unless the licensing and deployment policy explicitly allows it.

---

## ML Safety Rules

Do not:

- download unpinned models silently in production
- enable research-only models in production accidentally
- enable AGPL models in commercial production accidentally
- make model failures look like successful forensic findings
- hide degraded-analysis state from the report
- remove fallback/degradation telemetry

---

## Related Docs

- docs/MODELS.md
- docs/MODEL_LICENSING.md
- docs/AGENT_CAPABILITIES.md
- docs/ARCHITECTURE.md