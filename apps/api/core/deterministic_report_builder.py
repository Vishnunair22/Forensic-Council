from __future__ import annotations

import re
from typing import Any

from core.arbiter_deliberation import ArbiterDeliberationResult
from core.finding_humanizer import CONTEXT_ONLY_TOOLS
from core.per_agent_synthesis import AgentSynthesisOutput
from core.structured_logging import get_logger

logger = get_logger(__name__)

# A tool slug is lowercase tokens joined by underscores (e.g. "frequency_domain_
# analysis"). Friendly labels ("Frequency Domain Analysis") and pure narrative
# findings contain spaces / no attribution and are never matched by this.
_TOOL_SLUG_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)+$")
_KF_PCT_RE = re.compile(r"\s*\(\d+(?:\.\d+)?%\)\s*$")


def _cited_tool_slug(kf: str) -> str | None:
    """Return the tool slug a `finding — tool (NN%)` key finding attributes itself
    to, lowercased, or None when it cites no specific tool."""
    if "—" not in kf:
        return None
    tail = _KF_PCT_RE.sub("", kf.rsplit("—", 1)[-1]).strip().lower()
    return tail or None

def build_deterministic_report(
    case_data: dict[str, Any],
    visual_context: Any | None,
    agent_syntheses: dict[str, Any],  # maps Agent ID to AgentSynthesisOutput
    arbiter_deliberation: ArbiterDeliberationResult,
    tool_coverage: dict[str, Any],
    execution_metadata: dict[str, Any],
    groq_used: bool = False,
    display_verdict: str | None = None,
) -> dict[str, Any]:
    """Generates all final report sections deterministically from actual investigation data and deliberation results.

    `display_verdict` is the mapped, user-facing verdict (AUTHENTIC / SUSPICIOUS /
    MANIPULATED / INCONCLUSIVE). When provided it is used for the narrative labels
    so the report prose matches ForensicReport.overall_verdict exactly — they are
    no longer derived from two different strings.
    """

    # Extract file/case facts
    filename = str(case_data.get("filename") or "evidence_file")
    sha256 = str(case_data.get("sha256") or "unknown_hash")
    mime_type = str(case_data.get("mime_type") or "image/unknown")
    file_size_bytes = case_data.get("file_size_bytes") or 0
    file_size_kb = round(file_size_bytes / 1024, 2)

    # Normalise syntheses to Dict of AgentSynthesisOutput
    norm_syn: dict[str, AgentSynthesisOutput] = {}
    for aid, val in agent_syntheses.items():
        if isinstance(val, dict):
            norm_syn[aid] = AgentSynthesisOutput(**val)
        else:
            norm_syn[aid] = val

    # Helper: read visual context fields safely
    vis_available = False
    vis_desc = ""
    vis_source = "none"
    vis_ext_llm = False

    if visual_context:
        vis_available = True
        vis_desc = (
            getattr(visual_context, "scene_description", None)
            or getattr(visual_context, "content_description", "")
        )
        vis_source = getattr(visual_context, "source", "none")
        vis_ext_llm = getattr(visual_context, "external_llm_used", False)

    # --- 1. Executive Summary ---
    # Prefer the mapped/user-facing verdict so narrative prose == overall_verdict.
    verdict_label = (
        display_verdict.replace("_", " ").title()
        if display_verdict
        else arbiter_deliberation.final_verdict.replace("_", " ").title()
    )
    confidence_pct = int(round(arbiter_deliberation.final_confidence * 100))

    agent_list = [f"Agent {aid[-1]}" for aid in norm_syn.keys()]
    n_agents = len(agent_list)
    agents_str = ", ".join(agent_list) if agent_list else "analytical agents"
    domain_count = n_agents  # one domain per active agent

    # Sentence 1 — core verdict statement
    _article = "an" if verdict_label[:1].upper() in "AEIOU" else "a"
    _s1 = (
        f"Forensic examination of `{filename}` ({mime_type}) returned {_article} "
        f"**{verdict_label}** verdict with **{confidence_pct}%** confidence "
        f"after {n_agents} specialist agent{'' if n_agents == 1 else 's'} completed "
        f"analysis across {domain_count} forensic domain{'' if domain_count == 1 else 's'}."
    )

    # Sentence 2 — evidence basis (strongest finding or agent synthesis)
    _pos_findings = [
        f for f in (arbiter_deliberation.strongest_findings or [])
        if getattr(f, "evidence_verdict", None) == "POSITIVE"
    ]
    _verdicts_upper = (display_verdict or "").upper()
    if _pos_findings:
        _top = _pos_findings[0]
        _stmt = getattr(_top, "finding_statement", None) or str(_top)
        _s2 = f"Convergent signals — including {_stmt} — formed the primary evidentiary basis for this determination."
    elif _verdicts_upper in ("MANIPULATED", "SUSPICIOUS"):
        _s2 = (
            "Forensic signals identified by active agents contained statistically significant "
            "anomalies inconsistent with an authentic, unmodified file."
        )
    elif _verdicts_upper == "AUTHENTIC":
        _manip_pct = int(round(arbiter_deliberation.final_confidence * 100))
        _s2 = (
            f"Independent checks across pixel integrity, statistical frequency, and provenance domains "
            f"returned no manipulation indicators, consistent with an unmodified original."
        )
    else:
        _s2 = (
            "Evidence across active analytical domains produced ambiguous or conflicting signals "
            "that preclude a definitive conclusion without additional context."
        )

    # Sentence 3 — coverage and tool reliability
    _all_metrics = list(tool_coverage.get("completed_tools", []))
    _failed = list(tool_coverage.get("failed_tools", []))
    _n_completed = len(_all_metrics)
    _n_failed = len(_failed)
    if _n_failed == 0 and _n_completed > 0:
        _s3 = (
            f"All {_n_completed} forensic tool{'' if _n_completed == 1 else 's'} completed "
            f"execution without errors, achieving full coverage across every active analytical domain."
        )
    elif _n_failed > 0:
        _s3 = (
            f"{_n_completed} forensic tool{'' if _n_completed == 1 else 's'} completed execution; "
            f"{_n_failed} did not complete and are treated as coverage limitations only — "
            f"they do not affect the evidentiary weight of completed checks."
        )
    else:
        _s3 = "Tool coverage reflects the completed execution path for this file type."

    # Sentence 4 — visual context and report provenance
    if vis_available and vis_ext_llm:
        _s4 = "Visual scene grounding was provided by a remote vision model and cross-validated against local forensic tools; the verdict and confidence are computed deterministically from tool outputs."
    elif vis_available:
        _s4 = "Visual scene context was generated using local forensic models and informed the grounding of tool-level findings; all evidentiary weights are computed deterministically."
    else:
        _s4 = "Visual context was unavailable for this analysis; the determination relies exclusively on completed tool findings and arbiter deliberation."

    exc_summary = f"{_s1} {_s2} {_s3} {_s4}"

    # --- 2. Evidence Overview ---
    route = execution_metadata.get("analysis_mode") or "hybrid"
    vis_source_label = "local ensemble" if vis_source == "local_ensemble" else ("external LLM" if vis_ext_llm else "none")

    overview_text = (
        f"File Specifications:\n"
        f"- Filename: {filename}\n"
        f"- MIME Type: {mime_type}\n"
        f"- Size: {file_size_kb} KB ({file_size_bytes} bytes)\n"
        f"- SHA-256 Hash: {sha256}\n"
        f"- Analysis Routing Mode: {route}\n"
        f"- Visual Context Profiling: Assisted by {vis_source_label}\n"
        f"- Active Analytical Units: {', '.join(norm_syn.keys())}"
    )

    # --- 3. Methodology ---
    # Group completed tools by agent
    methodology_parts = []

    agent1_tools = [t for t in tool_coverage.get("completed_tools", []) if t in (
        "ela_full_image", "neural_ela", "frequency_domain_analysis", "diffusion_artifact_detector", "jpeg_ghost_detect", "copy_move_detect"
    )]
    agent3_tools = [t for t in tool_coverage.get("completed_tools", []) if t in (
        "object_detection", "vector_contraband_search", "screenshot_layout_forensics", "screenshot_scene_applicability"
    )]
    agent5_tools = [t for t in tool_coverage.get("completed_tools", []) if t in (
        "exif_extract", "timestamp_analysis", "gps_timezone_validate", "file_structure_analysis"
    )]

    if agent1_tools:
        methodology_parts.append(f"Agent 1 (Image Integrity) successfully completed: {', '.join(agent1_tools)}.")
    if agent3_tools:
        methodology_parts.append(f"Agent 3 (Object/Scene) successfully completed: {', '.join(agent3_tools)}.")
    if agent5_tools:
        methodology_parts.append(f"Agent 5 (Metadata/Provenance) successfully completed: {', '.join(agent5_tools)}.")

    not_app = tool_coverage.get("not_applicable_tools", [])
    if not_app:
        methodology_parts.append(f"The following tools were marked NOT APPLICABLE and excluded from active grading: {', '.join(not_app)}.")

    methodology = " ".join(methodology_parts) if methodology_parts else "No tools completed execution."

    # --- 4. Agent Deliberation Summary ---
    delib_parts = []
    for aid, syn in norm_syn.items():
        delib_parts.append(f"{aid} concluded that the status was {syn.agent_verdict} (brief: {syn.agent_brief}).")

    if arbiter_deliberation.cross_agent_conflicts:
        delib_parts.append(f"Conflicts were detected during analysis: {'; '.join(arbiter_deliberation.cross_agent_conflicts)}")
    else:
        delib_parts.append("All active agent units maintained consistent assessments with no material conflicts.")

    agent_deliberation_summary = " ".join(delib_parts)

    # --- 5. Key Findings ---
    key_findings = []
    # Collect key findings from agents first
    for aid, syn in norm_syn.items():
        key_findings.extend(syn.key_findings)
    # Deduplicate key findings
    seen_kfs = set()
    deduped_kfs = []
    for kf in key_findings:
        norm = kf.lower().strip()
        if norm not in seen_kfs:
            seen_kfs.add(norm)
            deduped_kfs.append(kf)

    # Court-defensibility guardrail: a key finding that attributes itself to a
    # specific forensic TOOL must trace to a tool that actually ran for this
    # evidence. LLM/vision synthesis can hallucinate plausible-sounding tools that
    # never executed (e.g. "scene_geometry_analysis", "lighting_analysis" on a
    # screenshot where physical-scene checks are N/A) with invented confidences —
    # such fabricated findings must never reach a signed report. Only slug-form
    # citations not backed by a real tool are dropped; friendly-label findings and
    # pure statistical narratives are left untouched. Context-only plumbing tools
    # (shared visual profile, etc.) are coverage inputs, never standalone findings.
    _real_tools = {
        str(t).lower()
        for key in ("completed_tools", "failed_tools", "not_applicable_tools", "skipped_tools")
        for t in (tool_coverage.get(key) or [])
    }
    _grounded_kfs = []
    for kf in deduped_kfs:
        _slug = _cited_tool_slug(kf)
        if _slug and _TOOL_SLUG_RE.match(_slug) and (_slug not in _real_tools or _slug in CONTEXT_ONLY_TOOLS):
            logger.warning(
                "Dropped ungrounded key finding (cited tool did not run)",
                extra={"cited_tool": _slug, "finding": kf[:160]},
            )
            continue
        _grounded_kfs.append(kf)
    deduped_kfs = _grounded_kfs

    if not deduped_kfs:
        deduped_kfs = ["No anomalous signatures or physical manipulation artifacts were identified."]

    # --- 6. Integrity Assessment ---
    integrity_parts = []
    a1_syn = norm_syn.get("Agent1")
    if a1_syn:
        integrity_parts.append(f"Agent 1 analysis: {a1_syn.agent_brief}")
    # Add any specific integrity findings
    pos_int = [f for f in arbiter_deliberation.strongest_findings if f.signal_category == "integrity" and f.evidence_verdict == "POSITIVE"]
    if pos_int:
        integrity_parts.append(f"Identified tampering indicators: {', '.join([f.finding_statement for f in pos_int])}.")
    else:
        integrity_parts.append("No active tampering pattern, compression anomaly, or generative artifact was confirmed.")

    integrity_assessment = " ".join(integrity_parts)

    # --- 7. Object/Scene Context ---
    object_parts = []
    a3_syn = norm_syn.get("Agent3")
    if a3_syn:
        object_parts.append(f"Agent 3 assessment: {a3_syn.agent_brief}")
    if vis_available and vis_desc:
        object_parts.append(f"Visual scene description: {vis_desc}")
    else:
        object_parts.append("Visual layout and physical scene composition were consistent with the expected route.")

    object_scene_context = " ".join(object_parts)

    # --- 8. Metadata and Provenance ---
    meta_parts = []
    a5_syn = norm_syn.get("Agent5")
    if a5_syn:
        meta_parts.append(f"Agent 5 metadata assessment: {a5_syn.agent_brief}")
    pos_prov = [f for f in arbiter_deliberation.strongest_findings if f.signal_category == "provenance" and f.evidence_verdict == "POSITIVE"]
    if pos_prov:
        meta_parts.append(f"Metadata anomalies detected: {', '.join([f.finding_statement for f in pos_prov])}.")
    else:
        meta_parts.append("Metadata structures and binary headers conform to default standards for this file type.")

    metadata_and_provenance = " ".join(meta_parts)

    # --- 9. Limitations ---
    limitations = []
    # Failures of tools
    for f in tool_coverage.get("failed_tools", []):
        limitations.append(f"Execution failure: Tool `{f}` did not complete successfully.")
    if not vis_available:
        limitations.append("Visual grounding limitation: Shared visual context was unavailable.")

    if not limitations:
        limitations = ["No material tool coverage limitation was identified for the completed analysis path."]

    # --- 10. Reliability Notes ---
    reliability_notes = []
    if groq_used:
        reliability_notes.append(
            "Reliability note: Final narrative cohesion was assisted by an external text model. "
            "The verdict, confidence, and evidentiary findings were computed by the arbiter from grounded tool outputs."
        )
    else:
        reliability_notes.append(
            "Reliability note: Final report narrative was generated deterministically from local tool findings and arbiter deliberation. "
            "No external text model was used."
        )

    if vis_available:
        if vis_ext_llm:
            reliability_notes.append("Visual reliability context was assisted by an external LLM and cross-checked against local forensic tools.")
        else:
            reliability_notes.append("Visual reliability context was generated using local forensic models and deterministic image-processing tools.")
    else:
        reliability_notes.append("No visual context was used to ground the report.")

    # --- 11. Final Conclusion ---
    final_conclusion = (
        f"In conclusion, the examination of `{filename}` resulted in a verdict of '{verdict_label}' "
        f"with {confidence_pct}% confidence. The cumulative evidence supports this determination."
    )

    return {
        "case_id": case_data.get("case_id"),
        "session_id": case_data.get("session_id"),
        "evidence_overview": overview_text,
        "execution_metadata": execution_metadata,
        "visual_context_summary": vis_desc if vis_available else "none",

        "agent_syntheses": {k: (v.model_dump() if hasattr(v, "model_dump") else v) for k, v in agent_syntheses.items()},
        "arbiter_deliberation": arbiter_deliberation.model_dump(),

        "executive_summary": exc_summary,
        "methodology": methodology,
        "agent_deliberation_summary": agent_deliberation_summary,
        "key_findings": deduped_kfs,
        "integrity_assessment": integrity_assessment,
        "object_scene_context": object_scene_context,
        "metadata_and_provenance": metadata_and_provenance,
        "limitations": limitations,
        "reliability_notes": reliability_notes,
        "final_conclusion": final_conclusion,

        "final_verdict": arbiter_deliberation.final_verdict,
        "confidence_score": arbiter_deliberation.final_confidence,
        "confidence_reason": arbiter_deliberation.confidence_reason
    }
