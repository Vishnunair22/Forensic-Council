"""
Severity Tier Assignment
========================

Shared logic for assigning INFO/LOW/MEDIUM/HIGH/CRITICAL severity tiers
to forensic findings. Used by both the Arbiter and the Investigation routes
to ensure consistent severity classification across the system.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Tools that are NEVER an "integrity manipulation" positive: provenance/metadata,
# content/object, hard-evidence (hash), and descriptive/non-manipulation tools.
# The corroboration grounding (arbiter overall verdict AND the live per-agent card
# in pipeline_phases) downgrades an uncorroborated INTEGRITY positive to
# INCONCLUSIVE when the holistic visual read is clean; these tools are excluded so
# provenance facts and hash mismatches are never silently cleared. Single source of
# truth shared by the arbiter and the live-stream gate so the two cannot drift.
NON_INTEGRITY_TOOLS: frozenset[str] = frozenset({
    # Provenance / metadata
    "exif_extract", "timestamp_analysis", "gps_timezone_validate",
    "file_structure_analysis", "file_hash_verify", "metadata_anomaly_score",
    "provenance_chain_verify", "hex_signature_scan", "compression_risk_audit",
    # Legacy aliases for file_hash_verify
    "hash_verify", "custody_check",
    # Content / context
    "object_detection", "vector_contraband_search", "scene_incongruence",
    # Descriptive / non-manipulation tools — never a manipulation claim
    "visual_evidence_profile", "analyze_image_content",
    "extract_text_from_image", "read_shared_image_context",
    "scale_validation",
})

_HOLISTIC_FLAGGED_VERDICTS = frozenset({
    "SUSPICIOUS", "AI_GENERATED", "MANIPULATED", "LIKELY_MANIPULATED", "SUSPECT", "TAMPERED",
})
_HOLISTIC_FLAGGED_ASSESSMENTS = frozenset({
    "suspicious", "likely_manipulated", "ai_generated_suspect",
})


def holistic_read_flags_manipulation(
    authenticity_verdict: str = "", integrity_assessment: str = ""
) -> bool:
    """True when the holistic visual read itself flagged the evidence.

    The corroboration-grounding gate (arbiter overall verdict, live per-agent card,
    and the agent's own verdict) only clears a lone uncorroborated integrity/AI
    positive when the holistic read is CLEAN. A SUSPICIOUS read (e.g. the ensemble's
    strong-AI determination on a synthetic image) CORROBORATES the tool positives —
    it must NOT be treated as clean, or genuine AI/manipulation gets cleared down to
    SUSPICIOUS/AUTHENTIC. Single source of truth so all three gates agree.
    """
    return (
        str(authenticity_verdict or "").upper() in _HOLISTIC_FLAGGED_VERDICTS
        or str(integrity_assessment or "").lower() in _HOLISTIC_FLAGGED_ASSESSMENTS
    )


# Screening-tier heuristics that co-fire on JPEG recompression — correlated, not
# independent, so they do not corroborate one another or the ML detectors. Excluded
# from the strong-corroborator COUNT (but still downgraded with the rest of the
# cluster when uncorroborated). Mirrors the arbiter's inline `_screening` set.
_SCREENING_TOOLS = frozenset({
    "neural_copy_move", "copy_move_detector", "neural_splicing",
    "splicing_detector", "neural_ela", "error_level_analysis",
    "frequency_domain_analysis",
})


def should_clear_uncorroborated_integrity(
    findings: list[dict[str, Any]], holistic_clean: bool
) -> bool:
    """Decide whether a cluster of integrity positives is UNCORROBORATED and should
    be held inconclusive — the single source of truth for the corroboration-grounding
    gate so the agent self-verdict, the live per-agent card, and the signed report
    (arbiter) all reach the same conclusion (no AUTHENTIC↔SUSPICIOUS drift between
    the evidence page and the result page).

    ``findings`` is a normalized list of dicts with keys: ``tool_name``,
    ``evidence_verdict``, ``court_defensible`` (bool), ``confidence`` (float),
    ``severity_tier`` (str). Mirrors the arbiter's inline grounding EXACTLY:

      - holistic visual read must be clean (a SUSPICIOUS/AI read corroborates), and
      - no hard provenance signal (file-hash mismatch), and
      - fewer than 2 STRONG court-defensible NON-screening positives, and
      - no authoritative TruFor (neural_splicing) localization — a real trained
        splicing model sees pixel forgeries the holistic read cannot, so it is
        authoritative on its own and is never cleared.
    """
    if not holistic_clean:
        return False
    if any(
        f.get("tool_name") == "file_hash_verify"
        and str(f.get("evidence_verdict", "")).upper() == "POSITIVE"
        for f in findings
    ):
        return False
    strong = sum(
        1 for f in findings
        if str(f.get("evidence_verdict", "")).upper() == "POSITIVE"
        and bool(f.get("court_defensible"))
        and str(f.get("severity_tier", "")).upper() in ("HIGH", "CRITICAL")
        and str(f.get("tool_name") or "") not in _SCREENING_TOOLS
    )
    if strong >= 2:
        return False
    trufor = any(
        str(f.get("tool_name") or "") == "neural_splicing"
        and str(f.get("evidence_verdict", "")).upper() == "POSITIVE"
        and bool(f.get("court_defensible"))
        and _safe_float(f.get("confidence")) >= 0.5
        for f in findings
    )
    return not trufor


def uncorroborated_screening_text(tool_name: str | None) -> str:
    """Canonical non-asserting narrative for an integrity-screening POSITIVE that
    the clean holistic read does not corroborate (held inconclusive as a benign
    processing artifact). Single source of truth so the live per-agent card and
    the signed report phrase the downgrade IDENTICALLY."""
    tool_disp = str(tool_name or "a screening check").replace("_", " ")
    return (
        f"A weak screening signal from {tool_disp} was not corroborated by the "
        "holistic visual model; held inconclusive — consistent with a benign "
        "processing/recompression artifact rather than manipulation."
    )


# P0.9 / P1.10 — screenshot gating, shared by the arbiter deliberation AND
# compute_agent_verdict (single source of truth so agent-phase and final verdicts
# cannot drift). On screen captures, pixel-integrity and compression-artifact
# detectors (ELA, splicing, copy-move, frequency/compression probes) fire on UI
# chrome, text anti-aliasing and the lossless re-encode rather than tampering —
# their POSITIVE findings are context-only for this content class: still recorded
# and shown, but barred from counting as alert/strong manipulation signals.
SCREENSHOT_FP_PRONE_TOOLS: frozenset[str] = frozenset({
    "ela_full_image", "neural_ela", "jpeg_ghost_detect",
    "neural_splicing", "splicing_detect", "copy_move_detect", "neural_copy_move",
    # compression-artifact probes co-fire on the screenshot re-encode
    "frequency_domain_analysis", "compression_artifact_analysis",
    # noise/PRNU tools unreliable on screenshots (no real camera sensor noise)
    "noiseprint_cluster", "noise_fingerprint", "prnu_sensor_verification",
    # adversarial/ROI tools tuned for natural images, not screenshots
    "adversarial_robustness_check", "roi_extract",
})


# Not-applicable metadata flags that indicate a tool doesn't apply to this file type
_NA_FLAGS = (
    "ela_not_applicable",
    "ghost_not_applicable",
    "noise_fingerprint_not_applicable",
    "prnu_not_applicable",
    "gan_not_applicable",
)


def _get_metadata(f: Any) -> dict[str, Any]:
    """Extract metadata dict from a finding (AgentFinding model or dict)."""
    if hasattr(f, "metadata"):
        return f.metadata or {}
    elif isinstance(f, dict):
        return f.get("metadata") or {}
    return {}


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Convert val to float, returning default on any error."""
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _get_confidence(f: Any) -> float | None:
    """Extract confidence score from a finding. Returns None if not found."""
    if hasattr(f, "confidence_raw"):
        v = getattr(f, "confidence_raw", None)
        return _safe_float(v) if v is not None else None
    elif isinstance(f, dict):
        v = f.get("confidence_raw")
        return _safe_float(v) if v is not None else None
    return None


def _get_status(f: Any) -> str:
    """Extract status string from a finding."""
    if hasattr(f, "status"):
        return str(getattr(f, "status", "")).upper()
    elif isinstance(f, dict):
        return str(f.get("status", "")).upper()
    return ""


def is_not_applicable(meta: dict[str, Any]) -> bool:
    """True if any not-applicable flag is set, or verdict/prnu_verdict is NOT_APPLICABLE."""
    if any(meta.get(flag) for flag in _NA_FLAGS):
        return True
    if str(meta.get("verdict", "")).upper() == "NOT_APPLICABLE":
        return True
    if str(meta.get("prnu_verdict", "")).upper() == "NOT_APPLICABLE":
        return True
    return False


def is_failed(meta: dict[str, Any], is_na: bool) -> bool:
    """True if the tool failed (not court-defensible or status INCOMPLETE/TIMEOUT/FAILED)."""
    if is_na:
        return False
    # Only return true if the tool failed to produce any usable forensic signal.
    # Degraded results (court_defensible=False) are still usable signals.
    status = str(meta.get("status", "")).upper()
    return status in ("INCOMPLETE", "TIMEOUT", "FAILED", "ERROR") or "error" in meta


def assign_severity_tier(f: Any) -> str:
    """
    Assign INFO/LOW/MEDIUM/HIGH/CRITICAL to a finding based on its metadata.

    Rules:
      - NOT_APPLICABLE tools → INFO
      - Hash match confirmed → INFO
      - Failed/INCOMPLETE → LOW
      - Direct manipulation signals (manipulation_detected, deepfake_detected,
        splicing_detected, copy_move_detected, mismatch_detected,
        stego_suspected, gan_artifact_detected, INCONSISTENT verdict) →
        CRITICAL if confidence >= 0.75, else HIGH
      - Anomaly signals (anomaly_detected, inconsistency_detected,
        TAMPERED/SUSPICIOUS/MANIPULATED verdict) → MEDIUM
      - Everything else → LOW
    """
    meta = _get_metadata(f)
    conf = _get_confidence(f)
    status_str = _get_status(f)
    evidence_verdict = ""
    if hasattr(f, "evidence_verdict"):
        evidence_verdict = str(getattr(f, "evidence_verdict", "")).upper()
    elif isinstance(f, dict):
        evidence_verdict = str(f.get("evidence_verdict", "")).upper()

    na = is_not_applicable(meta)
    failed = is_failed(meta, na)

    if evidence_verdict == "NOT_APPLICABLE" or na:
        return "INFO"
    if meta.get("not_applicable") or meta.get("skipped"):
        return "INFO"
    if meta.get("hash_matches"):
        return "INFO"
    if evidence_verdict == "ERROR" or failed or status_str == "INCOMPLETE":
        return "LOW"
    if evidence_verdict == "POSITIVE":
        return "CRITICAL" if conf >= 0.75 else "HIGH"
    if evidence_verdict == "NEGATIVE":
        return "LOW"

    has_manip = (
        meta.get("manipulation_detected")
        or meta.get("deepfake_detected")
        or meta.get("splicing_detected")
        or meta.get("copy_move_detected")
        or meta.get("mismatch_detected")
        or meta.get("gan_artifact_detected")
        or meta.get("stego_suspected")
        or "INCONSISTENT" in str(meta.get("prnu_verdict", "")).upper()
    )
    has_anomaly = (
        meta.get("anomaly_detected")
        or meta.get("inconsistency_detected")
        or meta.get("is_anomalous")
        or str(meta.get("verdict", "")).upper() in ("TAMPERED", "SUSPICIOUS", "MANIPULATED")
    )

    if has_manip:
        return "CRITICAL" if conf >= 0.75 else "HIGH"
    if has_anomaly:
        return "MEDIUM"
    return "LOW"


_SEVERITY_RANK: dict[str, int] = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}

