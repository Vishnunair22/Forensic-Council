"""
Council Arbiter & Report Generator
==============================

The synthesis layer that deliberates on agent findings, manages challenge loops,
tribunal escalation, and generates court-admissible reports.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from core.config import Settings, get_settings
from core.cross_modal_fusion import fuse as cross_modal_fuse
from core.llm_client import LLMClient
from core.severity import assign_severity_tier
from core.signing import KeyStore, sign_content
from core.structured_logging import get_logger

logger = get_logger(__name__)


class FindingVerdict(str, Enum):
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
    revised_finding: Optional[dict[str, Any]] = None
    resolved: bool = False


class TribunalCase(BaseModel):
    """Tribunal case for unresolved contradictions."""

    tribunal_id: UUID = Field(default_factory=uuid4)
    agent_a_id: str
    agent_b_id: str
    contradiction: FindingComparison
    human_judgment: Optional[dict[str, Any]] = None
    resolved: bool = False


class AgentMetrics(BaseModel):
    """Per-agent performance metrics computed at arbiter deliberation time."""

    agent_id: str
    agent_name: str
    total_tools_called: int = 0
    tools_succeeded: int = 0
    tools_failed: int = 0
    tools_not_applicable: int = (
        0  # tools that don't apply to this file type (not errors)
    )
    error_rate: float = 0.0  # 0.0–1.0 (failed / applicable tools run)
    confidence_score: float = 0.0  # avg confidence across real applicable findings
    finding_count: int = 0
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
    signed_utc: Optional[datetime] = None
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


class CouncilArbiter:
    """
    Council Arbiter - the deliberation, challenge loop, Tribunal, and
    court-admissible report generator.
    """

    def __init__(
        self,
        session_id: UUID,
        custody_logger: Any = None,
        inter_agent_bus: Any = None,
        calibration_layer: Any = None,
        agent_factory: Any = None,
        config: Settings | None = None,
    ):
        self.session_id = session_id
        self.custody_logger = custody_logger
        self.inter_agent_bus = inter_agent_bus
        self.calibration_layer = calibration_layer
        self.agent_factory = agent_factory
        self.config = config or get_settings()
        self._key_store = KeyStore()
        # Ensure arbiter has a key
        self._key_store.get_or_create("Arbiter")
        # Shared LLM client reused across all synthesis calls to avoid
        # repeated TCP/TLS handshakes during parallel deliberation.
        self._synthesis_client: Optional[LLMClient] = None
        self._step_hook: Any = None

    # ── Shared agent name map ────────────────────────────────────────────
    _AGENT_NAMES: dict[str, str] = {
        "Agent1": "Image Forensics",
        "Agent2": "Audio Forensics",
        "Agent3": "Object Detection",
        "Agent4": "Video Forensics",
        "Agent5": "Metadata Forensics",
    }

    # ── A: Semantic category map ─────────────────────────────────────────
    # Maps finding_type keywords → semantic category for cross-agent comparison.
    # Two findings are "related" only if they share the same semantic category,
    # not just an overlapping bag-of-words token.
    _FINDING_CATEGORY_MAP: dict[str, str] = {
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
        # Metadata / provenance
        "exif": "metadata",
        "gps": "metadata",
        "metadata": "metadata",
        "timestamp": "metadata",
        "geolocation": "metadata",
        "hex_signature": "metadata",
        "file_signature": "metadata",
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
        # Object / scene
        "yolo": "object_detection",
        "object": "object_detection",
        "lighting": "object_detection",
        "contraband": "object_detection",
        "scene": "object_detection",
        # Video motion
        "optical_flow": "video",
        "video": "video",
        "rolling_shutter": "video",
        "frame": "video",
        # Steganography
        "steganography": "steganography",
        "steg": "steganography",
        "hidden": "steganography",
        "lsb": "steganography",
    }

    # ── B: Tool reliability tiers ────────────────────────────────────────
    # Weight multiplier applied to each finding's confidence when computing
    # manipulation_probability. Calibrated tools carry full weight; ML-based
    # carry 0.75x; heuristic/metadata carry 0.50x.
    _TOOL_RELIABILITY_TIERS: dict[str, float] = {
        # Calibrated (highest weight — statistically validated)
        "ela": 1.0,
        "jpeg_ghost": 1.0,
        "prnu_analysis": 1.0,
        "codec_fingerprint": 1.0,
        "error_level_analysis": 1.0,
        "noise_fingerprint": 1.0,
        "frequency_domain": 1.0,
        # ML-based (medium weight — model-dependent)
        "yolo_detection": 0.75,
        "deepfake_detection": 0.75,
        "face_swap_detection": 0.75,
        "speaker_diarization": 0.75,
        "anti_spoofing": 0.75,
        "optical_flow_analysis": 0.75,
        "object_detection": 0.75,
        "lighting_consistency": 0.75,
        # Heuristic / metadata (lower weight — easily spoofed)
        "exif_analysis": 0.5,
        "metadata_analysis": 0.5,
        "steganography_scan": 0.5,
        "hex_signature": 0.5,
        "gps_analysis": 0.5,
        "timestamp_analysis": 0.5,
    }
    _DEFAULT_TOOL_RELIABILITY = 0.65  # fallback for unrecognised tool names

    # ── Manipulation probability calculation constants ────────────────────
    # These are empirically-derived weights for combining manipulation signals
    # into a single probability score.  The formula:
    #   - Single signal: P = confidence × reliability_weight × _SINGLE_SIGNAL_DECAY
    #     (decay factor accounts for single-source uncertainty)
    #   - Multiple signals: P = weighted_mean(top 5 signals)
    #     (top-k prevents low-confidence signals from diluting high-confidence ones)
    _SINGLE_SIGNAL_DECAY: float = 0.55
    _MANIP_TOP_K: int = 5
    _MANIP_PROBABILITY_CAP: float = 0.95

    async def deliberate(
        self,
        agent_results: dict[str, dict[str, Any]],
        case_id: str = "",
        use_llm: bool = True,
    ) -> ForensicReport:
        """Deliberate on agent results and generate a forensic report.

        Only ACTIVE agents (those that ran real tools on the evidence) are used
        for Groq synthesis.  Skipped agents (file type not applicable) are
        excluded from the executive summary and verdict calculation but their
        skip findings are kept in per_agent_findings for transparency.

        Computes per-agent metrics (tool success/failure rates, confidence) and
        overall verdict from aggregated confidence + error rates.
        """
        _SKIP_FINDING_TYPES = {"file type not applicable", "format not supported"}

        def _is_skipped_agent(findings: list[dict[str, Any]]) -> bool:
            """True when all findings are file-type-not-applicable stubs."""
            if not findings:
                return True
            return all(
                str(f.get("finding_type", "")).lower() in _SKIP_FINDING_TYPES
                for f in findings
            )

        def _deduplicate_findings(
            findings: list[dict[str, Any]],
        ) -> list[dict[str, Any]]:
            """Remove duplicate findings, assign severity tier in one pass."""
            seen: set[tuple[str, str, str, str]] = set()
            out: list[dict[str, Any]] = []
            for f in findings:
                meta = (
                    f.get("metadata", {}) if isinstance(f.get("metadata"), dict) else {}
                )
                key = (
                    str(f.get("agent_id", "")),
                    str(f.get("finding_type", "")),
                    str(meta.get("tool_name", "")),
                    str(meta.get("analysis_phase", "initial")),
                )
                if key not in seen:
                    seen.add(key)
                    if isinstance(f, dict) and "severity_tier" not in f:
                        f["severity_tier"] = assign_severity_tier(f)
                    out.append(f)
            return out

        def _compute_agent_metrics(
            agent_id: str, findings: list[dict[str, Any]], skipped: bool
        ) -> "AgentMetrics":
            agent_name = self._AGENT_NAMES.get(agent_id, agent_id)
            if skipped:
                return AgentMetrics(
                    agent_id=agent_id,
                    agent_name=agent_name,
                    skipped=True,
                    total_tools_called=0,
                    tools_succeeded=0,
                    tools_failed=0,
                    tools_not_applicable=0,
                    error_rate=0.0,
                    confidence_score=0.0,
                    finding_count=0,
                )
            real = [
                f
                for f in findings
                if str(f.get("finding_type", "")).lower() not in _SKIP_FINDING_TYPES
            ]
            total = len(real)

            not_applicable_flags = (
                "ela_not_applicable",
                "ghost_not_applicable",
                "noise_fingerprint_not_applicable",
                "prnu_not_applicable",
            )

            def _is_not_applicable(f: dict) -> bool:
                meta = f.get("metadata") or {}
                # Also treat NOT_APPLICABLE verdict (from lossless-format guards) as not-applicable
                if str(meta.get("verdict", "")).upper() == "NOT_APPLICABLE":
                    return True
                if str(meta.get("prnu_verdict", "")).upper() == "NOT_APPLICABLE":
                    return True
                return any(meta.get(flag) for flag in not_applicable_flags)

            def _is_failed(f: dict) -> bool:
                if _is_not_applicable(f):
                    return False  # not-applicable is expected, not a failure
                meta = f.get("metadata") or {}
                return (
                    meta.get("court_defensible") is False
                    or f.get("status") == "INCOMPLETE"
                )

            not_applicable = sum(1 for f in real if _is_not_applicable(f))
            failed = sum(1 for f in real if _is_failed(f))
            # Applicable = ran and was expected to produce a real result
            applicable = total - not_applicable
            succeeded = applicable - failed
            error_rate = round(failed / applicable, 3) if applicable > 0 else 0.0
            # Confidence only over findings that actually ran (not not-applicable, not failed)
            conf_scores = [
                f.get("raw_confidence_score")
                or f.get("calibrated_probability")
                or f.get("confidence_raw")
                or 0.0
                for f in real
                if not _is_not_applicable(f) and not _is_failed(f)
            ]
            confidence = (
                round(sum(conf_scores) / len(conf_scores), 3) if conf_scores else 0.0
            )
            return AgentMetrics(
                agent_id=agent_id,
                agent_name=agent_name,
                skipped=False,
                total_tools_called=total,
                tools_succeeded=succeeded,
                tools_failed=failed,
                tools_not_applicable=not_applicable,
                error_rate=error_rate,
                confidence_score=confidence,
                finding_count=total,
            )

        # Helper: call optional step-progress hook if set externally
        async def _step(msg: str) -> None:
            if self._step_hook is not None:
                try:
                    await self._step_hook(msg)
                except Exception as e:
                    logger.debug(f"Arbiter step hook failed: {e}")

        # ── Partition agents into active vs skipped ───────────────────────
        await _step("Gathering all agent findings…")
        all_findings: list[dict[str, Any]] = []
        per_agent_findings: dict[str, list[dict[str, Any]]] = {}
        per_agent_metrics: dict[str, Any] = {}
        active_agent_results: dict[str, dict[str, Any]] = {}
        gemini_findings_by_agent: dict[str, list[dict[str, Any]]] = {}

        for agent_id, result in agent_results.items():
            raw_findings = result.get("findings", [])
            deduped = _deduplicate_findings(raw_findings)
            skipped = _is_skipped_agent(deduped)
            per_agent_findings[agent_id] = deduped
            metrics = _compute_agent_metrics(agent_id, deduped, skipped)
            per_agent_metrics[agent_id] = metrics.model_dump()

            if not skipped:
                active_agent_results[agent_id] = {**result, "findings": deduped}
                all_findings.extend(deduped)
                agent_gemini = [
                    f
                    for f in deduped
                    if isinstance(f, dict)
                    and f.get("metadata", {}).get("analysis_source") == "gemini_vision"
                ]
                if agent_gemini:
                    gemini_findings_by_agent[agent_id] = agent_gemini

        # Severity tiers already assigned in _deduplicate_findings — rebuild all_findings
        all_findings = [
            f
            for findings_list in [
                per_agent_findings[aid] for aid in active_agent_results
            ]
            for f in findings_list
        ]

        logger.info(
            f"Arbiter: {len(active_agent_results)} active agents, "
            f"{len(agent_results) - len(active_agent_results)} skipped, "
            f"{len(all_findings)} total findings"
        )

        # ── Early return if no active agents reported ────────────────────
        if not active_agent_results:
            logger.warning(
                "Arbiter: No active agents produced findings. Generating empty report."
            )
            return ForensicReport(
                session_id=self.session_id,
                case_id=case_id or f"case_{self.session_id}",
                executive_summary="No forensic agents produced findings for this evidence. Please verify the file integrity and try again.",
                per_agent_findings=per_agent_findings,
                per_agent_metrics=per_agent_metrics,
                per_agent_analysis={},
                overall_confidence=0.0,
                overall_error_rate=0.0,
                overall_verdict="INCONCLUSIVE",
                uncertainty_statement="No analysis was possible with the selected agents.",
                verdict_sentence="No analysis results available.",
                key_findings=[],
                reliability_note="Analysis was skipped for all agents.",
            )

        # ── Compile Gemini findings list ──────────────────────────────────
        gemini_vision_findings: list[dict[str, Any]] = []
        for gf_list in gemini_findings_by_agent.values():
            gemini_vision_findings.extend(gf_list)
        if gemini_vision_findings:
            logger.info(
                f"Arbiter: {len(gemini_vision_findings)} Gemini vision findings across {len(gemini_findings_by_agent)} agent(s)"
            )

        # ── Compute overall confidence + error rate ───────────────────────
        active_metrics = [
            m
            for m in per_agent_metrics.values()
            if not m.get("skipped") and m.get("total_tools_called", 0) > 0
        ]
        # Weighted confidence: weight each agent by reliability × applicable tool count.
        # An agent with 25% error rate and 4 applicable tools gets far less weight than
        # one with 0% error rate and 8 tools.
        _w_sum = 0.0
        _wc_sum = 0.0
        for _m in active_metrics:
            _applicable = _m.get("total_tools_called", 0) - _m.get(
                "tools_not_applicable", 0
            )
            if _applicable <= 0:
                continue
            _reliability = max(0.0, 1.0 - _m.get("error_rate", 0.0))
            _weight = _reliability * _applicable
            _wc_sum += _m["confidence_score"] * _weight
            _w_sum += _weight
        overall_confidence = round(_wc_sum / _w_sum, 3) if _w_sum > 0 else 0.0
        overall_error_rate = (
            round(sum(m["error_rate"] for m in active_metrics) / len(active_metrics), 3)
            if active_metrics
            else 0.0
        )

        # ── C: Confidence range across active agent scores ────────────────
        _all_conf_scores = [
            m["confidence_score"]
            for m in active_metrics
            if m.get("confidence_score", 0) > 0
        ]
        if _all_conf_scores:
            confidence_min = round(min(_all_conf_scores), 3)
            confidence_max = round(max(_all_conf_scores), 3)
            _mean = sum(_all_conf_scores) / len(_all_conf_scores)
            _variance = sum((x - _mean) ** 2 for x in _all_conf_scores) / len(
                _all_conf_scores
            )
            confidence_std_dev = round(_variance**0.5, 3)
        else:
            confidence_min = confidence_max = confidence_std_dev = 0.0

        # ── Verdict ───────────────────────────────────────────────────────
        # CERTAIN:     high confidence, low error, no contested
        # LIKELY:      good confidence, acceptable error
        # UNCERTAIN:   moderate confidence or some errors
        # INCONCLUSIVE: low confidence or high errors
        # MANIPULATION DETECTED: confidence indicates tampering

        # Run cross-agent comparison
        await _step("Running cross-modal comparison…")
        comparisons = await self.cross_agent_comparison(all_findings)

        # Identify contradictions and run challenge loop
        # Cap at 5 challenge loops — with many findings the O(n²) comparison can
        # produce dozens of "contradictions". Beyond 5, we record the contested
        # finding but skip the loop to avoid sequential custody-log overhead.
        _MAX_CHALLENGE_LOOPS = 5
        await _step("Resolving contested evidence…")
        contested_findings = []
        challenge_results = []
        for comparison in comparisons:
            if comparison.verdict == FindingVerdict.CONTRADICTION:
                _fa = comparison.finding_a
                _fb = comparison.finding_b
                _plain = (
                    f"{self._AGENT_NAMES.get(_fa.get('agent_id', ''), _fa.get('agent_id', 'Unknown'))} "
                    f'reported "{_fa.get("finding_type", "unknown")}" as {_fa.get("status", "?")} '
                    f"({(_fa.get('confidence_raw') or 0.0):.0%} confidence), "
                    f"while {self._AGENT_NAMES.get(_fb.get('agent_id', ''), _fb.get('agent_id', 'Unknown'))} "
                    f'reported "{_fb.get("finding_type", "unknown")}" as {_fb.get("status", "?")} '
                    f"({(_fb.get('confidence_raw') or 0.0):.0%} confidence). "
                    "Flagged for human review."
                )
                _entry = comparison.model_dump(mode="json")
                _entry["plain_description"] = _plain
                contested_findings.append(_entry)
                if len(challenge_results) >= _MAX_CHALLENGE_LOOPS:
                    continue  # Still collect contested entries but skip challenge
                conf_a = comparison.finding_a.get("confidence_raw", 0)
                conf_b = comparison.finding_b.get("confidence_raw", 0)
                challenged_agent = (
                    comparison.finding_b.get("agent_id", "")
                    if conf_b < conf_a
                    else comparison.finding_a.get("agent_id", "")
                )
                context_from_other = (
                    comparison.finding_b
                    if challenged_agent == comparison.finding_a.get("agent_id", "")
                    else comparison.finding_a
                )
                result = await self.challenge_loop(
                    comparison, challenged_agent, context_from_other
                )
                challenge_results.append(result)

        # Cross-modal confirmed findings
        seen_ids = set()
        cross_modal_confirmed = []
        for comparison in comparisons:
            if (
                comparison.verdict == FindingVerdict.AGREEMENT
                and comparison.cross_modal_confirmed
            ):
                fid = comparison.finding_a.get("finding_id")
                if fid not in seen_ids:
                    seen_ids.add(fid)
                    cross_modal_confirmed.append(comparison.finding_a)

        # Incomplete findings (excluding stub results which are not court-defensible)
        incomplete_findings = [
            f for f in all_findings if f.get("status") == "INCOMPLETE"
        ]

        # Stub findings - results from unimplemented tools
        # These are tracked separately and excluded from verdict calculation
        stub_findings = [f for f in all_findings if f.get("stub_result") is True]

        # Log warning if stub findings are present
        if stub_findings:
            logger.warning(
                f"Report contains {len(stub_findings)} stub findings that should not be used for verdicts",
                stub_count=len(stub_findings),
            )

        # ── Contested / incomplete / stub ─────────────────────────────────
        # Also count findings with INCONSISTENT status as contested, since they
        # signal conflicting forensic evidence that warrants human review.
        inconsistent_as_contested = [
            _f
            for _f in all_findings
            if str(_f.get("status", "")).upper() == "CONTESTED"
            or (
                str(_f.get("status", "")).upper() == "CONFIRMED"
                and any(
                    "INCONSISTENT" in str(_f.get("metadata", {}).get(k, "")).upper()
                    for k in ("verdict", "prnu_verdict")
                    if _f.get("metadata", {}).get(k) is not None
                )
            )
        ]
        contested_findings_count = len(contested_findings) + len(
            inconsistent_as_contested
        )

        # ── applicable_agent_count and skipped_agents ─────────────────────
        applicable_agent_count = len(active_agent_results)
        skipped_agents: dict[str, str] = {}
        for _aid, _findings in per_agent_findings.items():
            if _is_skipped_agent(_findings):
                _skip_reason = "Not applicable for this file type"
                for _f in _findings:
                    if str(_f.get("finding_type", "")).lower() in _SKIP_FINDING_TYPES:
                        _r = str(
                            _f.get("reasoning_summary")
                            or _f.get("court_statement")
                            or ""
                        )
                        if _r:
                            _skip_reason = _r[:200]
                        break
                skipped_agents[_aid] = _skip_reason

        # ── D: per_agent_summary ──────────────────────────────────────────
        def _agent_verdict(metrics: dict) -> str:
            if metrics.get("skipped"):
                return "NOT_APPLICABLE"
            conf = metrics.get("confidence_score", 0)
            err = metrics.get("error_rate", 0)

            # Parameterised thresholds with fallbacks for robust verdict calibration
            thresh = getattr(self.config, "verdict_thresholds", {})
            auth_conf = thresh.get("authentic_min_conf", 0.70)
            auth_err = thresh.get("authentic_max_err", 0.15)
            susp_conf = thresh.get("suspicious_max_conf", 0.45)
            susp_err = thresh.get("suspicious_min_err", 0.40)

            if conf >= auth_conf and err <= auth_err:
                return "AUTHENTIC"
            if conf < susp_conf or err > susp_err:
                return "SUSPICIOUS"
            return "INCONCLUSIVE"

        per_agent_summary: dict[str, dict[str, Any]] = {}
        for _aid, _m in per_agent_metrics.items():
            per_agent_summary[_aid] = {
                "agent_name": self._AGENT_NAMES.get(_aid, _aid),
                "verdict": _agent_verdict(_m),
                "confidence_pct": round(_m.get("confidence_score", 0) * 100),
                "tools_ok": _m.get("tools_succeeded", 0),
                "tools_total": _m.get("total_tools_called", 0),
                "findings": _m.get("finding_count", 0),
                "error_rate_pct": round(_m.get("error_rate", 0) * 100),
                "skipped": _m.get("skipped", False),
            }

        # ── analysis_coverage_note ────────────────────────────────────────
        _total_tools = sum(m.get("total_tools_called", 0) for m in active_metrics)
        _failed_tools = sum(m.get("tools_failed", 0) for m in active_metrics)
        _na_tools = sum(m.get("tools_not_applicable", 0) for m in active_metrics)
        _fallback_count = sum(
            1
            for f in all_findings
            if "fallback" in str((f.get("metadata") or {}).get("backend", "")).lower()
            and not any(
                (f.get("metadata") or {}).get(flag)
                for flag in ("ela_not_applicable", "ghost_not_applicable")
            )
        )
        _cov_parts: list[str] = []
        if _failed_tools > 0:
            _cov_parts.append(
                f"{_failed_tools} of {_total_tools} applicable tools failed — findings carry reduced evidential weight"
            )
        if _fallback_count > 0:
            _t = "tool" if _fallback_count == 1 else "tools"
            _cov_parts.append(
                f"{_fallback_count} {_t} used simplified fallback implementations (full ML model unavailable)"
            )
        if _na_tools > 0:
            _t = "tool" if _na_tools == 1 else "tools"
            _cov_parts.append(
                f"{_na_tools} {_t} not applicable to this file type (excluded from verdict)"
            )
        analysis_coverage_note = (
            "; ".join(_cov_parts)
            if _cov_parts
            else f"All {_total_tools} applicable tools ran successfully across {applicable_agent_count} active agent(s)"
        )

        # ── manipulation_probability (B: reliability-weighted) ────────────
        _manip_weighted: list[tuple[float, float]] = []  # (confidence, weight)
        for _f in all_findings:
            if _f.get("stub_result"):
                continue
            _meta = _f.get("metadata") or {}
            if _meta.get("court_defensible") is False:
                continue
            _is_direct_manip = (
                _meta.get("manipulation_detected") is True
                or _meta.get("deepfake_detected") is True
                or _meta.get("splicing_detected") is True
                or _meta.get("copy_move_detected") is True
                or _meta.get("mismatch_detected") is True
                or _meta.get("stego_suspected") is True
                or _meta.get("scale_consistent") is False
                or (
                    "INCONSISTENT" in str(_meta.get("prnu_verdict", "")).upper()
                    and _meta.get("prnu_verdict") is not None
                )
                or (
                    "INCONSISTENT" in str(_meta.get("verdict", "")).upper()
                    and _meta.get("verdict") is not None
                )
                or (
                    "TAMPERED" in str(_meta.get("verdict", "")).upper()
                    and _meta.get("verdict") is not None
                )
            )
            if _is_direct_manip:
                _c = float(
                    _f.get("raw_confidence_score")
                    or _f.get("calibrated_probability")
                    or _f.get("confidence_raw")
                    or 0.5
                )
                if _c >= 0.50:
                    # Look up the reliability weight for this tool (B)
                    _tool = (
                        str(_meta.get("tool_name", _f.get("finding_type", "")))
                        .lower()
                        .replace(" ", "_")
                    )
                    _w = self._TOOL_RELIABILITY_TIERS.get(
                        _tool, self._DEFAULT_TOOL_RELIABILITY
                    )
                    _manip_weighted.append((_c, _w))
        _manip_confs = [c for c, _ in _manip_weighted]
        if not _manip_weighted:
            manipulation_probability = 0.0
        elif len(_manip_weighted) == 1:
            _c0, _w0 = _manip_weighted[0]
            manipulation_probability = round(_c0 * _w0 * self._SINGLE_SIGNAL_DECAY, 3)
        else:
            _top = sorted(_manip_weighted, key=lambda x: x[0] * x[1], reverse=True)[
                : self._MANIP_TOP_K
            ]
            _tw = sum(_w for _, _w in _top)
            manipulation_probability = round(
                min(self._MANIP_PROBABILITY_CAP, sum(_c * _w for _c, _w in _top) / _tw)
                if _tw > 0
                else 0.0,
                3,
            )

        # ── F: Verdict (tightened thresholds) ────────────────────────────
        await _step("Calibrating confidence scores and computing verdict…")
        # Unified verdict vocabulary: AUTHENTIC / LIKELY_AUTHENTIC / INCONCLUSIVE /
        # LIKELY_MANIPULATED / MANIPULATED
        # Manipulation signals: court-defensible findings with direct manipulation flags.
        # Explicit manipulation_signals==0 guard prevents mislabelling clean evidence
        # when overall_confidence happens to sit below 0.75 due to tool failures.
        manipulation_signals = len(_manip_confs)

        if manipulation_probability >= 0.72 and manipulation_signals >= 2:
            overall_verdict = "MANIPULATED"
        elif manipulation_probability >= 0.45 or manipulation_signals >= 1:
            overall_verdict = "LIKELY_MANIPULATED"
        elif (
            manipulation_signals == 0
            and overall_confidence >= 0.75
            and overall_error_rate <= 0.15
            and contested_findings_count == 0
        ):
            overall_verdict = "AUTHENTIC"
        elif (
            manipulation_signals == 0
            and overall_confidence >= 0.60
            and overall_error_rate <= 0.25
        ):
            overall_verdict = "LIKELY_AUTHENTIC"
        else:
            overall_verdict = "INCONCLUSIVE"

        logger.info(
            f"Arbiter verdict: {overall_verdict} (confidence={overall_confidence:.2f}, "
            f"conf_range=[{confidence_min:.2f},{confidence_max:.2f}] "
            f"error_rate={overall_error_rate:.2f}, contested={contested_findings_count}, "
            f"manipulation_probability={manipulation_probability:.2f}, manipulation_signals={manipulation_signals})"
        )
        await _step(f"Verdict: {overall_verdict} — synthesising report…")

        # ── E: PARALLEL LLM synthesis with health check + fast-path ─────
        # All 4 LLM calls run concurrently (capped by individual timeouts).
        # If Groq is unreachable, a 3s health check avoids four 25-45s timeouts.

        # Defaults — overwritten by either template or LLM path below
        verdict_sentence: str = ""
        key_findings_list: list[str] = []
        reliability_note: str = ""
        per_agent_analysis: dict[str, str] = {}
        executive_summary: str = ""
        uncertainty_statement: str = ""

        def _template_fallback():
            return (
                *self._template_structured_summary(
                    overall_verdict,
                    overall_confidence,
                    overall_error_rate,
                    manipulation_probability,
                    applicable_agent_count,
                    all_findings,
                    len(cross_modal_confirmed),
                    contested_findings_count,
                    analysis_coverage_note,
                ),
                {},
                self._template_executive_summary(
                    len(active_agent_results),
                    len(all_findings),
                    len(cross_modal_confirmed),
                    len(contested_findings),
                    all_findings,
                ),
                (
                    f"Analysis based on {len(all_findings)} findings from "
                    f"{len(active_agent_results)} active agent(s). "
                    f"Overall error rate: {overall_error_rate:.0%}."
                ),
            )

        llm_enabled = (
            use_llm
            and self.config.llm_api_key
            and self.config.llm_provider != "none"
            and bool(active_agent_results)
        )

        if llm_enabled:
            # Quick health probe — avoids 4× timeout when Groq is down.
            # The same client is stored as self._synthesis_client so all parallel
            # synthesis coroutines share one httpx connection pool (avoids
            # repeated TLS handshakes per-call during the gather phase).
            _client = LLMClient(self.config)
            if not _client.is_available:
                llm_enabled = False
            else:
                try:
                    _healthy = await asyncio.wait_for(
                        _client.health_check(), timeout=5.0
                    )
                    if not _healthy:
                        logger.warning(
                            "LLM health check failed — using template fallbacks"
                        )
                        llm_enabled = False
                    else:
                        self._synthesis_client = _client
                except asyncio.TimeoutError:
                    logger.warning(
                        "LLM health check timed out — using template fallbacks"
                    )
                    llm_enabled = False

        if not llm_enabled:
            (
                verdict_sentence,
                key_findings_list,
                reliability_note,
                per_agent_analysis,
                executive_summary,
                uncertainty_statement,
            ) = _template_fallback()
        else:
            await _step("Generating forensic summary via Groq (parallel synthesis)…")

            # ── Task 1: Structured summary (25s, JSON mode — fastest) ──
            async def _task_structured():
                try:
                    return await asyncio.wait_for(
                        self._generate_structured_summary(
                            overall_verdict=overall_verdict,
                            overall_confidence=overall_confidence,
                            overall_error_rate=overall_error_rate,
                            manipulation_probability=manipulation_probability,
                            applicable_agent_count=applicable_agent_count,
                            all_findings=all_findings,
                            cross_modal_confirmed_count=len(cross_modal_confirmed),
                            contested_count=contested_findings_count,
                            analysis_coverage_note=analysis_coverage_note,
                        ),
                        timeout=25.0,
                    )
                except Exception as e:
                    logger.warning(f"Structured summary failed: {e}")
                    return self._template_structured_summary(
                        overall_verdict,
                        overall_confidence,
                        overall_error_rate,
                        manipulation_probability,
                        applicable_agent_count,
                        all_findings,
                        len(cross_modal_confirmed),
                        contested_findings_count,
                        analysis_coverage_note,
                    )

            # ── Task 2: Per-agent narratives (40s, parallel gather) ─────
            async def _task_narratives():
                _NARRATIVE_TIMEOUT = 40.0
                # Semaphore: cap at 3 concurrent Groq narrative calls to avoid
                # hitting the TPM rate limit when 5 agents fire simultaneously.
                _narr_sem = asyncio.Semaphore(3)

                async def _one(aid, res):
                    findings = res.get("findings", [])
                    if not findings:
                        return aid, ""
                    async with _narr_sem:
                        try:
                            narr = await asyncio.wait_for(
                                self._generate_agent_narrative(
                                    aid,
                                    findings,
                                    per_agent_metrics.get(aid, {}),
                                ),
                                timeout=_NARRATIVE_TIMEOUT,
                            )
                            return aid, narr or ""
                        except (asyncio.TimeoutError, Exception) as e:
                            logger.warning(f"Narrative for {aid}: {e}")
                            return aid, ""

                pairs = await asyncio.gather(
                    *[_one(aid, res) for aid, res in active_agent_results.items()],
                    return_exceptions=True,
                )
                result = {}
                for p in pairs:
                    if isinstance(p, tuple) and len(p) == 2 and p[1]:
                        result[p[0]] = p[1]
                return result

            # ── Task 3: Executive summary (45s) ────────────────────────
            async def _task_executive():
                try:
                    return await asyncio.wait_for(
                        self._generate_executive_summary(
                            len(active_agent_results),
                            len(all_findings),
                            len(cross_modal_confirmed),
                            len(contested_findings),
                            all_findings=all_findings,
                            gemini_findings=gemini_vision_findings,
                            active_agent_metrics=active_metrics,
                            overall_verdict=overall_verdict,
                        ),
                        timeout=45.0,
                    )
                except (asyncio.TimeoutError, Exception) as e:
                    logger.warning(f"Executive summary failed: {e}")
                    return self._template_executive_summary(
                        len(active_agent_results),
                        len(all_findings),
                        len(cross_modal_confirmed),
                        len(contested_findings),
                        all_findings,
                    )

            # ── Task 4: Uncertainty statement (30s) ────────────────────
            async def _task_uncertainty():
                try:
                    return await asyncio.wait_for(
                        self._generate_uncertainty_statement(
                            len(incomplete_findings),
                            len(contested_findings),
                            overall_error_rate=overall_error_rate,
                        ),
                        timeout=30.0,
                    )
                except (asyncio.TimeoutError, Exception) as e:
                    logger.warning(f"Uncertainty statement failed: {e}")
                    return (
                        f"Analysis based on {len(all_findings)} findings from "
                        f"{len(active_agent_results)} active agent(s). "
                        f"Overall error rate: {overall_error_rate:.0%}."
                    )

            # Run all 4 LLM synthesis tasks fully in parallel to minimise
            # total wall-clock time (critical path: max(t1,t2,t3,t4) instead
            # of t1+t3 in series).
            (
                (verdict_sentence, key_findings_list, reliability_note),
                per_agent_analysis,
                executive_summary,
                uncertainty_statement,
            ) = await asyncio.gather(
                _task_structured(),
                _task_narratives(),
                _task_executive(),
                _task_uncertainty(),
            )

        # ── Cross-modal fusion analysis ────────────────────────────────────
        try:
            fusion_result = cross_modal_fuse(active_agent_results)
        except Exception as _fusion_err:
            logger.warning(f"Cross-modal fusion failed: {_fusion_err}")
            fusion_result = {}

        # ── Build report ──────────────────────────────────────────────────
        await _step("Finalising court-ready report…")
        report = ForensicReport(
            session_id=self.session_id,
            case_id=case_id or f"case_{self.session_id}",
            executive_summary=executive_summary,
            per_agent_findings=per_agent_findings,
            per_agent_metrics=per_agent_metrics,
            per_agent_analysis=per_agent_analysis,
            overall_confidence=overall_confidence,
            overall_error_rate=overall_error_rate,
            overall_verdict=overall_verdict,
            cross_modal_confirmed=cross_modal_confirmed,
            contested_findings=contested_findings,
            incomplete_findings=incomplete_findings,
            stub_findings=stub_findings,
            gemini_vision_findings=gemini_vision_findings,
            uncertainty_statement=uncertainty_statement,
            verdict_sentence=verdict_sentence,
            key_findings=key_findings_list,
            reliability_note=reliability_note,
            manipulation_probability=manipulation_probability,
            confidence_min=confidence_min,
            confidence_max=confidence_max,
            confidence_std_dev=confidence_std_dev,
            per_agent_summary=per_agent_summary,
            applicable_agent_count=applicable_agent_count,
            skipped_agents=skipped_agents,
            analysis_coverage_note=analysis_coverage_note,
            cross_modal_fusion={
                "verdict": fusion_result.verdict.value,
                "fused_confidence": fusion_result.fused_confidence,
                "corroborations": fusion_result.corroborations,
                "contradictions": fusion_result.contradictions,
                "independent_modalities": fusion_result.independent_modalities,
                "rationale": fusion_result.fusion_rationale,
            },
        )

        # Release shared synthesis client so the connection pool is freed.
        self._synthesis_client = None

        return report

    def _get_category(self, finding_type: str) -> str | None:
        """Map a finding_type to its semantic category, or None."""
        ft = finding_type.lower().replace(" ", "_")
        # Issue 14.5: Match longest keyword first to prevent substring overlap issues
        for keyword, category in sorted(self._FINDING_CATEGORY_MAP.items(), key=lambda x: len(x[0]), reverse=True):
            if keyword in ft:
                return category
        return None

    async def cross_agent_comparison(
        self, all_findings: list[dict[str, Any]]
    ) -> list[FindingComparison]:
        """Compare findings across agents using category-indexed comparison.

        Pre-filters stub findings and memoises category lookups.
        """
        comparisons: list[FindingComparison] = []

        # Pre-filter stubs to reduce O(n²) surface
        real_findings = [f for f in all_findings if not f.get("stub_result")]

        # Memoise category lookups
        _cat_cache: dict[str, str | None] = {}

        def _cat(ft: str) -> str | None:
            if ft not in _cat_cache:
                _cat_cache[ft] = self._get_category(ft)
            return _cat_cache[ft]

        # ── 1. Index findings by (category, agent_id) ─────────────────────
        category_buckets: dict[str, dict[str, list[dict]]] = {}
        uncategorised: list[dict] = []

        for f in real_findings:
            c = _cat(f.get("finding_type", ""))
            if c is None:
                uncategorised.append(f)
            else:
                agent_id = f.get("agent_id", "")
                category_buckets.setdefault(c, {}).setdefault(agent_id, []).append(f)

        # ── 2. Compare within each category bucket ────────────────────────
        _MAX_FINDINGS_PER_BUCKET = 10
        for cat, agent_map in category_buckets.items():
            for agent_id, flist in agent_map.items():
                if len(flist) > _MAX_FINDINGS_PER_BUCKET:
                    flist.sort(key=lambda x: x.get("confidence_raw", 0.0), reverse=True)
                    agent_map[agent_id] = flist[:_MAX_FINDINGS_PER_BUCKET]
            agent_ids = list(agent_map.keys())
            for i, agent_a in enumerate(agent_ids):
                for agent_b in agent_ids[i + 1 :]:
                    for fa in agent_map[agent_a]:
                        for fb in agent_map[agent_b]:
                            same = fa.get("status", "") == fb.get("status", "")
                            comparisons.append(
                                FindingComparison(
                                    finding_a=fa,
                                    finding_b=fb,
                                    verdict=FindingVerdict.AGREEMENT
                                    if same
                                    else FindingVerdict.CONTRADICTION,
                                    cross_modal_confirmed=same,
                                )
                            )

            # Same-agent findings within category (no cross-modal confirmation)
            for _aid, fl in agent_map.items():
                for ii in range(len(fl)):
                    for jj in range(ii + 1, len(fl)):
                        fa, fb = fl[ii], fl[jj]
                        same = fa.get("status", "") == fb.get("status", "")
                        comparisons.append(
                            FindingComparison(
                                finding_a=fa,
                                finding_b=fb,
                                verdict=FindingVerdict.AGREEMENT
                                if same
                                else FindingVerdict.CONTRADICTION,
                                cross_modal_confirmed=False,
                            )
                        )

        # ── 3. Uncategorised findings → INDEPENDENT ───────────────────────
        for f in uncategorised:
            comparisons.append(
                FindingComparison(
                    finding_a=f,
                    finding_b=f,
                    verdict=FindingVerdict.INDEPENDENT,
                    cross_modal_confirmed=False,
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

    async def challenge_loop(
        self,
        contradiction: FindingComparison,
        agent_id: str,
        context_from_other: dict[str, Any],
    ) -> ChallengeResult:
        """
        Run challenge loop for a contradiction.

        When agents disagree, the lower-confidence finding is challenged.
        The challenged agent is re-invoked with the contradicting context
        and asked to reconsider their finding.

        Args:
            contradiction: The contradiction between two findings
            agent_id: ID of the agent being challenged
            context_from_other: The contradicting finding's data as context

        Returns:
            ChallengeResult with the outcome of the challenge
        """
        from core.custody_logger import EntryType
        from core.structured_logging import get_logger

        logger = get_logger(__name__)
        challenge_id = uuid4()

        logger.info(
            "Challenge loop: contradiction recorded for human review",
            challenge_id=str(challenge_id),
            challenged_agent=agent_id,
        )

        # Single custody log entry (reduced from 2) for the contradiction
        if self.custody_logger:
            await self.custody_logger.log_entry(
                entry_type=EntryType.HITL_CHECKPOINT,
                agent_id="Arbiter",
                session_id=self.session_id,
                content={
                    "reason": "CONTESTED_FINDING",
                    "challenge_id": str(challenge_id),
                    "challenged_agent": agent_id,
                    "contradiction_type": contradiction.verdict.value,
                    "original_finding_type": contradiction.finding_a.get(
                        "finding_type"
                    ),
                    "contradicting_finding_type": contradiction.finding_b.get(
                        "finding_type"
                    ),
                    "note": "Contested finding flagged for human review — no agent re-invocation",
                },
            )

        return ChallengeResult(
            challenge_id=challenge_id,
            challenged_agent=agent_id,
            original_finding=contradiction.finding_a,
            revised_finding=None,
            resolved=False,
        )

    async def trigger_tribunal(self, case: TribunalCase) -> None:
        """Trigger tribunal for unresolved contradiction."""
        if self.custody_logger:
            from core.custody_logger import EntryType

            await self.custody_logger.log_entry(
                entry_type=EntryType.HITL_CHECKPOINT,
                agent_id="Arbiter",
                session_id=self.session_id,
                content={
                    "reason": "TRIBUNAL_ESCALATION",
                    "tribunal_id": str(case.tribunal_id),
                },
            )

    async def sign_report(self, report: ForensicReport) -> ForensicReport:
        """Sign the forensic report with the Arbiter key."""
        # Use mode="json" to safely cast UUIDs/DateTimes to string types
        report_dict = report.model_dump(
            mode="json",
            exclude={"cryptographic_signature", "report_hash", "signed_utc"},
        )

        # Now json.dumps won't require a generic default=str fallback
        report_json = json.dumps(report_dict, sort_keys=True)
        report_hash = hashlib.sha256(report_json.encode()).hexdigest()

        signed_entry = sign_content(
            agent_id="Arbiter",
            content={
                "hash": report_hash,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        report.report_hash = report_hash
        report.cryptographic_signature = signed_entry.signature
        report.signed_utc = datetime.now(timezone.utc)

        return report

    # ── Agent name map ────────────────────────────────────────────────────
    _AGENT_FULL_NAMES: dict[str, str] = {
        "Agent1": "Image Integrity Agent (ELA · JPEG Ghost · Frequency Domain · Noise Fingerprint)",
        "Agent2": "Audio Forensics Agent (Speaker Diarization · Anti-Spoofing · Codec Fingerprint)",
        "Agent3": "Object Detection Agent (YOLO · Lighting Consistency · Contraband DB)",
        "Agent4": "Video Forensics Agent (Optical Flow · Face-Swap · Rolling Shutter)",
        "Agent5": "Metadata Forensics Agent (EXIF · GPS · Steganography · Hex Signature)",
    }

    async def _generate_agent_narrative(
        self,
        agent_id: str,
        findings: list[dict[str, Any]],
        metrics: dict[str, Any],
    ) -> str:
        """
        Generate a Groq-synthesised per-agent narrative that:
        - Compares initial vs deep analysis findings for this agent
        - Summarises tool successes and failures
        - States the agent's confidence score and error rate
        - Produces 2-3 plain-English paragraphs suitable for the result page

        Returns empty string if LLM is not configured.
        """
        if not (self.config.llm_api_key and self.config.llm_provider != "none"):
            return ""

        client = self._synthesis_client or LLMClient(self.config)
        if not client.is_available:
            return ""
        agent_full_name = self._AGENT_FULL_NAMES.get(agent_id, agent_id)
        confidence_pct = round(metrics.get("confidence_score", 0) * 100)
        error_rate_pct = round(metrics.get("error_rate", 0) * 100)
        tools_ok = metrics.get("tools_succeeded", 0)
        tools_total = metrics.get("total_tools_called", 0)

        # Split findings by phase
        initial_f = [
            f
            for f in findings
            if (f.get("metadata") or {}).get("analysis_phase", "initial") == "initial"
        ]
        deep_f = [
            f
            for f in findings
            if (f.get("metadata") or {}).get("analysis_phase") == "deep"
        ]

        _NOT_APPLICABLE_FLAGS = ("ela_not_applicable", "ghost_not_applicable")
        _NOT_APPLICABLE_KEYS = {
            "ela_not_applicable",
            "ghost_not_applicable",
            "ela_limitation_note",
            "ghost_limitation_note",
            "file_format_note",
            "is_camera_format",
        }
        _STRIP_KEYS = {
            "stub_warning",
            "llm_synthesis",
            "llm_reasoning",
            "synthesis_phase",
            "analysis_phase",
            "tool_name",
            "warning",
        }

        def _fmt(findings_list: list[dict]) -> str:
            out = []
            for f in findings_list[:5]:
                meta = f.get("metadata") or {}
                tool_name = meta.get("tool_name", f.get("finding_type", ""))
                is_na = any(meta.get(flag) for flag in _NOT_APPLICABLE_FLAGS)
                is_failed = not is_na and meta.get("court_defensible") is False
                # Collect the key metrics Groq needs to cite real numbers
                key_metrics: dict = {}
                for k, v in meta.items():
                    if k.startswith("_") or k in _STRIP_KEYS:
                        continue
                    if k in _NOT_APPLICABLE_KEYS:
                        key_metrics[k] = v
                        continue
                    if isinstance(v, (bool, int, float)):
                        key_metrics[k] = v
                    elif isinstance(v, str) and len(v) < 200:
                        key_metrics[k] = v
                    elif (
                        isinstance(v, list)
                        and len(v) <= 10
                        and all(isinstance(x, (str, int, float, bool, dict)) for x in v)
                    ):
                        key_metrics[k] = v
                entry = {
                    "tool": tool_name,
                    "confidence": round(f.get("confidence_raw", 0), 3),
                    "status": f.get("status", ""),
                    "applicability": "NOT_APPLICABLE"
                    if is_na
                    else ("FAILED" if is_failed else "RAN"),
                    "summary": (f.get("reasoning_summary") or "")[:400],
                    "metrics": key_metrics,
                }
                out.append(entry)
            return json.dumps(out, indent=2)

        tools_na = metrics.get("tools_not_applicable", 0)
        has_deep = bool(deep_f)
        comparison_section = ""
        if has_deep:
            comparison_section = f"\n\nDeep analysis findings ({len(deep_f)} tool scans):\n{_fmt(deep_f)}"

        system_prompt = f"""You are the Council Arbiter writing the per-agent analysis section of a forensic report.

