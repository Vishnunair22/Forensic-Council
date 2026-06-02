from __future__ import annotations

import asyncio
import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.agent_personas import get_agent_narrative_persona
from core.config import Settings
from core.finding_formatter import TOOL_LABELS
from core.llm_client import LLMClient
from core.structured_logging import get_logger
from core.visual_context_models import VisualContext

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
    visual_context_section: dict | None = None
    visual_context_available: bool = False
    evidence_identity: str = ""
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

    verdict = str(finding.get("evidence_verdict") or "INCONCLUSIVE").upper()
    status = str(finding.get("status") or "").upper()

    # Honest default when a tool carries no narratable text: a failed/incomplete
    # tool is a coverage gap, never a fabricated "anomaly signature" line.
    if verdict == "ERROR" or status in ("INCOMPLETE", "TIMEOUT", "FAILED"):
        _default_text = f"{tool_label} did not complete — coverage gap"
    elif verdict in ("NEGATIVE", "CLEAN"):
        _default_text = "No supported anomaly signal"
    else:
        _default_text = "No determinate signal"

    # Extract finding text/signal
    finding_text = (
        meta.get("key_signal")
        or finding.get("reasoning_summary")
        or meta.get("summary")
        or finding.get("finding_type")
        or _default_text
    )

    finding_text = str(finding_text).strip()
    # Strip tool prefix if it duplicates the tool name
    if tool_label.lower() in finding_text.lower():
        for prefix in (tool_label + ":", tool_label + " -", tool_label + " —", tool_label):
            if finding_text.lower().startswith(prefix.lower()):
                finding_text = finding_text[len(prefix):].strip()
                break

    conf = finding.get("confidence_raw") or meta.get("confidence") or finding.get("raw_confidence_score")

    if verdict in ("NOT_APPLICABLE", "ERROR") or conf is None:
        return f"{finding_text} — {tool_label}"
    else:
        conf_pct = int(round(float(conf) * 100))
        return f"{finding_text} — {tool_label} ({conf_pct}%)"


_FILE_TYPE_ARTICLE = {
    "screenshot": "a screenshot",
    "photograph": "a photograph",
    "document_scan": "a scanned document",
    "ai_generated": "an AI-generated image",
    "composite": "a composite image",
}


def compose_evidence_identity(visual_context: Any) -> str:
    """Compose a short 'what the evidence appears to be' fragment from the
    visual context, for use after 'The evidence presents as ...'.

    This is INFERENCE (vision-derived), not a forensic finding — the brief
    frames it as observed context, never as a conclusion.
    Returns "" when no usable context exists.
    """
    if visual_context is None:
        return ""
    ft = str(getattr(visual_context, "file_type_assessment", "") or "").strip().lower()
    scene = str(getattr(visual_context, "scene_description", "") or "").strip()

    lead = _FILE_TYPE_ARTICLE.get(ft, ft if ft and ft not in ("unknown", "") else "")
    if lead and scene:
        scene_frag = scene.rstrip(".")
        # Avoid "a screenshot depicting a screenshot of ..."
        if ft and ft in scene_frag.lower()[:20]:
            return scene_frag
        return f"{lead} depicting {scene_frag[0].lower()}{scene_frag[1:]}"
    if lead:
        return lead
    if scene:
        return scene.rstrip(".")
    return ""


_BOILERPLATE_FINDING_MARKERS = (
    "found no supported anomaly signal",
    "completed with no",
    "no anomaly",
    "returned an inconclusive result",
    "was bypassed",
    "completed and found no",
    "no manipulation indicators",
    "no significant findings",
)


def _is_boilerplate_finding(text: str) -> bool:
    t = (text or "").lower()
    return any(marker in t for marker in _BOILERPLATE_FINDING_MARKERS)


