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
from tools.mediainfo_tools import (
    profile_av_container as real_profile_av_container,
    get_av_file_identity as real_get_av_file_identity,
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
    def deep_task_decomposition(self) -> list[str]:
        """
        Heavy tasks — deep face-swap detection, frequency analysis.
        Runs in background after initial findings are returned.
        """
        return [
            "Run deep face-swap detection with deepface ensemble on extracted frames",
            "Run comprehensive deepfake frequency analysis across full video",
            "Run inter-agent collaboration with Agent 2 for audio-visual timestamp correlation",
            "Run advanced codec fingerprinting for re-encoding event detection",
            "Run adversarial robustness check against optical flow evasion techniques",
        ]
    
    @property
    def iteration_ceiling(self) -> int:
        """Maximum iterations for the ReAct loop."""
        return 20
    
    @property
    def supported_file_types(self) -> list[str]:
        """Video agent supports video file types."""
        return ['video/']
    
    async def build_tool_registry(self) -> ToolRegistry:
        """
        Build and return the tool registry for this agent.
        
        Registers real tool implementations for:
        - optical_flow_analysis: Full-timeline optical flow analysis
        - frame_extraction: Frame window extraction
        - frame_consistency_analysis: Frame-to-frame consistency analysis
        - face_swap_detection: Face-swap detection
        - video_metadata: Video metadata extraction
        - anomaly_classification: SSIM + motion vector anomaly classification
        - rolling_shutter_validation: Optical flow scanline skew validation
        - inter_agent_call: Inter-agent communication via InterAgentBus
        - adversarial_robustness_check: Optical flow perturbation stability analysis
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
            # Use artifact directly - face_swap_detect_deepface expects EvidenceArtifact, not frames
            artifact = input_data.get("artifact") or input_data.get("frames_artifact") or self.evidence_artifact
            if artifact is None:
                return {"error": "artifact is required"}
            confidence_threshold = input_data.get("confidence_threshold", 0.5)
            return await real_face_swap_detect(
                artifact=artifact,
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
                callee_agent_id=input_data.get("target_agent", "Agent2"),
                call_type=InterAgentCallType.COLLABORATIVE,
                payload={
                    "timestamp_ref": input_data.get("timestamp_ref"),
                    "question": input_data.get("question", "Confirm audio-visual sync at flagged timestamp"),
                }
            )
            response = await self._inter_agent_bus.send(call, self._custody_logger)
            return response
        
        async def adversarial_robustness_check(input_data: dict) -> dict:
            """
            Adversarial robustness check for optical flow evasion.

            Extracts a short clip (up to 60 frames), adds mild per-frame
            perturbations (Gaussian noise at σ=3, brightness shift +10 %),
            and recomputes the dense optical flow mean on the perturbed
            frames.  If the temporal anomaly map changes substantially the
            original flow analysis is fragile and may have been engineered
            to evade temporal detectors.
            """
            import numpy as np
            import cv2

            artifact = input_data.get("artifact") or self.evidence_artifact

            try:
                cap = cv2.VideoCapture(artifact.file_path)
                if not cap.isOpened():
                    return {
                        "status": "skipped",
                        "court_defensible": True,
                        "adversarial_pattern_detected": False,
                        "note": "Video file could not be opened — skipping adversarial check.",
                    }

                frames = []
                MAX_FRAMES = 60
                while len(frames) < MAX_FRAMES:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
                cap.release()

                if len(frames) < 2:
                    return {
                        "status": "skipped",
                        "court_defensible": True,
                        "adversarial_pattern_detected": False,
                        "note": "Insufficient frames for adversarial flow check.",
                    }

                rng = np.random.default_rng(42)

                def _mean_flow(frame_list) -> float:
                    flows = []
                    for i in range(len(frame_list) - 1):
                        flow = cv2.calcOpticalFlowFarneback(
                            frame_list[i], frame_list[i + 1],
                            None, 0.5, 3, 15, 3, 5, 1.2, 0
                        )
                        mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
                        flows.append(float(mag.mean()))
                    return float(np.mean(flows)) if flows else 0.0

                original_flow = _mean_flow(frames)

                # 1 — Gaussian noise σ=3
                noisy_frames = [
                    np.clip(f.astype(np.float32) + rng.normal(0, 3.0, f.shape), 0, 255).astype(np.uint8)
                    for f in frames
                ]
                noisy_flow = _mean_flow(noisy_frames)
                noise_delta = abs(noisy_flow - original_flow) / (original_flow + 1e-9)

                # 2 — Brightness +10 %
                bright_frames = [
                    np.clip(f.astype(np.float32) * 1.10, 0, 255).astype(np.uint8)
                    for f in frames
                ]
                bright_flow = _mean_flow(bright_frames)
                bright_delta = abs(bright_flow - original_flow) / (original_flow + 1e-9)

                perturbation_deltas = {
                    "gaussian_noise_sigma3": round(noise_delta, 4),
                    "brightness_+10pct": round(bright_delta, 4),
                }

                EVASION_THRESHOLD = 0.40  # > 40 % relative flow shift is suspicious
                evasion_detected = any(v > EVASION_THRESHOLD for v in perturbation_deltas.values())

                return {
                    "status": "real",
                    "court_defensible": True,
                    "method": "Optical flow perturbation stability — Gaussian noise, brightness shift",
                    "adversarial_pattern_detected": evasion_detected,
                    "original_mean_flow": round(original_flow, 4),
                    "perturbation_deltas": perturbation_deltas,
                    "evasion_threshold": EVASION_THRESHOLD,
                    "frames_analyzed": len(frames),
                    "confidence": 0.73 if evasion_detected else 0.88,
                    "note": (
                        "Optical flow is highly sensitive to minor perturbations — possible adversarial frame blending."
                        if evasion_detected
                        else "Optical flow findings are stable under perturbation — results are robust."
                    ),
                }
            except Exception as e:
                return {
                    "status": "error",
                    "court_defensible": False,
                    "adversarial_pattern_detected": None,
                    "confidence": None,
                    "error": str(e),
                }

        async def mediainfo_profile_handler(input_data: dict) -> dict:
            """Deep container profiling via MediaInfo: codec, frame rate mode, encoding tool,
            creation date, VFR flag, container/codec mismatch, and editing software signals.
            Fast (<20ms) — should be called first on every video/audio file."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            return await real_profile_av_container(artifact=artifact)

        async def av_file_identity_handler(input_data: dict) -> dict:
            """Lightweight pre-screening: format, primary codec, duration, resolution,
            and any HIGH severity forensic flags only. Call before heavier ML tools."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            return await real_get_av_file_identity(artifact=artifact)

        # CRITICAL: optical_flow_analysis must be registered FIRST - it's the primary tool for this agent
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
        registry.register("mediainfo_profile", mediainfo_profile_handler, "Deep AV container profiling: codec, frame rate mode, encoding tool, VFR flag, forensic flags")
        registry.register("av_file_identity", av_file_identity_handler, "Lightweight AV pre-screen: format, codec, duration, high-severity flags")
        
        return registry
    
    async def build_initial_thought(self) -> str:
        """
        Build the contextually-grounded initial thought for the ReAct loop.

        Pre-screens with av_file_identity (MediaInfo, <20ms) to get
        container format, codec, duration, resolution, and any high-severity
        forensic flags before running heavy optical flow or face-swap models.
        """
        context_lines = []
        flags = []
        try:
            if self._tool_registry:
                handler = self._tool_registry._handlers.get("av_file_identity")
                if handler:
                    result = await handler({"artifact": self.evidence_artifact})
                    fmt = result.get("format", "")
                    codec = result.get("primary_video_codec", result.get("codec", ""))
                    duration = result.get("duration_seconds", "")
                    resolution = result.get("resolution", "")
                    fps = result.get("frame_rate", "")
                    if fmt:
                        context_lines.append(
                            f"Container: {fmt}, codec: {codec}, "
                            f"duration: {duration}s, resolution: {resolution}, fps: {fps}"
                        )
                    high_flags = result.get("high_severity_flags", [])
                    if high_flags:
                        flags = high_flags
                        context_lines.append("HIGH-SEVERITY FLAGS: " + ", ".join(high_flags))
        except Exception:
            pass

        context = " | ".join(context_lines) if context_lines else "Container pre-screen unavailable."
        flag_note = (
            " IMMEDIATE PRIORITY: investigate flags " + str(flags) + " in first 3 iterations."
            if flags else ""
        )
        return (
            f"Starting temporal video analysis. Evidence: {self.evidence_artifact.artifact_id}. "
            f"Container pre-screen — {context}.{flag_note} "
            f"Proceeding through {len(self.task_decomposition)} tasks: "
            "optical flow analysis, frame extraction, frame consistency, "
            "deepfake frequency check, face-swap detection, and rolling shutter validation. "
            "I will maintain EXPLAINABLE ANOMALIES and SUSPICIOUS ANOMALIES lists "
            "and cross-reference temporal signals with the container metadata above."
        )

    async def run_investigation(self):
        """
        Override to short-circuit when the evidence is not a video file.

        Always initialises working memory FIRST so the heartbeat shows
        task progress (including the validation step) even for skipped files.
        """
        from core.react_loop import AgentFinding
        from core.working_memory import TaskStatus

        # Step 1: always initialise working memory so the heartbeat shows
        # activity immediately, even when we end up skipping.
        await self._initialize_working_memory()

        file_path = self.evidence_artifact.file_path.lower()
        mime = (self.evidence_artifact.metadata or {}).get("mime_type", "").lower()
        image_exts = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".svg")
        audio_exts = (".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".wma", ".aiff")

        is_image = any(file_path.endswith(ext) for ext in image_exts) or mime.startswith("image/")
        is_audio = any(file_path.endswith(ext) for ext in audio_exts) or mime.startswith("audio/")

        async def _mark_all_complete():
            """Mark every task complete so the heartbeat shows full progress."""
            try:
                state = await self.working_memory.get_state(
                    session_id=self.session_id, agent_id=self.agent_id
                )
                if state:
                    for task in state.tasks:
                        await self.working_memory.update_task(
                            session_id=self.session_id,
                            agent_id=self.agent_id,
                            task_id=task.task_id,
                            status=TaskStatus.COMPLETE,
                            result_ref="file_type_validation",
                        )
            except Exception:
                pass

        if is_image:
            await _mark_all_complete()
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
            await _mark_all_complete()
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

        # For video files: skip memory re-init in base class, build registry, run full loop
        self._skip_memory_init = True
        self._tool_registry = await self.build_tool_registry()
        return await super().run_investigation()