# Changelog

All notable changes to the Forensic Council project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.9.1] — 2026-03-06

### Individual Agent Analysis Overhaul

Three structural fixes that make each agent's analysis substantially more
grounded, contextual, and visible in the final report.

### Added

**Fix 1 — Live tool registry snapshot in working memory** (`working_memory.py`, `base_agent.py`):
- `WorkingMemoryState` now has a `tool_registry_snapshot` field (list of dicts)
- `base_agent.run_investigation()` injects the live tool catalogue into working
  memory immediately after `build_tool_registry()` completes (Step 3b)
- `_get_available_tools_for_llm()` now reads from `state.tool_registry_snapshot`
  first — the LLM sees the actual registered tools with live availability status,
  not a static fallback list
- Unavailable tools are marked `available: false` in the snapshot so the LLM
  knows not to call them, preventing wasted ReAct iterations

**Fix 2 — LLM reasoning surfaced into findings** (`base_agent.py`):
- New `_attach_llm_reasoning_to_findings()` function runs after each ReAct loop
- Matches each `AgentFinding` to the THOUGHT step that immediately preceded its
  ACTION in the chain
- Stores full LLM thought in `finding.metadata["llm_reasoning"]`
- Extracts sentences containing anomaly signals (manipulat, inconsisten,
  suspicious, missing, unexpected, etc.) and prepends `[LLM] ...` to
  `finding.reasoning_summary` — so LLM insights appear in report cards
- Previously: LLM reasoning existed only in the raw chain log, invisible
  in the per-agent findings section of the report

**Fix 3 — Contextually-grounded initial thoughts** (all 5 agents):
All agents now call a fast pre-screen tool before the ReAct loop starts
and incorporate the real output into `build_initial_thought()`:
- Agent 1 (Image): `file_hash_verify` + `extract_evidence_text` (OCR word count)
- Agent 2 (Audio): `codec_fingerprinting` (codec, sample rate, encoding chain)
- Agent 3 (Scene): `scene_incongruence` (CLIP scene type, incongruent objects)
- Agent 4 (Video): `av_file_identity` (format, codec, fps, HIGH-SEVERITY flags)
- Agent 5 (Metadata): `exif_extract` (device, GPS presence, absent fields count)
- If a pre-screen reveals high-severity signals (VFR flag, absent EXIF, etc.),
  those are called out as IMMEDIATE PRIORITY in the opening thought

**Clean finding type labels** (`react_loop.py`):
- `_TOOL_LABELS` map gives every tool a clean, human-readable finding type
  (e.g. `"ELA — Image Manipulation"`, `"Face-Swap Detection"`)
- Previously: finding_type was the first 80 chars of the preceding THOUGHT,
  which was often verbose LLM reasoning or generic task text

**New tool interpreters** in `_build_readable_summary()`:
- `extract_evidence_text` / `extract_text_from_image`: word count + text preview
- `mediainfo_profile`: container format + forensic flags
- `av_file_identity`: codec + resolution + high-severity flags
- `noise_fingerprint`: PRNU inconsistency score with threshold interpretation
- `copy_move_detect`: keypoint match count + verdict
- `face_swap_detection`: face count + embedding distance
- `optical_flow_analyze`: anomalous frame count + discontinuity verdict
- `gps_timezone_validate`: consistency verdict + distance from expected zone
- `metadata_anomaly_score`: ML score + anomalous field list
- `speaker_diarize`: speaker count + segment count + speech duration
- `anti_spoofing_detect`: spoof score + genuine/synthetic verdict
- `file_hash_verify`: hash value + match status

---

## [0.9.0] — 2026-03-06

### Groq LLM Integration & Reasoning Overhaul

The LLM layer has been completely overhauled. Groq (Llama 3.3 70B) is now the
recommended and default provider, replacing the previous OpenAI default.
The system prompt, tool catalogue, Arbiter synthesis, and retry logic
have all been redesigned.

### Added

**Groq provider** (`LLM_PROVIDER=groq`):
- `llama-3.3-70b-versatile` as default model — ~700 tok/s vs ~80 tok/s on GPT-4o
- Full parallel function-calling support on Groq's hardware
- Free tier supports complete multi-agent investigations without cost
- `groq>=0.9` added to `pyproject.toml`

