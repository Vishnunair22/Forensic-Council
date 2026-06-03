"""Human, court-readable summaries for forensic tool findings.

The deterministic synthesis path (used whenever the LLM refiner is unavailable
or quota-limited — which on free-tier providers is the common case) previously
emitted contentless lines like "Forensic signal identified by neural_splicing
with confidence 0.43". That tells a reader nothing about WHAT was found and
leaks the internal tool name.

This module maps each tool to a plain-English description of what a POSITIVE /
NEGATIVE / INCONCLUSIVE result actually means, grounded in the tool's real
measurements (anomaly scores, region counts, matched keypoints, etc.). The
output reads as an examiner's finding, not a debug string, and never names the
underlying model/vendor.
"""

from __future__ import annotations

from typing import Any

# Per-tool phrasing. Each entry: what a flagged (POSITIVE) result indicates and
# what a clean (NEGATIVE) result indicates, in the examiner's voice. Phrases are
# deliberately calibrated — they state what the check observed, not a verdict.
_TOOL_PHRASES: dict[str, dict[str, str]] = {
    # ── Agent 1 — pixel / image integrity ─────────────────────────────────────
    "ela_full_image": {
        "positive": "Error-level analysis localized compression discontinuities consistent with a region that was edited and re-saved",
        "negative": "Error-level analysis found uniform compression across the frame, with no localized re-save discontinuity",
    },
    "neural_ela": {
        "positive": "Learned error-level analysis localized residual edges where compression history diverges from the surrounding image",
        "negative": "Learned error-level analysis found a consistent compression signature across the image",
    },
    "ela_anomaly_classify": {
        "positive": "Compression-anomaly classification flagged a region whose error profile departs from the rest of the frame",
        "negative": "Compression-anomaly classification found no region departing from the global error profile",
    },
    "jpeg_ghost_detect": {
        "positive": "JPEG-ghost analysis detected an area carrying a second, mismatched quantization history — a hallmark of a pasted region",
        "negative": "JPEG-ghost analysis found a single consistent quantization history with no spliced-region ghosting",
    },
    "frequency_domain_analysis": {
        "positive": "Frequency-domain analysis detected spectral artifacts atypical of a single in-camera capture",
        "negative": "Frequency-domain analysis found a natural spectral falloff consistent with an unmodified capture",
    },
    "deepfake_frequency_check": {
        "positive": "Spectral analysis detected periodic frequency artifacts associated with generative (GAN/diffusion) synthesis",
        "negative": "Spectral analysis found no periodic synthesis artifacts in the frequency bands",
    },
    "f3_net_frequency": {
        "positive": "Deep frequency analysis detected mid/high-band artifacts associated with synthetic or re-rendered content",
        "negative": "Deep frequency analysis found no synthesis artifacts in the examined bands",
    },
    "splicing_detect": {
        "positive": "Splicing analysis localized boundary inconsistencies indicative of a composited region",
        "negative": "Splicing analysis found no boundary inconsistencies indicating a composite",
    },
    "neural_splicing": {
        "positive": "Learned splicing analysis localized residual inconsistencies consistent with a composited region",
        "negative": "Learned splicing analysis found no residual evidence of compositing",
    },
    "copy_move_detect": {
        "positive": "Copy-move analysis matched duplicated regions consistent with content cloned within the same image",
        "negative": "Copy-move analysis found no duplicated regions indicative of cloning",
    },
    "neural_copy_move": {
        "positive": "Learned copy-move analysis matched duplicated feature clusters consistent with an in-image clone",
        "negative": "Learned copy-move analysis found no duplicated feature clusters",
    },
    "noise_fingerprint": {
        "positive": "Sensor-noise (PRNU) analysis found the noise fingerprint inconsistent across the frame, suggesting content from more than one source",
        "negative": "Sensor-noise (PRNU) analysis found a uniform noise fingerprint consistent with a single capture",
    },
    "noiseprint_cluster": {
        "positive": "Noise-fingerprint clustering isolated regions whose noise statistics differ from the surrounding image",
        "negative": "Noise-fingerprint clustering found uniform noise statistics across the image",
    },
    "prnu_sensor_verification": {
        "positive": "Sensor-pattern (PRNU) verification found the noise pattern inconsistent with a single, unaltered sensor capture",
        "negative": "Sensor-pattern (PRNU) verification found a noise pattern consistent with a single sensor origin",
    },
    "neural_fingerprint": {
        "positive": "Model-fingerprint analysis detected generative texture signatures characteristic of synthetic imagery",
        "negative": "Model-fingerprint analysis found no generative texture signature",
    },
    "diffusion_artifact_detector": {
        "positive": "Diffusion-artifact analysis detected texture and edge signatures characteristic of diffusion-generated imagery",
        "negative": "Diffusion-artifact analysis found no diffusion-generation signatures",
    },
    "anomaly_tracer": {
        "positive": "Anomaly tracing localized pixel regions whose statistics break from the surrounding content",
        "negative": "Anomaly tracing found no statistically anomalous pixel regions",
    },
    "adversarial_robustness": {
        "positive": "Adversarial-robustness probing found the result sensitive to minute perturbations, indicating possible adversarial tampering",
        "negative": "Adversarial-robustness probing found the result stable under perturbation",
    },
    "adversarial_robustness_check": {
        "positive": "Adversarial-robustness probing found the result sensitive to minute perturbations, indicating possible adversarial tampering",
        "negative": "Adversarial-robustness probing found the result stable under perturbation",
    },
    "detect_font_inconsistency": {
        "positive": "Font-rendering analysis flagged localized text-rendering outliers inconsistent with the surrounding typography",
        "negative": "Font-rendering analysis found uniform typography with no inserted-text outliers",
    },
    "detect_ui_overlay_forgery": {
        "positive": "UI-overlay analysis flagged a pasted or inserted interface region",
        "negative": "UI-overlay analysis found no pasted interface chrome or inserted notification panels",
    },
    "neural_fingerprint_match": {
        "positive": "Model-fingerprint matching associated the image with a known generative model family",
        "negative": "Model-fingerprint matching found no association with a known generative model",
    },
    # ── Agent 3 — scene / object integrity ────────────────────────────────────
    "object_detection": {
        "positive": "Object detection surfaced entities relevant to the forensic question",
        "negative": "Object detection found no entities of forensic concern",
    },
    "lighting_consistency": {
        "positive": "Lighting and shadow analysis found light directions inconsistent across the scene, suggesting composited elements",
        "negative": "Lighting and shadow analysis found a consistent illumination model across the scene",
    },
    "lighting_correlation_initial": {
        "positive": "Shadow-direction correlation flagged shadows that do not share a common light source",
        "negative": "Shadow-direction correlation found shadows consistent with a single light source",
    },
    "scene_incongruence": {
        "positive": "Scene-context analysis flagged semantic inconsistencies between the depicted objects and their setting",
        "negative": "Scene-context analysis found the objects coherent with their setting",
    },
    "scale_validation": {
        "positive": "Scale validation found object proportions inconsistent with a physically plausible scene",
        "negative": "Scale validation found object proportions physically consistent",
    },
    "vector_contraband_search": {
        "positive": "Threat/contraband vector search matched visual content of forensic concern",
        "negative": "Threat/contraband vector search returned no matches of concern",
    },
    "secondary_classification": {
        "positive": "Secondary classification disagreed with the primary object reading, indicating an ambiguous or manipulated subject",
        "negative": "Secondary classification corroborated the primary object reading",
    },
    "screenshot_layout_forensics": {
        "positive": "Screenshot-layout analysis flagged structural UI/document anomalies consistent with an edited capture",
        "negative": "Screenshot-layout analysis found a structurally consistent UI layout",
    },
    "analyze_image_content": {
        "positive": "Semantic content analysis flagged inconsistencies between the depicted elements and a coherent real scene",
        "negative": "Semantic content analysis found the depicted scene internally coherent",
    },
    "lens_style_multimodal_scan": {
        "positive": "Lens and style analysis flagged optical or stylistic characteristics atypical of a single authentic capture",
        "negative": "Lens and style analysis found optical characteristics consistent with a single authentic capture",
    },
    "extract_text_from_image": {
        "positive": "Text extraction recovered embedded text relevant to the forensic question",
        "negative": "Text extraction recovered no embedded text of forensic concern",
    },
    "extract_evidence_text": {
        "positive": "Text extraction recovered embedded text relevant to the forensic question",
        "negative": "Text extraction recovered no embedded text of forensic concern",
    },
    # ── Agent 5 — metadata / provenance ───────────────────────────────────────
    "exif_extract": {
        "positive": "EXIF extraction surfaced metadata fields that conflict with the image content or each other",
        "negative": "EXIF extraction found an internally consistent metadata record",
    },
    "metadata_anomaly_score": {
        "positive": "The metadata-anomaly model scored the field distribution as atypical relative to genuine camera captures",
        "negative": "The metadata-anomaly model scored the field distribution within the normal range for genuine captures",
    },
    "exif_isolation_forest": {
        "positive": "The EXIF outlier model flagged the metadata profile as anomalous against known-good camera baselines",
        "negative": "The EXIF outlier model placed the metadata profile within known-good camera baselines",
    },
    "gps_timezone_validate": {
        "positive": "GPS/timezone validation found the embedded location and timestamp offset mutually inconsistent",
        "negative": "GPS/timezone validation found the location and timestamp offset consistent",
    },
    "file_structure_analysis": {
        "positive": "File-structure analysis flagged header, trailer, or appended-payload anomalies",
        "negative": "File-structure analysis found a valid header/trailer profile with no appended-payload indicators",
    },
    "hex_signature_scan": {
        "positive": "Binary-signature scan detected an embedded editing-software marker",
        "negative": "Binary-signature scan found no embedded editing-software signature",
    },
    "timestamp_analysis": {
        "positive": "Timestamp analysis found a chronology inconsistency among the embedded date fields",
        "negative": "Timestamp analysis found the embedded date fields internally consistent",
    },
    "camera_profile_match": {
        "positive": "Camera-profile matching found the metadata inconsistent with the characteristics of the claimed capture device",
        "negative": "Camera-profile matching found the metadata consistent with the claimed device profile",
    },
    "steganography_scan": {
        "positive": "Steganography scan detected statistical indicators of hidden embedded data",
        "negative": "Steganography scan found no statistical indicators of hidden data",
    },
    "astro_grounding": {
        "positive": "Astronomical grounding found the sun/shadow geometry inconsistent with the claimed time and location",
        "negative": "Astronomical grounding found the sun/shadow geometry consistent with the claimed time and location",
    },
    "c2pa_provenance": {
        "positive": "Content-provenance (C2PA) validation found a broken or missing signature in the claimed manifest chain",
        "negative": "Content-provenance (C2PA) validation found an intact manifest chain",
    },
    "file_hash_verify": {
        "positive": "Hash verification found the evidence digest did NOT match the intake chain-of-custody record",
        "negative": "SHA-256 hash matched the intake chain-of-custody record",
    },
    "compression_risk_audit": {
        "positive": "Compression/provenance audit found re-compression or platform-normalization patterns that weaken provenance reliability",
        "negative": "Compression/provenance audit found no manipulation-related compression anomalies",
    },
}

