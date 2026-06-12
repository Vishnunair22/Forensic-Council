# Model Registry — Forensic Council

**Version:** v1.0.0 | **Source-of-truth:** `apps/api/config/models.lock.json`

This document covers model pinning, provider setup, licensing, and verification for the Forensic Council system. It supersedes the removed `docs/MODELS.md`.

---

## Free-Tier Mode

Set `FREE_TIER_MODE=true` in `.env` to enforce free-tier constraints:
- Blocks paid-tier model strings from Groq/Gemini requests
- Enforces per-provider RPM/RPD limits via `ProviderQuotaGuard`

Default: `FREE_TIER_MODE=true`

---

## LLM Providers

### Groq (Logic & Reasoning)

| Role | Model | Fallback | Use case |
|------|-------|----------|---------|
| Per-agent synthesis | `llama-3.1-8b-instant` | `llama-3.3-70b-versatile` | Per-agent narrative synthesis — routed to the small, separate-TPM-bucket model (`SYNTHESIS_MODEL`) to preserve 70B headroom |
| Arbiter / final refiner | `llama-3.3-70b-versatile` | `ARBITER_FALLBACK_CHAIN` | Cross-agent deliberation, narrative, and verdict reasoning (`ARBITER_PRIMARY_MODEL`) |

Per-agent synthesis is routed to `llama-3.1-8b-instant` (via `SYNTHESIS_MODEL`) — it is a low-reasoning task, and a separate TPM bucket keeps the 70B reserved for the arbiter. The arbiter and final refiner use `llama-3.3-70b-versatile` (`ARBITER_PRIMARY_MODEL`). The base agent model / fallback are `LLM_MODEL` / `LLM_FALLBACK_MODELS`.

**Get a key:** https://console.groq.com/keys

**Env vars:**
```dotenv
LLM_PROVIDER=groq
LLM_API_KEY=gsk_...
LLM_MODEL=llama-3.3-70b-versatile
LLM_FALLBACK_MODELS=llama-3.1-8b-instant
```

**Verification:**
```bash
cd apps/api && uv run python scripts/verify_llm_keys.py --json
```

**Fallback:** No Groq key → agents use local tool-only analysis; Arbiter produces deterministic report with `court_defensible=True` and `confidence=0.55`.

---

### Google Gemini (Vision & Audio Deep Analysis)

Required for Agents 1, 3, and 5 deep analysis passes.

| Role | Model | Notes |
|------|-------|-------|
| Primary | `gemini-2.5-flash` | Fast, multimodal, cost-effective |
| Fallback cascade | `gemini-2.5-flash-lite`, `gemini-2.0-flash`, `gemini-2.0-flash-lite` | Ordered fallback if primary unavailable |

**Get a key:** https://aistudio.google.com/apikey

**Env vars:**
```dotenv
GEMINI_API_KEY=AIza...
GEMINI_MODEL=gemini-2.5-flash
GEMINI_FALLBACK_MODELS=gemini-2.5-flash-lite,gemini-2.0-flash,gemini-2.0-flash-lite
GEMINI_TIMEOUT=55.0
```

**Policy flag (REQUIRED):**
```dotenv
# Read https://ai.google.dev/terms, then set to true.
# Leaving this false disables ALL Gemini calls (safe default).
GEMINI_API_KEY_POLICY_OK=true
```

Without `GEMINI_API_KEY_POLICY_OK=true`, the `GeminiVisionClient` is disabled at init time (`_enabled = False`). This is an intentional safety measure — Gemini calls will not fire without explicit policy acknowledgement.

**Separate Arbiter key:**
```dotenv
ARBITER_GEMINI_API_KEY=
# Leave empty to share GEMINI_API_KEY.
# Set to a different key to isolate Arbiter quota from agent quota.
```

