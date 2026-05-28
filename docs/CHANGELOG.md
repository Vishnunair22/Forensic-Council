# Changelog

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
