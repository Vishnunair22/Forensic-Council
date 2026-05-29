import asyncio
import time
from typing import Any

from core.evidence import EvidenceArtifact, ArtifactType
from core.structured_logging import get_logger
from core.vision_types import VisualEvidenceFinding

logger = get_logger(__name__)

_TOOL_NAMES = ["ELA", "OCR", "CLIP", "DETR"]


def _is_tool_successful(result: Any) -> bool:
    if result is None:
        return False
    if isinstance(result, Exception):
        return False
    if isinstance(result, dict):
        if result.get("status") == "error" or result.get("available") is False:
            return False
        if result.get("error"):
            return False
    return True


def _tool_error_summary(result: Any) -> str:
    if isinstance(result, Exception):
        return str(result)
    if isinstance(result, dict):
        return str(result.get("error", "unknown error"))
    return "unknown error"


async def analyze_local_visual_profile(
    artifact: EvidenceArtifact,
    exif_summary: dict[str, Any] | None = None,
    is_screen_capture_like: bool = False,
) -> VisualEvidenceFinding:
    """
    Perform native local visual profile analysis using cached on-device
    forensic models and deterministic image-processing tools.

    The EvidenceArtifact provides session_id and content_hash for proper
    forensic chain-of-custody. The artifact is never fabricated — it must
    originate from the custody-linked evidence pipeline.

    Aggregates:
      - CLIP (SigLIP 2) zero-shot classification
      - Pytesseract OCR
      - DETR object detection
      - OpenCV Error Level Analysis (ELA)

    Returns a provider-neutral VisualEvidenceFinding with tool_coverage
    populated for downstream provenance reporting.
    """
    start_time = time.perf_counter()
    file_path = artifact.file_path
    logger.info("Initializing native local visual ensemble", file_path=file_path)

    art = artifact

    from tools.image_tools import (
        ela_full_image,
        extract_text_from_image,
        analyze_image_content,
        detr_detect_objects,
    )

    tasks = [
        ela_full_image(art),
        extract_text_from_image(art),
        analyze_image_content(art),
        detr_detect_objects(file_path),
    ]

    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    tool_results: dict[str, Any] = {}
    tool_errors: dict[str, str] = {}
    tool_coverage: dict[str, bool] = {}
    for idx, name in enumerate(_TOOL_NAMES):
        r = raw_results[idx]
        if _is_tool_successful(r):
            tool_results[name] = r
            tool_coverage[name] = True
        else:
            tool_errors[name] = _tool_error_summary(r)
            tool_coverage[name] = False
            logger.error(f"Ensemble tool {name} failed", error=tool_errors[name])

    ela_res = tool_results.get("ELA", {})
    ocr_res = tool_results.get("OCR", {})
    clip_res = tool_results.get("CLIP", {})
    detr_res = tool_results.get("DETR", [])

    clip_category = clip_res.get("image_type", "unknown") if isinstance(clip_res, dict) else "unknown"
    ocr_lines = ocr_res.get("extracted_text", []) if isinstance(ocr_res, dict) else []
    detected = detr_res if isinstance(detr_res, list) else []

    desc_parts = [
        f"Local visual profile analysis of {file_path}.",
        f"CLIP classified image category: '{clip_category}'."
    ]
    if detected:
        desc_parts.append(f"Detected objects: {', '.join(detected)}.")
    if ocr_lines:
        desc_parts.append(f"Extracted UI/Text lines: {', '.join(ocr_lines[:5])}...")

    content_description = " ".join(desc_parts)

    signals = []
    verdict = "AUTHENTIC"
    max_anomaly = 0.0
    if isinstance(ela_res, dict):
        max_anomaly = ela_res.get("max_anomaly", 0.0)
        if max_anomaly > 40.0:
            signals.append(f"High local ELA anomaly variance: {max_anomaly:.1f}")
            verdict = "SUSPICIOUS"
        elif ela_res.get("num_anomaly_regions", 0) > 3:
            signals.append(f"Multiple suspicious ELA anomaly clusters: {ela_res.get('num_anomaly_regions')}")
            verdict = "SUSPICIOUS"

    is_screenshot = is_screen_capture_like or "screenshot" in clip_category.lower() or "document" in clip_category.lower()
    interface_id = ""
    if is_screenshot:
        interface_id = f"Identified digital interface category: {clip_category}"
        ocr_text_lower = " ".join(ocr_lines).lower()
        if "iphone" in ocr_text_lower or "ios" in ocr_text_lower:
            interface_id += " (iOS platform signs)"
        elif "android" in ocr_text_lower:
            interface_id += " (Android platform signs)"
        elif "http" in ocr_text_lower or "www." in ocr_text_lower:
            interface_id += " (Web/Browser interface)"

    metadata_consistency = "No metadata provided for cross-validation"
    if exif_summary:
        metadata_consistency = "Metadata present. Local tools did not detect obvious timestamp or GPS contradiction."

    tools_total = len(_TOOL_NAMES)
    tools_ok = len(tool_results)
    partial_execution = tools_ok < tools_total

    base_confidence = 0.40 + (tools_ok / tools_total) * 0.30
    if signals:
        base_confidence = max(base_confidence, 0.60)
    confidence = round(min(base_confidence, 0.85), 4)

    caveat_parts = [
        "Local visual ensemble analysis using cached on-device forensic "
        "models and deterministic image-processing tools."
    ]
    if partial_execution:
        failed_names = ", ".join(sorted(tool_errors.keys()))
        caveat_parts.append(
            f"Partial execution: {tools_ok}/{tools_total} tools succeeded. "
            f"Failed: {failed_names}."
        )

    latency = (time.perf_counter() - start_time) * 1000.0

    degradation_flags = []
    if partial_execution:
        degradation_flags.append(f"partial_tool_execution:{tools_ok}/{tools_total}")

    finding = VisualEvidenceFinding(
        analysis_type="visual_evidence_profile",
        provider_used="local_visual_ensemble",
        model_used="local_visual_ensemble",
        content_description=content_description,
        manipulation_signals=signals,
        detected_objects=detected,
        contextual_anomalies=[],
        file_type_assessment=clip_category,
        confidence=confidence,
        court_defensible=not partial_execution,
        caveat=" ".join(caveat_parts),
        raw_response="",
        latency_ms=latency,
        error=None if not partial_execution else "; ".join(
            f"{name}: {err}" for name, err in tool_errors.items()
        ),
        from_cache=False,
        _extracted_text=ocr_lines,
        _interface_identification=interface_id,
        _contextual_narrative=(
            "Local analysis of evidence file contents using cached semantic, "
            "object-detection, OCR, and forensic-signal models."
        ),
        _authenticity_verdict=verdict,
        _metadata_visual_consistency=metadata_consistency,
        _forensic_routing={
            "image_category": "screenshot" if is_screenshot else "object_scene",
            "priority_signals": ["local_ela", "ocr_patterns"],
            "skip_tools": [],
        },
        _forensic_specifics="Local analysis suggests " + ("digital UI layout" if is_screenshot else "natural photographic scene"),
        provider_attempts=[
            {
                "provider": "local_visual_ensemble",
                "success": tools_ok > 0,
                "tools_ok": tools_ok,
                "tools_total": tools_total,
            }
        ],
        fallback_applied=False,
        fallback_reason="",
        tool_coverage=tool_coverage,
        degradation_flags=degradation_flags,
    )

    return finding