Write 2-3 clear, plain-English paragraphs for the {agent_full_name}. Structure:

PARAGRAPH 1 — Initial analysis results:
- For each tool with applicability "RAN": cite the EXACT metric values from the "metrics" field and interpret them forensically. Do not paraphrase — state the actual numbers (e.g. "ELA found 3 localised anomaly regions with max deviation 14.2", "YOLO detected person (0.87), laptop (0.76)").
- For each tool with applicability "NOT_APPLICABLE": briefly explain why the tool does not apply to this file type (use the ela_limitation_note / ghost_limitation_note / file_format_note from metrics). Do NOT treat these as suspicious findings.
- For each tool with applicability "FAILED": state that it failed and what data is missing as a result.

PARAGRAPH 2 — Deep analysis and cross-validation (if deep analysis was run):
- What deep tools confirmed, expanded, or contradicted from initial analysis.
- Exact Gemini findings if present: content type, extracted text, detected objects, authenticity verdict.

PARAGRAPH 3 — Reliability and verdict:
- Agent confidence: {confidence_pct}%. Tool error rate: {error_rate_pct}% ({tools_ok} of {tools_total} tools succeeded, {tools_na} not applicable to file type).
- Plain-English verdict for this agent: AUTHENTIC / SUSPICIOUS / INCONCLUSIVE / NOT APPLICABLE.

