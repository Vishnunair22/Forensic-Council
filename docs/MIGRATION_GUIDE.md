# Migration Guide — v1.7.0 to v1.8.0

## Overview

This release introduces two new forensic tools for screenshot analysis and file-type-aware arbiter thresholds. No breaking schema changes are introduced.

## New Files

| File | Purpose |
|------|---------|
| `apps/api/tools/screenshot_tools.py` | Screenshot forensics: font inconsistency and UI overlay forgery detectors |
| `apps/api/tests/forensics/` | New test directory for forensic tool tests |

## Behavioral Changes

### 1. ELA now runs on lossless images

**Before (v1.7.0):** `ela_full_image` raised `ToolUnavailableError` for lossless formats (PNG, BMP, TIFF, WebP), stating that ELA is only meaningful for JPEG images.

**After (v1.8.0):** `ela_full_image` runs on lossless images with an adjusted anomaly threshold (default 5.0 instead of 10.0). Results include a `lossless_interpretation` field explaining that high residuals indicate copy-paste or format conversion boundaries, not JPEG compression artifacts.

**What to check:** If your code relies on ELA raising an error for PNG inputs, update it to handle the new result format. The `available` key is still `True` and results include `lossless_interpretation` when the source is lossless.

### 2. Arbiter verdict thresholds depend on file type

**Before (v1.7.0):** All image types used the same verdict thresholds (MANIPULATED at 0.72, LIKELY_MANIPULATED at 0.55, SUSPICIOUS at 0.45).

**After (v1.8.0):** Lossless formats (PNG, WebP, BMP, GIF) use higher thresholds:
- MANIPULATED: 0.85 (was 0.72)
- LIKELY_MANIPULATED: 0.70 (was 0.55)
- SUSPICIOUS: 0.55 (was 0.45)

JPEG thresholds remain unchanged.

**What to check:** If you have tests that assert specific verdicts for PNG images at particular confidence levels, update the expected verdicts based on the new thresholds.

### 3. JPEG ghost is court-defensible on PNG

**Before (v1.7.0):** `jpeg_ghost_detect` returned `court_defensible: False` for PNG images.

**After (v1.8.0):** `jpeg_ghost_detect` returns `court_defensible: True` for PNG images, with appropriate caveats in the forensic note.

### 4. Screenshot classification triggers additional analysis

**Before (v1.7.0):** When `analyze_image_content` classified an image as a screenshot, no additional tasks were scheduled.

**After (v1.8.0):** When the classification contains "screenshot" or "screen capture", Agent1 automatically injects `detect_font_inconsistency` and `detect_ui_overlay_forgery` tasks (priority 13).

## Configuration Changes

None. All new features are enabled by default.

## API Changes

No new API endpoints. New tools are accessible through the existing agent tool execution pipeline.

## Database Changes

None.

## Deprecations

None.
