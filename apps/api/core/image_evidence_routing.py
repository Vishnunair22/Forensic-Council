"""
Deterministic Image Evidence Routing and Tool Planning.

This module provides the ImageEvidenceProfile and functions to categorize
incoming image evidence files and construct their base agent tool plans
before analysis starts, avoiding inter-agent dependencies on visual profiles.
"""

from enum import Enum
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel
from PIL import Image

from core.structured_logging import get_logger
from core.media_kind import (
    is_screen_capture_like,
    is_document_like,
    is_camera_still_candidate,
)

logger = get_logger(__name__)


class ImageEvidenceClass(str, Enum):
    CAMERA_PHOTO = "camera_photo"
    WEB_OR_DIGITAL_IMAGE = "web_or_digital_image"
    DOCUMENT_OR_PAPER = "document_or_paper"
    SCREENSHOT = "screenshot"
    PEOPLE_OBJECT_WEAPON = "people_object_weapon"
    PHYSICAL_SCENE = "physical_scene"
    UNKNOWN_IMAGE = "unknown_image"


class ImageEvidenceProfile(BaseModel):
    mime_type: str
    extension: str
    pil_format: str
    width: int
    height: int
    has_exif: bool
    has_camera_make_model: bool
    has_gps: bool
    software: Optional[str] = None
    is_lossless: bool
    is_animated: bool
    is_screenshot_like: bool
    is_document_like: bool
    is_camera_photo: bool
    is_web_or_digital: bool
    route_classes: list[ImageEvidenceClass]


def build_image_evidence_profile(
    path: str,
    original_filename: str | None = None,
    mime_type: str | None = None,
    extension: str | None = None,
) -> ImageEvidenceProfile:
    """Probes the image to build a deterministic ImageEvidenceProfile."""
    path_obj = Path(path)
    ext = extension or path_obj.suffix.lower()
    mime = mime_type or "image/jpeg"

    # Default values in case PIL fails
    pil_format = "JPEG"
    width = 0
    height = 0
    has_exif = False
    has_camera_make_model = False
    has_gps = False
    software = None
    is_lossless = ext in {".png", ".tiff", ".tif", ".bmp"}
    is_animated = False

    try:
        with Image.open(path) as img:
            pil_format = (img.format or "").upper()
            width, height = img.size
            is_animated = getattr(img, "is_animated", False)
            exif = img.getexif()
            if exif:
                has_exif = True
                # Make is tag 271, Model is tag 272
                has_camera_make_model = any(exif.get(tag) for tag in (271, 272))
                # Software is tag 305
                software = exif.get(305)
                if software:
                    software = str(software).strip()
                # GPSInfo is tag 34853
                has_gps = (34853 in exif) or bool(exif.get_ifd(0x8825))
    except Exception as exc:
        logger.warning(
            "PIL failed to probe image in build_image_evidence_profile",
            path=path,
            error=str(exc)
        )

    class MockArtifact:
        def __init__(self, file_path, orig_name, mime_type):
            self.file_path = file_path
            self.original_filename = orig_name
            self.mime_type = mime_type

    artifact = MockArtifact(path, original_filename, mime)

    is_cam = is_camera_still_candidate(artifact)
    is_screenshot = is_screen_capture_like(artifact)
    is_doc = is_document_like(artifact)
    is_web = not is_cam and not is_screenshot and not is_doc

    route_classes = []
    if is_cam:
        route_classes.append(ImageEvidenceClass.CAMERA_PHOTO)
        route_classes.append(ImageEvidenceClass.PHYSICAL_SCENE)
        route_classes.append(ImageEvidenceClass.PEOPLE_OBJECT_WEAPON)
    elif is_screenshot:
        route_classes.append(ImageEvidenceClass.SCREENSHOT)
        if is_doc:
            route_classes.append(ImageEvidenceClass.DOCUMENT_OR_PAPER)
    elif is_doc:
        route_classes.append(ImageEvidenceClass.DOCUMENT_OR_PAPER)
    else:
        route_classes.append(ImageEvidenceClass.WEB_OR_DIGITAL_IMAGE)
        route_classes.append(ImageEvidenceClass.PHYSICAL_SCENE)
        route_classes.append(ImageEvidenceClass.PEOPLE_OBJECT_WEAPON)

    return ImageEvidenceProfile(
        mime_type=mime,
        extension=ext,
        pil_format=pil_format,
        width=width,
        height=height,
        has_exif=has_exif,
        has_camera_make_model=has_camera_make_model,
        has_gps=has_gps,
        software=software,
        is_lossless=is_lossless,
        is_animated=is_animated,
        is_screenshot_like=is_screenshot,
        is_document_like=is_doc,
        is_camera_photo=is_cam,
        is_web_or_digital=is_web,
        route_classes=route_classes,
    )