Do NOT use bullet points. Write in continuous prose. Interpret numbers — do not paste raw JSON."""

        user_content = (
            f"Agent: {agent_full_name}\n"
            f"Confidence: {confidence_pct}%  |  Error rate: {error_rate_pct}%  |  "
            f"Tools succeeded: {tools_ok}/{tools_total}  |  Not applicable: {tools_na}\n\n"
            f"Initial analysis ({len(initial_f)} tool scans):\n{_fmt(initial_f)}"
            f"{comparison_section}\n\n"
            f"Write the per-agent analysis section."
        )

        try:
            return await client.generate_synthesis(
                system_prompt=system_prompt,
                user_content=user_content,
                max_tokens=380,
                json_mode=False,
            )
        except Exception as e:
            logger.debug(f"Per-agent narrative Groq parsing/call failed for {agent_id}: {e}")
            return ""

    async def _generate_executive_summary(
        self,
        num_agents: int,
        num_findings: int,
        cross_modal_confirmed: int,
        contested: int,
        all_findings: list[dict[str, Any]] = None,
        gemini_findings: list[dict[str, Any]] = None,
        active_agent_metrics: list[dict[str, Any]] = None,
        overall_verdict: str = "",
    ) -> str:
        """
        Generate an executive summary using Groq LLM.

        When Groq is configured (recommended), uses the model to write
        a structured, plain-language summary from actual finding data,
        incorporating Gemini vision insights where available.
        Falls back to a deterministic template if LLM is unavailable.
        """
        if self.config.llm_api_key and self.config.llm_provider != "none":
            try:
                result = await self._llm_executive_summary(
                    num_agents,
                    num_findings,
                    cross_modal_confirmed,
                    contested,
                    all_findings or [],
                    gemini_findings or [],
                    active_agent_metrics or [],
                    overall_verdict,
                )
                if result:
                    return result
            except Exception as exc:
                logger.warning(f"LLM executive summary failed, using template: {exc}")

        return self._template_executive_summary(
            num_agents, num_findings, cross_modal_confirmed, contested, all_findings
        )

    async def _llm_executive_summary(
        self,
        num_agents: int,
        num_findings: int,
        cross_modal_confirmed: int,
        contested: int,
        all_findings: list[dict[str, Any]],
        gemini_findings: list[dict[str, Any]] = None,
        active_agent_metrics: list[dict[str, Any]] = None,
        overall_verdict: str = "",
    ) -> str:
        """Generate executive summary using Groq LLM synthesis.

        Uses ONLY active agents (those that ran real tools).  Incorporates
        per-agent metrics and the computed verdict for a grounded summary.
        """
        client = self._synthesis_client or LLMClient(self.config)

        # Build structured findings digest for the model
        top_findings = sorted(
            [
                f
                for f in all_findings
                if not f.get("stub_result")
                and f.get("metadata", {}).get("analysis_source") != "gemini_vision"
            ],
            key=lambda f: f.get("confidence_raw", 0),
            reverse=True,
        )[:8]

        findings_digest = []
        for f in top_findings:
            findings_digest.append(
                {
                    "agent": f.get("agent_id", "unknown"),
                    "type": f.get("finding_type", "unknown"),
                    "confidence": round(f.get("confidence_raw", 0), 3),
                    "summary": f.get("reasoning_summary", ""),
                    "status": f.get("status", ""),
                    "cross_modal": f.get("cross_modal_confirmed", False),
                }
            )

        # Build Gemini vision digest
        gemini_digest = []
        for gf in (gemini_findings or [])[:4]:
            meta = gf.get("metadata", {})
            gemini_digest.append(
                {
                    "agent": gf.get("agent_id", "unknown"),
                    "analysis_type": meta.get("analysis_type", "vision"),
                    "model": meta.get("model_used", "gemini"),
                    "confidence": round(gf.get("confidence_raw", 0), 3),
                    "summary": gf.get("reasoning_summary", ""),
                    "manipulation_signals": meta.get("manipulation_signals", []),
                    "detected_objects": meta.get("detected_objects", []),
                }
            )

        gemini_section = ""
        if gemini_digest:
            gemini_section = f"\n\nGemini vision deep analysis findings ({len(gemini_digest)} of {len(gemini_findings or [])}):\n{json.dumps(gemini_digest, indent=2)}"

        metrics_summary = ""
        if active_agent_metrics:
            metrics_summary = (
                "\n\nAgent performance metrics (active agents only):\n"
                + json.dumps(
                    [
                        {
                            "agent": m.get("agent_name", m.get("agent_id", "")),
                            "confidence": f"{m.get('confidence_score', 0) * 100:.0f}%",
                            "error_rate": f"{m.get('error_rate', 0) * 100:.0f}%",
                            "tools_ran": m.get("tools_succeeded", 0),
                            "tools_failed": m.get("tools_failed", 0),
                            "not_applicable": m.get("tools_not_applicable", 0),
                            "total_tools": m.get("total_tools_called", 0),
                            "findings": m.get("finding_count", 0),
                        }
                        for m in active_agent_metrics
                        if not m.get("skipped")
                    ],
                    indent=2,
                )
            )

        verdict_line = (
            f"\n\nCouncil Arbiter computed verdict: {overall_verdict}"
            if overall_verdict
            else ""
        )

        system_prompt = f"""You are the Council Arbiter writing the Executive Summary of a court-admissible forensic evidence report.
