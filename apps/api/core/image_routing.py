from __future__ import annotations

from pathlib import Path
from typing import Any

from core.file_classifier import CATEGORY_TO_RECOMMENDED_TOOLS, CATEGORY_TO_SKIP_TOOLS

TOOL_TO_TASK_DESCRIPTION: dict[str, str] = {
    "neural_ela": "Run neural_ela for high-confidence manipulation detection",
    "neural_fingerprint": "Run neural_fingerprint for conceptual similarity detection",
    "frequency_domain_analysis": "Run frequency_domain_analysis for frequency domain analysis",
    "noiseprint_cluster": "Run noiseprint_cluster for sensor-region source inconsistency",
    "detect_font_inconsistency": "Run detect_font_inconsistency for screenshot text font analysis",
    "detect_ui_overlay_forgery": "Run detect_ui_overlay_forgery for screenshot UI overlay analysis",
    "diffusion_artifact_detector": "Run diffusion_artifact_detector to confirm AI generation",
    "deepfake_frequency_check": "Run deepfake_frequency_check for GAN/Diffusion artifacts",
    "synthid_watermark_detect": "Run synthid_watermark_detect for SynthID and AI watermark detection",
}


def normalize_image_category(value: Any, *, description: str = "", file_path: str = "") -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    haystack = " ".join([raw, str(description or "").lower(), Path(str(file_path or "")).suffix.lower()])
    if any(token in haystack for token in ("screenshot", "screen_capture", "screen capture", "browser", "whatsapp", "telegram", "ui")):
        return "screenshot"
    if any(token in haystack for token in ("document", "receipt", "invoice", "letter", "form", "id card", "passport", "text page")):
        return "document"
    if any(token in haystack for token in ("ai_generated", "ai generated", "synthetic", "diffusion", "gan", "generated image")):
        return "ai_generated_suspect"
    if any(token in haystack for token in ("web_image", "web image", "social media", "downloaded")):
        return "web_image"
    if any(token in haystack for token in ("object_scene", "object scene", "product", "weapon", "vehicle", "room", "scene")):
        return "object_scene"
    return "live_photograph"


def build_image_forensic_routing(
    routing: dict[str, Any] | None,
    *,
    description: str = "",
    file_path: str = "",
    image_category: str | None = None,
) -> dict[str, Any]:
    """Return explicit image routing that can safely drive task gating."""
    source = dict(routing or {})
    category = image_category if image_category else normalize_image_category(
        source.get("image_category") or source.get("category"),
        description=description,
        file_path=file_path,
    )
    recommended = list(CATEGORY_TO_RECOMMENDED_TOOLS.get(category, CATEGORY_TO_RECOMMENDED_TOOLS["live_photograph"]))
    existing_skip = [str(tool) for tool in source.get("skip_tools") or [] if tool]
    other_category_tools = set().union(
        *[set(v) for k, v in CATEGORY_TO_RECOMMENDED_TOOLS.items() if k != category]
    )
    # NOTE: set '-' binds tighter than '|' in Python, so the recommended/keep
    # subtraction MUST wrap the full union — otherwise it only applies to the
    # last operand (CATEGORY_TO_SKIP_TOOLS) and tools that are recommended for
    # THIS category but appear in other categories' recommended lists (e.g. OCR,
    # analyze_image_content, frequency_domain_analysis for screenshots) get
    # wrongly skipped. Explicit parentheses keep the subtraction global.
    skip = sorted(
        (
            set(existing_skip)
            | other_category_tools
            | set(CATEGORY_TO_SKIP_TOOLS.get(category, ()))
        )
        - set(recommended)
        - {"file_hash_verify", "visual_evidence_profile"}
    )
    return {
        **source,
        "image_category": category,
        "recommended_initial_tools": recommended,
        "skip_tools": skip,
        "routing_policy": "category_relevant_image_tools_v1",
    }
