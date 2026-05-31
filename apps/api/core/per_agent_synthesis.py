from __future__ import annotations
import json
import asyncio
from typing import Literal, Any, Dict, List, Optional
from pydantic import BaseModel, Field
from core.config import Settings
from core.llm_client import LLMClient
from core.visual_context_models import VisualContext
from core.finding_formatter import TOOL_LABELS
from core.structured_logging import get_logger

logger = get_logger(__name__)

# ── Pydantic models for per-agent synthesis ──

class VisualContextSplit(BaseModel):
    agent1_image_integrity: dict = Field(default_factory=dict)
    agent3_object_scene: dict = Field(default_factory=dict)
    agent5_metadata_visual: dict = Field(default_factory=dict)
    source: Literal["llm_assisted", "local_ensemble", "none"] = "none"
    external_llm_used: bool = False
    available: bool = False
    limitations: list[str] = Field(default_factory=list)


class AgentSynthesisInput(BaseModel):
    agent_id: Literal["Agent1", "Agent3", "Agent5"]
    persona_name: str
    persona_rules: dict = Field(default_factory=dict)
    visual_context_section: Optional[dict] = None
    visual_context_available: bool = False
    completed_tools: list[str] = Field(default_factory=list)
    failed_tools: list[str] = Field(default_factory=list)
    not_applicable_tools: list[str] = Field(default_factory=list)
    findings: list[dict] = Field(default_factory=list)
    grounded_findings: list[dict] = Field(default_factory=list)
    agent_verdict: str = "INCONCLUSIVE"
    agent_confidence: float = 0.0
    confidence_reason: str = ""


class AgentSynthesisOutput(BaseModel):
    agent_id: str
    agent_brief: str
    visual_context_summary: str = ""
    key_findings: list[str] = Field(default_factory=list)
    agent_verdict: str
    confidence_score: float
    confidence_reason: str = ""
    limitations: list[str] = Field(default_factory=list)
    synthesis_source: Literal[
        "groq_refined", 
        "deterministic_with_visual_context", 
        "deterministic_tool_only", 
        "groq_tool_only"
    ]


# ── Helper functions ──

def split_visual_context(session_id: str, context_obj: VisualContext | None) -> VisualContextSplit:
    """Split the visual context into per-agent views."""
    if context_obj is None:
        return VisualContextSplit(
            agent1_image_integrity={},
            agent3_object_scene={},
            agent5_metadata_visual={},
            source="none",
            external_llm_used=False,
            available=False,
            limitations=["Visual context not available."]
        )
    
    # Image integrity
    img_integrity = (
        context_obj.image_integrity_context.model_dump()
        if hasattr(context_obj.image_integrity_context, "model_dump")
        else dict(context_obj.image_integrity_context or {})
    )
    
    # Object scene
    obj_scene = (
        context_obj.object_scene_context.model_dump()
        if hasattr(context_obj.object_scene_context, "model_dump")
        else dict(context_obj.object_scene_context or {})
    )
    obj_scene.update({
        "extracted_text": context_obj.extracted_text or [],
        "detected_objects": [
            (obj.model_dump() if hasattr(obj, "model_dump") else dict(obj or {}))
            for obj in (context_obj.detected_objects or [])
        ],
        "interface_elements": context_obj.interface_elements or [],
        "scene_description": context_obj.scene_description or "",
    })

    # Metadata visual
    meta_visual = (
        context_obj.metadata_visual_context.model_dump()
        if hasattr(context_obj.metadata_visual_context, "model_dump")
        else dict(context_obj.metadata_visual_context or {})
    )
    meta_visual.update({
        "visible_timestamps": context_obj.visible_timestamps or [],
        "file_type_assessment": context_obj.file_type_assessment or "",
    })

    return VisualContextSplit(
        agent1_image_integrity=img_integrity,
        agent3_object_scene=obj_scene,
        agent5_metadata_visual=meta_visual,
        source=context_obj.source,
        external_llm_used=context_obj.external_llm_used,
        available=True,
        limitations=context_obj.limitations or []
    )


