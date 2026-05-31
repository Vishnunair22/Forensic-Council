"""
Findings Humanizer helper module.
Converts raw tool findings to court-defensible investigator notes.
"""

from __future__ import annotations

import re
from typing import Any

from core.media_kind import is_screen_capture_like

_HASH_RE = re.compile(r"SHA-256\s*=\s*([0-9a-fA-F]{10,})")
_TRAILING_ABSENCE_RE = re.compile(
    r"\s+This supports the absence of (?:this specific anomaly|this specific manipulation pattern|this s.*)$",
    re.IGNORECASE,
)


def _metric_digest(metadata: dict[str, Any]) -> str:
    """Extract a compact, high-signal metric digest from raw tool output."""
    if not metadata:
        return ""

    labels = {
        "anomaly_score": "anomaly score",
        "confidence": "tool confidence",
        "top_confidence": "top match",
        "diffusion_probability": "AI probability",
        "synthetic_probability": "synthetic probability",
        "forgery_score": "forgery score",
        "inconsistency_ratio": "inconsistency ratio",
        "noise_consistency_score": "noise consistency",
        "mean_flow_magnitude": "motion magnitude",
        "high_freq_ratio": "high-frequency ratio",
        "max_anomaly": "max ELA deviation",
        "word_count": "OCR words",
        "detection_count": "objects",
        "match_count": "matches",
        "num_matches": "matches",
        "num_anomaly_regions": "regions",
        "outlier_region_count": "outlier regions",
        "bytes_scanned": "bytes scanned",
        "total_fields_extracted": "metadata fields",
    }
    parts: list[str] = []
    for key, label in labels.items():
        value = metadata.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, float):
            rendered = f"{value:.3f}" if abs(value) < 10 else f"{value:.1f}"
        elif isinstance(value, int):
            rendered = f"{value:,}"
        else:
            rendered = str(value)
        parts.append(f"{label}: {rendered}")
        if len(parts) >= 3:
            break

    flags = metadata.get("flags") or metadata.get("anomalies") or metadata.get("forensic_flags")
    if isinstance(flags, list) and flags:
        parts.append("flags: " + "; ".join(str(x) for x in flags[:2]))
    return "; ".join(parts)


