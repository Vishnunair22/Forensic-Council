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
    AgentMetrics,
    ChallengeResult,
    FindingComparison,
    FindingVerdict,
    ForensicReport,
    TribunalCase,
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


def _manipulation_probability(mapped_verdict: str, confidence: float) -> float:
    """Graduated P(manipulated) by verdict band × confidence.

    Replaces the prior binary rule (confidence if MANIPULATED else 0.0), which
    reported 0.0 manipulation probability for SUSPICIOUS / LIKELY_MANIPULATED
    files — misrepresenting genuinely suspicious evidence on the report gauge.
    """
    v = (mapped_verdict or "").upper()
    c = max(0.0, min(1.0, confidence))
    if v == "MANIPULATED":
        return round(max(0.75, c), 3)          # strong, floored at 0.75
    if v == "SUSPICIOUS":
        return round(0.50 + 0.25 * c, 3)        # 0.50–0.75 band
    if v == "AUTHENTIC":
        return round(0.15 * (1.0 - c), 3)       # high confidence → near 0
    return 0.5                                   # INCONCLUSIVE — genuine uncertainty

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
        # Original uploaded filename for report narration. Set by the pipeline
        # after evidence ingest; falls back to tool metadata / "evidence_file".
        self.original_filename: str | None = None
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
        self._pre_warm_task: asyncio.Task | None = None

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

        # Await pre-warm task if still running — avoids redundant deliberate() call
        if self._pre_warm_task is not None and not self._pre_warm_task.done():
            try:
                await asyncio.wait_for(self._pre_warm_task, timeout=30.0)
            except TimeoutError:
                logger.warning("Pre-warm task still running after 30s wait; proceeding independently")
            except Exception as exc:
                logger.warning("Pre-warm task failed during await", error=str(exc))

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
            # Sign even the empty report so the court-defensibility invariant holds:
            # every ForensicReport that leaves the arbiter carries a valid signature.
            empty = self._empty_report(case_id, per_agent_findings, per_agent_metrics)
            return await self.sign_report(empty)

        # ── 2. Reliability & Scoring ─────────────────────────────────────
        active_metrics = [
            m
            for m in per_agent_metrics.values()
            if not m.get("skipped") and m.get("total_tools_called", 0) > 0
        ]
        # Only the error rate is consumed downstream — the final overall_confidence
        # comes from deliberate_findings (and per-agent confidence spread from
        # active_metrics directly), so the weighted-confidence return is discarded.
        _, overall_error_rate = self._calculate_weighted_stats(active_metrics)

        # ── 3. Tool Coverage ──
        completed_tools = []
        failed_tools = []
        not_applicable_tools = []
        degraded_tools = []
        for _aid, res in active_results.items():
            findings = res.get("findings", [])
            for f in findings:
                meta = f.get("metadata") or {}
                tool = meta.get("tool_name") or f.get("finding_type") or "tool"
                status = f.get("status")
                evidence_verdict = f.get("evidence_verdict")

                # A tool "completed" if it produced a verdict and did not fail or
                # opt out. Finding status is CONFIRMED/INCONCLUSIVE/etc. (never the
                # literal "SUCCESS"), so classify by failure/NA first, then treat
                # everything else as completed — otherwise completed_tools is always
                # empty and the deliberation wrongly reads INCONCLUSIVE_LIMITED_COVERAGE.
                if status in ("FAILED", "ERROR", "TIMEOUT", "INCOMPLETE") or evidence_verdict == "ERROR":
                    failed_tools.append(tool)
                elif status == "NOT_APPLICABLE" or evidence_verdict == "NOT_APPLICABLE":
                    not_applicable_tools.append(tool)
                else:
                    completed_tools.append(tool)
                    # A tool that completed in a reduced-fidelity fallback path is a
                    # coverage limitation even though it did not error — the report's
                    # degradation notice surfaces it, so the executive summary must
                    # not simultaneously claim "without errors, full coverage".
                    if meta.get("degraded") or meta.get("fallback_reason"):
                        degraded_tools.append(tool)

        completed_tools = list(set(completed_tools))
        failed_tools = list(set(failed_tools))
        not_applicable_tools = list(set(not_applicable_tools))
        degraded_tools = list(set(degraded_tools))
        tool_coverage = {
            "completed_tools": completed_tools,
            "failed_tools": failed_tools,
            "not_applicable_tools": not_applicable_tools,
            "degraded_tools": degraded_tools,
        }

        # ── 4. Retrieve Visual Context & Per-Agent Synthesis ──
        from core.visual_context_store import get_visual_context
        visual_context = await get_visual_context(
            session_id=str(self.session_id), inter_agent_bus=self.inter_agent_bus
        )

        # ── Corroboration grounding (applied to the FINDINGS, before both the
        #    per-agent card verdict and the arbiter overall verdict, so they agree) ──
        # A lone integrity POSITIVE the holistic visual model (Gemini) does not
        # corroborate is, in practice, a false positive on a processed/recompressed
        # real photo. Downgrade such uncorroborated integrity positives to
        # INCONCLUSIVE. Requires Gemini available & clean and fewer than 2 strong,
        # court-defensible agreeing integrity signals. Provenance/content-risk
        # signals and hard evidence (hash mismatch) are not touched.
        # Reliability-honesty flag (reset per investigation): set when a strong
        # AI-generation signal is held inconclusive ONLY because the holistic
        # provider was local-only (no remote corroboration) — used downstream to
        # cap confidence + disclose, so an API-failure/no-Gemini "Authentic" is
        # never over-confident on a possible synthetic image.
        self._uncorroborated_ai_gen_local = False
        try:
            from core.severity import (
                NON_INTEGRITY_TOOLS,
                holistic_read_flags_manipulation,
            )
            _vc_clean = False
            if visual_context is not None:
                _vi = getattr(visual_context, "image_integrity_context", None)
                _ass = str(getattr(_vi, "integrity_assessment", "") or "").lower() if _vi else ""
                _av = str(getattr(visual_context, "authenticity_verdict", "") or "")
                _vc_clean = not holistic_read_flags_manipulation(_av, _ass)
            # Screening-tier heuristics that co-fire on JPEG recompression — they are
            # correlated, not independent, so they do not corroborate one another or
            # the ML detectors. Excluded from the strong-corroborator count (but still
            # downgraded along with the rest when the cluster is uncorroborated).
            _screening = {
                "neural_copy_move", "copy_move_detector", "neural_splicing",
                "splicing_detector", "neural_ela", "error_level_analysis",
                "frequency_domain_analysis",
            }
            _int_pos = []
            for _res in active_results.values():
                for _f in _res.get("findings", []):
                    _m = _f.get("metadata") or {}
                    _tool = _m.get("tool_name") or _f.get("finding_type") or ""
                    if str(_f.get("evidence_verdict")).upper() == "POSITIVE" and _tool not in NON_INTEGRITY_TOOLS:
                        _int_pos.append((_tool, _f))
            _strong = sum(
                1 for _tool, _f in _int_pos
                if _tool not in _screening
                and (_f.get("confidence_raw") or (_f.get("metadata") or {}).get("confidence") or 0) >= 0.7
                and (_f.get("metadata") or {}).get("court_defensible", True)
            )
            # A real, court-defensible TRAINED-MODEL detection (TruFor splicing
            # localization) is authoritative on its own: it sees pixel-level
            # forgeries that are invisible to the holistic vision model, so a clean
            # Gemini read must NOT clear it. When TruFor confirms a forgery, skip
            # the uncorroborated-positive downgrade entirely (the image is
            # manipulated, so the co-firing signals are not false positives).
            _trufor_detected = any(
                str((_f.get("metadata") or {}).get("tool_name") or _f.get("finding_type") or "") == "neural_splicing"
                and str(_f.get("evidence_verdict")).upper() == "POSITIVE"
                and (_f.get("metadata") or {}).get("court_defensible", False)
                and max(
                    float(_f.get("confidence_raw") or 0.0),
                    float((_f.get("metadata") or {}).get("confidence") or 0.0),
                ) >= 0.5
                for _res in active_results.values()
                for _f in _res.get("findings", [])
            )
            if visual_context is not None and _vc_clean and _int_pos and _strong < 2 and not _trufor_detected:
                for _tool, _f in _int_pos:
                    _f["evidence_verdict"] = "INCONCLUSIVE"
                    # A signal held inconclusive as a benign, uncorroborated artifact
                    # is no longer a HIGH-severity manipulation indicator — drop the
                    # tier so it stops reading as a strong alert in the verdict math,
                    # section flags, and finding ordering.
                    _f["severity_tier"] = "LOW"
                    _meta = _f.setdefault("metadata", {})
                    _meta["severity_tier"] = "LOW"
                    _meta["corroboration_downgrade"] = True
                    # Preserve the original alarming text for audit, but REWRITE the
                    # narrative so it matches the new INCONCLUSIVE verdict — appending
                    # left the original "manipulation detected" claim in place, which
                    # contradicted the downgraded verdict (item 7: verdict is authority).
                    _orig_summary = str(_f.get("reasoning_summary") or "").strip()
                    if _orig_summary:
                        _meta["pre_downgrade_summary"] = _orig_summary
                    from core.severity import uncorroborated_screening_text
                    _downgraded_text = uncorroborated_screening_text(_tool)
                    # Rewrite EVERY narrative field, not just reasoning_summary. The
                    # key-findings formatter (per_agent_synthesis.format_finding_first)
                    # and the evidence-card outcome text prefer metadata.key_signal /
                    # summary; leaving the original POSITIVE detection text there
                    # surfaced an assertive "X detected (prob 0.99)" key finding and a
                    # "N anomalies flagged" overview beneath an INCONCLUSIVE/AUTHENTIC
                    # verdict (the natural-image false-positive narrative class).
                    _f["reasoning_summary"] = _downgraded_text
                    _f["summary"] = _downgraded_text
                    _meta["summary"] = _downgraded_text
                    _meta["key_signal"] = _downgraded_text
                logger.info(f"Corroboration grounding downgraded {len(_int_pos)} uncorroborated integrity positive(s)")
        except Exception as _corr_err:
            logger.debug("Corroboration grounding skipped", error=str(_corr_err))

        from core.per_agent_synthesis import (
            AgentSynthesisInput,
            compose_evidence_identity,
            refine_synthesis_batch,
            split_visual_context,
        )
        splits = split_visual_context(str(self.session_id), visual_context)
        # Compose the shared "what the evidence appears to be" fragment once so
        # all three agent briefs open with consistent observed context.
        evidence_identity = compose_evidence_identity(visual_context)

        from core.severity import assign_severity_tier, compute_agent_verdict
        from core.visual_context_store import visual_context_to_profile_dict
        from core.visual_grounding import apply_visual_grounding

        # Build the grounding profile + holistic read once. A remote-vision
        # (Gemini) read is court-defensible and authoritative; a local-ensemble
        # read is screening-tier (mirrors visual_context_to_profile_dict).
        _vc_profile = (
            visual_context_to_profile_dict(visual_context) if visual_context is not None else None
        )
        _is_remote_vision = bool(
            visual_context is not None
            and getattr(visual_context, "external_llm_used", False)
            and getattr(visual_context, "source", "") != "local_ensemble"
        )
        _holistic_verdict = (
            str(getattr(visual_context, "authenticity_verdict", "") or "").upper()
            if visual_context is not None
            else ""
        )

        # Determine whether this is a deep-analysis run before building synthesis inputs
        # so we can pass is_deep + Phase-1 context to the synthesis and Groq prompt.
        _has_deep = any(
            str((f.get("metadata") or {}).get("analysis_phase") or "").lower() == "deep"
            for f in all_findings
        )

        inputs = {}
        # Capture the grounded, visual-context-aware per-agent verdicts so the card
        # badge (per_agent_summary) reuses the SAME value as the synthesis brief —
        # otherwise the badge recomputes tool-only/ungrounded and silently drifts.
        grounded_agent_verdicts: dict[str, tuple[str, float]] = {}
        # ALL applicable agents, not just the image pipeline. Audio (Agent2) and
        # video (Agent4) were previously excluded here, so audio/video evidence got
        # no grounded per-agent verdict and no structured synthesis/narrative from
        # the arbiter — the result page fell back to raw findings, contradicting the
        # holistic-driven verdict. They now flow through the same synthesis path.
        for aid in ("Agent1", "Agent2", "Agent3", "Agent4", "Agent5"):
            if aid in active_results:
                res = active_results[aid]
                findings = res.get("findings", [])

                # Check visual context applicability
                vc_avail = False
                vc_sec = None
                if aid == "Agent1" and splits.agent1_image_integrity:
                    vc_avail = True
                    vc_sec = splits.agent1_image_integrity
                elif aid == "Agent3" and splits.agent3_object_scene:
                    vc_avail = True
                    vc_sec = splits.agent3_object_scene
                elif aid == "Agent5" and splits.agent5_metadata_visual:
                    vc_avail = True
                    vc_sec = splits.agent5_metadata_visual

                a_completed = []
                a_failed = []
                for f in findings:
                    meta = f.get("metadata") or {}
                    tool = meta.get("tool_name") or f.get("finding_type") or "tool"
                    status = f.get("status")
                    if status == "SUCCESS":
                        a_completed.append(tool)
                    elif status in ("FAILED", "ERROR", "TIMEOUT"):
                        a_failed.append(tool)

                # Ground each finding's severity against the visual context so the
                # verdict math and the key findings read the SAME calibrated tiers
                # (camera-physics noise on screenshots capped, cross-modal conflicts
                # annotated). grounded_findings is what synthesis and the verdict
                # both consume — previously declared but never populated.
                grounded_findings = []
                for f in findings:
                    gf = dict(f)
                    meta = gf.get("metadata") or {}
                    tool = str(meta.get("tool_name") or gf.get("finding_type") or "")
                    base_sev = str(gf.get("severity_tier") or assign_severity_tier(gf))
                    if _vc_profile is not None:
                        gr = apply_visual_grounding(tool, aid, base_sev, _vc_profile, meta)
                        gf["severity_tier"] = gr.adjusted_severity
                        # Persist the grounded severity onto the ORIGINAL finding
                        # (shared with all_findings) so deliberate_findings honours
                        # the same caps the badge does — single source of grounding.
                        if gr.grounded:
                            f["severity_tier"] = gr.adjusted_severity
                            meta["severity_tier"] = gr.adjusted_severity
                        _new_meta = dict(meta)
                        if gr.context_note:
                            _new_meta["grounding_note"] = gr.context_note
                        # Apply the grounding confidence scale (≤1.0) — de-weights
                        # camera-physics noise on non-camera images so the verdict
                        # math and report reflect the calibrated confidence, not the
                        # raw tool score. Only ever reduces, never inflates.
                        if gr.confidence_scale < 1.0:
                            for _ck in ("confidence_raw", "confidence"):
                                _cv = gf.get(_ck)
                                if isinstance(_cv, (int, float)):
                                    gf[_ck] = round(float(_cv) * gr.confidence_scale, 4)
                                _mv = _new_meta.get(_ck)
                                if isinstance(_mv, (int, float)):
                                    _new_meta[_ck] = round(float(_mv) * gr.confidence_scale, 4)
                            _new_meta["grounding_confidence_scale"] = gr.confidence_scale
                        if _new_meta != meta:
                            gf["metadata"] = _new_meta
                    else:
                        gf["severity_tier"] = base_sev
                    grounded_findings.append(gf)

                # Per-agent visual signal for verdict grounding. Agent1 carries the
                # holistic authenticity read; Agent3 inherits it only when the whole
                # image is synthetic/manipulated (scene relevance); Agent5 stays on
                # provenance and only weighs metadata contradictions.
                _sec = vc_sec or {}
                if aid == "Agent1":
                    _vsig = {
                        "verdict": _holistic_verdict,
                        "court_defensible": _is_remote_vision,
                        "anomalies": list(_sec.get("ai_generation_signals") or []),
                    }
                elif aid == "Agent3":
                    _vsig = {
                        "verdict": _holistic_verdict
                        if _holistic_verdict in ("AI_GENERATED", "LIKELY_MANIPULATED")
                        else "",
                        "court_defensible": _is_remote_vision,
                        "anomalies": list(_sec.get("scene_inconsistencies") or []),
                    }
                else:  # Agent5
                    _vsig = {
                        "verdict": "",
                        "court_defensible": _is_remote_vision,
                        "anomalies": list(_sec.get("metadata_contradictions") or []),
                    }

                # Deterministic, severity-aware, visual-context-grounded per-agent
                # verdict / confidence. Pass is_deep so the holistic visual read
                # carries elevated weight in the deep-analysis verdict.
                a_verdict, a_conf, a_reason = compute_agent_verdict(
                    grounded_findings, visual_signal=_vsig, is_deep=_has_deep
                )
                grounded_agent_verdicts[aid] = (a_verdict, a_conf)
                # Parity: _compute_agent_metrics ran BEFORE grounding (ungrounded,
                # no visual_signal). Overwrite its confidence_score with this
                # grounded value so the metrics card and the verdict badge show the
                # exact same per-agent confidence.
                if aid in per_agent_metrics and not per_agent_metrics[aid].get("skipped"):
                    per_agent_metrics[aid]["confidence_score"] = a_conf

                # Pull Phase-1 verdict/confidence from the agent synthesis dict
                # (written by run_deep_investigation) so the Groq prompt can frame
                # the phase comparison sentence correctly.
                _aid_syn = (res.get("synthesis") or {}) if isinstance(res.get("synthesis"), dict) else {}
                _p1_v = str(_aid_syn.get("phase1_verdict") or "")
                _p1_c = float(_aid_syn.get("phase1_confidence") or 0.0)

                inputs[aid] = AgentSynthesisInput(
                    agent_id=aid,
                    persona_name=aid,
                    persona_rules={},
                    visual_context_available=vc_avail,
                    visual_context_section=vc_sec,
                    evidence_identity=evidence_identity,
                    completed_tools=list(set(a_completed)),
                    failed_tools=list(set(a_failed)),
                    findings=findings,
                    grounded_findings=grounded_findings,
                    agent_verdict=a_verdict,
                    agent_confidence=a_conf,
                    confidence_reason=a_reason,
                    is_deep_analysis=_has_deep,
                    phase1_verdict=_p1_v,
                    phase1_confidence=_p1_c,
                )

        agent_syntheses = await refine_synthesis_batch(inputs, self.config)

        # ── 5. Arbiter Deliberation ──
        from core.arbiter_deliberation import deliberate_findings
        deliberation_result = deliberate_findings(
            all_findings, visual_context, tool_coverage, mime_type=artifact_mime
        )

        # ── 6. Deterministic Report Builder ──
        from core.deterministic_report_builder import build_deterministic_report
        # Prefer the authoritative original filename threaded from the upload
        # (the case_id is NOT a filename — using it rendered "Forensic
        # examination of `CASE-…`"; an empty case_id fell back to the generic
        # "the submitted file" via tool metadata). Tool metadata is only a
        # fallback when the real filename was not provided.
        _orig_name = getattr(self, "original_filename", None)
        case_data = {
            "case_id": case_id or f"case_{self.session_id}",
            "session_id": str(self.session_id),
            "filename": _orig_name or "evidence_file",
            "sha256": "unknown_hash",
            "mime_type": artifact_mime or "image/png"
        }
        for f in all_findings:
            meta = f.get("metadata") or {}
            if not _orig_name and (meta.get("file_name") or meta.get("filename")):
                case_data["filename"] = meta.get("file_name") or meta.get("filename")
            if meta.get("file_hash") or meta.get("sha256"):
                case_data["sha256"] = meta.get("file_hash") or meta.get("sha256")
            if meta.get("mime_type"):
                case_data["mime_type"] = meta.get("mime_type")
            if meta.get("file_size"):
                case_data["file_size_bytes"] = meta.get("file_size")

        execution_metadata = {
            "analysis_mode": self.config.analysis_routing_mode if hasattr(self.config, "analysis_routing_mode") else "hybrid",
            "visual_context_source": getattr(visual_context, "source", "none") if visual_context else "none",
        }

        # ── Verdict mapping + derived metrics (computed BEFORE the report build
        #    so the narrative label and the verdict field can never disagree) ──
        mapped_verdict = "INCONCLUSIVE"
        v_upper = (deliberation_result.final_verdict or "INCONCLUSIVE").upper()
        if "LIKELY_MANIPULATED" in v_upper:
            mapped_verdict = "MANIPULATED"
        elif "SUSPICIOUS" in v_upper or "PROVENANCE" in v_upper or "CONTENT_RISK" in v_upper:
            mapped_verdict = "SUSPICIOUS"
        elif "NO_REPORTABLE_MANIPULATION_DETECTED" in v_upper:
            mapped_verdict = "AUTHENTIC"

        # Reliability honesty — detect the dangerous no-Gemini case independent of
        # WHERE the corroboration downgrade happened (agent grounding vs arbiter):
        # a dedicated AI-generation detector RAW-detected synthesis, the holistic
        # read was local-only (no remote vision to corroborate), and the verdict
        # still came out AUTHENTIC. Keyed off the detector's own tool output (which
        # survives any verdict downgrade), so it fires whether the positive was held
        # inconclusive upstream or here. A genuinely clean detector run (NEGATIVE /
        # low score) does NOT match, so the authentic majority is untouched.
        if mapped_verdict == "AUTHENTIC":
            _AI_GEN_TOOLS = {"diffusion_artifact_detector", "ai_generation_detector"}
            _holistic_local_only = (
                visual_context is None
                or str(getattr(visual_context, "source", "") or "") == "local_ensemble"
                or not getattr(visual_context, "external_llm_used", False)
            )
            if _holistic_local_only:
                for _f in all_findings:
                    if not isinstance(_f, dict):
                        continue
                    _m = _f.get("metadata") or {}
                    _tool = _m.get("tool_name") or _f.get("finding_type") or ""
                    if _tool not in _AI_GEN_TOOLS:
                        continue
                    try:
                        _prob = float(_m.get("diffusion_probability") or _m.get("confidence_raw") or _m.get("confidence") or 0.0)
                    except (TypeError, ValueError):
                        _prob = 0.0
                    if (
                        bool(_m.get("is_ai_generated"))
                        or str(_m.get("predicted_label") or "").lower() == "artificial"
                        or bool(_m.get("corroboration_downgrade"))
                        or str(_f.get("evidence_verdict") or "").upper() == "POSITIVE"
                        or _prob >= 0.70
                    ):
                        self._uncorroborated_ai_gen_local = True
                        break

        # Reliability honesty: cap an AUTHENTIC verdict's confidence when a local
        # AI-generation signal was held inconclusive purely for lack of a holistic
        # corroborator (no-Gemini / API-failure path). Done BEFORE _final_conf is
        # read so the verdict line, overall_confidence, manipulation probability,
        # and the deterministic report all reflect the capped value consistently.
        if getattr(self, "_uncorroborated_ai_gen_local", False) and mapped_verdict == "AUTHENTIC":
            _AI_GEN_CONF_CAP = 0.70
            if deliberation_result.final_confidence > _AI_GEN_CONF_CAP:
                logger.info(
                    "Confidence capped — uncorroborated local AI-generation signal "
                    "(holistic review unavailable)",
                    from_confidence=round(deliberation_result.final_confidence, 3),
                    cap=_AI_GEN_CONF_CAP,
                )
                deliberation_result.final_confidence = _AI_GEN_CONF_CAP

        _final_conf = deliberation_result.final_confidence
        manipulation_probability = _manipulation_probability(mapped_verdict, _final_conf)

        # Real confidence spread from the per-agent confidences (was hardcoded 0.0),
        # giving the report a genuine cross-agent discord/spread metric.
        _agent_confs = [
            float(m.get("confidence_score") or 0.0)
            for m in active_metrics
            if m.get("confidence_score") is not None and not m.get("skipped")
        ]
        if _agent_confs:
            import statistics as _stats
            confidence_min = round(min(_agent_confs), 3)
            confidence_max = round(max(_agent_confs), 3)
            confidence_std_dev = round(_stats.pstdev(_agent_confs), 3) if len(_agent_confs) > 1 else 0.0
        else:
            confidence_min = confidence_max = round(_final_conf, 3)
            confidence_std_dev = 0.0

        det_report_dict = build_deterministic_report(
            case_data=case_data,
            visual_context=visual_context,
            agent_syntheses=agent_syntheses,
            arbiter_deliberation=deliberation_result,
            tool_coverage=tool_coverage,
            execution_metadata=execution_metadata,
            groq_used=False,
            display_verdict=mapped_verdict,
        )

        # ── 7. Optional Groq Polish ──
        # P0.4 — hash the deterministic baseline BEFORE any LLM refinement so the
        # signed report carries proof of what the deterministic pipeline produced.
        import hashlib as _hashlib
        import json as _json
        _baseline_blob = _json.dumps(det_report_dict, sort_keys=True, default=str, ensure_ascii=False)
        _baseline_sha256 = _hashlib.sha256(_baseline_blob.encode("utf-8")).hexdigest()
        final_report_dict = det_report_dict
        groq_used = False
        if use_llm:
            from core.final_report_groq_refiner import refine_report_with_groq
            refined, success = await refine_report_with_groq(det_report_dict, self.config)
            if success:
                final_report_dict = refined
                groq_used = True

        # Disclose the uncorroborated AI-generation signal in the executive summary
        # (paired with the confidence cap above) so a reader of the report knows the
        # authenticity finding is provisional for lack of a holistic corroborator.
        if getattr(self, "_uncorroborated_ai_gen_local", False) and mapped_verdict == "AUTHENTIC":
            _ai_gen_caveat = (
                " Reliability note: an on-device AI-generation detector flagged this "
                "image, but no holistic vision model was available to corroborate it, "
                "so the signal was held inconclusive and this authenticity finding is "
                "provisional — recommend re-review with a holistic vision model before "
                "relying on it."
            )
            try:
                _es = str(final_report_dict.get("executive_summary") or "").rstrip()
                if "Reliability note:" not in _es:
                    final_report_dict["executive_summary"] = _es + _ai_gen_caveat
            except Exception:
                pass

        # ── 8. Mapping Back to ForensicReport Pydantic Model ──
        # (mapped_verdict + derived metrics computed above, before report build)
        p_anal = {}
        p_anal_structured = {}
        for aid, syn in agent_syntheses.items():
            p_anal[aid] = syn.agent_brief
            entry = {
                "agent_brief": syn.agent_brief,
                "visual_description": syn.visual_context_summary,
                "key_findings": "\n".join(syn.key_findings),
                "opinion": syn.confidence_reason,
                "synthesis_source": syn.synthesis_source,
            }
            # Surface the deep-vs-initial delta the agent computed in its deep
            # synthesis, plus the Groq-polished phase_comparison sentence when present.
            _agent_syn = (active_results.get(aid) or {}).get("synthesis") or {}
            if isinstance(_agent_syn, dict):
                _phase_delta = str(_agent_syn.get("phase_delta") or "").strip().upper()
                _delta_reason = str(_agent_syn.get("delta_reason") or "").strip()
                if _phase_delta and _phase_delta not in ("", "N/A"):
                    entry["phase_delta"] = _phase_delta
                    if _delta_reason:
                        entry["delta_reason"] = _delta_reason
            # Groq-polished phase comparison sentence (deep mode only)
            _pc = str(getattr(syn, "phase_comparison", "") or "").strip()
            if _pc:
                entry["phase_comparison"] = _pc
            p_anal_structured[aid] = entry

        degradation_flags = self._get_degradation_flags(
            llm_ok=groq_used,
            penalty=1.0,
            findings=all_findings,
            metrics=per_agent_metrics,
            narrative_warnings=[],
            llm_synthesis_failed=False,
            mime_type=artifact_mime,
        )

        summary_structured = {
            "verdict_line": f"{mapped_verdict.title()} at {int(deliberation_result.final_confidence * 100 + 0.5)}% confidence.",
            "integrity_lines": [f.finding_statement for f in deliberation_result.strongest_findings if f.signal_category == "integrity"],
            "context_lines": [f.finding_statement for f in deliberation_result.supporting_findings],
            "coverage_line": final_report_dict.get("methodology") or "Completed analysis."
        }

        comparisons = await cross_agent_comparison(all_findings)
        contested = await self._run_challenges(comparisons)

        # ── 9. Case Finalisation ──
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

        # Page-level "what this shows" context — descriptive scene + file type +
        # source provenance from the pre-flight VisualContext. Shown ONCE at the
        # top of the evidence page; never a verdict.
        evidence_summary: dict[str, Any] = {}
        if visual_context is not None:
            _scene = str(getattr(visual_context, "scene_description", "") or "").strip()
            _ftype = str(getattr(visual_context, "file_type_assessment", "") or "").strip()
            _remote = bool(
                getattr(visual_context, "external_llm_used", False)
                and getattr(visual_context, "source", "") == "llm_assisted"
            )
            if _scene or _ftype:
                evidence_summary = {
                    "scene_description": _scene,
                    "file_type_assessment": _ftype,
                    "source": "remote_vision" if _remote else "on_device",
                    "court_defensible": _remote,
                }
                # Full holistic-read details — the complete content/provenance the
                # vision/media model surfaced, rendered collapsed under the summary on
                # the result page. Same VisualContext for every modality (image scene,
                # audio/video media profile, document text), so the consolidated block
                # reads coherently for all supported file types. NOT a verdict —
                # manipulation/AI signals here are already verdict-gated upstream
                # (build_visual_context_from_finding only fills them on an alert read).
                def _strs(items, limit=24):
                    # A bare string is a single value, not an iterable of characters
                    # (metadata_consistency_notes can arrive as str OR list[str]).
                    if isinstance(items, str):
                        items = [items] if items.strip() else []
                    out = []
                    for it in (items or []):
                        if isinstance(it, str):
                            s = it
                        elif isinstance(it, dict):
                            s = it.get("label") or it.get("name") or ""
                        else:
                            s = getattr(it, "label", None) or str(it)
                        s = str(s or "").strip()
                        if s:
                            out.append(s)
                    return out[:limit]

                _osc = getattr(visual_context, "object_scene_context", None)
                _ii = getattr(visual_context, "image_integrity_context", None)
                _mv = getattr(visual_context, "metadata_visual_context", None)
                _details = {
                    "objects": _strs(getattr(_osc, "objects", None) or getattr(visual_context, "detected_objects", None)),
                    "people": _strs(getattr(_osc, "people", None)),
                    "weapons": _strs(getattr(_osc, "weapons_or_dangerous_items", None)),
                    "documents": _strs(getattr(_osc, "documents_or_ids", None)),
                    "extracted_text": _strs(getattr(visual_context, "extracted_text", None)),
                    "scene_inconsistencies": _strs(getattr(_osc, "scene_inconsistencies", None)),
                    "device_platform": _strs(getattr(_mv, "device_or_platform_clues", None)),
                    "software": _strs(getattr(_mv, "software_or_app_clues", None)),
                    "timestamps": _strs(getattr(_mv, "visible_timestamps", None)),
                    "location_clues": _strs(getattr(_mv, "visible_location_clues", None)),
                    "metadata_notes": _strs(getattr(_mv, "metadata_consistency_notes", None)),
                    "ai_generation_signals": _strs(getattr(_ii, "ai_generation_signals", None)),
                    "manipulation_signals": _strs(getattr(_ii, "visible_manipulation_signals", None)),
                }
                _integ = str(getattr(_ii, "integrity_assessment", "") or "").strip() if _ii is not None else ""
                if _integ and _integ.lower() not in ("cannot_determine", ""):
                    _details["integrity_assessment"] = _integ.replace("_", " ")
                # Keep only present fields so the frontend renders nothing empty.
                _details = {k: v for k, v in _details.items() if v}
                if _details:
                    evidence_summary["details"] = _details

        report = ForensicReport(
            session_id=self.session_id,
            case_id=case_id or f"case_{self.session_id}",
            executive_summary=final_report_dict["executive_summary"],
            is_deep_analysis=has_deep_findings,
            per_agent_findings=per_agent_findings,
            per_agent_metrics=per_agent_metrics,
            per_agent_analysis=p_anal,
            per_agent_narrative_structured=p_anal_structured,
            summary_structured=summary_structured,
            overall_confidence=deliberation_result.final_confidence,
            overall_error_rate=overall_error_rate,
            overall_verdict=mapped_verdict,
            cross_modal_confirmed=[
                c.finding_a
                for c in comparisons
                if c.verdict == FindingVerdict.AGREEMENT and c.cross_modal_confirmed
            ],
            contested_findings=contested,
            incomplete_findings=[f for f in all_findings if f.get("status") == "INCOMPLETE"],
            stub_findings=[f for f in all_findings if f.get("stub_result")],
            gemini_vision_findings=[f for fl in visual_profile_findings_by_agent.values() for f in fl],
            uncertainty_statement=final_report_dict["limitations"][0] if final_report_dict["limitations"] else "None",
            verdict_sentence=final_report_dict["final_conclusion"],
            key_findings=final_report_dict["key_findings"],
            evidence_summary=evidence_summary,
            reliability_note=final_report_dict["reliability_notes"][0] if final_report_dict["reliability_notes"] else "",
            manipulation_probability=manipulation_probability,
            confidence_min=confidence_min,
            confidence_max=confidence_max,
            confidence_std_dev=confidence_std_dev,
            per_agent_summary=self._get_agent_summary(
                per_agent_metrics, per_agent_findings, precomputed=grounded_agent_verdicts
            ),
            degradation_flags=degradation_flags,
            applicable_agent_count=len(active_results),
            skipped_agents=skipped_agents,
            analysis_coverage_note=final_report_dict["methodology"],
            cross_modal_fusion=_fusion,
            compression_penalty=1.0,
        )

        # P0.4 — embed the deterministic-baseline hash in the signed payload.
        report.deterministic_baseline_sha256 = _baseline_sha256

        return await self.sign_report(report)

    def _deduplicate_findings(self, findings: list[dict]) -> list[dict]:
        """
        Single-pass deduplication keyed by (tool_name, evidence_verdict, analysis_phase).

        Preserves forensic contradictions (same tool, different verdicts) while
        keeping deep and initial findings separate so the report can show
        phase progression.

        Stages:
        1. Filter out template/stale findings
        2. Group by (tool_name, evidence_verdict, analysis_phase) key
        3. Within each group, merge similar findings, keeping the highest confidence
        """
        from collections import defaultdict

        if not findings:
            return []

        # Stage 0: Filter out template/stale findings
        from core.synthesis import TEMPLATE_PATTERNS
        cleaned = []
        for f in findings:
            if not isinstance(f, dict):
                logger.warning(
                    "Skipping non-dict finding during deduplication", type=type(f).__name__
                )
                continue
            summary = f.get("reasoning_summary") or f.get("finding_type") or ""
            meta = f.get("metadata") or {}
            refined = meta.get("llm_refined_summary") or ""
            if any(p in str(summary).lower() or p in str(refined).lower() for p in TEMPLATE_PATTERNS):
                continue
            if "severity_tier" not in f:
                f["severity_tier"] = assign_severity_tier(f)
            cleaned.append(f)

        if not cleaned:
            return []

        # Stage 1+2: Group by (tool_name, evidence_verdict, analysis_phase) and merge
        finding_groups = defaultdict(list)
        for f in cleaned:
            key = self._dedup_key(f)
            finding_groups[key].append(f)

        deduplicated = []
        for group in finding_groups.values():
            if len(group) == 1:
                deduplicated.append(group[0])
            else:
                merged = self._merge_similar_findings(group)
                deduplicated.append(merged)

        return deduplicated

    @staticmethod
    def _dedup_key(finding: dict) -> str:
        """Build dedup key from (tool_name, evidence_verdict, analysis_phase)."""
        meta = finding.get("metadata") or {}
        tool = str(meta.get("tool_name", ""))
        evidence_verdict = evidence_verdict_of(finding)
        phase = meta.get("analysis_phase", "initial")
        return f"{tool}:{evidence_verdict}:{phase}"

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
        # Agent confidence comes from the single severity-aware authority
        # (compute_agent_verdict), the SAME function that produces the per-agent
        # summary badge — so the metrics confidence_score and the badge agree.
        # The prior mean-of-raw-confidence averaged heterogeneous per-tool scores
        # (e.g. ELA 0.23 + fingerprint 0.95) into a meaningless ~0.48 that
        # contradicted the badge's graduated confidence.
        from core.severity import compute_agent_verdict as _cav
        _agent_verdict, avg_conf, _ = _cav(real)
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
        # File-type-specific thresholds via ForensicPolicy
        thresholds = ForensicPolicy.get_verdict_thresholds(mime_type)
        _manipulated_threshold = thresholds["manipulated"]
        _likely_manipulated_threshold = thresholds["likely_manipulated"]
        _suspicious_threshold = thresholds["suspicious"]
        _authentic_conf_threshold = thresholds["authentic_conf"]
        _likely_authentic_conf_threshold = thresholds["likely_authentic_conf"]

        if (
            manipulation_probability >= _manipulated_threshold
            and manipulation_signals >= ForensicPolicy.MANIP_SIGNAL_MIN_REQUIRED
        ):
            return "MANIPULATED"

        elif (
            manipulation_probability >= _likely_manipulated_threshold
            and manipulation_signals >= ForensicPolicy.MANIP_SIGNAL_MIN_REQUIRED
        ):
            # P0.6 — removed the dead `signals == 1 and prob >= SINGLE_SIGNAL_MANIP_THRESHOLD`
            # branch: a solo signal is hard-capped at 0.45 (arbiter_verdict.py), so the
            # 0.85 threshold was unreachable. Hash mismatch — the one signal that may
            # stand alone — is already escalated separately in arbiter_deliberation. A
            # proper tiered single-signal rule (P1.9) must wait for validated tool weights
            # (P1.12) rather than build on unvalidated ones.
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

    def _get_agent_summary(self, metrics, findings, precomputed: dict | None = None) -> dict:
        # Use the single severity-aware compute_agent_verdict so the per-agent card
        # verdict matches the rest of the pipeline. When the caller already computed
        # the grounded, visual-context-aware verdict (Agent1/3/5 in deliberate), reuse
        # it verbatim so the badge can never drift from the synthesis brief. Agents
        # without a precomputed value (Agent2/Agent4, empty-report path) fall back to
        # a fresh tool-only computation.
        from core.severity import compute_agent_verdict

        precomputed = precomputed or {}
        summary = {}
        for aid, m in metrics.items():
            err = m.get("error_rate", 0)
            agent_findings = findings.get(aid, [])
            if m.get("skipped"):
                v, conf = "NOT_APPLICABLE", 0.0
            elif aid in precomputed:
                v, conf = precomputed[aid]
            else:
                v, conf, _reason = compute_agent_verdict(agent_findings)
            summary[aid] = {
                "agent_name": AGENT_NAMES.get(aid, aid),
                "verdict": v,
                "confidence_pct": round(conf * 100),
                "error_rate_pct": round(err * 100),
                "skipped": m.get("skipped", False),
            }
        return summary

    def _get_degradation_flags(self, llm_ok, penalty, findings, metrics, narrative_warnings: list[str] | None = None, llm_synthesis_failed: bool = False, mime_type: str = "") -> list[str]:
        flags = []
        for f in findings:
            meta = f.get("metadata") or {}
            tool = meta.get("tool_name") or f.get("finding_type") or "tool"
            if (
                f.get("status") in {"INCOMPLETE", "ERROR"}
                or f.get("evidence_verdict") == "ERROR"
                or meta.get("available") is False
                or meta.get("error")
            ):
                flags.append(f"{tool} failed or returned incomplete output")

        # P0.5 — disclose per-type reduced coverage so a reader is not misled into
        # treating a structurally limited analysis path as a full examination.
        _mt = (mime_type or "").lower()
        if _mt == "image/gif":
            flags.append(
                "Animated GIF: splicing, copy-move, and physical-scene checks were skipped "
                "(not applicable to this format) — coverage is reduced for this type."
            )
        if _mt.startswith("audio/") and not getattr(self.config, "enable_audio_models", False):
            flags.append(
                "Audio neural models are disabled — synthetic-speech and voice-clone detection "
                "ran at screening-tier capability only; a clean result does not exclude AI synthesis."
            )
        if _mt.startswith("video/") and not getattr(self.config, "enable_video_models", False):
            flags.append(
                "Video neural models are disabled — deepfake/frame-manipulation detection ran at "
                "screening-tier capability only; a clean result does not exclude AI synthesis."
            )
        return list(dict.fromkeys(flags))

    def _empty_report(self, case_id, findings, metrics) -> ForensicReport:
        return ForensicReport(
            session_id=self.session_id,
            case_id=case_id or f"case_{self.session_id}",
            executive_summary="No active agents produced findings.",
            per_agent_findings=findings,
            per_agent_metrics=metrics,
            uncertainty_statement="Analysis was skipped for all agents.",
            overall_verdict="ABSTAIN",
            per_agent_summary=self._get_agent_summary(metrics, findings),
            degradation_flags=[
                "REPORT_SYNTHESIZED_TEMPLATE_ZERO_AGENTS",
                "All agents failed or were skipped — no evidence was analyzed.",
            ],
            analysis_coverage_note="No applicable agents produced findings. ABSTAIN means no analysis was run, not that the evidence is authentic.",
        )