def format_finding_first(finding: dict) -> str:
    """Format any finding dict to enforce the `[Finding] — [Tool(s)] ([Confidence]%)` syntax."""
    meta = finding.get("metadata") or {}
    tool_id = meta.get("tool_name") or finding.get("finding_type") or "forensic_tool"
    tool_label = TOOL_LABELS.get(tool_id, tool_id.replace("_", " ").title())

    # Extract finding text/signal
    finding_text = (
        meta.get("key_signal")
        or finding.get("reasoning_summary")
        or meta.get("summary")
        or finding.get("finding_type")
        or "Anomaly signature check"
    )

    finding_text = str(finding_text).strip()
    # Strip tool prefix if it duplicates the tool name
    if tool_label.lower() in finding_text.lower():
        for prefix in (tool_label + ":", tool_label + " -", tool_label + " —", tool_label):
            if finding_text.lower().startswith(prefix.lower()):
                finding_text = finding_text[len(prefix):].strip()
                break

    verdict = str(finding.get("evidence_verdict") or "INCONCLUSIVE").upper()
    conf = finding.get("confidence_raw") or meta.get("confidence") or finding.get("raw_confidence_score")

    if verdict in ("NOT_APPLICABLE", "ERROR") or conf is None:
        return f"{finding_text} — {tool_label}"
    else:
        conf_pct = int(round(float(conf) * 100))
        return f"{finding_text} — {tool_label} ({conf_pct}%)"


def generate_deterministic_agent_synthesis(input_data: AgentSynthesisInput) -> AgentSynthesisOutput:
    """Generates structured agent findings and summary deterministically based on tool results."""
    # Build list of key findings using the standard formatting
    key_findings = []
    for f in input_data.grounded_findings or input_data.findings:
        key_findings.append(format_finding_first(f))

    # Formulate visual context summary if available
    vis_summary = ""
    if input_data.visual_context_available and input_data.visual_context_section:
        section = input_data.visual_context_section
        if input_data.agent_id == "Agent1":
            ass = section.get("integrity_assessment") or "cannot_determine"
            signals = section.get("visible_manipulation_signals") or []
            vis_summary = f"Visual assessment: {ass}."
            if signals:
                vis_summary += f" Detected signals: {', '.join(signals)}."
        elif input_data.agent_id == "Agent3":
            desc = section.get("scene_description") or ""
            objs = section.get("objects") or []
            vis_summary = f"Visual scene: {desc}."
            if objs:
                vis_summary += f" Objects: {', '.join(objs[:5])}."
        elif input_data.agent_id == "Agent5":
            clues = section.get("device_or_platform_clues") or []
            vis_summary = "Visual metadata: "
            if clues:
                vis_summary += f"Device/Platform clues: {', '.join(clues)}."
            else:
                vis_summary += "No visual metadata clues identified."
    else:
        vis_summary = "Shared visual context was unavailable for this agent."

    # Build agent brief
    if key_findings:
        findings_joined = "; ".join(key_findings[:3])
        agent_brief = f"{input_data.agent_id} completed analysis with findings: {findings_joined}."
    else:
        agent_brief = f"{input_data.agent_id} completed analysis. No specific anomalies were confirmed."

    source_mode = "deterministic_with_visual_context" if input_data.visual_context_available else "deterministic_tool_only"

    # Limitations are from failed tools
    limitations = []
    if input_data.failed_tools:
        limitations.append(f"Tool execution failures: {', '.join(input_data.failed_tools)}")

    return AgentSynthesisOutput(
        agent_id=input_data.agent_id,
        agent_brief=agent_brief,
        visual_context_summary=vis_summary,
        key_findings=key_findings,
        agent_verdict=input_data.agent_verdict,
        confidence_score=input_data.agent_confidence,
        confidence_reason=input_data.confidence_reason or f"Determined by {len(input_data.completed_tools)} completed tools.",
        limitations=limitations,
        synthesis_source=source_mode
    )