**Per-provider free-tier limits (as shipped in `.env.example`):**
```dotenv
GEMINI_RPM_LIMIT=5      # halved from the 10 RPM free-tier ceiling (API + worker share the key)
GEMINI_RPD_LIMIT=1500
GROQ_RPM_LIMIT=30       # free-tier ceiling
GROQ_TPM_LIMIT=12000    # matches llama-3.3-70b-versatile free-tier (12K TPM)
```
> Note: the in-code defaults (when these vars are unset) are more conservative —
> `GROQ_RPM_LIMIT=15` per process. `.env.example` is the canonical configuration.

**Verification:**
```bash
cd apps/api && uv run python scripts/verify_llm_keys.py --json
```

**Fallback:** No Gemini key → agents use local tool-only analysis; `degradation_flags` in report will be non-empty.

---

## Vision / Object Detection Models

| Model | License | Commercial use | Default |
|-------|---------|---------------|---------|
| DETR (`facebook/detr-resnet-50`) | Apache-2.0 | Yes | **Yes** |
| YOLO (`yolo11n.pt`, opt-in) | AGPL-3.0 | Requires source disclosure | No |

Default: `YOLO_MODEL_NAME=detr-resnet-50` (Apache-2.0, commercial-safe). Set `ENABLE_AGPL_MODELS=true` only if you have confirmed AGPL compliance.

---

## Audio Models

| Model | License | Commercial use | Default |
|-------|---------|---------------|---------|
| Vansh180/deepfake-audio-wav2vec2 | Apache-2.0 | Yes | **Yes** |
| AASIST (opt-in) | Research-only | No | No |

Default: `AASIST_MODEL_NAME=Vansh180/deepfake-audio-wav2vec2`. Set `ENABLE_RESEARCH_MODELS=true` only for research deployments.

---

## ML Model Verification

### Check cache health
```bash
docker exec forensic_api python scripts/model_cache_check.py --strict
```

Expected output:
```
[OK] HuggingFace  xxxx.x MB  (N files)  /app/cache/huggingface
[OK] PyTorch       xxx.x MB  (N files)  /app/cache/torch
[OK] EasyOCR        xx.x MB  (N files)  /app/cache/easyocr
```

### Pre-download models (first run only)
```bash
cd apps/api
POSTGRES_HOST=localhost uv run python scripts/model_pre_download.py --strict
```

This seeds the model cache directories configured by `HF_HOME` / `TORCH_HOME` / `YOLO_MODEL_DIR` / `EASYOCR_MODEL_DIR` (in Docker these are the named volumes `hf_cache`, `torch_cache`, `yolo_cache`, `easyocr_cache` mounted under `/app/cache/`). Subsequent runs skip download if weights are present.

### Validate ML tools
```bash
cd apps/api
POSTGRES_HOST=localhost uv run python scripts/validate_ml_tools.py
```

---

## Model Pinning

Pins specific commits/hashes for reproducibility. See `apps/api/config/models.lock.json` for the canonical version pins.

---

## Agent Tool Summary

| Agent | Primary Function | Key Tools |
|-------|-----------------|-----------|
| **Agent 1 (Image)** | Compression, splicing, GAN detection | ELA, JPEG Ghost, PRNU, Copy-Move, Deepfake, Gemini vision |
| **Agent 2 (Audio)** | Speaker verification, synthesis detection | Diarization, Anti-Spoofing, Prosody, ENF |
| **Agent 3 (Object)** | Scene context, incongruence detection | DETR/YOLO, CLIP, Scale validation, Lighting check, Gemini context injection |
| **Agent 4 (Video)** | Frame consistency, face swap detection | Optical Flow, Face Swap, Forgery, Liveness |
| **Agent 5 (Metadata)** | EXIF, GPS, steganography, C2PA | ExifTool, GPS validation, Steganography, C2PA, Gemini context injection |

**Agent 1 context injection:** During deep analysis, Agent 1 runs Gemini vision first and injects its context into Agents 3 and 5 via `inject_agent1_context()` before those agents run concurrently.
