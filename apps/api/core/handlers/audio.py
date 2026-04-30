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
import hashlib
import tempfile
from dataclasses import replace
from pathlib import Path

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

    async def _audio_artifact(self):
        """Return an audio-file artifact, extracting video audio once if needed."""
        artifact = self.agent.evidence_artifact
        mime = getattr(artifact, "mime_type", "") or ""
        if not mime.startswith("video/"):
            return artifact

        cached = getattr(self.agent, "_extracted_audio_artifact", None)
        if cached is not None:
            return cached

        src = Path(artifact.file_path)
        out_path = Path(tempfile.gettempdir()) / f"{self.agent.session_id}_{src.stem}_audio.wav"
        try:
            import imageio_ffmpeg

            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            proc = await asyncio.create_subprocess_exec(
                ffmpeg,
                "-y",
                "-i",
                str(src),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "wav",
                str(out_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            if proc.returncode != 0 or not out_path.exists() or out_path.stat().st_size == 0:
                err = stderr.decode("utf-8", errors="ignore")[-300:] if stderr else "ffmpeg failed"
                raise RuntimeError(err)

            content_hash = hashlib.sha256(out_path.read_bytes()).hexdigest()
            extracted = replace(
                artifact,
                file_path=str(out_path),
                content_hash=content_hash,
                metadata={
                    **(artifact.metadata or {}),
                    "mime_type": "audio/wav",
                    "extracted_from_video": artifact.file_path,
                },
            )
            self.agent._extracted_audio_artifact = extracted
            return extracted
        except Exception as exc:
            logger.warning("Video audio extraction failed", file_path=str(src), error=str(exc))
            return artifact

    def register_tools(self, registry) -> None:
        """Register tools with the agent's ToolRegistry."""
        registry.register(
            "speaker_diarize", self.speaker_diarization_handler, "Speaker diarization"
        )
        registry.register(
            "anti_spoofing_detect", self.anti_spoofing_detection_handler, "Anti-spoofing detection"
        )
        registry.register("prosody_analyze", self.prosody_analysis_handler, "Prosody analysis")
        registry.register(
            "audio_splice_detect", self.audio_splice_detect_handler, "ML splice detection"
        )
        registry.register(
            "background_noise_analysis", self.background_noise_analysis_handler, "Noise consistency"
        )
        registry.register(
            "codec_fingerprinting", self.codec_fingerprinting_handler, "Codec fingerprinting"
        )
        registry.register(
            "audio_visual_sync", self.audio_visual_sync_handler, "AV sync verification"
        )
        registry.register(
            "voice_clone_detect", self.voice_clone_detect_handler, "Voice clone detection"
        )
        registry.register("enf_analysis", self.enf_analysis_handler, "ENF analysis")
        registry.register(
            "neural_prosody",
            self.neural_prosody_handler,
            "Wav2Vec 2.0 based semantic prosody analysis",
        )
        registry.register(
            "audio_gen_signature",
            self.audio_gen_signature_handler,
            "Generative audio artifact signature analysis",
        )

    # ── Refinement: Neural Prosody ────────────────────────────────────────────

    async def neural_prosody_handler(self, input_data: dict) -> dict:
        """Neural prosody analysis. Falls back to acoustic prosody."""
        artifact = input_data.get("artifact") or await self._audio_artifact()

        try:
            result = await run_ml_tool(
                "neural_prosody_classifier.py", artifact.file_path, timeout=15.0
            )
            if not result.get("error") and result.get("available"):
                await self.agent._record_tool_result("neural_prosody", result)
                return result
        except Exception as exc:
            logger.warning("Neural prosody execution failed", error=str(exc))

        # Fallback — record result from prosody_analysis_handler
        fallback = await self.prosody_analysis_handler(input_data)
        fallback["degraded"] = True
        fallback["fallback_reason"] = (
            "neural_prosody_classifier failed; used acoustic prosody analysis"
        )

        # Ensure fallback path is recorded in metrics
        await self.agent._record_tool_result("neural_prosody", fallback)
        return fallback

    # ── Refinement: Audio Gen Signature ──────────────────────────────────────

    async def audio_gen_signature_handler(self, input_data: dict) -> dict:
        """Detection of spectral artifacts specific to generative TTS engines."""
        artifact = input_data.get("artifact") or await self._audio_artifact()
        result = await run_ml_tool(
            "audio_gen_signature_scanner.py", artifact.file_path, timeout=10.0
        )
        if not result.get("error") and result.get("available"):
            result.setdefault("is_ai_generated", bool(result.get("synthetic_detected")))
            result.setdefault(
                "verdict", "LIKELY_SYNTHETIC" if result.get("is_ai_generated") else "NATURAL"
            )
            result.setdefault("court_defensible", True)
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
        artifact = input_data.get("artifact") or await self._audio_artifact()
        min_speakers = input_data.get("min_speakers", 1)
        max_speakers = input_data.get("max_speakers", 10)
        await self.agent.update_sub_task("Establishing voice count baseline...")
        try:
            result = await real_speaker_diarize(
                artifact=artifact,
                min_speakers=min_speakers,
                max_speakers=max_speakers,
                progress_callback=self.agent.update_sub_task,
            )
        except Exception as exc:
            logger.warning(
                "Speaker diarization primary path failed; using heuristic fallback",
                error=str(exc),
            )
            result = {
                "error": str(exc),
                "available": False,
                "degraded": True,
            }
        if result.get("error") or result.get("available") is False:
            result = await self._diarization_fallback(
                artifact.file_path, min_speakers, max_speakers
            )
        else:
            result.setdefault("available", True)
            result.setdefault("court_defensible", True)
            result.setdefault("confidence", 0.85)
        if result.get("analysis_source") == "librosa_spectral_fallback":
            result.setdefault("available", True)
            result.setdefault("degraded", True)
            result.setdefault("court_defensible", False)
            result.setdefault("confidence", 0.50)
            result.setdefault(
                "fallback_reason",
                "SpeechBrain diarization unavailable; used librosa spectral-energy clustering",
            )
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
        artifact = input_data.get("artifact") or await self._audio_artifact()
        try:
            result = await real_anti_spoofing_detect(
                artifact=artifact, progress_callback=self.agent.update_sub_task
            )
        except Exception as exc:
            result = {"error": str(exc), "degraded": True, "available": False, "confidence": 0.0}
        if not result.get("error"):
            result.setdefault("available", True)
            result.setdefault("court_defensible", True)
            result.setdefault("is_spoofed", bool(result.get("spoof_detected")))
            result.setdefault(
                "verdict", "LIKELY_SPOOFED" if result.get("is_spoofed") else "GENUINE"
            )
        # Store under the registered tool name
        await self.agent._record_tool_result("anti_spoofing_detect", result)
        return result

    async def prosody_analysis_handler(self, input_data: dict) -> dict:
        """Acoustic prosody analysis (pitch, jitter, shimmer via Praat/librosa)."""
        artifact = input_data.get("artifact") or await self._audio_artifact()
        result = await real_prosody_analyze(artifact=artifact)
        anomalies = result.get("anomalies") if isinstance(result, dict) else None
        if isinstance(anomalies, list):
            result.setdefault("anomaly_count", len(anomalies))
            result.setdefault("prosody_anomaly", len(anomalies) > 0)
        result.setdefault("available", True)
        result.setdefault("court_defensible", True)
        await self.agent._record_tool_result("prosody_analyze", result)
        return result

    async def audio_splice_detect_handler(self, input_data: dict) -> dict:
        """MFCC IsolationForest splice point detection (sync — runs in executor)."""
        artifact = input_data.get("artifact") or await self._audio_artifact()
        loop = asyncio.get_running_loop()
        await self.agent.update_sub_task("Tracing isolation forest splice points...")
        result = await loop.run_in_executor(None, detect_audio_splices, artifact.file_path)
        result.setdefault("available", not bool(result.get("error")))
        result.setdefault("court_defensible", True)
        await self.agent._record_tool_result("audio_splice_detect", result)
        return result

    async def background_noise_analysis_handler(self, input_data: dict) -> dict:
        """Background noise floor consistency analysis."""
        artifact = input_data.get("artifact") or await self._audio_artifact()
        result = await real_background_noise_consistency(artifact=artifact)
        shift_points = result.get("shift_points") if isinstance(result, dict) else None
        result.setdefault("shift_detected", result.get("consistent") is False or bool(shift_points))
        result.setdefault("available", True)
        result.setdefault("court_defensible", True)
        result.setdefault("confidence", 0.70 if result.get("shift_detected") else 0.85)
        await self.agent._record_tool_result("background_noise_analysis", result)
        return result

    async def codec_fingerprinting_handler(self, input_data: dict) -> dict:
        """Codec chain re-encoding event fingerprinting."""
        artifact = input_data.get("artifact") or await self._audio_artifact()
        try:
            result = await real_codec_fingerprint(artifact=artifact)
        except Exception as exc:
            logger.warning(
                "Codec fingerprint primary path failed; using container metadata fallback",
                error=str(exc),
            )
            result = self._codec_fingerprint_fallback(artifact.file_path, str(exc))
        events = result.get("reencoding_events") if isinstance(result, dict) else None
        result.setdefault("re_encoding_detected", bool(events))
        result.setdefault("reencoding_event_count", len(events) if isinstance(events, list) else 0)
        format_info = result.get("format_info") if isinstance(result, dict) else {}
        if isinstance(format_info, dict):
            result.setdefault("sample_rate", format_info.get("samplerate"))
            result.setdefault("channels", format_info.get("channels"))
            result.setdefault("duration_seconds", format_info.get("duration"))
            codec_chain = result.get("codec_chain") or []
            if isinstance(codec_chain, list) and codec_chain:
                result.setdefault("codec", codec_chain[0])
        result.setdefault("available", True)
        result.setdefault("court_defensible", True)
        if "confidence" not in result:
            event_confidences = [
                float(event.get("confidence", 0.0) or 0.0)
                for event in events or []
                if isinstance(event, dict)
            ]
            result["confidence"] = max(event_confidences) if event_confidences else 0.85
        await self.agent._record_tool_result("codec_fingerprinting", result)
        return result

    def _codec_fingerprint_fallback(self, file_path: str, error_msg: str) -> dict:
        """SoundFile-only codec fallback when librosa/numba analysis is unavailable."""
        try:
            info = sf.info(file_path)
            ext = str(file_path).rsplit(".", 1)[-1].lower() if "." in str(file_path) else ""
            codec_by_ext = {
                "wav": "PCM",
                "mp3": "MP3",
                "m4a": "AAC",
                "mp4": "AAC",
                "aac": "AAC",
                "flac": "FLAC",
                "ogg": "Vorbis",
                "oga": "Vorbis",
            }
            codec = codec_by_ext.get(ext, f"Unknown ({ext or 'no extension'})")
            return {
                "reencoding_events": [],
                "codec_chain": [codec],
                "format_info": {
                    "format": info.format,
                    "subtype": info.subtype,
                    "channels": info.channels,
                    "samplerate": info.samplerate,
                    "duration": info.duration,
                    "frames": info.frames,
                },
                "available": True,
                "degraded": True,
                "court_defensible": False,
                "confidence": 0.65,
                "fallback_reason": f"Full codec fingerprint failed ({error_msg}); used container metadata only.",
            }
        except Exception as exc:
            return {
                "reencoding_events": [],
                "codec_chain": [],
                "available": False,
                "degraded": True,
                "court_defensible": False,
                "confidence": 0.0,
                "error": f"Codec fallback failed: {exc}",
                "fallback_reason": error_msg,
            }

    async def audio_visual_sync_handler(self, input_data: dict) -> dict:
        """Audio-visual synchronisation verification."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        result = await real_av_sync_verify(artifact=artifact)
        if not result.get("error") and result.get("available") is not False:
            result.setdefault("available", True)
            result.setdefault("court_defensible", True)
            result.setdefault("confidence", 0.82 if result.get("av_sync") == "IN_SYNC" else 0.55)
        await self.agent._record_tool_result("audio_visual_sync", result)
        return result

    async def voice_clone_detect_handler(self, input_data: dict) -> dict:
        """Voice clone / AI speech synthesis detection via subprocess."""
        artifact = input_data.get("artifact") or await self._audio_artifact()
        # Run as managed subprocess — avoids the Python startup cost on repeat calls
        # and keeps heavy SpeechBrain/librosa imports out of the main process.
        result = await run_ml_tool(
            "voice_clone_detector.py",
            artifact.file_path,
            timeout=30.0,
            model=self.agent.config.voice_clone_model_name,
        )
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
        artifact = input_data.get("artifact") or await self._audio_artifact()
        loop = asyncio.get_running_loop()
        await self.agent.update_sub_task("Analyzing electrical network frequency grid...")
        result = await loop.run_in_executor(None, analyze_enf, artifact.file_path)
        result.setdefault("available", not bool(result.get("error")))
        result.setdefault("court_defensible", True)
        await self.agent._record_tool_result("enf_analysis", result)
        return result
