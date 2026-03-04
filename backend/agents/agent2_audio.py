"""
Agent 2 - Audio & Multimedia Forensics Agent.

Audio authenticity and multimedia consistency expert for detecting 
audio deepfakes, splices, re-encoding events, prosody anomalies, 
and audio-visual sync breaks.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional
import random
import hashlib

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
from tools.audio_tools import (
    speaker_diarize_pyannote as real_speaker_diarize,       # pyannote.audio 3.1
    anti_spoofing_speechbrain as real_anti_spoofing_detect, # SpeechBrain ECAPA
    prosody_praat as real_prosody_analyze,                  # praat-parselmouth
    background_noise_consistency as real_background_noise_consistency,
    codec_fingerprint as real_codec_fingerprint,
    av_sync_verify as real_av_sync_verify,                  # moviepy+librosa
)


class Agent2Audio(ForensicAgent):
    """
    Agent 2 - Audio & Multimedia Forensics Agent.

    Mandate: Detect audio deepfakes, splices, re-encoding events,
    prosody anomalies, and audio-visual sync breaks.

    Task Decomposition:
    1. Run speaker diarization - establish voice count baseline
    2. Run anti-spoofing detection on primary speaker segments
    3. Run prosody analysis across full track
    4. Run ML-based splice point detection on audio segments
    5. Run background noise consistency analysis - identify shift points
    6. Run codec fingerprinting for re-encoding event detection
    7. Run audio-visual sync verification against video track timestamps
    8. Issue collaborative call to Agent 4 for any flagged timestamps
    9. Run adversarial robustness check against known anti-spoofing evasion
    10. Self-reflection pass
    11. Submit calibrated findings to Arbiter
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
        inter_agent_bus: Optional[InterAgentBus] = None,
    ) -> None:
        """Initialize Agent 2 with optional inter-agent bus."""
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
        return "Agent2_AudioForensics"
    
    @property
    def task_decomposition(self) -> list[str]:
        """
        List of tasks this agent performs.
        Exact 11 tasks from architecture document.
        """
        return [
            "Run speaker diarization - establish voice count baseline",
            "Run anti-spoofing detection on primary speaker segments",
            "Run prosody analysis across full track",
            "Run ML-based splice point detection on audio segments",
            "Run background noise consistency analysis - identify shift points",
            "Run codec fingerprinting for re-encoding event detection",
            "Run audio-visual sync verification against video track timestamps",
            "Issue collaborative call to Agent 4 for any flagged timestamps",
            "Run adversarial robustness check against known anti-spoofing evasion",
            "Self-reflection pass",
            "Submit calibrated findings to Arbiter",
        ]
    
    @property
    def iteration_ceiling(self) -> int:
        """Maximum iterations for the ReAct loop."""
        return 20
    
    async def build_tool_registry(self) -> ToolRegistry:
        """
        Build and return the tool registry for this agent.
        
        Registers real tool implementations for:
        - speaker_diarization: Speaker diarization
        - anti_spoofing_detection: Anti-spoofing detection
        - prosody_analysis: Prosody analysis
        - background_noise_analysis: Background noise consistency analysis
        - codec_fingerprinting: Codec fingerprinting
        - audio_visual_sync: Audio-visual sync verification (stub)
        - inter_agent_call: Inter-agent communication (stub)
        - adversarial_robustness_check: Adversarial robustness check (stub)
        """
        registry = ToolRegistry()
        
        # Real tool handlers - wrap to accept input_data dict
        async def speaker_diarization_handler(input_data: dict) -> dict:
            """Handle speaker diarization with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            min_speakers = input_data.get("min_speakers", 1)
            max_speakers = input_data.get("max_speakers", 10)
            return await real_speaker_diarize(
                artifact=artifact,
                min_speakers=min_speakers,
                max_speakers=max_speakers,
            )
        
        async def anti_spoofing_detection_handler(input_data: dict) -> dict:
            """Handle anti-spoofing detection with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            segment = input_data.get("segment")
            return await real_anti_spoofing_detect(
                artifact=artifact,
                segment=segment,
            )
        
        async def prosody_analysis_handler(input_data: dict) -> dict:
            """Handle prosody analysis with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            return await real_prosody_analyze(artifact=artifact)
        
        async def background_noise_analysis_handler(input_data: dict) -> dict:
            """Handle background noise analysis with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            segment_duration = input_data.get("segment_duration", 1.0)
            return await real_background_noise_consistency(
                artifact=artifact,
                segment_duration=segment_duration,
            )
        
        async def codec_fingerprinting_handler(input_data: dict) -> dict:
            """Handle codec fingerprinting with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            return await real_codec_fingerprint(artifact=artifact)
        
        async def audio_splice_detect_handler(input_data: dict) -> dict:
            """Run ML-based audio splice point detection on segments."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            window = input_data.get("window", 1.0)
            return await run_ml_tool("audio_splice_detector.py", artifact.file_path,
                                      extra_args=["--window", str(window)], timeout=25.0)
        
        async def audio_visual_sync_handler(input_data: dict) -> dict:
            """Real AV sync using moviepy+librosa onset correlation."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            return await real_av_sync_verify(artifact=artifact)

        async def inter_agent_call_handler(input_data: dict) -> dict:
            """Real inter-agent call via InterAgentBus."""
            if self._inter_agent_bus is None:
                return {"status": "error", "message": "No inter_agent_bus injected"}

            from core.inter_agent_bus import InterAgentCall, InterAgentCallType
            call = InterAgentCall(
                caller_agent_id=self.agent_id,
                callee_agent_id=input_data.get("target_agent", "Agent4"),
                call_type=InterAgentCallType.COLLABORATIVE,
                payload={
                    "timestamp_ref": input_data.get("timestamp_ref"),
                    "question": input_data.get("question", "Confirm audio-visual sync at flagged timestamp"),
                }
            )
            response = await self._inter_agent_bus.send(call, self._custody_logger)
            return response

        async def adversarial_robustness_check_handler(input_data: dict) -> dict:
            return {
                "status": "stub",
                "court_defensible": False,
                "warning": "STUB: adversarial_robustness_check returns fabricated data. Integrate real adversarial testing.",
                "adversarial_pattern_detected": None,
                "confidence": None,
            }
        
        # Register tools
        registry.register("speaker_diarization", speaker_diarization_handler, "Speaker diarization")
        registry.register("anti_spoofing_detection", anti_spoofing_detection_handler, "Anti-spoofing detection")
        registry.register("prosody_analysis", prosody_analysis_handler, "Prosody analysis")
        registry.register("audio_splice_detect", audio_splice_detect_handler, "Run ML-based audio splice detection on segments")
        registry.register("background_noise_analysis", background_noise_analysis_handler, "Background noise consistency analysis")
        registry.register("codec_fingerprinting", codec_fingerprinting_handler, "Codec fingerprinting")
        registry.register("audio_visual_sync", audio_visual_sync_handler, "Audio-visual sync verification")
        registry.register("inter_agent_call", inter_agent_call_handler, "Inter-agent communication")
        registry.register("adversarial_robustness_check", adversarial_robustness_check_handler, "Adversarial robustness check")
        
        return registry
    
    async def build_initial_thought(self) -> str:
        """
        Build the initial thought for the ReAct loop.
        
        Returns:
            Opening thought for audio forensics investigation
        """
        return (
            f"Starting audio and multimedia forensics analysis for artifact "
            f"{self.evidence_artifact.artifact_id}. "
            f"I will begin with speaker diarization to establish voice count baseline, "
            f"then proceed through anti-spoofing detection, prosody analysis, "
            f"background noise consistency, codec fingerprinting, and audio-visual sync verification. "
            f"Total tasks to complete: {len(self.task_decomposition)}."
        )

    async def run_investigation(self):
        """
        Override to short-circuit when the evidence is not an audio/video file.
        Returns a clear finding instead of running tools that will fail on images.
        """
        from core.react_loop import AgentFinding

        file_path = self.evidence_artifact.file_path.lower()
        mime = (self.evidence_artifact.metadata or {}).get("mime_type", "").lower()
        image_exts = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".svg")

        is_image = any(file_path.endswith(ext) for ext in image_exts) or mime.startswith("image/")

        if is_image:
            finding = AgentFinding(
                agent_id=self.agent_id,
                finding_type="File type not applicable",
                confidence_raw=1.0,
                status="CONFIRMED",
                evidence_refs=[],
                reasoning_summary=(
                    "Audio Forensics — The uploaded evidence is an image file. "
                    "Audio analysis (speaker diarization, anti-spoofing, prosody, "
                    "codec fingerprinting) is not applicable for image evidence. "
                    "No audio track was detected."
                ),
            )
            self._findings = [finding]
            self._react_chain = []
            self._reflection_report = None
            return self._findings

        # For audio/video files, run the full investigation
        return await super().run_investigation()