from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.media_kind import (
    is_camera_still_candidate,
    is_digitally_created_image,
    is_document_like,
    is_recompressed_web_image,
    is_screen_capture_like,
)
from core.structured_logging import get_logger

logger = get_logger(__name__)


@dataclass
class FileClassification:
    primary_category: str
    confidence: float
    detection_signals: dict[str, bool] = field(default_factory=dict)
    recommended_tools: list[str] = field(default_factory=list)
    skip_tools: list[str] = field(default_factory=list)


CATEGORY_TO_RECOMMENDED_TOOLS: dict[str, list[str]] = {
    "screenshot": [
        "file_hash_verify",
        "visual_evidence_profile",
        "extract_text_from_image",
        "analyze_image_content",
        "detect_font_inconsistency",
        "detect_ui_overlay_forgery",
        "frequency_domain_analysis",
    ],
    "document": [
        "file_hash_verify",
        "visual_evidence_profile",
        "extract_text_from_image",
        "analyze_image_content",
        "frequency_domain_analysis",
        "neural_ela",
    ],
    "ai_generated_suspect": [
        "file_hash_verify",
        "visual_evidence_profile",
        "analyze_image_content",
        "frequency_domain_analysis",
        "diffusion_artifact_detector",
        "deepfake_frequency_check",
        "synthid_watermark_detect",
    ],
    "web_image": [
        "file_hash_verify",
        "visual_evidence_profile",
        "neural_ela",
        "analyze_image_content",
        "frequency_domain_analysis",
        "neural_fingerprint",
    ],
    "object_scene": [
        "file_hash_verify",
        "visual_evidence_profile",
        "neural_ela",
        "analyze_image_content",
        "frequency_domain_analysis",
        "neural_fingerprint",
    ],
    "live_photograph": [
        "file_hash_verify",
        "visual_evidence_profile",
        "neural_ela",
        "analyze_image_content",
        "frequency_domain_analysis",
        "neural_fingerprint",
    ],
}

CATEGORY_TO_SKIP_TOOLS: dict[str, list[str]] = {
    "screenshot": [
        "neural_ela",
        "ela_full_image",
        "jpeg_ghost_detect",
        "noiseprint_cluster",
        "noise_fingerprint",
        "neural_splicing",
        "neural_copy_move",
    ],
    "document": [
        "detect_font_inconsistency",
        "detect_ui_overlay_forgery",
        "noiseprint_cluster",
        "noise_fingerprint",
    ],
    "ai_generated_suspect": [
        "noiseprint_cluster",
        "noise_fingerprint",
        "jpeg_ghost_detect",
    ],
    "web_image": [
        "detect_font_inconsistency",
        "detect_ui_overlay_forgery",
    ],
    "object_scene": [
        "detect_font_inconsistency",
        "detect_ui_overlay_forgery",
    ],
    "live_photograph": [
        "detect_font_inconsistency",
        "detect_ui_overlay_forgery",
    ],
}


async def classify_evidence_file(artifact: Any) -> FileClassification:
    signals = {
        "has_camera_exif": _check_camera_exif(artifact),
        "has_screenshot_dimensions": _check_screenshot_dimensions(artifact),
        "is_document_like": is_document_like(artifact),
        "is_screen_capture_like": is_screen_capture_like(artifact),
        "is_digitally_created": is_digitally_created_image(artifact),
        "is_camera_candidate": is_camera_still_candidate(artifact),
        "is_recompressed_web": is_recompressed_web_image(artifact),
    }

    category, confidence = _score_signals(signals)

    recommended = list(CATEGORY_TO_RECOMMENDED_TOOLS.get(category, CATEGORY_TO_RECOMMENDED_TOOLS["live_photograph"]))
    skip = list(CATEGORY_TO_SKIP_TOOLS.get(category, []))

    logger.info(
        "File classified",
        category=category,
        confidence=confidence,
        signals=signals,
    )

    return FileClassification(
        primary_category=category,
        confidence=confidence,
        detection_signals=signals,
        recommended_tools=recommended,
        skip_tools=skip,
    )


def _check_camera_exif(artifact: Any) -> bool:
    from core.media_kind import _image_probe
    file_path = str(getattr(artifact, "file_path", "") or "")
    if not file_path:
        return False
    probe = _image_probe(file_path)
    return bool(probe.get("has_camera_tags"))


def _check_screenshot_dimensions(artifact: Any) -> bool:
    from core.media_kind import _image_probe
    file_path = str(getattr(artifact, "file_path", "") or "")
    if not file_path:
        return False
    probe = _image_probe(file_path)
    width = int(probe.get("width") or 0)
    height = int(probe.get("height") or 0)
    if width < 600 or height < 350:
        return False
    aspect = width / max(height, 1)
    common_axis = any(
        v in {720, 768, 800, 900, 1024, 1080, 1170, 1179, 1200, 1284, 1290,
              1440, 1600, 2160, 2340, 2400, 2532, 2556, 2664, 2796, 3088}
        for v in (width, height)
    )
    return common_axis or (1.15 <= aspect <= 2.5) or (0.4 <= aspect <= 0.75)


def _score_signals(signals: dict[str, bool]) -> tuple[str, float]:
    if signals["is_screen_capture_like"] and signals["has_screenshot_dimensions"]:
        return "screenshot", 0.90

    if signals["is_screen_capture_like"]:
        return "screenshot", 0.80

    if signals["is_digitally_created"] and signals["has_screenshot_dimensions"]:
        return "screenshot", 0.75

    if signals["is_document_like"]:
        return "document", 0.80

    if signals["is_recompressed_web"]:
        return "web_image", 0.75

    if signals["is_camera_candidate"] and signals["has_camera_exif"]:
        return "live_photograph", 0.85

    if signals["is_camera_candidate"]:
        return "live_photograph", 0.70

    return "live_photograph", 0.55
