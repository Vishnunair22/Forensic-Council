"""Finding formatting — generates court-admissible reasoning and human-readable summaries.

Extracted from ReActLoopEngine to enable independent testing and reuse.
"""

from __future__ import annotations

from typing import Any

from core.structured_logging import get_logger
from core.tool_interpreters import _TOOL_INTERPRETERS
from core.tool_output_classifier import ToolOutputClassifier

logger = get_logger(__name__)

TOOL_LABELS: dict[str, str] = {
    "ela_full_image": "ELA — Image Manipulation",
    "ela_anomaly_classify": "ELA Anomaly Classification",
    "jpeg_ghost_detect": "JPEG Ghost Detection",
    "frequency_domain_analysis": "Frequency Domain Analysis",
    "deepfake_frequency_check": "GAN/Deepfake Frequency Check",
    "noise_fingerprint": "PRNU Noise Fingerprint",
    "copy_move_detect": "Copy-Move Forgery Detection",
    "extract_evidence_text": "OCR Text Extraction",
    "extract_text_from_image": "OCR Text Extraction",
    "analyze_image_content": "Semantic Image Analysis",
    "file_hash_verify": "File Hash Verification",
    "splicing_detect": "Splicing Detection",
    "roi_extract": "Region of Interest Extraction",
    "speaker_diarize": "Speaker Diarization",
    "anti_spoofing_detect": "Anti-Spoofing Detection",
    "prosody_analyze": "Prosody Analysis",
    "audio_splice_detect": "Audio Splice Detection",
    "background_noise_analysis": "Background Noise Consistency",
    "codec_fingerprinting": "Codec Fingerprinting",
    "audio_visual_sync": "Audio-Visual Sync Check",
    "object_detection": "Object Detection (YOLO)",
    "lighting_consistency": "Lighting & Shadow Consistency",
    "scene_incongruence": "Scene Incongruence (CLIP)",
    "secondary_classification": "Secondary Object Classification",
    "scale_validation": "Scale & Proportion Validation",
    "vector_contraband_search": "Threat / Contraband Vector Search",
    "lighting_correlation_initial": "Initial Lighting Correlation",
    "optical_flow_analysis": "Optical Flow Analysis",
    "frame_extraction": "Frame Window Extraction",
    "frame_consistency_analysis": "Frame Consistency Analysis",
    "face_swap_detection": "Face-Swap Detection",
    "video_metadata": "Video Metadata Extraction",
    "vfi_error_map": "VFI Motion Error Map",
    "thumbnail_coherence": "Thumbnail Coherence Check",
    "interframe_forgery_detector": "Interframe Forgery Detection",
    "rolling_shutter_validation": "Rolling Shutter Validation",
    "mediainfo_profile": "MediaInfo Container Profile",
    "av_file_identity": "AV File Identity Pre-Screen",
    "exif_extract": "EXIF Metadata Extraction",
    "metadata_anomaly_score": "Metadata Anomaly Score (ML)",
    "gps_timezone_validate": "GPS-Timezone Validation",
    "steganography_scan": "Steganography Scan",
    "file_structure_analysis": "File Structure Analysis",
    "hex_signature_scan": "Hex Signature Scan",
    "timestamp_analysis": "Timestamp Consistency Analysis",
    "device_fingerprint_db": "Device Fingerprint Analysis",
    "adversarial_robustness_check": "Adversarial Robustness Check",
    "neural_ela": "Neural ELA — ViT Manipulation Detection",
    "noiseprint_cluster": "Noiseprint++ Sensor Clustering",
    "neural_fingerprint": "SigLIP2 Neural Perceptual Fingerprint",
    "neural_splicing": "TruFor ViT Splicing Detection",
    "neural_copy_move": "BusterNet Dual-Branch Copy-Move",
    "anomaly_tracer": "ManTra-Net Universal Anomaly Tracer",
    "f3_net_frequency": "F3-Net Frequency Artifact Analysis",
    "diffusion_artifact_detector": "Diffusion/AI-Generation Artifact Detection",
    "synthid_watermark_detect": "SynthID / AI Watermark Detection",
    "visual_evidence_profile": "Visual Evidence Profile",
    "gemini_deep_forensic": "Visual Evidence Profile",
    "voice_clone_detect": "Voice Clone Detection",
    "enf_analysis": "ENF Frequency Analysis",
    "sensor_db_query": "Camera Sensor DB Query",
}


