"""
Severity Tier Assignment
=========================

Shared logic for assigning INFO/LOW/MEDIUM/HIGH/CRITICAL severity tiers
to forensic findings. Used by both the Arbiter and the Investigation routes
to ensure consistent severity classification across the system.
"""

from __future__ import annotations

from typing import Any

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


def _get_confidence(f: Any) -> float:
    """Extract confidence score from a finding."""
    if hasattr(f, "confidence_raw"):
        return float(getattr(f, "confidence_raw", 0.0) or 0.0)
    elif isinstance(f, dict):
        return float(f.get("confidence_raw") or 0.0)
    return 0.0


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
    """True if the tool failed (not court-defensible or status INCOMPLETE)."""
    if is_na:
        return False
    # Only return true if the tool failed to produce any usable forensic signal.
    # Degraded results (court_defensible=False) are still usable signals.
    return str(meta.get("status", "")).upper() == "INCOMPLETE" or "error" in meta


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
    if meta.get("hash_matches") is True:
        return "INFO"
    if evidence_verdict == "ERROR" or failed or status_str == "INCOMPLETE":
        return "LOW"
    if evidence_verdict == "POSITIVE":
        return "CRITICAL" if conf >= 0.75 else "HIGH"

    has_manip = (
        meta.get("manipulation_detected") is True
        or meta.get("deepfake_detected") is True
        or meta.get("splicing_detected") is True
        or meta.get("copy_move_detected") is True
        or meta.get("mismatch_detected") is True
        or meta.get("gan_artifact_detected") is True
        or meta.get("stego_suspected") is True
        or "INCONSISTENT" in str(meta.get("prnu_verdict", "")).upper()
    )
    has_anomaly = (
        meta.get("anomaly_detected") is True
        or meta.get("inconsistency_detected") is True
        or meta.get("is_anomalous") is True
        or str(meta.get("verdict", "")).upper() in ("TAMPERED", "SUSPICIOUS", "MANIPULATED")
    )

    if has_manip:
        return "CRITICAL" if conf >= 0.75 else "HIGH"
    if has_anomaly:
        return "MEDIUM"
    return "LOW"


_SEVERITY_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}


def compute_agent_verdict(findings: list[Any]) -> tuple[str, float, str]:
    """Compute a per-agent verdict + confidence from its findings, severity-aware.

    Replaces the previous crude rule (1 POSITIVE → SUSPICIOUS, 2 → MANIPULATED,
    hardcoded 0.8/0.9 confidence) which ignored severity tiers and counted
    grounded-to-LOW / not-applicable signals as real alerts.

    Rules:
      - NOT_APPLICABLE / ERROR / failed findings never move the verdict.
      - Only POSITIVE findings at MEDIUM+ severity count as alert signals;
        HIGH/CRITICAL count as strong signals. This means a camera-physics
        tool that was grounded to LOW (or returned NOT_APPLICABLE) on a
        screenshot does not inflate the verdict.
      - Confidence is graduated by signal strength and tool coverage, not
        hardcoded.

    Returns (verdict, confidence, reason) where verdict is one of
    AUTHENTIC / INCONCLUSIVE / SUSPICIOUS / MANIPULATED.
    """
    completed = 0
    failed = 0
    alert_signals = 0          # POSITIVE, MEDIUM+
    strong_signals = 0         # POSITIVE, HIGH/CRITICAL

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
        if verdict != "POSITIVE":
            continue

        # Prefer a pre-computed grounded severity_tier; fall back to deriving one.
        sev = ""
        if isinstance(f, dict):
            sev = str(f.get("severity_tier") or meta.get("severity_tier") or meta.get("severity") or "")
        if not sev:
            sev = assign_severity_tier(f)
        rank = _SEVERITY_RANK.get(str(sev).upper(), 1)
        if rank >= 3:
            strong_signals += 1
            alert_signals += 1
        elif rank >= 2:
            alert_signals += 1

    if strong_signals >= 2:
        verdict, conf = "MANIPULATED", 0.85
    elif strong_signals == 1:
        verdict, conf = "SUSPICIOUS", 0.72
    elif alert_signals >= 1:
        # Only medium-strength signals — genuinely ambiguous, not a manipulation call.
        verdict, conf = "INCONCLUSIVE", 0.6
    elif completed == 0:
        # No usable tool output — cannot assert authenticity.
        verdict, conf = "INCONCLUSIVE", 0.4
    else:
        # Clean: confidence scales modestly with coverage breadth, capped.
        verdict, conf = "AUTHENTIC", min(0.92, 0.74 + 0.03 * completed)

    reason = (
        f"{completed} tool(s) completed"
        + (f", {strong_signals} strong + {alert_signals - strong_signals} moderate signal(s)" if alert_signals else ", no alert signals")
        + (f", {failed} failed" if failed else "")
        + "."
    )
    return verdict, round(conf, 2), reason