# Minimum confidence for a high-severity POSITIVE finding to count as a STRONG
# (manipulation-confirming) signal. Below this it is treated as a medium alert.
_STRONG_SIGNAL_CONF_FLOOR = 0.6

# Visual context (Gemini) weight constants.
# A court-defensible remote-vision MANIPULATED/AI_GENERATED read is the strongest
# holistic signal in the visual domain. It alone does not call MANIPULATED (which
# requires corroboration with at least one tool strong signal), but when combined
# with a tool strong signal the convergence adds a confidence premium because the
# two independent pipelines (pixel-level tools + holistic vision) agree.
#
# In purely tool-only cases (Agent5 provenance, hash mismatch) the deterministic
# findings are authoritative on their own and get the standard weight.
_GEMINI_COURT_STRONG_WEIGHT = 1    # Gemini court-defensible → 1 strong signal vote
_GEMINI_SCREEN_ALERT_WEIGHT = 1    # Screening / local-ensemble → 1 alert signal vote

# Confidence boosts applied when independent pipelines converge.
_CONV_VISUAL_TOOL_CONF_BOOST = 0.06  # Gemini court-defensible + ≥1 tool strong agree → +6 pp
_GEMINI_SOLO_CONF_BOOST = 0.03       # Gemini court-defensible strong verdict alone → +3 pp on SUSPICIOUS


