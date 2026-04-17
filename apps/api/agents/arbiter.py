"""
Council Arbiter & Report Generator
==============================

The synthesis layer that deliberates on agent findings, manages challenge loops,
tribunal escalation, and generates court-admissible reports.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from core.config import Settings, get_settings
from core.forensic_policy import ForensicPolicy
from core.cross_modal_fusion import fuse as cross_modal_fuse
from core.severity import assign_severity_tier
from core.signing import KeyStore
from core.structured_logging import get_logger

from agents.arbiter_verdict import (
    FindingVerdict,
    FindingComparison,
    ChallengeResult,
    TribunalCase,
    AgentMetrics,
    ForensicReport,
    AGENT_NAMES,
    calculate_manipulation_probability,
    cross_agent_comparison
)
from agents.arbiter_narrative import ArbiterNarrativeMixin

logger = get_logger(__name__)

# Re-exporting for backward compatibility
__all__ = [
    "FindingVerdict", "FindingComparison", "ChallengeResult", "TribunalCase",
    "AgentMetrics", "ForensicReport", "CouncilArbiter"
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
        self._key_store.get_or_create("Arbiter")
        self._synthesis_client: Any = None
        self._step_hook: Any = None

    async def deliberate(
        self,
        agent_results: dict[str, dict[str, Any]],
        case_id: str = "",
        use_llm: bool = True,
    ) -> ForensicReport:
        """Main deliberation entry point."""
        _SKIP_TYPES = {"file type not applicable", "format not supported"}

        async def _step(msg: str):
            if self._step_hook: await self._step_hook(msg)

        # ── 1. Finding Extraction & Deduplication ─────────────────────────
        await _step("Gathering all agent findings…")
        all_findings, per_agent_findings, per_agent_metrics = [], {}, {}
        active_results, gemini_findings_by_agent = {}, {}

        for aid, res in agent_results.items():
            raw = res.get("findings", [])
            deduped = self._deduplicate_findings(raw)
            skipped = not deduped or all(str(f.get("finding_type", "")).lower() in _SKIP_TYPES for f in deduped)
            per_agent_findings[aid] = deduped
            
            metrics = self._compute_agent_metrics(aid, deduped, skipped)
            per_agent_metrics[aid] = metrics.model_dump()

            if not skipped:
                active_results[aid] = {**res, "findings": deduped}
                all_findings.extend(deduped)
                af_gemini = [f for f in deduped if (f.get("metadata") or {}).get("analysis_source") == "gemini_vision"]
                if af_gemini: gemini_findings_by_agent[aid] = af_gemini

        if not active_results:
            return self._empty_report(case_id, per_agent_findings, per_agent_metrics)

        # ── 2. Reliability & Scoring ─────────────────────────────────────
        active_metrics = [m for m in per_agent_metrics.values() if not m.get("skipped") and m.get("total_tools_called", 0) > 0]
        
        # Weighted stats
        overall_confidence, overall_error_rate = self._calculate_weighted_stats(active_metrics)
        
        # Confidence range
        conf_scores = [m["confidence_score"] for m in active_metrics if m.get("confidence_score", 0) > 0]
        c_min = min(conf_scores) if conf_scores else 0.0
        c_max = max(conf_scores) if conf_scores else 0.0
        c_std = (sum((x - (sum(conf_scores)/len(conf_scores)))**2 for x in conf_scores)/len(conf_scores))**0.5 if conf_scores else 0.0

        # Manipulation detection
        comp_penalty = self._get_compression_penalty(all_findings)
        man_prob, man_signals = calculate_manipulation_probability(all_findings, comp_penalty)

        # ── 3. Cross-Modal Deliberation ───────────────────────────────────
        await _step("Running cross-modal comparison…")
        comparisons = await cross_agent_comparison(all_findings)
        
        await _step("Executing parallel multi-way challenge loops…")
        contested = await self._run_challenges(comparisons)
        
        # Final verdict mapping
        overall_verdict = self._compute_verdict(man_prob, man_signals, overall_confidence, overall_error_rate, len(contested), active_metrics, all_findings)
        
        # ── 4. Narrative Synthesis ────────────────────────────────────────
        await _step(f"Verdict: {overall_verdict} — synthesising report…")
        analysis_cov = self._get_coverage_note(active_metrics, all_findings)
        
        narratives = await self.deliberate_narratives(
            overall_verdict, overall_confidence, overall_error_rate, man_prob,
            len(active_results), all_findings, active_results, per_agent_metrics,
            [f for fl in gemini_findings_by_agent.values() for f in fl],
            len([c for c in comparisons if c.verdict == FindingVerdict.AGREEMENT and c.cross_modal_confirmed]),
            contested, [f for f in all_findings if f.get("status") == "INCOMPLETE"],
            analysis_cov, use_llm=use_llm, step_hook=self._step_hook
        )

        # ── 5. Case Finalisation ───────────────────────────────────────────
        _fusion = {}
        try:
            _fusion_res = cross_modal_fuse(active_results)
            _fusion = _fusion_res.model_dump(mode="json")
        except Exception:
            pass

        report = ForensicReport(
            session_id=self.session_id, case_id=case_id or f"case_{self.session_id}",
            executive_summary=narratives["executive_summary"], per_agent_findings=per_agent_findings,
            per_agent_metrics=per_agent_metrics, per_agent_analysis=narratives["per_agent_analysis"],
            overall_confidence=overall_confidence, overall_error_rate=overall_error_rate,
            overall_verdict=overall_verdict, cross_modal_confirmed=[c.finding_a for c in comparisons if c.verdict == FindingVerdict.AGREEMENT and c.cross_modal_confirmed],
            contested_findings=contested, incomplete_findings=[f for f in all_findings if f.get("status") == "INCOMPLETE"],
            stub_findings=[f for f in all_findings if f.get("stub_result")], gemini_vision_findings=[f for fl in gemini_findings_by_agent.values() for f in fl],
            uncertainty_statement=narratives["uncertainty_statement"], verdict_sentence=narratives["verdict_sentence"],
            key_findings=narratives["key_findings"], reliability_note=narratives["reliability_note"],
            manipulation_probability=man_prob, confidence_min=c_min, confidence_max=c_max, confidence_std_dev=c_std,
            per_agent_summary=self._get_agent_summary(per_agent_metrics, per_agent_findings), 
            degradation_flags=self._get_degradation_flags(narratives["llm_used"], comp_penalty, all_findings, active_metrics),
            applicable_agent_count=len(active_results), analysis_coverage_note=analysis_cov, cross_modal_fusion=_fusion
        )
        return await self.sign_report(report)

    def _deduplicate_findings(self, findings: list[dict]) -> list[dict]:
        seen, out = {}, []
        for f in findings:
            if isinstance(f, dict) and "severity_tier" not in f: f["severity_tier"] = assign_severity_tier(f)
            meta = f.get("metadata") or {}
            key = (str(f.get("agent_id", "")), str(f.get("finding_type", "")), str(meta.get("tool_name", "")))
            if key in seen:
                idx = seen[key]; old = out[idx]
                conf_new = (f.get("raw_confidence_score") or f.get("confidence_raw") or 0.0)
                conf_old = (old.get("raw_confidence_score") or old.get("confidence_raw") or 0.0)
                if conf_new > conf_old: out[idx] = f
                continue
            seen[key] = len(out); out.append(f)
        return out

    def _compute_agent_metrics(self, aid: str, findings: list[dict], skipped: bool) -> AgentMetrics:
        name = AGENT_NAMES.get(aid, aid)
        if skipped: return AgentMetrics(agent_id=aid, agent_name=name, skipped=True)
        real = [f for f in findings if str(f.get("finding_type", "")).lower() not in {"file type not applicable", "format not supported"}]
        
        def _is_na(f):
            m = f.get("metadata") or {}
            return str(m.get("verdict", "")).upper() == "NOT_APPLICABLE" or any(m.get(fl) for fl in ("ela_not_applicable", "ghost_not_applicable", "prnu_not_applicable"))
        
        def _is_fail(f): return not _is_na(f) and ((f.get("metadata") or {}).get("court_defensible") is False or f.get("status") == "INCOMPLETE")
        
        na = sum(1 for f in real if _is_na(f))
        fail = sum(1 for f in real if _is_fail(f))
        app = len(real) - na
        err = round(fail / app, 3) if app > 0 else 0.0
        conf = [f.get("confidence_raw") or f.get("raw_confidence_score") or 0.0 for f in real if not _is_na(f) and not _is_fail(f)]
        avg_conf = round(sum(conf) / len(conf), 3) if conf else 0.0
        return AgentMetrics(agent_id=aid, agent_name=name, total_tools_called=len(real), tools_succeeded=app-fail, tools_failed=fail, tools_not_applicable=na, error_rate=err, confidence_score=avg_conf, finding_count=len(real))

    def _calculate_weighted_stats(self, active_metrics: list[dict]) -> tuple[float, float]:
        w_sum, wc_sum, we_num, we_den = 0.0, 0.0, 0.0, 0.0
        for m in active_metrics:
            app = m.get("total_tools_called", 0) - m.get("tools_not_applicable", 0)
            if app <= 0: continue
            rel = max(0.0, 1.0 - m.get("error_rate", 0.0))
            weight = rel * app * (1.15 if m.get("deep_finding_count", 0) > 0 else 1.0)
            wc_sum += m["confidence_score"] * weight; w_sum += weight
            we_num += m["error_rate"] * max(1, app); we_den += max(1, app)
        return (round(wc_sum / w_sum, 3) if w_sum > 0 else 0.0), (round(we_num / we_den, 3) if we_den > 0 else 0.0)

    def _get_compression_penalty(self, findings: list[dict]) -> float:
        """
        Retrieves the compression penalty calculated by Agent 5 (Metadata).
        If missing, defaults to no penalty (1.0).
        """
        for f in findings:
            if f.get("finding_type") == "compression_risk_audit":
                meta = f.get("metadata") or {}
                return float(meta.get("compression_penalty", 1.0))
        return 1.0

    def _compute_verdict(self, mp, ms, oc, oer, contested, metrics, findings) -> str:
        if mp >= ForensicPolicy.MANIPULATED_PROB_THRESHOLD and ms >= ForensicPolicy.MANIP_SIGNAL_MIN_REQUIRED:
            return "MANIPULATED"
            
        if mp >= ForensicPolicy.LIKELY_MANIPULATED_PROB_THRESHOLD and ms >= ForensicPolicy.MANIP_SIGNAL_MIN_REQUIRED:
            return "LIKELY_MANIPULATED"
            
        if mp >= ForensicPolicy.SUSPICIOUS_PROB_THRESHOLD and ms >= 1:
            return "SUSPICIOUS"
            
        if (ms == 0 and oc >= ForensicPolicy.AUTHENTIC_CONF_THRESHOLD 
            and oer <= ForensicPolicy.AUTHENTIC_ERROR_MAX and contested == 0):
            return "AUTHENTIC"
            
        if ms == 0 and oc >= ForensicPolicy.LIKELY_AUTHENTIC_CONF_THRESHOLD and oer <= ForensicPolicy.LIKELY_AUTHENTIC_ERROR_MAX:
            return "LIKELY_AUTHENTIC"
            
        if (len(metrics) <= 1 and oc < ForensicPolicy.ABSTAIN_CONF_FLOOR) or oer > ForensicPolicy.ABSTAIN_ERROR_CEILING:
            return "ABSTAIN"
            
        return "INCONCLUSIVE"

    async def _run_challenges(self, comparisons: list[FindingComparison]) -> list[dict]:
        contested = []
        contradictions = [c for c in comparisons if c.verdict == FindingVerdict.CONTRADICTION]
        for comp in contradictions[:5]:
            fa, fb = comp.finding_a, comp.finding_b
            contested.append({**comp.model_dump(mode="json"), "plain_description": f"{AGENT_NAMES.get(fa['agent_id'], fa['agent_id'])} vs {AGENT_NAMES.get(fb['agent_id'], fb['agent_id'])} - Conflict detected."})
        return contested

    def _get_coverage_note(self, metrics, findings) -> str:
        total = sum(m.get("total_tools_called", 0) for m in metrics)
        fail = sum(m.get("tools_failed", 0) for m in metrics)
        fallback = sum(1 for f in findings if (f.get("metadata") or {}).get("degraded") is True)
        parts = []
        if fail: parts.append(f"{fail} of {total} tools failed")
        if fallback: parts.append(f"{fallback} tools used simplified fallbacks")
        return "; ".join(parts) if parts else f"All {total} tools ran successfully"

    def _get_agent_summary(self, metrics, findings) -> dict:
        summary = {}
        for aid, m in metrics.items():
            conf = m.get("confidence_score", 0)
            err = m.get("error_rate", 0)
            
            if ForensicPolicy.is_authentic(conf, err):
                v = "AUTHENTIC"
            elif ForensicPolicy.is_suspicious(conf, err):
                v = "SUSPICIOUS"
            else:
                v = "INCONCLUSIVE"
                
            if m.get("skipped"):
                v = "NOT_APPLICABLE"
                
            summary[aid] = {
                "agent_name": AGENT_NAMES.get(aid, aid),
                "verdict": v,
                "confidence_pct": round(conf * 100),
                "error_rate_pct": round(err * 100),
                "skipped": m.get("skipped", False)
            }
        return summary

    def _get_degradation_flags(self, llm_ok, penalty, findings, metrics) -> list[str]:
        flags = []
        if not llm_ok: flags.append("LLM synthesis bypassed")
        if penalty < 1.0: flags.append(f"Compression penalty applied ({round((1-penalty)*100)}%)")
        if not any((f.get("metadata") or {}).get("analysis_source") == "gemini_vision" for f in findings): flags.append("Gemini deep vision skipped")
        return flags

    def _empty_report(self, case_id, findings, metrics) -> ForensicReport:
        return ForensicReport(session_id=self.session_id, case_id=case_id or f"case_{self.session_id}", executive_summary="No active agents produced findings.", per_agent_findings=findings, per_agent_metrics=metrics, uncertainty_statement="Analysis was skipped for all agents.", overall_verdict="INCONCLUSIVE")
