from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from core.react_loop import AgentFinding
from core.structured_logging import get_logger

logger = get_logger(__name__)

class EvidenceWeight(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    CONTEXT_ONLY = "context_only"
    EXCLUDED = "excluded"

class DeliberatedFinding(BaseModel):
    finding_id: str
    agent_id: str
    tool_name: str
    finding_statement: str
    signal_category: str
    evidence_verdict: str
    report_safe: bool
    evidence_weight: EvidenceWeight
    supports_final_verdict: bool
    conflicts_with: list[str] = Field(default_factory=list)
    limitation_notes: list[str] = Field(default_factory=list)

class ArbiterDeliberationResult(BaseModel):
    final_verdict: str
    final_confidence: float
    confidence_reason: str
    strongest_findings: list[DeliberatedFinding] = Field(default_factory=list)
    supporting_findings: list[DeliberatedFinding] = Field(default_factory=list)
    excluded_findings: list[DeliberatedFinding] = Field(default_factory=list)
    cross_agent_agreements: list[str] = Field(default_factory=list)
    cross_agent_conflicts: list[str] = Field(default_factory=list)
    unresolved_limitations: list[str] = Field(default_factory=list)
    tool_failures_affecting_report: list[str] = Field(default_factory=list)

def deliberate_findings(
    findings_list: list[AgentFinding] | list[dict],
    visual_context: Any | None,
    tool_coverage: dict[str, Any],
    mime_type: str = "",
) -> ArbiterDeliberationResult:
    """Deliberates agent findings, resolves conflicts, and determines the final verdict and confidence score.

    ``mime_type`` selects file-type-specific verdict thresholds (lossless formats
    use higher bars to resist false positives from compression/ELA artifacts).
    """
    from core.forensic_policy import ForensicPolicy

    thresholds = ForensicPolicy.get_verdict_thresholds(mime_type)
    # Single court-defensible positive escalates to LIKELY_MANIPULATED only above
    # this confidence. The mime thresholds only ever RAISE the bar (lossless →
    # 0.85); clamped at the historical 0.8 floor so non-lossless behaviour is
    # unchanged and no file type becomes more trigger-happy.
    single_signal_bar = max(0.8, float(thresholds.get("manipulated", 0.8)))
    # A corroborating integrity signal must clear this confidence to count as one
    # of the "2 strong agreeing signals" that defeat the corroboration gate.
    strong_corroborator_bar = 0.75 if mime_type in (
        "image/png", "image/webp", "image/bmp", "image/gif"
    ) else 0.70
    # Convert findings to clean dicts
    findings: list[dict] = []
    for f in findings_list:
        if isinstance(f, dict):
            findings.append(f)
        elif hasattr(f, "model_dump"):
            findings.append(f.model_dump(mode="json"))
        else:
            findings.append(dict(f or {}))

    deliberated: list[DeliberatedFinding] = []

    # Track metrics for verdict rules
    completed_tools = set(tool_coverage.get("completed_tools", []))
    failed_tools = set(tool_coverage.get("failed_tools", []))

    positive_integrity_tools: list[str] = []
    positive_integrity_findings: list[dict] = []

    provenance_anomalies: list[str] = []
    content_risks: list[str] = []

    # Define critical/important tools
    critical_tools = {"file_structure_analysis", "exif_extract", "ela_full_image", "neural_ela"}
    important_tools = {
        "ela_full_image", "neural_ela", "frequency_domain_analysis",
        "diffusion_artifact_detector", "object_detection",
        "screenshot_layout_forensics", "exif_extract", "file_structure_analysis"
    }

    # First pass: Deliberate each finding
    for f in findings:
        fid = str(f.get("finding_id", ""))
        aid = str(f.get("agent_id", ""))
        meta = f.get("metadata") or {}
        tool_name = str(meta.get("tool_name") or f.get("finding_type") or "")
        verdict = str(f.get("evidence_verdict") or "INCONCLUSIVE").upper()

        # Decide report safe
        report_safe = True
        if verdict == "ERROR" or f.get("status") in ("TIMEOUT", "INCOMPLETE"):
            report_safe = False
        if not meta.get("court_defensible", True):
            report_safe = False

        # Determine weight
        weight = EvidenceWeight.MEDIUM
        if tool_name in critical_tools:
            weight = EvidenceWeight.CRITICAL
        elif tool_name in important_tools:
            weight = EvidenceWeight.HIGH
        elif tool_name in ("hash_verify", "custody_check"):
            weight = EvidenceWeight.CRITICAL
        elif tool_name in ("jpeg_ghost_detect", "copy_move_detect"):
            weight = EvidenceWeight.LOW

        if not report_safe:
            weight = EvidenceWeight.EXCLUDED

        # Signal categorization
        category = "integrity"
        if tool_name in ("object_detection", "vector_contraband_search"):
            category = "content_risk"
        elif tool_name in ("exif_extract", "timestamp_analysis", "gps_timezone_validate", "file_structure_analysis"):
            category = "provenance"

        statement = str(f.get("reasoning_summary") or meta.get("summary") or "")

        df = DeliberatedFinding(
            finding_id=fid,
            agent_id=aid,
            tool_name=tool_name,
            finding_statement=statement,
            signal_category=category,
            evidence_verdict=verdict,
            report_safe=report_safe,
            evidence_weight=weight,
            supports_final_verdict=False
        )

        # Honour visual-context grounding: a POSITIVE that grounding capped to
        # LOW/INFO severity (camera-physics noise on a non-camera-origin image, or
        # a corroboration-downgrade) is expected noise, not a manipulation signal —
        # it must not drive the verdict, mirroring compute_agent_verdict.
        grounded_sev = str(meta.get("severity_tier") or f.get("severity_tier") or "").upper()
        grounded_down = grounded_sev in ("LOW", "INFO")

        if report_safe:
            if verdict == "POSITIVE" and not grounded_down:
                if category == "integrity":
                    positive_integrity_tools.append(tool_name)
                    positive_integrity_findings.append(f)
                elif category == "provenance":
                    provenance_anomalies.append(tool_name)
                elif category == "content_risk":
                    # Check if it contains danger words
                    content_risks.append(tool_name)

        deliberated.append(df)

    # Detect conflicts and agreements
    agreements: list[str] = []
    conflicts: list[str] = []

    # Conflict: positive integrity signal from ELA but clean visual context or vice versa
    has_vc_integrity_issue = False
    if visual_context:
        # Check integrity assessment
        vis_integrity = getattr(visual_context, "image_integrity_context", None)
        if vis_integrity:
            ass = getattr(vis_integrity, "integrity_assessment", "cannot_determine")
            if ass in ("likely_manipulated", "ai_generated_suspect"):
                has_vc_integrity_issue = True

    # ── Gemini as a bounded weighted voter ───────────────────────────────────
    # The REMOTE (court-defensible) visual model is a strong weighted participant:
    # a high-confidence manipulation/AI read can RAISE the verdict on its own
    # (vision models lead on AI-generation and obvious composites), and a clean
    # read can LOWER an uncorroborated tool signal (the corroboration gate below).
    # It is bounded — it cannot override 2+ strong court-defensible deterministic
    # signals — and the local-ensemble fallback stays screening-tier (never gets
    # this elevated weight).
    vc_remote = bool(
        visual_context is not None
        and getattr(visual_context, "external_llm_used", False)
        and getattr(visual_context, "source", "") == "llm_assisted"
    )
    vc_conf = float(getattr(visual_context, "confidence", 0.0) or 0.0) if visual_context else 0.0
    vc_strong_vote = vc_remote and has_vc_integrity_issue and vc_conf >= 0.7

    if positive_integrity_tools and not has_vc_integrity_issue and visual_context:
        msg = f"Conflict: Tool(s) {', '.join(positive_integrity_tools)} flag anomaly, but visual integrity assessment is clean/inconclusive."
        conflicts.append(msg)
        for df in deliberated:
            if df.tool_name in positive_integrity_tools:
                df.conflicts_with.append("visual_context")
                df.limitation_notes.append("Tool anomaly uncorroborated by visual context.")
    elif positive_integrity_tools and has_vc_integrity_issue:
        agreements.append("Agreement: Local integrity tools and visual context both flag potential manipulation.")

    # Rule-based final verdict determination
    final_verdict = "NO_REPORTABLE_MANIPULATION_DETECTED"

    # Check custody hash mismatch
    hash_mismatches = [f for f in findings if f.get("metadata", {}).get("tool_name") == "file_hash_verify" and f.get("evidence_verdict") == "POSITIVE"]

    # Determine verdict
    if hash_mismatches:
        final_verdict = "LIKELY_MANIPULATED"
    elif len(positive_integrity_tools) >= 2:
        final_verdict = "LIKELY_MANIPULATED"
    elif len(positive_integrity_tools) == 1:
        # Check if high confidence or supported by visual context
        finding = positive_integrity_findings[0]
        conf = finding.get("confidence_raw") or finding.get("metadata", {}).get("confidence") or 0.0
        if conf >= single_signal_bar or has_vc_integrity_issue:
            final_verdict = "LIKELY_MANIPULATED"
        else:
            final_verdict = "SUSPICIOUS_INTEGRITY_SIGNALS"
    elif has_vc_integrity_issue:
        # Bounded weighted voter: a high-confidence remote-Gemini manipulation/AI
        # read carries real weight on its own, so it can raise the verdict to
        # LIKELY_MANIPULATED even with no positive integrity tool. A low-confidence
        # or local-ensemble read only raises suspicion.
        if vc_strong_vote:
            final_verdict = "LIKELY_MANIPULATED"
            agreements.append(
                f"Visual model (remote) independently assessed manipulation/AI generation "
                f"at {int(round(vc_conf * 100))}% confidence."
            )
        else:
            final_verdict = "SUSPICIOUS_INTEGRITY_SIGNALS"
    elif provenance_anomalies:
        final_verdict = "PROVENANCE_CONCERN"
    elif content_risks:
        final_verdict = "CONTENT_RISK_OBSERVED"

    # ── Corroboration gate ──
    # A manipulation/suspicion verdict driven by integrity tool signals must be
    # corroborated by the holistic visual model (Gemini) OR by 2+ strong,
    # court-defensible agreeing signals. A lone screening/single-model positive
    # that Gemini does NOT see is, in practice, a false positive on a processed or
    # recompressed real photo (e.g. WhatsApp/phone-pipeline artifacts) — hold the
    # verdict inconclusive rather than asserting manipulation. Hard provenance
    # evidence (hash mismatch) is exempt; it is not overridden by visual assessment.
    if final_verdict in ("LIKELY_MANIPULATED", "SUSPICIOUS_INTEGRITY_SIGNALS") and not hash_mismatches:
        gemini_available_and_clean = visual_context is not None and not has_vc_integrity_issue
        strong_corroborating = sum(
            1
            for f in positive_integrity_findings
            if (f.get("confidence_raw") or (f.get("metadata") or {}).get("confidence") or 0) >= strong_corroborator_bar
            and (f.get("metadata") or {}).get("court_defensible", True)
        )
        if gemini_available_and_clean and strong_corroborating < 2:
            final_verdict = "INCONCLUSIVE_UNCORROBORATED_SIGNAL"
            conflicts.append(
                "Integrity signal(s) uncorroborated by the visual model — consistent with "
                "processing/recompression artifacts rather than manipulation; verdict held inconclusive."
            )

    # Coverage calculation
    total_important = len(important_tools)
    completed_important = len(important_tools.intersection(completed_tools))
    failed_important = len(important_tools.intersection(failed_tools))

    # If key tools failed, it is inconclusive
    if failed_important >= 2 or (total_important > 0 and (completed_important / total_important) < 0.4):
        final_verdict = "INCONCLUSIVE_LIMITED_COVERAGE"

    # Set supports_final_verdict on findings
    for df in deliberated:
        if final_verdict == "LIKELY_MANIPULATED" and df.evidence_verdict == "POSITIVE" and df.signal_category == "integrity":
            df.supports_final_verdict = True
        elif final_verdict == "SUSPICIOUS_INTEGRITY_SIGNALS" and df.evidence_verdict == "POSITIVE":
            df.supports_final_verdict = True
        elif final_verdict == "PROVENANCE_CONCERN" and df.signal_category == "provenance" and df.evidence_verdict == "POSITIVE":
            df.supports_final_verdict = True
        elif final_verdict == "CONTENT_RISK_OBSERVED" and df.signal_category == "content_risk" and df.evidence_verdict == "POSITIVE":
            df.supports_final_verdict = True
        elif final_verdict == "NO_REPORTABLE_MANIPULATION_DETECTED" and df.evidence_verdict == "NEGATIVE":
            df.supports_final_verdict = True

    # ── Confidence Scoring Formula ──
    # base confidence = 0.45
    # + 0.20 * important_tool_completion_rate
    # + 0.15 * cross_agent_agreement_score
    # + 0.15 * high_weight_evidence_score
    # + 0.05 * visual_context_support_score
    # - 0.20 * critical_tool_failure_rate
    # - 0.15 * unresolved_conflict_score
    # - 0.10 * weak_single_signal_penalty

    # 1. important_tool_completion_rate
    important_tool_completion_rate = (completed_important / total_important) if total_important > 0 else 1.0

    # 2. cross_agent_agreement_score
    # If no conflicts, score is 1.0. If conflicts, score is 0.0.
    cross_agent_agreement_score = 1.0 if not conflicts else 0.0

    # 3. high_weight_evidence_score
    # If all critical/high tools that completed are clean/negative, or support the final verdict
    high_weight_completed = [df for df in deliberated if df.report_safe and df.evidence_weight in (EvidenceWeight.CRITICAL, EvidenceWeight.HIGH)]
    if high_weight_completed:
        supporting_high_weight = [df for df in high_weight_completed if df.supports_final_verdict]
        high_weight_evidence_score = len(supporting_high_weight) / len(high_weight_completed)
    else:
        high_weight_evidence_score = 1.0

    # 4. visual_context_support_score
    # Remote (court-defensible) Gemini is weighted more than the screening-tier
    # local ensemble — the bounded weighted voter contributes more confidence.
    visual_context_support_score = 1.0 if visual_context else 0.0
    _vc_coeff = 0.10 if vc_remote else 0.05

    # 5. critical_tool_failure_rate
    failed_critical = critical_tools.intersection(failed_tools)
    critical_tool_failure_rate = (len(failed_critical) / len(critical_tools)) if critical_tools else 0.0

    # 6. unresolved_conflict_score
    unresolved_conflict_score = 1.0 if conflicts else 0.0

    # 7. weak_single_signal_penalty
    # If only 1 integrity signal and it is low weight
    weak_completed_positives = [df for df in deliberated if df.report_safe and df.evidence_verdict == "POSITIVE" and df.evidence_weight == EvidenceWeight.LOW]
    weak_single_signal_penalty = 1.0 if len(weak_completed_positives) == 1 and len(positive_integrity_tools) == 1 else 0.0

    raw_conf = (
        0.45
        + 0.20 * important_tool_completion_rate
        + 0.15 * cross_agent_agreement_score
        + 0.15 * high_weight_evidence_score
        + _vc_coeff * visual_context_support_score
        - 0.20 * critical_tool_failure_rate
        - 0.15 * unresolved_conflict_score
        - 0.10 * weak_single_signal_penalty
    )
    final_confidence = max(0.0, min(0.98, raw_conf))

    # Formulate confidence reason
    reasons = []
    if important_tool_completion_rate > 0.8:
        reasons.append("High tool coverage")
    if cross_agent_agreement_score > 0.8:
        reasons.append("consistent agent findings")
    if visual_context:
        reasons.append("corroborative visual context")
    if failed_critical:
        reasons.append(f"reduced by {len(failed_critical)} critical tool failures")
    if conflicts:
        reasons.append("penalized for cross-agent contradictions")

    confidence_reason = "Computed based on: " + ", ".join(reasons) if reasons else "Based on completed tools coverage."

    strongest_findings = [df for df in deliberated if df.evidence_weight in (EvidenceWeight.CRITICAL, EvidenceWeight.HIGH) and df.report_safe]
    supporting_findings = [df for df in deliberated if df.evidence_weight == EvidenceWeight.MEDIUM and df.report_safe]
    excluded_findings = [df for df in deliberated if not df.report_safe or df.evidence_weight == EvidenceWeight.EXCLUDED]

    unresolved_limitations = []
    for f in failed_tools:
        unresolved_limitations.append(f"Tool failed: {f}")

    return ArbiterDeliberationResult(
        final_verdict=final_verdict,
        final_confidence=round(final_confidence, 3),
        confidence_reason=confidence_reason,
        strongest_findings=strongest_findings,
        supporting_findings=supporting_findings,
        excluded_findings=excluded_findings,
        cross_agent_agreements=agreements,
        cross_agent_conflicts=conflicts,
        unresolved_limitations=unresolved_limitations,
        tool_failures_affecting_report=list(failed_tools)
    )
