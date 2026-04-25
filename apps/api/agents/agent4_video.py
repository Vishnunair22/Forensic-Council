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
from core.handlers.video import VideoHandlers
from core.inter_agent_bus import InterAgentCall, InterAgentCallType
from core.react_loop import AgentFinding
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
        # Include both initial and deep tasks to prevent truncation of the forensic pipeline.
        base_count = len(self.task_decomposition) + len(self.deep_task_decomposition)
        return self._compute_ceiling(base_count)

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

        # ── Gemini Vision Handler (Unified) ───────────────────────────────────
        async def gemini_deep_forensic_handler(input_data: dict) -> dict:
            async def _gemini_signal_callback(msg: str):
                """Signal callback for early hand-off to Arbiter."""
                try:
                    if self.inter_agent_bus:
                        self.inter_agent_bus.signal_event(
                            self.session_id,
                            "agent4_initial_signal",
                            {
                                "progress": msg,
                                "anomalies_detected": self._tool_context.get(
                                    "optical_flow_analysis", {}
                                ).get("anomaly_count", 0),
                            },
                        )
                except Exception as e:
                    logger.debug(f"{self.agent_id}: Gemini signal callback failed", error=str(e))

            return await self._gemini_deep_forensic_handler(
                input_data, model_hint="gemini-2.5-flash", signal_callback=_gemini_signal_callback
            )

        registry.register(
            "gemini_deep_forensic",
            gemini_deep_forensic_handler,
            "Gemini deep forensic analysis for video frames",
        )

        return registry

    async def on_tool_result(self, finding: AgentFinding) -> None:
        """Reactive task expansion based on temporal signals."""
        try:
            await self._on_tool_result_impl(finding)
        except Exception as e:
            logger.warning("on_tool_result failed", agent_id=self.agent_id, error=str(e))

    async def _on_tool_result_impl(self, finding: AgentFinding) -> None:
        """Implementation of reactive task expansion."""
        tool_name = finding.metadata.get("tool_name")

        # 1. If frame consistency shows discontinuities, escalate to face swap check
        if tool_name == "frame_consistency_analysis":
            if finding.evidence_verdict == "POSITIVE" or finding.metadata.get(
                "discontinuity_detected"
            ):
                logger.info(
                    "Temporal discontinuity detected; injecting face-swap audit",
                    agent_id=self.agent_id,
                )
                await self.inject_task(
                    description="Run face_swap_detection on frames near detected discontinuities",
                    priority=20,  # High priority
                )

        # 2. Reactive trigger for VFI (Video Frame Interpolation) artifacts
        if tool_name == "vfi_error_map":
            vfi_signals = [
                finding.metadata.get("vfi_artifact_detected"),
                finding.metadata.get("interpolation_artifact_detected"),
                finding.metadata.get("manipulation_detected"),
            ]
            if any(vfi_signals) or finding.evidence_verdict == "POSITIVE":
                logger.info(
                    "VFI motion interpolation artifact detected; injecting deep optical flow audit",
                    agent_id=self.agent_id,
                )
                await self.inject_task(
                    description="Run deep optical_flow_analysis on VFI-flagged segments to verify motion continuity",
                    priority=15,
                )