def build_detailed_reasoning(tool_name: str, output: dict) -> str:
    """
    Generate specific, court-admissible reasoning based on tool output.
    Each tool type produces a unique numerical-rich summary sentence.
    """
    if not isinstance(output, dict):
        return ""

    lower_tool = tool_name.lower()

    if lower_tool in ("ela_full_image", "neural_ela"):
        num_regions = output.get("num_anomaly_regions", 0)
        threshold = output.get("threshold_used", output.get("ela_threshold", "N/A"))
        max_ela = output.get("max_ela_value", output.get("max_ela", "N/A"))
        return (
            f"ELA analysis at threshold {threshold}: {num_regions} anomaly regions detected. "
            f"Maximum ELA value: {max_ela}."
        )

    if lower_tool in ("noise_fingerprint", "noiseprint_cluster"):
        consistency = output.get("noise_consistency_score", output.get("consistency_score", 0))
        blocks = output.get("blocks_analyzed", output.get("num_blocks", 0))
        verdict = str(output.get("verdict", "") or "")
        return (
            f"PRNU noise fingerprint: Consistency score {float(consistency):.3f} "
            f"across {int(blocks)} analyzed blocks. "
            f"{'No sensor inconsistencies detected.' if not verdict or 'inconsist' not in verdict.lower() else 'Potential sensor mismatch detected.'}"
        )

    if lower_tool == "object_detection":
        detections = output.get("detections", [])
        classes = set(d.get("class", "") for d in detections if isinstance(d, dict) and d.get("class"))
        return (
            f"YOLO object detection: {len(detections)} objects detected "
            f"across {len(classes)} classes. "
            f"Objects: {', '.join(sorted(classes)[:5])}."
        )

    if lower_tool in {"visual_evidence_profile", "gemini_deep_forensic"}:
        verdict = output.get(
            "authenticity_verdict",
            output.get("verdict", "INCONCLUSIVE"),
        )
        signals = output.get(
            "manipulation_signals",
            output.get("visual_manipulation_signals", []),
        )
        text = output.get(
            "text_content",
            output.get("extracted_text", ""),
        )
        parts = [f"Visual evidence profile verdict: {verdict}."]
        if signals and isinstance(signals, list):
            parts.append(
                f"Manipulation signals: {', '.join(str(item) for item in signals[:3])}."
            )
        if text and isinstance(text, str) and len(text) > 3:
            parts.append(f"Text extracted: '{text[:120]}'.")
        return " ".join(parts)

    if lower_tool == "frequency_domain_analysis":
        anomaly_score = output.get("anomaly_score", 0)
        hfr = output.get("high_freq_ratio", output.get("high_frequency_ratio", "N/A"))
        regions = output.get("num_anomaly_regions", 0)
        detected = output.get("anomaly_detected", False)
        return (
            f"FFT frequency analysis: anomaly score {float(anomaly_score):.3f}, "
            f"high-frequency ratio {hfr}, {int(regions)} anomalous region(s). "
            f"{'Anomalies detected.' if detected else 'No significant frequency anomalies.'}"
        )

    if lower_tool == "extract_text_from_image":
        word_count = output.get("word_count", 0)
        method = output.get("method", output.get("ocr_engine", "OCR"))
        preview = str(output.get("text", output.get("full_text", "")) or "")[:120]
        return (
            f"{method} OCR: {int(word_count)} words extracted. "
            f"Content: '{preview}'" if preview else f"{method} OCR: {int(word_count)} words extracted."
        )

    if lower_tool in ("exif_extract",):
        fields = output.get("total_fields_extracted", 0)
        camera = output.get("camera_make", output.get("device_model", ""))
        gps = "GPS coordinates present" if output.get("gps_coordinates") else "No GPS data"
        return (
            f"EXIF extraction: {int(fields)} fields found. "
            f"{'Camera: ' + str(camera) + '. ' if camera else ''}"
            f"{gps}."
        )

    if lower_tool == "compression_risk_audit":
        penalty = output.get("compression_penalty", 1.0)
        raw_platform = output.get("platform", output.get("detected_platform", "unknown"))
        platform = (
            "stripped or platform-normalized metadata"
            if str(raw_platform or "").lower() in {"", "unknown", "none"}
            else raw_platform
        )
        impact = output.get("forensic_reliability_impact", "not specified")
        return (
            f"Compression/platform audit: {platform}; reliability impact {impact}; "
            f"penalty factor {float(penalty):.2f}. This limits provenance strength but is not a manipulation signal by itself."
        )

    if lower_tool == "file_structure_analysis":
        anomalies = output.get("anomalies")
        anomaly_count = len(anomalies) if isinstance(anomalies, list) else int(output.get("anomaly_count", 0) or 0)
        header_valid = output.get("header_valid", output.get("valid_header", True))
        trailer_valid = output.get("trailer_valid", output.get("valid_trailer", True))
        if anomaly_count:
            details = "; ".join(str(x) for x in anomalies[:3]) if isinstance(anomalies, list) else f"{anomaly_count} anomaly flag(s)"
            return f"File structure check found {details}. Header valid: {bool(header_valid)}; trailer valid: {bool(trailer_valid)}."
        return (
            f"File structure check found a valid header/trailer profile and no appended-payload indicators. "
            f"Header valid: {bool(header_valid)}; trailer valid: {bool(trailer_valid)}."
        )

    if lower_tool in ("file_hash_verify", "hash_verify"):
        match = output.get("hash_matches", output.get("hash_match", None))
        status_str = "matched intake custody" if match else "mismatched intake custody"
        return f"SHA-256 hash verification: {status_str}."

    if lower_tool in ("lighting_consistency", "lighting_correlation_initial"):
        score = output.get("lighting_consistency_score", output.get("correlation_score", 0))
        direction = output.get("light_direction_consistency", "unknown")
        return (
            f"Lighting analysis: consistency score {float(score):.3f}, "
            f"direction consistency: {direction}."
        )

    if lower_tool in ("scene_incongruence",):
        score = output.get("incongruence_score", 0)
        anomalies = output.get("anomalies", output.get("contextual_anomalies", []))
        return (
            f"Scene incongruence analysis: score {float(score):.3f} "
            f"with {len(anomalies) if isinstance(anomalies, list) else 0} anomaly flag(s)."
        )

    if lower_tool in ("neural_splicing", "splicing_detect"):
        detected = output.get("splicing_detected", output.get("manipulation_detected", False))
        conf = output.get("confidence", output.get("tampering_score", 0))
        return (
            f"Splicing detection: {'SPLICE DETECTED' if detected else 'No splice detected'}. "
            f"Confidence: {float(conf):.3f}."
        )

    if lower_tool == "neural_copy_move":
        detected = output.get("copy_move_detected", output.get("manipulation_detected", False))
        matches = output.get("keypoint_matches", output.get("num_matches", 0))
        return (
            f"Copy-move detection: {'FORGERY DETECTED' if detected else 'No copy-move forgery detected'}. "
            f"Keypoint matches: {int(matches)}."
        )

    if lower_tool == "deepfake_frequency_check":
        prob = output.get("deepfake_probability", output.get("ai_probability", 0))
        return f"Deepfake frequency analysis: AI generation probability {float(prob):.3f}."

    if lower_tool == "diffusion_artifact_detector":
        detected = output.get("diffusion_detected", output.get("ai_generated", False))
        prob = output.get("diffusion_probability", output.get("ai_probability", 0))
        return (
            f"Diffusion artifact detection: "
            f"{'AI-generation artifacts detected' if detected else 'No AI-generation artifacts detected'}. "
            f"Probability: {float(prob):.3f}."
        )

    if lower_tool == "audio_splice_detect":
        detected = output.get("splice_detected", False)
        count = output.get("splice_count", output.get("num_splices", 0))
        return f"Audio splice detection: {int(count)} splice(s) {'detected' if detected else 'found'}."

    if lower_tool == "codec_fingerprinting":
        detected = output.get("re_encoding_detected", False)
        codec = output.get("detected_codec", output.get("codec", "unknown"))
        return (
            f"Codec fingerprinting: {'Re-encoding detected' if detected else 'No re-encoding detected'}. "
            f"Codec: {codec}."
        )

    if lower_tool in ("optical_flow_analysis",):
        anomalies = output.get("anomaly_count", 0)
        flow_score = output.get("flow_consistency_score", output.get("consistency_score", 0))
        return (
            f"Optical flow analysis: {int(anomalies)} anomaly frame(s), "
            f"consistency score {float(flow_score):.3f}."
        )

    if lower_tool in ("frame_consistency_analysis", "interframe_forgery_detector"):
        discontinuities = output.get("discontinuity_count", output.get("anomaly_count", 0))
        ssim = output.get("ssim_variance", output.get("consistency_score", 0))
        return (
            f"Frame consistency: {int(discontinuities)} discontinuity(ies), "
            f"SSIM variance {float(ssim):.3f}."
        )

    # Fallback: extract key numerical fields
    key_results = []
    for key in ("verdict", "score", "confidence", "confidence_raw", "anomaly_count",
                 "detection_count", "num_anomaly_regions", "splice_count", "word_count"):
        if key in output:
            key_results.append(f"{key}={output[key]}")
    if key_results:
        return f"Tool results: {', '.join(key_results)}."

    return ""