def build_image_agent_tool_plan(profile: ImageEvidenceProfile) -> dict[str, dict[str, list[str]]]:
    """Generates deterministic initial and deep phase tool plans for specialists."""
    plan = {
        "Agent1": {"initial": [], "deep": [], "forbidden": []},
        "Agent3": {"initial": [], "deep": [], "forbidden": []},
        "Agent5": {"initial": [], "deep": [], "forbidden": []},
    }

    is_gif = profile.pil_format == "GIF"

    if ImageEvidenceClass.SCREENSHOT in profile.route_classes:
        # Agent 1
        plan["Agent1"]["initial"] = [
            "file_hash_verify",
            "visual_evidence_profile",
            "extract_text_from_image",
            "analyze_image_content",
            "frequency_domain_analysis",
        ]
        if not profile.is_lossless:
            plan["Agent1"]["initial"].append("neural_ela")
        plan["Agent1"]["deep"] = [
            "neural_fingerprint",
            "f3_net_frequency",
            "deepfake_frequency_check",
            "diffusion_artifact_detector",
            "synthid_watermark_detect",
            "detect_ui_overlay_forgery",
            "detect_font_inconsistency",
        ]
        plan["Agent1"]["forbidden"] = ["noiseprint_cluster"] if profile.is_lossless else []

        # Agent 3
        plan["Agent3"]["initial"] = [
            "screenshot_scene_applicability",
            "screenshot_layout_forensics",
        ]
        plan["Agent3"]["deep"] = ["read_shared_image_context"]
        plan["Agent3"]["forbidden"] = [
            "lighting_correlation_initial",
            "scale_validation",
            "lighting_consistency",
        ]

        # Agent 5
        plan["Agent5"]["initial"] = [
            "file_hash_verify",
            "exif_extract",
            "hex_signature_scan",
            "compression_risk_audit",
            "file_structure_analysis",
        ]
        plan["Agent5"]["deep"] = [
            "timestamp_analysis",
            "provenance_chain_verify",
            "read_shared_image_context",
        ]
        plan["Agent5"]["forbidden"] = ["camera_profile_match", "astro_grounding"]

    elif ImageEvidenceClass.DOCUMENT_OR_PAPER in profile.route_classes:
        # Agent 1
        plan["Agent1"]["initial"] = [
            "file_hash_verify",
            "visual_evidence_profile",
            "extract_text_from_image",
            "analyze_image_content",
            "frequency_domain_analysis",
        ]
        if not profile.is_lossless:
            plan["Agent1"]["initial"].append("neural_ela")
        else:
            plan["Agent1"]["initial"].append("noiseprint_cluster")

        plan["Agent1"]["deep"] = [
            "neural_splicing",
            "neural_copy_move",
            "f3_net_frequency",
            "diffusion_artifact_detector",
            "detect_font_inconsistency",
        ]

        # Agent 3
        plan["Agent3"]["initial"] = ["screenshot_layout_forensics"]
        plan["Agent3"]["deep"] = ["read_shared_image_context"]
        plan["Agent3"]["forbidden"] = [
            "lighting_correlation_initial",
            "scale_validation",
        ]

        # Agent 5
        plan["Agent5"]["initial"] = [
            "file_hash_verify",
            "exif_extract",
            "file_structure_analysis",
            "hex_signature_scan",
            "compression_risk_audit",
            "timestamp_analysis",
        ]
        plan["Agent5"]["deep"] = [
            "provenance_chain_verify",
            "metadata_anomaly_score",
        ]
        if profile.has_camera_make_model:
            plan["Agent5"]["deep"].append("camera_profile_match")
        if profile.has_gps:
            plan["Agent5"]["deep"].append("gps_timezone_validate")

    elif ImageEvidenceClass.CAMERA_PHOTO in profile.route_classes:
        # Agent 1
        plan["Agent1"]["initial"] = [
            "file_hash_verify",
            "visual_evidence_profile",
            "neural_ela",
            "neural_fingerprint",
            "analyze_image_content",
            "frequency_domain_analysis",
        ]
        plan["Agent1"]["deep"] = [
            "diffusion_artifact_detector",
            "synthid_watermark_detect",
            "f3_net_frequency",
            "neural_splicing",
            "neural_copy_move",
        ]

        # Agent 3
        plan["Agent3"]["initial"] = [
            "object_detection",
            "scene_incongruence",
            "lighting_correlation_initial",
            "vector_contraband_search",
        ]
        plan["Agent3"]["deep"] = [
            "scale_validation",
            "lighting_consistency",
            "read_shared_image_context",
        ]

        # Agent 5
        plan["Agent5"]["initial"] = [
            "file_hash_verify",
            "exif_extract",
            "file_structure_analysis",
            "hex_signature_scan",
            "compression_risk_audit",
            "timestamp_analysis",
        ]
        plan["Agent5"]["deep"] = [
            "metadata_anomaly_score",
            "exif_isolation_forest",
            "provenance_chain_verify",
        ]
        if profile.has_camera_make_model:
            plan["Agent5"]["deep"].append("camera_profile_match")
        if profile.has_gps:
            plan["Agent5"]["deep"].extend(["gps_timezone_validate", "astro_grounding"])

    else:
        # Web or digital image (or animated GIF)
        # Agent 1
        plan["Agent1"]["initial"] = [
            "file_hash_verify",
            "visual_evidence_profile",
            "analyze_image_content",
            "frequency_domain_analysis",
        ]
        if not is_gif:
            plan["Agent1"]["initial"].append("neural_fingerprint")
            if not profile.is_lossless:
                plan["Agent1"]["initial"].append("neural_ela")
            else:
                plan["Agent1"]["initial"].append("noiseprint_cluster")

        plan["Agent1"]["deep"] = [
            "diffusion_artifact_detector",
            "synthid_watermark_detect",
            "f3_net_frequency",
        ]
        if not is_gif:
            plan["Agent1"]["deep"].extend(["neural_splicing", "neural_copy_move"])

        # Agent 3
        if is_gif:
            plan["Agent3"]["initial"] = ["object_detection"]
        else:
            plan["Agent3"]["initial"] = [
                "object_detection",
                "scene_incongruence",
                "vector_contraband_search",
                "lighting_correlation_initial",
            ]
            plan["Agent3"]["deep"] = [
                "scale_validation",
                "lighting_consistency",
                "read_shared_image_context",
            ]

        # Agent 5
        plan["Agent5"]["initial"] = [
            "file_hash_verify",
            "exif_extract",
            "file_structure_analysis",
            "hex_signature_scan",
            "compression_risk_audit",
        ]
        plan["Agent5"]["deep"] = [
            "provenance_chain_verify",
            "metadata_anomaly_score",
        ]

    return plan