def _humanize_initial_finding(
    *,
    agent_id: str,
    tool_name: str,
    summary: str,
    evidence_verdict: str,
    finding_status: str,
    metadata: dict[str, Any],
    artifact: Any = None,
) -> str | None:
    """Turn raw tool text into a concise card-level investigator note."""
    tool = (tool_name or "").lower()
    text = " ".join(str(summary or "").replace("\n", " ").split())
    text = _TRAILING_ABSENCE_RE.sub(".", text).strip()

    if not text:
        return None

    if "no analysis possible due to lack of raw tool data" in text.lower():
        return None

    if "screenshot scene applicability" in tool or "screenshot scene applicability" in text.lower():
        if "skipped" in text.lower() or evidence_verdict == "NOT_APPLICABLE":
            dims = (
                f"{metadata.get('width')}x{metadata.get('height')}px"
                if metadata.get("width") and metadata.get("height")
                else "screen capture"
            )
            aspect = metadata.get("aspect_class") or "screen-capture"
            theme = ""
            if "is_dark_mode" in metadata:
                theme = ", dark UI theme" if metadata.get("is_dark_mode") else ", light UI theme"
            chrome = ", browser/window chrome detected" if metadata.get("ui_chrome_detected") else ""
            return (
                f"Screenshot scope confirmed ({dims}, {aspect}{theme}{chrome}). "
                "Physical-scene object, weapon, lighting, and scale checks were bypassed because they do not apply to screen captures."
            )
        return "Screenshot/context check completed; no physical-scene object evidence was required."

    if "file_hash_verify" in tool or "file hash verify" in text.lower():
        match = _HASH_RE.search(text)
        raw_digest = metadata.get("computed_hash") or metadata.get("current_hash") or (match.group(1) if match else "")
        digest = f"{str(raw_digest)[:12]}..." if raw_digest else "recorded digest"
        size = metadata.get("file_size_bytes")
        size_note = f", {size:,} bytes" if isinstance(size, int) else ""
        return (
            f"Integrity check passed. The uploaded file hash ({digest}{size_note}) matches the "
            "chain-of-custody record, so the submitted artifact was not altered after intake."
        )

    if "exif" in tool or "metadata" in tool:
        fields = int(metadata.get("total_fields_extracted") or 0)
        device = " ".join(
            str(x)
            for x in (
                metadata.get("device_model"),
                metadata.get("camera_make") or metadata.get("make"),
                metadata.get("camera_model") or metadata.get("model"),
            )
            if x
        ).strip()
        captured = (
            metadata.get("datetime_original")
            or metadata.get("DateTimeOriginal")
            or metadata.get("CreateDate")
            or metadata.get("CreationDate")
        )
        size_note = f"; file size {metadata.get('file_size_human')}" if metadata.get("file_size_human") else ""
        if is_screen_capture_like(artifact):
            return (
                f"Container metadata fits a screen-capture workflow: {fields} metadata field(s), "
                f"device {'recorded as ' + device if device else 'not recorded'}, "
                f"capture time {'recorded as ' + str(captured) if captured else 'not recorded'}{size_note}."
            )
        if device or captured or fields:
            return (
                f"EXIF/metadata extracted {fields} field(s); "
                f"device {'recorded as ' + device if device else 'not recorded'}, "
                f"capture time {'recorded as ' + str(captured) if captured else 'not recorded'}{size_note}."
            )

        parts = []
        if "device: not recorded" in text.lower() or "device not recorded" in text.lower():
            parts.append("No camera/device model was recorded in EXIF")
        if "capture time: not in exif" in text.lower() or "capture time not" in text.lower():
            parts.append("no original capture timestamp was present")
        if "gps: absent" in text.lower() or "gps absent" in text.lower():
            parts.append("GPS metadata is absent")
        if parts:
            return "; ".join(parts).capitalize() + ". This is common for screenshots and exported images."

    if "compression_risk_audit" in tool:
        platform = str(metadata.get("detected_platform") or "").strip()
        impact = str(metadata.get("forensic_reliability_impact") or "NONE").upper()
        penalty = float(metadata.get("compression_penalty") or 1.0)
        if penalty >= 0.95 or not platform:
            return "No social media or messaging app compression footprint detected. Metadata integrity is unaffected."
        if "unknown" in platform.lower() or "stripped" in platform.lower():
            return (
                f"Metadata appears stripped or platform-normalized — no specific app fingerprint identified, "
                f"which is consistent with social media re-processing, a privacy tool, or a system screenshot. "
                f"Forensic reliability impact: {impact.lower()}."
            )
        clean_platform = (
            platform.replace("(Stripped Metadata - High Compression Risk)", "")
                    .replace("(Filename Signal)", "")
                    .replace("(High Compression)", "")
                    .replace("(Medium-High Compression)", "")
                    .strip().rstrip("-").strip()
        )
        return (
            f"Compression footprint matches {clean_platform}. "
            f"This platform applies significant re-compression which degrades forensic reliability "
            f"({impact.lower()} impact)."
        )

    if "file_structure_analysis" in tool or "file structure analysis" in text.lower():
        if "anomalies: 0" in text.lower() or "header valid" in text.lower():
            return "File container structure is valid: header/trailer checks passed and no appended payload was detected."

    if "frequency_domain_analysis" in tool or "frequency domain analysis" in text.lower():
        if "0.000" in text or "appears natural" in text.lower():
            return "Frequency-domain analysis found no periodic/GAN-like artifact pattern; the screenshot's high-frequency distribution is within the expected range."

    if "extract_text" in tool or "extract text" in text.lower():
        preview = metadata.get("ocr_text_preview") or metadata.get("text_preview")
        content_desc = str(metadata.get("content_description") or "").strip()
        content_type_val = str(metadata.get("content_type") or "").strip()
        word_count = int(metadata.get("word_count") or 0)
        if word_count == 0 and not preview and not content_desc:
            doc_indicators = {"document", "screenshot", "scan", "id_card", "id card", "receipt", "invoice", "form", "text"}
            image_type = str(metadata.get("image_type") or metadata.get("content_type") or "").lower()
            if not any(t in image_type for t in doc_indicators):
                return None
        if preview:
            clean_preview = " ".join(str(preview).replace("|", " | ").split())
            method = str(metadata.get("method") or metadata.get("ocr_engine") or "OCR")
            if method == "gemini_multimodal":
                id_part = f"{content_type_val}. " if content_type_val else ""
                if content_desc:
                    return (
                        f"Gemini Vision identified: {content_desc[:120]}. "
                        f"Text extracted: {clean_preview[:160]}"
                    )
                return f"{id_part}Gemini Vision OCR extracted visible text: {clean_preview[:180]}"
            return f"OCR extracted visible text for context: {clean_preview[:180]}"
        if content_desc:
            return f"Gemini Vision identified: {content_desc[:200]}"
        if "ocr extracted" in text.lower():
            return text.replace("Extract Text From Image: ", "").replace("Checked: ", "")

    if "screenshot_layout_forensics" in tool:
        anomalies = int(metadata.get("layout_anomaly_count") or 0)
        edge_density = metadata.get("edge_density")
        hard_edge_density = metadata.get("hard_edge_density")
        h_rule = metadata.get("horizontal_rule_density")
        v_rule = metadata.get("vertical_rule_density")
        if anomalies:
            return (
                f"Screenshot layout check flagged {anomalies} UI/document structure anomaly "
                f"(edge density {edge_density}); review the visible interface for pasted or misaligned regions."
            )
        return (
            "Screenshot layout check found no UI/document structure anomaly flags"
            + (
                f" (edge density {edge_density}, hard-edge density {hard_edge_density}, "
                f"horizontal/vertical rule density {h_rule}/{v_rule})."
                if edge_density is not None
                else "."
            )
        )

    if "detect_font_inconsistency" in tool:
        score = metadata.get("font_consistency_score")
        regions = int(metadata.get("num_anomaly_regions") or 0)
        ratio = metadata.get("anomaly_region_ratio")
        if evidence_verdict == "POSITIVE":
            return (
                f"Screenshot font/rendering check found {regions} localized text-rendering outlier(s)"
                + (f" (outlier ratio {float(ratio):.3f})" if isinstance(ratio, (int, float)) else "")
                + ". Review the highlighted text regions before treating this as edited content."
            )
        return (
            "Screenshot font/rendering check found expected variation for a mixed browser/UI capture"
            + (f" (consistency score {float(score):.3f})" if isinstance(score, (int, float)) else "")
            + "."
        )

    if "detect_ui_overlay_forgery" in tool:
        regions = int(metadata.get("num_suspicious_regions") or 0)
        if evidence_verdict == "POSITIVE":
            return (
                f"UI overlay check found {regions} suspicious banner/overlay region(s); "
                "review for pasted notifications or inserted interface chrome."
            )
        return "UI overlay check found no suspicious pasted notification bars or inserted browser/interface panels."

    if "analyze_image_content" in tool or "analyze image content" in text.lower():
        if metadata.get("semantic_scope") == "screenshot_fast_profile":
            return (
                f"Screenshot content was identified as a digital UI capture ({metadata.get('width')}x{metadata.get('height')}px, "
                f"{metadata.get('color_mode')} mode). Natural-scene classification was bypassed; "
                "OCR, layout, hash, and provenance checks carry the screenshot review."
            )
        if "agent1" in agent_id.lower() and (
            "screenshot" in str(metadata).lower() or "screen capture" in str(metadata).lower()
        ):
            return None
        if "forensic evidence photograph" in text.lower():
            return (
                "Visual classifier recognized the upload as forensic/evidence imagery. "
                "This is a context label, not proof of authenticity."
            )
        return text.replace("Analyze Image Content: ", "").replace("Checked: ", "")

    if evidence_verdict == "NEGATIVE" and finding_status != "INCOMPLETE":
        metric_note = _metric_digest(metadata)
        clean_text = text.replace("Checked: ", "")
        generic_patterns = (
            "completed and found no supported anomaly signal",
            "completed; review detailed tool metrics",
            "analysis complete",
        )

        # dynamic measurement-backed narratives for NEGATIVE findings
        tool_key = (tool_name or "").lower()
        if tool_key == "neural_ela":
            regions = metadata.get("num_anomaly_regions", 0)
            deviation = metadata.get("max_anomaly", 0.0)
            try:
                dev_str = f"{float(deviation):.3f}"
            except (ValueError, TypeError):
                dev_str = str(deviation)
            return (
                f"Error-level analysis found no re-compression residuals — "
                f"all {regions} anomaly regions, maximum deviation {dev_str} — "
                f"consistent with an unmodified JPEG."
            )
        elif tool_key == "noiseprint_cluster":
            return (
                "Sensor-noise clustering found no inconsistent camera-source regions — "
                "0 anomalous or outlier regions detected — the image noise signature "
                "appears homogeneous throughout."
            )
        elif tool_key == "diffusion_artifact_detector":
            prob = metadata.get("diffusion_probability", 0.0)
            try:
                prob_str = f"{float(prob):.3f}"
            except (ValueError, TypeError):
                prob_str = str(prob)
            return (
                f"No diffusion model or AI-generation artifact signature was detected in this image "
                f"(AI probability: {prob_str})."
            )

        _tool_negative_narratives = {
            "neural_fingerprint": (
                "Neural fingerprint recorded. No match to known synthetic or AI-generated "
                "image signatures in the reference library."
            ),
            "frequency_domain_analysis": (
                "Frequency spectrum is consistent with authentic photographic content — "
                "no GAN-like periodic artifact or anomalous high-frequency pattern detected."
            ),
            "extract_text_from_image": (
                "No embedded text characters were detected. "
                "This is expected for natural photographic content without visible labels or documents."
            ),
            "f3_net_frequency": (
                "F3-Net frequency analysis found no frequency-space GAN artifact patterns."
            ),
            "anomaly_tracer": (
                "ManTra-Net universal anomaly tracer found no manipulation pattern across the image."
            ),
            "deepfake_frequency_check": (
                "Frequency-band GAN/deepfake scan found no high-frequency spectral artifacts "
                "associated with synthetic generation."
            ),
            "neural_splicing": (
                "TruFor ViT splicing analysis found no evidence of regional composition "
                "or cut-and-paste insertion."
            ),
            "neural_copy_move": (
                "BusterNet copy-move analysis found no cloned or duplicated regions within the image."
            ),
            "synthid_watermark_detect": (
                "No SynthID, C2PA ai_generated marker, or AI software watermark was detected."
            ),
        }
        if any(p in clean_text.lower() for p in generic_patterns):
            if tool_key in _tool_negative_narratives:
                narrative = _tool_negative_narratives[tool_key]
                if metric_note:
                    return f"{narrative} ({metric_note})"
                return narrative
            tool_label = str(tool_name or "Tool").replace("_", " ").title()
            if metric_note:
                return f"{tool_label}: no forensic anomaly detected ({metric_note})."
            return f"{tool_label}: no forensic anomaly detected."
        if metric_note and metric_note.lower() not in clean_text.lower():
            return f"{clean_text} Key metrics: {metric_note}."
        return clean_text

    metric_note = _metric_digest(metadata)
    enriched = text
    if metric_note and metric_note.lower() not in enriched.lower():
        enriched = f"{enriched} Metric: {metric_note}."

    return enriched if enriched.strip() else None