async def refine_synthesis_batch(
    inputs: dict[str, AgentSynthesisInput], 
    config: Settings
) -> dict[str, AgentSynthesisOutput]:
    """Single batched synthesis refiner. 
    Constructs a single prompt for Groq/Cerebras containing all three agent inputs,
    makes one single LLM call, and falls back to deterministic if fails.
    """
    outputs = {}
    
    # 1. First, build deterministic syntheses as the fallback and foundation
    for aid, inp in inputs.items():
        outputs[aid] = generate_deterministic_agent_synthesis(inp)

    # 2. Check if LLM is enabled and configured
    llm_client = LLMClient(config=config)
    if not (config.llm_enable_post_synthesis and config.llm_api_key and llm_client.is_available):
        logger.info("Groq batched synthesis skipped (LLM disabled/unavailable).")
        return outputs

    # 3. Construct the prompt
    batch_prompt_data = {}
    for aid, inp in inputs.items():
        # Convert findings/grounded_findings to clean dicts without excess payload
        clean_findings = []
        for f in (inp.grounded_findings or inp.findings):
            clean_findings.append({
                "tool": f.get("metadata", {}).get("tool_name") or f.get("finding_type"),
                "summary": f.get("reasoning_summary") or f.get("metadata", {}).get("summary"),
                "verdict": f.get("evidence_verdict"),
                "confidence": f.get("confidence_raw") or f.get("metadata", {}).get("confidence")
            })

        batch_prompt_data[aid] = {
            "agent_id": inp.agent_id,
            "persona_name": inp.persona_name,
            "persona_rules": inp.persona_rules,
            "visual_context_available": inp.visual_context_available,
            "visual_context_section": inp.visual_context_section,
            "completed_tools": inp.completed_tools,
            "failed_tools": inp.failed_tools,
            "findings": clean_findings,
            "agent_verdict": inp.agent_verdict,
            "agent_confidence": inp.agent_confidence,
            "confidence_reason": inp.confidence_reason
        }

    system_prompt = (
        "You are a forensic report narrative refiner. You are given the raw tool results, verdicts, "
        "and visual contexts for Agent1 (Image Integrity), Agent3 (Object/Scene/Contraband), and Agent5 (Metadata/Provenance).\n"
        "Your task is to refine and polish the 'agent_brief', 'visual_context_summary', 'confidence_reason', "
        "and 'key_findings' lists into professional, cohesive, provider-neutral forensic language.\n"
        "STRICT CONSTRAINTS:\n"
        "1. DO NOT change the 'agent_verdict' or 'agent_confidence' values. They are strictly computed by local validators.\n"
        "2. DO NOT mention any provider or model names (e.g. Gemini, Groq, Cerebras, OpenAI, Llama, Google, NCFI, NCFTA).\n"
        "3. DO NOT treat missing API access or LLM unavailable as a degradation. Only tool execution failures may appear as limitations.\n"
        "4. Enforce a finding-first format for each refined key finding: `[Finding] — [Tool(s)] ([Confidence]%)`.\n"
        "5. Output a single valid JSON object mapping agent IDs ('Agent1', 'Agent3', 'Agent5') to their polished outputs.\n"
        "Do not include any chat formatting, markdown, or explainers. Just return the raw JSON matching this schema:\n"
        "{\n"
        "  \"Agent1\": {\n"
        "    \"agent_brief\": \"Polished summary description...\",\n"
        "    \"visual_context_summary\": \"Polished visual context summary...\",\n"
        "    \"key_findings\": [\"Finding A — Tool Name (80%)\", \"Finding B — Tool Name (95%)\"],\n"
        "    \"confidence_reason\": \"Polished explanation...\",\n"
        "    \"limitations\": []\n"
        "  },\n"
        "  \"Agent3\": { ... },\n"
        "  \"Agent5\": { ... }\n"
        "}"
    )

    user_payload = json.dumps(batch_prompt_data, indent=2, default=str)