def compute_agent_verdict(
    findings: list[Any],
    visual_signal: dict[str, Any] | None = None,
    is_deep: bool = False,
    screenshot_context: bool | None = None,
) -> tuple[str, float, str]:
    """Compute a per-agent verdict + confidence from its findings, severity-aware
    and grounded in the shared visual context.

    Replaces the previous crude rule (1 POSITIVE → SUSPICIOUS, 2 → MANIPULATED,
    hardcoded 0.8/0.9 confidence) which ignored severity tiers and counted
    grounded-to-LOW / not-applicable signals as real alerts.

    Rules:
      - NOT_APPLICABLE / ERROR / failed findings never move the verdict.
      - Only POSITIVE findings at MEDIUM+ severity count as alert signals;
        HIGH/CRITICAL count as strong signals. This means a camera-physics
        tool that was grounded to LOW (or returned NOT_APPLICABLE) on a
        screenshot does not inflate the verdict.
      - The holistic visual read is folded in as a grounding signal so the
        verdict can never contradict it (the prior tool-only computation let
        the badge say AUTHENTIC while the Visual Context said "AI-generated").
        A court-defensible (remote vision) AI_GENERATED / LIKELY_MANIPULATED
        read counts as a STRONG signal; SUSPICIOUS or court-defensible scene/
        metadata anomalies count as a MEDIUM alert. A local-ensemble read is
        screening-tier — it can raise ambiguity but never asserts manipulation
        on its own.
      - Confidence is graduated by signal strength and tool coverage, not
        hardcoded.

    ``visual_signal`` (per agent, built by the arbiter) carries:
      ``verdict``           – holistic authenticity read (Agent1) or "" otherwise
      ``court_defensible``  – True when from the remote vision model, not local
      ``anomalies``         – scene inconsistencies (Agent3) / metadata
                              contradictions (Agent5) / AI-gen signals (Agent1)

    ``screenshot_context`` (P0.9, optional/backward-compatible): when truthy, the
    evidence is a screen capture and POSITIVE findings from the FP-prone
    pixel-integrity / compression-artifact tools (SCREENSHOT_FP_PRONE_TOOLS,
    mirroring the arbiter's screenshot exclusion list) are treated as
    context-only — they never count as alert or strong signals — so the
    agent-phase verdict matches the arbiter's screenshot gating.

    Returns (verdict, confidence, reason) where verdict is one of
    AUTHENTIC / INCONCLUSIVE / SUSPICIOUS / MANIPULATED.
    """
    completed = 0
    clean_confirmations = 0    # NEGATIVE verdicts — tools that affirmatively confirmed clean
    clean_conf_sum = 0.0       # Σ per-tool clean confidence — its MEAN drives the clean score
    clean_conf_n = 0           # count of clean findings carrying a usable confidence
    failed = 0
    alert_signals = 0          # POSITIVE, MEDIUM+
    strong_signals = 0         # POSITIVE, HIGH/CRITICAL
    alert_conf_max = 0.0       # strongest alert-signal confidence (graduates INCONCLUSIVE)
    strong_conf_sum = 0.0      # Σ per-signal confidence for strong signals (graduates MANIPULATED)
    strong_conf_n = 0          # count of strong signals with usable confidence

    for f in findings or []:
        meta = _get_metadata(f)
        verdict = ""
        if hasattr(f, "evidence_verdict"):
            verdict = str(getattr(f, "evidence_verdict", "")).upper()
        elif isinstance(f, dict):
            verdict = str(f.get("evidence_verdict", "")).upper()
        status = _get_status(f)

        if verdict == "NOT_APPLICABLE" or status == "NOT_APPLICABLE" or is_not_applicable(meta):
            continue
        if verdict == "ERROR" or status in ("ERROR", "TIMEOUT", "INCOMPLETE"):
            failed += 1
            continue

        completed += 1
        if verdict == "NEGATIVE":
            clean_confirmations += 1
            # Capture HOW STRONGLY this tool confirmed clean (its measurement-derived
            # confidence), so the agent's clean score reflects evidence strength, not
            # just the count of clean tools.
            _cc = _get_confidence(f)
            if _cc is None:
                _cc = float(
                    meta.get("confidence")
                    or (f.get("raw_confidence_score") if isinstance(f, dict) else 0.0)
                    or 0.0
                )
            if _cc > 0:
                # Platt-scaled raw_confidence_score represents P(anomaly), not
                # "confidence in clean" — the sigmoid was fitted for POSITIVE
                # findings so it systematically crushes NEGATIVE confidence
                # (e.g. confidence_raw=0.85 → raw_confidence_score=0.284 for
                # Agent1). Invert: confidence in clean = max(conf, 1-conf).
                # Deterministic tools (raw_confidence_score == confidence_raw)
                # are unchanged since both sides are already ≥ 0.50.
                _cc = max(_cc, 1.0 - _cc)
                clean_conf_sum += _cc
                clean_conf_n += 1
        if verdict != "POSITIVE":
            continue

        # P0.9 — screenshot gating (mirrors the arbiter's exclusion list so the
        # agent-phase verdict agrees with the final): on a screen capture, a
        # POSITIVE from an FP-prone pixel-integrity / compression-artifact tool is
        # context-only — recorded as a completed check but never an alert/strong
        # signal driving the verdict.
        if screenshot_context:
            if isinstance(f, dict):
                _tool = str(meta.get("tool_name") or f.get("finding_type") or "")
            else:
                _tool = str(meta.get("tool_name") or getattr(f, "finding_type", "") or "")
            if _tool in SCREENSHOT_FP_PRONE_TOOLS:
                continue

        # Prefer a pre-computed grounded severity_tier; fall back to deriving one.
        sev = ""
        if isinstance(f, dict):
            sev = str(f.get("severity_tier") or meta.get("severity_tier") or meta.get("severity") or "")
        if not sev:
            sev = assign_severity_tier(f)
        rank = _SEVERITY_RANK.get(str(sev).upper(), 1)
        # A POSITIVE finding only counts as a STRONG signal when it is BOTH
        # high-severity AND backed by sufficient confidence. A high-severity
        # tier with weak confidence (e.g. a 0.50 hex/metadata hit) is a genuine
        # but soft signal — it should register as a medium alert, not help push
        # the agent to MANIPULATED. This stops a cluster of low-confidence
        # positives from over-calling manipulation.
        conf_f = _get_confidence(f)
        if conf_f is None:
            conf_f = float(
                meta.get("confidence")
                or (f.get("raw_confidence_score") if isinstance(f, dict) else 0.0)
                or 0.0
            )
        if rank >= 3 and conf_f >= _STRONG_SIGNAL_CONF_FLOOR:
            strong_signals += 1
            alert_signals += 1
            alert_conf_max = max(alert_conf_max, conf_f)
            strong_conf_sum += conf_f
            strong_conf_n += 1
        elif rank >= 2:
            alert_signals += 1
            alert_conf_max = max(alert_conf_max, conf_f)

    # ── Fold in the holistic visual read as a grounding signal ──────────────
    tool_strong = strong_signals  # tool-only counts, for honest reason phrasing
    tool_alert = alert_signals    # tool-only alert count, before visual folding
    vs = visual_signal or {}
    v_verdict = str(vs.get("verdict") or "").upper()
    v_court = bool(vs.get("court_defensible"))
    v_conf = float(vs.get("confidence") or 0.0)
    v_anomalies = [a for a in (vs.get("anomalies") or []) if a]
    visual_contributed = False
    gemini_strong_vote = False  # True when court-defensible Gemini asserts manipulation

    # In deep analysis, the holistic visual read carries more weight: it has
    # already been cross-checked against Phase-1 tool findings, so a court-
    # defensible manipulation verdict is treated as 2 strong signal votes instead
    # of 1. This lets a confirmed Gemini read break ties in the deep verdict without
    # requiring a second independent tool strong signal.
    _court_strong_weight = (_GEMINI_COURT_STRONG_WEIGHT + 1) if is_deep else _GEMINI_COURT_STRONG_WEIGHT

    if v_verdict in ("AI_GENERATED", "LIKELY_MANIPULATED", "MANIPULATED"):
        visual_contributed = True
        if v_court:
            gemini_strong_vote = True
            # In deep mode, Gemini with tool corroboration gets extra weight;
            # without any deterministic tool strong signal, treat the extra
            # weight as an alert-only signal so a solo Gemini read cannot push
            # the verdict to MANIPULATED on its word alone.
            if is_deep and tool_strong == 0:
                _effective_weight = _GEMINI_COURT_STRONG_WEIGHT       # 1 strong
                _alert_extra = _GEMINI_COURT_STRONG_WEIGHT + 1        # +1 alert
            else:
                _effective_weight = _court_strong_weight
                _alert_extra = _court_strong_weight
            strong_signals += _effective_weight
            alert_signals += _alert_extra
            # Gemini's confidence contributes to the average strong-signal
            # confidence used to graduate the MANIPULATED verdict floor.
            # When weighted (deep mode), add confidence proportionally so the
            # mean remains correct: weight=N means the signal counts as N entries.
            strong_conf_sum += v_conf * _effective_weight
            strong_conf_n += _effective_weight
        else:
            alert_signals += _GEMINI_SCREEN_ALERT_WEIGHT
    elif v_verdict == "SUSPICIOUS":
        visual_contributed = True
        alert_signals += _GEMINI_SCREEN_ALERT_WEIGHT
    if v_anomalies and v_court:
        visual_contributed = True
        # An uncorroborated holistic ANOMALY (a visual observation no deterministic
        # tool isolated) is screening-tier, not manipulation evidence — e.g. the
        # vision model reading an on-screen clock as a "future date" while every
        # metadata tool confirms the file is consistent (a model temporal-staleness
        # false positive). Only let an anomaly raise an alert when a tool
        # corroborates it; otherwise it is noted (visual_contributed) but must not
        # flip an otherwise-clean agent to INCONCLUSIVE. A court-defensible
        # manipulation VERDICT (handled above) still escalates regardless — this
        # gate applies only to anomaly observations.
        if (tool_alert + tool_strong) >= 1:
            alert_signals += _GEMINI_SCREEN_ALERT_WEIGHT

    # Convergence flag: Gemini court-defensible + at least one deterministic tool
    # strong signal agree — two independent pipelines pointing to the same conclusion
    # is stronger evidence than either alone.
    visual_tool_convergent = gemini_strong_vote and tool_strong >= 1

    # Gemini-clean alignment: Gemini says AUTHENTIC/CLEAN and all tools NEGATIVE →
    # higher confidence in the clean verdict because the holistic read corroborates.
    gemini_clean_vote = v_court and v_verdict in ("AUTHENTIC", "CLEAN", "NO_REPORTABLE_MANIPULATION_DETECTED")

    if strong_signals >= 2:
        verdict = "MANIPULATED"
        # Graduated floor: start at mean strong-signal confidence (bounded
        # 0.70–0.90) so two barely-strong signals (0.65 conf each) produce
        # a lower floor than two high-confidence hits. Convergent pipeline
        # boost applies on top.
        _mean_strong = strong_conf_sum / strong_conf_n if strong_conf_n else 0.85
        _graduated_floor = min(0.90, max(0.70, _mean_strong))
        conf = min(0.94, _graduated_floor + (_CONV_VISUAL_TOOL_CONF_BOOST if visual_tool_convergent else 0.0))
        logger.info(
            "MANIPULATED confidence: strong_signals=%d _mean_strong=%.4f "
            "visual_tool_convergent=%s conf=%.4f",
            strong_signals, _mean_strong, visual_tool_convergent, conf,
        )
    elif strong_signals == 1:
        verdict = "SUSPICIOUS"
        if gemini_strong_vote and tool_strong == 0:
            # Gemini asserts manipulation but no deterministic tool corroborates yet —
            # slight confidence premium over a purely tool-driven suspicious call because
            # court-defensible holistic vision is a strong visual-domain signal.
            conf = round(0.72 + _GEMINI_SOLO_CONF_BOOST, 2)
        else:
            conf = 0.72
        logger.info(
            "SUSPICIOUS confidence: strong_signals=1 gemini_strong_vote=%s "
            "gemini_solo=%s conf=%.4f",
            gemini_strong_vote, gemini_strong_vote and tool_strong == 0, conf,
        )
    elif alert_signals >= 1:
        # Only medium-strength signals — genuinely ambiguous, not a manipulation
        # call. Confidence is graduated by how strong/numerous the ambiguous signals
        # are (bounded to the inconclusive band) rather than a flat placeholder, so
        # two different inconclusive reads don't both render an identical 60%.
        verdict = "INCONCLUSIVE"
        conf = round(min(0.70, 0.50 + 0.18 * alert_conf_max + 0.03 * (alert_signals - 1)), 2)
        logger.info(
            "INCONCLUSIVE (alert_signals): completed=%d alert_signals=%d "
            "alert_conf_max=%.4f conf=%.4f",
            completed, alert_signals, alert_conf_max, conf,
        )
    elif completed == 0:
        # No usable tool output — cannot assert authenticity.
        verdict, conf = "INCONCLUSIVE", 0.4
        logger.info("INCONCLUSIVE (no completed): conf=0.4")
    elif clean_confirmations == 0:
        # Tools ran but NONE affirmatively confirmed clean (every usable result was
        # inconclusive). Asserting AUTHENTIC here would be dishonest — this is
        # genuine ambiguity, not a clean read. Confidence stays in the low band.
        verdict = "INCONCLUSIVE"
        conf = round(min(0.6, 0.45 + 0.03 * completed), 2)
        logger.info(
            "INCONCLUSIVE (no clean_confirmations): completed=%d conf=%.4f",
            completed, conf,
        )
    else:
        # Clean: confidence scales with the number of tools that AFFIRMATIVELY
        # confirmed clean (NEGATIVE verdicts), not with raw completed count — an
        # INCONCLUSIVE "couldn't determine" result or a context-only tool is
        # coverage, not confirmation, and must not inflate confidence in a clean
        # verdict. A small additional bump when Gemini's holistic read also says
        # clean/authentic (two independent pipelines agreeing is meaningful).
        # Confidence reflects HOW STRONGLY the tools confirmed clean (the mean
        # per-tool clean confidence), not just HOW MANY did. Two different clean
        # files with the same tool count but different measurement strength no
        # longer render an identical score. Same clean band/bounds, now genuinely
        # file-dependent: base + a small count bump + the measurement-strength term.
        _mean_clean = (clean_conf_sum / clean_conf_n) if clean_conf_n else 0.65
        conf = min(
            0.95,
            max(
                0.65,
                0.35 + 0.02 * clean_confirmations + 0.55 * _mean_clean
                + (0.04 if gemini_clean_vote else 0.0),
            ),
        )
        verdict = "AUTHENTIC"
        logger.info(
            "AUTHENTIC confidence: completed=%d clean_confirmations=%d "
            "clean_conf_n=%d clean_conf_sum=%.4f _mean_clean=%.4f "
            "gemini_clean_vote=%s conf=%.4f",
            completed, clean_confirmations, clean_conf_n, clean_conf_sum,
            _mean_clean, gemini_clean_vote, conf,
        )

    moderate_signals = alert_signals - strong_signals
    failed_note = f" {failed} check(s) did not complete and are treated as coverage gaps." if failed else ""
    visual_note = ""
    if visual_contributed:
        if v_verdict in ("AI_GENERATED", "LIKELY_MANIPULATED", "MANIPULATED"):
            _read = "AI-generated" if v_verdict == "AI_GENERATED" else v_verdict.replace("_", " ").lower()
            visual_note = (
                f" The holistic visual analysis independently read the evidence as {_read}"
                f"{' (corroborating vision model)' if v_court else ' (screening-tier)'}."
            )
        elif v_verdict == "SUSPICIOUS":
            visual_note = " The holistic visual analysis flagged the evidence as suspicious."
        elif v_anomalies:
            visual_note = (
                f" The visual analysis flagged {len(v_anomalies)} corroborating "
                f"context anomal{'y' if len(v_anomalies) == 1 else 'ies'}."
            )
    if verdict == "MANIPULATED":
        reason = (
            f"{tool_strong} high-severity manipulation signal(s) were confirmed across "
            f"{completed} completed check(s), corroborating a manipulated finding.{failed_note}{visual_note}"
        )
    elif verdict == "SUSPICIOUS":
        if tool_strong >= 1:
            reason = (
                f"One high-severity manipulation signal was confirmed across {completed} completed "
                f"check(s); the evidence is flagged suspicious pending corroboration.{failed_note}{visual_note}"
            )
        else:
            reason = (
                f"No discrete tool isolated a high-severity signal across {completed} completed "
                f"check(s), but the holistic visual read flags the evidence suspicious pending "
                f"corroboration.{failed_note}{visual_note}"
            )
    elif alert_signals >= 1:
        reason = (
            f"{moderate_signals} medium-strength signal(s) across {completed} completed check(s) "
            f"were ambiguous and do not support a definitive manipulation call.{failed_note}{visual_note}"
        )
    elif completed == 0:
        reason = (
            "No usable tool output was available for this agent, so authenticity cannot be "
            f"asserted.{failed_note}"
        )
    else:
        reason = (
            f"All {completed} completed check(s) returned clean results with no manipulation "
            f"signal.{failed_note}"
        )
    return verdict, round(conf, 2), reason
