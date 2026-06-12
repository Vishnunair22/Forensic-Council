# Changelog

## [v1.9.0] - 2026-06-12

CPU / free-tier elevation: makes the verdict math defensible, the confidence
numbers honest, the LLM layer non-degrading, and the report court-grade — all
within CPU-only inference and Gemini/Groq free tiers. (Folds in the former
`ELEVATION_PLAN_CPU_FREE_TIER.md` and `CALIBRATION_PLAN.md`, now removed.)

### Added
- **Capability manifest per investigation** (`core/capability_manifest.py`): snapshots every applicable tool as `{ran, failed, gated_off, model_unavailable}` plus model name/version, embedded in the signed report. Drives the Methodology and Limitations sections and truthful tool naming.
- **Per-tool threshold sweep** (`scripts/run_threshold_sweep.py`): ROC table + AUC + operating thresholds at FPR ≤ 0.05 / 0.01 from a `score,label` CSV, for disclosing measured per-tool error rates.
- **End-to-end calibration runner** (`scripts/run_agent_calibration.py`): one command chains collect → sweep → validate → gated-train; persists a model only on an `ADOPT` verdict *and* explicit `--adopt`. See `docs/CALIBRATION_RUNBOOK.md`.
- **AI-text detector** (`tools/ml_tools/ai_text_detector.py`) wired into the collector — Agent5 (text) is now calibratable; **Agent5 is TRAINED+ADOPTED** on HC3 (`storage/calibration_models/Agent5/`).
- **DeepFace face-swap detection** wired into Agent4's production path (CPU-fine on sampled frames).
- **TruFor localization heatmaps** (Phase 3.4): the per-pixel forgery-probability map is colour-mapped, overlaid on the evidence, and surfaced inline in the report/UI (`AgentFindingCard`) via finding metadata — the base64 image is isolated from LLM/narrative extraction.
- **Report sections**: Methodology (from the manifest), qualitative likelihood-ratio language, auto-generated Limitations, Reproducibility block, and a calibration disclosure block (court-inadmissibility statement for UNCALIBRATED agents; dataset+version citation for TRAINED agents).

### Changed
- **EXIF anomaly scoring** (`tools/ml_tools/exif_isolation_forest.py`): replaced the runtime 5-row IsolationForest fit with transparent rule scores; absent metadata is now INFO, not a forced anomaly (kills the screenshot/social-export false positive).
- **Verdict engine** (`agents/arbiter_verdict.py`, `core/forensic_policy.py`): signal-family fusion (correlated recompression tools counted once), a tiered single-signal rule (validated tools can reach SUSPICIOUS alone; weak tools need a different-family corroborator), and tool weights/severity bands re-derived from measured AUC instead of unsourced defaults.
- **Lost-coverage handling** (`core/arbiter_deliberation.py`): a failed/gated *critical* tool reads as "could not be verified", not "no anomaly" — removing the silent-clean bias.
- **Screenshot gating** is now applied in `compute_agent_verdict` (`core/severity.py`), so agent-phase verdicts agree with the final arbiter verdict.
- **LLM layer** (`core/synthesis.py`, `agents/arbiter.py`, `core/quota_manager.py`, `core/provider_quota_guard.py`): batch synthesis is canonical (1 Groq call, not 5), job-based model routing, a per-investigation token budget that falls back to template *with a provenance tag* rather than silently, and Redis-backed quota state. Enum-constrained JSON everywhere; the substring-keyword taxonomy is demoted to a legacy fallback.
- **Truthful tool naming** (`core/finding_formatter.py`): `neural_*` / `f3_net` / `mantra` / `synthid` tools state the method that actually ran when research weights are not loaded.

### Fixed
- **`fit_platt` ran gradient *ascent*** (`scripts/train_calibration.py`): the sign was inverted for the `p = 1/(1+exp(A·x+B))` parameterisation, so `A` diverged and any "calibrated" model was random (`A=+954, acc=0.500`). Corrected to descent (`A=-17, acc≈1.0, ECE 0.218→0.029`), with tuned `lr`/`max_iter` and a gradient-norm stop. Any model trained before this fix must be discarded and refit; on-disk UNCALIBRATED defaults were unaffected.
- Verdict↔confidence pinning: removed the fabricated ~98% confidence floor on clean files.

