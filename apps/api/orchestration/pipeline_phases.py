"""
Pipeline Phases
===============

Concurrent agent execution and HITL deep-analysis gate.
Extracted from pipeline.py to keep the orchestrator file under 400 lines.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any
from uuid import UUID

from core.agent_registry import AgentID
from core.media_kind import is_screen_capture_like
from core.structured_logging import get_logger
from core.tool_names import TOOL_VISUAL_PROFILE, is_visual_profile_tool
from orchestration.agent_factory import AgentLoopResult, _serialize_react_chain

if TYPE_CHECKING:
    from orchestration.pipeline import ForensicCouncilPipeline

logger = get_logger(__name__)


from core.findings_humanizer import _humanize_initial_finding, _is_discovery_finding, _verdict_score

PREVIEW_EXCLUDED_TOOLS = {"hash_verify", "custody_check", "file_type_validation"}
SCREENSHOT_PREVIEW_EXCLUDED_TOOLS = {
    "lighting_consistency",
    "lighting_correlation_initial",
    "shadow_validation",
    "scale_validation",
    "prnu_sensor_verification",
}


async def run_agents_concurrent(
    pipeline: ForensicCouncilPipeline,
    evidence_artifact,
    session_id: UUID,
) -> list[AgentLoopResult]:
    """
    Run all specialist agents in two phases:
      Phase 1 — concurrent initial passes
      HITL gate — await analyst decision
      Phase 2 — concurrent deep passes (if approved)
    """
    from core.agent_registry import get_agent_registry
    from core.observability import get_tracer

    _tracer = get_tracer("forensic-council.pipeline")

    # O-C-3: previously this span closed immediately because the function
    # body was unindented from the `with` block. Use start_span +
    # try/finally so the entire concurrent-agents phase is captured under
    # one span without bulk-reindenting 600 lines of body.
    _pac_span = _tracer.start_span("pipeline.run_agents_concurrent")
    try:
        _pac_span.set_attribute("session_id", str(session_id))
    except Exception:
        pass

    registry = get_agent_registry()

    # --- Broadcast helper ---------------------------------------------------

    async def _broadcast_agent_status(
        aid: str, status: str, message: str, findings=None, error=None, agent_inst=None,
        initial_tool_names: set | None = None,
        analysis_phase: str = "initial",
    ):
        try:
            from api.routes._session_state import AGENT_NAMES, broadcast_update
            from api.schemas import BriefUpdate
            from core.severity import assign_severity_tier
            from core.visual_grounding import apply_visual_grounding

            # Fetch the pre-flight visual context once per broadcast — used to
            # calibrate finding severity for all findings in this agent's batch.
            _visual_profile: dict | None = None
            if pipeline.inter_agent_bus is not None:
                try:
                    _visual_profile = pipeline.inter_agent_bus.get_visual_profile(str(session_id)) or None
                except Exception:
                    pass

            aname = AGENT_NAMES.get(aid, aid)
            preview = []

            # Humanized tool names for frontend progress display
            tool_display_names = {
                "extract_text_from_image": "Forensic OCR",
                "file_hash_verify": "Hash Verification",
                "analyze_image_content": "Semantic Audit",
                "frequency_domain_analysis": "FFT Noise Scan",
                "neural_fingerprint": "Neural Fingerprint",
                "diffusion_artifact_detector": "Diffusion Scan",
                "object_detection": "Structural Audit",
                "scene_incongruence": "Contextual Scan",
                "hex_signature_scan": "Binary Signature",
                "compression_risk_audit": "Compression Scan",
                "provenance_chain_verify": "C2PA Provenance",
                "timestamp_analysis": "Chronology Audit",
                "file_structure_analysis": "Structure Check",
                "visual_evidence_profile": "Visual Evidence Profile",
            }

            def _normalize_tool_name(raw: str) -> str:
                return tool_display_names.get(raw, raw.replace("_", " ").title())

            def _suppress_preview_tool(tool_name: Any) -> bool:
                tool_text = str(tool_name or "")
                if tool_text in PREVIEW_EXCLUDED_TOOLS:
                    return True
                return (
                    tool_text in SCREENSHOT_PREVIEW_EXCLUDED_TOOLS
                    and is_screen_capture_like(evidence_artifact)
                )

            def _resolve_image_context(agent_inst) -> str | None:
                if agent_inst is None:
                    return None
                tool_ctx = getattr(agent_inst, "_tool_context", {}) or {}
                visual_profile = (
                    tool_ctx.get(TOOL_VISUAL_PROFILE)
                    or {}
                )
                clip_result = tool_ctx.get("analyze_image_content") or {}
                content_type = str(visual_profile.get("content_type") or "").strip()
                clip_image_type = str(clip_result.get("image_type") or clip_result.get("semantic_context") or "").strip()
                base = ""
                if content_type and content_type.lower() not in ("", "unknown", "none"):
                    base = content_type
                elif clip_image_type and clip_image_type.lower() not in ("", "unknown", "none"):
                    base = clip_image_type

                # Fall back to the shared visual context threaded onto every agent
                # so Agent3 (object/scene) and Agent5 (metadata) show their own
                # visual axis live — not just Agent1's content type. This is the
                # live-page counterpart to the report's per-agent Visual Context.
                vctx = getattr(agent_inst, "visual_context", None)
                aid = str(getattr(agent_inst, "agent_id", "") or "")
                if vctx is not None:
                    try:
                        # The integrity pass carries a factual "what the image shows"
                        # description. It is the live counterpart to the report's
                        # per-agent Visual Context and is far more useful for the
                        # integrity (Agent1) and metadata (Agent5) axes than a bare
                        # content-type token ("photograph").
                        _integ = getattr(vctx, "image_integrity_context", None)
                        _desc = " ".join(str(getattr(_integ, "description", "") or "").split())
                        if len(_desc) <= 240:
                            identity = _desc
                        else:
                            _cut = _desc.rfind(". ", 0, 240)
                            identity = (
                                _desc[: _cut + 1]
                                if _cut > 80
                                else _desc[:240].rsplit(" ", 1)[0].rstrip(",;") + "…"
                            )
                        if aid == "Agent3":
                            objs = []
                            for o in (getattr(vctx, "detected_objects", None) or []):
                                lbl = getattr(o, "label", None) if not isinstance(o, dict) else o.get("label")
                                if lbl:
                                    objs.append(str(lbl))
                            scene = str(getattr(vctx, "scene_description", "") or "").strip()
                            parts = []
                            if scene:
                                parts.append(scene.rstrip("."))
                            if objs:
                                parts.append("objects: " + ", ".join(objs[:4]))
                            if parts:
                                return "; ".join(parts)
                        elif aid == "Agent5":
                            ftype = str(getattr(vctx, "file_type_assessment", "") or "").strip()
                            meta = getattr(vctx, "metadata_visual_context", None)
                            clues = [str(c) for c in (getattr(meta, "device_or_platform_clues", None) or []) if c]
                            if clues:
                                parts = []
                                if ftype:
                                    parts.append(ftype.replace("_", " "))
                                parts.append("clues: " + ", ".join(clues[:3]))
                                return "; ".join(parts)
                            # No live provenance clues: a bare file-type word is not a
                            # useful identity — fall back to the shared scene read.
                            if identity:
                                return identity
                        else:
                            # Agent1 / default: lead with the integrity description
                            # rather than a bare content-type token.
                            if identity:
                                return identity
                        if not base:
                            base = str(
                                getattr(vctx, "file_type_assessment", "")
                                or getattr(vctx, "scene_description", "")
                                or ""
                            ).strip()
                    except Exception:
                        pass
                return base or None

            synthesis = (
                getattr(agent_inst, "_agent_synthesis", None) if agent_inst is not None else None
            )
            agent_confidence = (
                getattr(agent_inst, "_agent_confidence", None) if agent_inst is not None else None
            )
            def _finding_attr(finding, key: str, default: Any = None) -> Any:
                if hasattr(finding, key):
                    return getattr(finding, key)
                if isinstance(finding, dict):
                    return finding.get(key, default)
                return default

            def _summary_for_finding(finding, metadata: dict[str, Any]) -> str:
                summary_candidates = (
                    metadata.get("llm_refined_summary"),
                    _finding_attr(finding, "reasoning_summary", ""),
                    metadata.get("raw_tool_summary"),
                    metadata.get("analysis_summary"),
                    metadata.get("summary"),
                    metadata.get("message"),
                    metadata.get("note"),
                    metadata.get("verdict"),
                    metadata.get("status"),
                )
                for candidate in summary_candidates:
                    text = str(candidate or "").strip()
                    if text:
                        return text

                tool_name = metadata.get("tool_name") or _finding_attr(
                    finding, "finding_type", "forensic tool"
                )
                evidence_verdict = str(_finding_attr(finding, "evidence_verdict", "")).upper()
                _label = str(tool_name).replace("_", " ").title()
                if evidence_verdict == "NEGATIVE":
                    return f"No anomaly detected ({_label})."
                if evidence_verdict == "POSITIVE":
                    return f"Forensic signal detected ({_label})."
                if evidence_verdict == "NOT_APPLICABLE":
                    return f"Not applicable to this file type ({_label})."
                if evidence_verdict == "ERROR":
                    return f"Did not complete — coverage gap, not evidence of authenticity ({_label})."
                return f"No determinate signal ({_label})."

            def _append_synthesis_sections(synthesis_data: dict[str, Any]) -> None:
                # Build actual_tools from the passed findings.
                # When findings is None (deep phase with no new tool findings), allow ALL
                # synthesis sections through so the deep card can still show LLM-refined summaries.
                actual_tools: set[str] = set()
                restrict_to_actual = bool(findings) or bool(initial_tool_names)
                for existing_finding in findings or []:
                    existing_meta = (
                        existing_finding.metadata
                        if hasattr(existing_finding, "metadata")
                        else existing_finding.get("metadata", {})
                        if isinstance(existing_finding, dict)
                        else {}
                    )
                    existing_tool = existing_meta.get("tool_name") or (
                        existing_finding.finding_type
                        if hasattr(existing_finding, "finding_type")
                        else existing_finding.get("finding_type")
                        if isinstance(existing_finding, dict)
                        else None
                    )
                    if existing_tool:
                        actual_tools.add(str(existing_tool))

                seen_synthesis_tools: set[str] = set()
                for section in synthesis_data.get("sections") or []:
                    refined = section.get("refined_findings") or []
                    for item in refined:
                        tool_name = str(item.get("tool") or "").strip()
                        if not tool_name:
                            continue
                        if restrict_to_actual and (
                            tool_name not in actual_tools
                            or (analysis_phase == "deep" and tool_name in (initial_tool_names or set()))
                        ):
                            continue
                        if _suppress_preview_tool(tool_name):
                            continue
                        if tool_name in seen_synthesis_tools:
                            continue
                        seen_synthesis_tools.add(tool_name)
                        summary = str(item.get("user_friendly_summary") or "").strip()
                        if not summary:
                            continue
                        preview.append(
                            {
                                "tool": _normalize_tool_name(tool_name),
                                "summary": summary[:560],
                                "severity": section.get("severity") or "LOW",
                                "verdict": str(synthesis_data.get("verdict") or "INCONCLUSIVE"),
                                "key_signal": "",
                                "confidence": synthesis_data.get("agent_confidence"),
                                "section": section.get("label") or "",
                                # A refined narrative section is NOT a degraded/fallback
                                # result just because LLM synthesis was off (deterministic
                                # is the normal free-tier path). Only flag genuine section
                                # degradation.
                                "degraded": bool(section.get("degraded")),
                                "fallback_reason": section.get("fallback_reason"),
                                "finding_kind": "discovery" if (section.get("severity") or "LOW") in ("HIGH", "CRITICAL", "MEDIUM") else "confirmation",
                            }
                        )

            if findings:
                seen_raw_tools: set[str] = set()
                for f in findings:
                    m = (
                        f.metadata
                        if hasattr(f, "metadata")
                        else f.get("metadata", {})
                        if isinstance(f, dict)
                        else {}
                    )
                    tool = m.get("tool_name") or (
                        f.finding_type if hasattr(f, "finding_type") else f.get("finding_type")
                    )

                    # Filter out low-signal/internal tools and non-applicable tools from the UI preview
                    if _suppress_preview_tool(tool):
                        continue
                    finding_ev = str(_finding_attr(f, "evidence_verdict", "")).upper()
                    finding_st = str(_finding_attr(f, "status", "")).upper()
                    if finding_ev == "NOT_APPLICABLE" or finding_st == "NOT_APPLICABLE":
                        continue
                    if (
                        aid == AgentID.AGENT5.value
                        and tool == "extract_text_from_image"
                        and is_screen_capture_like(evidence_artifact)
                    ):
                        continue

                    # Dedup by tool name — same tool running twice produces one card entry
                    tool_key = str(tool or "")
                    if tool_key and tool_key in seen_raw_tools:
                        continue

                    s = _summary_for_finding(f, m)
                    sev = assign_severity_tier(f)

                    # Ground severity against visual context — calibrates
                    # camera-physics tool noise and surfaces cross-modal conflicts.
                    _grounding = apply_visual_grounding(
                        tool_name=str(tool or ""),
                        agent_id=aid,
                        current_severity=sev,
                        visual_context=_visual_profile,
                        metadata=m,
                    )
                    sev = _grounding.adjusted_severity

                    evidence_verdict = str(
                        _finding_attr(f, "evidence_verdict", "")
                    ).upper()
                    finding_status = str(
                        _finding_attr(f, "status", "")
                    ).upper()
                    if evidence_verdict == "ERROR" or finding_status == "INCOMPLETE":
                        tv = "NEEDS_REVIEW"
                    elif evidence_verdict in (
                        "POSITIVE",
                        "TAMPERED",
                        "SUSPICIOUS",
                        "MANIPULATED",
                    ) or sev in ("CRITICAL", "HIGH", "MEDIUM"):
                        tv = "FLAGGED"
                    elif evidence_verdict == "NOT_APPLICABLE" or finding_status == "NOT_APPLICABLE":
                        tv = "NOT_APPLICABLE"
                    else:
                        tv = "CLEAN"
                    human_summary = _humanize_initial_finding(
                        agent_id=aid,
                        tool_name=str(tool or ""),
                        summary=s,
                        evidence_verdict=evidence_verdict,
                        finding_status=finding_status,
                        metadata=m,
                        artifact=evidence_artifact,
                    )
                    if human_summary is None:
                        human_summary = s[:240] if s else f"{tool or 'Tool'} completed."

                    if tool_key:
                        seen_raw_tools.add(tool_key)
                    preview.append(
                        {
                            "tool": _normalize_tool_name(str(tool or "")),
                            "summary": human_summary[:640],
                            "severity": sev,
                            "verdict": tv,
                            "key_signal": (
                                m.get("section_key_signal")
                                or m.get("raw_tool_summary")
                                or m.get("key_finding")
                                or m.get("anomaly_description")
                                or m.get("match_description")
                                or ""
                            ),
                            "section": m.get("section") or "",
                            # Badge "(fallback)" only on GENUINE tool degradation —
                            # an explicit degraded flag or a real failure/incomplete
                            # status. A benign fallback_reason (e.g. Gemini->local
                            # ensemble switch) on a clean result must not be flagged.
                            "degraded": bool(m.get("degraded")) or evidence_verdict == "ERROR" or finding_status in ("INCOMPLETE", "TIMEOUT", "ERROR"),
                            "fallback_reason": m.get("fallback_reason"),
                            "elapsed_s": m.get("elapsed_s"),
                            "finding_kind": "discovery" if tv in ("FLAGGED", "NEEDS_REVIEW") or _is_discovery_finding(tool, m) else "confirmation",
                            # Visual context grounding fields — present only when grounding applied
                            "context_note": _grounding.context_note if _grounding.grounded else None,
                            "grounding_type": _grounding.grounding_type if _grounding.grounded else None,
                        }
                    )

                # Sort by severity (CRITICAL > HIGH > MEDIUM > LOW),
                # then discoveries before confirmations within same tier
                _sev_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
                preview.sort(
                    key=lambda x: (
                        _sev_rank.get(x.get("severity") or "LOW", 0),
                        1 if x.get("finding_kind") == "discovery" else 0,
                    ),
                    reverse=True,
                )
            if isinstance(synthesis, dict) and synthesis.get("sections"):
                before = len(preview)
                _append_synthesis_sections(synthesis)
                # Always deduplicate by tool name — synthesis sections often overlap with
                # raw tool findings. Synthesis (LLM-refined) entries take precedence.
                # Also filter out any tool that was already run in the initial phase
                # (even synthesis-wrapped versions of initial tools) to prevent
                # deep-phase cards from showing initial-phase findings.
                seen_tools: set[str] = set()
                _norm_initial_tools: set[str] = set()
                if initial_tool_names:
                    for _raw_tn in initial_tool_names:
                        _norm_initial_tools.add(_normalize_tool_name(_raw_tn))
                # Two-pass: synthesis entries first (they are appended after `before`), then raw
                priority_preview = preview[before:] + preview[:before]
                deduped = []
                for item in priority_preview:
                    tool_key = str(item.get("tool") or "")
                    if tool_key and tool_key in seen_tools:
                        continue
                    if analysis_phase == "deep" and initial_tool_names and tool_key in _norm_initial_tools:
                        continue
                    if tool_key:
                        seen_tools.add(tool_key)
                    deduped.append(item)
                    if len(deduped) >= 8:
                        break
                preview = deduped
            if isinstance(synthesis, dict) and synthesis.get("narrative_summary") and not preview:
                summary = str(synthesis.get("narrative_summary") or "").strip()
                if summary and not any(
                    p in summary.lower()
                    for p in (
                        "empty raw tool results",
                        "lack of results",
                        "no digital traces or anomalies were detected due to",
                    )
                ):
                    # Prepend narrative summary as the first preview item
                    preview.insert(
                        0,
                        {
                            "tool": "agent_synthesis",
                            "summary": summary[:420],
                            "severity": "LOW",
                            "verdict": str(synthesis.get("verdict") or "INCONCLUSIVE"),
                        }
                    )


            # Align the streamed (live-card) verdict with the SAME
            # compute_agent_verdict the final report uses, so the card verdict
            # does not flip after deliberation (e.g. a preliminary self-assessed
            # "Suspicious" settling to "Authentic" on the result page). Falls back
            # to the agent's self-synthesis verdict on any error.
            _live_verdict = synthesis.get("verdict") if isinstance(synthesis, dict) else None
            _live_conf = agent_confidence
            if status == "complete" and isinstance(synthesis, dict):
                try:
                    _af = (
                        list(getattr(agent_inst, "_findings", []) or [])
                        if agent_inst is not None else []
                    )
                    if _af:
                        from core.severity import compute_agent_verdict
                        _cv, _cc, _ = compute_agent_verdict(_af)
                        if _cv:
                            _live_verdict = _cv
                            _live_conf = _cc
                        # Holistic corroboration gate (mirrors arbiter_deliberation):
                        # a Suspicious/Manipulated live verdict driven only by
                        # uncorroborated integrity-screening positives — while the
                        # holistic visual model reads the image as clean and there is
                        # no hard provenance signal (hash mismatch / 2+ strong
                        # court-defensible positives) — is, in practice, a tool false
                        # positive (e.g. copy-move matching repetitive real texture).
                        # Hold it Inconclusive at the live stage so the card does not
                        # assert manipulation that deliberation will then clear.
                        if _live_verdict in ("SUSPICIOUS", "MANIPULATED"):
                            _g = lambda f, k, d=None: (f.get(k, d) if isinstance(f, dict) else getattr(f, k, d))
                            _vc = getattr(agent_inst, "visual_context", None)
                            _av = str(getattr(_vc, "authenticity_verdict", "") or "").upper()
                            _ii = getattr(_vc, "image_integrity_context", None)
                            _ass = str(getattr(_ii, "integrity_assessment", "") or "").lower()
                            _holistic_flags = (
                                _av in ("AI_GENERATED", "MANIPULATED", "LIKELY_MANIPULATED", "SUSPECT")
                                or _ass in ("likely_manipulated", "ai_generated_suspect")
                            )
                            _holistic_clean = (_vc is not None) and not _holistic_flags
                            _hash_mm = any(
                                str((_g(f, "metadata", {}) or {}).get("tool_name")) == "file_hash_verify"
                                and str(_g(f, "evidence_verdict", "")).upper() == "POSITIVE"
                                for f in _af
                            )
                            _strong_cd = sum(
                                1 for f in _af
                                if str(_g(f, "evidence_verdict", "")).upper() == "POSITIVE"
                                and bool(_g(f, "court_defensible", False))
                                and str(_g(f, "severity_tier", "")).upper() in ("HIGH", "CRITICAL")
                            )
                            if _holistic_clean and not _hash_mm and _strong_cd < 2:
                                # Mirror the arbiter's corroboration grounding at the
                                # live stage: integrity screening positives the clean
                                # holistic read does not corroborate are benign (tool
                                # false positives on real texture / studio lighting).
                                # Clear them and recompute so the card reaches the SAME
                                # verdict deliberation will (AUTHENTIC) instead of
                                # stalling at an INCONCLUSIVE the final report flips.
                                _grounded = []
                                for f in _af:
                                    _is_pos = str(_g(f, "evidence_verdict", "")).upper() == "POSITIVE"
                                    _is_strong = (
                                        bool(_g(f, "court_defensible", False))
                                        and str(_g(f, "severity_tier", "")).upper() in ("HIGH", "CRITICAL")
                                    )
                                    if _is_pos and not _is_strong and isinstance(f, dict):
                                        _grounded.append({**f, "evidence_verdict": "INCONCLUSIVE"})
                                    else:
                                        _grounded.append(f)
                                _gv, _gc, _ = compute_agent_verdict(_grounded)
                                if _gv:
                                    _live_verdict, _live_conf = _gv, _gc
                except Exception:
                    pass

            await broadcast_update(
                str(session_id),
                BriefUpdate(
                    type="AGENT_COMPLETE"
                    if status in ("complete", "error", "skipped")
                    else "AGENT_UPDATE",
                    session_id=str(session_id),
                    agent_id=aid,
                    agent_name=aname,
                    message=message,
                    data={
                        "status": status,
                        "analysis_phase": analysis_phase,
                        "thinking": message,
                        "tool_name": "file_type_validation"
                        if status == "validating"
                        else None,
                        "tools_done": 0 if status in ("validating", "running") else None,
                        "tools_total": len(getattr(agent_inst, "deep_task_decomposition" if analysis_phase == "deep" else "task_decomposition", []) or [])
                        if agent_inst is not None and status == "running"
                        else 1
                        if status == "validating"
                        else None,
                         "findings_count": 0
                         if status == "skipped"
                         else len(preview),
                        "confidence": 0
                        if status == "skipped"
                        else (
                            _live_conf
                        ),
                        "error": error,
                        "findings_preview": preview,
                        "agent_verdict": _live_verdict,
                        "verdict_score": _verdict_score(_live_verdict),
                        # Suppress initial-phase narrative from deep-phase card summary
                        "summary": (
                            None if initial_tool_names
                            else synthesis.get("narrative_summary")
                            if isinstance(synthesis, dict)
                            else None
                        ),
                        "tool_error_rate": getattr(agent_inst, "_agent_error_rate", None)
                        if agent_inst
                        else None,
                        # Reconcile with the findings the user actually sees: count the
                        # distinct forensic tools represented in the displayed preview,
                        # not the raw success count (which includes deduped, suppressed,
                        # and not-applicable tools → "4 ran but 2 findings" discrepancy).
                        "tools_ran": (
                            len({
                                p.get("tool")
                                for p in preview
                                if p.get("tool") and p.get("tool") != "agent_synthesis"
                            })
                            or getattr(agent_inst, "_tool_success_count", None)
                        )
                        if agent_inst
                        else None,
                        "tools_failed": getattr(agent_inst, "_tool_error_count", None)
                        if agent_inst
                        else None,
                        "section_flags": synthesis.get("sections")
                        if isinstance(synthesis, dict)
                        else None,
                        "agent_brief": synthesis.get("agent_brief")
                        if isinstance(synthesis, dict)
                        else None,
                        "image_context": _resolve_image_context(agent_inst),
                    },
                ),
            )
        except Exception as exc:
            logger.debug("Agent status broadcast failed", agent_id=aid, error=str(exc))

    # --- Phase 1: Initialize agents and run initial passes ------------------

    async def _init_agent(aid: str):
        try:
            extra = {}
            if aid in (AgentID.AGENT2.value, AgentID.AGENT3.value, AgentID.AGENT4.value):
                extra = {"inter_agent_bus": pipeline.inter_agent_bus}

            cls = registry.get_agent_class(aid)
            kwargs = {
                "agent_id": aid,
                "session_id": session_id,
                "evidence_artifact": evidence_artifact,
                "config": pipeline.config,
                "working_memory": pipeline.working_memory,
                "episodic_memory": pipeline.episodic_memory,
                "custody_logger": pipeline.custody_logger,
                "evidence_store": pipeline.evidence_store,
                "heavy_tool_semaphore": pipeline.heavy_tool_semaphore,
                **extra,
            }
            inst = cls(**kwargs)
            # Thread the shared visual context onto every agent so it can read it
            # directly (no Agent-1 gate, no bus-timing race). Resolved up-front in
            # pipeline._run_investigation_core; may be None when unavailable.
            inst.visual_context = getattr(pipeline, "_visual_context", None)
            if pipeline.inter_agent_bus is not None:
                pipeline.inter_agent_bus.register_agent(aid, inst)

            # Log LLM availability for this agent
            from core.llm_client import LLMClient
            _llm_check = LLMClient(config=pipeline.config)
            inst._llm_available = _llm_check.is_available
            inst._synthesis_mode = "llm" if _llm_check.is_available else "deterministic"
            if _llm_check.is_available:
                logger.debug(f"{aid}: LLM available for enhanced reasoning")
            else:
                logger.info(f"{aid}: NO-LLM mode (classical tools only)")

            # Broadcast "validating" phase start for this specific node
            await _broadcast_agent_status(
                aid,
                "validating",
                f"{aid} file type validation in progress.",
                agent_inst=inst,
            )
            # Yield the event loop so the "validating" state renders in the UI
            # before immediately overwriting with "running" or "skipped"
            await asyncio.sleep(0)

            supported = inst.supports_uploaded_file

            if not supported:
                await _broadcast_agent_status(
                    aid,
                    "skipped",
                    f"{aid} bypassed: file type '{evidence_artifact.mime_type}' not supported for this analysis dimension.",
                    error="Unsupported file type.",
                    agent_inst=inst,
                )
            else:
                await _broadcast_agent_status(
                    aid,
                    "running",
                    f"{aid} file type validated. Starting initial analysis.",
                    agent_inst=inst,
                )
            return inst, supported
        except Exception as e:
            logger.error(f"Failed to initialize agent {aid}", error=str(e))
            await _broadcast_agent_status(
                aid,
                "error",
                f"Failed to initialize {aid}: {str(e)}",
                error=str(e)
            )
            return None, False


    # Initialize all agents and their status states concurrently to minimize time-to-first-feedback
    agent_instances = await asyncio.gather(
        *[_init_agent(aid) for aid in registry.get_all_agent_ids()]
    )


    applicable_ids = [
        aid
        for (inst, supported), aid in zip(
            agent_instances, registry.get_all_agent_ids(), strict=True
        )
        if supported
    ]
    if pipeline.signal_bus:
        pipeline.signal_bus.update_applicable_agents(applicable_ids)

    async def _run_one(agent, aid: str, supported: bool):
        if not supported:
            return agent, [], "unsupported"
        agent_timeout = 300  # 5 minutes per agent maximum
        try:
            logger.info(f"Running {aid} initial investigation")
            initial_findings = await asyncio.wait_for(
                agent.run_investigation(),
                timeout=min(float(pipeline.config.investigation_timeout), agent_timeout),
            )
            if pipeline.signal_bus:
                await pipeline.signal_bus.signal_ready(aid, initial_findings)
            await _broadcast_agent_status(
                aid,
                "complete",
                f"{aid} initial analysis complete.",
                findings=initial_findings,
                agent_inst=agent,
            )
            return agent, initial_findings, "complete"
        except TimeoutError as e:
            # Per-agent timeout (Fix 4): collect whatever findings the agent
            # accumulated before the deadline and continue the pipeline in a
            # degraded state.  Never re-raise — one slow agent must not abort
            # the full council investigation.
            findings = list(getattr(agent, "_findings", []) or [])
            logger.warning(
                f"{aid} initial pass timed out after {agent_timeout}s; "
                f"continuing with {len(findings)} partial findings",
                agent_id=aid,
                timeout_s=agent_timeout,
                partial_findings=len(findings),
            )
            if pipeline.signal_bus:
                await pipeline.signal_bus.signal_failure(aid)
            await _broadcast_agent_status(
                aid,
                "degraded",
                f"{aid} timed out — partial findings retained.",
                findings=findings,
                error=str(e),
                agent_inst=agent,
            )
            return agent, findings, "degraded"
        except Exception as e:
            logger.error(f"{aid} initial pass failed", error=str(e))
            findings = list(getattr(agent, "_findings", []) or [])
            if pipeline.signal_bus:
                await pipeline.signal_bus.signal_failure(aid)
            await _broadcast_agent_status(
                aid,
                "error",
                f"{aid} error: {e}",
                findings=findings,
                error=str(e),
                agent_inst=agent,
            )
            return agent, findings, "error"

    async def _run_one_staggered(agent, aid: str, supported: bool, idx: int):
        """Stagger initial agent startup by idx * 2s to avoid simultaneous API quota bursts."""
        if idx > 0:
            await asyncio.sleep(idx * 2.0)
        return await _run_one(agent, aid, supported)

    raw_initial = await asyncio.gather(
        *[
            _run_one_staggered(inst, aid, supported, idx)
            for idx, ((inst, supported), aid) in enumerate(zip(
                agent_instances, registry.get_all_agent_ids(), strict=True
            ))
        ],
        return_exceptions=True,
    )

    agent_map: dict[str, tuple] = {}
    for i, aid in enumerate(registry.get_all_agent_ids()):
        res = (
            raw_initial[i] if not isinstance(raw_initial[i], BaseException) else (None, [], "error")
        )
        agent_map[aid] = res

    initial_results = [
        AgentLoopResult(
            agent_id=aid,
            findings=[
                f.model_dump(mode="json") if hasattr(f, "model_dump") else f for f in findings
            ],
            reflection_report=(
                getattr(agent, "_reflection_report", None).model_dump(mode="json")
                if getattr(agent, "_reflection_report", None)
                else {}
            ),
            react_chain=_serialize_react_chain(getattr(agent, "_react_chain", [])),
            agent_active=status != "unsupported",
            supports_file_type=status != "unsupported",
            synthesis=getattr(agent, "_agent_synthesis", None),
        )
        for aid, (agent, findings, status) in agent_map.items()
    ]

    # Content-based routing: if CLIP analysis in Agent1 detected a video frame
    # screenshot, invoke Agent4 (Video) even though the MIME type is image/*.
    # This ensures deepfake video screenshots get video-specific forensic analysis.
    _video_frame_detected = False
    _a1_result = agent_map.get(AgentID.AGENT1.value)
    if _a1_result:
        _, _a1_findings, _ = _a1_result
        for _f in _a1_findings or []:
            _meta = (
                _f.metadata if hasattr(_f, "metadata")
                else _f.get("metadata", {}) if isinstance(_f, dict)
                else {}
            )
            if _meta.get("tool_name") == "analyze_image_content":
                _image_type = str(_meta.get("image_type") or "").lower()
                if "video frame" in _image_type or "screenshot of a video" in _image_type:
                    _video_frame_detected = True
                    break

    if _video_frame_detected:
        _a4_entry = agent_map.get(AgentID.AGENT4.value)
        if _a4_entry:
            _a4_agent, _a4_findings, _a4_status = _a4_entry
            if _a4_status == "unsupported" or not _a4_agent:
                from orchestration.agent_factory import AgentLoopResult as _ALR
                _a4_cls = registry.get_agent_class(AgentID.AGENT4.value)
                if _a4_cls:
                    _a4_instance = _a4_cls(
                        agent_id=AgentID.AGENT4.value,
                        session_id=session_id,
                        evidence_artifact=evidence_artifact,
                        config=pipeline.config,
                        working_memory=pipeline.working_memory,
                        episodic_memory=pipeline.episodic_memory,
                        custody_logger=pipeline.custody_logger,
                        evidence_store=pipeline.evidence_store,
                        heavy_tool_semaphore=pipeline.heavy_tool_semaphore,
                    )
                    if pipeline.inter_agent_bus is not None:
                        pipeline.inter_agent_bus.register_agent(AgentID.AGENT4.value, _a4_instance)
                    _a4_result = await _run_one(_a4_instance, AgentID.AGENT4.value, True)
                    _a4_agent, _a4_new_findings, _a4_new_status = _a4_result
                    agent_map[AgentID.AGENT4.value] = (_a4_agent, _a4_new_findings, _a4_new_status)
                    _a4_result_entry = _ALR(
                        agent_id=AgentID.AGENT4.value,
                        findings=[
                            f.model_dump(mode="json") if hasattr(f, "model_dump") else f
                            for f in _a4_new_findings
                        ],
                        reflection_report=getattr(_a4_agent, "_reflection_report", None),
                        react_chain=_serialize_react_chain(getattr(_a4_agent, "_react_chain", [])),
                        agent_active=True,
                        supports_file_type=True,
                        synthesis=getattr(_a4_agent, "_agent_synthesis", None),
                    )
                    initial_results = [
                        _a4_result_entry if r.agent_id == AgentID.AGENT4.value else r
                        for r in initial_results
                    ]
                    logger.info("Routed video frame screenshot to Agent4 for video-specific analysis")

    # --- HITL Gate ----------------------------------------------------------
    # Start the arbiter pre-warm with Phase 1 findings NOW so it runs concurrently
    # while the investigator reads the initial results and makes the Accept/Deep decision.
    # If deep analysis is chosen the resume endpoint cancels this via invalidate_pre_warm()
    # and a fresh pre-warm is kicked off after the deep pass.
    try:
        _initial_norm = pipeline._normalize_agent_results(initial_results)
        pipeline._pre_warm_task = asyncio.create_task(
            pipeline._run_arbiter_pre_warm(_initial_norm, pipeline._case_id, suppress_broadcasts=True)
        )
    except Exception as _pw_err:
        logger.debug("Phase-1 pre-warm task creation failed", error=str(_pw_err))

    if not await _await_deep_analysis_decision(pipeline, session_id):
        logger.info("Deep analysis skipped by analyst decision", session_id=str(session_id))
        return initial_results

    # Broadcast deep analysis start so the frontend transitions immediately
    try:
        from api.routes._session_state import broadcast_update
        from api.schemas import BriefUpdate

        await broadcast_update(
            str(session_id),
            BriefUpdate(
                type="AGENT_UPDATE",
                session_id=str(session_id),
                agent_id=None,
                message="Deep forensic analysis initiated.",
                data={"status": "processing", "analysis_phase": "deep", "thinking": "Dispatching deep forensic tools..."},
            ),
        )
    except Exception:
        pass

    # Clear stale findings and AgentX_deep namespaces from working memory before deep phase
    for _aid in registry.get_all_agent_ids():
        try:
            await pipeline.working_memory.clear(session_id, _aid)
            logger.debug(f"Cleared working memory for {_aid} before deep phase")
        except Exception as _wm_err:
            logger.debug(f"Working memory clear failed for {_aid}: {_wm_err}")
        try:
            await pipeline.working_memory.clear(session_id, f"{_aid}_deep")
            logger.debug(f"Cleared {_aid}_deep namespace before deep phase")
        except Exception as _wm_err:
            logger.debug(f"Working memory clear failed for {_aid}_deep: {_wm_err}")

    # --- Phase 2: Deep passes with early context sync ----------------------

    context_event = asyncio.Event()
    context_injected: set[str] = set()
    producer_id = AgentID.AGENT1.value

    def _broadcast_context(producer_finding: Any):
        broadcast_ok = False
        try:
            context_payload = {}
            if hasattr(producer_finding, "metadata"):
                if hasattr(producer_finding, "model_dump"):
                    context_payload = producer_finding.model_dump(mode="json")
                else:
                    context_payload = {
                        "metadata": producer_finding.metadata
                        if isinstance(producer_finding.metadata, dict)
                        else {}
                    }
            elif isinstance(producer_finding, dict):
                context_payload = producer_finding

            if context_payload:
                if pipeline.inter_agent_bus is not None:
                    pipeline.inter_agent_bus.set_visual_profile(str(session_id), context_payload)
                for aid, (agent_inst, _, _) in agent_map.items():
                    if agent_inst is None or aid in context_injected or aid == producer_id:
                        continue
                    if hasattr(agent_inst, "inject_agent1_context"):
                        agent_inst.inject_agent1_context(context_payload)
                        context_injected.add(aid)
                logger.info(f"Early context broadcast from {producer_id} triggered")
            broadcast_ok = True
        except Exception as _cb_err:
            logger.warning(f"Early signal callback failed: {_cb_err}")
        finally:
            context_event.set()
        return broadcast_ok

    producer_inst = agent_map.get(producer_id, (None, None, "error"))[0]
    if producer_inst:
        producer_inst._gemini_signal_callback = _broadcast_context

    for _aid, (agent_inst, _, _) in agent_map.items():
        if agent_inst and hasattr(agent_inst, "_agent1_context_event"):
            agent_inst._agent1_context_event = context_event

    # Pre-inject Agent 1 context from Phase 1 if already available to unblock parallel execution.
    # If Agent 1's Gemini failed in Phase 1, we must still signal context_event so
    # downstream agents are not stuck waiting on _agent1_context_event indefinitely.
    _context_seeded = False
    _producer_tuple = agent_map.get(producer_id)
    if _producer_tuple:
        _, _initial_findings, _ = _producer_tuple
        for _f in _initial_findings or []:
            _f_meta = (
                _f.metadata if hasattr(_f, "metadata")
                else _f.get("metadata", {}) if isinstance(_f, dict)
                else {}
            )
            _tool_name = _f_meta.get("tool_name") if isinstance(_f_meta, dict) else None
            if is_visual_profile_tool(_tool_name):
                logger.info(
                    "Found Phase 1 visual profile for Agent 1; "
                    "pre-injecting context to unblock Phase 2 concurrency."
                )
                if _broadcast_context(_f):
                    _context_seeded = True
                break

    if not _context_seeded:
        context_event.set()

    async def _run_deep_with_fallback(aid: str) -> AgentLoopResult:
        a_inst, a_init, a_status = agent_map[aid]
        a_supported = a_status != "unsupported"
        if not a_supported:
            if aid == producer_id:
                context_event.set()
            return AgentLoopResult(
                agent_id=aid,
                findings=[],
                reflection_report={},
                react_chain=[],
                agent_active=False,
                supports_file_type=False,
            )

        # Build initial tool set BEFORE any deep-phase broadcast so the "running"
        # and "error" status updates also suppress initial-phase narrative/synthesis.
        _initial_tool_names: set[str] = set()
        for _f in a_init or []:
            _m = (
                _f.metadata if hasattr(_f, "metadata")
                else _f.get("metadata", {}) if isinstance(_f, dict)
                else {}
            )
            _t = _m.get("tool_name") if isinstance(_m, dict) else None
            if _t:
                _initial_tool_names.add(str(_t))

        try:
            await _broadcast_agent_status(
                aid,
                "running",
                f"{aid} deep analysis in progress.",
                agent_inst=a_inst,
                initial_tool_names=_initial_tool_names,
                analysis_phase="deep",
            )

            # Progress monitor: polls working memory every 3s to show per-tool progress
            _progress_stop = asyncio.Event()

            async def _deep_progress_monitor():
                _last_current = ""
                while not _progress_stop.is_set():
                    try:
                        _deep_aid = f"{aid}_deep"
                        _state = await a_inst.working_memory.get_state(
                            a_inst.session_id, _deep_aid
                        )
                        if _state and _state.tasks:
                            _in_progress = [
                                t for t in _state.tasks if t.status == "IN_PROGRESS"
                            ]
                            _done = [t for t in _state.tasks if t.status == "COMPLETE"]
                            _current = _in_progress[0].description if _in_progress else ""
                            if _current and _current != _last_current:
                                await _broadcast_agent_status(
                                    aid,
                                    "running",
                                    f"Deep: {_current}",
                                    agent_inst=a_inst,
                                    initial_tool_names=_initial_tool_names,
                                    analysis_phase="deep",
                                )
                                _last_current = _current
                            if _done and not _in_progress:
                                await _broadcast_agent_status(
                                    aid,
                                    "running",
                                    f"{aid} deep analysis aggregating results.",
                                    agent_inst=a_inst,
                                    initial_tool_names=_initial_tool_names,
                                    analysis_phase="deep",
                                )
                    except Exception:
                        pass
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(_progress_stop.wait()), timeout=3.0
                        )
                    except TimeoutError:
                        pass
                    except asyncio.CancelledError:
                        break

            _monitor_task = asyncio.create_task(_deep_progress_monitor())
            try:
                result = await _run_agent_deep_only(pipeline, a_inst, aid, a_init, a_supported)
            finally:
                _progress_stop.set()
                _monitor_task.cancel()
                try:
                    await _monitor_task
                except (asyncio.CancelledError, Exception):
                    pass

            if result.error:
                await _broadcast_agent_status(
                    aid,
                    "error",
                    f"{aid} error: {result.error}",
                    error=result.error,
                    agent_inst=a_inst,
                    initial_tool_names=_initial_tool_names,
                    analysis_phase="deep",
                )
            else:
                # Broadcast only findings produced in the deep pass, identified by phase tag.
                deep_only = [
                    f for f in (result.findings or [])
                    if (f.get("metadata") or {}).get("analysis_phase") == "deep"
                ]
                await _broadcast_agent_status(
                    aid,
                    "complete",
                    f"{aid} deep analysis complete.",
                    findings=deep_only,
                    agent_inst=a_inst,
                    initial_tool_names=_initial_tool_names,
                    analysis_phase="deep",
                )

            if aid == producer_id:
                try:
                    visual_profile_result = {}
                    for finding in result.findings or []:
                        if (
                            isinstance(finding, dict)
                            and is_visual_profile_tool(
                                finding.get("metadata", {}).get("tool_name")
                            )
                        ):
                            visual_profile_result = finding
                            break
                    if visual_profile_result:
                        _broadcast_context(visual_profile_result)
                        for _ctx_aid in [AgentID.AGENT3.value, AgentID.AGENT5.value]:
                            _ctx_entry = agent_map.get(_ctx_aid)
                            if _ctx_entry:
                                _ctx_inst, _, _ = _ctx_entry
                                if _ctx_inst and hasattr(_ctx_inst, "_agent1_context"):
                                    if not _ctx_inst._agent1_context:
                                        logger.warning(
                                            f"Agent1 context injection failed for {_ctx_aid} — "
                                            "agent may run without multimodal context",
                                        )
                finally:
                    context_event.set()

            return result
        except Exception:
            if aid == producer_id:
                context_event.set()
            raise

    async def _run_deep_with_stagger(aid: str, idx: int):
        """Stagger deep agent start by index * 4s to avoid simultaneous Gemini slot contention."""
        if idx > 0:
            await asyncio.sleep(idx * 4.0)
        return await _run_deep_with_fallback(aid)

    raw_deep_all = await asyncio.gather(
        *[_run_deep_with_stagger(aid, idx) for idx, aid in enumerate(agent_map.keys())],
        return_exceptions=True,
    )

    agent_ids_deep = registry.get_all_agent_ids()
    results: list[AgentLoopResult] = []
    for i, r in enumerate(raw_deep_all):
        if isinstance(r, BaseException):
            logger.error(
                f"Agent {agent_ids_deep[i]} deep pass raised unexpectedly",
                error=str(r),
                exc_info=r,
            )
            results.append(
                AgentLoopResult(
                    agent_id=agent_ids_deep[i],
                    findings=[],
                    reflection_report={},
                    react_chain=[],
                    error=str(r),
                    agent_active=False,
                )
            )
        else:
            results.append(r)

    # Keep Phase 1 + Phase 2 evidence together for the final arbiter report.
    # _run_agent_deep_only already appends only non-duplicate deep findings to
    # the agent's existing findings; stripping here removes useful initial
    # evidence from the signed deep report.

    active_agents = [r.agent_id for r in results if r.agent_active]
    skipped_agents = [r.agent_id for r in results if not r.supports_file_type]
    logger.info(
        "Agent execution summary", active_agents=active_agents, skipped_agents=skipped_agents
    )

    # Re-warm with complete (Phase 1 + deep) findings so the arbiter has the full
    # evidence picture while the investigator reads the deep results and decides.
    try:
        _deep_norm = pipeline._normalize_agent_results(results)
        pipeline._pre_warm_task = asyncio.create_task(
            pipeline._run_arbiter_pre_warm(_deep_norm, pipeline._case_id, suppress_broadcasts=True)
        )
    except Exception as _pw_err:
        logger.debug("Phase-2 pre-warm task creation failed", error=str(_pw_err))

    await _await_deep_report_request(pipeline, session_id)

    for aid in registry.get_all_agent_ids():
        if pipeline.inter_agent_bus is not None:
            pipeline.inter_agent_bus.unregister_agent(aid)

    # O-C-3: close the span opened at function entry.
    try:
        _pac_span.end()
    except Exception:
        pass

    return results


async def _run_agent_deep_only(
    pipeline: ForensicCouncilPipeline,
    agent,
    agent_id: str,
    initial_findings: list,
    supports_file: bool,
) -> AgentLoopResult:
    """Run the deep investigation pass on an already-initialized agent."""
    from core.observability import get_tracer

    _tracer = get_tracer("forensic-council.pipeline")

    if agent is None:
        return AgentLoopResult(
            agent_id=agent_id,
            findings=[],
            reflection_report={},
            react_chain=[],
            agent_active=False,
            supports_file_type=supports_file,
            error="Initial pass failed",
        )
    if not supports_file:
        return AgentLoopResult(
            agent_id=agent_id,
            findings=[],
            reflection_report={},
            react_chain=[],
            agent_active=False,
            supports_file_type=False,
        )

    with _tracer.start_as_current_span(f"agent.{agent_id}.deep_pass") as span:
        span.set_attribute("agent_id", agent_id)
        try:
            logger.info(f"Running {agent_id} deep investigation")
            deep_timeout = min(
                pipeline.config.deep_agent_timeout_seconds,
                pipeline.config.deep_agent_hard_cap_seconds,
            )
            agent.deep_tool_timeout = pipeline.config.deep_tool_timeout_seconds
            await asyncio.wait_for(
                agent.run_deep_investigation(),
                timeout=deep_timeout,
            )
            all_findings = getattr(agent, "_findings", initial_findings)
            for finding in all_findings:
                meta = finding.metadata
                if not isinstance(meta, dict):
                    meta = {}
                    finding.metadata = meta
                meta["context_version"] = 2
                phase = meta.get("analysis_phase", "")
                if phase != "deep":
                    continue
                reason_str = str(meta.get("reason") or meta.get("skipped_reason") or "").lower()
                is_gated = (
                    meta.get("skipped") is True
                    or meta.get("anomaly_tracer_skipped") is True
                    or meta.get("adversarial_check_skipped") is True
                    or "not triggered" in reason_str
                    or "not warranted" in reason_str
                )
                if is_gated:
                    meta["gated"] = True

            deep_only = [f for f in all_findings if (f.metadata or {}).get("analysis_phase") == "deep"]
            deep_count = len(deep_only)
            span.set_attribute("deep_finding_count", deep_count)
            span.set_attribute("total_finding_count", len(all_findings))
            return AgentLoopResult(
                agent_id=agent_id,
                findings=[f.model_dump(mode="json") for f in all_findings],
                reflection_report=(
                    getattr(agent, "_reflection_report", None).model_dump(mode="json")
                    if getattr(agent, "_reflection_report", None)
                    else {}
                ),
                react_chain=_serialize_react_chain(getattr(agent, "_react_chain", [])),
                agent_active=True,
                supports_file_type=True,
                deep_findings_count=max(0, deep_count),
                synthesis=getattr(agent, "_agent_synthesis", None),
            )
        except Exception as e:
            logger.error(f"{agent_id} deep pass failed", error=str(e), exc_info=True)
            return AgentLoopResult(
                agent_id=agent_id,
                findings=[f.model_dump(mode="json") for f in initial_findings],
                reflection_report={},
                react_chain=_serialize_react_chain(getattr(agent, "_react_chain", [])),
                agent_active=True,
                supports_file_type=True,
                error=str(e),
                deep_findings_count=0,
                synthesis=getattr(agent, "_agent_synthesis", None),
            )


async def _await_deep_analysis_decision(
    pipeline: ForensicCouncilPipeline,
    session_id: UUID,
) -> bool:
    """
    Pause pipeline and poll Redis/event for analyst decision.
    Returns True if deep analysis should proceed, False to skip.
    """
    from api.routes._session_state import (
        broadcast_update,
        update_active_pipeline_metadata,
    )
    from api.schemas import BriefUpdate
    from core.persistence.redis_client import get_redis_client

    decision_key = f"forensic:session:resume_decision:{session_id}:initial_to_deep"
    redis = await get_redis_client()

    # F-2: delete the wrong-phase decision key (deep_to_report) so a
    # resume request racing between phases cannot write to the wrong key.
    try:
        await redis.delete(f"forensic:session:resume_decision:{session_id}:deep_to_report")
    except Exception:
        pass

    # Set pause status BEFORE consuming any pre-existing decision.
    # This ensures the resume endpoint writes to the correct key and
    # eliminates the TOCTOU race where GETDEL could consume a decision
    # before the pipeline is registered as "awaiting_decision".
    pipeline._awaiting_user_decision = True
    pipeline.deep_analysis_decision_event.clear()
    pipeline.run_deep_analysis_flag = False

    # Broadcast initial results complete before pausing
    try:
        await broadcast_update(
            str(session_id),
            BriefUpdate(
                type="INITIAL_ANALYSIS_COMPLETE",
                session_id=str(session_id),
                message="Initial analysis phase complete - all agent findings ready.",
                data={"status": "initial_complete", "phase": "initial"},
            ),
        )
        await asyncio.sleep(0.5)
    except Exception as broadcast_err:
        logger.warning("Initial complete broadcast failed", error=str(broadcast_err))

    # F-14: use atomic CAS for phase-gate status transition
    await update_active_pipeline_metadata(
        str(session_id),
        {
            "status": "awaiting_decision",
            "brief": "Initial analysis complete. Awaiting analyst decision.",
            "awaiting_decision": True,
        },
    )
    await broadcast_update(
        str(session_id),
        BriefUpdate(
            type="PIPELINE_PAUSED",
            session_id=str(session_id),
            message="Initial analysis complete. Awaiting analyst decision.",
            data={"status": "awaiting_decision", "initial_results_ready": True},
        ),
    )

    # Now consume any decision that arrived during the status transition.
    # Any decision written after the status was set will be in the correct key.
    try:
        raw_pre_gate_decision = await redis.getdel(decision_key)
    except AttributeError:
        raw_pre_gate_decision = await redis.get(decision_key)
        if raw_pre_gate_decision:
            await redis.delete(decision_key)
    except Exception as getdel_err:
        raw_pre_gate_decision = None
        logger.debug("GETDEL failed on decision key", error=str(getdel_err))

    if raw_pre_gate_decision:
        decision = None
        try:
            decision = json.loads(raw_pre_gate_decision)
        except json.JSONDecodeError:
            logger.warning(
                "Corrupt decision key data",
                session_id=str(session_id),
            )

        if isinstance(decision, dict):
            pipeline.run_deep_analysis_flag = bool(decision.get("deep_analysis"))
            logger.info(
                "Analyst decision consumed after pause gate",
                session_id=str(session_id),
                deep_analysis=pipeline.run_deep_analysis_flag,
            )
            pipeline._awaiting_user_decision = False
            return pipeline.run_deep_analysis_flag

        logger.info(
            "Cleared stale/out-of-session decision key",
            session_id=str(session_id),
        )

    try:
        active_redis = pipeline._redis or await get_redis_client()
        timeout = pipeline.config.hitl_decision_timeout or 3600
        start_time = time.perf_counter()

        while (time.perf_counter() - start_time) < timeout:
            try:
                raw_decision = await active_redis.get(decision_key)
                if raw_decision:
                    decision = json.loads(raw_decision)
                    if isinstance(decision, dict):
                        pipeline.run_deep_analysis_flag = bool(decision.get("deep_analysis"))
                        logger.info(
                            "Analyst decision received via Redis",
                            session_id=str(session_id),
                            deep_analysis=pipeline.run_deep_analysis_flag,
                        )
                        return pipeline.run_deep_analysis_flag
            except Exception as poll_err:
                logger.debug("Decision polling flicker", error=str(poll_err))

            if pipeline.deep_analysis_decision_event.is_set():
                logger.info(
                    "Analyst decision received via internal event",
                    session_id=str(session_id),
                )
                return bool(pipeline.run_deep_analysis_flag)

            await asyncio.sleep(2.0)

        logger.warning(
            "HITL decision timed out; defaulting to skip deep analysis",
            session_id=str(session_id),
            timeout_seconds=timeout,
        )
        return False
    finally:
        pipeline._awaiting_user_decision = False
        try:
            await redis.delete(decision_key)
        except Exception as _e:
            logger.debug("Decision key cleanup skipped (Redis may be unavailable)", error=str(_e))


async def _await_deep_report_request(
    pipeline: ForensicCouncilPipeline,
    session_id: UUID,
) -> None:
    """Pause after deep analysis so the analyst controls final arbiter synthesis."""
    from api.routes._session_state import (
        broadcast_update,
        update_active_pipeline_metadata,
    )
    from api.schemas import BriefUpdate
    from core.persistence.redis_client import get_redis_client

    decision_key = f"forensic:session:resume_decision:{session_id}:deep_to_report"
    redis = await get_redis_client()

    # F-2: delete the wrong-phase decision key (initial_to_deep) so a
    # resume request racing between phases cannot write to the wrong key.
    try:
        await redis.delete(f"forensic:session:resume_decision:{session_id}:initial_to_deep")
    except Exception:
        pass

    # Set pause status BEFORE consuming any pre-existing decision.
    # This ensures the resume endpoint writes to the correct key and
    # eliminates the TOCTOU race.
    pipeline._awaiting_user_decision = True
    pipeline.deep_analysis_decision_event.clear()
    pipeline.run_deep_analysis_flag = False

    # F-14: use atomic CAS for phase-gate status transition
    await update_active_pipeline_metadata(
        str(session_id),
        {
            "status": "awaiting_deep_report",
            "brief": "Deep analysis complete. Awaiting analyst request for arbiter synthesis.",
            "awaiting_decision": True,
            "deep_analysis_complete": True,
        },
    )
    await broadcast_update(
        str(session_id),
        BriefUpdate(
            type="PIPELINE_PAUSED",
            session_id=str(session_id),
            message="Deep analysis complete. Awaiting analyst request for arbiter synthesis.",
            data={
                "status": "awaiting_deep_report",
                "deep_results_ready": True,
            },
        ),
    )

    # Now consume any decision that arrived during the status transition.
    try:
        raw_pre_gate_decision = await redis.getdel(decision_key)
    except AttributeError:
        raw_pre_gate_decision = await redis.get(decision_key)
        if raw_pre_gate_decision:
            await redis.delete(decision_key)
    except Exception as pre_gate_err:
        raw_pre_gate_decision = None
        logger.debug("Pre-gate final-report decision check flicker", error=str(pre_gate_err))

    if raw_pre_gate_decision:
        logger.info(
            "Final report request consumed after post-deep pause gate",
            session_id=str(session_id),
            decision_key=decision_key,
        )
        pipeline._awaiting_user_decision = False
        return

    try:
        active_redis = pipeline._redis or await get_redis_client()
        timeout = pipeline.config.hitl_decision_timeout or 3600
        start_time = time.perf_counter()

        while (time.perf_counter() - start_time) < timeout:
            try:
                raw_decision = await active_redis.get(decision_key)
                if raw_decision:
                    logger.info(
                        "Final report request received via Redis",
                        session_id=str(session_id),
                    )
                    return
            except Exception as poll_err:
                logger.debug("Final-report decision polling flicker", error=str(poll_err))

            if pipeline.deep_analysis_decision_event.is_set():
                logger.info(
                    "Final report request received via internal event",
                    session_id=str(session_id),
                )
                return

            await asyncio.sleep(2.0)

        logger.warning(
            "Deep report request timed out; proceeding to arbiter synthesis",
            session_id=str(session_id),
            timeout_seconds=timeout,
        )
    finally:
        pipeline._awaiting_user_decision = False
        try:
            await redis.delete(decision_key)
        except Exception as _e:
            logger.debug("Decision key cleanup skipped (Redis may be unavailable)", error=str(_e))
