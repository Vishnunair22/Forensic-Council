"""
Cross-Modal Fusion Layer
========================

Provides structured cross-modal reasoning by creating a joint feature space
from multi-agent findings. This is the architectural bridge between the
"passing notes" inter-agent bus and true cross-modal fusion.

The fusion layer operates in three modes:
1. Contradiction detection — finds disagreements across modalities
2. Correlation analysis — identifies reinforcing signals
3. Joint scoring — computes a fused confidence from multi-modal evidence

This module does NOT require a shared embedding model. Instead, it uses
structured feature extraction and weighted fusion heuristics designed
for forensic evidence analysis. A future version could replace the
heuristic fusion with a learned joint encoder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from core.structured_logging import get_logger

logger = get_logger(__name__)


class Modality(StrEnum):
    """Evidence modalities."""

    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    OBJECT = "OBJECT"
    VIDEO = "VIDEO"
    METADATA = "METADATA"


class CrossModalVerdict(StrEnum):
    """Verdict from cross-modal fusion."""

    CORROBORATED = "CORROBORATED"
    PARTIALLY_CORROBORATED = "PARTIALLY_CORROBORATED"
    CONTRADICTED = "CONTRADICTED"
    INDEPENDENT = "INDEPENDENT"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass
class ModalitySignal:
    """A normalized signal from one modality."""

    modality: Modality
    agent_id: str
    finding_type: str
    confidence: float
    status: str  # CONFIRMED, CONTESTED, INCONCLUSIVE
    manipulation_detected: bool
    key_metrics: dict[str, float] = field(default_factory=dict)
    summary: str = ""
    analysis_phase: str = "initial"  # initial or deep


@dataclass
class FusionResult:
    """Result of cross-modal fusion analysis."""

    verdict: CrossModalVerdict
    fused_confidence: float
    corroborations: list[dict[str, str]]
    contradictions: list[dict[str, str]]
    independent_modalities: list[str]
    fusion_rationale: str


# Weight table for modality pairs when checking for cross-modal agreement.
# Higher weight = more valuable corroboration between those modalities.
_MODALITY_PAIR_WEIGHTS: dict[frozenset, float] = {
    frozenset({Modality.IMAGE, Modality.OBJECT}): 1.2,
    frozenset({Modality.IMAGE, Modality.VIDEO}): 1.3,
    frozenset({Modality.IMAGE, Modality.METADATA}): 1.1,
    frozenset({Modality.AUDIO, Modality.VIDEO}): 1.4,
    frozenset({Modality.OBJECT, Modality.METADATA}): 0.9,
    frozenset({Modality.VIDEO, Modality.METADATA}): 1.0,
    frozenset({Modality.IMAGE, Modality.AUDIO}): 0.7,
    frozenset({Modality.AUDIO, Modality.OBJECT}): 0.6,
    frozenset({Modality.AUDIO, Modality.METADATA}): 0.8,
    frozenset({Modality.OBJECT, Modality.VIDEO}): 1.1,
}

DEFAULT_PAIR_WEIGHT = 0.8


def _extract_signals(findings_by_agent: dict[str, list[dict]]) -> list[ModalitySignal]:
    """
    Extract normalized ModalitySignal objects from per-agent findings.

    Maps agent IDs to modalities and extracts key forensic signals
    (manipulation detection, confidence, status) from each finding.
    """
    _AGENT_MODALITY = {
        "Agent1": Modality.IMAGE,
        "Agent2": Modality.AUDIO,
        "Agent3": Modality.OBJECT,
        "Agent4": Modality.VIDEO,
        "Agent5": Modality.METADATA,
    }

    signals: list[ModalitySignal] = []

    for agent_id, findings in findings_by_agent.items():
        modality = _AGENT_MODALITY.get(agent_id)
        if modality is None:
            continue

        for f in findings:
            if not isinstance(f, dict):
                continue

            status = f.get("status", "CONFIRMED")
            confidence = f.get("confidence_raw", f.get("raw_confidence_score", 0.5))
            finding_type = f.get("finding_type", "unknown")
            summary = f.get("reasoning_summary", "")
            analysis_phase = (f.get("metadata") or {}).get("analysis_phase", "initial")

            # Detect manipulation signal from metadata
            meta = f.get("metadata", {})
            manipulation = False
            if meta:
                manipulation = (
                    meta.get("splicing_detected", False)
                    or meta.get("anomaly_detected", False)
                    or meta.get("inconsistency_detected", False)
                    or meta.get("face_swap_detected", False)
                    or meta.get("spoofing_detected", False)
                    or meta.get("gan_artifact_detected", False)
                    or meta.get("copy_move_detected", False)
                    or meta.get("editing_software_detected", False)
                    or meta.get("adversarial_pattern_detected", False)
                    or meta.get("concern_flag", False)
                    or meta.get("is_anomalous", False)
                    or meta.get("scene_incongruent", False)
                    or meta.get("prosody_anomaly", False)
                    or meta.get("is_reliable") is False
                )

            # Extract numeric metrics for correlation
            key_metrics: dict[str, float] = {}
            for metric_key in (
                "anomaly_score",
                "noise_consistency_score",
                "synthetic_probability",
                "ela_mean",
                "max_anomaly",
                "inconsistency_ratio",
                "splice_count",
                "forgery_score",
                "confidence",
            ):
                val = meta.get(metric_key)
                if isinstance(val, (int, float)):
                    key_metrics[metric_key] = float(val)

            signals.append(
                ModalitySignal(
                    modality=modality,
                    agent_id=agent_id,
                    finding_type=finding_type,
                    confidence=float(confidence) if confidence else 0.5,
                    status=status,
                    manipulation_detected=manipulation,
                    key_metrics=key_metrics,
                    summary=summary[:200] if summary else "",
                    analysis_phase=analysis_phase,
                )
            )

    return signals


def _find_corroboration(sig_a: ModalitySignal, sig_b: ModalitySignal) -> dict[str, str] | None:
    """
    Check if two signals corroborate each other.

    Corroboration requires both signals to be CONFIRMED AND at least one
    must detect manipulation. Two "nothing found" findings from different
    modalities do NOT count as meaningful corroboration — absence of
    evidence is not evidence of absence.
    """
    if sig_a.status != "CONFIRMED" or sig_b.status != "CONFIRMED":
        return None
    if sig_a.manipulation_detected and sig_b.manipulation_detected:
        return {
            "agents": f"{sig_a.agent_id} + {sig_b.agent_id}",
            "modalities": f"{sig_a.modality.value} + {sig_b.modality.value}",
            "direction": "manipulation",
            "detail": f"{sig_a.finding_type} and {sig_b.finding_type} both detect manipulation",
        }
    return None


def _find_contradiction(sig_a: ModalitySignal, sig_b: ModalitySignal) -> dict[str, str] | None:
    """
    Check if two signals contradict each other.

    Contradiction occurs when one detects manipulation and the other
    asserts authenticity, with both at CONFIRMED status.
    """
    if (
        sig_a.manipulation_detected != sig_b.manipulation_detected
        and sig_a.status == "CONFIRMED"
        and sig_b.status == "CONFIRMED"
    ):
        return {
            "agents": f"{sig_a.agent_id} vs {sig_b.agent_id}",
            "modalities": f"{sig_a.modality.value} vs {sig_b.modality.value}",
            "detail": (
                f"{sig_a.finding_type} ({sig_a.agent_id}) detects manipulation "
                f"while {sig_b.finding_type} ({sig_b.agent_id}) indicates authenticity"
            ),
        }
    return None


def fuse(
    findings_by_agent: dict[str, list[dict]],
) -> FusionResult:
    """
    Perform cross-modal fusion analysis on multi-agent findings.

    This is the main entry point for the fusion layer. It extracts signals
    from all agents, then computes:
    1. Corroboration pairs (signals that agree)
    2. Contradiction pairs (signals that disagree)
    3. Fused confidence (weighted average of corroborated signals)

    Args:
        findings_by_agent: Dict mapping agent_id -> list of finding dicts

    Returns:
        FusionResult with verdict, fused confidence, and rationale
    """
    signals = _extract_signals(findings_by_agent)

    if not signals:
        return FusionResult(
            verdict=CrossModalVerdict.INSUFFICIENT,
            fused_confidence=0.0,
            corroborations=[],
            contradictions=[],
            independent_modalities=[],
            fusion_rationale="No signals extracted from any agent findings.",
        )

    # Check all pairs for corroboration and contradiction
    corroborations: list[dict[str, str]] = []
    contradictions: list[dict[str, str]] = []

    for i in range(len(signals)):
        for j in range(i + 1, len(signals)):
            # Skip same-agent pairs for cross-agent comparison
            # (intra-agent phase comparison handled separately below)
            if signals[i].agent_id == signals[j].agent_id:
                continue

            corr = _find_corroboration(signals[i], signals[j])
            if corr:
                corroborations.append(corr)
                continue

            contra = _find_contradiction(signals[i], signals[j])
            if contra:
                contradictions.append(contra)

    # Intra-agent phase comparison: check if initial and deep findings
    # from the same agent agree or contradict on manipulation.
    _agent_signals: dict[str, list[ModalitySignal]] = {}
    for s in signals:
        _agent_signals.setdefault(s.agent_id, []).append(s)
    for agent_id, agent_sigs in _agent_signals.items():
        initial_sigs = [s for s in agent_sigs if s.analysis_phase == "initial"]
        deep_sigs = [s for s in agent_sigs if s.analysis_phase == "deep"]
        for ini in initial_sigs:
            for dep in deep_sigs:
                if ini.manipulation_detected and not dep.manipulation_detected:
                    contradictions.append(
                        {
                            "agents": f"{agent_id} initial vs deep",
                            "modalities": f"{ini.modality.value} initial vs deep",
                            "detail": (
                                f"{ini.finding_type} (initial) detects manipulation "
                                f"while {dep.finding_type} (deep) indicates authenticity "
                                f"within the same agent"
                            ),
                        }
                    )
                elif ini.manipulation_detected and dep.manipulation_detected:
                    corroborations.append(
                        {
                            "agents": f"{agent_id} initial + deep",
                            "modalities": f"{ini.modality.value} initial + deep",
                            "direction": "manipulation",
                            "detail": (
                                f"{ini.finding_type} (initial) and {dep.finding_type} (deep) "
                                f"both detect manipulation within the same agent"
                            ),
                        }
                    )

    # Determine independent modalities (no corroboration or contradiction)
    involved_agents: set[str] = set()
    for c in corroborations + contradictions:
        for part in c.get("agents", "").replace(" vs ", " + ").split(" + "):
            involved_agents.add(part.strip())

    independent_modalities = [
        s.modality.value for s in signals if s.agent_id not in involved_agents
    ]

    # Compute fused confidence using Weighted Power Mean (p=2)
    # This prevents low-confidence noise from diluting high-confidence forensic proof.
    if corroborations:
        weighted_power_sum = 0.0
        weight_sum = 0.0
        p = 2.0  # Power factor to favor strong signals

        for s in signals:
            # Find max pair weight with any corroborating modality
            max_weight = DEFAULT_PAIR_WEIGHT
            for corr in corroborations:
                if s.agent_id in corr.get("agents", ""):
                    for other_s in signals:
                        if other_s.agent_id != s.agent_id and other_s.agent_id in corr.get(
                            "agents", ""
                        ):
                            pk = frozenset({s.modality, other_s.modality})
                            max_weight = max(
                                max_weight,
                                _MODALITY_PAIR_WEIGHTS.get(pk, DEFAULT_PAIR_WEIGHT),
                            )

            # Weighted Power Mean calculation
            weighted_power_sum += (s.confidence**p) * max_weight
            weight_sum += max_weight

        fused_confidence = (weighted_power_sum / weight_sum) ** (1 / p) if weight_sum > 0 else 0.5
    else:
        # No corroboration — use simple max confidence to represent "strongest hint"
        fused_confidence = max(s.confidence for s in signals)

    # Determine verdict
    if contradictions and not corroborations:
        verdict = CrossModalVerdict.CONTRADICTED
    elif contradictions and corroborations:
        verdict = CrossModalVerdict.PARTIALLY_CORROBORATED
    elif len(corroborations) >= 3:
        verdict = CrossModalVerdict.CORROBORATED
    elif corroborations:
        verdict = CrossModalVerdict.PARTIALLY_CORROBORATED
    elif independent_modalities:
        verdict = CrossModalVerdict.INDEPENDENT
    else:
        verdict = CrossModalVerdict.INSUFFICIENT

    # Build rationale
    rationale_parts: list[str] = []
    if corroborations:
        unique_corr = {c["detail"] for c in corroborations}
        rationale_parts.append(
            f"{len(unique_corr)} cross-modal agreement anchor(s) detected: "
            + "; ".join(list(unique_corr)[:3])
        )
    if contradictions:
        unique_contra = {c["detail"] for c in contradictions}
        rationale_parts.append(
            f"{len(unique_contra)} cross-modal contradiction(s) flagged for human review: "
            + "; ".join(list(unique_contra)[:3])
        )
    if independent_modalities:
        rationale_parts.append(
            f"Independent modalities (unverified sensors): {', '.join(set(independent_modalities))}"
        )

    rationale = (
        " ".join(rationale_parts) if rationale_parts else "No cross-modal relationships detected."
    )

    logger.info(
        "Cross-modal fusion complete",
        verdict=verdict.value,
        fused_confidence=round(fused_confidence, 3),
        corroboration_count=len(corroborations),
        contradiction_count=len(contradictions),
    )

    return FusionResult(
        verdict=verdict,
        fused_confidence=round(fused_confidence, 4),
        corroborations=corroborations,
        contradictions=contradictions,
        independent_modalities=list(set(independent_modalities)),
        fusion_rationale=rationale,
    )
