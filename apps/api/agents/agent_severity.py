"""
Forensic Agent Severity & Verdict Mapping
=========================================

Standardizes the severity assessment across diverse forensic agents.
"""

from enum import StrEnum


class SeverityTier(StrEnum):
    INFORMATIONAL = "INFORMATIONAL"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


def assign_severity_tier(confidence: float, verdict: str) -> SeverityTier:
    """
    Assign a severity tier based on agent confidence and verdict.
    This ensures that high-confidence suspicious findings are escalated
    while low-confidence or informational signals are kept at lower tiers.
    """
    v = verdict.upper()

    if v in ("CLEAN", "NATURAL", "AUTHENTIC"):
        return SeverityTier.INFORMATIONAL

    if confidence >= 0.85:
        if v in ("SUSPICIOUS", "MANIPULATED", "AI_GENERATED"):
            return SeverityTier.CRITICAL
        return SeverityTier.HIGH

    if confidence >= 0.60:
        if v in ("SUSPICIOUS", "MANIPULATED", "AI_GENERATED"):
            return SeverityTier.HIGH
        return SeverityTier.MEDIUM

    if confidence >= 0.30:
        return SeverityTier.LOW

    return SeverityTier.INFORMATIONAL


def assign_severity_for_finding(f: Any) -> SeverityTier:
    """
    Wrapper to assign a severity tier from a finding dictionary or object.
    """
    from typing import Any
    if isinstance(f, dict):
        confidence = float(f.get("confidence_raw") or f.get("confidence") or 0.0)
        verdict = str(f.get("evidence_verdict") or f.get("verdict") or "CLEAN")
    else:
        confidence = float(getattr(f, "confidence_raw", 0.0) or getattr(f, "confidence", 0.0) or 0.0)
        verdict = str(getattr(f, "evidence_verdict", "CLEAN") or getattr(f, "verdict", "CLEAN"))
    return assign_severity_tier(confidence, verdict)

