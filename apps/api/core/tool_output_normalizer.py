from __future__ import annotations

from typing import Any, Literal, List, Dict, Optional
from pydantic import BaseModel, Field

from core.tool_output_classifier import ToolOutputClassifier
from core.structured_logging import get_logger

logger = get_logger(__name__)

class ToolOutputEnvelope(BaseModel):
    tool_name: str
    available: bool = True
    status: Literal[
        "SUCCESS",
        "NEGATIVE",
        "POSITIVE",
        "INCONCLUSIVE",
        "NOT_APPLICABLE",
        "ERROR",
        "TIMEOUT",
    ]
    signal_category: str
    evidence_verdict: Literal[
        "POSITIVE",
        "NEGATIVE",
        "INCONCLUSIVE",
        "NOT_APPLICABLE",
        "ERROR",
    ]
    confidence: float | None = None
    court_defensible: bool = False
    summary: str = ""
    measurements: Dict[str, Any] = Field(default_factory=dict)
    regions: List[Dict[str, Any]] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    raw: Dict[str, Any] = Field(default_factory=dict)

TOOL_SIGNAL_CATEGORIES = {
    # Agent 1 (Pixel Integrity)
    "ela_full_image": "pixel_integrity",
    "ela_anomaly_classify": "pixel_integrity",
    "roi_extract": "pixel_integrity",
    "jpeg_ghost_detect": "pixel_integrity",
    "frequency_domain_analysis": "pixel_integrity",
    "splicing_detect": "pixel_integrity",
    "noise_fingerprint": "pixel_integrity",
    "noiseprint_cluster": "pixel_integrity",
    "deepfake_frequency_check": "pixel_integrity",
    "neural_fingerprint": "pixel_integrity",
    "neural_copy_move": "pixel_integrity",
    "neural_splicing": "pixel_integrity",
    "detect_font_inconsistency": "pixel_integrity",
    "detect_ui_overlay_forgery": "pixel_integrity",
    # Agent 3 (Scene / Objects)
    "object_detection": "scene_integrity",
    "lighting_consistency": "scene_integrity",
    "scene_incongruence": "scene_integrity",
    "vector_contraband_search": "scene_integrity",
    "scale_validation": "scene_integrity",
    "screenshot_scene_applicability": "scene_integrity",
    "screenshot_layout_forensics": "scene_integrity",
    "secondary_classification": "scene_integrity",
    # Agent 5 (Metadata)
    "exif_extract": "metadata_integrity",
    "metadata_anomaly_score": "metadata_integrity",
    "gps_timezone_validate": "metadata_integrity",
    "file_structure_analysis": "metadata_integrity",
    "hex_signature_scan": "metadata_integrity",
    "timestamp_analysis": "metadata_integrity",
    "exif_isolation_forest": "metadata_integrity",
    "astro_grounding": "metadata_integrity",
}

def normalize_tool_output(
    tool_name: str,
    output: Any,
    available: bool = True,
    agent_id: str = ""
) -> ToolOutputEnvelope:
    """
    Standardize the raw result of any forensic tool into a ToolOutputEnvelope.
    Guarantees consistent, court-defensible structure.
    """
    raw_dict = {}
    if isinstance(output, dict):
        raw_dict = output
    else:
        raw_dict = {"output_raw": str(output)}

    # Determine signal category
    signal_cat = TOOL_SIGNAL_CATEGORIES.get(tool_name, "general")

    # If it is a timeout / error from the ReActLoopEngine or tool runner
    is_timeout = raw_dict.get("status") == "TIMEOUT" or "timeout" in str(raw_dict.get("error", "")).lower()
    is_error = raw_dict.get("error") is not None or not available

    if is_timeout:
        return ToolOutputEnvelope(
            tool_name=tool_name,
            available=available,
            status="TIMEOUT",
            signal_category=signal_cat,
            evidence_verdict="ERROR",
            confidence=None,
            court_defensible=False,
            summary=f"Tool {tool_name} execution timed out.",
            raw=raw_dict
        )

    if is_error:
        err_msg = str(raw_dict.get("error", "Unknown error or tool unavailable"))
        return ToolOutputEnvelope(
            tool_name=tool_name,
            available=available,
            status="ERROR",
            signal_category=signal_cat,
            evidence_verdict="ERROR",
            confidence=None,
            court_defensible=False,
            summary=f"Tool {tool_name} failed: {err_msg}",
            raw=raw_dict
        )

    # Classify verdict & confidence using ToolOutputClassifier
    confidence, conf_fallback = ToolOutputClassifier.extract_confidence(raw_dict, tool_name, agent_id)
    status_val, verdict_val, final_conf, court_def = ToolOutputClassifier.classify(
        raw_dict, tool_name, confidence, conf_fallback
    )

    # Map verdict_val to envelope status
    status_map = {
        "POSITIVE": "POSITIVE",
        "NEGATIVE": "NEGATIVE",
        "INCONCLUSIVE": "INCONCLUSIVE",
        "NOT_APPLICABLE": "NOT_APPLICABLE",
        "ERROR": "ERROR"
    }
    env_status = status_map.get(verdict_val, "INCONCLUSIVE")

    # Extract measurements (numerical outputs, confidence scores, etc.)
    measurements = {}
    for k, v in raw_dict.items():
        if k in [
            "anomaly_score", "tampering_score", "synthetic_probability", "forgery_score",
            "diffusion_probability", "noise_consistency_score", "consistency_score",
            "overall_consistency", "avg_confidence", "score", "probability", "similarity",
            "elapsed_time", "time_taken", "num_anomaly_regions"
        ] or (isinstance(v, (int, float)) and k not in ["confidence", "court_defensible"]):
            measurements[k] = v

    # Extract regions (bounding boxes, localized anomalies)
    regions = []
    for rkey in ["regions", "roi_boxes", "detections", "weapon_detections", "contraband_detections", "anomalies"]:
        if rkey in raw_dict and isinstance(raw_dict[rkey], list):
            for idx, item in enumerate(raw_dict[rkey]):
                if isinstance(item, dict):
                    regions.append(item)
                elif isinstance(item, (list, tuple)) and len(item) == 4:
                    regions.append({"box": list(item), "index": idx})

    # Extract limitations and warnings
    limitations = []
    if "limitations" in raw_dict and isinstance(raw_dict["limitations"], list):
        limitations.extend([str(l) for l in raw_dict["limitations"]])
    for wkey in ["warning", "note", "skipped_reason", "file_format_note", "limitation_note"]:
        if wkey in raw_dict and raw_dict[wkey]:
            limitations.append(str(raw_dict[wkey]))

    # Construct clean summary
    summary = str(raw_dict.get("summary", ""))
    if not summary:
        if env_status == "POSITIVE":
            summary = f"Forensic signal identified by {tool_name} with confidence {final_conf}."
        elif env_status == "NEGATIVE":
            summary = f"No forensic anomaly detected by {tool_name}."
        elif env_status == "NOT_APPLICABLE":
            summary = f"{tool_name} was not applicable to the evidence format or constraints."
        else:
            summary = f"{tool_name} completed with inconclusive or mixed results."

    return ToolOutputEnvelope(
        tool_name=tool_name,
        available=available,
        status=env_status,
        signal_category=signal_cat,
        evidence_verdict=verdict_val,
        confidence=final_conf,
        court_defensible=court_def,
        summary=summary,
        measurements=measurements,
        regions=regions,
        limitations=limitations,
        raw=raw_dict
    )