def shape_analyst_finding(
    tool_label: str,
    message: str,
    evidence_verdict: str,
    status: str,
    output: dict[str, Any],
) -> str:
    """Turn technical tool output into a concise analyst-facing finding."""
    verdict = (evidence_verdict or "INCONCLUSIVE").upper()
    limitation = (
        output.get("limitation")
        or output.get("limitation_note")
        or output.get("note")
        or output.get("fallback_reason")
        or ""
    )
    limitation = str(limitation).strip()
    if len(limitation) > 180:
        limitation = limitation[:177] + "..."

    if verdict == "POSITIVE":
        prefix = "Finding"
        meaning = "This is a forensic signal and should be weighed with corroborating tools."
    elif verdict == "NEGATIVE":
        prefix = "Checked"
        meaning = "This supports the absence of this specific anomaly."
    elif verdict == "NOT_APPLICABLE":
        prefix = "Skipped"
        meaning = "This does not count for or against authenticity."
    elif verdict == "ERROR" or status == "INCOMPLETE":
        prefix = "Incomplete"
        meaning = "This is a tool limitation, not evidence of manipulation."
    else:
        prefix = "Inconclusive"
        meaning = "The signal is not strong enough to support a firm conclusion."

    parts = [f"{tool_label}: {prefix}: {message.strip()}"]
    if limitation and verdict in {"INCONCLUSIVE", "ERROR", "NOT_APPLICABLE"}:
        parts.append(f"Limitation: {limitation}")
    parts.append(meaning)
    return " ".join(parts)


