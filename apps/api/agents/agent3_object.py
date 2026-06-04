"""
Agent 3 - Object & Context Validation Agent.

MANDATE (strict): Object presence, identification, and contextual
plausibility ONLY. This agent is NOT a second image-forensics agent.
It does NOT perform pixel integrity, ELA, noise fingerprint, or
splicing detection — those belong to Agent 1. It does NOT perform
metadata analysis — that belongs to Agent 5.

Object detection, contraband search, and contextual scene validation
are the sole responsibilities.
"""

from __future__ import annotations

import asyncio
from functools import cached_property
from typing import Any

from agents.base_agent import ForensicAgent
from core.handlers.image import ImageHandlers
from core.handlers.scene import SceneHandlers
from core.media_kind import is_digitally_created_image, is_screen_capture_like
from core.react_loop import AgentFinding
from core.structured_logging import get_logger
from core.tool_registry import ToolRegistry

logger = get_logger(__name__)


class Agent3Object(ForensicAgent):

    persona: str = (
        "You are Detective Inspector Priya Nair, a 10-year computer vision forensic analyst for a national "
        "digital crimes unit. You specialize in scene-object inconsistencies, lighting and shadow anomalies, "
        "scale violations, and weapon/contraband detection. You write verdicts that link specific detected "
        "objects or scene anomalies to the forensic question at hand. You explicitly note when lighting or "
        "shadow geometry is inconsistent with the claimed context. You never conflate low-confidence detections "
        "with confirmed findings."
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._agent1_context: dict = {}
        self._agent1_context_event: asyncio.Event = asyncio.Event()

    @property
    def agent_name(self) -> str:
        return "Agent3_ObjectDetection"

    def inject_agent1_context(self, agent1_gemini_findings: dict) -> None:
        self._agent1_context = agent1_gemini_findings or {}
        self._agent1_context_event.set()

    @cached_property
    def _is_screen_capture(self) -> bool:
        return is_screen_capture_like(self.evidence_artifact)

    @cached_property
    def _is_digital_capture(self) -> bool:
        return is_digitally_created_image(self.evidence_artifact)

    @property
    def task_decomposition(self) -> list[str]:
        from core.image_evidence_routing import get_agent_plan
        plan = get_agent_plan(self.evidence_artifact, self.agent_id, phase="initial")
        if plan:
            return plan

        # Fallback logic
        if self._is_screen_capture:
            return [
                "Run screenshot_scene_applicability for screen-capture object/scene scope",
                "Run screenshot_layout_forensics for UI and document layout anomaly scan",
            ]

        if self._is_digital_capture:
            return [
                "Run object_detection for scene object identification",
                "Run scene_incongruence for contextual anomaly detection",
                "Run vector_contraband_search for risk object screening",
            ]

        file_type = (self.evidence_artifact.mime_type or "").lower()
        if file_type.startswith("video/"):
            return [
                "Run frame_extraction for video frame sampling and scene segmentation",
                "Run object_detection for scene object identification",
                "Run scene_incongruence for contextual anomaly detection",
                "Run lighting_correlation_initial for initial shadow and light direction audit",
                "Run vector_contraband_search for risk object screening",
            ]

        return [
            "Run object_detection for scene object identification",
            "Run scene_incongruence for contextual anomaly detection",
            "Run lighting_correlation_initial for initial shadow and light direction audit",
            "Run vector_contraband_search for risk object screening",
        ]

    @property
    def deep_task_decomposition(self) -> list[str]:
        from core.image_evidence_routing import get_agent_plan
        plan = get_agent_plan(self.evidence_artifact, self.agent_id, phase="deep")
        if plan:
            return plan

        # Fallback logic
        if self._is_screen_capture or self._is_digital_capture:
            return [
                "Read shared image context for UI/screenshot grounding from Agent 1 visual profile",
                "Run screenshot_layout_forensics for deep UI/document consistency cross-check",
            ]

        return [
            "Run scale_validation for object proportion and geometry consistency",
            "Run lighting_consistency for deep ROI-aware shadow-angle audit",
            "Read shared image context for object/scene grounding from Agent 1 visual profile",
        ]

    @property
    def iteration_ceiling(self) -> int:
        # deep_task_decomposition reads _tool_context which is empty at init time, so it
        # always resolves to the no-detections branch (3 tasks). Use the max possible deep
        # task count (5: secondary_classification + scale_validation + adversarial +
        # lighting_consistency + gemini_deep_forensic) so the ceiling is never underestimated
        # when Phase 1 detects objects and Phase 2 expands the task list at runtime.
        max_deep_tasks = 5
        base_count = len(self.task_decomposition) + max_deep_tasks
        return self._compute_ceiling(base_count)

    async def build_initial_thought(self) -> str:
        if self._is_screen_capture or self._is_digital_capture:
            return (
                f"Starting UI/screenshot object identification for {self.evidence_artifact.artifact_id}. "
                f"UI/screenshot images undergo screenshot-specific layout analysis; physical scene geometry tools are not applicable."
            )
        return (
            f"Starting object and weapon analysis for {self.evidence_artifact.artifact_id}. "
            f"I will perform scene-wide object detection, lighting consistency checks, "
            f"and search for any prohibited items or contextual anomalies."
        )

    async def on_tool_result(self, finding: AgentFinding) -> None:
        """Reactive task expansion based on object/scene signals."""
        try:
            await self._on_tool_result_impl(finding)
        except Exception as e:
            logger.warning("on_tool_result failed", agent_id=self.agent_id, error=str(e))

    def _visual_profile(self) -> dict:
        """Return the shared visual context dict from _tool_context or inter_agent_bus."""
        ctx = getattr(self, "_tool_context", {}) or {}
        profile = ctx.get("visual_evidence_profile") or ctx.get("read_shared_image_context") or {}
        if not profile and self.inter_agent_bus:
            try:
                profile = self.inter_agent_bus.get_visual_profile(str(self.session_id)) or {}
            except Exception as exc:
                logger.debug("Visual profile bus lookup failed", error=str(exc))
        if hasattr(profile, "to_finding_dict"):
            profile = profile.to_finding_dict()
        return profile if isinstance(profile, dict) else {}

    async def _on_tool_result_impl(self, finding: AgentFinding) -> None:
        """Implementation of reactive task expansion for object detection."""
        tool_name = finding.metadata.get("tool_name")
        is_screenshot = self._is_screen_capture_context()

        # 1. Visual context arrival — route tools based on what the image IS
        if tool_name == "read_shared_image_context":
            profile = self._visual_profile()
            file_type = str(profile.get("file_type_assessment") or "").lower()
            content_desc = str(profile.get("content_description") or "").lower()
            is_ss = any(t in file_type or t in content_desc for t in (
                "screenshot", "screen capture", "digital ui", "web page", "app interface",
            ))
            if is_ss:
                logger.info(
                    "Visual context confirms screenshot — routing to UI forensics",
                    agent_id=self.agent_id,
                )
                await self.inject_task(
                    description="Run screenshot_scene_applicability to assess screenshot analysis scope",
                    priority=16,
                )
                await self.inject_task(
                    description="Run screenshot_layout_forensics for UI element consistency check",
                    priority=15,
                )
            # Gemini flagged weapons or dangerous items → prioritise contraband scan
            weapons = list(profile.get("weapons_or_dangerous_items") or [])
            if weapons:
                logger.info(
                    f"Visual context flagged dangerous items: {weapons}; routing to contraband scan",
                    agent_id=self.agent_id,
                )
                await self.inject_task(
                    description="Run vector_contraband_search for dangerous item risk screening",
                    priority=20,
                )
            # Gemini flagged scene inconsistencies → run incongruence check immediately
            inconsistencies = list(profile.get("scene_inconsistencies") or [])
            if inconsistencies and not is_ss:
                logger.info(
                    f"Visual context flagged {len(inconsistencies)} scene inconsistencies — "
                    "injecting scene_incongruence for corroboration",
                    agent_id=self.agent_id,
                )
                await self.inject_task(
                    description="Run scene_incongruence to validate visual context anomaly signals",
                    priority=18,
                )

        # 2. Weapon/contraband confirmed → secondary classification + physics checks
        if tool_name == "vector_contraband_search":
            if finding.evidence_verdict == "POSITIVE" and (finding.confidence_raw or 0.0) > 0.6:
                logger.info(
                    "High-confidence contraband detected; escalating", agent_id=self.agent_id
                )
                await self.inject_task(
                    description="Run secondary_classification on flagged objects for validation",
                    priority=20,
                )
                await self.inject_task(
                    description="Run scale_validation for weapon size plausibility check",
                    priority=18,
                )
                if not is_screenshot:
                    await self.inject_task(
                        description="Run lighting_consistency for shadow validation on held objects",
                        priority=17,
                    )

        # 3. Lighting inconsistency initial → deep shadow audit (photos only)
        if tool_name == "lighting_correlation_initial":
            if finding.evidence_verdict == "POSITIVE" and not is_screenshot:
                logger.info(
                    "Lighting inconsistency detected; escalating to deep analysis",
                    agent_id=self.agent_id,
                )
                await self.inject_task(
                    description="Run lighting_consistency for deep ROI-aware shadow-angle audit",
                    priority=15,
                )

        # 4. Scene incongruence confirmed
        if tool_name == "scene_incongruence":
            if finding.evidence_verdict == "POSITIVE" or finding.metadata.get("incongruence_detected"):
                if is_screenshot:
                    # For screenshots, UI layout audit is more meaningful than adversarial check
                    logger.info(
                        "Scene incongruence in screenshot context — routing to UI layout forensics",
                        agent_id=self.agent_id,
                    )
                    await self.inject_task(
                        description="Run screenshot_layout_forensics for UI element consistency validation",
                        priority=14,
                    )
                else:
                    logger.info(
                        "Scene incongruence in photo context — injecting adversarial check",
                        agent_id=self.agent_id,
                    )
                    await self.inject_task(
                        description="Run adversarial_robustness_check against object detection evasion",
                        priority=12,
                    )

        # 5. Object detection — signal bus + check for Gemini/YOLO mismatch
        if tool_name == "object_detection":
            obj_count = finding.metadata.get("detection_count", 0)
            if self.inter_agent_bus:
                try:
                    self.inter_agent_bus.signal_event(
                        self.session_id,
                        "agent3_object_signal",
                        {"progress": f"Detected {obj_count} objects", "verdict": finding.evidence_verdict},
                    )
                except Exception as signal_error:
                    logger.debug("Failed to publish object agent signal", error=str(signal_error))

            # If YOLO finds many objects but visual context lists few → inject incongruence check
            profile = self._visual_profile()
            gemini_objects = list(profile.get("detected_objects") or [])
            if obj_count > 0 and len(gemini_objects) == 0 and not is_screenshot:
                logger.info(
                    f"YOLO detected {obj_count} objects but visual context lists none — "
                    "possible misclassification; injecting scene_incongruence",
                    agent_id=self.agent_id,
                )
                await self.inject_task(
                    description="Run scene_incongruence for YOLO vs visual context object mismatch",
                    priority=13,
                )

    async def build_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()

        # ── Domain Handlers (Decentralized) ──────────────────────────────────
        scene_h = SceneHandlers(self)
        registry.register_domain_handler(scene_h)

        # Adversarial robustness from image domain (relevant to object detection evasion)
        image_h = ImageHandlers(self)
        registry.register(
            "adversarial_robustness_check",
            image_h.adversarial_robustness_check_handler,
            "Adversarial robustness check",
        )
        # Content-understanding tools — these answer "what is in the image", which
        # is Agent 3's axis. Moved here from Agent 1 (image integrity) so each
        # agent runs only the tools for its concern. Agent 1 now reads the content
        # it needs from the shared visual context (canonical tool taxonomy).
        registry.register(
            "analyze_image_content",
            image_h.analyze_image_content_handler,
            "CLIP semantic classification",
        )
        registry.register(
            "extract_text_from_image",
            image_h.extract_text_from_image_handler,
            "Gemini Multimodal OCR",
        )

        # ── Shared Image Context Reader ───────────────────────────────────────
        # Agent 1's Phase 1 visual evidence profile is stored in the inter-agent bus.
        # Agent 3 reads it here instead of making its own API call.
        async def read_shared_image_context_handler(input_data: dict) -> dict:
            """Read Agent 1's shared visual evidence profile from bus context."""
            result = {"shared_context_available": False, "source": "agent1_visual_profile"}
            try:
                # Surface the rich VisualContext fields the reactive routing in
                # _on_tool_result_impl consumes (weapons_or_dangerous_items,
                # scene_inconsistencies, file_type_assessment). The flat bus profile
                # omits them, so without this they only resolved via the bus
                # fallback (which never fired once the profile was non-empty).
                vc = getattr(self, "visual_context", None)
                if vc is not None:
                    from core.visual_context_store import visual_context_to_profile_dict
                    prof = visual_context_to_profile_dict(vc)
                    result["shared_context_available"] = True
                    result["content_description"] = prof.get("content_description", "")
                    result["detected_objects"] = prof.get("detected_objects", [])
                    result["weapons_or_dangerous_items"] = prof.get("weapons_or_dangerous_items", [])
                    result["scene_inconsistencies"] = prof.get("scene_inconsistencies", [])
                    result["file_type_assessment"] = prof.get("file_type_assessment", "")
                    result["authenticity_verdict"] = prof.get("verdict", "")
                    result["reasoning_summary"] = prof.get("content_description", "")
                    result["metadata"] = prof.get("metadata", {})

                if self.inter_agent_bus:
                    ctx = self.inter_agent_bus.get_visual_profile(str(self.session_id))
                    if ctx:
                        result["shared_context_available"] = True
                        # Bus profile fills any gaps the VisualContext didn't cover.
                        result.setdefault("metadata", ctx.get("metadata", {}))
                        if not result.get("content_description"):
                            result["content_description"] = ctx.get("content_description", "")
                        if not result.get("detected_objects"):
                            result["detected_objects"] = ctx.get("detected_objects", [])
                        if not result.get("authenticity_verdict"):
                            result["authenticity_verdict"] = ctx.get("authenticity_verdict", "")
                        if not result.get("reasoning_summary"):
                            result["reasoning_summary"] = ctx.get("reasoning_summary", "")
                        self.inter_agent_bus.signal_event(
                            self.session_id,
                            "agent3_initial_signal",
                            {
                                "progress": "Shared image context loaded from Agent 1 visual profile",
                                "object_count": self._tool_context.get("object_detection", {}).get(
                                    "detection_count", 0
                                ),
                            },
                        )
            except Exception as e:
                logger.warning(f"{self.agent_id}: Failed to read shared image context", error=str(e))
            return result

        registry.register(
            "read_shared_image_context",
            read_shared_image_context_handler,
            "Read Agent 1 shared visual evidence profile from bus context",
        )

        # ── No-API Fallback Tools ──────────────────────────────────────────────
        async def lens_style_scan_handler(input_data: dict) -> dict:
            from tools.lens_style_tools import lens_style_multimodal_scan
            artifact = input_data.get("artifact") or self.evidence_artifact
            result = await lens_style_multimodal_scan(artifact=artifact)
            return result

        registry.register(
            "lens_style_multimodal_scan",
            lens_style_scan_handler,
            "On-device multi-modal scan with OCR, barcode, object, and logo analysis (no API key)",
        )

        async def reverse_image_search_handler(input_data: dict) -> dict:
            from tools.google_search_tools import reverse_image_search
            artifact = input_data.get("artifact") or self.evidence_artifact
            result = await reverse_image_search(artifact=artifact)
            return result

        registry.register(
            "reverse_image_search",
            reverse_image_search_handler,
            "Google reverse image search for online provenance (no API key required)",
        )

        return registry
