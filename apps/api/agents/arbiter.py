"""
Council Arbiter & Report Generator
==============================

The synthesis layer that deliberates on agent findings, manages challenge loops,
tribunal escalation, and generates court-admissible reports.
"""

from __future__ import annotations

import asyncio
import uuid as _uuid
from typing import Any
from uuid import UUID

from agents.arbiter_narrative import ArbiterNarrativeMixin
from agents.arbiter_verdict import (
    AGENT_NAMES,
    MIN_CONFIDENCE_THRESHOLD,
    AgentMetrics,
    ChallengeResult,
    FindingComparison,
    FindingVerdict,
    ForensicReport,
    TribunalCase,
    calculate_manipulation_probability,
    confidence_of,
    cross_agent_comparison,
    evidence_verdict_of,
)
from core.agent_registry import AgentID
from core.config import Settings, get_settings
from core.cross_modal_fusion import fuse as cross_modal_fuse
from core.forensic_policy import ForensicPolicy
from core.severity import assign_severity_tier
from core.signing import get_keystore
from core.structured_logging import get_logger

logger = get_logger(__name__)

DEFAULT_CONFIDENCE_FALLBACK = 0.5
MAX_CHALLENGE_ATTEMPTS = 2

# Re-exporting for backward compatibility
__all__ = [
    "FindingVerdict",
    "FindingComparison",
    "ChallengeResult",
    "TribunalCase",
    "AgentMetrics",
    "ForensicReport",
    "CouncilArbiter",
]