# Category-level fallback when a specific tool has no entry — still far better
# than naming the raw tool. Keyed by signal_category from the normalizer.
_CATEGORY_PHRASES: dict[str, dict[str, str]] = {
    "pixel_integrity": {
        "positive": "Pixel-integrity analysis flagged a localized manipulation signal",
        "negative": "Pixel-integrity analysis found no localized manipulation signal",
    },
    "scene_integrity": {
        "positive": "Scene analysis flagged an inconsistency in the depicted content",
        "negative": "Scene analysis found the depicted content internally consistent",
    },
    "metadata_integrity": {
        "positive": "Metadata analysis flagged a provenance inconsistency",
        "negative": "Metadata analysis found the provenance record consistent",
    },
    "audio_integrity": {
        "positive": "Acoustic analysis flagged an integrity anomaly in the audio",
        "negative": "Acoustic analysis found no integrity anomaly in the audio",
    },
    "temporal_integrity": {
        "positive": "Temporal analysis flagged an inter-frame inconsistency",
        "negative": "Temporal analysis found consistent motion across frames",
    },
    "general": {
        "positive": "Forensic analysis flagged an anomaly signal",
        "negative": "Forensic analysis found no anomaly signal",
    },
}

# Tools whose output is shared context / plumbing rather than an independent
# forensic finding. They must never appear as a "signal" in key findings.
CONTEXT_ONLY_TOOLS: frozenset[str] = frozenset({
    "read_shared_image_context",
    "visual_evidence_profile",
    "shared_visual_evidence_profile",
    "roi_extract",
    "frame_extraction",
})


