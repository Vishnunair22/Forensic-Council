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
import uuid
from functools import cached_property
from typing import Any

from agents.base_agent import ForensicAgent
from core.config import Settings
from core.custody_logger import CustodyLogger
from core.episodic_memory import EpisodicMemory
from core.evidence import EvidenceArtifact
from core.handlers.image import ImageHandlers
from core.handlers.scene import SceneHandlers
from core.media_kind import is_screen_capture_like
from core.persistence.evidence_store import EvidenceStore
from core.react_loop import AgentFinding
from core.structured_logging import get_logger
from core.tool_registry import ToolRegistry
from core.working_memory import WorkingMemory

logger = get_logger(__name__)


class Agent3Object(ForensicAgent):
    @property
    def agent_name(self) -> str:
        return "Agent3_ObjectDetection"


    def __init__(
        self,
        agent_id: str,
        session_id: uuid.UUID,
        evidence_artifact: EvidenceArtifact,
        config: Settings,
        working_memory: WorkingMemory,
        episodic_memory: EpisodicMemory,
        custody_logger: CustodyLogger,
        evidence_store: EvidenceStore,
        inter_agent_bus: Any | None = None,
        heavy_tool_semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        super().__init__(
            agent_id=agent_id,
            session_id=session_id,
            evidence_artifact=evidence_artifact,
            config=config,
            working_memory=working_memory,
            episodic_memory=episodic_memory,
            custody_logger=custody_logger,
            evidence_store=evidence_store,
            inter_agent_bus=inter_agent_bus,
            heavy_tool_semaphore=heavy_tool_semaphore,
        )
        self._agent1_context: dict = {}
        self._agent1_context_event: asyncio.Event = asyncio.Event()

    def inject_agent1_context(self, agent1_gemini_findings: dict) -> None:
        self._agent1_context = agent1_gemini_findings or {}
        self._agent1_context_event.set()

    @cached_property
    def _is_screen_capture(self) -> bool:
        return is_screen_capture_like(self.evidence_artifact)

    @property
    def task_decomposition(self) -> list[str]:
        # PHASE 1: INITIAL ANALYSIS (Neural Refined)
        if self._is_screen_capture:
            return [
                "Run gemini_deep_forensic to identify UI elements, interface objects, and potential document fabrication",
            ]
        return [
            "Run object_detection for scene object identification",
            "Run scene_incongruence for contextual anomaly detection",
            "Run lighting_consistency for shadow and light direction analysis",
            "Run scale_validation for object proportion consistency",
            "Run contraband_database for risk object screening",
        ]

    @property
    def deep_task_decomposition(self) -> list[str]:
        if self._is_screen_capture:
            return [
                "Run scene_incongruence for document and text contextual anomalies",
                "Run gemini_deep_forensic to describe content and identify any concerns",
            ]
        object_ctx = self._tool_context.get("object_detection", {})
        detections = object_ctx.get("detections", []) if isinstance(object_ctx, dict) else []
        tasks = []
        if detections:
            tasks.extend(
                [
                    "Run secondary_classification on low-confidence objects",
                    "Run scale_validation on confirmed objects",
                    "Run adversarial_robustness_check against object detection evasion",
                ]
            )
        tasks.extend(
            [
                "Run lighting_consistency for deep ROI-aware shadow-angle audit",
                "Run gemini_deep_forensic to identify content, detect weapons, describe context",
            ]
        )
        return tasks

    @property
    def iteration_ceiling(self) -> int:
        # Include both initial and deep tasks to prevent truncation of the forensic pipeline.
        base_count = len(self.task_decomposition) + len(self.deep_task_decomposition)
        return self._compute_ceiling(base_count)

    async def build_initial_thought(self) -> str:
        if self._is_screen_capture:
            return (
                f"Starting UI/screenshot object identification for {self.evidence_artifact.artifact_id}. "
                f"UI/screenshot images undergo streamlined object detection; scene incongruence and lighting tools are not applicable."
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

        # ── Gemini Vision Handler (Unified) ───────────────────────────────────
        async def gemini_deep_forensic_handler(input_data: dict) -> dict:
            async def _gemini_signal_callback(msg: str):
                """Signal callback for early hand-off to Arbiter."""
                try:
                    if self.inter_agent_bus:
                        self.inter_agent_bus.signal_event(
                            self.session_id,
                            "agent3_initial_signal",
                            {
                                "progress": msg,
                                "object_count": self._tool_context.get("object_detection", {}).get(
                                    "detection_count", 0
                                ),
                            },
                        )
                except Exception as e:
                    logger.debug(f"{self.agent_id}: Gemini signal callback failed", error=str(e))

            return await self._gemini_deep_forensic_handler(
                input_data, signal_callback=_gemini_signal_callback
            )

        registry.register(
            "gemini_deep_forensic",
            gemini_deep_forensic_handler,
            "Gemini deep forensic analysis for objects and scene context",
        )

        return registry
