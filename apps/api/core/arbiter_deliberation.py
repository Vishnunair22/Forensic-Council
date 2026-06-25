from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from core.calibration import is_system_uncalibrated
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
    # P0.5 — explicit "could not be verified" entries, one per failed/gated-off
    # CRITICAL tool. Lost coverage is named, never silently scored as "no anomaly".
    unverified_domains: list[str] = Field(default_factory=list)

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
            try:
                findings.append(dict(f or {}))
            except (TypeError, ValueError):
                logger.warning("Skipping unconvertible finding", type=type(f).__name__)

    deliberated: list[DeliberatedFinding] = []

    # Track metrics for verdict rules
    completed_tools = set(tool_coverage.get("completed_tools", []))
    failed_tools = set(tool_coverage.get("failed_tools", []))

    positive_integrity_tools: list[str] = []
    positive_integrity_findings: list[dict] = []

    provenance_anomalies: list[str] = []
    content_risks: list[str] = []

    # Define critical/important tools — MODALITY-AWARE. Image-only forensic tools
    # (ELA, frequency, diffusion, object detection) never run for audio/video/
    # document evidence, so scoring those modalities against the image set made
    # their coverage appear <0.4 and forced a spurious INCONCLUSIVE_LIMITED_COVERAGE
    # verdict + depressed confidence even when every applicable agent was clean.
    _mt = (mime_type or "").lower()
    if _mt.startswith("audio/"):
        critical_tools = {"file_hash_verify", "audio_gen_signature"}
        important_tools = {
            "audio_gen_signature", "voice_clone_detect", "anti_spoofing_detect",
            "neural_prosody", "voice_clone_deep_ensemble", "anti_spoofing_deep_ensemble",
            "speaker_diarize",
        }
    elif _mt.startswith("video/"):
        critical_tools = {"file_hash_verify", "av_file_identity"}
        important_tools = {
            "frame_consistency_analysis", "optical_flow_analysis",
            "interframe_forgery_detector", "compression_artifact_analysis",
            "rolling_shutter_validation", "video_metadata", "mediainfo_profile",
        }
    elif _mt == "application/pdf" or _mt.startswith("text/") or "document" in _mt:
        critical_tools = {"file_hash_verify", "file_structure_analysis"}
        important_tools = {
            "file_structure_analysis", "hex_signature_scan", "provenance_chain_verify",
            "metadata_anomaly_score", "timestamp_analysis",
            "ai_text_detector",
        }
    else:  # image/* and default
        critical_tools = {"file_structure_analysis", "exif_extract", "ela_full_image", "neural_ela"}
        important_tools = {
            "ela_full_image", "neural_ela", "frequency_domain_analysis",
            "diffusion_artifact_detector", "ai_generation_detector", "object_detection",
            "screenshot_layout_forensics", "exif_extract", "file_structure_analysis"
        }

    # P1.10 — modality gating. On a screenshot, the pixel-integrity detectors
    # (ELA, splicing, copy-move) fire on UI chrome, text anti-aliasing, and the
    # lossless re-encode rather than tampering — they are FP-prone and must not
    # drive the verdict for this content class. Their findings are still recorded
    # and shown; they are only barred from escalating the manipulation verdict.
    # P0.9 — the exclusion list is shared with compute_agent_verdict via
    # core.severity.SCREENSHOT_FP_PRONE_TOOLS (single source of truth, no drift).
    from core.severity import SCREENSHOT_FP_PRONE_TOOLS

    _is_screenshot = bool(
        visual_context is not None
        and "screenshot" in str(getattr(visual_context, "file_type_assessment", "")).lower()
    )
    _SCREENSHOT_FP_PRONE = SCREENSHOT_FP_PRONE_TOOLS

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

        _screenshot_discounted = _is_screenshot and tool_name in _SCREENSHOT_FP_PRONE
        if _screenshot_discounted and verdict == "POSITIVE":
            df.limitation_notes.append(
                "Discounted for screenshot: pixel-integrity detectors are false-positive-prone "
                "on screen captures and do not drive the verdict."
            )

        if report_safe:
            if verdict == "POSITIVE" and not grounded_down and not _screenshot_discounted:
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

    # Check custody hash mismatch — includes legacy tool name aliases
    _HASH_MISMATCH_TOOLS = {"file_hash_verify", "hash_verify", "custody_check"}
    hash_mismatches = [f for f in findings if f.get("metadata", {}).get("tool_name") in _HASH_MISMATCH_TOOLS and f.get("evidence_verdict") == "POSITIVE"]

    # Determine verdict
    if hash_mismatches:
        final_verdict = "LIKELY_MANIPULATED"
    elif len(set(positive_integrity_tools)) >= 2:
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

    # P0.5 — a failed (or gated-off / never-run) CRITICAL tool is LOST COVERAGE,
    # never "no anomaly": each one becomes an explicit unverified-domain entry.
    # (A gated-off critical tool also depresses important_tool_completion_rate
    # below, so effective coverage genuinely shrinks; tool absence never counts
    # toward clean confirmations anywhere in this function.)
    failed_critical_tools = sorted(critical_tools.intersection(failed_tools))
    gated_critical_tools = sorted(critical_tools - completed_tools - failed_tools)
    unverified_domains: list[str] = [
        f"Critical tool '{t}' failed — its domain could not be verified."
        for t in failed_critical_tools
    ] + [
        f"Critical tool '{t}' did not run (gated off or unavailable) — "
        "its domain could not be verified."
        for t in gated_critical_tools
    ]

    # P0.5 — INCONCLUSIVE_LIMITED_COVERAGE triggers when EITHER important-tool
    # coverage is <40% OR at least two critical tools failed, OR one critical tool
    # failed while coverage is below 80% — a single dead critical detector must
    # not leave a confident "clean" verdict standing on partial evidence, but
    # a single failure in an otherwise well-covered analysis is not enough.
    _has_strong_signal = bool(hash_mismatches) or any(
        (f.get("confidence_raw") or (f.get("metadata") or {}).get("confidence") or 0)
        >= strong_corroborator_bar
        and (f.get("metadata") or {}).get("court_defensible", True)
        for f in positive_integrity_findings
    )
    _coverage_low = total_important > 0 and (completed_important / total_important) < 0.4
    _coverage_moderate = total_important > 0 and (completed_important / total_important) < 0.8
    if (
        failed_important >= 2
        or _coverage_low
        or len(failed_critical_tools) >= 2
        or (failed_critical_tools and _coverage_moderate and not _has_strong_signal)
    ) and not hash_mismatches:
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
    # Graduated: start at 1.0, deduct 0.10 per conflict (floored at 0.0).
    # A single minor cross-agent disagreement no longer destroys the entire
    # agreement term — only a barrage of contradictions drives it to zero.
    cross_agent_agreement_score = max(0.0, 1.0 - 0.10 * len(conflicts))

    # 3. high_weight_evidence_score
    # If all critical/high tools that completed are clean/negative, or support the final verdict
    high_weight_completed = [df for df in deliberated if df.report_safe and df.evidence_weight in (EvidenceWeight.CRITICAL, EvidenceWeight.HIGH)]
    if high_weight_completed:
        supporting_high_weight = [df for df in high_weight_completed if df.supports_final_verdict]
        high_weight_evidence_score = len(supporting_high_weight) / len(high_weight_completed)
    else:
        high_weight_evidence_score = 1.0

    # 3b. evidence_strength_score — mean per-tool confidence of the report-safe
    # findings that SUPPORT the verdict. This is the term that makes the score VARY
    # per file: a strongly/uniformly clean read scores higher than a weakly clean
    # one, instead of every clean fully-covered file collapsing to the same value
    # once the coverage/agreement/high-weight rates all saturate to 1.0. Confidence
    # travels on the raw findings (DeliberatedFinding carries no score), so map back
    # by finding_id.
    _raw_conf_by_id: dict[str, float] = {}
    for _f in findings_list:
        _fid = str((_f.get("finding_id") if isinstance(_f, dict) else getattr(_f, "finding_id", "")) or "")
        if not _fid:
            continue
        _c = float(
            (_f.get("confidence_raw") if isinstance(_f, dict) else getattr(_f, "confidence_raw", 0.0))
            or (_f.get("raw_confidence_score") if isinstance(_f, dict) else getattr(_f, "raw_confidence_score", 0.0))
            or (_f.get("metadata", {}) if isinstance(_f, dict) else {}).get("confidence")
            or 0.0
        )
        if _c > 0:
            _raw_conf_by_id[_fid] = _c
    _supporting_confs = [
        _raw_conf_by_id[df.finding_id]
        for df in deliberated
        if df.report_safe and df.supports_final_verdict and df.finding_id in _raw_conf_by_id
    ]
    evidence_strength_score = (
        sum(_supporting_confs) / len(_supporting_confs) if _supporting_confs else 0.0
    )

    # 4. visual_context_support_score
    # Honesty fix: credit the visual context ONLY when it AGREES with the final
    # verdict's direction. Corroboration = both read clean OR both flag a problem;
    # disagreement (and ambiguous/uncorroborated verdicts) earns no visual-support
    # credit. Remote (court-defensible) Gemini is weighted more than the screening-
    # tier local ensemble.
    _vc_coeff = 0.10 if vc_remote else 0.05
    if visual_context is None:
        visual_context_support_score = 0.0
    else:
        _verdict_clean = final_verdict == "NO_REPORTABLE_MANIPULATION_DETECTED"
        _vc_flags_issue = bool(has_vc_integrity_issue)
        # Agreement: both clean (no issue flagged) or both dirty (issue flagged).
        # Disagreement or ambiguous verdicts earn no credit.
        visual_context_support_score = 1.0 if (_verdict_clean == (not _vc_flags_issue)) else 0.0

    # 5. critical_tool_failure_rate
    failed_critical = critical_tools.intersection(failed_tools)
    critical_tool_failure_rate = (len(failed_critical) / len(critical_tools)) if critical_tools else 0.0

    # 6. unresolved_conflict_score
    unresolved_conflict_score = 1.0 if conflicts else 0.0

    # 7. weak_single_signal_penalty
    # If only 1 integrity signal and it is low weight
    weak_completed_positives = [df for df in deliberated if df.report_safe and df.evidence_verdict == "POSITIVE" and df.evidence_weight == EvidenceWeight.LOW]
    weak_single_signal_penalty = 1.0 if len(weak_completed_positives) == 1 and len(positive_integrity_tools) == 1 else 0.0

    # Confidence must be HONEST, not pinned at the ceiling (audit C1). The previous
    # weights summed to ~1.05 for any clean, fully-covered, Gemini-corroborated file,
    # so every clean verdict clipped to a fabricated 0.98 "certainty" — the same flat
    # 98% on every file, which an UNCALIBRATED system cannot justify. Rescaled so a
    # perfect-coverage clean result tops out near 0.85 and the score genuinely varies
    # with tool coverage, cross-agent agreement, and visual corroboration below that.
    # (WS-5 calibration training will replace these hand-set weights with benchmarked
    # ones; until then the report labels confidence "indicative (uncalibrated)".)
    # Constant terms rebalanced DOWN to leave headroom for evidence_strength_score —
    # the file-dependent term — so a clean, fully-covered result no longer pins to a
    # flat value the moment coverage/agreement/high-weight all hit 1.0. With strength
    # at 0.15 weight, a strongly-clean file approaches the uncalibrated 0.85 ceiling
    # while a weakly-clean one settles ~0.81, genuinely varying with the evidence.
    # Clamp penalty coefficients so the formula can never go negative before the
    # floor.  Worst case: base 0.30 + all positives at 0 − all penalties at max.
    # Penalties are capped at 0.30 total (0.10 + 0.10 + 0.10) so the raw sum
    # stays ≥ 0.0 and the floor is never the only thing preventing an absurd value.
    _penalty_total = (
        0.20 * critical_tool_failure_rate
        + 0.15 * unresolved_conflict_score
        + 0.10 * weak_single_signal_penalty
    )
    _max_penalty = 0.30  # sum of the three penalty coefficients
    if _penalty_total > _max_penalty:
        _penalty_scale = _max_penalty / _penalty_total if _penalty_total > 0 else 1.0
        critical_tool_failure_rate *= _penalty_scale
        unresolved_conflict_score *= _penalty_scale
        weak_single_signal_penalty *= _penalty_scale

    raw_conf = (
        0.15
        + 0.12 * important_tool_completion_rate
        + 0.10 * cross_agent_agreement_score
        + 0.10 * high_weight_evidence_score
        + _vc_coeff * visual_context_support_score
        + 0.40 * evidence_strength_score
        - 0.20 * critical_tool_failure_rate
        - 0.15 * unresolved_conflict_score
        - 0.10 * weak_single_signal_penalty
    )
    # Hard ceiling stays defensive; an uncalibrated system is additionally capped so
    # it can never present >~0.85 certainty regardless of the term sum.
    _ceiling = 0.90 if is_system_uncalibrated() else 0.98
    # Floor of 0.10 — a fully-failed investigation still carries minimal
    # non-zero confidence so downstream consumers can distinguish "we checked
    # and found nothing" (0.0) from "we could not check" (0.10).
    final_confidence = max(0.10, min(_ceiling, raw_conf))

    # P0.2 — PDF/document verdicts reached on the metadata-only path (no content
    # or rendered-page analysis) cannot earn high confidence: a forged visible
    # payload with clean container metadata would pass undetected. Cap confidence
    # to reflect the limited evidentiary basis. Hard provenance evidence (custody
    # hash mismatch) is exempt — it stands on its own regardless of content reach.
    _is_document = _mt == "application/pdf" or _mt.startswith("text/") or "document" in _mt
    _content_analyzed = bool(
        visual_context is not None and getattr(visual_context, "external_llm_used", False)
    )
    if _is_document and not _content_analyzed and not hash_mismatches:
        final_confidence = min(final_confidence, 0.70)

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

    # Partition the deliberated findings so that NOTHING report-safe is dropped:
    # strongest = CRITICAL/HIGH, supporting = everything else report-safe
    # (MEDIUM, LOW, CONTEXT_ONLY), excluded = not report-safe. Previously
    # `supporting` only captured MEDIUM, so a report-safe LOW-weight finding
    # (jpeg_ghost_detect / copy_move_detect) landed in no bucket and vanished
    # from the report even though it still counted toward the verdict — the
    # arbiter could assert a concern without ever surfacing the finding.
    strongest_findings = [df for df in deliberated if df.evidence_weight in (EvidenceWeight.CRITICAL, EvidenceWeight.HIGH) and df.report_safe]
    supporting_findings = [
        df for df in deliberated
        if df.report_safe
        and df.evidence_weight not in (EvidenceWeight.CRITICAL, EvidenceWeight.HIGH, EvidenceWeight.EXCLUDED)
    ]
    excluded_findings = [df for df in deliberated if not df.report_safe or df.evidence_weight == EvidenceWeight.EXCLUDED]

    # P0.3 — a failed critical tool is LOST COVERAGE, not absence of evidence: its
    # domain could not be verified. Name those domains explicitly, and cap an
    # otherwise-clean verdict so a silently-dead critical detector cannot leave the
    # report MORE confident than a fully-covered run.
    unresolved_limitations = []
    for f in failed_tools:
        if f in critical_tools:
            unresolved_limitations.append(
                f"Critical tool '{f}' did not complete — its domain could not be verified."
            )
        else:
            unresolved_limitations.append(f"Tool failed: {f}")
    if failed_critical and final_verdict == "NO_REPORTABLE_MANIPULATION_DETECTED":
        final_confidence = min(final_confidence, 0.75)

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
        tool_failures_affecting_report=list(failed_tools),
        unverified_domains=unverified_domains,
    )