def _num(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _measurement_detail(measurements: dict[str, Any], regions: list[Any]) -> str:
    """Pick the single most salient measurement and render it as a short
    parenthetical (e.g. "anomaly score 0.57; 2 region(s)")."""
    bits: list[str] = []
    m = measurements or {}

    score_keys = (
        ("anomaly_score", "anomaly score"),
        ("tampering_score", "tampering score"),
        ("forgery_score", "forgery score"),
        ("synthetic_probability", "synthetic probability"),
        ("diffusion_probability", "diffusion probability"),
        ("incongruence_score", "incongruence score"),
        ("noise_consistency_score", "noise-consistency score"),
        ("consistency_score", "consistency score"),
        ("similarity", "similarity"),
    )
    for key, label in score_keys:
        val = _num(m.get(key))
        if val is not None:
            bits.append(f"{label} {val:.2f}")
            break

    n_regions = _num(m.get("num_anomaly_regions"))
    if n_regions is None and isinstance(regions, list) and regions:
        n_regions = float(len(regions))
    if n_regions is not None and n_regions > 0:
        n = int(n_regions)
        bits.append(f"{n} region{'s' if n != 1 else ''} localized")

    return "; ".join(bits[:2])


def humanize_finding_summary(
    tool_name: str,
    status: str,
    measurements: dict[str, Any] | None = None,
    regions: list[Any] | None = None,
    confidence: float | None = None,
    signal_category: str = "general",
) -> str:
    """Return a plain-English, examiner-voice summary of a tool finding.

    Falls back from tool-specific → category-specific phrasing, then appends the
    most salient measurement. Never emits the raw tool name or a vendor/model.
    """
    status = (status or "").upper()
    phrases = _TOOL_PHRASES.get(tool_name) or _CATEGORY_PHRASES.get(
        signal_category, _CATEGORY_PHRASES["general"]
    )

    if status == "POSITIVE":
        base = phrases.get("positive") or _CATEGORY_PHRASES["general"]["positive"]
        detail = _measurement_detail(measurements or {}, regions or [])
        return f"{base} ({detail})." if detail else f"{base}."
    if status in ("NEGATIVE", "SUCCESS"):
        return (phrases.get("negative") or _CATEGORY_PHRASES["general"]["negative"]) + "."
    if status == "NOT_APPLICABLE":
        return ""  # handled by callers as a bypass, not a finding
    # INCONCLUSIVE / unknown
    return f"{_humanize_label(tool_name)} returned no determinate signal."


def _humanize_label(tool_name: str) -> str:
    return tool_name.replace("_", " ").strip().capitalize()
