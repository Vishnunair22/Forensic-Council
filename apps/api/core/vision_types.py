from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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
        verdict = self._authenticity_verdict.upper()
        manipulation_detected = verdict in {
            "SUSPICIOUS",
            "LIKELY_MANIPULATED",
            "TAMPERED",
            "MANIPULATED",
        } or bool(self.manipulation_signals)
        deepfake_detected = verdict == "AI_GENERATED"
        if manipulation_detected or deepfake_detected:
            evidence_verdict = "POSITIVE"
        elif verdict in {"AUTHENTIC", "LIKELY_AUTHENTIC", "CLEAN"} and self.confidence >= 0.5:
            evidence_verdict = "NEGATIVE"
        else:
            evidence_verdict = "INCONCLUSIVE"
        status = (
            "CONFIRMED"
            if self.confidence >= 0.6
            or evidence_verdict == "POSITIVE"
            else "INCONCLUSIVE"
        )

        return {
            "agent_id": agent_id,
            "finding_type": "visual_evidence_profile",
            "confidence_raw": self.confidence,
            "status": status,
            "evidence_verdict": evidence_verdict,
            "verdict": verdict or evidence_verdict,
            "evidence_refs": [],
            "reasoning_summary": self.content_description,
            "summary": self.content_description[:240],
            "analysis_source": self.provider_used,
            "provider_used": self.provider_used,
            "model_used": self.model_used,
            "file_type_assessment": self.file_type_assessment,
            "detected_objects": self.detected_objects,
            "manipulation_signals": self.manipulation_signals,
            "contextual_anomalies": self.contextual_anomalies,
            "extracted_text": self._extracted_text,
            "interface_identification": self._interface_identification,
            "contextual_narrative": self._contextual_narrative,
            "authenticity_verdict": self._authenticity_verdict,
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
                "contextual_anomalies": self.contextual_anomalies,
                "extracted_text": self._extracted_text,
                "interface_identification": self._interface_identification,
                "contextual_narrative": self._contextual_narrative,
                "authenticity_verdict": self._authenticity_verdict,
                "metadata_visual_consistency": self._metadata_visual_consistency,
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