**Retry logic with exponential backoff** in `llm_client.py`:
- Retries on HTTP 429 (rate-limit), 500, 502, 503, 504
- Up to 3 attempts with 1s → 2s → 4s backoff
- Timeout retries with backoff for flaky connections

**`LLMClient.generate_synthesis()`** — single-shot non-ReAct generation:
- Used by the Arbiter for report writing; low temperature (0.2) for factual prose
- Shared across Groq, OpenAI, Anthropic providers

**Forensic system prompt** (`_build_forensic_system_prompt`):
- Agent-specific mandates: each of Agent 1–5 gets a role-specific forensic brief
- Evidence metadata in prompt: file name, MIME type, file size, SHA-256
- All outstanding tasks listed (previously capped at 5)
- Court-admissible reasoning standards: CONFIRMED vs INDICATIVE distinction
- Explicit completion signal: "ANALYSIS COMPLETE:" prefix
- Guidance on handling unavailable tools and ambiguous evidence

**Full tool catalogue in `_get_available_tools_for_llm()`**:
- Replaced hardcoded 10-item list with full 35-tool catalogue covering all 5 agents
- Reads from `state.tool_registry_snapshot` when available (live registry)
- Includes all v0.8.1 tools: `extract_evidence_text`, `mediainfo_profile`, `av_file_identity`

**LLM-powered Arbiter report synthesis** in `arbiter.py`:
- `_generate_executive_summary()` — calls LLM to write structured forensic prose from top findings
- `_generate_uncertainty_statement()` — LLM writes legally-aware limitations statement
- Both methods fall back gracefully to deterministic templates when LLM is unavailable
- `CouncilArbiter` now accepts `config: Settings` param; pipeline passes it automatically

**New task→tool overrides** in `_TASK_TOOL_OVERRIDES`:
- OCR: `extract evidence text`, `ocr text extraction`, `text from pdf`
- MediaInfo: `mediainfo`, `av container profiling`, `variable frame rate`, `av file identity`

**Enriched evidence context** passed to system prompt:
- `file_size_bytes` and `sha256` now included (read from `EvidenceArtifact`)

### Changed

- `config.py` `llm_provider` default: `openai` → `groq`
- `config.py` `llm_model` default: `gpt-4` → `llama-3.3-70b-versatile`
- `config.py` `llm_max_tokens` default: `2048` → `4096`
- `config.py` `llm_timeout` default: `60.0` → `30.0` (Groq is fast)
- `config.py` validator now explicitly accepts `groq | openai | anthropic | none` and rejects unknown providers with a helpful error
- `.env.example` updated: Groq is now the example provider with setup instructions
- `STARTUP.md`: new "Groq LLM Setup" section with quick-start guide and provider comparison table

### How to enable Groq

```bash
# 1. Get free API key at https://console.groq.com/keys
# 2. Set in .env:
LLM_PROVIDER=groq
LLM_API_KEY=gsk_your_key_here
LLM_MODEL=llama-3.3-70b-versatile
# 3. Restart
docker compose restart backend
```

---

## [0.8.1] — 2026-03-06

### Three-Tier OCR & AV Container Profiling

Adds deep file-content understanding so agents know what evidence files actually contain before analysis begins. All tools are lazy-loaded, non-blocking, and degrade gracefully — zero performance impact on builds or existing forensic workflows.

### Added

**`backend/tools/ocr_tools.py`** — Three-tier text extraction pipeline:
- **Tier 1 — PyMuPDF** (`fitz`): Lossless PDF embedded-text extraction (<50ms). Also extracts page count, embedded image count, and document metadata (title, author, creator, creation/mod dates, encryption status).
- **Tier 2 — EasyOCR**: Neural OCR for images — handles curved text, low-resolution forensic scans, uneven lighting, and mixed-language documents. CPU-only, no GPU required.
- **Tier 3 — Tesseract** (existing, upgraded): Fallback when EasyOCR is unavailable. Still used via `extract_text_from_image` for backward compatibility.
- `extract_evidence_text()` — unified auto-dispatching entry point; routes PDFs to PyMuPDF, images to EasyOCR→Tesseract, AV files to a skip result, unknown types to EasyOCR.