_TOOL_TO_TASK_DESC = {
    # Agent 1
    "file_hash_verify": "run file_hash_verify for evidence integrity check",
    "visual_evidence_profile": "run visual_evidence_profile for visual evidence profile and forensic routing hints",
    "extract_text_from_image": "run extract_text_from_image for visible text extraction",
    "analyze_image_content": "run analyze_image_content for semantic image understanding",
    "frequency_domain_analysis": "run frequency_domain_analysis for frequency domain analysis",
    "detect_font_inconsistency": "run detect_font_inconsistency for document/font inconsistency",
    "detect_ui_overlay_forgery": "run detect_ui_overlay_forgery for ui overlay forgery detection",
    "synthid_watermark_detect": "run synthid_watermark_detect for synthid and ai watermark detection",
    "neural_ela": "run neural_ela for high-confidence manipulation detection",
    "noiseprint_cluster": "run noiseprint_cluster for sensor-region source inconsistency",
    "neural_fingerprint": "run neural_fingerprint for conceptual similarity detection",
    "anomaly_tracer": "run anomaly_tracer for mantra-net universal anomaly tracing",
    "f3_net_frequency": "run f3_net_frequency for ai-gan artifact detection",
    "neural_splicing": "run neural_splicing for vit-based region composition analysis",
    "neural_copy_move": "run neural_copy_move for dual-branch copy-move detection",
    "diffusion_artifact_detector": "run diffusion_artifact_detector for ai-generation signatures",
    "deepfake_frequency_check": "run deepfake_frequency_check for gan/diffusion artifacts",
    "jpeg_ghost_detect": "run jpeg_ghost_detect for double compression analysis",
    "roi_extract": "run roi_extract for localized forensic region analysis",
    
    # Agent 3
    "object_detection": "run object_detection for scene object identification",
    "vector_contraband_search": "run vector_contraband_search for risk object screening",
    "lighting_correlation_initial": "run lighting_correlation_initial for initial shadow and light direction audit",
    "scene_incongruence": "run scene_incongruence for contextual anomaly detection",
    "screenshot_scene_applicability": "run screenshot_scene_applicability for screen-capture object/scene scope",
    "screenshot_layout_forensics": "run screenshot_layout_forensics for ui and document layout anomaly scan",
    "secondary_classification": "run secondary_classification on flagged objects for validation",
    "scale_validation": "run scale_validation for object proportion and geometry consistency",
    "lighting_consistency": "run lighting_consistency for deep ROI-aware shadow-angle audit",
    "read_shared_image_context": "read shared image context for object/scene grounding from Agent 1 visual profile",

    # Agent 5
    "exif_extract": "run exif_extract to capture all metadata fields",
    "timestamp_analysis": "run timestamp_analysis for cross-field date and time consistency",
    "file_structure_analysis": "run file_structure_analysis for binary anomalies in headers and trailers",
    "hex_signature_scan": "run hex_signature_scan for raw-byte software signatures",
    "compression_risk_audit": "run compression_risk_audit to check for social media footprints",
    "metadata_anomaly_score": "run metadata_anomaly_score",
    "provenance_chain_verify": "run provenance_chain_verify for c2pa/jumbf integrity check",
    "camera_profile_match": "run camera_profile_match",
    "exif_isolation_forest": "run exif_isolation_forest for ml-based field outlier detection",
    "astro_grounding": "run astro_grounding to verify shadow-sun-gps-time parity",
    "gps_timezone_validate": "run gps_timezone_validate for coordinate timeline checking",
}


def get_agent_plan(
    evidence_artifact: Any,
    agent_id: str,
    phase: str = "initial"
) -> list[str] | None:
    """Helper to retrieve the planned tools list from evidence artifact metadata."""
    metadata = getattr(evidence_artifact, "metadata", {}) or {}
    agent_plan = metadata.get("agent_tool_plan", {})
    if not agent_plan:
        return None

    agent_key = None
    for k in ["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"]:
        if k.lower() in agent_id.lower():
            agent_key = k
            break

    if not agent_key or agent_key not in agent_plan:
        return None

    tools = agent_plan[agent_key].get(phase)
    if not tools:
        return []

    return [_TOOL_TO_TASK_DESC.get(t, t) for t in tools]
