# Phase 03: Quality Audit & Cleanup - Research

## Objective
Identify gaps in test coverage, linting, and type auditing to ensure the Forensic Council codebase transitions from "functional" to "production-grade".

## Current State Analysis
- **Test Coverage**: 52.37% (Target: 60% minimum, 80%+ for critical paths).
- **Critical Gaps**:
    - `tools/ocr_tools.py`: 11% coverage. Missing PDF extraction logic tests, EasyOCR integration tests.
    - `tools/video_tools.py`: 6% coverage. Optical flow, frame consistency, and face swap detection are virtually untested.
    - `agents/agent4_video.py`: Low coverage (inferred).
    - `core/auth.py`: Needs verification for RS256 and `aud` enforcement.
- **Linting**: Existing `ruff` and `pyright` configs exist but may have accumulated warnings during refactor.
- **Types**: Strict typing exists but many `Any` usages remain in tool results and agent contexts.

## Technical Approach

### 1. OCR Tool Testing
- **Strategy**: Use specialized mock binaries for PDF and images.
- **Dependencies**: `PyMuPDF` (fitz), `EasyOCR`.
- **Mocking**: Mock `easyocr.Reader` to return predictable bounding boxes and text. Use a tiny 1-page PDF artifact for `fitz` tests.

### 2. Video Tool Testing
- **Strategy**: Use `OpenCV` to generate synthetic gray-scale videos with known motion for optical flow testing.
- **Scenarios**:
    - Video with uniform gray: zero motion.
    - Video with moving white square: predictable optical flow.
    - Spliced video: test `frame_consistency_analyze` for histogram jumps.

### 3. Auth & Security Hardening
- **Strategy**: Unit tests for `RS256` transition.
- **Verification**: Ensure `jwt.decode` fails if `aud` is missing or mismatched. Test key rotation logic.

### 4. Integration Consistency
- **Strategy**: Test `InterAgentBus` with all 5 agents registered.
- **Scenario**: Verify Agent 1 context injection into Agents 3 and 5 works as expected (multi-agent orchestration).

## Validation Architecture
- **Dimension 1 (Coverage)**: 60% global threshold via `pytest-cov`.
- **Dimension 2 (Foundational)**: `auth.py` and `signing.py` must have 95%+ coverage.
- **Dimension 3 (Static)**: `pyright` and `ruff` must pass with 0 errors.

## Success Criteria
1. Global coverage >= 60%.
2. Critical tools (OCR, Video) >= 70%.
3. No `pyright` errors in `apps/api/core/`.
4. Auth tests cover RS256 and `aud` validation.