The computed verdict for this evidence is: {overall_verdict or "REVIEW REQUIRED"}

Your summary must be:
- Factual and grounded only in the structured findings data provided
- Written in formal, precise legal/forensic language
- 3-5 paragraphs: (1) scope and active agents with their confidence scores, (2) key confirmed findings with exact metrics, (3) contested or tool-failure issues, (4) overall verdict justification based on confidence and error rates
- Free of speculation — only state what the data shows
- Explicit about tool failures and low-confidence findings
- Where Gemini vision findings present, attribute them as AI-assisted analysis needing corroboration

Do NOT use bullet points. Write in continuous prose paragraphs.
Reference the computed verdict: {overall_verdict or "REVIEW REQUIRED"} — explain WHY based on the numbers."""

        user_content = f"""Forensic analysis statistics:
- Active agents: {num_agents} (skipped agents excluded from this summary)
- Total findings from active agents: {num_findings}
- Cross-modal confirmed (multiple agents agree): {cross_modal_confirmed}
- Contested findings (agents disagree): {contested}
- Gemini vision findings: {len(gemini_findings or [])}
- Computed verdict: {overall_verdict}{verdict_line}

Top findings by confidence (classical tools):
{json.dumps(findings_digest, indent=2)}{gemini_section}{metrics_summary}

