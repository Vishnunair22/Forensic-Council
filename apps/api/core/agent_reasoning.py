from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel

from core.structured_logging import get_logger
from core.agent_personas import get_agent_persona_profile, AgentPersonaProfile
from core.tool_output_normalizer import ToolOutputEnvelope
from core.visual_context_models import (
    VisualContext,
    ImageIntegrityContext,
    ObjectSceneContext,
    MetadataVisualContext
)
from core.visual_context_store import get_visual_context
from core.react_loop import AgentFinding

logger = get_logger(__name__)

TOOL_BASE_WEIGHTS = {
    # Agent 1
    "ela_full_image": 0.8,
    "ela_anomaly_classify": 0.75,
    "roi_extract": 0.8,
    "jpeg_ghost_detect": 0.8,
    "frequency_domain_analysis": 0.75,
    "splicing_detect": 0.85,
    "noise_fingerprint": 0.95,
    "noiseprint_cluster": 0.95,
    "neural_copy_move": 0.9,
    "neural_splicing": 0.9,
    "detect_font_inconsistency": 0.8,
    "detect_ui_overlay_forgery": 0.8,
    # Agent 3
    "object_detection": 0.85,
    "vector_contraband_search": 0.75,
    "scene_incongruence": 0.7,
    "lighting_consistency": 0.75,
    "scale_validation": 0.7,
    "screenshot_scene_applicability": 0.75,
    "screenshot_layout_forensics": 0.8,
    "secondary_classification": 0.8,
    # Agent 5
    "exif_extract": 1.0,
    "metadata_anomaly_score": 0.8,
    "gps_timezone_validate": 0.9,
    "file_structure_analysis": 0.95,
    "hex_signature_scan": 0.9,
    "timestamp_analysis": 0.9,
    "exif_isolation_forest": 0.8,
    "astro_grounding": 0.85,
}

def get_empty_visual_context(session_id: str) -> VisualContext:
    """Return a safe fallback empty VisualContext object."""
    return VisualContext(
        session_id=session_id,
        evidence_sha256="",
        source="local_ensemble",
        external_llm_used=False,
        image_integrity_context=ImageIntegrityContext(),
        object_scene_context=ObjectSceneContext(),
        metadata_visual_context=MetadataVisualContext(),
        created_at=datetime.datetime.utcnow().isoformat()
    )

