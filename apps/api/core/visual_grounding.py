"""
Visual Context Grounding
========================

Calibrates per-tool finding severity based on the pre-flight VisualContext.
Prevents finding inflation from camera-physics tools whose output is expected
noise for the detected file type (e.g. ELA on screenshots), and surfaces
cross-modal conflicts as additional forensic signals.

Principles — hard constraints:
  1. CONTEXTUALISE, never suppress. Every finding stays in the record.
  2. Downgrade severity when a tool's output is predictably elevated for the
     confirmed file type. The original severity is preserved in context_note
     for report transparency.
  3. Annotate conflicts (EXIF vs visual context, YOLO vs Gemini scene) without
     changing severity — the Arbiter weighs those signals independently.
  4. Never let Gemini override a deterministic tool's hard positive signal.
     Grounding applies only when the finding would otherwise be noise.

This is the SEVERITY-tier grounding layer. It is one of two grounding layers and
both MUST source from the same canonical pre-flight VisualContext:
  - core/agent_reasoning.py post_tool_reasoning  → grounds VERDICT/confidence
    in-loop, consuming the VisualContext object directly.
  - this module (apply_visual_grounding)          → grounds SEVERITY post-hoc,
    consuming the flat dict from visual_context_store.visual_context_to_profile_dict.
Callers (orchestration/pipeline_phases.py broadcast, agents/arbiter.py) must pass
that canonical flat dict — never the raw inter-agent-bus profile, whose shape
varies with whichever writer last touched it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ── Screenshot detection ───────────────────────────────────────────────────

# File type strings that indicate a screen-rendered image rather than a
# photographic capture.  Matched as substrings against file_type_assessment
# and content_description from the VisualContext profile dict.
_SCREENSHOT_TOKENS = frozenset({
    "screenshot",
    "screen_capture",
    "screen capture",
    "screen shot",
    "screengrab",
    "phone_screenshot",
    "desktop_screenshot",
    "digital_ui",
    "digital ui",
    "web_download",
    "ui capture",
})


def _is_screenshot(profile: dict[str, Any]) -> bool:
    """True when the visual context identifies this as a screen-rendered image."""
    for field_name in ("file_type_assessment", "content_description", "interface_identification"):
        val = str(profile.get(field_name) or "").lower()
        if any(token in val for token in _SCREENSHOT_TOKENS):
            return True
    return False


# Non-camera origins where camera-sensor tools (ELA, PRNU, noiseprint, JPEG
# ghost, frequency) produce expected/unreliable output rather than manipulation
# evidence. EXCLUDES "photograph" (real camera capture — keep its signals) and
# "composite" (a flagged manipulation — keep its signals).
_NON_CAMERA_FILETYPE_TOKENS = frozenset({
    "document_scan",
    "scanned_doc",
    "scanned document",
    "ai_generated",
    "ai-generated",
    "synthetic",
    "diffusion",
    "web_image",
    "web download",
    "web_download",
})


def _is_non_camera_origin(profile: dict[str, Any]) -> bool:
    """True when the image is not a primary camera capture, so camera-physics
    tool output is expected noise rather than manipulation evidence.

    Screenshots qualify; so do document scans, AI-generated, and recompressed
    web images. A genuine ``photograph`` or a flagged ``composite`` does NOT —
    those are exactly where camera-physics signals must be preserved.
    """
    file_type = str(profile.get("file_type_assessment") or "").lower()
    if "photograph" in file_type or "composite" in file_type:
        return False
    if _is_screenshot(profile):
        return True
    return any(token in file_type for token in _NON_CAMERA_FILETYPE_TOKENS)


# ── Camera-physics tools ───────────────────────────────────────────────────

# These tools measure physical camera-sensor properties.  On screen-rendered
# images they always produce elevated outputs (expected noise), not evidence
# of manipulation.
_CAMERA_PHYSICS_TOOLS = frozenset({
    "ela_full_image",
    "ela_anomaly_classify",
    "noise_fingerprint",
    "noiseprint_cluster",
    "prnu_analysis",
    "prnu_sensor_verification",
    "jpeg_ghost_detect",
    "frequency_domain_analysis",
    "deepfake_frequency_check",
    "copy_move_detect",
    "neural_copy_move",
    # NOTE: "neural_splicing" intentionally NOT camera-physics. It is now the real
    # TruFor learned model (SegFormer+Noiseprint++), which detects forgeries on any
    # image (camera or not) and does not false-positive on clean images
    # (validated). Capping its severity to LOW on "non-camera" images suppressed
    # genuine splice/clone detections and left the verdict Authentic. (The SRM
    # heuristic fallback only runs if the weights are absent.)
    "adversarial_robustness_check",
    "camera_profile_match",
    "roi_extract",
    "splicing_detect",
})


# ── EXIF / metadata fields that imply camera provenance ───────────────────

_CAMERA_EXIF_KEYS = frozenset({
    "camera_make",
    "camera_model",
    "gps_location",
    "gps_coordinates",
    "datetime_original",
    "focal_length",
    "aperture",
    "iso",
    "shutter_speed",
    "lens_model",
})


# ── Severity scale ─────────────────────────────────────────────────────────

_SEV_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}
_RANK_SEV = {v: k for k, v in _SEV_RANK.items()}


def _cap_severity(current: str, cap: str) -> str:
    """Return the lower of current and cap."""
    current_rank = _SEV_RANK.get(current, 1)
    cap_rank = _SEV_RANK.get(cap, 1)
    return _RANK_SEV[min(current_rank, cap_rank)]


# ── Result type ────────────────────────────────────────────────────────────

@dataclass
class GroundingResult:
    adjusted_severity: str
    context_note: str = ""
    grounded: bool = False
    grounding_type: str = ""  # "camera_noise" | "metadata_conflict" | "scene_corroboration"
    confidence_scale: float = 1.0


# ── Main function ──────────────────────────────────────────────────────────

def apply_visual_grounding(
    tool_name: str,
    agent_id: str,
    current_severity: str,
    visual_context: dict[str, Any] | None,
    metadata: dict[str, Any],
) -> GroundingResult:
    """
    Calibrate a single finding's severity against the pre-flight VisualContext.

    Args:
        tool_name:        Normalised tool name (snake_case, no version suffix).
        agent_id:         "Agent1", "Agent3", or "Agent5".
        current_severity: Severity string from assign_severity_tier().
        visual_context:   Dict from inter_agent_bus.get_visual_profile() or None.
        metadata:         The finding's metadata dict.

    Returns:
        GroundingResult with adjusted_severity and an optional context_note.
        If no grounding applies, adjusted_severity == current_severity.
    """
    if not visual_context:
        return GroundingResult(adjusted_severity=current_severity)

    is_screenshot = _is_screenshot(visual_context)
    is_non_camera = _is_non_camera_origin(visual_context)
    file_type = str(visual_context.get("file_type_assessment") or "").lower()

    # ── Rule 1: Camera-physics tools on non-camera-origin images ───────────
    # ELA/PRNU/noiseprint/JPEG-ghost/frequency measure sensor properties that
    # don't exist (or are destroyed) in screen-rendered, scanned, AI-generated,
    # or recompressed-web images. Their elevated output there is expected noise,
    # not manipulation evidence. Cap severity at LOW and annotate. Genuine
    # photographs and flagged composites are excluded by _is_non_camera_origin,
    # so real splicing/tamper signals are never suppressed.
    if (
        tool_name in _CAMERA_PHYSICS_TOOLS
        and agent_id in ("Agent1", "Agent5")
        and is_non_camera
        and current_severity in ("CRITICAL", "HIGH", "MEDIUM")
    ):
        adj = _cap_severity(current_severity, "LOW")
        _origin = file_type or ("screenshot" if is_screenshot else "non-camera-origin")
        note = (
            f"Severity reduced from {current_severity} to {adj}: "
            f"{tool_name} measures camera-sensor properties that produce "
            f"expected elevated output on {_origin} images "
            "(not a primary camera capture). "
            "Signal is not indicative of manipulation for this file type."
        )
        return GroundingResult(
            adjusted_severity=adj,
            context_note=note,
            grounded=True,
            grounding_type="camera_noise",
            confidence_scale=0.3,
        )

    # ── Rule 2: Agent5 EXIF/metadata claims camera provenance but visual ───
    # context confirms screenshot — strong manipulation signal.
    # Annotate the conflict without changing severity (Arbiter weighs this).
    if (
        agent_id == "Agent5"
        and is_screenshot
        and tool_name in ("exif_extract", "exif_isolation_forest", "metadata_anomaly_score")
    ):
        has_camera_exif = any(metadata.get(k) for k in _CAMERA_EXIF_KEYS)
        claimed_device = str(metadata.get("camera_make") or metadata.get("camera_model") or "")
        if has_camera_exif:
            note = (
                "Cross-modal conflict: embedded metadata claims camera-originated file "
                f"{'(device: ' + claimed_device + ') ' if claimed_device else ''}"
                "but visual analysis confirms this is a screen-rendered image. "
                "This discrepancy is a strong provenance anomaly — potential metadata forgery."
            )
            return GroundingResult(
                adjusted_severity=current_severity,  # keep — Arbiter interprets the conflict
                context_note=note,
                grounded=True,
                grounding_type="metadata_conflict",
            )

    # ── Rule 3: Agent3 scene inconsistency corroborated by Gemini ──────────
    # When both YOLO-based scene analysis and the Gemini visual context agree
    # on an inconsistency, elevate the finding's note to flag the corroboration.
    if (
        agent_id == "Agent3"
        and tool_name in ("scene_incongruence", "lighting_consistency", "scale_validation")
        and current_severity in ("MEDIUM", "HIGH", "CRITICAL")
    ):
        gemini_inconsistencies = list(
            visual_context.get("scene_inconsistencies") or []
        )
        if gemini_inconsistencies:
            note = (
                "Corroborated by visual analysis: Gemini independently flagged "
                f"{len(gemini_inconsistencies)} scene inconsistenc"
                f"{'y' if len(gemini_inconsistencies) == 1 else 'ies'} "
                f"({'; '.join(gemini_inconsistencies[:2])}). "
                "Deterministic and vision-model signals are in agreement."
            )
            return GroundingResult(
                adjusted_severity=current_severity,
                context_note=note,
                grounded=True,
                grounding_type="scene_corroboration",
            )

    return GroundingResult(adjusted_severity=current_severity)
