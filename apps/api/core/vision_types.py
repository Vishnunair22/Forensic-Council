from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.manipulation_signal_taxonomy import partition_manipulation_signals
from core.tool_names import TOOL_VISUAL_PROFILE


@dataclass
class VisualEvidenceFinding:
    analysis_type: str
    model_used: str
    content_description: str
    provider_used: str = "local_visual_ensemble"
    manipulation_signals: list[str] = field(default_factory=list)
    detected_objects: list[str] = field(default_factory=list)
    contextual_anomalies: list[str] = field(default_factory=list)
    file_type_assessment: str = ""
    confidence: float = 0.0
    court_defensible: bool = True
    caveat: str = ""
    raw_response: str = ""
    latency_ms: float = 0.0
    error: str | None = None
    from_cache: bool = False
    _extracted_text: list[str] = field(default_factory=list)
    _interface_identification: str = ""
    _contextual_narrative: str = ""
    _authenticity_verdict: str = ""
    _metadata_visual_consistency: str = ""
    _forensic_routing: dict[str, Any] = field(default_factory=dict)
    _forensic_specifics: str = ""
    # Structured provenance clues visible IN the image (timestamps, device/platform,
    # app, location). Populated by the local ensemble so Agent5's metadata
    # provenance section is filled even on the no-Gemini path.
    _visible_metadata_clues: dict[str, Any] = field(default_factory=dict)
    provider_attempts: list[dict] = field(default_factory=list)
    fallback_applied: bool = False
    fallback_reason: str = ""
    tool_coverage: dict[str, bool] = field(default_factory=dict)
    degradation_flags: list[str] = field(default_factory=list)

    def to_finding_dict(
        self,
        agent_id: str,
        *,
        tool_name: str = TOOL_VISUAL_PROFILE,
    ) -> dict[str, Any]:
        # Separate the three axes a "manipulation_signals" list conflates:
        # benign processing/editing (background removal, crop, re-save) must NOT
        # be read as deceptive tampering. See core.manipulation_signal_taxonomy.
        buckets = partition_manipulation_signals(self.manipulation_signals)
        tampering_signals = buckets["tampering"]
        processing_observations = buckets["processing"]
        ai_generation_signals = buckets["ai_generation"]
        raw_verdict = self._authenticity_verdict.upper()
        # Both providers return their OWN holistic authenticity verdict and have
        # already weighed their observations:
        #   • Gemini decides authenticity holistically;
        #   • the local ensemble's _assess_authenticity applies corroboration-aware
        #     calibration (a single uncorroborated screening signal — e.g. one ELA
        #     hotspot on a heavily recompressed JPEG — yields INCONCLUSIVE, never
        #     SUSPICIOUS; see vision_local_ensemble).
        # Trust that verdict. Re-deriving a louder verdict from the individual raw
        # signal buckets double-counts one uncorroborated artifact into a false
        # POSITIVE — the gin.jpeg false-positive class.
        is_gemini = (self.provider_used or "").lower().startswith("gemini")
        holistic_manip_verdicts = {"SUSPICIOUS", "LIKELY_MANIPULATED", "TAMPERED", "MANIPULATED"}
        clean_verdicts = {"AUTHENTIC", "LIKELY_AUTHENTIC", "CLEAN"}

        deepfake_detected = raw_verdict == "AI_GENERATED" or bool(ai_generation_signals)

        if not is_gemini:
            # Local ensemble: its holistic verdict is authoritative. A weak AI or
            # artifact signal that the ensemble itself declined to escalate stays
            # INCONCLUSIVE here (surfaced for review, not alarmed).
            if raw_verdict in holistic_manip_verdicts:
                verdict = raw_verdict
                manipulation_detected = True
                evidence_verdict = "POSITIVE"
            elif raw_verdict in clean_verdicts and self.confidence >= 0.5:
                verdict = raw_verdict
                manipulation_detected = False
                evidence_verdict = "NEGATIVE"
            else:
                verdict = raw_verdict or "INCONCLUSIVE"
                manipulation_detected = False
                evidence_verdict = "INCONCLUSIVE"
        else:
            # Gemini holistic provider: trust its verdict, but a genuine tampering
            # observation still escalates even when it called the image authentic,
            # and a benign editing observation never overrides an AUTHENTIC call.
            if raw_verdict in holistic_manip_verdicts:
                verdict = raw_verdict
                manipulation_detected = True
            elif tampering_signals:
                verdict = "SUSPICIOUS"
                manipulation_detected = True
            elif deepfake_detected:
                verdict = "AI_GENERATED"
                manipulation_detected = False
            else:
                verdict = raw_verdict
                manipulation_detected = False

            if manipulation_detected or deepfake_detected:
                evidence_verdict = "POSITIVE"
            elif verdict in clean_verdicts and self.confidence >= 0.5:
                evidence_verdict = "NEGATIVE"
            else:
                evidence_verdict = "INCONCLUSIVE"

        # "edited" is a separate, descriptive axis from "tampered": a file can be
        # edited (cropped, background removed) yet authentic / not deceptive.
        edited = bool(processing_observations or tampering_signals)
        status = (
            "CONFIRMED"
            if self.confidence >= 0.6
            or evidence_verdict == "POSITIVE"
            else "INCONCLUSIVE"
        )

        return {
            "agent_id": agent_id,
            "finding_type": "visual_evidence_profile",
            "content_description": self.content_description,
            "confidence_raw": self.confidence,
            "status": status,
            "evidence_verdict": evidence_verdict,
            "verdict": verdict or evidence_verdict,
            "evidence_refs": [],
            "reasoning_summary": self.content_description[:200],
            "summary": self.content_description[:240],
            "analysis_source": self.provider_used,
            "provider_used": self.provider_used,
            "model_used": self.model_used,
            "file_type_assessment": self.file_type_assessment,
            "detected_objects": self.detected_objects,
            "manipulation_signals": self.manipulation_signals,
            "tampering_signals": tampering_signals,
            "processing_observations": processing_observations,
            "ai_generation_signals": ai_generation_signals,
            "edited": edited,
            "contextual_anomalies": self.contextual_anomalies,
            "extracted_text": self._extracted_text,
            "interface_identification": self._interface_identification,
            "contextual_narrative": self._contextual_narrative,
            "authenticity_verdict": verdict or self._authenticity_verdict,
            "raw_authenticity_verdict": raw_verdict,
            "metadata_visual_consistency": self._metadata_visual_consistency,
            "forensic_routing": self._forensic_routing,
            "forensic_specifics": self._forensic_specifics,
            "manipulation_detected": manipulation_detected,
            "deepfake_detected": deepfake_detected,
            "fallback_applied": self.fallback_applied,
            "fallback_reason": self.fallback_reason,
            "degradation_flags": self.degradation_flags,
            "metadata": {
                "tool_name": tool_name,
                "content_description": self.content_description,
                "evidence_verdict": evidence_verdict,
                "verdict": verdict or evidence_verdict,
                "analysis_source": self.provider_used,
                "provider_used": self.provider_used,
                "model_used": self.model_used,
                "external_ai_used": self.provider_used != "local_visual_ensemble",
                "analysis_type": self.analysis_type,
                "file_type_assessment": self.file_type_assessment,
                "detected_objects": self.detected_objects,
                "manipulation_signals": self.manipulation_signals,
                "tampering_signals": tampering_signals,
                "processing_observations": processing_observations,
                "ai_generation_signals": ai_generation_signals,
                "edited": edited,
                "contextual_anomalies": self.contextual_anomalies,
                "extracted_text": self._extracted_text,
                "interface_identification": self._interface_identification,
                "contextual_narrative": self._contextual_narrative,
                "authenticity_verdict": verdict or self._authenticity_verdict,
                "raw_authenticity_verdict": raw_verdict,
                "metadata_visual_consistency": self._metadata_visual_consistency,
                "visible_metadata_clues": self._visible_metadata_clues,
                "forensic_routing": self._forensic_routing,
                "forensic_specifics": self._forensic_specifics,
                "latency_ms": round(self.latency_ms, 1),
                "manipulation_detected": manipulation_detected,
                "deepfake_detected": deepfake_detected,
                "provider_attempts": self.provider_attempts,
                "fallback_applied": self.fallback_applied,
                "fallback_reason": self.fallback_reason,
                "tool_coverage": self.tool_coverage,
                "degradation_flags": self.degradation_flags,
            },
            "court_defensible": self.court_defensible,
            "caveat": self.caveat,
            "stub_result": False,
        }
