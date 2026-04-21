"""
Audio Tool Handlers
===================

Domain-specific handlers for audio forensic tools.

Fix log (applied in audit pass):
  - All imports corrected — audio_tools function names changed between versions.
  - audio_splice_detect and enf_analysis moved to ml_tools; wrapped in executor.
  - All standard handlers now call _record_tool_result so results persist to
    _tool_context and are visible to the deep ensemble and cross-tool consumers.
  - Key mismatches fixed: anti_spoofing_detect and speaker_diarize stored under
    the registered tool name, not the legacy underscore variant.
  - Removed dead InferenceClient allocation from anti_spoofing_detection_handler.
  - audio_gen_signature failure path now returns a fully-structured degraded dict.
  - _diarization_fallback reshape guarded against non-divisible audio lengths;
    forensic keys (confidence, available, court_defensible) added to result.
  - neural_prosody fallback records result before returning.
"""

from __future__ import annotations

import asyncio

import numpy as np
import soundfile as sf

from core.handlers.base import BaseToolHandler
from core.ml_subprocess import run_ml_tool
from core.structured_logging import get_logger
from tools.audio_tools import (
    anti_spoofing_detect as real_anti_spoofing_detect,
)
from tools.audio_tools import (
    av_sync_verify as real_av_sync_verify,
)
from tools.audio_tools import (
    background_noise_consistency as real_background_noise_consistency,
)
from tools.audio_tools import (
    codec_fingerprint as real_codec_fingerprint,
)
from tools.audio_tools import (
    prosody_analyze as real_prosody_analyze,
)
from tools.audio_tools import (
    speaker_diarize as real_speaker_diarize,
)
from tools.ml_tools.audio_splice_detector import detect_audio_splices  # sync
from tools.ml_tools.enf_analysis import analyze_enf  # sync

# voice_clone_detect is run via ml_subprocess (subprocess isolation, correct async boundary)

logger = get_logger(__name__)


