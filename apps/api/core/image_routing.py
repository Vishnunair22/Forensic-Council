from __future__ import annotations

from pathlib import Path
from typing import Any


IMAGE_CATEGORY_TO_INITIAL_TOOLS: dict[str, tuple[str, ...]] = {
    "screenshot": (
        "file_hash_verify",
        "visual_evidence_profile",
        "extract_text_from_image",
        "analyze_image_content",
        "detect_font_inconsistency",
        "detect_ui_overlay_forgery",
        "frequency_domain_analysis",
    ),
    "document": (
        "file_hash_verify",
        "visual_evidence_profile",
        "extract_text_from_image",
        "analyze_image_content",
        "frequency_domain_analysis",
        "neural_ela",
    ),
    "ai_generated_suspect": (
        "file_hash_verify",
        "visual_evidence_profile",
        "analyze_image_content",
        "frequency_domain_analysis",
        "diffusion_artifact_detector",
        "deepfake_frequency_check",
        "synthid_watermark_detect",
    ),
    "web_image": (
        "file_hash_verify",
        "visual_evidence_profile",
        "neural_ela",
        "analyze_image_content",
        "frequency_domain_analysis",
        "neural_fingerprint",
    ),
    "object_scene": (
        "file_hash_verify",
        "visual_evidence_profile",
        "neural_ela",
        "analyze_image_content",
        "frequency_domain_analysis",
        "neural_fingerprint",
    ),
    "live_photograph": (
        "file_hash_verify",
        "visual_evidence_profile",
        "neural_ela",
        "analyze_image_content",
        "frequency_domain_analysis",
        "neural_fingerprint",
    ),
}


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

CATEGORY_HARD_SKIP_TOOLS: dict[str, tuple[str, ...]] = {
    "screenshot": (
        "neural_ela",
        "ela_full_image",
        "jpeg_ghost_detect",
        "noiseprint_cluster",
        "noise_fingerprint",
        "neural_splicing",
        "neural_copy_move",
    ),
    "document": (
        "detect_font_inconsistency",
        "detect_ui_overlay_forgery",
        "noiseprint_cluster",
        "noise_fingerprint",
    ),
    "ai_generated_suspect": (
        "noiseprint_cluster",
        "noise_fingerprint",
        "jpeg_ghost_detect",
    ),
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
) -> dict[str, Any]:
    """Return explicit image routing that can safely drive task gating."""
    source = dict(routing or {})
    category = normalize_image_category(
        source.get("image_category") or source.get("category"),
        description=description,
        file_path=file_path,
    )
    recommended = list(IMAGE_CATEGORY_TO_INITIAL_TOOLS.get(category, IMAGE_CATEGORY_TO_INITIAL_TOOLS["live_photograph"]))
    existing_skip = [str(tool) for tool in source.get("skip_tools") or [] if tool]
    other_category_tools = set().union(
        *[set(v) for k, v in IMAGE_CATEGORY_TO_INITIAL_TOOLS.items() if k != category]
    )
    skip = sorted(
        (set(existing_skip) | other_category_tools)
        | set(CATEGORY_HARD_SKIP_TOOLS.get(category, ()))
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