**`backend/tools/mediainfo_tools.py`** — Deep AV container profiling via MediaInfo:
- `profile_av_container()` — full container dissection: codec, resolution, frame rate mode (CFR vs VFR), bit depth, colour space, HDR flags, encoding tool, creation/tagged dates, track-level writing library.
- `get_av_file_identity()` — lightweight pre-screen returning only format, primary codec, duration, resolution, and HIGH-severity flags. Intended as fast pre-flight before heavy ML tools.
- Automated forensic flag detection: `VARIABLE_FRAME_RATE`, `TRACK_LIBRARY_MISMATCH`, `FUTURE_ENCODING_DATE`, `EDITING_SOFTWARE_DETECTED`, `CONTAINER_CODEC_MISMATCH`, `NO_CREATION_DATE`.

**New Docker named volume** — `easyocr_cache` → `/app/cache/easyocr`: EasyOCR model weights (~100MB) persist across rebuilds; download happens once on first OCR call.

**New env var** — `EASYOCR_MODEL_DIR=/app/cache/easyocr` set in Dockerfile and exported to all compose profiles.

### Wired into Agents

- **Agent 1 (Image)** — `extract_evidence_text` registered alongside existing `extract_text_from_image`. EasyOCR now handles image evidence with higher accuracy than Tesseract alone.
- **Agent 4 (Video)** — `mediainfo_profile` and `av_file_identity` registered. Container metadata is now available as a fast pre-screen before optical flow or face-swap analysis.
- **Agent 5 (Metadata)** — `extract_evidence_text`, `mediainfo_profile`, and `av_file_identity` all registered. Agent 5 can now correlate OCR-extracted document text with EXIF metadata and MediaInfo container signals for richer provenance analysis.

### Changed

- **`orchestration/pipeline.py` `_get_mime_type()`** — upgraded from extension-based lookup to `python-magic` (libmagic magic-byte detection). Extension-spoofed files (e.g. a video renamed to `.jpg`) are now correctly identified at ingest time. Extension fallback retained for robustness.
- **`backend/Dockerfile`** — added `libmediainfo-dev` (C library for pymediainfo) and `libmagic1` (C library for python-magic) to the apt install layer. Layer cache is not invalidated for unrelated changes.
- **`pyproject.toml`** — added `PyMuPDF>=1.24`, `easyocr>=1.7`, `pymediainfo>=6.1` to main dependencies.
- **`docs/start/STARTUP.md`** — model cache table updated to include `easyocr_cache` volume.

### Performance Notes

- PyMuPDF: <50ms per PDF, pure C, zero model loading.
- EasyOCR: First call per container start loads model from cache volume (~2s). Subsequent calls: <500ms per image.
- MediaInfo: <20ms per file, pure header parsing, no models.
- All three tools run in `ThreadPoolExecutor` workers — the FastAPI event loop is never blocked.
- No performance impact on investigations that don't involve text-bearing or AV evidence.

---

## [0.8.0] — 2026-03-06

### ✅ Final Release — v0.8.0

Complete audit, cleanup, and Docker hardening pass. All known issues resolved.
Full production-ready Docker stack with model caching, hot-reload dev mode, and comprehensive startup guide.

### Added
- `.env.example` and `backend/.env.example` — missing environment templates added
- `.gitignore` — comprehensive gitignore covering Python, Node, Docker, OS, and IDE artifacts
- `backend/.dockerignore` and `frontend/.dockerignore` — build context exclusion to speed up Docker builds
- `LICENSE` — MIT license file
- Frontend healthcheck in `docker-compose.yml` base config
- `docker-compose.dev.yml` — explicit ML model volume mounts so dev mode also benefits from model caching

### Changed
- **Version aligned to 0.8.0** across `pyproject.toml`, `package.json`, `api/main.py`
- **`docker-compose.dev.yml`** — added explicit named volume mounts for all ML caches (`hf_cache`, `torch_cache`, etc.) so models are preserved in dev mode, matching production behaviour
- **`docker-compose.prod.yml`** — clarified MODE A (local build) vs MODE B (registry image) workflows; added `depends_on` with healthchecks for Caddy service
- **`docs/start/STARTUP.md`** — full rewrite for v0.8.0: step-by-step from Step 0 (prerequisites) through healthy containers; covers production mode, development mode, no-cache rebuilds, model caching behaviour, and troubleshooting
- **`README.md`** — updated version badge, corrected compose command examples, added `.env.example` setup step
- **`Makefile`** — verified all targets consistent with docker-compose file paths