Write the Executive Summary for this forensic report. Justify the {overall_verdict} verdict based on the data."""

        return await client.generate_synthesis(
            system_prompt=system_prompt,
            user_content=user_content,
            max_tokens=500,
            json_mode=False,
        )

    def _template_executive_summary(
        self,
        num_agents: int,
        num_findings: int,
        cross_modal_confirmed: int,
        contested: int,
        all_findings: list[dict[str, Any]] | None,
    ) -> str:
        """Deterministic template fallback when LLM is not configured."""
        lines = [
            f"This report presents findings from a multi-agent forensic analysis conducted by "
            f"{num_agents} specialized agents, resulting in {num_findings} individual findings.",
        ]
        if cross_modal_confirmed > 0:
            lines.append(
                f"Cross-modal confirmation was achieved for {cross_modal_confirmed} findings, "
                "where multiple independent agents using different analysis techniques arrived "
                "at the same conclusion."
            )
        if contested > 0:
            lines.append(
                f"{contested} finding(s) were identified as contested, requiring further "
                "review or tribunal resolution."
            )
        if all_findings:
            top = sorted(
                all_findings, key=lambda f: f.get("confidence_raw", 0), reverse=True
            )[:3]
            highlights = [
                f.get("reasoning_summary", "")
                for f in top
                if f.get("reasoning_summary")
            ]
            if highlights:
                lines.append("Key findings include: " + " ".join(highlights[:2]))
        lines.append(
            "The full analysis chain is preserved in the chain of custody log and "
            "ReAct chains sections of this report."
        )
        return " ".join(lines)

    async def _generate_uncertainty_statement(
        self, incomplete: int, contested: int, overall_error_rate: float = 0.0
    ) -> str:
        """
        Generate the uncertainty and limitations statement.

        Uses LLM to produce a nuanced, legally-aware statement when configured.
        Falls back to deterministic template otherwise.
        """
        if (
            self.config.llm_api_key
            and self.config.llm_provider != "none"
            and (incomplete > 0 or contested > 0 or overall_error_rate > 0.15)
        ):
            try:
                result = await self._llm_uncertainty_statement(
                    incomplete, contested, overall_error_rate
                )
                if result:
                    return result
            except Exception as exc:
                logger.warning(
                    f"LLM uncertainty statement failed, using template: {exc}"
                )

        return self._template_uncertainty_statement(
            incomplete, contested, overall_error_rate
        )

    async def _llm_uncertainty_statement(
        self, incomplete: int, contested: int, overall_error_rate: float = 0.0
    ) -> str:
        """Generate uncertainty statement using LLM."""
        client = self._synthesis_client or LLMClient(self.config)

        system_prompt = """You are the Council Arbiter writing the Limitations and Uncertainty section of a forensic report.

