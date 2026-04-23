"""
Agent 4 - Temporal Video Analysis Agent.

MANDATE (strict): Temporal consistency and video integrity ONLY.
Detects frame-level edit points, optical flow anomalies, face-swap
artifacts, and rolling shutter violations. Produces timestamped,
frame-indexed hypotheses as its core artifact.

Does NOT perform pixel-level image forensics (Agent 1), audio
analysis (Agent 2), object detection (Agent 3), or metadata
analysis (Agent 5).

Non-real capabilities (rPPG, reverse image search) are quarantined
and MUST NOT appear in the active reasoning surface until enabled
and validated.
"""

from __future__ import annotations

from agents.base_agent import ForensicAgent
from core.gemini_client import GeminiVisionClient
from core.handlers.video import VideoHandlers
from core.inter_agent_bus import InterAgentCall, InterAgentCallType
from core.structured_logging import get_logger
from core.tool_registry import ToolRegistry

logger = get_logger(__name__)

class Agent4Video(ForensicAgent):
    """
    Agent 4 - Temporal Video Analysis Agent.

    Mandate (STRICT): Temporal consistency and video integrity ONLY.
    Produces timestamped, frame-indexed hypotheses as core artifacts.
    """

    @property
    def agent_name(self) -> str:
        return "Agent4_TemporalVideo"

    @property
    def task_decomposition(self) -> list[str]:
        # PHASE 1: INITIAL ANALYSIS (Neural Refined)
        return [
            "Run video_metadata for advanced stream probe",
            "Run vfi_error_map to flag motion interpolation artifacts",
            "Run thumbnail_coherence to verify metadata preview parity",
            "Run frame_consistency_analysis on sampled frames",
        ]

    @property
    def deep_task_decomposition(self) -> list[str]:
        return [
            "Run optical_flow_analysis and generate temporal anomaly heatmap",
            "Run interframe_forgery_detector for motion ghosting and SSIM variance",
            "Run frame_extraction on flagged anomaly windows",
            "Run face_swap_detection on frames containing human faces",
            "Run deepfake_frequency_check on extracted frames",
            "Run rolling_shutter_validation against claimed device metadata",
            "Run compression_artifact_analysis for P-frame/I-frame incongruence",
            "Run adversarial_robustness_check on optical flow results",
            "Perform gemini_deep_forensic on key extracted frames",
        ]

    @property
    def iteration_ceiling(self) -> int:
        # Phase 1 ceiling only — deep pass has its own budget via run_deep_investigation.
        return self._compute_ceiling(len(self.task_decomposition))

    async def build_initial_thought(self) -> str:
        return (
            f"Starting temporal video analysis for {self.evidence_artifact.artifact_id}. "
            f"I will analyze optical flow continuity, interframe consistency, face-swap artifacts, "
            f"and rolling shutter signatures to detect frame-level edits or deepfake compositing."
        )

    @property
    def supported_file_types(self) -> list[str]:
        return ["video/"]

    async def build_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()

        # ── Domain Handlers (Decentralized) ──────────────────────────────────
        video_h = VideoHandlers(self)
        registry.register_domain_handler(video_h)

        # Agent-specific inter-agent call
        async def inter_agent_call_handler(input_data: dict) -> dict:
            if self.inter_agent_bus is None:
                return {"status": "error", "message": "No inter_agent_bus injected"}

            call = InterAgentCall(
                caller_agent_id=self.agent_id,
                callee_agent_id=input_data.get("target_agent", "Agent2"),
                call_type=InterAgentCallType.COLLABORATIVE,
                payload={
                    "timestamp_ref": input_data.get("timestamp_ref"),
                    "question": input_data.get("question", "Confirm audio-visual sync"),
                },
            )
            return await self.inter_agent_bus.send(call, self.custody_logger)

        registry.register("inter_agent_call", inter_agent_call_handler, "Inter-agent communication")

        # rPPG liveness is QUARANTINED — not a real capability yet.
        # Do NOT register it in the active tool registry until the model
        # is loaded, tested, and validated. See agent4_video.py docstring.
        # When ready, register with available=False and a clear quarantine flag.

        _gemini = GeminiVisionClient(self.config)

        async def _gemini_signal_callback(msg: str):
            """Signal callback for early hand-off to Arbiter."""
            try:
                if self.inter_agent_bus:
                    self.inter_agent_bus.signal_event(
                        self.session_id,
                        "agent4_initial_signal",
                        {"progress": msg, "anomalies_detected": self._tool_context.get("optical_flow_analysis", {}).get("anomaly_count", 0)}
                    )
            except Exception as e:
                logger.debug(f"{self.agent_id}: Gemini signal callback failed", error=str(e))

        async def gemini_deep_forensic_handler(input_data: dict) -> dict:
            artifact = input_data.get("artifact") or self.evidence_artifact
            # Audit Fix: DYNAMIC CONTEXT AGGREGATION
            from core.context_utils import aggregate_tool_context
            dynamic_context = aggregate_tool_context(self._tool_context, agent_id=self.agent_id)

            # Context from Agent 1 (Image Integrity) for cross-modal check
            agent1_context = {}
            if self.working_memory:
                try:
                    a1 = await self.working_memory.get_agent_context(self.session_id, "Agent1")
                    agent1_context = a1.get("initial_summary", {})
                except Exception as e:
                    logger.warning(f"{self.agent_id}: Failed to retrieve Agent1 context from working memory", error=str(e))

            context_summary = {"tools": dynamic_context, "agent1": agent1_context}

            try:
                await self.update_sub_task("Synthesizing temporal consistency verdict...")
                finding = await _gemini.deep_forensic_analysis(
                    file_path=artifact.file_path,
                    exif_summary=context_summary,
                    signal_callback=_gemini_signal_callback
                )
                result = finding.to_finding_dict(self.agent_id)
                result["analysis_source"] = "gemini_vision"
                await self._record_tool_result("gemini_deep_forensic", result)
                return result
            except Exception as e:
                await self._record_tool_error("gemini_deep_forensic", str(e))
                return {
                    "error": str(e),
                    "analysis_source": "gemini_vision",
                    "available": False,
                    "court_defensible": False,
                    "confidence": 0.0,
                }

        registry.register("gemini_deep_forensic", gemini_deep_forensic_handler, "Gemini deep forensic analysis for video frames")

        return registry
