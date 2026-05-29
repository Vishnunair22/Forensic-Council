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
        # PHASE 1: INITIAL ANALYSIS

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

        shared = {}
        if self.inter_agent_bus:
            shared = self.inter_agent_bus.get_image_context(
                str(self.session_id)
            ) or {}

        routing = shared.get("metadata", {}).get("forensic_routing", {}) or {}
        image_category = str(routing.get("image_category") or "").lower()
        skip_contraband = image_category == "live_photograph"

        tasks = [
            "Run object_detection for scene object identification",
            "Run scene_incongruence for contextual anomaly detection",
            "Run lighting_correlation_initial for initial shadow and light direction audit",
        ]

        if not skip_contraband:
            tasks.append(
                "Run vector_contraband_search for risk object screening"
            )

        return tasks

    @property
    def deep_task_decomposition(self) -> list[str]:
        if self._is_screen_capture or self._is_digital_capture:
            return [
                "Read shared image context for UI/screenshot grounding from Agent 1 visual profile",
                "Run screenshot_layout_forensics for deep UI/document consistency cross-check",
            ]
        object_ctx = self._tool_context.get("object_detection", {})
        detections = object_ctx.get("detections", []) if isinstance(object_ctx, dict) else []
        tasks = []
        # secondary_classification and adversarial_robustness_check removed from base —
        # both are already reactively injected by _on_tool_result_impl
        # (secondary from vector_contraband_search, adversarial from scene_incongruence).
        if detections:
            tasks.append("Run scale_validation on confirmed objects for geometric proportion validation")
        else:
            tasks.append("Run scale_validation for object proportion and geometry consistency")
        tasks.extend(
            [
                "Run lighting_consistency for deep ROI-aware shadow-angle audit",
                "Read shared image context for object/scene grounding from Agent 1 visual profile",
            ]
        )
        return tasks

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

    async def _on_tool_result_impl(self, finding: AgentFinding) -> None:
        """Implementation of reactive task expansion for object detection."""
        tool_name = finding.metadata.get("tool_name")

        # 1. If weapon/contraband detected, escalate to secondary classification
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
                await self.inject_task(
                    description="Run lighting_consistency for shadow validation on held objects",
                    priority=17,
                )

        # 2. If lighting inconsistency in initial check, escalate to deep analysis
        if tool_name == "lighting_correlation_initial":
            if finding.evidence_verdict == "POSITIVE":
                logger.info(
                    "Lighting inconsistency detected; escalating to deep analysis",
                    agent_id=self.agent_id,
                )
                await self.inject_task(
                    description="Run lighting_consistency for deep ROI-aware shadow-angle audit",
                    priority=15,
                )

        # 3. If scene incongruence found, inject adversarial robustness check
        if tool_name == "scene_incongruence":
            if finding.evidence_verdict == "POSITIVE" or finding.metadata.get(
                "incongruence_detected"
            ):
                logger.info(
                    "Scene incongruence detected; injecting adversarial check",
                    agent_id=self.agent_id,
                )
                await self.inject_task(
                    description="Run adversarial_robustness_check against object detection evasion",
                    priority=12,
                )

        # 4. Signal to inter-agent bus
        if tool_name == "object_detection":
            if self.inter_agent_bus:
                try:
                    obj_count = finding.metadata.get("detection_count", 0)
                    self.inter_agent_bus.signal_event(
                        self.session_id,
                        "agent3_object_signal",
                        {
                            "progress": f"Detected {obj_count} objects",
                            "verdict": finding.evidence_verdict,
                        },
                    )
                except Exception as signal_error:
                    logger.debug(
                        "Failed to publish object agent signal",
                        session_id=self.session_id,
                        error=str(signal_error),
                    )

    @property
    def supported_file_types(self) -> list[str]:
        return ["image/", "video/"]

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

        # ── Shared Image Context Reader ───────────────────────────────────────
        # Agent 1's Phase 1 visual evidence profile is stored in the inter-agent bus.
        # Agent 3 reads it here instead of making its own API call.
        async def read_shared_image_context_handler(input_data: dict) -> dict:
            """Read Agent 1's shared visual evidence profile from bus context."""
            result = {"shared_context_available": False, "source": "agent1_visual_profile"}
            try:
                if self.inter_agent_bus:
                    ctx = self.inter_agent_bus.get_image_context(str(self.session_id))
                    if ctx:
                        result["shared_context_available"] = True
                        result["metadata"] = ctx.get("metadata", {})
                        result["content_description"] = ctx.get("content_description", "")
                        result["detected_objects"] = ctx.get("detected_objects", [])
                        result["authenticity_verdict"] = ctx.get("authenticity_verdict", "")
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