def generate_deterministic_agent_synthesis(input_data: AgentSynthesisInput) -> AgentSynthesisOutput:
    """Generates structured agent findings and summary deterministically based on tool results."""
    # Build key findings — surface real signals, but collapse clean results into
    # one coverage statement rather than emitting a generic boilerplate line per
    # clean tool (which floods the report with fallback-looking text).
    _source_findings = input_data.grounded_findings or input_data.findings
    _meaningful: list[str] = []
    _clean_tools: list[str] = []
    for f in _source_findings:
        verdict = str(f.get("evidence_verdict") or "").upper()
        formatted = format_finding_first(f)
        meta = f.get("metadata") or {}
        tool_label = TOOL_LABELS.get(
            meta.get("tool_name") or f.get("finding_type") or "",
            str(meta.get("tool_name") or f.get("finding_type") or "").replace("_", " ").title(),
        )
        if verdict == "POSITIVE" or not _is_boilerplate_finding(formatted):
            _meaningful.append(formatted)
        elif verdict not in ("NOT_APPLICABLE", "ERROR") and tool_label:
            _clean_tools.append(tool_label)

    key_findings = list(_meaningful)
    if not key_findings and _clean_tools:
        _checks = ", ".join(dict.fromkeys(t for t in _clean_tools if t))  # dedup, keep order
        key_findings = [
            f"No manipulation indicators detected across {len(set(_clean_tools))} forensic check(s): {_checks}."
        ]

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

    # Build agent brief — lead with the evidence identity (observed context),
    # then the deterministic findings. The identity is vision-derived inference
    # and is framed as "presents as", never as a forensic conclusion.
    identity_lead = ""
    if input_data.evidence_identity:
        identity_lead = f"The evidence presents as {input_data.evidence_identity}. "

    if _meaningful:
        # Real signals present — lead with them.
        findings_joined = "; ".join(_meaningful[:3])
        agent_brief = f"{identity_lead}Examination identified: {findings_joined}."
    elif _clean_tools:
        # Clean — state the conclusion naturally, not "identified: no indicators".
        agent_brief = (
            f"{identity_lead}Examination across {len(set(_clean_tools))} forensic check(s) "
            f"found no supported manipulation indicators."
        )
    else:
        agent_brief = f"{identity_lead}Examination found no supported anomalies across the applicable checks."

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


def _build_persona_system_prompt(agent_ids: list[str]) -> str:
    """
    Build the Groq system prompt with per-agent expert voice instructions.
    The persona voice definitions are the single source of truth — they live
    in agent_personas.py and are injected here at call time so a change to
    a persona definition automatically propagates to the synthesis prompt.
    """
    voice_blocks: list[str] = []
    for aid in agent_ids:
        persona = get_agent_narrative_persona(aid)
        if persona:
            vocab = ", ".join(persona.vocabulary_signature[:8])
            forbidden = ", ".join(f'"{p}"' for p in persona.forbidden_phrases[:5])
            voice_blocks.append(
                f"**{aid} — {persona.expert_name}, {persona.title}**\n"
                f"Voice: {persona.voice_style}\n"
                f"Emphasis: {persona.emphasis}\n"
                f"Finding lead: {persona.finding_lead}\n"
                f"Domain vocabulary to use naturally: {vocab}.\n"
                f"Never use these phrases: {forbidden}."
            )

    persona_section = "\n\n".join(voice_blocks)

    return (
        "You are a forensic narrative specialist writing expert testimony for a multi-agent "
        "digital evidence analysis system. Each agent has a distinct expert identity. "
        "Write ONLY in their assigned voice — not in generic template language.\n\n"
        + persona_section
        + "\n\n"
        "INVIOLABLE CONSTRAINTS — these override everything else:\n"
        "1. NEVER change 'agent_verdict' or 'agent_confidence' — these are deterministic forensic "
        "measurements. They are facts, not opinions.\n"
        "2. NEVER mention any tool vendor, AI provider, or model name "
        "(Gemini, Groq, Cerebras, OpenAI, Llama, Google, CLIP, YOLO, etc.).\n"
        "3. NEVER treat a missing API key or unavailable model as a degradation. "
        "Only actual tool execution failures may appear as limitations.\n"
        "4. Every key finding MUST follow this format: "
        "[Finding statement] — [Tool name] ([Confidence]%)\n"
        "5. Write in the present tense. The analysis has been completed; report its findings.\n"
        "6. Return ONLY valid JSON — no markdown, no prose outside the JSON.\n"
        "7. OPEN each agent_brief by grounding the reader in what the evidence appears to be, "
        "using the supplied 'evidence_identity' value: begin with 'The evidence presents as "
        "<evidence_identity>.' This is OBSERVED CONTEXT (what the evidence looks like), NOT a "
        "forensic finding — never state it as a conclusion or let it imply a verdict. After this "
        "one grounding sentence, state the deterministic findings in the expert's voice. "
        "If evidence_identity is empty, open directly with the findings.\n\n"
        "Schema:\n"
        "{\n"
        "  \"Agent1\": {\n"
        "    \"agent_brief\": \"<opens with 'The evidence presents as ...' then 2-3 sentence expert summary in Agent1 voice>\",\n"
        "    \"visual_context_summary\": \"<1-2 sentences on what the image context revealed>\",\n"
        "    \"key_findings\": [\"<Finding> — <Tool> (<Conf>%)\", ...],\n"
        "    \"confidence_reason\": \"<1 sentence on why the confidence level is justified>\",\n"
        "    \"limitations\": [\"<only real tool failures>\"]\n"
        "  },\n"
        "  \"Agent3\": { ... },\n"
        "  \"Agent5\": { ... }\n"
        "}"
    )