class AudioHandlers(BaseToolHandler):
    """Handles Audio Integrity, Voice Clone, and Anti-spoofing tools."""

    def register_tools(self, registry) -> None:
        """Register tools with the agent's ToolRegistry."""
        registry.register("speaker_diarize",         self.speaker_diarization_handler,     "Speaker diarization")
        registry.register("anti_spoofing_detect",    self.anti_spoofing_detection_handler,  "Anti-spoofing detection")
        registry.register("prosody_analyze",         self.prosody_analysis_handler,         "Prosody analysis")
        registry.register("audio_splice_detect",     self.audio_splice_detect_handler,      "ML splice detection")
        registry.register("background_noise_analysis", self.background_noise_analysis_handler, "Noise consistency")
        registry.register("codec_fingerprinting",    self.codec_fingerprinting_handler,     "Codec fingerprinting")
        registry.register("audio_visual_sync",       self.audio_visual_sync_handler,        "AV sync verification")
        registry.register("voice_clone_detect",      self.voice_clone_detect_handler,       "Voice clone detection")
        registry.register("enf_analysis",            self.enf_analysis_handler,             "ENF analysis")
        registry.register("neural_prosody",          self.neural_prosody_handler,           "Wav2Vec 2.0 based semantic prosody analysis")
        registry.register("audio_gen_signature",     self.audio_gen_signature_handler,      "Generative audio artifact signature analysis")

    # ── Refinement: Neural Prosody ────────────────────────────────────────────

    async def neural_prosody_handler(self, input_data: dict) -> dict:
        """Neural prosody analysis. Falls back to acoustic prosody."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        result = await run_ml_tool("neural_prosody_classifier.py", artifact.file_path, timeout=15.0)
        if not result.get("error") and result.get("available"):
            await self.agent._record_tool_result("neural_prosody", result)
            return result
        # Fallback — record result from prosody_analysis_handler
        fallback = await self.prosody_analysis_handler(input_data)
        return fallback

    # ── Refinement: Audio Gen Signature ──────────────────────────────────────

    async def audio_gen_signature_handler(self, input_data: dict) -> dict:
        """Detection of spectral artifacts specific to generative TTS engines."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        result = await run_ml_tool("audio_gen_signature_scanner.py", artifact.file_path, timeout=10.0)
        if not result.get("error") and result.get("available"):
            await self.agent._record_tool_result("audio_gen_signature", result)
            return result
        # Degraded — ML tool unavailable
        degraded = {
            "available": False,
            "analysis_source": "neural_signature",
            "confidence": 0.0,
            "court_defensible": False,
            "degraded": True,
            "fallback_reason": "audio_gen_signature_scanner unavailable",
        }
        await self.agent._record_tool_result("audio_gen_signature", degraded)
        return degraded

    # ── Standard Handlers ────────────────────────────────────────────────────

    async def speaker_diarization_handler(self, input_data: dict) -> dict:
        """Speaker diarization using SpeechBrain ECAPA-TDNN."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        min_speakers = input_data.get("min_speakers", 1)
        max_speakers = input_data.get("max_speakers", 10)
        await self.agent.update_sub_task("Establishing voice count baseline...")
        result = await real_speaker_diarize(
            artifact=artifact,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
            progress_callback=self.agent.update_sub_task,
        )
        if result.get("error") or not result.get("available"):
            result = await self._diarization_fallback(artifact.file_path, min_speakers, max_speakers)
        # Store under the registered tool name
        await self.agent._record_tool_result("speaker_diarize", result)
        return result

    async def _diarization_fallback(self, file_path: str, min_s: int, max_s: int) -> dict:
        """Heuristic VAD-based speaker estimation."""
        try:
            audio, sr = sf.read(file_path)
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            frame_len = int(sr * 0.02)
            if frame_len < 1:
                raise ValueError("Sample rate too low for 20ms frames")
            # Trim to multiple of frame_len to avoid reshape error
            trim_len = len(audio) - (len(audio) % frame_len)
            audio = audio[:trim_len]
            if trim_len == 0:
                raise ValueError("Audio too short after trimming")
            rms = np.sqrt(np.mean(audio.reshape(-1, frame_len) ** 2, axis=1))
            thresh = np.percentile(rms, 20)
            is_speech = rms > thresh
            changes = int(np.sum(np.diff(is_speech.astype(int)) != 0))
            return {
                "estimated_speakers": max(min_s, min(max_s, changes // 10)),
                "degraded": True,
                "confidence": 0.40,
                "available": True,
                "court_defensible": False,
                "note": "Energy-based VAD estimate — diarization model unavailable.",
            }
        except Exception as exc:
            return {
                "error": f"Diarization fallback failed: {exc}",
                "available": False,
                "confidence": 0.0,
                "court_defensible": False,
                "degraded": True,
            }

    async def anti_spoofing_detection_handler(self, input_data: dict) -> dict:
        """Anti-spoofing detection via AASIST / legacy SpeechBrain."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        try:
            result = await real_anti_spoofing_detect(
                artifact=artifact,
                progress_callback=self.agent.update_sub_task
            )
        except Exception as exc:
            result = {"error": str(exc), "degraded": True, "available": False, "confidence": 0.0}
        # Store under the registered tool name
        await self.agent._record_tool_result("anti_spoofing_detect", result)
        return result

    async def prosody_analysis_handler(self, input_data: dict) -> dict:
        """Acoustic prosody analysis (pitch, jitter, shimmer via Praat/librosa)."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        result = await real_prosody_analyze(artifact=artifact)
        await self.agent._record_tool_result("prosody_analyze", result)
        return result

    async def audio_splice_detect_handler(self, input_data: dict) -> dict:
        """MFCC IsolationForest splice point detection (sync — runs in executor)."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        loop = asyncio.get_running_loop()
        await self.agent.update_sub_task("Tracing isolation forest splice points...")
        result = await loop.run_in_executor(None, detect_audio_splices, artifact.file_path)
        await self.agent._record_tool_result("audio_splice_detect", result)
        return result

    async def background_noise_analysis_handler(self, input_data: dict) -> dict:
        """Background noise floor consistency analysis."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        result = await real_background_noise_consistency(artifact=artifact)
        await self.agent._record_tool_result("background_noise_analysis", result)
        return result

    async def codec_fingerprinting_handler(self, input_data: dict) -> dict:
        """Codec chain re-encoding event fingerprinting."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        result = await real_codec_fingerprint(artifact=artifact)
        await self.agent._record_tool_result("codec_fingerprinting", result)
        return result

    async def audio_visual_sync_handler(self, input_data: dict) -> dict:
        """Audio-visual synchronisation verification."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        result = await real_av_sync_verify(artifact=artifact)
        await self.agent._record_tool_result("audio_visual_sync", result)
        return result

    async def voice_clone_detect_handler(self, input_data: dict) -> dict:
        """Voice clone / AI speech synthesis detection via subprocess."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        # Run as managed subprocess — avoids the Python startup cost on repeat calls
        # and keeps heavy SpeechBrain/librosa imports out of the main process.
        result = await run_ml_tool("voice_clone_detector.py", artifact.file_path, timeout=30.0)
        if not result.get("error") and result.get("available"):
            await self.agent._record_tool_result("voice_clone_detect", result)
            return result
        # Degraded path — subprocess failed (missing deps, timeout, etc.)
        degraded = {
            "verdict": "UNAVAILABLE",
            "available": False,
            "degraded": True,
            "confidence": 0.0,
            "court_defensible": False,
            "fallback_reason": result.get("error", "voice_clone_detector subprocess failed"),
        }
        await self.agent._record_tool_result("voice_clone_detect", degraded)
        return degraded

    async def enf_analysis_handler(self, input_data: dict) -> dict:
        """ENF electrical network frequency analysis (sync — runs in executor)."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        loop = asyncio.get_running_loop()
        await self.agent.update_sub_task("Analyzing electrical network frequency grid...")
        result = await loop.run_in_executor(None, analyze_enf, artifact.file_path)
        await self.agent._record_tool_result("enf_analysis", result)
        return result