### Removed
- Audit/scratch artifacts and standalone planning docs (`ELEVATION_PLAN_CPU_FREE_TIER.md`, `CALIBRATION_PLAN.md`, `docs/audits/`) — completed and folded here. Tracked one-off audit scripts (`scripts/*_audit.py`, `apps/api/test_scripts/`) removed.

## [v1.8.0] - 2026-05-28

### Added
- **Issue #25: Screenshot-specific forensic tools**
  - `detect_font_inconsistency`: Analyzes stroke-width variance and edge-density across OCR-identified text regions to detect font mismatches in fake tweet / edited screenshot images
  - `detect_ui_overlay_forgery`: Detects solid-color banner overlays (fake notification bars, edited buttons) via contour analysis and color uniformity checks
  - Both tools registered in `core/handlers/image.py` with court-defensible certificates
  - Reactive task injection in `Agent1Image._on_tool_result_impl` — when `analyze_image_content` classifies an image as "screen capture" or "screenshot", font and UI overlay analysis tasks are automatically queued

- **Issue #16: File-type-aware arbiter thresholds**
  - `Arbiter._compute_verdict` now accepts an `artifact_mime` parameter and adjusts verdict thresholds based on file type:
    - Lossless formats (PNG, WebP, BMP, GIF): MANIPULATED at 0.85, LIKELY_MANIPULATED at 0.70, SUSPICIOUS at 0.55
    - JPEG: MANIPULATED at 0.72, LIKELY_MANIPULATED at 0.55, SUSPICIOUS at 0.45
  - `artifact_mime` threaded through `pipeline.py`: `_run_deliberation` -> `_run_arbiter_pre_warm` -> `Arbiter.deliberate` -> `finalise_from_cache` -> `pre_warm` -> `_compute_verdict`
  - `pipeline.py` stores `_evidence_mime` from evidence artifact on pipeline start

- **Phase 4: Test suites**
  - `tests/forensics/test_screenshot_analysis.py`: 6 tests for font inconsistency and UI overlay forgery detectors
  - `tests/forensics/test_weapon_detection.py`: 4 tests for CLIP category prioritization and Agent3/Agent1 weapon escalation
  - `tests/forensics/test_png_forensics.py`: 4 tests for ELA on lossless images and screenshot-triggered reactive tasks
  - `tests/forensics/test_timeout_handling.py`: 4 tests for ML subprocess timeouts, agent timeouts, memory limits, and OCR resolution scaling
  - `tests/integration/test_end_to_end_png.py`: End-to-end PNG/lossless ELA, ghost detection, and arbiter thresholds
  - `tests/integration/test_end_to_end_weapon.py`: Integration tests for weapon detection pipeline, CLIP categories, and evidence store extension preservation
  - `tests/integration/test_reconnect_replay.py`: WebSocket replay buffer TTL and max-length validation

### Changed
- **Lossless ELA behavior**: `ela_full_image` now runs on lossless images (PNG, BMP, TIFF, WebP) with an adjusted anomaly threshold (`anomaly_threshold * 0.5` or default 5.0). Results include a `lossless_interpretation` key explaining that high residual values indicate copy-paste or format conversion boundaries rather than JPEG compression artifacts.
- **JPEG ghost on lossless sources**: `jpeg_ghost_detect` now marks results as court-defensible when run on PNG images, with appropriate caveats about lossless source interpretation.
- **Weapon categories prioritized**: `CLIPImageAnalyzer.DEFAULT_IMAGE_CATEGORIES` reordered to list weapon types first (knife, gun, firearm, weapon, etc.) followed by general categories.

### Fixed
- Reactive task injection in `Agent1Image` now correctly checks for "screen capture" classification to trigger font and UI overlay analysis
- `Arbiter._compute_verdict` correctly receives file-type information through the full deliberation pipeline
- Test import hygiene: removed raw `__import__("PIL")` calls in integration tests, replaced with proper `from PIL import ImageDraw` imports

### Known Issues
- Pre-existing `_append_chunk` import error in `api/routes/investigation.py` affects `test_investigation_start_flow.py` and WebSocket integration tests (`test_replay_buffer_stores_messages`, `test_replay_messages_sent_on_websocket_connect`). These tests are skipped when the import fails.