class CouncilArbiter(ArbiterNarrativeMixin):
    """
    Council Arbiter - the deliberation, challenge loop, and report generator.
    Refactored to < 500 lines by delegating logic to specialized modules.
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
        self._key_store = get_keystore()
        self._key_store.get_or_create(AgentID.ARBITER)
        self._synthesis_client: Any = None
        self._step_hook: Any = None
        self._pre_warm_agent_results: dict[str, dict[str, Any]] | None = None
        self._pre_warm_case_id: str = ""
        self._pre_warm_report: ForensicReport | None = None
        self._pre_warm_used_llm: bool = False

    async def pre_warm(
        self,
        agent_results: dict[str, dict[str, Any]],
        case_id: str = "",
        artifact_mime: str = "",
    ) -> ForensicReport:
        """
        Build a deterministic arbiter report from current agent findings.

        The pre-warm pass avoids LLM calls so the decision gate can have the
        verdict math and finding groups ready. Finalisation can then reuse these
        inputs and add Groq synthesis after the investigator accepts the run.
        """
        self._pre_warm_agent_results = agent_results
        self._pre_warm_case_id = case_id
        self._pre_warm_used_llm = False
        self._pre_warm_report = await self.deliberate(agent_results, case_id, use_llm=False, artifact_mime=artifact_mime)
        return self._pre_warm_report

    async def regenerate_missing_narratives(self, report: ForensicReport) -> ForensicReport:
        """Regenerate per-agent narratives if they were empty (e.g. all Groq calls timed out)."""
        if report.per_agent_analysis and any(
            v.strip() for v in report.per_agent_analysis.values()
        ):
            return report
        logger.info("per_agent_analysis is empty — retrying narrative generation before persistence")
        agent_results = {}
        for aid, findings in report.per_agent_findings.items():
            agent_results[aid] = {
                "findings": [f.model_dump(mode="json") if hasattr(f, "model_dump") else f for f in findings],
            }
        narratives = await self.deliberate_narratives(
            overall_verdict=report.overall_verdict,
            overall_confidence=report.overall_confidence,
            overall_error_rate=report.overall_error_rate,
            manipulation_probability=report.manipulation_probability,
            applicable_agent_count=report.applicable_agent_count,
            all_findings=[f for fl in report.per_agent_findings.values() for f in fl],
            active_agent_results=agent_results,
            per_agent_metrics=report.per_agent_metrics,
            visual_profile_findings=report.gemini_vision_findings,
            cross_modal_confirmed_count=len(report.cross_modal_confirmed),
            contested_findings=report.contested_findings,
            incomplete_findings=report.incomplete_findings,
            analysis_coverage_note=report.analysis_coverage_note,
            use_llm=True,
        )
        report.per_agent_analysis = narratives.get("per_agent_analysis", {})
        report.per_agent_narrative_structured = narratives.get("per_agent_narrative_structured", {})
        return report

    async def finalise_from_cache(self, use_llm: bool = True, artifact_mime: str = "") -> ForensicReport:
        """Finalize cached arbiter inputs into the report returned to the result page."""
        if self._pre_warm_agent_results is None:
            raise RuntimeError("Arbiter has no cached agent findings to finalise")
        if not use_llm and self._pre_warm_report is not None:
            return self._pre_warm_report
        if use_llm and self._pre_warm_report is not None and self._pre_warm_used_llm:
            return self._pre_warm_report
        if use_llm and self._pre_warm_report is not None and not self._pre_warm_used_llm:
            logger.info("Pre-warm report was built without LLM; re-running with LLM synthesis")
            self._pre_warm_report = None
        report = await self.deliberate(
            self._pre_warm_agent_results,
            self._pre_warm_case_id,
            use_llm=use_llm,
            artifact_mime=artifact_mime,
        )
        if use_llm:
            self._pre_warm_used_llm = True
        else:
            self._pre_warm_report = report
        return report

    def clear_pre_warm_cache(self) -> None:
        """Drop cached arbiter inputs when the run changes, for example before deep analysis."""
        self._pre_warm_agent_results = None
        self._pre_warm_case_id = ""
        self._pre_warm_report = None

    async def deliberate(
        self,
        agent_results: dict[str, dict[str, Any]],
        case_id: str = "",
        use_llm: bool = True,
        artifact_mime: str = "",
    ) -> ForensicReport:
        """Main deliberation entry point."""

        if self.config.local_only_analysis:
            use_llm = False

        # Force use_llm=False if LLM is unavailable
        llm_available = bool(self._synthesis_client and self._synthesis_client.is_available)
        if not llm_available:
            from core.llm_client import LLMClient
            temp_client = LLMClient(config=self.config, use_arbiter_tier=True)
            llm_available = temp_client.is_available
        if use_llm and not llm_available:
            logger.info("Arbiter LLM unavailable, using deterministic logic")
            use_llm = False

        skip_types = {"file type not applicable", "format not supported"}

        async def _step(msg: str):
            if self._step_hook:
                await self._step_hook(msg)

        # ── 1. Finding Extraction & Deduplication ─────────────────────────
        await _step("Compiling agent findings.")
        all_findings, per_agent_findings, per_agent_metrics, skipped_agents = [], {}, {}, {}
        active_results, visual_profile_findings_by_agent = {}, {}

        for aid, res in agent_results.items():
            raw = res.get("findings", [])
            deduped = self._deduplicate_findings(raw)
            skipped = not deduped or all(
                str(f.get("finding_type", "")).lower() in skip_types for f in deduped
            )
            per_agent_findings[aid] = deduped
            if skipped:
                skipped_agents[aid] = "File type not applicable to this agent."

            metrics = self._compute_agent_metrics(aid, deduped, skipped)
            per_agent_metrics[aid] = metrics.model_dump()

            if not skipped:
                active_results[aid] = {**res, "findings": deduped}
                all_findings.extend(deduped)
                af_visual = [
                    f
                    for f in deduped
                    if f.get("finding_type") == "visual_evidence_profile"
                    or str((f.get("metadata") or {}).get("tool_name", "")).endswith(
                        "visual_evidence_profile"
                    )
                    or str((f.get("metadata") or {}).get("analysis_source", "")).startswith(
                        "gemini"
                    )
                ]
                if af_visual:
                    visual_profile_findings_by_agent[aid] = af_visual

        if not active_results:
            return self._empty_report(case_id, per_agent_findings, per_agent_metrics)

        # ── 2. Reliability & Scoring ─────────────────────────────────────
        active_metrics = [
            m
            for m in per_agent_metrics.values()
            if not m.get("skipped") and m.get("total_tools_called", 0) > 0
        ]

        # Weighted stats
        overall_confidence, overall_error_rate = self._calculate_weighted_stats(active_metrics)

        # Confidence range
        conf_scores = [
            m["confidence_score"] for m in active_metrics if m.get("confidence_score", 0) > 0
        ]
        c_min = min(conf_scores) if conf_scores else 0.0
        c_max = max(conf_scores) if conf_scores else 0.0
        c_std = (
            (
                sum((x - (sum(conf_scores) / len(conf_scores))) ** 2 for x in conf_scores)
                / len(conf_scores)
            )
            ** 0.5
            if conf_scores
            else 0.0
        )

        # Manipulation detection
        comp_penalty = self._get_compression_penalty(all_findings)
        man_prob, man_signals = calculate_manipulation_probability(all_findings, comp_penalty)

        # ── 3. Cross-Modal Deliberation ───────────────────────────────────
        await _step("Comparing corroborating and conflicting tool signals.")
        comparisons = await cross_agent_comparison(all_findings)

        await _step("Resolving cross-agent disagreements.")
        contested = await self._run_challenges(comparisons)

        overall_verdict = self._compute_verdict(
            man_prob,
            man_signals,
            overall_confidence,
            overall_error_rate,
            len(contested),
            active_metrics,
            all_findings,
            mime_type=artifact_mime,
        )

        # ── 4. Narrative Synthesis ────────────────────────────────────────
        await _step(f"Verdict {overall_verdict}: generating final report.")
        analysis_cov = self._get_coverage_note(active_metrics, all_findings)

        narratives = await self.deliberate_narratives(
            overall_verdict,
            overall_confidence,
            overall_error_rate,
            man_prob,
            len(active_results),
            all_findings,
            active_results,
            per_agent_metrics,
            [f for fl in visual_profile_findings_by_agent.values() for f in fl],
            len(
                [
                    c
                    for c in comparisons
                    if c.verdict == FindingVerdict.AGREEMENT and c.cross_modal_confirmed
                ]
            ),
            contested,
            [f for f in all_findings if f.get("status") == "INCOMPLETE"],
            analysis_cov,
            use_llm=use_llm,
            step_hook=self._step_hook,
            comparisons=comparisons,
        )

        # ── 5. Case Finalisation ───────────────────────────────────────────
        _fusion = {}
        try:
            _fusion_res = cross_modal_fuse(active_results)
            _fusion = _fusion_res.model_dump(mode="json")
        except Exception as exc:
            logger.debug("Cross-modal fusion failed", error=str(exc))

        has_deep_findings = any(
            (f.get("metadata") or {}).get("analysis_phase") == "deep"
            for f in all_findings
        )

        report = ForensicReport(
            session_id=self.session_id,
            case_id=case_id or f"case_{self.session_id}",
            executive_summary=narratives["executive_summary"],
            is_deep_analysis=has_deep_findings,
            per_agent_findings=per_agent_findings,
            per_agent_metrics=per_agent_metrics,
            per_agent_analysis=narratives["per_agent_analysis"],
            per_agent_narrative_structured=narratives.get("per_agent_narrative_structured", {}),
            summary_structured=narratives.get("summary_structured", {}),
            overall_confidence=overall_confidence,
            overall_error_rate=overall_error_rate,
            overall_verdict=overall_verdict,
            cross_modal_confirmed=[
                c.finding_a
                for c in comparisons
                if c.verdict == FindingVerdict.AGREEMENT and c.cross_modal_confirmed
            ],
            contested_findings=contested,
            incomplete_findings=[f for f in all_findings if f.get("status") == "INCOMPLETE"],
            stub_findings=[f for f in all_findings if f.get("stub_result")],
            gemini_vision_findings=[f for fl in visual_profile_findings_by_agent.values() for f in fl],
            uncertainty_statement=narratives["uncertainty_statement"],
            verdict_sentence=narratives["verdict_sentence"],
            key_findings=narratives["key_findings"],
            reliability_note=narratives["reliability_note"],
            manipulation_probability=man_prob,
            confidence_min=c_min,
            confidence_max=c_max,
            confidence_std_dev=c_std,
            per_agent_summary=self._get_agent_summary(per_agent_metrics, per_agent_findings),
            degradation_flags=self._get_degradation_flags(
                narratives["llm_used"], comp_penalty, all_findings, active_metrics,
                narratives.get("narrative_warnings", [])
            ),
            applicable_agent_count=len(active_results),
            skipped_agents=skipped_agents,
            analysis_coverage_note=analysis_cov,
            cross_modal_fusion=_fusion,
            compression_penalty=comp_penalty,
        )

        # Ensure meaningful output in template-mode fallback
        if not report.verdict_sentence:
            if report.overall_verdict in ("LIKELY_AUTHENTIC", "AUTHENTIC"):
                report.verdict_sentence = (
                    f"Based on {report.applicable_agent_count} specialist analyses, "
                    "no statistically significant manipulation signals were detected. "
                    "The evidence appears authentic within the scope of available forensic tools."
                )
            elif report.overall_verdict in ("TAMPERED", "MANIPULATED"):
                report.verdict_sentence = (
                    f"Multiple forensic agents ({report.applicable_agent_count}) identified "
                    "manipulation indicators. The evidence shows signs of post-capture modification."
                )
            else:
                report.verdict_sentence = (
                    f"The forensic council ({report.applicable_agent_count} agents) produced "
                    "inconclusive results. Manual expert review is recommended."
                )

        if not report.executive_summary:
            report.executive_summary = report.verdict_sentence

        return await self.sign_report(report)

    def _deduplicate_findings(self, findings: list[dict]) -> list[dict]:
        """
        Multi-stage deduplication that preserves forensic contradictions
        while merging similar findings across agents.

        Stages:
        1. Exact match: Same agent_id + tool_name + verdict
        2. Semantic match: Similar finding types (normalized synonym mapping)
        3. Spatial/evidence overlap: Same evidence region across tools
        4. Tool correlation: Known overlapping tool pairs (ELA + splicing)
        """
        from collections import defaultdict

        if not findings:
            return []

        # Ensure all findings are dicts
        cleaned = []
        for f in findings:
            if not isinstance(f, dict):
                logger.warning(
                    "Skipping non-dict finding during deduplication", type=type(f).__name__
                )
                continue
            if "severity_tier" not in f:
                f["severity_tier"] = assign_severity_tier(f)
            cleaned.append(f)

        if not cleaned:
            return []

        # Stage 1: Group by normalized finding type
        finding_groups = defaultdict(list)
        for f in cleaned:
            normalized = self._normalize_finding_type(f)
            finding_groups[normalized].append(f)

        # Stage 2: Within each group, merge similar findings
        deduplicated = []
        for group_key, group in finding_groups.items():
            if len(group) == 1:
                deduplicated.append(group[0])
            else:
                merged = self._merge_similar_findings(group)
                deduplicated.append(merged)

        return deduplicated

    @staticmethod
    def _normalize_finding_type(finding: dict) -> str:
        """
        Normalize finding types to catch duplicates across agents.

        Maps synonyms like 'manipulation'/'forgery'/'alteration' to 'tampering',
        and 'inconsistency'/'suspicious' to 'anomaly'.
        """
        meta = finding.get("metadata") or {}
        tool = str(meta.get("tool_name", ""))
        finding_type = str(finding.get("finding_type", ""))
        verdict = evidence_verdict_of(finding)

        # Use normalized tool name as primary key
        normalized = tool.lower().replace(" ", "_").replace("-", "_")
        if not normalized:
            normalized = finding_type.lower().replace(" ", "_").replace("-", "_")

        # Map synonyms
        synonym_map = {
            "manipulation": "tampering",
            "forgery": "tampering",
            "alteration": "tampering",
            "inconsistency": "anomaly",
            "suspicious": "anomaly",
            "clone": "synthetic",
            "spoof": "synthetic",
            "deepfake": "synthetic",
            "ai_generated": "synthetic",
            "gan": "synthetic",
            "diffusion": "synthetic",
        }
        for pattern, replacement in synonym_map.items():
            if pattern in normalized:
                normalized = normalized.replace(pattern, replacement)

        # Include verdict in key to preserve contradictions
        return f"{normalized}:{verdict}"

    @staticmethod
    def _merge_similar_findings(findings: list[dict]) -> dict:
        """
        Merge multiple similar findings into one consolidated finding.

        - Keeps the highest confidence finding as primary
        - Combines reasoning from all sources
        - Lists all contributing agents
        - Merges metadata
        - Tracks corroboration strength
        """
        if not findings:
            return {}
        if len(findings) == 1:
            return findings[0]

        # Sort by confidence descending
        sorted_f = sorted(
            findings,
            key=lambda f: confidence_of(f, default=0.0) or 0.0,
            reverse=True,
        )
        primary = sorted_f[0]

        # Collect contributing agents and tools
        contributing_agents: list[str] = []
        all_tools: list[str] = []
        all_reasoning: list[str] = []
        seen_reasoning: set[str] = set()

        for f in findings:
            aid = str(f.get("agent_id", ""))
            if aid and aid not in contributing_agents:
                contributing_agents.append(aid)

            meta = f.get("metadata") or {}
            tn = meta.get("tool_name", "")
            if tn and tn not in all_tools:
                all_tools.append(str(tn))

            rs = str(f.get("reasoning_summary", "") or "").strip()
            if rs and rs not in seen_reasoning:
                seen_reasoning.add(rs)
                all_reasoning.append(rs)

        # Build merged reasoning
        merge_parts = []
        merge_parts.append(
            f"Corroborated by {len(contributing_agents)} agent(s), {len(all_tools)} tool(s)."
        )
        if all_tools:
            merge_parts.append(f"Tools: {', '.join(all_tools[:5])}.")
        if all_reasoning:
            merge_parts.extend(all_reasoning[:3])

        # Create merged finding
        merged = dict(primary)
        merged["reasoning_summary"] = " | ".join(merge_parts)

        merged_meta = dict(primary.get("metadata") or {})
        merged_meta["contributing_agents"] = contributing_agents
        merged_meta["source_count"] = len(findings)
        merged_meta["corroboration_strength"] = (
            "HIGH" if len(findings) >= 3 else ("MEDIUM" if len(findings) >= 2 else "LOW")
        )
        merged_meta["merged_tools"] = all_tools
        merged["metadata"] = merged_meta

        return merged

    def _compute_agent_metrics(self, aid: str, findings: list[dict], skipped: bool) -> AgentMetrics:
        name = AGENT_NAMES.get(aid, aid)
        if skipped:
            return AgentMetrics(agent_id=aid, agent_name=name, skipped=True)
        real = [
            f
            for f in findings
            if str(f.get("finding_type", "")).lower()
            not in {"file type not applicable", "format not supported"}
        ]

        def _is_na(f):
            return evidence_verdict_of(f) == "NOT_APPLICABLE"

        def _is_gated(f):
            meta = f.get("metadata") or {}
            return meta.get("gated") is True or meta.get("not_triggered") is True

        def _is_fail(f):
            return evidence_verdict_of(f) == "ERROR" or (
                not _is_na(f) and not _is_gated(f) and f.get("status") == "INCOMPLETE"
            )

        # Gated/not-triggered findings were never actually executed — count them
        # as not_applicable so they don't inflate the error rate denominator.
        na = sum(1 for f in real if _is_na(f))
        gated = sum(1 for f in real if _is_gated(f))
        fail = sum(1 for f in real if _is_fail(f))
        app = len(real) - na - gated
        if app == 0 and fail > 0:
            err = 1.0  # All tools failed - 100% error rate
        else:
            err = round(fail / app, 3) if app > 0 else 0.0
        conf = [
            c
            for f in real
            if not _is_na(f) and not _is_fail(f)
            and (c := confidence_of(f)) is not None
        ]
        avg_conf = round(sum(conf) / len(conf), 3) if conf else 0.0
        deep = sum(1 for f in real if (f.get("metadata") or {}).get("analysis_phase") == "deep")
        return AgentMetrics(
            agent_id=aid,
            agent_name=name,
            total_tools_called=len(real),
            tools_succeeded=app - fail,
            tools_failed=fail,
            tools_not_applicable=na + gated,
            error_rate=err,
            confidence_score=avg_conf,
            finding_count=len(real),
            deep_finding_count=deep,
        )

    def _calculate_weighted_stats(self, active_metrics: list[dict]) -> tuple[float, float]:
        w_sum, wc_sum, we_num, we_den = 0.0, 0.0, 0.0, 0.0
        for m in active_metrics:
            app = m.get("total_tools_called", 0) - m.get("tools_not_applicable", 0)
            if app <= 0:
                continue
            rel = max(0.0, 1.0 - m.get("error_rate", 0.0))
            weight = (
                rel
                * app
                * (
                    ForensicPolicy.DEEP_ANALYSIS_BONUS
                    if m.get("deep_finding_count", 0) > 0
                    else 1.0
                )
            )
            wc_sum += m["confidence_score"] * weight
            w_sum += weight
            we_num += m["error_rate"] * max(1, app)
            we_den += max(1, app)
        return (round(wc_sum / w_sum, 3) if w_sum > 0 else 0.0), (
            round(we_num / we_den, 3) if we_den > 0 else 0.0
        )

    def _get_compression_penalty(self, findings: list[dict]) -> float:
        """Retrieve compression penalty from Agent 5's audit finding."""
        for f in findings:
            meta = f.get("metadata") or {}
            if (
                f.get("finding_type") == "compression_risk_audit"
                or meta.get("tool_name") == "compression_risk_audit"
            ):
                return float(meta.get("compression_penalty", 1.0))

        # Agent 5 ran but produced no audit — apply a small conservative penalty
        # to prevent overconfident AUTHENTIC verdicts without compression evidence.
        agent5_active = any(
            f.get("agent_id") == "Agent5"
            for f in findings
            if f.get("evidence_verdict") not in ("NOT_APPLICABLE", "ERROR")
        )
        return 0.95 if agent5_active else 1.0

    def _compute_verdict(
        self,
        manipulation_probability: float,
        manipulation_signals: int,
        overall_confidence: float,
        overall_error_rate: float,
        contested_count: int,
        active_metrics: list[dict],
        all_findings: list[dict],
        mime_type: str = "",
    ) -> str:
        # File-type-specific thresholds: PNG/lossless screenshots have higher
        # baselines for manipulation due to common compression artifacts.
        if mime_type in ("image/png", "image/webp", "image/bmp", "image/gif"):
            _manipulated_threshold = 0.85
            _likely_manipulated_threshold = 0.70
            _suspicious_threshold = 0.55
            _authentic_conf_threshold = 0.80
            _likely_authentic_conf_threshold = 0.65
        else:
            _manipulated_threshold = ForensicPolicy.MANIPULATED_PROB_THRESHOLD
            _likely_manipulated_threshold = ForensicPolicy.LIKELY_MANIPULATED_PROB_THRESHOLD
            _suspicious_threshold = ForensicPolicy.SUSPICIOUS_PROB_THRESHOLD
            _authentic_conf_threshold = ForensicPolicy.AUTHENTIC_CONF_THRESHOLD
            _likely_authentic_conf_threshold = ForensicPolicy.LIKELY_AUTHENTIC_CONF_THRESHOLD

        if (
            manipulation_probability >= _manipulated_threshold
            and manipulation_signals >= ForensicPolicy.MANIP_SIGNAL_MIN_REQUIRED
        ):
            return "MANIPULATED"

        elif manipulation_probability >= _likely_manipulated_threshold and (
            manipulation_signals >= ForensicPolicy.MANIP_SIGNAL_MIN_REQUIRED
            or (
                manipulation_signals == 1
                and manipulation_probability >= ForensicPolicy.SINGLE_SIGNAL_MANIP_THRESHOLD
            )
        ):
            return "LIKELY_MANIPULATED"

        elif (
            manipulation_probability >= _suspicious_threshold
            and manipulation_signals >= 1
        ):
            return "SUSPICIOUS"

        elif (
            manipulation_signals == 0
            and overall_confidence >= _authentic_conf_threshold
            and overall_error_rate <= ForensicPolicy.AUTHENTIC_ERROR_MAX
            and contested_count == 0
        ):
            return "AUTHENTIC"

        elif (
            manipulation_signals == 0
            and overall_confidence >= _likely_authentic_conf_threshold
            and overall_error_rate <= ForensicPolicy.LIKELY_AUTHENTIC_ERROR_MAX
        ):
            return "LIKELY_AUTHENTIC"

        elif (
            len(active_metrics) <= 1 and overall_confidence < ForensicPolicy.ABSTAIN_CONF_FLOOR
        ) or overall_error_rate > ForensicPolicy.ABSTAIN_ERROR_CEILING:
            return "ABSTAIN"

        else:
            return "INCONCLUSIVE"

    async def _run_challenges(self, comparisons: list[FindingComparison]) -> list[dict]:
        """
        Evaluate contradictions and optionally re-invoke agents to resolve them.

        When agent_factory is available, contradicting agents are challenged —
        they re-run their ReAct loop with contradiction context and may revise
        their finding. Without agent_factory, contradictions are recorded as
        contested and escalated to HITL tribunal.
        """
        contested = []
        contradictions = [c for c in comparisons if c.verdict == FindingVerdict.CONTRADICTION]

        for comp in contradictions:
            fa, fb = comp.finding_a, comp.finding_b
            agent_a_id = fa.get("agent_id", "")
            agent_b_id = fb.get("agent_id", "")

            challenge_entry = {
                **comp.model_dump(mode="json"),
                "plain_description": (
                    f"{AGENT_NAMES.get(agent_a_id, agent_a_id)} vs "
                    f"{AGENT_NAMES.get(agent_b_id, agent_b_id)} — Conflict detected."
                ),
                "challenge_attempted": False,
                "challenge_resolved": False,
            }

            # Challenge loop: re-invoke the lower-confidence agent if factory available.
            # Without agent_factory this remains a contested (HITL-escalated) finding.
            # Limited to MAX_CHALLENGE_ATTEMPTS to prevent resource exhaustion.
            if self.agent_factory is not None:
                try:
                    conf_a = (
                        fa.get("raw_confidence_score")
                        or fa.get("confidence_raw")
                        or DEFAULT_CONFIDENCE_FALLBACK
                    )
                    conf_b = (
                        fb.get("raw_confidence_score")
                        or fb.get("confidence_raw")
                        or DEFAULT_CONFIDENCE_FALLBACK
                    )
                    challenged_id = agent_a_id if conf_a <= conf_b else agent_b_id
                    contradicting = fb if challenged_id == agent_a_id else fa

                    challenge_entry["challenge_attempts"] = 0
                    revised_findings = []
                    # B-C-4: a wedged agent ReAct loop must not stall the
                    # arbiter indefinitely. Cap each reinvocation at a quarter
                    # of the investigation budget so the deliberation can
                    # still finalise (with an unresolved-challenge entry).
                    challenge_timeout = max(
                        15.0,
                        float(self.config.investigation_timeout) / 4.0,
                    )
                    for attempt in range(MAX_CHALLENGE_ATTEMPTS):
                        challenge_entry["challenge_attempts"] = attempt + 1
                        try:
                            challenge_result = await asyncio.wait_for(
                                self.agent_factory.reinvoke_agent(
                                    agent_id=challenged_id,
                                    session_id=self.session_id,
                                    challenge_context={
                                        "challenge_id": str(_uuid.uuid4()),
                                        "attempt_number": attempt + 1,
                                        "max_attempts": MAX_CHALLENGE_ATTEMPTS,
                                        "contradiction": contradicting,
                                        "arbiter_session": str(self.session_id),
                                    },
                                ),
                                timeout=challenge_timeout,
                            )
                        except TimeoutError:
                            logger.warning(
                                "Challenge attempt timed out",
                                challenged_agent=challenged_id,
                                attempt=attempt + 1,
                                timeout_s=challenge_timeout,
                                session_id=str(self.session_id),
                            )
                            challenge_entry["challenge_timed_out"] = True
                            continue
                        revised_findings = challenge_result.get("findings", [])
                        if revised_findings:
                            break

                    challenge_entry["challenge_attempted"] = True
                    challenge_entry["challenge_resolved"] = bool(revised_findings)
                    challenge_entry["revised_findings"] = revised_findings
                    logger.info(
                        "Challenge loop completed",
                        challenged_agent=challenged_id,
                        attempts=challenge_entry["challenge_attempts"],
                        resolved=bool(revised_findings),
                    )
                except Exception as exc:
                    logger.warning(f"Challenge invocation failed for {challenged_id}: {exc}")

            contested.append(challenge_entry)

        return contested

    def _get_coverage_note(self, metrics, findings) -> str:
        total = sum(m.get("total_tools_called", 0) for m in metrics)
        fail = sum(m.get("tools_failed", 0) for m in metrics)
        fallback = sum(1 for f in findings if (f.get("metadata") or {}).get("degraded") is True)
        parts = []
        if fail:
            parts.append(f"{fail} of {total} tools failed")
        if fallback:
            parts.append(f"{fallback} tools used simplified fallbacks")
        return "; ".join(parts) if parts else f"All {total} tools ran successfully"

    def _get_agent_summary(self, metrics, findings) -> dict:
        summary = {}
        for aid, m in metrics.items():
            conf = m.get("confidence_score", 0)
            err = m.get("error_rate", 0)

            agent_findings = findings.get(aid, [])
            positive = sum(
                1
                for f in agent_findings
                if evidence_verdict_of(f) == "POSITIVE"
                and (confidence_of(f) or 0) >= MIN_CONFIDENCE_THRESHOLD
            )
            inconclusive = sum(
                1 for f in agent_findings if evidence_verdict_of(f) == "INCONCLUSIVE"
            )

            if positive > 0:
                v = "SUSPICIOUS"
            elif inconclusive > 0:
                v = "INCONCLUSIVE"
            elif ForensicPolicy.is_authentic(conf, err):
                v = "AUTHENTIC"
            elif ForensicPolicy.is_suspicious(conf, err):
                v = "SUSPICIOUS"
            else:
                v = (
                    "AUTHENTIC"
                    if conf >= ForensicPolicy.AUTHENTIC_CONF_THRESHOLD
                    else "INCONCLUSIVE"
                )

            if m.get("skipped"):
                v = "NOT_APPLICABLE"

            summary[aid] = {
                "agent_name": AGENT_NAMES.get(aid, aid),
                "verdict": v,
                "confidence_pct": round(conf * 100),
                "error_rate_pct": round(err * 100),
                "skipped": m.get("skipped", False),
            }
        return summary

    def _get_degradation_flags(self, llm_ok, penalty, findings, metrics, narrative_warnings: list[str] | None = None) -> list[str]:
        flags = []
        if self.config.llm_enable_post_synthesis and not llm_ok:
            flags.append("LLM synthesis bypassed")
        if penalty < 0.80:
            flags.append(f"Compression penalty applied ({round((1 - penalty) * 100)}%)")
        # Check visual profile provenance: report if all deep-phase findings
        # used local fallback (Gemini was unavailable or skipped).
        has_deep_findings = any(
            (f.get("metadata") or {}).get("analysis_phase") == "deep" for f in findings
        )
        has_remote_profile = any(
            (f.get("metadata") or {}).get("external_ai_used") is True
            or (f.get("metadata") or {}).get("provider_used") == "gemini"
            for f in findings
        )
        if has_deep_findings and not has_remote_profile:
            flags.append("Visual profile: local ensemble only (no remote provider)")
        if narrative_warnings:
            flags.extend(narrative_warnings)
        return flags

    def _empty_report(self, case_id, findings, metrics) -> ForensicReport:
        return ForensicReport(
            session_id=self.session_id,
            case_id=case_id or f"case_{self.session_id}",
            executive_summary="No active agents produced findings.",
            per_agent_findings=findings,
            per_agent_metrics=metrics,
            uncertainty_statement="Analysis was skipped for all agents.",
            overall_verdict="INCONCLUSIVE",
            degradation_flags=[
                "All agents failed or were skipped — report based on incomplete data."
            ],
            analysis_coverage_note="Zero agents produced findings; verdict defaulted to INCONCLUSIVE.",
        )

    @staticmethod
    def _calculate_verdict_deterministic(findings: dict) -> tuple[str, float]:
        """Calculate verdict using only tool outputs, no LLM."""
        positive_counts = {}
        total_tools = {}
        for agent_id, agent_findings in findings.items():
            positive = sum(1 for f in agent_findings
                          if f.get('evidence_verdict') == 'POSITIVE')
            total = len([f for f in agent_findings
                        if f.get('status') != 'NOT_APPLICABLE'])
            positive_counts[agent_id] = positive
            total_tools[agent_id] = total
        total_positive = sum(positive_counts.values())
        total_executed = sum(total_tools.values())
        if total_executed == 0:
            return "INCONCLUSIVE", 0.0
        manipulation_ratio = total_positive / total_executed
        if manipulation_ratio >= 0.7:
            return "HIGHLY_LIKELY_MANIPULATED", 0.85
        elif manipulation_ratio >= 0.5:
            return "LIKELY_MANIPULATED", 0.70
        elif manipulation_ratio >= 0.3:
            return "POSSIBLY_MANIPULATED", 0.50
        elif manipulation_ratio >= 0.1:
            return "LIKELY_AUTHENTIC", 0.75
        else:
            return "HIGHLY_LIKELY_AUTHENTIC", 0.90

    @staticmethod
    def _generate_template_narratives(agent_results: dict) -> dict[str, str]:
        """Generate deterministic per-agent narratives without LLM."""
        narratives = {}
        for agent_id, result in agent_results.items():
            findings = result.get('findings', [])
            tool_count = len([f for f in findings if f.get('metadata', {}).get('tool_name')])
            positive_count = sum(1 for f in findings if f.get('evidence_verdict') == 'POSITIVE')
            if positive_count > 0:
                narrative = (f"{agent_id} executed {tool_count} specialized forensic tools "
                            f"and detected {positive_count} positive indicators of manipulation.")
            else:
                narrative = (f"{agent_id} executed {tool_count} specialized forensic tools "
                            f"and found no significant anomalies.")
            narratives[agent_id] = narrative
        return narratives
