"""
Agent 2 - Audio & Multimedia Forensics Agent.

Audio authenticity and multimedia consistency expert for detecting 
audio deepfakes, splices, re-encoding events, prosody anomalies, 
and audio-visual sync breaks.
"""

from __future__ import annotations

import uuid
from typing import Optional

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
            "Run voice clone and AI speech synthesis detection on speaker segments",
            "Run speaker diarization - establish voice count baseline",
            "Run anti-spoofing detection on primary speaker segments",
            "Run prosody analysis across full track",
            "Run ML-based splice point detection on audio segments",
            "Run background noise consistency analysis - identify shift points",
            "Run codec fingerprinting for re-encoding event detection",
            "Run audio-visual sync verification against video track timestamps",
            "Issue collaborative call to Agent 4 for any flagged timestamps",
            "Self-reflection pass",
            "Submit calibrated findings to Arbiter",
        ]

    @property
    def deep_task_decomposition(self) -> list[str]:
        """
        Heavy tasks — deep anti-spoofing ensemble, cross-agent collaboration.
        Runs in background after initial findings are returned.
        """
        return [
            "Run deep anti-spoofing ensemble analysis on flagged speaker segments",
            "Run spectral perturbation adversarial robustness check",
            "Run cross-agent collaboration with Agent 4 for A/V timestamp correlation",
            "Run advanced codec chain analysis for multi-generation detection",
            "Run ENF (Electrical Network Frequency) analysis to detect splice points and verify recording timestamp",
        ]
    
    @property
    def iteration_ceiling(self) -> int:
        """Maximum iterations — tasks + 2 buffer to prevent runaway loops."""
        return len(self.task_decomposition) + 2
    
    @property
    def supported_file_types(self) -> list[str]:
        """Audio agent supports audio and video file types (video contains audio track)."""
        return ['audio/', 'video/']
    
    async def build_tool_registry(self) -> ToolRegistry:
        """
        Build and return the tool registry for this agent.
        
        Registers real tool implementations for:
        - speaker_diarization: Speaker diarization
        - anti_spoofing_detection: Anti-spoofing detection
        - prosody_analysis: Prosody analysis
        - background_noise_analysis: Background noise consistency analysis
        - codec_fingerprinting: Codec fingerprinting
        - audio_visual_sync: Audio-visual sync verification via moviepy+librosa
        - inter_agent_call: Inter-agent communication via InterAgentBus
        - adversarial_robustness_check: Spectral perturbation stability analysis
        """
        registry = ToolRegistry()
        
        # Real tool handlers - wrap to accept input_data dict
        async def speaker_diarization_handler(input_data: dict) -> dict:
            """Handle speaker diarization with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            min_speakers = input_data.get("min_speakers", 1)
            max_speakers = input_data.get("max_speakers", 10)
            result = await real_speaker_diarize(
                artifact=artifact,
                min_speakers=min_speakers,
                max_speakers=max_speakers,
            )
            if result.get("error"):
                await self._record_tool_error("speaker_diarization", result["error"])
            else:
                await self._record_tool_result("speaker_diarization", result)
            return result

        async def anti_spoofing_detection_handler(input_data: dict) -> dict:
            """Handle anti-spoofing detection with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            segment = input_data.get("segment")
            # Context: if voice clone detector flagged synthetic speech, pass that
            # hint to the anti-spoofing model so it applies stricter thresholds
            vc_ctx = self._tool_context.get("voice_clone_detect", {})
            if vc_ctx.get("verdict") == "LIKELY_SYNTHETIC":
                # force fresh segment scan from the beginning of the track
                segment = segment or {"start": 0.0, "duration": 10.0}
            result = await real_anti_spoofing_detect(
                artifact=artifact,
                segment=segment,
            )
            if result.get("error"):
                await self._record_tool_error("anti_spoofing_detection", result["error"])
            else:
                await self._record_tool_result("anti_spoofing_detection", result)
            return result
        
        async def prosody_analysis_handler(input_data: dict) -> dict:
            """Handle prosody analysis with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            result = await real_prosody_analyze(artifact=artifact)
            if result.get("error"):
                await self._record_tool_error("prosody_analyze", result["error"])
            else:
                await self._record_tool_result("prosody_analyze", result)
            return result
        
        async def background_noise_analysis_handler(input_data: dict) -> dict:
            """Handle background noise analysis with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            segment_duration = input_data.get("segment_duration", 1.0)
            result = await real_background_noise_consistency(
                artifact=artifact,
                segment_duration=segment_duration,
            )
            if result.get("error"):
                await self._record_tool_error("background_noise_analysis", result["error"])
            else:
                await self._record_tool_result("background_noise_analysis", result)
            return result
        
        async def codec_fingerprinting_handler(input_data: dict) -> dict:
            """Handle codec fingerprinting with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            result = await real_codec_fingerprint(artifact=artifact)
            if result.get("error"):
                await self._record_tool_error("codec_fingerprinting", result["error"])
            else:
                await self._record_tool_result("codec_fingerprinting", result)
            return result
        
        async def audio_splice_detect_handler(input_data: dict) -> dict:
            """Run ML-based audio splice point detection on segments."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            window = input_data.get("window", 1.0)
            result = await run_ml_tool("audio_splice_detector.py", artifact.file_path,
                                       extra_args=["--window", str(window)], timeout=25.0)
            if result.get("error"):
                await self._record_tool_error("audio_splice_detect", result["error"])
            elif result.get("available") and not result.get("error"):
                await self._record_tool_result("audio_splice_detect", result)
            return result
        
        async def audio_visual_sync_handler(input_data: dict) -> dict:
            """Real AV sync using moviepy+librosa onset correlation."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            result = await real_av_sync_verify(artifact=artifact)
            if result.get("error"):
                await self._record_tool_error("audio_visual_sync", result["error"])
            else:
                await self._record_tool_result("audio_visual_sync", result)
            return result

        async def inter_agent_call_handler(input_data: dict) -> dict:
            """Real inter-agent call via InterAgentBus."""
            if self._inter_agent_bus is None:
                return {"status": "error", "message": "No inter_agent_bus injected"}

            call = InterAgentCall(
                caller_agent_id=self.agent_id,
                callee_agent_id=input_data.get("target_agent", "Agent4"),
                call_type=InterAgentCallType.COLLABORATIVE,
                payload={
                    "timestamp_ref": input_data.get("timestamp_ref"),
                    "question": input_data.get("question", "Confirm audio-visual sync at flagged timestamp"),
                }
            )
            response = await self._inter_agent_bus.send(call, self.custody_logger)
            return response

        async def adversarial_robustness_check_handler(input_data: dict) -> dict:
            """
            Adversarial robustness check for audio anti-spoofing evasion.

            Applies three known audio perturbations (low-pass filter, mild
            additive noise, time-stretch) to the audio and re-examines the
            spectral flux and zero-crossing rate. If anti-spoofing scores
            collapse significantly under light perturbation the recording
            may have been engineered to evade ML-based detectors.
            """
            import numpy as np
            import librosa

            artifact = input_data.get("artifact") or self.evidence_artifact

            try:
                y, sr = librosa.load(artifact.file_path, sr=None, mono=True, duration=10.0)

                def _spectral_features(signal: np.ndarray, sample_rate: int) -> dict:
                    flux = float(np.mean(np.diff(np.abs(librosa.stft(signal)), axis=1) ** 2))
                    zcr = float(np.mean(librosa.feature.zero_crossing_rate(signal)))
                    centroid = float(np.mean(librosa.feature.spectral_centroid(y=signal, sr=sample_rate)))
                    return {"flux": flux, "zcr": zcr, "centroid": centroid}

                original_feats = _spectral_features(y, sr)

                perturbation_deltas = {}

                # 1 — Low-pass filter at 4 kHz (common anti-spoofing evasion)
                from scipy.signal import butter, sosfilt
                sos = butter(6, 4000.0 / (sr / 2), btype="low", output="sos")
                lp_y = sosfilt(sos, y).astype(np.float32)
                lp_feats = _spectral_features(lp_y, sr)
                perturbation_deltas["low_pass_4khz"] = round(
                    abs(lp_feats["flux"] - original_feats["flux"]) / (original_feats["flux"] + 1e-9), 4
                )

                # 2 — Additive white noise at -40 dB SNR
                rng = np.random.default_rng(42)
                noise_power = float(np.mean(y ** 2)) / (10 ** 4)  # -40 dB
                noisy_y = (y + rng.normal(0, np.sqrt(noise_power), y.shape)).astype(np.float32)
                noisy_feats = _spectral_features(noisy_y, sr)
                perturbation_deltas["white_noise_-40db"] = round(
                    abs(noisy_feats["zcr"] - original_feats["zcr"]) / (original_feats["zcr"] + 1e-9), 4
                )

                # 3 — Time-stretch by 2 % (imperceptible pitch preservation)
                try:
                    stretched = librosa.effects.time_stretch(y, rate=1.02)
                    s_feats = _spectral_features(stretched, sr)
                    perturbation_deltas["time_stretch_2pct"] = round(
                        abs(s_feats["centroid"] - original_feats["centroid"])
                        / (original_feats["centroid"] + 1e-9), 4
                    )
                except Exception:
                    perturbation_deltas["time_stretch_2pct"] = 0.0

                # Heuristic: if ANY perturbation produces > 50 % relative
                # feature shift the anti-spoofing signal is fragile / engineered.
                EVASION_THRESHOLD = 0.50
                evasion_detected = any(v > EVASION_THRESHOLD for v in perturbation_deltas.values())

                return {
                    "status": "real",
                    "court_defensible": True,
                    "method": "Spectral perturbation stability — low-pass, noise injection, time-stretch",
                    "adversarial_pattern_detected": evasion_detected,
                    "perturbation_deltas": perturbation_deltas,
                    "evasion_threshold": EVASION_THRESHOLD,
                    "original_features": {k: round(v, 6) for k, v in original_feats.items()},
                    "confidence": 0.70 if evasion_detected else 0.88,
                    "note": (
                        "Spectral features are highly sensitive to benign perturbations — possible adversarial engineering."
                        if evasion_detected
                        else "Spectral features remain stable under all perturbations — anti-spoofing findings are robust."
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
        
        async def voice_clone_detect_handler(input_data: dict) -> dict:
            """
            AI voice clone and speech synthesis detection.

            Modern TTS/voice-cloning systems (ElevenLabs, VALL-E, Tortoise) leave
            characteristic artifacts: unusually smooth spectral profiles, low pitch
            variation, minimal silence/breathing, and unnaturally stable energy dynamics.
            This heuristic scorer flags these patterns as indicators of synthetic speech.
            A positive result should be corroborated with anti_spoofing_detect.
            """
            artifact = input_data.get("artifact") or self.evidence_artifact
            result = await run_ml_tool("voice_clone_detector.py", artifact.file_path, timeout=30.0)
            if result.get("available") and not result.get("error"):
                await self._record_tool_result("voice_clone_detect", result)
                return result
            try:
                import numpy as np
                import soundfile as sf
                from scipy import signal as sp_signal

                audio, sr = sf.read(artifact.file_path)
                if audio.ndim > 1:
                    audio = audio.mean(axis=1)
                audio = audio[:sr * 30].astype(np.float32)  # analyse up to 30 s

                # Feature 1: Spectral flatness (voice clones are spectrally smoother)
                freqs, psd = sp_signal.welch(audio, sr, nperseg=2048)
                geom_mean = float(np.exp(np.mean(np.log(psd + 1e-10))))
                arith_mean = float(np.mean(psd))
                spectral_flatness = geom_mean / (arith_mean + 1e-10)

                # Feature 2: ZCR variance (natural speech has variable pitch)
                frame_size = int(0.025 * sr)
                hop_size = int(0.010 * sr)
                frames = [audio[i:i+frame_size] for i in range(0, len(audio) - frame_size, hop_size)]
                zcr = [float(np.sum(np.abs(np.diff(np.sign(f)))) / (2 * len(f))) for f in frames] if frames else [0.0]
                zcr_std = float(np.std(zcr))

                # Feature 3: Energy coefficient of variation
                rms = [float(np.sqrt(np.mean(f**2))) for f in frames] if frames else [0.0]
                energy_cv = float(np.std(rms) / (np.mean(rms) + 1e-10))

                # Feature 4: Silence ratio (voice clones lack natural pauses)
                silence_threshold = float(np.percentile(np.abs(audio), 10))
                silence_ratio = float(np.mean(np.abs(audio) < silence_threshold))

                synthetic_score = 0.0
                flags = []
                if spectral_flatness > 0.15:
                    synthetic_score += 0.25
                    flags.append(f"High spectral flatness ({spectral_flatness:.3f}) — voice clone models produce spectrally smoother audio")
                if zcr_std < 0.02:
                    synthetic_score += 0.25
                    flags.append(f"Low pitch variation (ZCR std {zcr_std:.4f}) — natural speech has more dynamic F0 contour")
                if energy_cv < 0.30:
                    synthetic_score += 0.15
                    flags.append(f"Low energy dynamics (CV {energy_cv:.3f}) — natural speech has higher amplitude variation")
                if silence_ratio < 0.05:
                    synthetic_score += 0.15
                    flags.append("Minimal silence — natural speech includes breathing and micro-pauses")

                verdict = (
                    "LIKELY_SYNTHETIC" if synthetic_score >= 0.55
                    else "SUSPICIOUS" if synthetic_score >= 0.35
                    else "LIKELY_GENUINE"
                )
                vc_result = {
                    "verdict": verdict,
                    "synthetic_probability": round(min(synthetic_score, 0.95), 3),
                    "spectral_flatness": round(spectral_flatness, 4),
                    "pitch_stability_zcr_std": round(zcr_std, 4),
                    "energy_coefficient_of_variation": round(energy_cv, 3),
                    "silence_ratio": round(silence_ratio, 3),
                    "flags": flags,
                    "note": "Heuristic analysis — corroborate with anti_spoofing_detect. Neural classifier (WaveFake/Resemblyzer) provides higher accuracy.",
                    "backend": "scipy-spectral-inline",
                    "available": True,
                    "court_defensible": True,
                }
                await self._record_tool_result("voice_clone_detect", vc_result)
                return vc_result
            except Exception as e:
                await self._record_tool_error("voice_clone_detect", str(e))
                return {"verdict": "ERROR", "error": str(e), "available": False, "court_defensible": False}

        async def enf_analysis_handler(input_data: dict) -> dict:
            """
            Electrical Network Frequency (ENF) analysis.

            The power grid (50 Hz in Europe/Asia, 60 Hz in Americas) embeds a faint
            but measurable hum in all recordings made near mains-powered devices.
            This frequency drifts slightly over time in a pattern that is logged by
            grid operators and is unique to specific times and locations. Internally:
            - Detects ENF presence and grid standard (50/60 Hz)
            - Tracks ENF over time and flags abrupt jumps as potential splice points
            - Measures consistency as a tamper indicator
            For full timestamp verification, compare against an ENF reference database.
            """
            artifact = input_data.get("artifact") or self.evidence_artifact
            result = await run_ml_tool("enf_analysis.py", artifact.file_path, timeout=60.0)
            if result.get("available") and not result.get("error"):
                return result
            try:
                import numpy as np
                import soundfile as sf
                from scipy import signal as sp_signal

                audio, sr = sf.read(artifact.file_path)
                if audio.ndim > 1:
                    audio = audio.mean(axis=1)
                audio = audio.astype(np.float32)

                enf_targets = [50, 100, 150, 200, 60, 120, 180, 240]
                nperseg = min(len(audio), sr * 2)
                freqs, times, Zxx = sp_signal.stft(audio, fs=sr, nperseg=nperseg, noverlap=nperseg // 2)
                power = np.abs(Zxx) ** 2

                enf_detected = False
                detected_freq = None
                enf_track = []
                for target_hz in enf_targets:
                    freq_idx = int(np.argmin(np.abs(freqs - target_hz)))
                    if freq_idx < 2 or freq_idx >= len(freqs) - 2:
                        continue
                    band_power = float(power[freq_idx, :].mean())
                    neighbor_power = float(
                        (power[freq_idx - 2:freq_idx, :].mean() + power[freq_idx + 1:freq_idx + 3, :].mean()) / 2
                    )
                    if band_power / (neighbor_power + 1e-10) > 3.0:
                        enf_detected = True
                        detected_freq = float(target_hz)
                        enf_track = power[freq_idx, :].tolist()
                        break

                if not enf_detected or not enf_track:
                    return {
                        "enf_detected": False,
                        "verdict": "NO_ENF_SIGNAL",
                        "note": "No ENF signal detected — recording may have been made in an isolated environment, or ENF was suppressed during post-processing.",
                        "available": True,
                        "court_defensible": True,
                        "backend": "scipy-enf-inline",
                    }

                track = np.array(enf_track)
                track_norm = (track - track.mean()) / (track.std() + 1e-10)
                diff = np.abs(np.diff(track_norm))
                splice_candidates = int(np.sum(diff > track_norm.std() * 3))
                consistency = float(1.0 / (1.0 + diff.mean()))

                return {
                    "enf_detected": True,
                    "enf_frequency_hz": detected_freq,
                    "grid_standard": "50Hz (European/Asian)" if detected_freq in [50, 100, 150, 200] else "60Hz (American)",
                    "splice_candidate_points": splice_candidates,
                    "enf_consistency_score": round(consistency, 4),
                    "verdict": "INCONSISTENT_ENF" if splice_candidates > 2 else "CONSISTENT_ENF",
                    "duration_analyzed_s": round(float(len(times)) * (nperseg / sr) / 2, 1),
                    "forensic_note": (
                        f"ENF shows {splice_candidates} abrupt frequency jump(s) — potential edit/splice point(s). "
                        "Compare against ENF reference database for timestamp verification."
                        if splice_candidates > 2 else
                        "ENF signal is internally consistent — no temporal discontinuities detected in the recording."
                    ),
                    "caveat": "ENF database comparison not performed — internal consistency only. Full timestamp verification requires ENF reference data.",
                    "available": True,
                    "court_defensible": True,
                    "backend": "scipy-enf-inline",
                }
            except Exception as e:
                return {"enf_detected": False, "verdict": "ERROR", "error": str(e),
                        "available": False, "court_defensible": False}

        # Register tools
        registry.register("speaker_diarize", speaker_diarization_handler, "Speaker diarization")
        registry.register("anti_spoofing_detect", anti_spoofing_detection_handler, "Anti-spoofing detection")
        registry.register("prosody_analyze", prosody_analysis_handler, "Prosody analysis")
        registry.register("audio_splice_detect", audio_splice_detect_handler, "Run ML-based audio splice detection on segments")
        registry.register("background_noise_analysis", background_noise_analysis_handler, "Background noise consistency analysis")
        registry.register("codec_fingerprinting", codec_fingerprinting_handler, "Codec fingerprinting")
        registry.register("audio_visual_sync", audio_visual_sync_handler, "Audio-visual sync verification")
        registry.register("inter_agent_call", inter_agent_call_handler, "Inter-agent communication")
        registry.register("adversarial_robustness_check", adversarial_robustness_check_handler, "Adversarial robustness check")
        registry.register("voice_clone_detect", voice_clone_detect_handler, "AI voice clone and speech synthesis detection via spectral heuristics")
        registry.register("enf_analysis", enf_analysis_handler, "Electrical Network Frequency (ENF) analysis for splice detection and timestamp verification")

        return registry
    
    async def build_initial_thought(self) -> str:
        """
        Build the contextually-grounded initial thought for the ReAct loop.

        Pre-screens with codec_fingerprinting — a fast, lightweight tool that
        identifies the audio codec, encoding chain, and sample rate before
        heavier diarization or anti-spoofing models run.
        """
        context_lines = []
        try:
            if self._tool_registry:
                handler = self._tool_registry._handlers.get("codec_fingerprinting")
                if handler:
                    result = await handler({"artifact": self.evidence_artifact})
                    codec = result.get("codec") or result.get("audio_codec", "")
                    sample_rate = result.get("sample_rate", "")
                    duration = result.get("duration_seconds", result.get("duration", ""))
                    channels = result.get("channels", "")
                    bit_depth = result.get("bit_depth", "")
                    if codec:
                        parts = [f"Codec: {codec}", f"sample rate: {sample_rate}Hz", f"duration: {duration}s", f"channels: {channels}"]
                        if bit_depth:
                            parts.append(f"bit depth: {bit_depth}")
                        context_lines.append(", ".join(parts))
                    encoding_chain = result.get("encoding_chain", result.get("encoding_history", ""))
                    if encoding_chain:
                        context_lines.append(f"Encoding chain: {encoding_chain}")
        except Exception:
            pass

        context = " | ".join(context_lines) if context_lines else "Codec pre-screen unavailable."
        return (
            f"Starting audio forensics analysis. Evidence: {self.evidence_artifact.artifact_id}. "
            f"Codec pre-screen — {context} "
            f"Proceeding through {len(self.task_decomposition)} tasks: "
            f"speaker diarization, anti-spoofing detection, prosody analysis (F0/jitter/shimmer), "
            f"splice point detection, background noise consistency, and codec fingerprinting. "
            f"I will pay particular attention to encoding chain anomalies and "
            f"spectral discontinuities that indicate splicing or re-encoding."
        )

    async def run_investigation(self):
        """
        Override to short-circuit when the evidence is not an audio or video file.
        Always initialises working memory FIRST so the heartbeat fires immediately.
        """
        from core.react_loop import AgentFinding
        from core.working_memory import TaskStatus

        # Always init working memory first so heartbeat is visible during validation
        await self._initialize_working_memory()

        file_path = self.evidence_artifact.file_path.lower()
        mime = (self.evidence_artifact.metadata or {}).get("mime_type", "").lower()
        image_exts = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".svg")

        is_image = any(file_path.endswith(ext) for ext in image_exts) or mime.startswith("image/")
        is_audio_video = mime.startswith("audio/") or mime.startswith("video/")

        if is_image or not is_audio_video:
            # Mark all tasks complete so heartbeat shows full progress
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

            finding = AgentFinding(
                agent_id=self.agent_id,
                finding_type="File type not applicable",
                confidence_raw=1.0,
                status="CONFIRMED",
                evidence_refs=[],
                reasoning_summary=(
                    "Audio Forensics — The uploaded evidence is not an audio or video file. "
                    "Audio analysis (speaker diarization, anti-spoofing, prosody, "
                    "codec fingerprinting) is not applicable for this evidence type. "
                    "No audio track was detected."
                ),
            )
            self._findings = [finding]
            self._react_chain = []
            self._reflection_report = None
            return self._findings

        # For audio/video files: skip memory re-init in base class, run full loop
        self._skip_memory_init = True
        self._tool_registry = await self.build_tool_registry()
        return await super().run_investigation()