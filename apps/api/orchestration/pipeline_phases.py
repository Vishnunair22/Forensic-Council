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


def _build_live_visual_signal(aid: str, agent_inst: Any, session_id: str) -> dict[str, Any] | None:
    """Per-agent ``visual_signal`` mirroring ``arbiter.deliberate``.

    The live agent card streams a per-agent verdict/confidence computed by
    ``compute_agent_verdict``. The signed report computes the SAME function but
    additionally feeds it this ``visual_signal`` (the holistic vision read +
    per-agent anomalies). Without it the live card misses the holistic
    corroboration term — e.g. a clean Agent1 streams 86% but the report shows
    90% — so the number silently drifts between the evidence page and the
    result page. Building it identically here makes the card equal the report
    by construction. Only Agent1 carries the holistic verdict (Agent3 only when
    the whole image is synthetic/manipulated; Agent5 stays on provenance),
    matching the arbiter so Agent3/Agent5 never inherit an authenticity boost.
    """
    vc = getattr(agent_inst, "visual_context", None) if agent_inst is not None else None
    if vc is None:
        return None
    is_remote = bool(
        getattr(vc, "external_llm_used", False)
        and getattr(vc, "source", "") != "local_ensemble"
    )
    holistic = str(getattr(vc, "authenticity_verdict", "") or "").upper()
    splits = None
    try:
        from core.per_agent_synthesis import split_visual_context

        splits = split_visual_context(session_id, vc)
    except Exception:
        splits = None

    def _sec(name: str) -> dict[str, Any]:
        return (getattr(splits, name, None) or {}) if splits is not None else {}

    if aid == "Agent1":
        return {
            "verdict": holistic,
            "court_defensible": is_remote,
            "anomalies": list(_sec("agent1_image_integrity").get("ai_generation_signals") or []),
        }
    if aid == "Agent3":
        return {
            "verdict": holistic if holistic in ("AI_GENERATED", "LIKELY_MANIPULATED") else "",
            "court_defensible": is_remote,
            "anomalies": list(_sec("agent3_object_scene").get("scene_inconsistencies") or []),
        }
    if aid == "Agent5":
        return {
            "verdict": "",
            "court_defensible": is_remote,
            "anomalies": list(_sec("agent5_metadata_visual").get("metadata_contradictions") or []),
        }
    return None

PREVIEW_EXCLUDED_TOOLS = {
    "hash_verify", "custody_check", "file_type_validation",
    # Context-only tools: their output IS the per-agent Visual Context box, not a
    # forensic Key Finding. Surfacing the scene description as a "finding" made the
    # key-findings list read like duplicated narration rather than tool results.
    "visual_evidence_profile", "shared_visual_evidence_profile",
    "read_shared_image_context", "frame_extraction",
}
SCREENSHOT_PREVIEW_EXCLUDED_TOOLS = {
    "lighting_consistency",
    "lighting_correlation_initial",
    "shadow_validation",
    "scale_validation",
    "prnu_sensor_verification",
}