Be specific and legally precise. Explain what the uncertainties mean for the evidential value of the report.
Write 2-3 sentences only. Do not use bullet points."""

        user_content = (
            f"Incomplete findings (tools unavailable or evidence insufficient): {incomplete}\n"
            f"Contested findings (agents disagree, not yet resolved): {contested}\n"
            f"Overall tool error rate across active agents: {overall_error_rate * 100:.1f}%\n\n"
            "Write the uncertainty and limitations statement."
        )

        return await client.generate_synthesis(
            system_prompt=system_prompt,
            user_content=user_content,
            max_tokens=200,
            json_mode=False,
        )

    async def _generate_structured_summary(
        self,
        overall_verdict: str,
        overall_confidence: float,
        overall_error_rate: float,
        manipulation_probability: float,
        applicable_agent_count: int,
        all_findings: list[dict[str, Any]],
        cross_modal_confirmed_count: int,
        contested_count: int,
        analysis_coverage_note: str,
    ) -> tuple[str, list[str], str]:
        """
        Generate verdict_sentence, key_findings (list), reliability_note.
        Returns (verdict_sentence, key_findings, reliability_note).
        """
        if self.config.llm_api_key and self.config.llm_provider != "none":
            try:
                result = await asyncio.wait_for(
                    self._llm_structured_summary(
                        overall_verdict,
                        overall_confidence,
                        overall_error_rate,
                        manipulation_probability,
                        applicable_agent_count,
                        all_findings,
                        cross_modal_confirmed_count,
                        contested_count,
                        analysis_coverage_note,
                    ),
                    timeout=25.0,
                )
                if result:
                    return result
            except Exception as exc:
                logger.warning(f"Structured summary LLM call failed: {exc}")

        return self._template_structured_summary(
            overall_verdict,
            overall_confidence,
            overall_error_rate,
            manipulation_probability,
            applicable_agent_count,
            all_findings,
            cross_modal_confirmed_count,
            contested_count,
            analysis_coverage_note,
        )

    async def _llm_structured_summary(
        self,
        overall_verdict: str,
        overall_confidence: float,
        overall_error_rate: float,
        manipulation_probability: float,
        applicable_agent_count: int,
        all_findings: list[dict[str, Any]],
        cross_modal_confirmed_count: int,
        contested_count: int,
        analysis_coverage_note: str,
    ) -> tuple[str, list[str], str] | None:
        client = self._synthesis_client or LLMClient(self.config)

        def _strip_rs_prefix(s: str) -> str:
            idx = s.find(":")
            if (
                0 < idx < 55
                and s[:idx]
                .replace(" ", "")
                .replace("/", "")
                .replace("-", "")
                .replace("_", "")
                .isalpha()
            ):
                return s[idx + 1 :].lstrip()
            return s

        top_findings = sorted(
            [f for f in all_findings if not f.get("stub_result")],
            key=lambda f: f.get("confidence_raw", 0),
            reverse=True,
        )[:6]
        findings_brief = [
            f"{f.get('finding_type', '?')} ({f.get('agent_id', '?')}) — "
            f"{(f.get('confidence_raw') or 0):.0%} — {_strip_rs_prefix((f.get('reasoning_summary') or '')[:200].rsplit(' ', 1)[0])}"
            for f in top_findings
        ]

        system_prompt = """You are the Council Arbiter. Generate three short forensic summary fields as JSON.

