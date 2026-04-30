"""
Council Arbiter & Report Generator
==============================

The synthesis layer that deliberates on agent findings, manages challenge loops,
tribunal escalation, and generates court-admissible reports.
"""

from __future__ import annotations

import uuid as _uuid
from typing import Any
from uuid import UUID

from agents.arbiter_narrative import ArbiterNarrativeMixin
from agents.arbiter_verdict import (
    AGENT_NAMES,
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
from core.signing import KeyStore
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
        self._key_store = KeyStore()
        self._key_store.get_or_create(AgentID.ARBITER)
        self._synthesis_client: Any = None
        self._step_hook: Any = None

    async def deliberate(
        self,
        agent_results: dict[str, dict[str, Any]],
        case_id: str = "",
        use_llm: bool = True,
    ) -> ForensicReport:
        """Main deliberation entry point."""
        skip_types = {"file type not applicable", "format not supported"}

        async def _step(msg: str):
            if self._step_hook:
                await self._step_hook(msg)

        # ── 1. Finding Extraction & Deduplication ─────────────────────────
        await _step("Gathering all agent findings…")
        all_findings, per_agent_findings, per_agent_metrics, skipped_agents = [], {}, {}, {}
        active_results, gemini_findings_by_agent = {}, {}

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
                af_gemini = [
                    f
                    for f in deduped
                    if str((f.get("metadata") or {}).get("analysis_source", "")).startswith(
                        "gemini"
                    )
                ]
                if af_gemini:
                    gemini_findings_by_agent[aid] = af_gemini

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
        await _step("Running cross-modal comparison…")
        comparisons = await cross_agent_comparison(all_findings)

        await _step("Executing parallel multi-way challenge loops…")
        contested = await self._run_challenges(comparisons)

        # Final verdict mapping
        overall_verdict = self._compute_verdict(
            man_prob,
            man_signals,
            overall_confidence,
            overall_error_rate,
            len(contested),
            active_metrics,
            all_findings,
        )

        # ── 4. Narrative Synthesis ────────────────────────────────────────
        await _step(f"Verdict: {overall_verdict} — synthesising report…")
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
            [f for fl in gemini_findings_by_agent.values() for f in fl],
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
        )

        # ── 5. Case Finalisation ───────────────────────────────────────────
        _fusion = {}
        try:
            _fusion_res = cross_modal_fuse(active_results)
            _fusion = _fusion_res.model_dump(mode="json")
        except Exception as exc:
            logger.debug("Cross-modal fusion failed", error=str(exc))

        report = ForensicReport(
            session_id=self.session_id,
            case_id=case_id or f"case_{self.session_id}",
            executive_summary=narratives["executive_summary"],
            per_agent_findings=per_agent_findings,
            per_agent_metrics=per_agent_metrics,
            per_agent_analysis=narratives["per_agent_analysis"],
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
            gemini_vision_findings=[f for fl in gemini_findings_by_agent.values() for f in fl],
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
                narratives["llm_used"], comp_penalty, all_findings, active_metrics
            ),
            applicable_agent_count=len(active_results),
            skipped_agents=skipped_agents,
            analysis_coverage_note=analysis_cov,
            cross_modal_fusion=_fusion,
            compression_penalty=comp_penalty,
        )
        return await self.sign_report(report)

    def _deduplicate_findings(self, findings: list[dict]) -> list[dict]:
        """
        Deduplicate findings while preserving forensic contradictions.

        If the same tool produces different verdicts (e.g. POSITIVE and NEGATIVE),
        both are preserved so the tribunal can deliberate on the inconsistency.
        Otherwise, the highest-confidence finding for a given key is kept.
        """
        seen, out = {}, []
        for f in findings:
            if not isinstance(f, dict):
                logger.warning(
                    "Skipping non-dict finding during deduplication", type=type(f).__name__
                )
                continue

            if "severity_tier" not in f:
                f["severity_tier"] = assign_severity_tier(f)

            meta = f.get("metadata") or {}
            verdict = evidence_verdict_of(f)

            # Key now includes verdict to ensure contradictions are not deduped away
            key = (
                str(f.get("agent_id", "")),
                str(f.get("finding_type", "")),
                str(meta.get("tool_name", "")),
                verdict,
            )

            if key in seen:
                idx = seen[key]
                old = out[idx]
                conf_new = confidence_of(f, default=0.0) or 0.0
                conf_old = confidence_of(old, default=0.0) or 0.0
                if conf_new > conf_old:
                    out[idx] = f
                continue

            seen[key] = len(out)
            out.append(f)
        return out

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

        def _is_fail(f):
            return evidence_verdict_of(f) == "ERROR" or (
                not _is_na(f) and f.get("status") == "INCOMPLETE"
            )

        na = sum(1 for f in real if _is_na(f))
        fail = sum(1 for f in real if _is_fail(f))
        app = len(real) - na
        if app == 0 and fail > 0:
            err = 1.0  # All tools failed - 100% error rate
        else:
            err = round(fail / app, 3) if app > 0 else 0.0
        conf = [
            c
            for f in real
            if not _is_na(f) and not _is_fail(f)
            for c in [confidence_of(f)]
            if c is not None
        ]
        avg_conf = round(sum(conf) / len(conf), 3) if conf else 0.0
        deep = sum(1 for f in real if (f.get("metadata") or {}).get("analysis_phase") == "deep")
        return AgentMetrics(
            agent_id=aid,
            agent_name=name,
            total_tools_called=len(real),
            tools_succeeded=app - fail,
            tools_failed=fail,
            tools_not_applicable=na,
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
    ) -> str:
        if (
            manipulation_probability >= ForensicPolicy.MANIPULATED_PROB_THRESHOLD
            and manipulation_signals >= ForensicPolicy.MANIP_SIGNAL_MIN_REQUIRED
        ):
            return "MANIPULATED"

        elif manipulation_probability >= ForensicPolicy.LIKELY_MANIPULATED_PROB_THRESHOLD and (
            manipulation_signals >= ForensicPolicy.MANIP_SIGNAL_MIN_REQUIRED
            or (
                manipulation_signals == 1
                and manipulation_probability >= ForensicPolicy.SINGLE_SIGNAL_MANIP_THRESHOLD
            )
        ):
            return "LIKELY_MANIPULATED"

        elif (
            manipulation_probability >= ForensicPolicy.SUSPICIOUS_PROB_THRESHOLD
            and manipulation_signals >= 1
        ):
            return "SUSPICIOUS"

        elif (
            manipulation_signals == 0
            and overall_confidence >= ForensicPolicy.AUTHENTIC_CONF_THRESHOLD
            and overall_error_rate <= ForensicPolicy.AUTHENTIC_ERROR_MAX
            and contested_count == 0
        ):
            return "AUTHENTIC"

        elif (
            manipulation_signals == 0
            and overall_confidence >= ForensicPolicy.LIKELY_AUTHENTIC_CONF_THRESHOLD
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
                    for attempt in range(MAX_CHALLENGE_ATTEMPTS):
                        challenge_entry["challenge_attempts"] = attempt + 1
                        challenge_result = await self.agent_factory.reinvoke_agent(
                            agent_id=challenged_id,
                            session_id=self.session_id,
                            challenge_context={
                                "challenge_id": str(_uuid.uuid4()),
                                "attempt_number": attempt + 1,
                                "max_attempts": MAX_CHALLENGE_ATTEMPTS,
                                "contradiction": contradicting,
                                "arbiter_session": str(self.session_id),
                            },
                        )
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
            from agents.arbiter_verdict import MIN_CONFIDENCE_THRESHOLD, confidence_of

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
                # Default to AUTHENTIC if confidence is high and no suspicious signals found
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

    def _get_degradation_flags(self, llm_ok, penalty, findings, metrics) -> list[str]:
        flags = []
        if self.config.llm_enable_post_synthesis and not llm_ok:
            flags.append("LLM synthesis bypassed")
        if penalty < 1.0:
            flags.append(f"Compression penalty applied ({round((1 - penalty) * 100)}%)")
        if not any(
            str((f.get("metadata") or {}).get("analysis_source", "")).startswith("gemini")
            for f in findings
        ):
            flags.append("Gemini deep analysis skipped")
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
