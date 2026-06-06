"""Tool output classification — determines evidence verdict and confidence.

Extracted from ReActLoopEngine to enable independent testing and reuse.
All methods are pure/static; no instance state required.
"""

from __future__ import annotations

from typing import Any

from core.structured_logging import get_logger

logger = get_logger(__name__)


class ToolOutputClassifier:
    """Classify heterogeneous tool outputs into the strict evidence contract."""

    @staticmethod
    def has_not_applicable_marker(output: dict[str, Any]) -> bool:
        if str(output.get("verdict", "")).upper() == "NOT_APPLICABLE":
            return True
        if output.get("not_applicable") is True or output.get("skipped") is True:
            return True
        return any(
            bool(output.get(k))
            for k in (
                "ela_not_applicable",
                "ghost_not_applicable",
                "noise_fingerprint_not_applicable",
                "prnu_not_applicable",
                "gan_not_applicable",
                "roi_skipped",
            )
        )

    @staticmethod
    def looks_like_condition_skip(output: dict[str, Any]) -> bool:
        text = " ".join(
            str(output.get(k, ""))
            for k in ("reason", "note", "skipped_reason", "file_format_note", "limitation_note")
        ).lower()
        condition_words = (
            "not applicable",
            "requires",
            "no gps",
            "no timestamp",
            "no readable",
            "no face",
            "no audio",
            "not enough",
            "insufficient",
            "cannot be verified from metadata",
        )
        return any(word in text for word in condition_words)

    @staticmethod
    def positive_signal(output: dict[str, Any]) -> bool:
        if (
            output.get("not_applicable")
            or output.get("skipped")
            or str(output.get("status", "")).upper() in {"NOT_APPLICABLE", "SKIPPED"}
            or str(output.get("verdict", "")).upper() == "NOT_APPLICABLE"
        ):
            return False

        positive_keys = (
            "manipulation_detected",
            "splicing_detected",
            "copy_move_detected",
            "is_ai_generated",
            "gan_artifact_detected",
            "anomaly_detected",
            "inconsistency_detected",
            "contextual_anomalies_detected",
            "scene_incongruent",
            "concern_flag",
            "spoofing_detected",
            "spoof_detected",
            "is_spoofed",
            "synthetic_detected",
            "splice_detected",
            "re_encoding_detected",
            "shift_detected",
            "prosody_anomaly",
            "sync_drift_detected",
            "desync_detected",
            "face_swap_detected",
            "deepfake_suspected",
            "discontinuity_detected",
            "chimeric_signature_detected",
            "has_appended_data",
            "editing_software_detected",
            "is_anomalous",
        )
        nested_metadata = output.get("metadata") if isinstance(output.get("metadata"), dict) else {}
        if nested_metadata and ToolOutputClassifier.positive_signal(nested_metadata):
            return True
        if any(bool(output.get(k)) for k in positive_keys):
            return True
        if any(bool(output.get(f"gemini_{k}")) for k in positive_keys):
            return True
        if output.get("gemini_manipulation_signals") or output.get("manipulation_signals"):
            confidence = float(output.get("confidence", 0.0) or 0.0)
            if confidence >= 0.40:
                return True
        if output.get("weapon_detections") or output.get("contraband_detections"):
            return True
        if (
            output.get("plausible") is False
            or output.get("hash_match") is False
            or output.get("hash_matches") is False
            or output.get("scale_consistent") is False
            or output.get("lighting_consistent") is False
            or output.get("inconsistency_detected") is True
        ):
            return True

        if output.get("contextual_anomalies") and len(output.get("contextual_anomalies", [])) > 0:
            return True

        if output.get("manipulation_signals") and len(output.get("manipulation_signals", [])) > 0:
            return True
        if int(output.get("anomaly_count", 0) or 0) > 0:
            return True
        verdict = str(output.get("verdict", "")).upper()
        authenticity_verdict = str(output.get("authenticity_verdict", "")).upper()
        verdict_is_positive = verdict in {
            "SUSPICIOUS",
            "TAMPERED",
            "MANIPULATED",
            "INCONSISTENT",
            "ANOMALOUS",
            "SPLICE_DETECTED",
            "SPLICE_SUSPECTED",
            # Audio synthesis/spoof verdicts: voice_clone_detect and
            # anti_spoofing_detect emit these on their neural paths with no
            # accompanying positive flag, so without them here a confirmed
            # synthetic voice or spoof was never classified POSITIVE.
            "LIKELY_SYNTHETIC",
            "SYNTHETIC",
            "CLONE",
            "LIKELY_SPOOFED",
            "SPOOF",
        } or authenticity_verdict in {
            "SUSPICIOUS",
            "LIKELY_MANIPULATED",
            "AI_GENERATED",
            "TAMPERED",
            "MANIPULATED",
            "LIKELY_SYNTHETIC",
            "LIKELY_SPOOFED",
        }
        if verdict_is_positive and output.get("court_defensible") is False:
            return bool(output.get("manipulation_detected") or output.get("splicing_detected"))
        return verdict_is_positive

    @staticmethod
    def extract_confidence(output: Any, tool_name: str, agent_id: str = "") -> tuple[float, bool]:
        """Extract a 0-1 confidence score from tool output. Returns (confidence, from_fallback)."""
        raw_conf: float | None = None

        def _as_unit_float(value: Any) -> float | None:
            try:
                parsed = float(value)
            except (TypeError, ValueError):
                return None
            if parsed > 1.0 and parsed <= 100.0:
                parsed = parsed / 100.0
            return max(0.0, min(1.0, parsed))

        if isinstance(output, dict):
            if output.get("shared_context_available") is not None:
                raw_conf = 0.75 if output.get("shared_context_available") else 0.0
            elif output.get("available") is False or output.get("degraded") is True or "error" in output:
                raw_conf = 0.0
            for key in ("confidence", "confidence_raw", "confidence_score"):
                if raw_conf is None:
                    raw_conf = _as_unit_float(output.get(key))
                    if raw_conf is not None:
                        break
            if raw_conf is None:
                for key in (
                    "anomaly_score",
                    "tampering_score",
                    "synthetic_probability",
                    "forgery_score",
                    "diffusion_probability",
                ):
                    val = _as_unit_float(output.get(key))
                    if val is not None:
                        raw_conf = val if ToolOutputClassifier.positive_signal(output) else 1.0 - val
                        break
            if raw_conf is None:
                for key in (
                    "noise_consistency_score",
                    "consistency_score",
                    "overall_consistency",
                    "avg_confidence",
                    "confidence_score",
                    "top_confidence",
                    "max_confidence",
                    "mean_confidence",
                    "score",
                    "probability",
                    "top_score",
                    "similarity",
                    "top_similarity",
                    "trace_continuity",
                    "provenance_score",
                    "completeness",
                ):
                    val = _as_unit_float(output.get(key))
                    if val is not None:
                        raw_conf = val
                        break
            if raw_conf is None:
                if "detections" in output:
                    detections = output.get("detections") or []
                    raw_conf = 0.65 if len(detections) > 0 else 0.82
                elif "objects_detected" in output:
                    raw_conf = 0.65 if len(output.get("objects_detected") or []) > 0 else 0.82
                elif "weapon_detections" in output:
                    raw_conf = 0.70 if len(output.get("weapon_detections") or []) > 0 else 0.82
                elif "detection_count" in output:
                    raw_conf = 0.70 if int(output.get("detection_count") or 0) > 0 else 0.82
                elif "classes_found" in output:
                    classes_found = output.get("classes_found") or []
                    raw_conf = 0.65 if hasattr(classes_found, "__len__") and len(classes_found) > 0 else 0.82
                elif output.get("hash_matches") is True or output.get("hash_match") is True:
                    raw_conf = 1.0
                elif output.get("hash_matches") is False or output.get("hash_match") is False:
                    raw_conf = 0.30
                elif output.get("scale_consistent") is True:
                    raw_conf = 0.85
                elif output.get("scale_consistent") is False:
                    raw_conf = 0.40
                elif "verdict" in output:
                    v = str(output.get("verdict", "")).upper()
                    if v in (
                        "CONSISTENT",
                        "AUTHENTIC",
                        "CLEAN",
                        "NATURAL_OR_CLEAN",
                        "LIKELY_AUTHENTIC",
                        "LIKELY_GENUINE",
                        "CONTENT_CREDENTIALS_PRESENT",
                        "NO_CONTENT_CREDENTIALS",
                    ):
                        raw_conf = 0.85
                    elif v in (
                        "INCONSISTENT",
                        "SUSPICIOUS",
                        "TAMPERED",
                        "SPLICE_SUSPECTED",
                        "SPLICE_DETECTED",
                    ):
                        raw_conf = 0.40
                    elif v in ("INCONCLUSIVE", "ERROR", "NO_ENF_SIGNAL", "TOO_SHORT"):
                        raw_conf = 0.50
                    elif v == "NOT_APPLICABLE":
                        raw_conf = 0.0
                elif output.get("ai_probability") is not None:
                    raw_conf = round(max(0.10, 1.0 - float(output["ai_probability"])), 3)
                elif output.get("synthetic_probability") is not None:
                    raw_conf = round(max(0.10, 1.0 - float(output["synthetic_probability"])), 3)
                elif output.get("spoof_probability") is not None:
                    raw_conf = round(max(0.10, 1.0 - float(output["spoof_probability"])), 3)
                elif "gemini_verdict" in output:
                    v = str(output.get("gemini_verdict", "")).upper()
                    if v in ("AUTHENTIC", "LIKELY_AUTHENTIC", "CLEAN"):
                        raw_conf = 0.85
                    elif v in ("SUSPICIOUS", "MANIPULATED", "ALTERED"):
                        raw_conf = 0.40
                    else:
                        raw_conf = 0.50
                elif "anomalies" in output and isinstance(output["anomalies"], list):
                    num_anomalies = len(output["anomalies"])
                    raw_conf = max(0.40, 1.0 - (num_anomalies * 0.15))
                elif output.get("num_anomaly_regions") is not None:
                    raw_conf = 0.85 if int(output["num_anomaly_regions"]) == 0 else 0.40
                elif (
                    output.get("anomaly_detected") is True
                    or output.get("inconsistency_detected") is True
                ):
                    raw_conf = 0.40
                elif (
                    output.get("anomaly_detected") is False
                    or output.get("inconsistency_detected") is False
                ):
                    raw_conf = 0.85
                elif output.get("header_valid") is not None:
                    anomalies = output.get("anomalies", [])
                    raw_conf = 0.85 if isinstance(anomalies, list) and len(anomalies) == 0 else 0.40
                elif output.get("editing_software_detected") is True:
                    raw_conf = 0.30
                elif output.get("editing_software_detected") is False:
                    raw_conf = 0.90
                elif "present_fields" in output and "absent_fields" in output:
                    present = len(output.get("present_fields") or [])
                    absent = len(output.get("absent_fields") or [])
                    total = present + absent
                    raw_conf = max(0.40, min(0.90, present / total)) if total > 0 else 0.50
                elif "plausible" in output:
                    p = output.get("plausible")
                    raw_conf = 0.80 if p is True else (0.40 if p is False else 0.50)
                elif output.get("c2pa_present") is not None or output.get("provenance_found") is not None:
                    raw_conf = 0.85 if output.get("c2pa_present") or output.get("provenance_found") else 0.50

        from_fallback = raw_conf is None
        try:
            confidence = float(raw_conf) if raw_conf is not None else 0.50
        except (TypeError, ValueError):
            confidence = 0.50
            from_fallback = True

        if from_fallback:
            logger.warning(
                "Unrecognised tool output format — confidence fallback to 0.50",
                tool=tool_name,
                agent_id=agent_id,
                output_keys=list(output.keys())
                if isinstance(output, dict)
                else type(output).__name__,
            )
        return confidence, from_fallback

    @staticmethod
    def classify(
        output: Any,
        tool_name: str,
        confidence: float,
        conf_from_fallback: bool,
    ) -> tuple[str, str, float | None, bool]:
        """
        Convert heterogeneous tool output into the strict evidence contract.

        Returns (status, evidence_verdict, confidence_or_none, court_defensible).
        """
        if not isinstance(output, dict):
            return "INCONCLUSIVE", "INCONCLUSIVE", confidence, False

        if output.get("error"):
            return "INCOMPLETE", "ERROR", None, False

        if ToolOutputClassifier.has_not_applicable_marker(output):
            return "NOT_APPLICABLE", "NOT_APPLICABLE", None, False

        if output.get("available") is False:
            if ToolOutputClassifier.looks_like_condition_skip(output):
                return "NOT_APPLICABLE", "NOT_APPLICABLE", None, False
            return "INCOMPLETE", "ERROR", None, False

        if ToolOutputClassifier.looks_like_condition_skip(output) and confidence <= 0.05:
            return "NOT_APPLICABLE", "NOT_APPLICABLE", None, False

        declared_status = str(output.get("status", "")).upper()
        if declared_status in {"INCOMPLETE", "FAILED", "ERROR"}:
            return "INCOMPLETE", "ERROR", None, False
        if declared_status in {"NOT_APPLICABLE", "SKIPPED"}:
            return "NOT_APPLICABLE", "NOT_APPLICABLE", None, False

        court_defensible = bool(output.get("court_defensible", True))
        declared_evidence_verdict = str(
            output.get("evidence_verdict")
            or (
                output.get("metadata", {}).get("evidence_verdict")
                if isinstance(output.get("metadata"), dict)
                else ""
            )
            or ""
        ).upper()
        if declared_evidence_verdict == "POSITIVE":
            return "CONFIRMED", "POSITIVE", confidence, court_defensible
        if declared_evidence_verdict == "NEGATIVE":
            return "CONFIRMED", "NEGATIVE", confidence, court_defensible
        if declared_evidence_verdict == "INCONCLUSIVE":
            return "INCONCLUSIVE", "INCONCLUSIVE", confidence, court_defensible
        if ToolOutputClassifier.positive_signal(output):
            return "CONFIRMED", "POSITIVE", confidence, court_defensible

        inconclusive_verdicts = {"INCONCLUSIVE", "UNKNOWN", "NO_ENF_SIGNAL"}
        verdict = str(output.get("verdict", "")).upper()
        declared_clean = verdict in {
            "AUTHENTIC",
            "CLEAN",
            "CONSISTENT",
            "LIKELY_AUTHENTIC",
            "LIKELY_GENUINE",
            "NATURAL_OR_CLEAN",
        } or declared_status in {"CONFIRMED", "COMPLETE", "OK", "SUCCESS"}
        if verdict in inconclusive_verdicts or (conf_from_fallback and not declared_clean):
            return "INCONCLUSIVE", "INCONCLUSIVE", confidence, court_defensible

        return "CONFIRMED", "NEGATIVE", confidence, court_defensible