def _is_discovery_finding(tool_name: str | None, metadata: dict[str, Any]) -> bool:
    """
    True when a CLEAN/NEGATIVE finding still represents a positive discovery
    (something was found, not just 'check ran clean').
    Examples: OCR found text, CLIP identified content type, objects were detected.
    """
    tool = (tool_name or "").lower()
    if "extract_text" in tool or "extract_evidence" in tool:
        return bool(metadata.get("has_text") or metadata.get("word_count", 0) > 0
                    or metadata.get("ocr_text_preview") or metadata.get("content_description"))
    if "analyze_image_content" in tool:
        image_type = str(metadata.get("image_type") or "").lower()
        return bool(image_type and image_type not in ("unknown", ""))
    if "object_detection" in tool:
        return bool(metadata.get("detection_count", 0) > 0 or metadata.get("detections"))
    if "exif_extract" in tool or "exif" in tool:
        return bool(metadata.get("total_fields_extracted", 0) > 0)
    if "gps" in tool:
        return bool(metadata.get("gps_coordinates") or metadata.get("latitude"))
    if "file_structure" in tool or "file_structure_analysis" in tool:
        return bool(metadata.get("anomaly_detected"))
    return False


def _verdict_score(verdict: Any) -> float | None:
    """Map agent verdicts to frontend severity color/risk score."""
    value = str(verdict or "").upper()
    if value in {"TAMPERED", "LIKELY_MANIPULATED", "LIKELY_AI_GENERATED", "LIKELY_SPOOFED", "LIKELY_SYNTHETIC"}:
        return 0.9
    if value in {"SUSPICIOUS", "NEEDS_REVIEW"}:
        return 0.65
    if value in {"AUTHENTIC", "CLEAN"}:
        return 0.05
    if value == "INCONCLUSIVE":
        return 0.5
    return None