def build_readable_summary(
    tool_name: str,
    task_description: str,
    tool_result: Any,
    confidence: float,
    status: str,
    evidence_verdict: str = "INCONCLUSIVE",
    llm_reasoning: str | None = None,
    agent_id: str = "",
) -> str:
    """
    Build a human-readable summary from a tool result.

    Uses tool-specific detailed reasoning builders for rich,
    court-admissible findings. Falls back to generic scalar extraction.
    """
    tool_label = tool_name.replace("_", " ").title()

    if not tool_result.success:
        err = tool_result.error or "unknown error"
        for prefix in (
            "[ToolUnavailableError]",
            "[ToolError]",
            "ToolError:",
            "Exception:",
            "ValueError:",
            "TypeError:",
            "KeyError:",
        ):
            err = err.replace(prefix, "").strip()
        if "ModuleNotFoundError" in err or "ImportError" in err or "No module named" in err:
            dep_name = err.split("'")[1] if "'" in err else "required dependency"
            err_msg = f"ML dependency '{dep_name}' not installed — tool skipped."
        elif "Timeout" in err or "timeout" in err:
            err_msg = "Tool timed out — likely model cold-start. Result skipped."
        elif "FileNotFoundError" in err:
            err_msg = "Evidence file not accessible — skipped."
        else:
            err_msg = err[:140] + ("…" if len(err) > 140 else "")
        return (
            f"{tool_label}: Incomplete: {err_msg} "
            "This is a tool/runtime limitation, not evidence of manipulation. "
            "Other available checks continued."
        )

    reasoning_prefix = ""
    if llm_reasoning:
        last_thought = llm_reasoning.strip().split("\n")[-1]
        if len(last_thought) > 120:
            last_thought = last_thought[:117] + "..."
        reasoning_prefix = f"[{last_thought}] "

    output = tool_result.output or {}

    if isinstance(output, dict):
        if ToolOutputClassifier.has_not_applicable_marker(output) or (
            output.get("available") is False and ToolOutputClassifier.looks_like_condition_skip(output)
        ):
            reason = (
                output.get("reason")
                or output.get("note")
                or output.get("skipped_reason")
                or output.get("limitation_note")
                or "This tool is not applicable to the submitted evidence."
            )
            return (
                f"{tool_label}: Skipped: {str(reason)[:220]} "
                "This does not count as suspicious evidence."
            )

        if output.get("available") is False and not output.get("error"):
            reason = (
                output.get("note")
                or output.get("reason")
                or "Tool unavailable in this environment."
            )
            return (
                f"{tool_label}: Incomplete: {str(reason)[:220]} "
                "This is reported as a limitation, not as a forensic signal."
            )

    def _is_stub(output: Any) -> bool:
        if not isinstance(output, dict):
            return False
        return (
            output.get("status") in ("stub", "stub_response")
            or output.get("stub_result") is True
        )

    if _is_stub(output):
        return (
            f"{reasoning_prefix}{tool_label}: The agent's external module returned a temporary placeholder response. "
            f"This indicates that advanced ML features are still structurally integrating. "
            f"Confidence: {confidence:.0%}."
        )

    detailed = build_detailed_reasoning(tool_name, output)
    if detailed:
        return shape_analyst_finding(
            tool_label=tool_label,
            message=str(detailed),
            evidence_verdict=evidence_verdict,
            status=status,
            output=output,
        )

    interpreter = _TOOL_INTERPRETERS.get(tool_name)
    if interpreter and tool_result.success:
        try:
            interpreted_msg = interpreter(output)
            return shape_analyst_finding(
                tool_label=tool_label,
                message=str(interpreted_msg),
                evidence_verdict=evidence_verdict,
                status=status,
                output=output,
            )
        except Exception as exc:
            logger.debug(
                "Tool interpreter failed; using generic summary",
                agent_id=agent_id,
                tool_name=tool_name,
                error=str(exc),
            )

    highlights: list[str] = []
    for key, value in output.items():
        if key.startswith("_") or key in (
            "status",
            "tool_name",
            "analysis_report",
            "artifact_id",
            "session_id",
            "case_id",
        ):
            continue

        clean_key = key.replace("_", " ")

        if isinstance(value, list):
            if len(value) > 5:
                highlights.append(f"{len(value)} {clean_key}")
            else:
                items = ", ".join(str(v) for v in value)
                if items:
                    highlights.append(f"{clean_key}: {items}")
            continue

        if isinstance(value, dict):
            continue

        if isinstance(value, bool):
            highlights.append(f"{clean_key}: {'yes' if value else 'no'}")
        elif isinstance(value, float):
            highlights.append(f"{clean_key} {value:.3f}")
        elif isinstance(value, int):
            highlights.append(f"{clean_key} {value}")
        elif isinstance(value, str) and len(value) < 200:
            highlights.append(f"{clean_key}: {value}")

    if highlights:
        top = highlights[:4]
        detail = "; ".join(top)
        if len(highlights) > 4:
            detail += f" (+{len(highlights) - 4} more)"
        return shape_analyst_finding(
            tool_label=tool_label,
            message=f"{detail}.",
            evidence_verdict=evidence_verdict,
            status=status,
            output=output if isinstance(output, dict) else {},
        )
    else:
        return f"{tool_label}: analysis complete — no anomalies detected."


def format_tool_result(result: Any) -> str:
    """Format a tool result for observation content."""
    if result.unavailable:
        return f"Tool '{result.tool_name}' is unavailable. Error: {result.error}"
    if result.success:
        return f"Tool '{result.tool_name}' succeeded. Output: {result.output}"
    return f"Tool '{result.tool_name}' failed. Error: {result.error}"
