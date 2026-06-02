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
    "neural_splicing",
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
    file_type = str(visual_context.get("file_type_assessment") or "").lower()

    # ── Rule 1: Camera-physics tools on screenshots ────────────────────────
    # These tools measure sensor properties that don't exist in screen-rendered
    # images. Their output is expected noise, not manipulation evidence.
    # Cap severity at LOW and annotate the finding.
    if (
        agent_id == "Agent1"
        and is_screenshot
        and tool_name in _CAMERA_PHYSICS_TOOLS
        and current_severity in ("CRITICAL", "HIGH", "MEDIUM")
    ):
        adj = _cap_severity(current_severity, "LOW")
        note = (
            f"Severity reduced from {current_severity} to {adj}: "
            f"{tool_name} measures camera-sensor properties that produce "
            f"expected elevated output on screen-rendered images "
            f"(file type confirmed: {file_type or 'screenshot'}). "
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
