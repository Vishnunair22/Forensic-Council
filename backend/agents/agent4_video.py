"""
Agent 4 - Temporal Video Analysis Agent.

Temporal consistency and video integrity expert for detecting 
frame-level edit points, deepfake face swaps, optical flow anomalies, 
rolling shutter violations, and cross-modal temporal inconsistencies.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from agents.base_agent import ForensicAgent
from core.config import Settings
from core.custody_logger import CustodyLogger
from core.episodic_memory import EpisodicMemory
from core.evidence import EvidenceArtifact
from core.inter_agent_bus import InterAgentBus, InterAgentCall, InterAgentCallType
from core.tool_registry import ToolRegistry
from core.working_memory import WorkingMemory
from core.ml_subprocess import run_ml_tool
from infra.evidence_store import EvidenceStore
# Import real tool implementations
from tools.video_tools import (
    optical_flow_analyze as real_optical_flow_analyze,
    frame_window_extract as real_frame_window_extract,
    frame_consistency_analyze as real_frame_consistency_analyze,
    face_swap_detect_deepface as real_face_swap_detect,  # DeepFace embedding model
    video_metadata_extract as real_video_metadata_extract,
)


class Agent4Video(ForensicAgent):
    """
    Agent 4 - Temporal Video Analysis Agent.
    
    Mandate: Detect frame-level edit points, deepfake face swaps, 
    optical flow anomalies, rolling shutter violations, and 
    cross-modal temporal inconsistencies.
    
    Task Decomposition:
    1. Run full-timeline optical flow analysis and generate temporal anomaly heatmap
    2. For each flagged anomaly window: extract frames and run frame-to-frame consistency analysis
    3. Classify each anomaly as EXPLAINABLE or SUSPICIOUS
    4. For frames containing human faces: run face-swap detection
    5. Run frequency-domain GAN artifact detection on extracted frames
    6. For each suspicious anomaly: issue collaborative call to Agent 2 for audio cross-verification
    7. Validate rolling shutter behavior and compression patterns against claimed device metadata
    8. Run adversarial robustness check against optical flow evasion
    9. Self-reflection pass
    10. Submit calibrated findings to Arbiter with dual anomaly classification list preserved
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
        inter_agent_bus: Optional[Any] = None,
    ) -> None:
        """Initialize Agent 4 with optional inter-agent bus."""
        super().__init__(
            agent_id=agent_id,
            session_id=session_id,
            evidence_artifact=evidence_artifact,
            config=config,
            working_memory=working_memory,
            episodic_memory=episodic_memory,
            custody_logger=custody_logger,
            evidence_store=evidence_store,
        )
        self._inter_agent_bus = inter_agent_bus
    
    @property
    def agent_name(self) -> str:
        """Human-readable name of this agent."""
        return "Agent4_TemporalVideo"
    
    @property
    def task_decomposition(self) -> list[str]:
        """
        List of tasks this agent performs.
        Exact 10 tasks from architecture document.
        """
        return [
            "Run full-timeline optical flow analysis and generate temporal anomaly heatmap",
            "For each flagged anomaly window: extract frames and run frame-to-frame consistency analysis",
            "Classify each anomaly as EXPLAINABLE or SUSPICIOUS",
            "For frames containing human faces: run face-swap detection",
            "Run frequency-domain GAN artifact detection on extracted frames",
            "For each suspicious anomaly: issue collaborative call to Agent 2 for audio cross-verification",
            "Validate rolling shutter behavior and compression patterns against claimed device metadata",
            "Run adversarial robustness check against optical flow evasion",
            "Self-reflection pass",
            "Submit calibrated findings to Arbiter with dual anomaly classification list preserved",
        ]
    
    @property
    def iteration_ceiling(self) -> int:
        """Maximum iterations for the ReAct loop."""
        return 20
    
    async def build_tool_registry(self) -> ToolRegistry:
        """
        Build and return the tool registry for this agent.
        
        Registers real tool implementations for:
        - optical_flow_analysis: Full-timeline optical flow analysis
        - frame_extraction: Frame window extraction
        - frame_consistency_analysis: Frame-to-frame consistency analysis
        - face_swap_detection: Face-swap detection
        - video_metadata: Video metadata extraction
        - anomaly_classification: Anomaly classification (stub)
        - rolling_shutter_validation: Rolling shutter validation (stub)
        - inter_agent_call: Inter-agent communication (stub)
        - adversarial_robustness_check: Adversarial robustness check (stub)
        """
        registry = ToolRegistry()
        
        # Real tool handlers - wrap to accept input_data dict
        async def optical_flow_analysis_handler(input_data: dict) -> dict:
            """Handle optical flow analysis with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            flow_threshold = input_data.get("flow_threshold", 5.0)
            return await real_optical_flow_analyze(
                artifact=artifact,
                flow_threshold=flow_threshold,
            )
        
        async def frame_extraction_handler(input_data: dict) -> dict:
            """Handle frame extraction with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            start_frame = input_data.get("start_frame", 0)
            end_frame = input_data.get("end_frame", 100)
            return await real_frame_window_extract(
                artifact=artifact,
                start_frame=start_frame,
                end_frame=end_frame,
            )
        
        async def frame_consistency_analysis_handler(input_data: dict) -> dict:
            """Handle frame consistency analysis with input_data dict."""
            frames_artifact = input_data.get("frames_artifact")
            if frames_artifact is None:
                return {"error": "frames_artifact is required"}
            histogram_threshold = input_data.get("histogram_threshold", 0.5)
            edge_threshold = input_data.get("edge_threshold", 0.3)
            return await real_frame_consistency_analyze(
                frames_artifact=frames_artifact,
                histogram_threshold=histogram_threshold,
                edge_threshold=edge_threshold,
            )
        
        async def face_swap_detection_handler(input_data: dict) -> dict:
            """Handle face swap detection with input_data dict."""
            frames_artifact = input_data.get("frames_artifact")
            if frames_artifact is None:
                return {"error": "frames_artifact is required"}
            confidence_threshold = input_data.get("confidence_threshold", 0.5)
            return await real_face_swap_detect(
                frames_artifact=frames_artifact,
                confidence_threshold=confidence_threshold,
            )
        
        async def video_metadata_handler(input_data: dict) -> dict:
            """Handle video metadata extraction with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            return await real_video_metadata_extract(artifact=artifact)
            
        async def deepfake_frequency_check_handler(input_data: dict) -> dict:
            artifact = input_data.get("frames_artifact") or input_data.get("artifact") or self.evidence_artifact
            return await run_ml_tool("deepfake_frequency.py", artifact.file_path, timeout=25.0)
        
        async def anomaly_classification(input_data: dict) -> dict:
            """Classify anomaly via SSIM + motion vector analysis."""
            frame_a = input_data.get("frame_a_path")
            frame_b = input_data.get("frame_b_path")
            motion = input_data.get("motion_vector_magnitude", 0.0)
            if not frame_a or not frame_b:
                return {"classification": "INCONCLUSIVE", "court_defensible": True,
                        "note": "frame_a_path and frame_b_path required"}
            return await run_ml_tool(
                "anomaly_classifier.py",
                frame_a,
                extra_args=["--frameB", frame_b, "--motion", str(motion)],
                timeout=15.0
            )
        
        async def rolling_shutter_validation(input_data: dict) -> dict:
            """Validate rolling shutter via optical flow scanline skew analysis."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            sample = input_data.get("sample_seconds", 5.0)
            return await run_ml_tool(
                "rolling_shutter_validator.py",
                artifact.file_path,
                extra_args=["--sample", str(sample)],
                timeout=30.0
            )
        
        async def inter_agent_call_handler(input_data: dict) -> dict:
            """Real inter-agent call via InterAgentBus."""
            if self._inter_agent_bus is None:
                return {"status": "error", "message": "No inter_agent_bus injected"}

            from core.inter_agent_bus import InterAgentCall, InterAgentCallType
            call = InterAgentCall(
                caller_agent_id=self.agent_id,
                target_agent_id=input_data.get("target_agent", "agent2"),
                call_type=InterAgentCallType.CROSS_VERIFY,
                payload={
                    "timestamp_ref": input_data.get("timestamp_ref"),
                    "question": input_data.get("question", "Confirm audio-visual sync at flagged timestamp"),
                }
            )
            response = await self._inter_agent_bus.send(call)
            return response
        
        async def adversarial_robustness_check(input_data: dict) -> dict:
            return {
                "status": "stub",
                "court_defensible": False,
                "warning": "STUB: adversarial_robustness_check returns fabricated data. Integrate real adversarial testing.",
                "adversarial_pattern_detected": None,
                "confidence": None,
            }
        
        # Register tools
        registry.register("optical_flow_analysis", optical_flow_analysis_handler, "Full-timeline optical flow analysis")
        registry.register("frame_extraction", frame_extraction_handler, "Frame window extraction")
        registry.register("frame_consistency_analysis", frame_consistency_analysis_handler, "Frame-to-frame consistency analysis")
        registry.register("face_swap_detection", face_swap_detection_handler, "Face-swap detection")
        registry.register("deepfake_frequency_check", deepfake_frequency_check_handler, "Detect GAN/deepfake artifacts in frequency domain")
        registry.register("video_metadata", video_metadata_handler, "Video metadata extraction")
        registry.register("anomaly_classification", anomaly_classification, "Anomaly classification")
        registry.register("rolling_shutter_validation", rolling_shutter_validation, "Rolling shutter validation")
        registry.register("inter_agent_call", inter_agent_call_handler, "Inter-agent communication")
        registry.register("adversarial_robustness_check", adversarial_robustness_check, "Adversarial robustness check")
        
        return registry
    
    async def build_initial_thought(self) -> str:
        """
        Build the initial thought for the ReAct loop.
        
        Returns:
            Opening thought for temporal video analysis investigation
        """
        return (
            f"Starting temporal video analysis for artifact "
            f"{self.evidence_artifact.artifact_id}. "
            f"I will begin with full-timeline optical flow analysis to generate a temporal anomaly heatmap, "
            f"then proceed through frame extraction, consistency analysis, anomaly classification, "
            f"face-swap detection, and rolling shutter validation. "
            f"Total tasks to complete: {len(self.task_decomposition)}. "
            f"Note: I will maintain two distinct lists: EXPLAINABLE ANOMALIES and SUSPICIOUS ANOMALIES."
        )

    async def run_investigation(self):
        """
        Override to short-circuit when the evidence is not a video file.
        Returns a clear finding instead of running tools that will fail on images.
        """
        from core.react_loop import AgentFinding

        file_path = self.evidence_artifact.file_path.lower()
        mime = (self.evidence_artifact.metadata or {}).get("mime_type", "").lower()
        image_exts = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".svg")
        audio_exts = (".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".wma", ".aiff")

        is_image = any(file_path.endswith(ext) for ext in image_exts) or mime.startswith("image/")
        is_audio = any(file_path.endswith(ext) for ext in audio_exts) or mime.startswith("audio/")

        if is_image:
            finding = AgentFinding(
                agent_id=self.agent_id,
                finding_type="File type not applicable",
                confidence_raw=1.0,
                status="CONFIRMED",
                evidence_refs=[],
                reasoning_summary=(
                    "Temporal Video Analysis — The uploaded evidence is an image file. "
                    "Video analysis (optical flow, frame consistency, face-swap detection, "
                    "rolling shutter validation) is not applicable for image evidence. "
                    "No video frames were detected."
                ),
            )
            self._findings = [finding]
            self._react_chain = []
            self._reflection_report = None
            return self._findings

        if is_audio:
            finding = AgentFinding(
                agent_id=self.agent_id,
                finding_type="File type not applicable",
                confidence_raw=1.0,
                status="CONFIRMED",
                evidence_refs=[],
                reasoning_summary=(
                    "Temporal Video Analysis — The uploaded evidence is an audio file. "
                    "Video analysis (optical flow, frame consistency, face-swap detection, "
                    "rolling shutter validation) is not applicable for audio evidence. "
                    "No video track was detected."
                ),
            )
            self._findings = [finding]
            self._react_chain = []
            self._reflection_report = None
            return self._findings

        # For video files, run the full investigation
        return await super().run_investigation()