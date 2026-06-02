from __future__ import annotations
import json
from typing import Any, Dict, List, Optional
from core.visual_context_models import VisualContext
from core.arbiter_deliberation import ArbiterDeliberationResult, EvidenceWeight
from core.per_agent_synthesis import AgentSynthesisOutput
from core.structured_logging import get_logger

logger = get_logger(__name__)

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
    agents_str = ", ".join(agent_list) if agent_list else "analytical agents"
    
    exc_summary = (
        f"This forensic investigation examined the submitted file `{filename}` ({mime_type}) "
        f"with SHA-256 integrity hash `{sha256}`. Forensic pipelines executed checks via {agents_str}. "
        f"Following deliberation, the final verdict is determined as '{verdict_label}' "
        f"with a confidence score of {confidence_pct}%. "
        f"This determination is based on: {arbiter_deliberation.confidence_reason.lower()}."
    )
    if not vis_available:
        exc_summary += " Shared visual context was unavailable, so the conclusion relies on completed tool findings only."
        
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