def _task_text_surfaces(task_text: Any, evidence_artifact: Any) -> bool:
    """True when a planned task maps to a tool that will surface as a Key Finding.

    Mirrors the per-finding _suppress_preview_tool gate so the live "X/Y tools"
    counter/denominator converge to the completed "N tools ran": context/custody
    tools (visual_evidence_profile, hash, file-type validation, frame extraction)
    are planned and executed but never surfaced, so counting them inflated the
    live progress above the eventual finding count (e.g. "5/5" → "3 ran"). Task
    descriptions embed the tool name as a substring (see TOOL_TO_TASK_DESCRIPTION),
    so a substring match is sufficient.
    """
    excluded = set(PREVIEW_EXCLUDED_TOOLS)
    _mime = (getattr(evidence_artifact, "mime_type", "") or "").lower()
    if not _mime.startswith("image/"):
        # For audio/video/document the shared native profile IS the headline
        # finding and DOES surface — keep it counted.
        excluded -= {
            "read_shared_image_context",
            "visual_evidence_profile",
            "shared_visual_evidence_profile",
        }
    if is_screen_capture_like(evidence_artifact):
        excluded |= SCREENSHOT_PREVIEW_EXCLUDED_TOOLS
    text = str(task_text or "").lower()
    return not any(tool in text for tool in excluded)


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
        tools_done: int | None = None,
    ):
        try:
            from api.routes._session_state import AGENT_NAMES, broadcast_update
            from api.schemas import BriefUpdate
            from core.severity import assign_severity_tier
            from core.visual_grounding import apply_visual_grounding

            # Fetch the pre-flight visual context once per broadcast — used to
            # calibrate finding severity for all findings in this agent's batch.
            # Normalise to the canonical profile shape (file_type_assessment +
            # scene_inconsistencies + weapons_or_dangerous_items) that
            # apply_visual_grounding expects — the SAME shape the Arbiter uses via
            # visual_context_to_profile_dict. The raw bus profile is whatever the
            # last writer stored (Agent 1 overwrites the preflight dump with its
            # flat finding dict), so passing it directly left Rule 3 scene
            # corroboration dead and screenshot detection relying on free text.
            _visual_profile: dict | None = None
            try:
                from core.visual_context_store import (
                    get_visual_context,
                    visual_context_to_profile_dict,
                )

                _vc = await get_visual_context(
                    session_id=str(session_id),
                    working_memory=getattr(pipeline, "working_memory", None),
                    inter_agent_bus=pipeline.inter_agent_bus,
                )
                if _vc is not None:
                    _visual_profile = visual_context_to_profile_dict(_vc)
            except Exception as _vc_err:
                logger.debug("Canonical visual profile unavailable for grounding", error=str(_vc_err))
            if _visual_profile is None and pipeline.inter_agent_bus is not None:
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
                    # For non-image evidence (audio/video/document) the shared native
                    # profile IS the headline forensic signal — synthetic-speech,
                    # deepfake, or AI-generated-text. It must be a VISIBLE key finding,
                    # not hidden the way it is for images (where it's the scene box).
                    if tool_text in (
                        "read_shared_image_context",
                        "visual_evidence_profile",
                        "shared_visual_evidence_profile",
                    ):
                        _mime = (getattr(evidence_artifact, "mime_type", "") or "").lower()
                        if not _mime.startswith("image/"):
                            return False
                    return True
                return (
                    tool_text in SCREENSHOT_PREVIEW_EXCLUDED_TOOLS
                    and is_screen_capture_like(evidence_artifact)
                )

            def _count_surfacing_tasks(tasks: Any) -> int:
                """Count planned tasks whose tool will surface as a Key Finding."""
                return sum(
                    1 for task in (tasks or [])
                    if _task_text_surfaces(task, evidence_artifact)
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

                # Non-image modalities surface the native CONTENT context (Gemini's
                # understanding of the audio/video/document) instead of an image axis.
                # The shared visual_context is often NOT threaded onto audio/video
                # agents at live-brief time (the holistic read runs DURING the agent),
                # so resolve the content_description from the agent's own holistic
                # finding / tool context. Audio (Agent2) and video (Agent4) always;
                # metadata (Agent5) only when the file itself is a document.
                _mime = (getattr(evidence_artifact, "mime_type", "") or "").lower()
                _is_document = (
                    _mime == "application/pdf" or _mime.startswith("text/") or "document" in _mime
                )
                if aid in ("Agent2", "Agent4") or (aid == "Agent5" and _is_document):
                    def _is_image_ensemble_text(s: str) -> bool:
                        sl = (s or "").lower()
                        # Local IMAGE-ensemble content fragments — meaningless on a
                        # non-image card (they appear when the native content read
                        # falls back to the local image ensemble).
                        return (
                            sl.startswith("clip classified")
                            or sl.startswith("identified as:")
                            or "forensic signals: ela" in sl
                            or "forensic screening surfaced" in sl
                            or "visual content could not" in sl
                            or ("resolution:" in sl and "px" in sl)
                        )
                    _cd = ""
                    # 1. Threaded preflight visual context.
                    if vctx is not None:
                        _cd = str(getattr(vctx, "scene_description", "") or "").strip()
                    # 2. Persisted preflight context from the bus — the authoritative
                    #    native (Gemini) content read the signed report uses.
                    if not _cd:
                        try:
                            _bus = getattr(agent_inst, "inter_agent_bus", None)
                            _sid = str(getattr(agent_inst, "session_id", "") or "")
                            if _bus is not None and _sid:
                                _vp_bus = _bus.get_visual_profile(_sid) or {}
                                _cd = str(_vp_bus.get("scene_description") or "").strip()
                        except Exception:
                            _cd = ""
                    # 3. The agent's own holistic finding — but never the image-ensemble
                    #    fallback ("CLIP classified the image as unknown ...") which is
                    #    meaningless for audio/video.
                    if not _cd:
                        for _f in (getattr(agent_inst, "_findings", []) or []):
                            _fm = getattr(_f, "metadata", {}) or {}
                            _tn = str(_fm.get("tool_name") or getattr(_f, "finding_type", "") or "")
                            if _tn in ("visual_evidence_profile", "read_shared_image_context"):
                                _cand = str(_fm.get("content_description") or getattr(_f, "content_description", "") or "").strip()
                                if _cand and not _is_image_ensemble_text(_cand):
                                    _cd = _cand
                                    break
                    if _is_image_ensemble_text(_cd):
                        _cd = ""
                    return _cd or None

                if vctx is not None:
                    try:
                        # Each agent shows its OWN slice of the shared Gemini visual
                        # context so the three cards are DISTINCT (Agent1 integrity,
                        # Agent3 object/scene, Agent5 metadata/provenance) — never the
                        # same scene sentence echoed across all three.
                        _integ = getattr(vctx, "image_integrity_context", None)
                        scene = str(getattr(vctx, "scene_description", "") or "").strip()

                        if aid == "Agent3":
                            # Object/scene axis: what is depicted + detected objects.
                            objs = []
                            for o in (getattr(vctx, "detected_objects", None) or []):
                                lbl = getattr(o, "label", None) if not isinstance(o, dict) else o.get("label")
                                if lbl:
                                    objs.append(str(lbl))
                            parts = []
                            if scene:
                                parts.append(scene.rstrip("."))
                            if objs:
                                parts.append("objects: " + ", ".join(objs[:4]))
                            if parts:
                                return "; ".join(parts)
                        elif aid == "Agent5":
                            # Metadata/provenance axis: visible provenance markers ONLY
                            # (timestamps, device/platform, software, location). Never
                            # falls back to the scene description — that is Agent3's axis.
                            ftype = str(getattr(vctx, "file_type_assessment", "") or "").strip().replace("_", " ")
                            meta = getattr(vctx, "metadata_visual_context", None)

                            def _mc(attr: str) -> list[str]:
                                return [str(c) for c in (getattr(meta, attr, None) or []) if c]

                            groups = []
                            if _mc("visible_timestamps"):
                                groups.append("timestamps: " + ", ".join(_mc("visible_timestamps")[:2]))
                            if _mc("device_or_platform_clues"):
                                groups.append("device/platform: " + ", ".join(_mc("device_or_platform_clues")[:2]))
                            if _mc("software_or_app_clues"):
                                groups.append("software: " + ", ".join(_mc("software_or_app_clues")[:2]))
                            if _mc("visible_location_clues"):
                                groups.append("location: " + ", ".join(_mc("visible_location_clues")[:2]))
                            lead = (ftype + " — ") if ftype else ""
                            if groups:
                                return lead + "; ".join(groups)
                            return (
                                lead
                                + "no visible provenance markers (timestamps, device, or software signatures) in the image content"
                            )
                        else:
                            # Agent1 integrity axis: the holistic integrity read, not a
                            # bare scene sentence (the scene is Agent3's axis).
                            manip = [str(s) for s in (getattr(_integ, "visible_manipulation_signals", None) or []) if s]
                            ai = [str(s) for s in (getattr(_integ, "ai_generation_signals", None) or []) if s]
                            edits = [str(s) for s in (getattr(_integ, "editing_or_compositing_signals", None) or []) if s]
                            assessment = str(getattr(_integ, "integrity_assessment", "") or "").replace("_", " ").strip()
                            if manip or ai:
                                return "Visual integrity signals: " + "; ".join((manip + ai)[:3]) + "."
                            if assessment in ("suspicious", "likely manipulated", "ai generated", "ai generated suspect"):
                                # Alert assessment with no discrete signal — state it
                                # honestly rather than the contradictory "No visible
                                # manipulation … (assessment: likely manipulated)".
                                body = f"Holistic visual read: {assessment} (no discrete pixel-level signal isolated)"
                            else:
                                body = "No visible manipulation or AI-generation indicators"
                                if assessment == "no visible issue":
                                    body += " (assessment: no visible issue)"
                            if edits:
                                # Gemini's benign-edit phrases often already end with a
                                # period; strip per-item trailing punctuation before
                                # joining so we never emit "edit." + ", " or a trailing
                                # "..".
                                _edits = [e.strip().rstrip(".").strip() for e in edits[:2] if e.strip()]
                                _edits = [e for e in _edits if e]
                                if _edits:
                                    body += "; benign edits noted: " + ", ".join(_edits)
                            body = body.rstrip()
                            return body if body.endswith(".") else body + "."
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
                # Map each tool to ITS OWN evidence verdict/severity so a refined
                # synthesis section carries the tool's real conclusion — NOT the
                # agent-level verdict. Previously every section inherited the agent
                # verdict, so a clean voice-clone/anti-spoof check read as SUSPICIOUS
                # under a Suspicious agent and inflated the "N anomalies flagged" count.
                _raw_fv: dict[str, tuple[str, str]] = {}
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
                        _ev = str(_finding_attr(existing_finding, "evidence_verdict", "")).upper()
                        _sevt = str(existing_meta.get("severity_tier") or "").upper()
                        _raw_fv[_normalize_tool_name(str(existing_tool))] = (_ev, _sevt)

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
                        # Per-tool verdict from the tool's OWN result (evidence_verdict
                        # is authoritative; NEGATIVE/NOT_APPLICABLE are never alerts),
                        # falling back to the section's flag only when no raw finding
                        # exists (e.g. deep synthesis-only section).
                        _nt = _normalize_tool_name(tool_name)
                        _ev, _sevt = _raw_fv.get(_nt, ("", ""))
                        _sec_sev = (section.get("severity") or "LOW").upper()
                        if _ev == "NOT_APPLICABLE":
                            _item_tv = "NOT_APPLICABLE"
                        elif _ev == "ERROR":
                            _item_tv = "NEEDS_REVIEW"
                        elif _ev in ("NEGATIVE", "CLEAN"):
                            _item_tv = "CLEAN"
                        elif _ev in ("POSITIVE", "TAMPERED", "SUSPICIOUS", "MANIPULATED") or _sevt in ("CRITICAL", "HIGH"):
                            _item_tv = "FLAGGED"
                        elif not _ev:
                            # No matching raw finding — trust the section's own flag.
                            _item_tv = "FLAGGED" if _sec_sev in ("CRITICAL", "HIGH", "MEDIUM") else "CLEAN"
                        else:
                            _item_tv = "INCONCLUSIVE"
                        preview.append(
                            {
                                "tool": _normalize_tool_name(tool_name),
                                "summary": summary[:560],
                                # A clean / not-applicable finding must never carry an
                                # alerting severity — otherwise it is counted as an
                                # "anomaly" purely on a stray section severity.
                                "severity": "LOW" if _item_tv in ("CLEAN", "NOT_APPLICABLE")
                                else (_sevt or section.get("severity") or "LOW"),
                                "verdict": _item_tv,
                                "key_signal": "",
                                "confidence": synthesis_data.get("agent_confidence"),
                                "section": section.get("label") or "",
                                # A refined narrative section is NOT a degraded/fallback
                                # result just because LLM synthesis was off (deterministic
                                # is the normal free-tier path). Only flag genuine section
                                # degradation.
                                "degraded": bool(section.get("degraded")),
                                "fallback_reason": section.get("fallback_reason"),
                                "finding_kind": "discovery" if _item_tv in ("FLAGGED", "NEEDS_REVIEW") else "confirmation",
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
                    if len(deduped) >= 12:
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

                        # Feed the SAME per-agent visual_signal the arbiter uses
                        # so the streamed card value equals the signed report's
                        # grounded per-agent verdict/confidence (single source of
                        # truth — no 86%→90% drift between evidence and result).
                        _vsig = _build_live_visual_signal(aid, agent_inst, str(session_id))
                        _is_deep = analysis_phase == "deep"
                        _cv, _cc, _ = compute_agent_verdict(_af, visual_signal=_vsig, is_deep=_is_deep)
                        if _cv:
                            _live_verdict = _cv
                            _live_conf = _cc

                        # Card/report parity: the arbiter holds uncorroborated
                        # integrity-screening POSITIVES inconclusive (benign processing
                        # artifact) whenever the holistic read is clean — INDEPENDENT of
                        # the agent verdict. Mirror that REFRAMING on the live preview so
                        # a screening ELA/copy-move positive does not read as an assertive
                        # manipulation signal beside an Authentic card while the result
                        # page shows the non-asserting text. Verdict-agnostic by design.
                        try:
                            from core.severity import (
                                NON_INTEGRITY_TOOLS,
                                holistic_read_flags_manipulation,
                                should_clear_uncorroborated_integrity,
                                uncorroborated_screening_text,
                            )

                            def _gf(f, k, d=None):
                                return f.get(k, d) if isinstance(f, dict) else getattr(f, k, d)

                            _vc2 = getattr(agent_inst, "visual_context", None)
                            _av2 = str(getattr(_vc2, "authenticity_verdict", "") or "")
                            _ii2 = getattr(_vc2, "image_integrity_context", None)
                            _ass2 = str(getattr(_ii2, "integrity_assessment", "") or "").lower()
                            _holistic_clean2 = (_vc2 is not None) and not holistic_read_flags_manipulation(_av2, _ass2)
                            _norm2 = [
                                {
                                    "tool_name": (_gf(f, "metadata", {}) or {}).get("tool_name")
                                    or _gf(f, "finding_type", "") or "",
                                    "evidence_verdict": _gf(f, "evidence_verdict", ""),
                                    "court_defensible": _gf(f, "court_defensible", False),
                                    "confidence": _gf(f, "confidence_raw", 0.0),
                                    "severity_tier": _gf(f, "severity_tier", "")
                                    or (_gf(f, "metadata", {}) or {}).get("severity_tier", ""),
                                }
                                for f in _af
                            ]
                            if preview and should_clear_uncorroborated_integrity(_norm2, _holistic_clean2):
                                # Map normalized tool name -> raw name for the cleared
                                # integrity positives (mirrors the arbiter's _int_pos set).
                                _cleared_raw = {}
                                for f in _af:
                                    if str(_gf(f, "evidence_verdict", "")).upper() != "POSITIVE":
                                        continue
                                    _rt = str(
                                        (_gf(f, "metadata", {}) or {}).get("tool_name")
                                        or _gf(f, "finding_type", "") or ""
                                    )
                                    if _rt and _rt not in NON_INTEGRITY_TOOLS:
                                        _cleared_raw[_normalize_tool_name(_rt)] = _rt
                                for p in preview:
                                    _pn = _normalize_tool_name(str(p.get("tool") or ""))
                                    if _pn in _cleared_raw and p.get("verdict") in ("FLAGGED", "NEEDS_REVIEW"):
                                        p["summary"] = uncorroborated_screening_text(_cleared_raw[_pn])
                                        p["key_signal"] = ""
                                        p["severity"] = "LOW"
                                        p["verdict"] = "CLEAN"
                                        p["finding_kind"] = "confirmation"
                        except Exception:
                            pass

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
                            def _g(f, k, d=None):
                                return f.get(k, d) if isinstance(f, dict) else getattr(f, k, d)
                            from core.severity import (
                                NON_INTEGRITY_TOOLS,
                                holistic_read_flags_manipulation,
                                should_clear_uncorroborated_integrity,
                            )
                            _vc = getattr(agent_inst, "visual_context", None)
                            _av = str(getattr(_vc, "authenticity_verdict", "") or "")
                            _ii = getattr(_vc, "image_integrity_context", None)
                            _ass = str(getattr(_ii, "integrity_assessment", "") or "").lower()
                            _holistic_clean = (_vc is not None) and not holistic_read_flags_manipulation(_av, _ass)
                            _norm = [
                                {
                                    "tool_name": (_g(f, "metadata", {}) or {}).get("tool_name")
                                    or _g(f, "finding_type", "") or "",
                                    "evidence_verdict": _g(f, "evidence_verdict", ""),
                                    "court_defensible": _g(f, "court_defensible", False),
                                    "confidence": _g(f, "confidence_raw", 0.0),
                                    "severity_tier": _g(f, "severity_tier", "")
                                    or (_g(f, "metadata", {}) or {}).get("severity_tier", ""),
                                }
                                for f in _af
                            ]
                            # Single shared decision (mirrors the arbiter EXACTLY): a
                            # lone uncorroborated integrity/AI positive the clean holistic
                            # read does not corroborate is a tool false positive. Clear it
                            # so the live card reaches the SAME verdict the signed report
                            # will, with no SUSPICIOUS/72%→AUTHENTIC flip.
                            if should_clear_uncorroborated_integrity(_norm, _holistic_clean):
                                _grounded = []
                                for f in _af:
                                    _is_pos = str(_g(f, "evidence_verdict", "")).upper() == "POSITIVE"
                                    _ftool = str(
                                        (_g(f, "metadata", {}) or {}).get("tool_name")
                                        or _g(f, "finding_type", "") or ""
                                    )
                                    if _is_pos and _ftool not in NON_INTEGRITY_TOOLS and isinstance(f, dict):
                                        _grounded.append({**f, "evidence_verdict": "INCONCLUSIVE"})
                                    else:
                                        _grounded.append(f)
                                _gv, _gc, _ = compute_agent_verdict(_grounded, visual_signal=_vsig, is_deep=_is_deep)
                                if _gv:
                                    _live_verdict, _live_conf = _gv, _gc
                except Exception:
                    pass

            await broadcast_update(
                str(session_id),
                BriefUpdate(
                    # "degraded" (per-agent timeout with partial findings) is a
                    # TERMINAL state — it must ship as AGENT_COMPLETE so the card
                    # resolves and partial findings render, not stay "running".
                    type="AGENT_COMPLETE"
                    if status in ("complete", "error", "skipped", "degraded")
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
                        # Use the caller-supplied per-tool count when given (the deep
                        # progress monitor passes the real completed-task count). Only
                        # the "validating" pre-roll seeds 0 — NEVER "running", which
                        # previously reset the live X/Y counter to 0 on every 3s deep
                        # progress poll, freezing it at 1/N while the text cycled.
                        "tools_done": tools_done if tools_done is not None else (0 if status == "validating" else None),
                        "tools_total": _count_surfacing_tasks(
                            getattr(agent_inst, "deep_task_decomposition" if analysis_phase == "deep" else "task_decomposition", [])
                        )
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
        # P2.15 — config-driven per-agent initial timeout (was hardcoded 300s).
        # Bounded by the overall investigation budget so one agent can't exceed it.
        agent_timeout = float(getattr(pipeline.config, "initial_agent_timeout_seconds", 300))
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
            # A crashed initialization (status="error") must not appear as an
            # "active" agent with no findings — that misleads the arbiter into
            # treating it as a legitimately-run agent that found nothing.
            agent_active=status not in ("unsupported", "error"),
            supports_file_type=status != "unsupported",
            error="Agent initialization failed" if status == "error" else None,
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
                from orchestration.agent_factory import AgentLoopResult as _AgentLoopResult
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
                    _a4_result_entry = _AgentLoopResult(
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
                tools_done=0,  # reset the X/Y counter for the fresh deep pass
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
                                # Count only SURFACING tasks so the deep "X/Y" tracks
                                # the same set as its denominator (_count_surfacing_tasks)
                                # and the completed "N tools ran" — context/custody tasks
                                # (e.g. read_shared_image_context on an image) execute but
                                # never surface, so counting them drifted X above Y.
                                _done_surf = sum(
                                    1 for t in _done
                                    if _task_text_surfaces(t.description, evidence_artifact)
                                )
                                _inprog_surf = 1 if (
                                    _in_progress
                                    and _task_text_surfaces(_in_progress[0].description, evidence_artifact)
                                ) else 0
                                await _broadcast_agent_status(
                                    aid,
                                    "running",
                                    f"Deep: {_current}",
                                    agent_inst=a_inst,
                                    initial_tool_names=_initial_tool_names,
                                    analysis_phase="deep",
                                    # Authoritative per-tool progress from working memory:
                                    # completed surfacing tasks + the one now in progress = current X.
                                    tools_done=_done_surf + _inprog_surf,
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
                                    tools_done=len(_done),
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
                if isinstance(finding, dict):
                    meta = finding.get("metadata") or {}
                    if not isinstance(meta, dict):
                        meta = {}
                        finding["metadata"] = meta
                else:
                    meta = getattr(finding, "metadata", None) or {}
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

            def _get_meta(f):
                if isinstance(f, dict):
                    return f.get("metadata") or {}
                return getattr(f, "metadata", None) or {}

            deep_only = [f for f in all_findings if _get_meta(f).get("analysis_phase") == "deep"]
            deep_count = len(deep_only)
            span.set_attribute("deep_finding_count", deep_count)
            span.set_attribute("total_finding_count", len(all_findings))
            return AgentLoopResult(
                agent_id=agent_id,
                findings=[f.model_dump(mode="json") if hasattr(f, "model_dump") else (f if isinstance(f, dict) else {}) for f in all_findings],
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
        # Record a provenance flag so the report distinguishes an auto-skipped
        # deep pass (no analyst response) from a deliberate baseline acceptance.
        # Matters for court-admissibility — the two look identical otherwise.
        try:
            existing_flags = list(getattr(pipeline, "_degradation_flags", []) or [])
            if "DEEP_ANALYSIS_AUTO_SKIPPED_TIMEOUT" not in existing_flags:
                existing_flags.append("DEEP_ANALYSIS_AUTO_SKIPPED_TIMEOUT")
            pipeline._degradation_flags = existing_flags
        except Exception:
            pass
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
        # II.1 — record that the analyst-decision window timed out so the signed
        # report DISCLOSES that final synthesis proceeded automatically (not
        # analyst-confirmed), instead of silently shipping a bare template report.
        try:
            pipeline.arbiter._gate2_timed_out = True
        except Exception:
            pass
    finally:
        pipeline._awaiting_user_decision = False
        try:
            await redis.delete(decision_key)
        except Exception as _e:
            logger.debug("Decision key cleanup skipped (Redis may be unavailable)", error=str(_e))