### Removed
- `$null` — stray PowerShell artifact file
- `backend/Dockerfile.bak` — backup Dockerfile no longer needed
- `COMPREHENSIVE_UPDATES_v4.md`, `CONTROL_FLOW_TESTING.md`, `DEVELOPER_SETUP_AND_HOTRELOAD.md` — superseded by STARTUP.md
- `DOCKER_BUILD.md`, `DOCKER_BUILD_VERIFICATION.md` — superseded by STARTUP.md
- `FINAL_RELEASE_v4.md`, `FIXES_AND_IMPROVEMENTS_v2.md` — stale release notes
- `IMPLEMENTATION_SUMMARY.md`, `PRODUCTION_READY.md`, `RESULT_PAGE_REDESIGN.md` — internal work docs not relevant to users

### Fixed
- **Docker model caching** — dev mode now mounts the same named volumes as production so ML models are never re-downloaded after the first build
- **`docker-compose.prod.yml`** — Caddy service was missing `depends_on` healthcheck conditions causing race conditions on cold start
- **Frontend healthcheck** — base compose was missing a healthcheck for the frontend service; added `node` HTTP probe

---

## [0.7.0] — 2026-03-04

### Fixed — Docker & Build (13 issues)
- Added `build:` context to backend and frontend services in `docker-compose.yml`
- Added `evidence_data` volume + keys bind-mount to fix `read_only: true` crash on first upload
- Added `libgl1` and `libglib2.0-0` to backend runner stage (OpenCV import fix)
- Pinned `uv` to `0.6.6` (was `latest`, non-deterministic)
- Removed conflicting `build:` block from `docker-compose.prod.yml` frontend service
- Added `SIGNING_KEY` `:?` guard — compose now aborts with a clear message if unset
- Added `HEALTHCHECK` instructions to both backend and frontend Dockerfiles
- Added `caddy_logs` volume for `/var/log/caddy` in production compose
- Removed nested `${JWT_SECRET_KEY:-${SIGNING_KEY}}` — `config.py` fallback handles this correctly
- Added `ports: 3000:3000` to frontend service in base compose
- Added `HF_TOKEN` to both dev and prod compose (required for `pyannote.audio`)
- Changed `npm install` to `npm ci` in frontend Dockerfile

### Fixed — Frontend App (7 issues)
- `startSimulation("pending")` now correctly triggers `"initiating"` status on the evidence page
- Fixed `URL.createObjectURL` memory leak — blob URL now derived via `useMemo` and revoked on cleanup
- Fixed CSS typo `linear_gradient` → `linear-gradient` on result page grid background
- Added `Poppins` font via `next/font/google` in `layout.tsx`
- Removed unused `AgentResult` import from `constants.ts`
- Removed redundant `env:` block from `next.config.ts`
- Throttled `"think"` sound to only play on new agent activation

### Fixed — Backend & Tests (5 issues)
- Added missing MIME types `.webp`, `.mkv`, `.flac` to `_get_mime_type()` in `pipeline.py`
- Fixed `SigningService` class reference in E2E tests
- Fixed EXIF bytes/string comparison in test fixtures
- Updated test to accept `401` or `422` on auth-required endpoints

---

## [0.6.0] — 2026-03-02

### Added
- Multi-Agent Core Pipeline: Sequential execution loop for 5 active agents
- Arbiter Synthesis Module: Cross-modal findings → cohesive verdicts
- ML Subsystem: Deepfake detection, ELA, noise fingerprinting as secure subprocesses
- WebSocket Streaming: Live THOUGHT and ACTION blocks to frontend
- Human-In-The-Loop (HITL): Webhook support for operator decisions
- Deterministic Cryptography: ECDSA-signed reports from `SIGNING_KEY`

### Changed
- Memory Management: Redis models with 24-hour TTLs
- Container Architecture: Optimized Docker builds using `uv`
- UI Aesthetics: Tailwind v4 + Framer Motion

### Fixed
- CORS blocking bugs via standardizing `NEXT_PUBLIC_API_URL`
- AttributeErrors in backend ML handlers

---

## [0.1.0] — Initial Alpha

### Added
- Initial FastAPI backend and standalone React interface
- Basic routing and placeholder endpoints for single-agent analysis
