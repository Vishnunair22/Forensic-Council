from __future__ import annotations

import datetime
from typing import Any
from uuid import UUID

from core.agent_personas import get_agent_persona_profile
from core.react_loop import AgentFinding
from core.structured_logging import get_logger
from core.tool_output_normalizer import ToolOutputEnvelope
from core.visual_context_models import (
    ImageIntegrityContext,
    MetadataVisualContext,
    ObjectSceneContext,
    VisualContext,
)
from core.visual_context_store import get_visual_context

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
        # Per-agent caches. The persona is static and the visual-context digest
        # changes at most once (when the shared context resolves). Caching them
        # avoids a working-memory read + context fetch + write on EVERY tool call
        # — previously ~one extra round-trip per tool per agent for no new data.
        self._persona_cache: dict[str, Any] = {}
        self._primed_agents: set[str] = set()

    def _persona_for(self, agent_id: str) -> Any:
        if agent_id not in self._persona_cache:
            self._persona_cache[agent_id] = get_agent_persona_profile(agent_id)
        return self._persona_cache[agent_id]

    async def pre_tool_reasoning(
        self,
        session_id: str,
        agent_id: str,
        tool_name: str,
        tool_input: dict[str, Any],
        working_memory: Any
    ) -> dict[str, Any]:
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

        # Once persona + visual digest are written to working memory there is
        # nothing left to prime — skip the read/fetch/save on every later tool.
        if agent_id in self._primed_agents:
            return tool_input

        # Retrieve state from working memory
        try:
            state = await working_memory.get_state(UUID(session_id), agent_id)
        except Exception as e:
            logger.warning("Failed to retrieve state in pre_tool_reasoning", error=str(e))
            state = None

        persona = self._persona_for(agent_id)

        # Update working memory state with persona profile if present
        if state and persona:
            mutated = False
            if not getattr(state, "agent_persona_profile", None):
                state.agent_persona_profile = persona.model_dump()
                mutated = True

            # Read/cache the visual context digest if available.
            digest_written = bool(getattr(state, "shared_visual_context_digest", None))
            vis_ctx = await get_visual_context(
                session_id=session_id,
                working_memory=working_memory,
                inter_agent_bus=self.inter_agent_bus
            )
            if vis_ctx:
                digest = {
                    "source": vis_ctx.source,
                    "authenticity_verdict": vis_ctx.authenticity_verdict,
                    "confidence": vis_ctx.confidence,
                    "objects_count": len(vis_ctx.object_scene_context.objects),
                    "weapons_count": len(vis_ctx.object_scene_context.weapons_or_dangerous_items)
                }
                if getattr(state, "shared_visual_context_digest", None) != digest:
                    state.shared_visual_context_digest = digest
                    mutated = True
                digest_written = True

            if mutated:
                try:
                    await working_memory.save_state(UUID(session_id), agent_id, state)
                except Exception as e:
                    logger.warning("Failed to save working memory state in pre_tool_reasoning", error=str(e))

            # Prime only once both are in place. A context that never resolves
            # keeps retrying (cheaply) rather than caching an empty digest.
            if getattr(state, "agent_persona_profile", None) and digest_written:
                self._primed_agents.add(agent_id)

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
                label = str(r.get("label") or r.get("class_name") or r.get("name") or "").lower()
                if any(w in label for w in ["weapon", "gun", "knife", "pistol", "rifle", "firearm", "contraband", "bomb"]):
                    detected_weapons_or_contraband.append(label)

            if detected_weapons_or_contraband:
                # Check visual context for corresponding mentions
                vc_weapons = [w.lower() for w in vis_ctx.object_scene_context.weapons_or_dangerous_items]
                vc_objects = [obj.lower() for obj in vis_ctx.object_scene_context.objects]
                vc_desc = vis_ctx.object_scene_context.scene_description.lower()

                # Match an item against text/labels, tolerating singular/plural and
                # the irregular f→ves plural ("knife" ↔ "knives") so a benign mention
                # is not misread as absence.
                def _variants(w: str) -> set[str]:
                    v = {w, w + "s", w + "es"}
                    if w.endswith("fe"):
                        v.add(w[:-2] + "ves")   # knife → knives
                    elif w.endswith("f"):
                        v.add(w[:-1] + "ves")   # leaf → leaves
                    if w.endswith("ves"):
                        v.add(w[:-3] + "fe")
                    return v

                def _mentioned(item: str, haystack: str) -> bool:
                    return any(var in haystack for var in _variants(item))

                # A dual-use object (knife, etc.) is a reportable THREAT only if the
                # holistic visual model independently classifies it as dangerous. Mere
                # presence in the scene is NOT threat corroboration: if Gemini saw the
                # object and did not flag it (e.g. "artist's palette knives"), that
                # contradicts the threat rather than confirming it.
                flagged_dangerous = any(
                    (w_ctx in item or item in w_ctx)
                    for item in detected_weapons_or_contraband
                    for w_ctx in vc_weapons
                )
                seen_but_benign = (not flagged_dangerous) and any(
                    _mentioned(item, vc_desc) or any(_mentioned(item, obj_ctx) for obj_ctx in vc_objects)
                    for item in detected_weapons_or_contraband
                )

                if flagged_dangerous:
                    pass  # corroborated threat — keep the verdict as reported
                elif seen_but_benign:
                    # Gemini observed the object and judged it benign → not a threat.
                    is_uncorroborated_visual_claim = True
                    court_defensible = False
                    if verdict == "POSITIVE":
                        verdict = "NEGATIVE"
                    if confidence is not None:
                        confidence = min(confidence, 0.3)
                    msg = (
                        f"YOLO flagged a potential weapon/contraband "
                        f"({', '.join(detected_weapons_or_contraband)}), but the visual model "
                        f"identifies it as a benign object in context — not a threat."
                    )
                    limitations.append(msg)
                    logger.info(msg)
                else:
                    # Not present in the visual context at all — possible misdetection.
                    is_uncorroborated_visual_claim = True
                    court_defensible = False
                    if confidence is not None:
                        confidence *= 0.5  # scaling penalty
                    if verdict == "POSITIVE":
                        verdict = "INCONCLUSIVE"
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
            # Descriptive text from the tool's own output — carried so downstream
            # synthesis/report rendering uses the REAL tool result instead of being
            # forced into template fallback text (the prior root cause: digests
            # stored only verdict/scoring fields with no summary).
            _raw = envelope.raw if isinstance(getattr(envelope, "raw", None), dict) else {}
            _summary_text = str(getattr(envelope, "summary", "") or "").strip()
            _key_signal = str(
                _raw.get("key_signal")
                or _raw.get("key_finding")
                or _raw.get("anomaly_description")
                or _raw.get("match_description")
                or ""
            ).strip()

            # Update tool result summaries
            state.tool_result_summaries[tool_name] = {
                "status": status_val,
                "evidence_verdict": verdict,
                "confidence": confidence,
                "court_defensible": court_defensible,
                "report_safe": report_safe,
                "arbiter_weight": arbiter_weight,
                "summary": _summary_text,
                "key_signal": _key_signal,
                "timestamp": datetime.datetime.utcnow().isoformat()
            }

            # Update contradiction register
            if contradiction_notes:
                state.contradiction_register.extend(contradiction_notes)

            # Record grounded finding — now carries the descriptive text + metadata
            # so synthesis/report rendering has the real tool result, not a template.
            finding_digest = {
                "tool_name": tool_name,
                "evidence_verdict": verdict,
                "status": status_val,
                "confidence": confidence,
                "court_defensible": court_defensible,
                "report_safe": report_safe,
                "arbiter_weight": arbiter_weight,
                "uncorroborated": is_uncorroborated_visual_claim,
                "forbidden_breach": is_forbidden_claim_breach,
                "visual_inference_only": visual_inference_only,
                "reasoning_summary": _summary_text,
                "metadata": {
                    "tool_name": tool_name,
                    "summary": _summary_text,
                    "key_signal": _key_signal,
                    "degraded": bool(_raw.get("degraded")),
                    "fallback_reason": _raw.get("fallback_reason"),
                },
            }
            state.grounded_findings.append(finding_digest)

            # Save the updated state
            try:
                await working_memory.save_state(UUID(session_id), agent_id, state)
            except Exception as e:
                logger.warning("Failed to save working memory state in post_tool_reasoning", error=str(e))

        # 5. Build and return the AgentFinding
        # finding_status reflects COMPLETION, not court-defensibility. A heuristic
        # screening tool (court_defensible=False) that ran and produced a valid
        # verdict is COMPLETE — it must NOT be marked INCOMPLETE just because it is
        # not court-defensible. Only genuine non-completion (error / timeout /
        # unavailable) is INCOMPLETE. (report_safe stays a separate flag used for
        # arbiter weighting; it no longer forces an INCOMPLETE status.)
        finding_status = "CONFIRMED"
        if (
            verdict == "ERROR"
            or str(status_val).upper() in {"ERROR", "TIMEOUT", "INCOMPLETE", "FAILED"}
            or getattr(envelope, "available", True) is False
        ):
            finding_status = "INCOMPLETE"
        elif verdict == "NOT_APPLICABLE":
            finding_status = "NOT_APPLICABLE"
        elif verdict == "INCONCLUSIVE":
            finding_status = "INCONCLUSIVE"

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