def _has_narratable_signal(inp: AgentSynthesisInput) -> bool:
    """True if this agent has anything worth a Groq-polished narrative.

    Clean evidence (no positive/alert findings, no visual anomalies) produces
    a perfectly adequate deterministic synthesis — calling Groq for it only
    burns quota. We narrate only when there is a real signal to articulate.
    """
    _ALERT_VERDICTS = {"POSITIVE", "SUSPICIOUS", "TAMPERED", "MANIPULATED", "LIKELY_MANIPULATED"}
    for f in (inp.grounded_findings or inp.findings):
        verdict = str(f.get("evidence_verdict") or "").upper()
        if verdict in _ALERT_VERDICTS:
            return True
        meta = f.get("metadata") or {}
        severity = str(meta.get("severity_tier") or meta.get("severity") or "").upper()
        if severity in ("CRITICAL", "HIGH", "MEDIUM"):
            return True
    # Visual-context anomalies are narratable even when tools are clean
    section = inp.visual_context_section or {}
    if isinstance(section, dict):
        for key in ("visible_manipulation_signals", "ai_generation_signals", "scene_inconsistencies", "metadata_contradictions"):
            if section.get(key):
                return True
        if str(section.get("integrity_assessment") or "").lower() not in ("", "no_visible_issue", "cannot_determine"):
            return True
    # Tool failures are worth narrating as limitations
    return bool(inp.failed_tools)


async def refine_synthesis_batch(
    inputs: dict[str, AgentSynthesisInput],
    config: Settings,
) -> dict[str, AgentSynthesisOutput]:
    """Single batched synthesis refiner.

    Constructs one Groq prompt covering all three agents with per-agent expert
    persona voices, makes one LLM call, and falls back to deterministic output
    on any failure. The deterministic fallback is always pre-built first so the
    function never blocks.
    """
    outputs = {}

    # 1. Build deterministic syntheses first — these are the fallback AND the
    #    foundation: numeric values (verdict, confidence) come from here and the
    #    LLM is only allowed to touch the narrative fields.
    for aid, inp in inputs.items():
        outputs[aid] = generate_deterministic_agent_synthesis(inp)

    # 2. Guard: skip LLM refinement if not configured
    llm_client = LLMClient(config=config)
    if not (config.llm_enable_post_synthesis and config.llm_api_key and llm_client.is_available):
        logger.info("Groq batched synthesis skipped (LLM disabled/unavailable).")
        return outputs

    # 2b. Clean-evidence early-exit: if NO agent has a narratable signal, the
    #     deterministic synthesis is already optimal. Skip the Groq call to
    #     preserve free-tier quota — this is the common clean-screenshot case.
    if not any(_has_narratable_signal(inp) for inp in inputs.values()):
        logger.info("Groq synthesis skipped — all agents clean, deterministic output is sufficient.")
        return outputs

    # 3. Build the per-agent payload
    batch_prompt_data = {}
    for aid, inp in inputs.items():
        clean_findings = [
            {
                "tool": f.get("metadata", {}).get("tool_name") or f.get("finding_type"),
                "summary": f.get("reasoning_summary") or f.get("metadata", {}).get("summary"),
                "verdict": f.get("evidence_verdict"),
                "confidence": f.get("confidence_raw") or f.get("metadata", {}).get("confidence"),
            }
            for f in (inp.grounded_findings or inp.findings)
        ]
        batch_prompt_data[aid] = {
            "agent_id": inp.agent_id,
            "evidence_identity": inp.evidence_identity,
            "visual_context_available": inp.visual_context_available,
            "visual_context_section": inp.visual_context_section,
            "completed_tools": inp.completed_tools,
            "failed_tools": inp.failed_tools,
            "findings": clean_findings,
            "agent_verdict": inp.agent_verdict,
            "agent_confidence": inp.agent_confidence,
            "confidence_reason": inp.confidence_reason,
        }

    system_prompt = _build_persona_system_prompt(list(inputs.keys()))
    user_payload = json.dumps(batch_prompt_data, indent=2, default=str)

    try:
        # Hard ceiling on the Groq refinement so a rate-limited/slow run can never
        # block the arbiter deliberation — the deterministic outputs are already
        # built above and used as-is on timeout.
        raw_response = await asyncio.wait_for(
            llm_client.generate_synthesis(
                system_prompt=system_prompt,
                user_content=user_payload,
                json_mode=True,
                priority="medium",
                # Three short expert briefs — 1200 tokens is ample and keeps the
                # call well within free-tier TPM limits.
                max_tokens=1200,
            ),
            timeout=40.0,
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