class AgentReasoningService:
    """
    Forensic reasoning service that executes pre-tool checks and post-tool grounding.
    Enforces persona operating contracts, resolves visual context contradictions,
    and calculates court report safety parameters.
    """

    def __init__(self, inter_agent_bus: Any = None) -> None:
        self.inter_agent_bus = inter_agent_bus

    async def pre_tool_reasoning(
        self,
        session_id: str,
        agent_id: str,
        tool_name: str,
        tool_input: Dict[str, Any],
        working_memory: Any
    ) -> Dict[str, Any]:
        """
        Cognitive verification before a tool runs.
        Ensures persona context is loaded and tracks intention.
        """
        logger.info(
            "Executing pre-tool reasoning",
            session_id=session_id,
            agent_id=agent_id,
            tool=tool_name
        )

        # Retrieve state from working memory
        try:
            state = await working_memory.get_state(UUID(session_id), agent_id)
        except Exception as e:
            logger.warning("Failed to retrieve state in pre_tool_reasoning", error=str(e))
            state = None

        persona = get_agent_persona_profile(agent_id)
        
        # Update working memory state with persona profile if present
        if state and persona:
            state.agent_persona_profile = persona.model_dump()
            # Also read/cache visual context digest if available
            vis_ctx = await get_visual_context(
                session_id=session_id,
                working_memory=working_memory,
                inter_agent_bus=self.inter_agent_bus
            )
            if vis_ctx:
                state.shared_visual_context_digest = {
                    "source": vis_ctx.source,
                    "authenticity_verdict": vis_ctx.authenticity_verdict,
                    "confidence": vis_ctx.confidence,
                    "objects_count": len(vis_ctx.object_scene_context.objects),
                    "weapons_count": len(vis_ctx.object_scene_context.weapons_or_dangerous_items)
                }
            
            # Save the updated state
            try:
                key = working_memory._get_key(UUID(session_id), agent_id)
                await working_memory._client.set(key, state.model_dump_json(), ex=working_memory._ttl)
            except Exception as e:
                logger.warning("Failed to save working memory state in pre_tool_reasoning", error=str(e))

        return tool_input

    async def post_tool_reasoning(
        self,
        session_id: str,
        agent_id: str,
        tool_name: str,
        envelope: ToolOutputEnvelope,
        working_memory: Any
    ) -> AgentFinding:
        """
        Grounding verification after a tool runs.
        Cross-checks the findings against the shared visual context and persona allowed/forbidden claims.
        """
        logger.info(
            "Executing post-tool grounding",
            session_id=session_id,
            agent_id=agent_id,
            tool=tool_name,
            status=envelope.status
        )

        # Fetch working memory state
        try:
            state = await working_memory.get_state(UUID(session_id), agent_id)
        except Exception as e:
            logger.warning("Failed to retrieve working memory state in post_tool_reasoning", error=str(e))
            state = None

        # Fetch shared visual context (fall back to empty context if missing)
        vis_ctx = await get_visual_context(
            session_id=session_id,
            working_memory=working_memory,
            inter_agent_bus=self.inter_agent_bus
        )
        if not vis_ctx:
            logger.info("Visual context not found. Using empty fallback context.")
            vis_ctx = get_empty_visual_context(session_id)

        persona = get_agent_persona_profile(agent_id)

        # Base parameters
        verdict = envelope.evidence_verdict
        status_val = envelope.status
        confidence = envelope.confidence
        court_defensible = envelope.court_defensible
        limitations = list(envelope.limitations)
        measurements = dict(envelope.measurements)
        regions = list(envelope.regions)

        # Dynamic adjustments
        is_uncorroborated_visual_claim = False
        is_forbidden_claim_breach = False
        visual_inference_only = False
        contradiction_notes = []

        # 1. Grounding: Agent 3 (Object/Scene/Contraband)
        if agent_id.startswith("Agent3") and tool_name in ["object_detection", "vector_contraband_search"]:
            # If weapon or contraband detected, verify against visual context
            detected_weapons_or_contraband = []
            for r in regions:
                label = str(r.get("label", "")).lower()
                if any(w in label for w in ["weapon", "gun", "knife", "pistol", "rifle", "firearm", "contraband", "bomb"]):
                    detected_weapons_or_contraband.append(label)
            
            if detected_weapons_or_contraband:
                # Check visual context for corresponding mentions
                vc_weapons = [w.lower() for w in vis_ctx.object_scene_context.weapons_or_dangerous_items]
                vc_objects = [obj.lower() for obj in vis_ctx.object_scene_context.objects]
                vc_desc = vis_ctx.object_scene_context.scene_description.lower()
                
                corroborated = False
                for item in detected_weapons_or_contraband:
                    # Check if any token or synonym has a match
                    if any(w_ctx in item or item in w_ctx for w_ctx in vc_weapons):
                        corroborated = True
                        break
                    if any(obj_ctx in item or item in obj_ctx for obj_ctx in vc_objects):
                        corroborated = True
                        break
                    if item in vc_desc:
                        corroborated = True
                        break

                if not corroborated:
                    is_uncorroborated_visual_claim = True
                    court_defensible = False
                    if confidence is not None:
                        confidence *= 0.5  # scaling penalty
                    msg = (
                        f"Warning: YOLO/contraband tool detected potential weapon/contraband "
                        f"({', '.join(detected_weapons_or_contraband)}), but it is completely "
                        f"absent from the shared visual context description."
                    )
                    limitations.append(msg)
                    logger.warning(msg)

        # 2. Grounding: Agent 5 (Metadata) - Strict Protection Layer
        if agent_id.startswith("Agent5"):
            # Ensure physical metadata exists before allowing concrete device/GPS claims
            # Look at exif_extract tool output in working_memory if available, or envelope measurements
            exif_present = True
            # Check if exif_extract was executed and succeeded
            if state and hasattr(state, "tool_result_summaries"):
                exif_summary = state.tool_result_summaries.get("exif_extract", {})
                if exif_summary.get("status") == "NOT_APPLICABLE" or exif_summary.get("evidence_verdict") == "NOT_APPLICABLE":
                    exif_present = False
            
            # Or check the raw EXIF extraction fields
            if tool_name == "exif_extract":
                if envelope.evidence_verdict == "NOT_APPLICABLE" or not envelope.raw.get("present_fields"):
                    exif_present = False

            # If tool outputs location clues or software edit traces, we must separate physical vs inferred
            if not exif_present and tool_name in ["gps_timezone_validate", "timestamp_analysis", "exif_isolation_forest"]:
                visual_inference_only = True
                court_defensible = False
                msg = (
                    f"Warning: Physical EXIF metadata is missing. Inferences for {tool_name} "
                    f"are derived solely from visual context clues and cannot be treated as physical ground truth."
                )
                limitations.append(msg)
                logger.warning(msg)

        # 3. Persona Allowed/Forbidden Claims validation
        if persona:
            # Check forbidden claims keywords in summary or reasoning
            summary_lower = envelope.summary.lower()
            for forbidden in persona.forbidden_claims:
                keywords = forbidden.lower().split()
                # If all words of a forbidden claim phrase match in the summary, trigger breach
                if all(kw in summary_lower for kw in keywords):
                    is_forbidden_claim_breach = True
                    court_defensible = False
                    msg = f"Forbidden claim breach: Agent persona forbids making claims regarding '{forbidden}'."
                    limitations.append(msg)
                    logger.warning(msg)

        # 4. Contradiction Checking
        # If tool flags positive manipulation but visual context is clean, register contradiction
        if verdict == "POSITIVE" and vis_ctx.image_integrity_context.integrity_assessment == "no_visible_issue":
            note = f"Contradiction: Tool '{tool_name}' flags anomaly/manipulation, but shared visual context assessment is 'no_visible_issue'."
            contradiction_notes.append({
                "tool_name": tool_name,
                "message": note,
                "timestamp": datetime.datetime.utcnow().isoformat()
            })
            if confidence is not None:
                confidence = max(0.1, confidence - 0.2)  # decrease confidence slightly due to contradiction

        # Calculate Report-Safe & Arbiter-Weight flags
        report_safe = True
        if verdict == "ERROR" or status_val == "TIMEOUT":
            report_safe = False
        if not court_defensible:
            report_safe = False
        if is_forbidden_claim_breach:
            report_safe = False

        # Calculate weight
        base_weight = TOOL_BASE_WEIGHTS.get(tool_name, 0.8)
        if verdict == "ERROR" or status_val == "TIMEOUT":
            arbiter_weight = 0.0
        else:
            arbiter_weight = base_weight
            if is_uncorroborated_visual_claim:
                arbiter_weight *= 0.5
            if visual_inference_only:
                arbiter_weight *= 0.3
            if contradiction_notes:
                arbiter_weight *= 0.7

        # Save updates to working memory
        if state:
            # Update tool result summaries
            state.tool_result_summaries[tool_name] = {
                "status": status_val,
                "evidence_verdict": verdict,
                "confidence": confidence,
                "court_defensible": court_defensible,
                "report_safe": report_safe,
                "arbiter_weight": arbiter_weight,
                "timestamp": datetime.datetime.utcnow().isoformat()
            }

            # Update contradiction register
            if contradiction_notes:
                state.contradiction_register.extend(contradiction_notes)

            # Record grounded finding
            finding_digest = {
                "tool_name": tool_name,
                "evidence_verdict": verdict,
                "confidence": confidence,
                "court_defensible": court_defensible,
                "report_safe": report_safe,
                "arbiter_weight": arbiter_weight,
                "uncorroborated": is_uncorroborated_visual_claim,
                "forbidden_breach": is_forbidden_claim_breach,
                "visual_inference_only": visual_inference_only
            }
            state.grounded_findings.append(finding_digest)

            # Save the updated state
            try:
                key = working_memory._get_key(UUID(session_id), agent_id)
                await working_memory._client.set(key, state.model_dump_json(), ex=working_memory._ttl)
            except Exception as e:
                logger.warning("Failed to save working memory state in post_tool_reasoning", error=str(e))

        # 5. Build and return the AgentFinding
        # Check finding status
        finding_status = "CONFIRMED"
        if not report_safe:
            finding_status = "INCOMPLETE"
        if verdict == "NOT_APPLICABLE":
            finding_status = "NOT_APPLICABLE"
        elif verdict == "INCONCLUSIVE":
            finding_status = "INCONCLUSIVE"
        elif verdict == "ERROR":
            finding_status = "INCOMPLETE"

        # Build readable summary integrating pre-tool thought and post-tool grounding details
        grounding_notes = []
        if is_uncorroborated_visual_claim:
            grounding_notes.append("[UNCORROBORATED VISUAL CLAIM]")
        if visual_inference_only:
            grounding_notes.append("[VISUAL INFERENCE ONLY - NOT PHYSICAL METADATA]")
        if is_forbidden_claim_breach:
            grounding_notes.append("[PERSONA CONTRACT BREACH]")
        
        prefix = " ".join(grounding_notes) + " " if grounding_notes else ""
        readable_summary = f"{prefix}{envelope.summary}"

        finding = AgentFinding(
            agent_id=agent_id,
            agent_name=agent_id.replace("_deep", ""),
            finding_type=tool_name.replace("_", " ").title(),
            confidence_raw=confidence,
            raw_confidence_score=confidence,
            calibrated=False,
            calibration_status="UNCALIBRATED",
            evidence_verdict=verdict,
            status=finding_status,  # type: ignore[arg-type]
            reasoning_summary=readable_summary,
            metadata={
                **envelope.raw,
                "tool_name": tool_name,
                "court_defensible": court_defensible,
                "report_safe": report_safe,
                "arbiter_weight": arbiter_weight,
                "uncorroborated_visual_claim": is_uncorroborated_visual_claim,
                "visual_inference_only": visual_inference_only,
                "forbidden_claim_breach": is_forbidden_claim_breach,
                "measurements": measurements,
                "regions": regions,
                "limitations": limitations
            }
        )

        return finding