async def refine_synthesis_batch(
    inputs: dict[str, AgentSynthesisInput], 
    config: Settings
) -> dict[str, AgentSynthesisOutput]:
    """Single batched synthesis refiner. 
    Constructs a single prompt for Groq/Cerebras containing all three agent inputs,
    makes one single LLM call, and falls back to deterministic if fails.
    """
    outputs = {}
    
    # 1. First, build deterministic syntheses as the fallback and foundation
    for aid, inp in inputs.items():
        outputs[aid] = generate_deterministic_agent_synthesis(inp)

    # 2. Check if LLM is enabled and configured
    llm_client = LLMClient(config=config)
    if not (config.llm_enable_post_synthesis and config.llm_api_key and llm_client.is_available):
        logger.info("Groq batched synthesis skipped (LLM disabled/unavailable).")
        return outputs

    # 3. Construct the prompt
    batch_prompt_data = {}
    for aid, inp in inputs.items():
        # Convert findings/grounded_findings to clean dicts without excess payload
        clean_findings = []
        for f in (inp.grounded_findings or inp.findings):
            clean_findings.append({
                "tool": f.get("metadata", {}).get("tool_name") or f.get("finding_type"),
                "summary": f.get("reasoning_summary") or f.get("metadata", {}).get("summary"),
                "verdict": f.get("evidence_verdict"),
                "confidence": f.get("confidence_raw") or f.get("metadata", {}).get("confidence")
            })

        batch_prompt_data[aid] = {
            "agent_id": inp.agent_id,
            "persona_name": inp.persona_name,
            "persona_rules": inp.persona_rules,
            "visual_context_available": inp.visual_context_available,
            "visual_context_section": inp.visual_context_section,
            "completed_tools": inp.completed_tools,
            "failed_tools": inp.failed_tools,
            "findings": clean_findings,
            "agent_verdict": inp.agent_verdict,
            "agent_confidence": inp.agent_confidence,
            "confidence_reason": inp.confidence_reason
        }

    system_prompt = (
        "You are a forensic report narrative refiner. You are given the raw tool results, verdicts, "
        "and visual contexts for Agent1 (Image Integrity), Agent3 (Object/Scene/Contraband), and Agent5 (Metadata/Provenance).\n"
        "Your task is to refine and polish the 'agent_brief', 'visual_context_summary', 'confidence_reason', "
        "and 'key_findings' lists into professional, cohesive, provider-neutral forensic language.\n"
        "STRICT CONSTRAINTS:\n"
        "1. DO NOT change the 'agent_verdict' or 'agent_confidence' values. They are strictly computed by local validators.\n"
        "2. DO NOT mention any provider or model names (e.g. Gemini, Groq, Cerebras, OpenAI, Llama, Google, NCFI, NCFTA).\n"
        "3. DO NOT treat missing API access or LLM unavailable as a degradation. Only tool execution failures may appear as limitations.\n"
        "4. Enforce a finding-first format for each refined key finding: `[Finding] — [Tool(s)] ([Confidence]%)`.\n"
        "5. Output a single valid JSON object mapping agent IDs ('Agent1', 'Agent3', 'Agent5') to their polished outputs.\n"
        "Do not include any chat formatting, markdown, or explainers. Just return the raw JSON matching this schema:\n"
        "{\n"
        "  \"Agent1\": {\n"
        "    \"agent_brief\": \"Polished summary description...\",\n"
        "    \"visual_context_summary\": \"Polished visual context summary...\",\n"
        "    \"key_findings\": [\"Finding A — Tool Name (80%)\", \"Finding B — Tool Name (95%)\"],\n"
        "    \"confidence_reason\": \"Polished explanation...\",\n"
        "    \"limitations\": []\n"
        "  },\n"
        "  \"Agent3\": { ... },\n"
        "  \"Agent5\": { ... }\n"
        "}"
    )

    user_payload = json.dumps(batch_prompt_data, indent=2, default=str)

    try:
        raw_response = await llm_client.generate_synthesis(
            system_prompt=system_prompt,
            user_content=user_payload,
            json_mode=True,
            priority="medium"
        )
        if raw_response:
            cleaned_resp = raw_response.strip()
            if cleaned_resp.startswith("```"):
                lines = cleaned_resp.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                cleaned_resp = "\n".join(lines).strip()

            parsed = json.loads(cleaned_resp)
            for aid in ("Agent1", "Agent3", "Agent5"):
                if aid in parsed and aid in outputs:
                    polished_data = parsed[aid]
                    brief = polished_data.get("agent_brief")
                    if brief and isinstance(brief, str):
                        outputs[aid].agent_brief = brief
                    
                    vc_sum = polished_data.get("visual_context_summary")
                    if vc_sum and isinstance(vc_sum, str):
                        outputs[aid].visual_context_summary = vc_sum
                    
                    reason = polished_data.get("confidence_reason")
                    if reason and isinstance(reason, str):
                        outputs[aid].confidence_reason = reason
                    
                    kfs = polished_data.get("key_findings")
                    if kfs and isinstance(kfs, list):
                        validated_kfs = []
                        for kf in kfs:
                            kf_str = str(kf).strip()
                            if " — " in kf_str:
                                validated_kfs.append(kf_str)
                            else:
                                validated_kfs.append(kf_str)
                        if validated_kfs:
                            outputs[aid].key_findings = validated_kfs
                    
                    outputs[aid].synthesis_source = "groq_refined"
                    logger.info(f"Refined synthesis for {aid} using LLM.")
    except Exception as e:
        logger.warning(f"Batched synthesis refinement failed or rejected: {e}. Using deterministic fallbacks.")
        # Fallbacks are already populated in outputs

    return outputs
