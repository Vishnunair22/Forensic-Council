"""
Arbiter Verdict Data Models and Scoring Logic.
Extracted from arbiter.py to improve maintainability.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from core.agent_registry import AgentID
from core.forensic_policy import ForensicPolicy


class FindingVerdict(StrEnum):
    """Verdict for finding comparison."""

    AGREEMENT = "AGREEMENT"
    INDEPENDENT = "INDEPENDENT"
    CONTRADICTION = "CONTRADICTION"


class FindingComparison(BaseModel):
    """Comparison between two agent findings."""

    finding_a: dict[str, Any]
    finding_b: dict[str, Any]
    verdict: FindingVerdict
    cross_modal_confirmed: bool = False


class ChallengeResult(BaseModel):
    """Result of a challenge loop."""

    challenge_id: UUID = Field(default_factory=uuid4)
    challenged_agent: str
    original_finding: dict[str, Any]
    revised_finding: dict[str, Any] | None = None
    resolved: bool = False


class TribunalCase(BaseModel):
    """Tribunal case for unresolved contradictions."""

    tribunal_id: UUID = Field(default_factory=uuid4)
    agent_a_id: str
    agent_b_id: str
    contradiction: FindingComparison
    human_judgment: dict[str, Any] | None = None
    resolved: bool = False


class AgentMetrics(BaseModel):
    """Per-agent performance metrics computed at arbiter deliberation time."""

    agent_id: str
    agent_name: str
    total_tools_called: int = 0
    tools_succeeded: int = 0
    tools_failed: int = 0
    tools_not_applicable: int = 0  # tools that don't apply to this file type (not errors)
    error_rate: float = 0.0  # 0.0–1.0 (failed / applicable tools run)
    confidence_score: float = 0.0  # avg confidence across real applicable findings
    finding_count: int = 0
    deep_finding_count: int = 0  # Number of deep-phase findings
    skipped: bool = False  # True when file type not applicable


class ForensicReport(BaseModel):
    """Complete forensic report with all required sections."""

    report_id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    case_id: str
    executive_summary: str
    per_agent_findings: dict[str, list[dict[str, Any]]]
    per_agent_metrics: dict[str, Any] = Field(
        default_factory=dict,
        description="Per-agent tool success rates, error rates, and confidence scores.",
    )
    per_agent_analysis: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Per-agent Groq-synthesised narrative comparing initial vs deep findings. "
            "Keyed by agent_id. Only present for active agents."
        ),
    )
    overall_confidence: float = 0.0
    overall_error_rate: float = 0.0
    overall_verdict: str = "REVIEW REQUIRED"
    cross_modal_confirmed: list[dict[str, Any]] = Field(default_factory=list)
    contested_findings: list[dict[str, Any]] = Field(default_factory=list)
    tribunal_resolved: list[TribunalCase] = Field(default_factory=list)
    incomplete_findings: list[dict[str, Any]] = Field(default_factory=list)
    stub_findings: list[dict[str, Any]] = Field(default_factory=list)
    gemini_vision_findings: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Deep vision findings produced by Google Gemini (Agents 1, 3, 5 deep pass). "
            "Compiled separately for review; also present inside per_agent_findings."
        ),
    )
    case_linking_flags: list[dict[str, Any]] = Field(default_factory=list)
    chain_of_custody_log: list[dict[str, Any]] = Field(default_factory=list)
    evidence_version_trees: list[dict[str, Any]] = Field(default_factory=list)
    react_chains: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    self_reflection_outputs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    uncertainty_statement: str
    # New structured summary fields
    verdict_sentence: str = ""
    key_findings: list[str] = Field(default_factory=list)
    reliability_note: str = ""
    # New verdict/confidence fields
    manipulation_probability: float = 0.0
    compression_penalty: float = Field(
        default=1.0,
        description="Reliability multiplier applied to fragile compression-sensitive tools.",
    )
    # C: Confidence range across all active agent findings
    confidence_min: float = 0.0
    confidence_max: float = 0.0
    confidence_std_dev: float = 0.0
    # New coverage/agent fields
    applicable_agent_count: int = 0
    skipped_agents: dict[str, str] = Field(default_factory=dict)
    analysis_coverage_note: str = ""
    # D: Flat per-agent verdict/confidence summary
    per_agent_summary: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "Flat summary for each agent: verdict, confidence_pct, tools_ok, "
            "tools_total, findings, error_rate_pct."
        ),
    )
    cryptographic_signature: str = ""
    report_hash: str = ""
    signed_utc: datetime | None = None
    cross_modal_fusion: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Cross-modal fusion analysis result: verdict, fused_confidence, "
            "corroborations, contradictions, independent_modalities, rationale."
        ),
    )
    degradation_flags: list[str] = Field(
        default_factory=list,
        description=(
            "Populated whenever an analysis subsystem fell back to a reduced-capability "
            "mode (e.g. Gemini unavailable, LLM synthesis disabled, Redis offline). "
            "A non-empty list means this report does NOT reflect full AI analysis "
            "and MUST display a DEGRADED ANALYSIS warning in any UI or printout."
        ),
    )


# --- Verdict Constants ---

AGENT_NAMES: dict[str, str] = {aid.value: aid.friendly_name for aid in AgentID}

FINDING_CATEGORY_MAP: dict[str, str] = {
    # Image integrity
    "ela": "image_integrity",
    "error_level": "image_integrity",
    "ghost": "image_integrity",
    "jpeg_ghost": "image_integrity",
    "noise": "image_integrity",
    "frequency": "image_integrity",
    "prnu": "image_integrity",
    "chromatic": "image_integrity",
    # Manipulation signals
    "splicing": "manipulation",
    "copy_move": "manipulation",
    "manipulation": "manipulation",
    "deepfake": "manipulation",
    "face_swap": "manipulation",
    "tamper": "manipulation",
    "forgery": "manipulation",
    "diffusion": "manipulation",
    "gan": "manipulation",
    # Metadata / provenance
    "exif": "metadata",
    "gps": "metadata",
    "metadata": "metadata",
    "timestamp": "metadata",
    "geolocation": "metadata",
    "hex_signature": "metadata",
    "file_signature": "metadata",
    "chimeric": "metadata",
    "provenance": "metadata",
    # Codec / encoding
    "codec": "codec",
    "encoding": "codec",
    "bitrate": "codec",
    "compression": "codec",
    "quantization": "codec",
    # Audio authenticity
    "speaker": "audio",
    "anti_spoofing": "audio",
    "audio": "audio",
    "diarization": "audio",
    "voice": "audio",
    "enf": "audio",
    "flux": "audio",
    # Object / scene
    "yolo": "object_detection",
    "object": "object_detection",
    "lighting": "object_detection",
    "contraband": "object_detection",
    "scene": "object_detection",
    "incongruence": "object_detection",
    "scale": "object_detection",
    # Video motion
    "optical_flow": "video",
    "video": "video",
    "rolling_shutter": "video",
    "frame": "video",
    "interframe": "video",
    # Steganography
    "steganography": "steganography",
    "steg": "steganography",
    "hidden": "steganography",
    "lsb": "steganography",
}

SHARED_TOOLS: set[str] = {
    "splicing_detect",
    "deepfake_frequency_check",
    "noise_fingerprint",
    "copy_move_detect",
    "adversarial_robustness_check",
}


def evidence_verdict_of(finding: dict[str, Any]) -> str:
    """Return the normalized evidence verdict for a finding."""
    verdict = str(finding.get("evidence_verdict") or "").upper()
    if verdict in {"POSITIVE", "NEGATIVE", "INCONCLUSIVE", "NOT_APPLICABLE", "ERROR"}:
        return verdict

    meta = finding.get("metadata") or {}
    meta_verdict = str(meta.get("evidence_verdict") or meta.get("verdict") or "").upper()
    if meta_verdict in {"NOT_APPLICABLE", "ERROR"}:
        return meta_verdict
    if finding.get("status") == "NOT_APPLICABLE":
        return "NOT_APPLICABLE"
    if meta.get("court_defensible") is False:
        return "ERROR"
    if _has_legacy_positive_signal(finding):
        return "POSITIVE"
    if finding.get("status") == "INCONCLUSIVE":
        return "INCONCLUSIVE"
    return "NEGATIVE"


def confidence_of(finding: dict[str, Any], default: float | None = None) -> float | None:
    """Return a usable confidence, preserving None for NA/error findings."""
    if evidence_verdict_of(finding) in {"NOT_APPLICABLE", "ERROR"}:
        return None
    calibration_status = str(finding.get("calibration_status") or "").upper()
    use_calibrated = bool(finding.get("calibrated")) or calibration_status == "TRAINED"
    keys = (
        (
            "calibrated_probability",
            "tool_reliability",
            "raw_confidence_score",
            "confidence_raw",
            "manipulation_confidence",
        )
        if use_calibrated
        else (
            "tool_reliability",
            "confidence_raw",
            "manipulation_confidence",
            "raw_confidence_score",
            "calibrated_probability",
        )
    )
    for key in keys:
        value = finding.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return default


# Confidence floor for a signal to be considered "Positive" or "Strong" in
# final report synthesis. Low-confidence semantic matches (e.g. CLIP 5%)
# are excluded from manipulation probability and should be excluded from
# "Suspicious" status labels to prevent false alarms.
MIN_CONFIDENCE_THRESHOLD = 0.15


def _has_legacy_positive_signal(finding: dict[str, Any]) -> bool:
    meta = finding.get("metadata") or {}
    return (
        meta.get("manipulation_detected") is True
        or meta.get("deepfake_detected") is True
        or meta.get("deepfake_suspected") is True
        or meta.get("splicing_detected") is True
        or meta.get("copy_move_detected") is True
        or meta.get("is_ai_generated") is True
        or meta.get("gan_artifact_detected") is True
        or meta.get("diffusion_detected") is True
        or meta.get("concern_flag") is True
        or meta.get("scene_incongruent") is True
        or meta.get("mismatch_detected") is True
        or meta.get("stego_suspected") is True
        or meta.get("scale_consistent") is False
        or meta.get("swap_suspect") is True
        or meta.get("face_swap_detected") is True
        or meta.get("splice_detected") is True
        or meta.get("spoof_detected") is True
        or meta.get("synthetic_detected") is True
        or meta.get("shift_detected") is True
        or meta.get("discontinuity_detected") is True
        or meta.get("re_encoding_detected") is True
        or meta.get("re_encode_suspect") is True
        or meta.get("adversarial_pattern_detected") is True
        or meta.get("uniformity_suspect") is True
        or meta.get("prosody_anomaly") is True
        or str(meta.get("verdict", "")).upper()
        in ("LIKELY_AI_GENERATED", "LIKELY_SPOOFED", "LIKELY_SYNTHETIC")
        or (
            "INCONSISTENT" in str(meta.get("prnu_verdict", "")).upper()
            and meta.get("prnu_verdict") is not None
        )
        or (
            "INCONSISTENT" in str(meta.get("verdict", "")).upper()
            and meta.get("verdict") is not None
        )
        or ("TAMPERED" in str(meta.get("verdict", "")).upper() and meta.get("verdict") is not None)
    )


def calculate_manipulation_probability(
    all_findings: list[dict[str, Any]],
    compression_penalty: float = 1.0,
) -> tuple[float, int]:
    """
    Core deterministic calculation of manipulation probability.
    Returns (probability, signals_count).
    """
    _diffusion_detected_globally = any(
        (f.get("metadata") or {}).get("diffusion_detected") is True
        for f in all_findings
        if not f.get("stub_result")
    )

    _manip_weighted: list[tuple[float, float]] = []  # (confidence, weight)
    _seen_tool_agents: dict[tuple[str, str], tuple[float, str]] = {}

    for _f in all_findings:
        if _f.get("stub_result"):
            continue
        _meta = _f.get("metadata") or {}
        _evidence_verdict = evidence_verdict_of(_f)
        if _evidence_verdict in {"NOT_APPLICABLE", "ERROR", "NEGATIVE"}:
            continue
        _is_direct_manip = _evidence_verdict == "POSITIVE" or _has_legacy_positive_signal(_f)

        if _is_direct_manip:
            _c = confidence_of(_f, default=0.5) or 0.5
            if _c >= MIN_CONFIDENCE_THRESHOLD:
                _tool = (
                    str(_meta.get("tool_name", _f.get("finding_type", "")))
                    .lower()
                    .replace(" ", "_")
                )
                _w = ForensicPolicy.get_tool_weight(_tool)

                if compression_penalty < 1.0:
                    fragile_tools = {
                        "ela_full_image",
                        "jpeg_ghost_detect",
                        "noise_fingerprint",
                        "copy_move_detect",
                        "splicing_detect",
                        "diffusion_artifact_detector",
                        "frequency_domain_analysis",
                    }
                    if _tool in fragile_tools:
                        _w *= compression_penalty

                if _diffusion_detected_globally and _tool in {
                    "ela_full_image",
                    "jpeg_ghost_detect",
                }:
                    _w = 0.4

                _phase = str(_meta.get("analysis_phase", "initial"))
                _agent_tool_key = (str(_f.get("agent_id", "")), _tool)
                _prev = _seen_tool_agents.get(_agent_tool_key)
                if _prev is not None:
                    _prev_c, _prev_phase = _prev
                    if _prev_phase == "deep" and _phase == "initial":
                        continue
                    if _prev_phase == _phase and _prev_c >= _c:
                        continue
                _seen_tool_agents[_agent_tool_key] = (_c, _phase)

                _manip_weighted.append((_c, _w))

    signals_count = len(_manip_weighted)

    if not _manip_weighted:
        return 0.0, 0
    elif len(_manip_weighted) == 1:
        # For a single signal, we apply a more conservative decay unless the weight is very high.
        _c0, _w0 = _manip_weighted[0]
        _anchored_decay = max(0.4, _w0 * 0.8) # Cap single-signal impact
        return round(_c0 * _anchored_decay, 3), 1
    else:
        # Multi-signal corroboration: calculate weighted average and add volume bonus
        _sorted_manip = sorted(_manip_weighted, key=lambda x: x[0] * x[1], reverse=True)
        _top = _sorted_manip[:7]
        _tw = sum(_w for _, _w in _top)
        _sum_weighted = sum(_c * _w for _c, _w in _top)
        _base_prob = _sum_weighted / _tw if _tw > 0 else 0.0

        # Volume bonus: more signals from independent agents increase the probability
        _volume_bonus = min(0.25, (len(_sorted_manip) - 1) * 0.05)

        final_prob = round(min(ForensicPolicy.MANIP_PROBABILITY_CAP, _base_prob + _volume_bonus), 3)
        return final_prob, signals_count


def _get_finding_category(finding_type: str, agent_id: str = "") -> str | None:
    """Map a finding_type to its semantic category, or None."""
    ft = finding_type.lower().replace(" ", "_")
    aid = agent_id.upper()
    for keyword, category in sorted(
        FINDING_CATEGORY_MAP.items(), key=lambda x: len(x[0]), reverse=True
    ):
        if keyword in ft:
            if keyword in ("noise", "prnu") and aid == AgentID.AGENT3.value.upper():
                return "object_detection"
            return category
    return None


async def cross_agent_comparison(all_findings: list[dict[str, Any]]) -> list[FindingComparison]:
    """Compare findings across agents using category-indexed comparison."""
    comparisons: list[FindingComparison] = []
    real_findings = [f for f in all_findings if not f.get("stub_result")]
    _cat_cache: dict[tuple[str, str], str | None] = {}

    def _cat(ft: str, aid: str) -> str | None:
        key = (ft, aid)
        if key not in _cat_cache:
            _cat_cache[key] = _get_finding_category(ft, aid)
        return _cat_cache[key]

    category_buckets: dict[str, dict[str, list[dict]]] = {}
    uncategorised: list[dict] = []

    for f in real_findings:
        agent_id = f.get("agent_id", "")
        c = _cat(f.get("finding_type", ""), agent_id)
        if c is None:
            uncategorised.append(f)
        else:
            category_buckets.setdefault(c, {}).setdefault(agent_id, []).append(f)

    # 10 findings per bucket balances thoroughness vs O(n²) comparison performance
    max_findings_per_bucket = 10
    for _cat_name, agent_map in category_buckets.items():
        for agent_id, flist in agent_map.items():
            if len(flist) > max_findings_per_bucket:
                flist.sort(key=lambda x: confidence_of(x, default=0.0) or 0.0, reverse=True)
                agent_map[agent_id] = flist[:max_findings_per_bucket]
        agent_ids = list(agent_map.keys())
        for i, agent_a in enumerate(agent_ids):
            for agent_b in agent_ids[i + 1 :]:
                for fa in agent_map[agent_a]:
                    for fb in agent_map[agent_b]:
                        _tool_a = str((fa.get("metadata") or {}).get("tool_name", "")).lower()
                        _tool_b = str((fb.get("metadata") or {}).get("tool_name", "")).lower()
                        if _tool_a == _tool_b and _tool_a in SHARED_TOOLS:
                            continue
                        verdict_a = evidence_verdict_of(fa)
                        verdict_b = evidence_verdict_of(fb)
                        if "ERROR" in {verdict_a, verdict_b} or "NOT_APPLICABLE" in {
                            verdict_a,
                            verdict_b,
                        }:
                            continue
                        conf_a = confidence_of(fa, default=0.5) or 0.5
                        conf_b = confidence_of(fb, default=0.5) or 0.5
                        conf_aligned = abs(conf_a - conf_b) <= 0.35
                        is_agreement = verdict_a == verdict_b and conf_aligned
                        comparisons.append(
                            FindingComparison(
                                finding_a=fa,
                                finding_b=fb,
                                verdict=FindingVerdict.AGREEMENT
                                if is_agreement
                                else FindingVerdict.CONTRADICTION,
                                cross_modal_confirmed=is_agreement,
                            )
                        )

    for f in uncategorised:
        comparisons.append(
            FindingComparison(
                finding_a=f,
                finding_b=f,
                verdict=FindingVerdict.INDEPENDENT,
                cross_modal_confirmed=False,
            )
        )

    return comparisons
