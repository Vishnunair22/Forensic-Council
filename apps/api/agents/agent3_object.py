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
from typing import Any

from agents.base_agent import ForensicAgent
from core.config import Settings
from core.custody_logger import CustodyLogger
from core.episodic_memory import EpisodicMemory
from core.evidence import EvidenceArtifact
from core.gemini_client import GeminiVisionClient
from core.handlers.image import ImageHandlers
from core.handlers.scene import SceneHandlers
from core.persistence.evidence_store import EvidenceStore
from core.structured_logging import get_logger
from core.tool_registry import ToolRegistry
from core.working_memory import WorkingMemory

logger = get_logger(__name__)

class Agent3Object(ForensicAgent):
    """
    Agent 3 - Object & Context Validation Agent.

    Mandate (STRICT): Object presence, identification, and contextual
    plausibility ONLY. Not a second image-forensics agent.
    """

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
        )
        self._agent1_context: dict = {}
        self._agent1_context_event: Any | None = None

    def inject_agent1_context(self, agent1_gemini_findings: dict) -> None:
        self._agent1_context = agent1_gemini_findings or {}

    @property
    def agent_name(self) -> str:
        return "Agent3_ObjectWeapon"

    @property
    def task_decomposition(self) -> list[str]:
        # PHASE 1: INITIAL ANALYSIS (Neural Refined)
        return [
            "Run object_detection on full scene",
            "Run vector_contraband_search for high-dimensional weapon/threat detection",
            "Run lighting_correlation_initial to flag compositing candidates",
            "Run scene_incongruence for contextual anomalies",
        ]

    @property
    def deep_task_decomposition(self) -> list[str]:
        object_ctx = self._tool_context.get("object_detection", {})
        detections = object_ctx.get("detections", []) if isinstance(object_ctx, dict) else []
        tasks = []
        if detections:
            tasks.extend([
                "Run secondary_classification on low-confidence objects",
                "Run scale_validation on confirmed objects",
                "Run adversarial_robustness_check against object detection evasion",
            ])
        tasks.extend([
            "Run lighting_consistency for deep ROI-aware shadow-angle audit",
            "Run gemini_deep_forensic to identify content, detect weapons, describe context",
        ])
        return tasks

    @property
    def iteration_ceiling(self) -> int:
        # Phase 1 ceiling only — deep pass has its own budget via run_deep_investigation.
        return self._compute_ceiling(len(self.task_decomposition))

    async def build_initial_thought(self) -> str:
        return (
            f"Starting object and weapon analysis for {self.evidence_artifact.artifact_id}. "
            f"I will perform scene-wide object detection, lighting consistency checks, "
            f"and search for any prohibited items or contextual anomalies."
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
        registry.register("adversarial_robustness_check", image_h.adversarial_robustness_check_handler, "Adversarial robustness check")

        # Gemini deep forensic analysis handler
        _gemini = GeminiVisionClient(self.config)

        async def _gemini_signal_callback(msg: str):
            """Signal callback for early hand-off to Arbiter."""
            try:
                if self.inter_agent_bus:
                    self.inter_agent_bus.signal_event(
                        self.session_id,
                        "agent3_initial_signal",
                        {"progress": msg, "object_count": self._tool_context.get("object_detection", {}).get("detection_count", 0)}
                    )
            except Exception as e:
                logger.debug(f"{self.agent_id}: Gemini signal callback failed", error=str(e))

        async def gemini_deep_forensic_handler(input_data: dict) -> dict:
            try:
                artifact = input_data.get("artifact") or self.evidence_artifact

                # Wait for Agent1 context if event exists
                _ctx_event = getattr(self, "_agent1_context_event", None)
                if _ctx_event is not None and not _ctx_event.is_set():
                    try:
                        await asyncio.wait_for(asyncio.shield(_ctx_event.wait()), timeout=60.0)
                    except TimeoutError:
                        logger.warning(f"{self.agent_id}: Agent1 context wait timed out after 60s — proceeding without image-integrity context")
                        await self._record_tool_error(
                            "agent1_context_sync",
                            "Agent1 Gemini context unavailable (60s timeout) — object/scene analysis may lack image-integrity grounding",
                        )

                # Audit Fix: DYNAMIC CONTEXT AGGREGATION
                # Collect all successful tool results from the current session
                # to ensure the AI has total forensic visibility (Lighting, Contraband, Scale etc)
                dynamic_context = {}
                for tool_name, result in self._tool_context.items():
                    if not isinstance(result, dict):
                        continue
                    if result.get("error") and not result.get("detections"):
                        # Skip pure error results; keep results that have data alongside an error
                        continue

                    # Extract high-value forensic keys for Gemini
                    dynamic_context[tool_name] = {
                        k: v for k, v in result.items()
                        if k not in ("detections", "artifact", "error", "box")
                    }
                    if tool_name == "object_detection":
                        # Include summarized detections with bounding boxes so Gemini
                        # can reason about spatial layout and compositing plausibility.
                        dynamic_context[tool_name]["detections_summary"] = [
                            {
                                "class": d["class_name"],
                                "confidence": d.get("confidence"),
                                "box": d.get("box", {}),
                            }
                            for d in result.get("detections", [])[:20]
                            if "class_name" in d
                        ]

                agent1_context = self._agent1_context
                context_summary = {"tools": dynamic_context, "agent1": agent1_context}

                try:
                    await self.update_sub_task("Synthesizing neural object-scene verdict...")
                    finding = await _gemini.deep_forensic_analysis(
                        file_path=artifact.file_path,
                        exif_summary=context_summary,
                        signal_callback=_gemini_signal_callback
                    )

                    result = finding.to_finding_dict(self.agent_id)
                    await self._record_tool_result("gemini_deep_forensic", result)
                    return result
                except Exception as e:
                    logger.error(f"{self.agent_id}: Gemini deep analysis failed", error=str(e))
                    err_result = {
                        "error": str(e),
                        "status": "FAILED",
                        "finding_type": "Gemini analysis error",
                        "reasoning_summary": "Deep forensic analysis via Gemini LLM failed or timed out."
                    }
                    await self._record_tool_error("gemini_deep_forensic", str(e))
                    return err_result
            except Exception as e:
                logger.error(f"{self.agent_id}: gemini_deep_forensic_handler failed", error=str(e))
                return {
                    "error": str(e),
                    "status": "FAILED",
                    "finding_type": "Handler error",
                    "reasoning_summary": "Deep forensic handler encountered an unexpected error."
                }

        registry.register(
            "gemini_deep_forensic",
            gemini_deep_forensic_handler,
            "Gemini deep forensic analysis for objects and scene context",
        )

        return registry
