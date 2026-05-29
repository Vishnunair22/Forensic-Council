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

import asyncio

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

    persona: str = (
        "You are Dr. Lena Fischer, a video forensics specialist with the European Cybercrime Centre. "
        "You specialize in inter-frame forgery detection, VFI artifacts, optical flow discontinuities, "
        "and rolling shutter validation. You produce timestamped, frame-indexed findings. You report "
        "specific frame numbers and time codes, distinguish between encoding artifacts and deliberate "
        "manipulation, and explicitly mark any sections where frame-level evidence was insufficient "
        "to reach a definitive conclusion."
    )

    @property
    def agent_name(self) -> str:
        return "Agent4_VideoTemporal"

    @property
    def task_decomposition(self) -> list[str]:
        # PHASE 1: INITIAL ANALYSIS
        return [
            "Run optical_flow_analysis and generate temporal anomaly heatmap",
            "Run frame_consistency_analysis for temporal inter-frame jumps",
            "Run video_metadata for container timing validation",
        ]

    @property
    def deep_task_decomposition(self) -> list[str]:
        # frame_extraction, face_swap_detection, deepfake_frequency_check, and
        # adversarial_robustness_check removed from base — all reactively injected
        # by _on_tool_result_impl when their trigger conditions are met.
        return [
            "Run optical_flow_analysis and generate temporal anomaly heatmap",
            "Run interframe_forgery_detector for motion ghosting and SSIM variance",
            "Run rolling_shutter_validation against claimed device metadata",
            "Run compression_artifact_analysis for P-frame/I-frame incongruence",
            "Read shared image context for key-frame visual grounding",
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

        # ── Shared Visual Profile Reader ──────────────────────────────────────
        async def read_shared_image_context_handler(input_data: dict) -> dict:
            async def _visual_profile_signal_callback(msg: str):
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
                    logger.debug(f"{self.agent_id}: Visual profile signal callback failed", error=str(e))

            return await self._visual_evidence_profile_handler(
                input_data, signal_callback=_visual_profile_signal_callback
            )

        registry.register(
            "read_shared_image_context",
            read_shared_image_context_handler,
            "Read Agent 1 visual profile for video frame grounding",
        )

        return registry

    async def run_deep_investigation(self) -> list[AgentFinding]:
        """Run the deep analysis pass with a hard timeout for heavy ML."""
        try:
            # Frontend expected maximum threshold for deep analysis
            timeout_limit = min(float(self.config.investigation_timeout), 120.0)
            return await asyncio.wait_for(super().run_deep_investigation(), timeout=timeout_limit)
        except TimeoutError:
            logger.error(
                f"{self.agent_name} deep investigation reached hard timeout budget. Gracefully yielding existing findings.",
                agent_id=self.agent_id,
            )
            # Return whatever findings were accumulated up to this point in self._findings
            return getattr(self, "_findings", [])

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

        # 3. If optical flow finds anomalies, inject frame extraction + adversarial check
        if tool_name == "optical_flow_analysis":
            anomaly_count = finding.metadata.get("anomaly_count", 0)
            if anomaly_count > 0:
                logger.info(
                    "Optical flow anomalies detected; injecting frame extraction and adversarial check",
                    agent_id=self.agent_id,
                )
                await self.inject_task(
                    description="Run frame_extraction on flagged anomaly windows",
                    priority=18,
                )
                await self.inject_task(
                    description="Run adversarial_robustness_check on optical flow results",
                    priority=14,
                )

        # 4. If face swap detected, inject deepfake frequency check
        if tool_name == "face_swap_detection":
            if finding.evidence_verdict == "POSITIVE":
                logger.info(
                    "Face swap detected; injecting deepfake frequency check",
                    agent_id=self.agent_id,
                )
                await self.inject_task(
                    description="Run deepfake_frequency_check on extracted frames",
                    priority=17,
                )
