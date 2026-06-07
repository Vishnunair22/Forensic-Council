from __future__ import annotations

from typing import Any


def _tool_name(finding: dict[str, Any]) -> str:
    meta = finding.get("metadata") or {}
    return str(meta.get("tool_name") or finding.get("tool_name") or "")


def _tool_meta(finding: dict[str, Any]) -> dict[str, Any]:
    meta = finding.get("metadata") or {}
    return meta


def _evidence_verdict_of(finding: dict[str, Any]) -> str:
    meta = finding.get("metadata") or {}
    return str(
        meta.get("evidence_verdict")
        or finding.get("evidence_verdict")
        or "UNKNOWN"
    ).upper()


def _confidence_of(finding: dict[str, Any]) -> float:
    meta = finding.get("metadata") or {}
    return float(
        meta.get("confidence_raw")
        or meta.get("confidence")
        or finding.get("confidence_raw")
        or 0.0
    )


class FindingHumanizer:

    @staticmethod
    def humanize_finding(finding: dict[str, Any]) -> dict[str, Any]:
        tool = _tool_name(finding)
        meta = _tool_meta(finding)
        verdict = _evidence_verdict_of(finding)
        conf = _confidence_of(finding)

        tool_lower = tool.lower()

        if "ela" in tool_lower or "ela_full_image" in tool_lower:
            statement = FindingHumanizer._humanize_ela(meta, verdict, conf)
        elif "noiseprint" in tool_lower or "noise_fingerprint" in tool_lower or "noise" in tool_lower:
            statement = FindingHumanizer._humanize_noise(meta, verdict, conf)
        elif "splicing" in tool_lower or "splicing_detect" in tool_lower:
            statement = FindingHumanizer._humanize_splicing(meta, verdict, conf)
        elif "diffusion" in tool_lower or "ai_generated" in tool_lower or "ai" in tool_lower:
            statement = FindingHumanizer._humanize_ai_detection(meta, verdict, conf)
        elif "hash" in tool_lower or "file_hash" in tool_lower:
            statement = FindingHumanizer._humanize_hash(meta, verdict, conf)
        elif "copy_move" in tool_lower:
            statement = FindingHumanizer._humanize_copy_move(meta, verdict, conf)
        elif "frequency" in tool_lower or "f3_net" in tool_lower or "deepfake" in tool_lower:
            statement = FindingHumanizer._humanize_frequency(meta, verdict, conf)
        elif "font" in tool_lower:
            statement = FindingHumanizer._humanize_font(meta, verdict, conf)
        elif "ui_overlay" in tool_lower:
            statement = FindingHumanizer._humanize_ui_overlay(meta, verdict, conf)
        elif "scene_incongruence" in tool_lower:
            statement = FindingHumanizer._humanize_scene_incongruence(meta, verdict, conf)
        elif "visual_evidence_profile" in tool_lower or "visual_profile" in tool_lower:
            statement = FindingHumanizer._humanize_visual_profile(meta, verdict, conf)
        else:
            statement = FindingHumanizer._humanize_generic(finding)

        finding["court_statement"] = statement
        return finding

    @staticmethod
    def _humanize_ela(meta: dict, verdict: str, conf: float) -> str:
        num_regions = meta.get("num_anomaly_regions", 0)
        max_anomaly = meta.get("max_anomaly", 0)
        conf_text = FindingHumanizer._confidence_text(conf)

        if verdict in ("POSITIVE", "SUSPICIOUS") or num_regions > 0:
            return (
                f"Error Level Analysis, a technique that detects digital editing by examining "
                f"JPEG compression patterns, identified {num_regions} suspicious region(s) "
                f"with a maximum anomaly score of {max_anomaly:.1f}. "
                f"This finding has {conf_text} and suggests the image may have been altered "
                f"after its original creation."
            )
        return (
            f"Error Level Analysis examined the image's JPEG compression patterns and "
            f"found no signs of digital manipulation ({conf_text})."
        )

    @staticmethod
    def _humanize_noise(meta: dict, verdict: str, conf: float) -> str:
        conf_text = FindingHumanizer._confidence_text(conf)
        if verdict in ("POSITIVE", "INCONSISTENT"):
            outliers = meta.get("outlier_region_count", 0)
            return (
                f"Camera sensor noise analysis detected {outliers} region(s) with "
                f"inconsistent noise patterns, suggesting portions of the image may "
                f"originate from different cameras or sensors ({conf_text})."
            )
        return (
            f"Camera sensor noise analysis found the image's noise pattern to be "
            f"consistent across all regions, suggesting it was captured by a single "
            f"device ({conf_text})."
        )

    @staticmethod
    def _humanize_splicing(meta: dict, verdict: str, conf: float) -> str:
        method = "neural network" if meta.get("method") == "neural" else "pattern-matching"
        conf_text = FindingHumanizer._confidence_text(conf)

        if verdict == "POSITIVE" or meta.get("splicing_detected"):
            return (
                f"Image splicing analysis using {method} detection identified signs that "
                f"portions of this image originated from different sources and were digitally "
                f"combined ({conf_text}). This suggests the image is a composite."
            )
        return (
            f"{method.capitalize()} image splicing analysis found no evidence that "
            f"the image was assembled from multiple sources ({conf_text})."
        )

    @staticmethod
    def _humanize_ai_detection(meta: dict, verdict: str, conf: float) -> str:
        prob = meta.get("diffusion_probability", conf)
        conf_text = FindingHumanizer._confidence_text(conf)

        if verdict == "POSITIVE" or meta.get("is_ai_generated") or meta.get("diffusion_detected"):
            return (
                f"AI-generation analysis detected artifacts consistent with synthetic image "
                f"generation ({prob:.0%} probability). This indicates the image may have been "
                f"created by artificial intelligence rather than captured by a camera. "
                f"Confidence: {conf_text}."
            )
        return (
            f"AI-generation analysis found no significant artifacts associated with "
            f"synthetic image generation ({conf_text})."
        )

    @staticmethod
    def _humanize_hash(meta: dict, verdict: str, conf: float) -> str:
        hash_matched = meta.get("hash_matches") is True or meta.get("hash_match") is True
        if hash_matched or verdict in ("NEGATIVE", "CLEAN"):
            return (
                "Cryptographic hash verification confirmed the file has not been altered "
                "since initial upload. The file's digital fingerprint matches the original."
            )
        return (
            "WARNING: Cryptographic hash verification failed. The file's digital fingerprint "
            "does not match the original, indicating the file has been modified."
        )

    @staticmethod
    def _humanize_copy_move(meta: dict, verdict: str, conf: float) -> str:
        conf_text = FindingHumanizer._confidence_text(conf)
        if verdict == "POSITIVE" or meta.get("copy_move_detected"):
            matches = meta.get("matched_pairs", meta.get("num_matches", 0))
            return (
                f"Copy-move analysis detected {matches} region(s) where content was duplicated "
                f"within the image ({conf_text}). This suggests portions of the image were cloned "
                f"to hide or replicate objects."
            )
        return (
            f"Copy-move analysis found no evidence of cloned or duplicated regions "
            f"within the image ({conf_text})."
        )

    @staticmethod
    def _humanize_frequency(meta: dict, verdict: str, conf: float) -> str:
        conf_text = FindingHumanizer._confidence_text(conf)
        if verdict == "POSITIVE" or meta.get("gan_artifact_detected") or meta.get("anomaly_detected"):
            return (
                f"Frequency-domain analysis detected unusual patterns in the image's "
                f"spectral content that are consistent with AI-generated or GAN-produced "
                f"imagery ({conf_text})."
            )
        return (
            f"Frequency-domain analysis found the image's spectral patterns to be "
            f"consistent with natural photographic content ({conf_text})."
        )

    @staticmethod
    def _humanize_font(meta: dict, verdict: str, conf: float) -> str:
        score = meta.get("font_consistency_score")
        regions = meta.get("num_anomaly_regions", 0)
        if verdict == "POSITIVE" or regions > 0:
            return (
                f"Font consistency analysis identified {regions} text region(s) with "
                f"rendering anomalies (consistency score: {score}). These may indicate "
                f"altered or inserted text in the screenshot."
            )
        return (
            f"Font rendering appears consistent throughout the screenshot "
            f"(consistency score: {score})."
        )

    @staticmethod
    def _humanize_ui_overlay(meta: dict, verdict: str, conf: float) -> str:
        regions = meta.get("num_suspicious_regions", 0)
        if verdict == "POSITIVE" or regions > 0:
            return (
                f"UI overlay analysis found {regions} suspicious banner or notification "
                f"region(s) that may have been digitally inserted into the screenshot."
            )
        return (
            "UI overlay analysis found no suspicious inserted interface elements "
            "in the screenshot."
        )

    @staticmethod
    def _humanize_scene_incongruence(meta: dict, verdict: str, conf: float) -> str:
        score = float(meta.get("incongruence_score") or 0.0)
        anomalies = meta.get("contextual_anomalies") or meta.get("anomalies") or []
        count = len(anomalies) if isinstance(anomalies, list) else int(meta.get("anomaly_count") or 0)
        conf_text = FindingHumanizer._confidence_text(conf)
        if verdict == "POSITIVE" or meta.get("scene_incongruent") or count:
            return (
                f"Scene incongruence analysis found {count or 1} contextual mismatch "
                f"signal(s) with incongruence score {score:.3f} ({conf_text}). "
                "This suggests the image may contain pasted, synthetic, or visually inconsistent regions."
            )
        return (
            f"Scene incongruence analysis found no supported contextual mismatch "
            f"signals (score {score:.3f}, {conf_text})."
        )

    @staticmethod
    def _humanize_visual_profile(meta: dict, verdict: str, conf: float) -> str:
        desc = str(meta.get("content_description") or meta.get("contextual_narrative") or "").strip()
        _raw_signals = meta.get("manipulation_signals")
        signals = _raw_signals if isinstance(_raw_signals, list) else []
        if verdict == "POSITIVE" or signals:
            signal_text = "; ".join(str(s) for s in signals[:3]) or "visual manipulation indicators"
            return (
                f"Visual evidence profiling described the content as: {desc or 'submitted image'}. "
                f"It flagged {len(signals) or 1} visual concern(s): {signal_text}."
            )
        return f"Visual evidence profiling described the content as: {desc or 'submitted image'}."

    @staticmethod
    def _humanize_generic(finding: dict) -> str:
        tool = _tool_name(finding)
        verdict = _evidence_verdict_of(finding)
        status = str(finding.get("status") or "").upper()
        reasoning = finding.get("reasoning_summary", "")
        label = tool.replace("_", " ").title()

        if verdict == "POSITIVE":
            return f"{label} analysis detected anomalies: {reasoning}"
        if verdict == "ERROR" or status in ("INCOMPLETE", "TIMEOUT", "FAILED"):
            detail = str(reasoning).strip()
            return (
                f"{label} did not complete{f' ({detail})' if detail else ''} — "
                "this is a coverage gap, not evidence of authenticity."
            )
        if verdict == "NOT_APPLICABLE":
            return f"{label} was not applicable to this evidence and did not run."
        if verdict in ("NEGATIVE", "CLEAN"):
            return f"{label} found no supported anomaly signal for its specific test."
        return f"{label} ran but produced no determinate signal; the result is inconclusive."

    @staticmethod
    def _confidence_text(conf: float) -> str:
        if conf >= 0.90:
            return "very high confidence"
        elif conf >= 0.75:
            return "high confidence"
        elif conf >= 0.60:
            return "moderate confidence"
        elif conf >= 0.40:
            return "low confidence"
        else:
            return "very low confidence"