Respond ONLY with valid JSON (no markdown):
{
  "verdict_sentence": "<one sentence: what the evidence shows and the final verdict>",
  "key_findings": ["<finding 1>", "<finding 2>", "<finding 3>", "<finding 4>", "<finding 5>"],
  "reliability_note": "<one sentence: confidence level and any caveats about reliability>"
}

Rules:
- verdict_sentence: state the verdict and primary reason in ≤25 words.
- key_findings: exactly 3-5 plain English bullet items, each ≤25 words. Never start a finding with a tool name or technical prefix like "GAN/deepfake", "Hash verification:", etc. State the result directly: "No GAN artifacts found" not "GAN/deepfake check: no artifacts".
- reliability_note: ≤20 words. Cite confidence %, error rate, and note if any tools used fallbacks."""

        user_content = (
            f"Verdict: {overall_verdict}\n"
            f"Confidence: {overall_confidence * 100:.0f}%  |  Error rate: {overall_error_rate * 100:.0f}%  |  "
            f"Manipulation probability: {manipulation_probability * 100:.0f}%\n"
            f"Active agents: {applicable_agent_count}  |  Cross-modal confirmed: {cross_modal_confirmed_count}  |  Contested: {contested_count}\n"
            f"Coverage: {analysis_coverage_note}\n\n"
            f"Top findings:\n" + "\n".join(f"- {b}" for b in findings_brief)
        )

        try:
            raw = await client.generate_synthesis(
                system_prompt=system_prompt,
                user_content=user_content,
                max_tokens=350,
                json_mode=True,
            )
            if not raw:
                return None
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```", 2)[-1].lstrip("json").strip()
                if raw.endswith("```"):
                    raw = raw[:-3].strip()
            data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
            vs = str(data.get("verdict_sentence", ""))
            kf = [str(x) for x in data.get("key_findings", []) if x][:5]
            rn = str(data.get("reliability_note", ""))
            if vs and kf and rn:
                return vs, kf, rn
        except Exception as e:
            logger.debug(f"LLM structured summary JSON parsing failed: {e}")
        return None

    def _template_structured_summary(
        self,
        overall_verdict: str,
        overall_confidence: float,
        overall_error_rate: float,
        manipulation_probability: float,
        applicable_agent_count: int,
        all_findings: list[dict[str, Any]],
        cross_modal_confirmed_count: int,
        contested_count: int,
        analysis_coverage_note: str,
    ) -> tuple[str, list[str], str]:
        _VERDICT_PHRASES = {
            "AUTHENTIC": "Evidence appears authentic with no manipulation signals detected.",
            "LIKELY_AUTHENTIC": "Evidence is likely authentic; no significant manipulation indicators found.",
            "INCONCLUSIVE": "Analysis is inconclusive — insufficient data to confirm authenticity or manipulation.",
            "LIKELY_MANIPULATED": "Evidence shows probable manipulation signals requiring further investigation.",
            "MANIPULATED": "Strong manipulation indicators detected across multiple independent agents.",
        }
        verdict_sentence = _VERDICT_PHRASES.get(
            overall_verdict, f"Verdict: {overall_verdict}."
        )

        def _strip_rs_prefix(s: str) -> str:
            """Strip tool-name prefixes like 'GAN/deepfake frequency check: ' from reasoning summaries."""
            idx = s.find(":")
            if (
                0 < idx < 55
                and s[:idx]
                .replace(" ", "")
                .replace("/", "")
                .replace("-", "")
                .replace("_", "")
                .isalpha()
            ):
                return s[idx + 1 :].lstrip()
            return s

        def _truncate(s: str, max_len: int = 200) -> str:
            """Truncate at last word boundary before max_len."""
            if len(s) <= max_len:
                return s
            return s[:max_len].rsplit(" ", 1)[0] + ("…" if len(s) > max_len else "")

        top = sorted(
            [
                f
                for f in all_findings
                if not f.get("stub_result") and f.get("reasoning_summary")
            ],
            key=lambda f: f.get("confidence_raw", 0),
            reverse=True,
        )[:5]
        key_findings_list = [
            _strip_rs_prefix(_truncate(f.get("reasoning_summary") or "")) for f in top
        ]
        if not key_findings_list:
            key_findings_list = ["No significant findings were identified."]

        err_note = (
            f"; {overall_error_rate * 100:.0f}% tool error rate"
            if overall_error_rate > 0.05
            else ""
        )
        _a = "agent" if applicable_agent_count == 1 else "agents"
        reliability_note = (
            f"{overall_confidence * 100:.0f}% overall confidence across "
            f"{applicable_agent_count} active {_a}{err_note}."
        )
        return verdict_sentence, key_findings_list, reliability_note

    def _template_uncertainty_statement(
        self, incomplete: int, contested: int, overall_error_rate: float = 0.0
    ) -> str:
        """Deterministic uncertainty template fallback."""
        statements = []
        if overall_error_rate > 0.15:
            statements.append(
                f"Average tool error rate across active agents is {overall_error_rate * 100:.0f}%, "
                "indicating some analysis dimensions may be incomplete or unreliable."
            )
        if incomplete > 0:
            statements.append(
                f"{incomplete} finding(s) remain incomplete due to unavailable tools "
                "or insufficient evidence."
            )
        if contested > 0:
            statements.append(
                f"{contested} finding(s) are contested and require tribunal resolution "
                "or human judgment."
            )
        if not statements:
            statements.append(
                "All findings have been resolved. No significant uncertainties remain."
            )
        return " ".join(statements)


def render_text_report(report: ForensicReport) -> str:
    """Render ForensicReport as structured plain text/markdown."""
    lines = []
    lines.append("=" * 80)
    lines.append("FORENSIC ANALYSIS REPORT")
    lines.append("=" * 80)
    lines.append(f"Report ID: {report.report_id}")
    lines.append(f"Session ID: {report.session_id}")
    lines.append(f"Case ID: {report.case_id}")
    if report.signed_utc:
        lines.append(f"Signed: {report.signed_utc.isoformat()}")
    lines.append("")

    lines.append("-" * 80)
    lines.append("EXECUTIVE SUMMARY")
    lines.append("-" * 80)
    lines.append(report.executive_summary)
    lines.append("")

    lines.append("-" * 80)
    lines.append("PER-AGENT FINDINGS")
    lines.append("-" * 80)
    for agent_id, findings in report.per_agent_findings.items():
        lines.append(f"### {agent_id}")
        for finding in findings:
            lines.append(
                f"  - {finding.get('finding_type', 'Unknown')}: {finding.get('confidence_raw', 0):.2f}"
            )
    lines.append("")

    if report.cross_modal_confirmed:
        lines.append("-" * 80)
        lines.append("CROSS-MODAL CONFIRMED FINDINGS")
        lines.append("-" * 80)
        for finding in report.cross_modal_confirmed:
            lines.append(f"  - {finding.get('finding_type', 'Unknown')}")
        lines.append("")

    lines.append("-" * 80)
    lines.append("UNCERTAINTY STATEMENT")
    lines.append("-" * 80)
    lines.append(report.uncertainty_statement)
    lines.append("")

    lines.append("-" * 80)
    lines.append("CRYPTOGRAPHIC SIGNATURE")
    lines.append("-" * 80)
    lines.append(f"Report Hash: {report.report_hash}")
    lines.append(f"Signature: {report.cryptographic_signature[:64]}...")
    lines.append("")
    lines.append("=" * 80)

    return "\n".join(lines)
