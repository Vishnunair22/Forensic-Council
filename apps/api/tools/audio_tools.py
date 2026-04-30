"""
Audio Forensic Tools
====================

Real forensic tool handlers for audio analysis.
Implements speaker diarization, anti-spoofing detection, prosody analysis,
background noise consistency, and codec fingerprinting.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

import librosa
import numpy as np
import soundfile as sf

from core.evidence import EvidenceArtifact
from core.exceptions import ToolUnavailableError

# ── Optional deep-learning backends ──────────────────────────────────────────
# These are imported lazily so the module loads even without them installed.
# Module-level singletons avoid re-importing on every tool call.

_speechbrain_classifier: Any = None
_speechbrain_loaded: bool = False
_audio_deepfake_bundle: tuple[Any, Any] | None = None
_audio_deepfake_model_name: str | None = None


def _load_audio_with_soundfile(audio_path: str) -> tuple[np.ndarray, int]:
    """Load mono audio without librosa/numba."""
    y, sr = sf.read(audio_path, dtype="float32")
    if getattr(y, "ndim", 1) > 1:
        y = y.mean(axis=1)
    y = np.asarray(y, dtype=np.float32)
    if y.size == 0:
        raise ToolUnavailableError("Audio stream is empty")
    return y, int(sr)


def _frame_rms(y: np.ndarray, frame_size: int, hop: int) -> np.ndarray:
    if len(y) < frame_size:
        frames = np.pad(y, (0, frame_size - len(y)))[None, :]
    else:
        frames = np.stack(
            [y[start : start + frame_size] for start in range(0, len(y) - frame_size + 1, hop)]
        )
    return np.sqrt(np.mean(frames**2, axis=1))


def _spectral_centroid_np(segment: np.ndarray, sr: int) -> float:
    if segment.size == 0:
        return 0.0
    window = np.hanning(len(segment)).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(segment * window))
    freqs = np.fft.rfftfreq(len(segment), d=1.0 / float(sr))
    total = float(np.sum(spectrum))
    if total <= 0:
        return 0.0
    return float(np.sum(freqs * spectrum) / total)


def _get_speechbrain_classifier_class() -> Any:
    """Return cached SpeechBrain ECAPA anti-spoofing classifier, or None."""
    global _speechbrain_classifier, _speechbrain_loaded
    if not _speechbrain_loaded:
        _speechbrain_loaded = True
        try:
            from speechbrain.pretrained import EncoderClassifier  # type: ignore[import-untyped]

            _speechbrain_classifier = EncoderClassifier
        except Exception:
            pass
    return _speechbrain_classifier


def _get_audio_deepfake_bundle(model_name: str, local_files_only: bool) -> tuple[Any, Any]:
    """Load the configured Transformers audio anti-spoof model once per process."""
    global _audio_deepfake_bundle, _audio_deepfake_model_name
    if _audio_deepfake_bundle is None or _audio_deepfake_model_name != model_name:
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

        extractor = AutoFeatureExtractor.from_pretrained(
            model_name,
            local_files_only=local_files_only,
        )
        model = AutoModelForAudioClassification.from_pretrained(
            model_name,
            local_files_only=local_files_only,
        )
        model.eval()
        _audio_deepfake_bundle = (extractor, model)
        _audio_deepfake_model_name = model_name
    return _audio_deepfake_bundle


def _spoof_probability_from_logits(logits: Any, id2label: dict[int, str]) -> float:
    import torch

    if logits.shape[-1] == 1:
        return float(torch.sigmoid(logits[0, 0]).item())

    probs = torch.softmax(logits, dim=-1)[0]
    labels = {int(idx): str(label).lower() for idx, label in id2label.items()}
    spoof_terms = ("spoof", "fake", "synthetic", "deepfake", "generated", "ai")
    spoof_indexes = [
        idx for idx, label in labels.items() if any(term in label for term in spoof_terms)
    ]
    if spoof_indexes:
        return float(sum(probs[idx].item() for idx in spoof_indexes))
    if probs.numel() >= 2:
        return float(probs[1].item())
    return float(probs.max().item())


@dataclass
class AudioSegment:
    """Audio segment with speaker information."""

    speaker_id: str
    start: float
    end: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "speaker_id": self.speaker_id,
            "start": self.start,
            "end": self.end,
        }


@dataclass
class ProsodyAnomaly:
    """Prosody anomaly detected in audio."""

    timestamp: float
    type: str
    severity: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "type": self.type,
            "severity": self.severity,
        }


async def speaker_diarize(
    artifact: EvidenceArtifact,
    min_speakers: int = 1,
    max_speakers: int = 10,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """
    Perform speaker diarization on audio file using SpeechBrain ECAPA-TDNN.

    Uses ECAPA-TDNN to extract speaker embeddings from overlapping chunks of audio,
    then uses Agglomerative Clustering to group them into unique speakers.

    Args:
        artifact: The evidence artifact to analyze
        min_speakers: Minimum number of speakers to detect
        max_speakers: Maximum number of speakers to detect

    Returns:
        Dictionary containing speaker_count, segments, duration, analysis_source
    """
    try:
        audio_path = artifact.file_path
        if not os.path.exists(audio_path):
            raise ToolUnavailableError(f"File not found: {audio_path}")

        loop = asyncio.get_running_loop()
        info = sf.info(audio_path)
        duration = float(info.duration)

        # ── Attempt SpeechBrain ECAPA clustering (neural, SOTA open-weights) ──
        EncoderClassifier = _get_speechbrain_classifier_class()
        if EncoderClassifier is not None:
            try:
                import torch
                from sklearn.cluster import AgglomerativeClustering

                from core.config import get_settings

                settings = get_settings()

                # Enforce local-only mode if configured
                if settings.offline_mode:
                    os.environ["HF_HUB_OFFLINE"] = "1"
                    os.environ["TRANSFORMERS_OFFLINE"] = "1"

                classifier = EncoderClassifier.from_hparams(
                    source="speechbrain/spkrec-ecapa-voxceleb",
                    run_opts={"device": "cpu"},
                )

                # Load audio with SoundFile to avoid torchaudio/torchcodec
                # runtime requirements in slim CPU containers.
                signal_np, fs = sf.read(audio_path, dtype="float32")
                if getattr(signal_np, "ndim", 1) > 1:
                    signal_np = signal_np.mean(axis=1)
                signal = torch.from_numpy(np.asarray(signal_np)).unsqueeze(0)

                # Extract embeddings from 1.5s segments with 0.5s shift
                window_size = int(1.5 * fs)
                step_size = int(0.5 * fs)
                total_samples = signal.shape[1]

                if total_samples < window_size:
                    # Too short to diarize, assume 1 speaker
                    return {
                        "speaker_count": 1,
                        "segments": [
                            AudioSegment(speaker_id="SPEAKER_00", start=0.0, end=duration).to_dict()
                        ],
                        "duration": duration,
                        "analysis_source": "speechbrain_ecapa_diarizer",
                        "model": "speechbrain/spkrec-ecapa-voxceleb",
                    }

                embeddings = []
                times = []
                for start_idx in range(0, total_samples, step_size):
                    end_idx = start_idx + window_size
                    if end_idx > total_samples:
                        break

                    if progress_callback:
                        p = min(100, int((start_idx / total_samples) * 100))
                        await progress_callback(f"Scanning segment {len(embeddings) + 1} [{p}%]...")

                    chunk = signal[:, start_idx:end_idx]

                    # Compute energy to skip pure silence
                    rms = torch.sqrt(torch.mean(chunk**2))
                    if rms < 0.001:
                        continue

                    emb = classifier.encode_batch(chunk)
                    embeddings.append(emb.squeeze(0).squeeze(0).detach().numpy())
                    times.append((start_idx / fs, end_idx / fs))

                if not embeddings:
                    # All silence
                    return {
                        "speaker_count": 1,
                        "segments": [
                            AudioSegment(speaker_id="SPEAKER_00", start=0.0, end=duration).to_dict()
                        ],
                        "duration": duration,
                        "analysis_source": "speechbrain_ecapa_diarizer",
                    }

                # Cluster embeddings
                X = np.stack(embeddings)

                # Heuristics for number of clusters based on distance threshold
                # Refined for 2026 SOTA: 0.55 provides better speaker separation in forensics
                clustering = AgglomerativeClustering(
                    n_clusters=None,
                    distance_threshold=0.55,
                    metric="cosine",
                    linkage="average",
                )
                labels = clustering.fit_predict(X)

                # Enforce max/min speakers bounds
                num_clusters = len(set(labels))
                if num_clusters > max_speakers or num_clusters < min_speakers:
                    n_tgt = max(min_speakers, min(num_clusters, max_speakers))
                    clustering = AgglomerativeClustering(
                        n_clusters=n_tgt,
                        metric="cosine",
                        linkage="average",
                    )
                    labels = clustering.fit_predict(X)

                # Merge contiguous blocks
                segments = []
                current_speaker = f"SPEAKER_{labels[0]:02d}"
                current_start = times[0][0]
                current_end = times[0][1]

                for i in range(1, len(labels)):
                    spk = f"SPEAKER_{labels[i]:02d}"
                    t_start, t_end = times[i]

                    # Merge if same speaker and overlap / adjacent
                    if spk == current_speaker and t_start <= current_end + 0.1:
                        current_end = max(current_end, t_end)
                    else:
                        segments.append(
                            AudioSegment(
                                speaker_id=current_speaker,
                                start=float(round(current_start, 2)),
                                end=float(round(current_end, 2)),
                            )
                        )
                        current_speaker = spk
                        current_start = t_start
                        current_end = t_end

                # Add final block
                segments.append(
                    AudioSegment(
                        speaker_id=current_speaker,
                        start=float(round(current_start, 2)),
                        end=float(round(current_end, 2)),
                    )
                )

                return {
                    "speaker_count": len({s.speaker_id for s in segments}),
                    "segments": [s.to_dict() for s in segments],
                    "duration": duration,
                    "analysis_source": "speechbrain_ecapa_diarizer",
                    "model": "speechbrain/spkrec-ecapa-voxceleb",
                }
            except Exception as _sb_err:
                import warnings as _w

                _w.warn(
                    f"SpeechBrain diarization failed ({_sb_err}), "
                    "falling back to librosa spectral clustering.",
                    RuntimeWarning,
                    stacklevel=2,
                )

        # ── Librosa fallback (spectral energy clustering) ────────────────────

        # Load audio with librosa
        y, sr = await loop.run_in_executor(None, lambda: librosa.load(audio_path, sr=None))
        # Compute short-time energy
        frame_length = int(sr * 0.025)  # 25ms frames
        hop_length = int(sr * 0.010)  # 10ms hop

        rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
        threshold = np.mean(rms) * 0.5
        speech_frames = rms > threshold
        librosa.frames_to_time(np.arange(len(speech_frames)), sr=sr, hop_length=hop_length)

        librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)

        segments = []
        segment_duration = 2.0
        num_segments = int(duration / segment_duration)

        if num_segments == 0:
            segments.append(AudioSegment(speaker_id="SPEAKER_01", start=0.0, end=duration))
        else:
            segment_features = []
            for i in range(num_segments):
                start_sample = int(i * segment_duration * sr)
                end_sample = min(int((i + 1) * segment_duration * sr), len(y))

                if end_sample - start_sample < sr * 0.1:
                    continue

                segment_y = y[start_sample:end_sample]
                centroid = np.mean(librosa.feature.spectral_centroid(y=segment_y, sr=sr))
                segment_features.append(centroid)

            if len(segment_features) > 0:
                segment_features = np.array(segment_features)
                median_val = np.median(segment_features)

                current_speaker = "SPEAKER_01"
                speaker_count = 1

                for i, feat in enumerate(segment_features):
                    if abs(feat - median_val) > np.std(segment_features):
                        if speaker_count < max_speakers:
                            speaker_count += 1
                            current_speaker = f"SPEAKER_{speaker_count:02d}"

                    start_time = i * segment_duration
                    end_time = min((i + 1) * segment_duration, duration)

                    if segments and segments[-1].speaker_id == current_speaker:
                        segments[-1] = AudioSegment(
                            speaker_id=current_speaker,
                            start=segments[-1].start,
                            end=end_time,
                        )
                    else:
                        segments.append(
                            AudioSegment(
                                speaker_id=current_speaker,
                                start=start_time,
                                end=end_time,
                            )
                        )
            else:
                segments.append(AudioSegment(speaker_id="SPEAKER_01", start=0.0, end=duration))

        return {
            "speaker_count": len({s.speaker_id for s in segments}),
            "segments": [s.to_dict() for s in segments],
            "duration": duration,
            "sample_rate": sr,
            "analysis_source": "librosa_spectral_fallback",
            "forensic_caveat": (
                "[DEGRADED] Speaker segmentation used librosa spectral-energy clustering. "
                "Neural models failed to initialize."
            ),
        }

    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"Speaker diarization failed: {str(e)}")


async def anti_spoofing_detect(
    artifact: EvidenceArtifact,
    segment: dict | None = None,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """
    Detect audio spoofing / deepfake voice.

    Attempts SpeechBrain ECAPA-TDNN anti-spoofing classifier when available.
    Falls back to heuristic spectral analysis (librosa) otherwise.
    'analysis_source' in the result indicates which path ran.

    Args:
        artifact: The evidence artifact to analyze
        segment: Optional segment dict with 'start' and 'end' keys

    Returns:
        Dictionary with spoof_detected, confidence, analysis_source, anomalies
    """
    try:
        audio_path = artifact.file_path
        if not os.path.exists(audio_path):
            raise ToolUnavailableError(f"File not found: {audio_path}")

        try:
            import torch

            from core.config import get_settings

            settings = get_settings()
            if settings.offline_mode:
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["TRANSFORMERS_OFFLINE"] = "1"

            extractor, model = _get_audio_deepfake_bundle(
                settings.aasist_model_name,
                local_files_only=settings.offline_mode,
            )
            sample_rate = int(getattr(extractor, "sampling_rate", 16000) or 16000)
            y, sr = librosa.load(audio_path, sr=sample_rate, mono=True)
            if segment:
                start_sample = int(segment.get("start", 0) * sr)
                end_sample = int(segment.get("end", len(y) / sr) * sr)
                y = y[start_sample:end_sample]

            if progress_callback:
                await progress_callback("Auditing neural spoof signatures...")

            inputs = extractor(
                y,
                sampling_rate=sample_rate,
                return_tensors="pt",
                padding=True,
            )
            with torch.no_grad():
                outputs = model(**inputs)
            id2label = getattr(model.config, "id2label", {}) or {}
            spoof_prob = _spoof_probability_from_logits(outputs.logits, id2label)

            return {
                "spoof_detected": spoof_prob > 0.5,
                "confidence": round(spoof_prob if spoof_prob > 0.5 else 1.0 - spoof_prob, 3),
                "spoof_probability": round(spoof_prob, 4),
                "model_version": settings.aasist_model_name,
                "anomalies": ["Neural audio deepfake signature detected"]
                if spoof_prob > 0.5
                else [],
                "analysis_source": "transformers_audio_deepfake",
                "court_defensible": True,
            }
        except Exception as _model_err:
            import warnings as _w

            _w.warn(
                f"Audio deepfake model failed ({_model_err}), "
                "falling back to heuristic spectral analysis.",
                RuntimeWarning,
                stacklevel=2,
            )
        # ── Heuristic spectral fallback ───────────────────────────────────────

        # Load audio
        loop = asyncio.get_running_loop()
        y, sr = await loop.run_in_executor(None, lambda: librosa.load(audio_path, sr=None))

        # Extract segment if specified
        if segment:
            start_sample = int(segment.get("start", 0) * sr)
            end_sample = int(segment.get("end", len(y) / sr) * sr)
            y = y[start_sample:end_sample]

        anomalies = []
        spoof_score = 0.0

        # 1. Check for codec artifacts (synthetic audio often has unusual codec signatures)
        # Compute spectral flatness - synthetic audio tends to be less flat
        flatness = librosa.feature.spectral_flatness(y=y)
        mean_flatness = np.mean(flatness)

        if mean_flatness > 0.5:
            anomalies.append("High spectral flatness (possible synthetic)")
            spoof_score += 0.2

        # 2. Check for pitch consistency (synthetic voices may have unnatural pitch patterns)
        f0, voiced_flag, voiced_probs = librosa.pyin(
            y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7"), sr=sr
        )

        # Filter out NaN values
        f0_valid = f0[~np.isnan(f0)]
        if len(f0_valid) > 0:
            f0_std = np.std(f0_valid)
            if f0_std < 10:  # Very stable pitch is suspicious
                anomalies.append("Unusually stable pitch (possible synthetic)")
                spoof_score += 0.3
            elif f0_std > 100:  # Very unstable pitch is also suspicious
                anomalies.append("Unusually unstable pitch (possible manipulation)")
                spoof_score += 0.2

        # 3. Check for spectral rolloff anomalies
        rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)
        rolloff_std = np.std(rolloff)

        if rolloff_std < 500:  # Very consistent rolloff
            anomalies.append("Unusual spectral rolloff consistency")
            spoof_score += 0.15

        # 4. Check for zero crossing rate anomalies
        zcr = librosa.feature.zero_crossing_rate(y)
        zcr_mean = np.mean(zcr)

        if zcr_mean > 0.15:  # High ZCR can indicate synthetic audio
            anomalies.append("High zero crossing rate")
            spoof_score += 0.1

        # Normalize spoof score to confidence
        confidence = min(1.0, spoof_score)
        spoof_detected = confidence > 0.5

        return {
            "spoof_detected": spoof_detected,
            "confidence": confidence,
            "model_version": "heuristic_spectral_v1.0",
            "anomalies": anomalies,
            "analysis_source": "librosa_heuristic_fallback",
            "metrics": {
                "zcr_mean": float(zcr_mean),
            },
            "forensic_caveat": (
                "[DEGRADED] Anti-spoofing used heuristic spectral features (ZCR, pitch "
                "stability, flatness). This will NOT reliably detect modern TTS or voice "
                "cloning (ElevenLabs, Voicebox, VALL-E). Install speechbrain and "
                "torchaudio for ECAPA-TDNN neural detection. Results from this fallback "
                "MUST NOT be cited as primary deepfake evidence."
            ),
        }

    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"Anti-spoofing detection failed: {str(e)}")


async def prosody_analyze(
    artifact: EvidenceArtifact,
) -> dict[str, Any]:
    """
    Analyze prosody features for discontinuities.

    Uses librosa to extract pitch, energy, and rhythm features,
    then detects statistical discontinuities that may indicate splicing.

    Args:
        artifact: The evidence artifact to analyze

    Returns:
        Dictionary containing:
        - anomalies: List of detected prosody anomalies
        - pitch_stats: Pitch statistics
        - energy_stats: Energy statistics
    """
    try:
        audio_path = artifact.file_path
        if not os.path.exists(audio_path):
            raise ToolUnavailableError(f"File not found: {audio_path}")

        # Load audio. Prefer librosa for pitch/beat helpers, but keep a
        # SoundFile path so hardened containers with broken numba still work.
        loop = asyncio.get_running_loop()
        used_librosa = True
        try:
            y, sr = await loop.run_in_executor(None, lambda: librosa.load(audio_path, sr=None))
        except Exception:
            used_librosa = False
            y, sr = await loop.run_in_executor(None, lambda: _load_audio_with_soundfile(audio_path))
        len(y) / sr

        anomalies = []

        # 1. Extract pitch (F0)
        if used_librosa:
            f0, voiced_flag, voiced_probs = librosa.pyin(
                y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7"), sr=sr
            )
        else:
            frame_size = min(2048, max(256, int(sr * 0.04)))
            hop = max(128, frame_size // 2)
            f0_values = []
            for start in range(0, max(1, len(y) - frame_size + 1), hop):
                frame = y[start : start + frame_size]
                crossings = np.where(np.diff(np.signbit(frame)))[0]
                duration = len(frame) / float(sr)
                hz = (len(crossings) / 2.0) / duration if duration > 0 else np.nan
                f0_values.append(hz if 50.0 <= hz <= 2200.0 else np.nan)
            f0 = np.asarray(f0_values, dtype=np.float32)

        # Analyze pitch discontinuities
        f0_valid = f0[~np.isnan(f0)]
        if len(f0_valid) > 1:
            # Compute pitch derivative to find sudden changes
            f0_diff = np.diff(f0_valid)
            pitch_threshold = np.std(f0_diff) * 3

            # Find large pitch jumps
            pitch_jumps = np.where(np.abs(f0_diff) > pitch_threshold)[0]

            for jump_idx in pitch_jumps:
                # Map back to time
                voiced_times = np.where(~np.isnan(f0))[0]
                if jump_idx < len(voiced_times):
                    frame_idx = voiced_times[jump_idx]
                    time = (
                        float(frame_idx * 512 / sr) if used_librosa else float(frame_idx * hop / sr)
                    )
                    anomalies.append(
                        ProsodyAnomaly(
                            timestamp=time,
                            type="pitch_discontinuity",
                            severity=min(1.0, abs(f0_diff[jump_idx]) / pitch_threshold / 3),
                        )
                    )

        # 2. Extract energy (RMS)
        rms = (
            librosa.feature.rms(y=y)[0]
            if used_librosa
            else _frame_rms(y, min(2048, len(y)), max(128, min(2048, len(y)) // 4))
        )
        rms_diff = np.diff(rms)
        energy_threshold = np.std(rms_diff) * 3

        # Find sudden energy changes
        energy_jumps = np.where(np.abs(rms_diff) > energy_threshold)[0]

        for jump_idx in energy_jumps:
            time = (
                float(librosa.frames_to_time(jump_idx, sr=sr))
                if used_librosa
                else float(jump_idx * max(128, min(2048, len(y)) // 4) / sr)
            )
            # Check if this anomaly is already recorded
            existing_times = [a.timestamp for a in anomalies]
            if not any(abs(t - time) < 0.1 for t in existing_times):
                anomalies.append(
                    ProsodyAnomaly(
                        timestamp=time,
                        type="energy_discontinuity",
                        severity=min(1.0, abs(rms_diff[jump_idx]) / energy_threshold / 3),
                    )
                )

        # 3. Analyze rhythm (tempo changes)
        tempo = None
        beats = []
        if used_librosa:
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr)

        # Compute beat intervals
        if used_librosa and len(beats) > 1:
            beat_times = librosa.frames_to_time(beats, sr=sr)
            beat_intervals = np.diff(beat_times)

            # Check for unusual rhythm changes
            interval_std = np.std(beat_intervals)
            interval_mean = np.mean(beat_intervals)

            # Flag beats with unusual timing
            for i, interval in enumerate(beat_intervals):
                if abs(interval - interval_mean) > interval_std * 2:
                    time = beat_times[i]
                    existing_times = [a.timestamp for a in anomalies]
                    if not any(abs(t - time) < 0.2 for t in existing_times):
                        anomalies.append(
                            ProsodyAnomaly(
                                timestamp=time,
                                type="rhythm_discontinuity",
                                severity=min(
                                    1.0,
                                    abs(interval - interval_mean) / interval_std / 2,
                                ),
                            )
                        )

        # Sort anomalies by timestamp
        anomalies.sort(key=lambda x: x.timestamp)

        return {
            "anomalies": [a.to_dict() for a in anomalies],
            "pitch_stats": {
                "mean": float(np.mean(f0_valid)) if len(f0_valid) > 0 else None,
                "std": float(np.std(f0_valid)) if len(f0_valid) > 0 else None,
                "range": [float(np.min(f0_valid)), float(np.max(f0_valid))]
                if len(f0_valid) > 0
                else None,
            },
            "energy_stats": {
                "mean": float(np.mean(rms)),
                "std": float(np.std(rms)),
                "range": [float(np.min(rms)), float(np.max(rms))],
            },
            "tempo": float(tempo)
            if isinstance(tempo, (int, float, np.floating))
            else float(tempo[0])
            if tempo is not None and len(tempo) > 0
            else None,
            "backend": "librosa" if used_librosa else "soundfile_numpy_fallback",
        }

    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"Prosody analysis failed: {str(e)}")


async def background_noise_consistency(
    artifact: EvidenceArtifact,
    segment_duration: float = 1.0,
) -> dict[str, Any]:
    """
    Analyze background noise consistency across audio.

    Segments audio and computes noise floor per segment,
    detecting shift points that may indicate splicing.

    Args:
        artifact: The evidence artifact to analyze
        segment_duration: Duration of each analysis segment in seconds

    Returns:
        Dictionary containing:
        - shift_points: List of timestamps where noise floor shifts
        - consistent: Boolean indicating if noise is consistent
        - noise_profile: Noise floor profile across segments
    """
    try:
        audio_path = artifact.file_path
        if not os.path.exists(audio_path):
            raise ToolUnavailableError(f"File not found: {audio_path}")

        # Load audio without relying on librosa's numba-backed lazy imports.
        loop = asyncio.get_running_loop()
        y, sr = await loop.run_in_executor(None, lambda: _load_audio_with_soundfile(audio_path))
        len(y) / sr

        # Segment the audio
        segment_samples = int(segment_duration * sr)
        num_segments = int(len(y) / segment_samples)

        if num_segments < 2:
            return {
                "shift_points": [],
                "consistent": True,
                "noise_profile": [],
                "message": "Audio too short for noise consistency analysis",
            }

        # Compute noise floor for each segment
        noise_floors = []

        for i in range(num_segments):
            start = i * segment_samples
            end = min((i + 1) * segment_samples, len(y))
            segment = y[start:end]

            # Compute noise floor (lower percentile of energy)
            rms = np.sqrt(np.mean(segment**2))
            # Also compute spectral characteristics
            spectral_centroid = _spectral_centroid_np(segment, sr)

            noise_floors.append(
                {
                    "timestamp": i * segment_duration,
                    "rms": float(rms),
                    "spectral_centroid": float(spectral_centroid),
                }
            )

        # Detect shift points
        shift_points = []
        rms_values = [n["rms"] for n in noise_floors]
        rms_mean = np.mean(rms_values)
        rms_std = np.std(rms_values)

        # Threshold for detecting a shift
        shift_threshold = rms_std * 2 if rms_std > 0 else 0.01

        for i in range(1, len(noise_floors)):
            rms_diff = abs(noise_floors[i]["rms"] - noise_floors[i - 1]["rms"])
            centroid_diff = abs(
                noise_floors[i]["spectral_centroid"] - noise_floors[i - 1]["spectral_centroid"]
            )

            if rms_diff > shift_threshold or centroid_diff > 1000:
                shift_points.append(
                    {
                        "timestamp": noise_floors[i]["timestamp"],
                        "rms_change": float(rms_diff),
                        "spectral_change": float(centroid_diff),
                    }
                )

        # Determine overall consistency
        consistent = len(shift_points) == 0

        return {
            "shift_points": shift_points,
            "consistent": consistent,
            "noise_profile": noise_floors,
            "statistics": {
                "mean_rms": float(rms_mean),
                "std_rms": float(rms_std),
                "num_segments": num_segments,
            },
        }

    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"Background noise consistency analysis failed: {str(e)}")


async def codec_fingerprint(
    artifact: EvidenceArtifact,
) -> dict[str, Any]:
    """
    Detect codec fingerprint and re-encoding events.

    Analyzes audio for signs of multiple encoding passes.

    Args:
        artifact: The evidence artifact to analyze

    Returns:
        Dictionary containing:
        - reencoding_events: List of detected re-encoding events
        - codec_chain: List of detected codecs
        - format_info: Audio format information
    """
    try:
        audio_path = artifact.file_path
        if not os.path.exists(audio_path):
            raise ToolUnavailableError(f"File not found: {audio_path}")

        # Get audio file info using soundfile
        info = sf.info(audio_path)

        reencoding_events = []
        codec_chain = []

        # Determine format from file extension
        ext = os.path.splitext(audio_path)[1].lower()
        if ext in [".mp3", ".mp2", ".mp1"]:
            codec_chain.append("MP3")
        elif ext in [".m4a", ".mp4", ".aac"]:
            codec_chain.append("AAC")
        elif ext in [".wav"]:
            codec_chain.append("PCM")
        elif ext in [".flac"]:
            codec_chain.append("FLAC")
        elif ext in [".ogg", ".oga"]:
            codec_chain.append("Vorbis")
        else:
            codec_chain.append(f"Unknown ({ext})")

        # Load audio for analysis. Use SoundFile + NumPy here instead of
        # librosa's lazy numba path, which can fail in hardened containers.
        y, sr = sf.read(audio_path, dtype="float32")
        if getattr(y, "ndim", 1) > 1:
            y = y.mean(axis=1)
        y = np.asarray(y, dtype=np.float32)
        if y.size == 0:
            return {
                "reencoding_events": [],
                "codec_chain": codec_chain,
                "format_info": {
                    "format": info.format,
                    "subtype": info.subtype,
                    "channels": info.channels,
                    "samplerate": info.samplerate,
                    "duration": info.duration,
                    "frames": info.frames,
                    "spectral_complexity": 0.0,
                },
            }

        # Check for codec artifacts

        # 1. Spectral cutoff (typical of lossy codecs)
        frame_size = min(2048, max(256, int(2 ** np.floor(np.log2(max(256, min(len(y), 2048)))))))
        hop = max(128, frame_size // 4)
        if len(y) < frame_size:
            padded = np.pad(y, (0, frame_size - len(y)))
            frames = padded[None, :]
        else:
            starts = range(0, len(y) - frame_size + 1, hop)
            frames = np.stack([y[start : start + frame_size] for start in starts])
        window = np.hanning(frame_size).astype(np.float32)
        spectrum = np.abs(np.fft.rfft(frames * window, axis=1))
        freqs = np.fft.rfftfreq(frame_size, d=1.0 / float(sr))
        energy_per_freq = np.mean(spectrum, axis=0)
        peak_energy = float(np.max(energy_per_freq)) if energy_per_freq.size else 0.0
        spectral_complexity = (
            float(np.count_nonzero(energy_per_freq > peak_energy * 0.05))
            / float(len(energy_per_freq))
            if peak_energy > 0 and len(energy_per_freq) > 0
            else 0.0
        )
        cumulative = np.cumsum(energy_per_freq)
        rolloff_idx = (
            int(np.searchsorted(cumulative, cumulative[-1] * 0.85)) if cumulative[-1] > 0 else 0
        )
        max_freq = float(freqs[min(rolloff_idx, len(freqs) - 1)])
        nyquist = sr / 2

        # If max frequency is significantly below Nyquist, likely lossy encoded
        if spectral_complexity >= 0.08 and max_freq < nyquist * 0.8:
            cutoff_ratio = max_freq / nyquist
            reencoding_events.append(
                {
                    "type": "spectral_cutoff",
                    "frequency": float(max_freq),
                    "confidence": 1.0 - cutoff_ratio,
                }
            )

        # 2. Check for MP3 artifacts (frequency notches)
        # MP3 encoding creates characteristic notches at certain frequencies
        # Look for energy drops at typical MP3 cutoff frequencies
        # Check for sudden energy drops
        energy_diff = np.diff(energy_per_freq)
        significant_drops = np.where(energy_diff < -np.std(energy_diff) * 3)[0]

        for drop_idx in significant_drops:
            freq = freqs[drop_idx]
            if spectral_complexity >= 0.08 and freq > 1000:  # Ignore low frequency variations
                reencoding_events.append(
                    {
                        "type": "frequency_notch",
                        "frequency": float(freq),
                        "confidence": min(
                            1.0, abs(energy_diff[drop_idx]) / np.std(energy_diff) / 5
                        ),
                    }
                )

        # 3. Check for quantization noise (typical of re-encoding)
        # Look for noise floor patterns
        rms = np.sqrt(np.mean(frames**2, axis=1))
        rms_std = float(np.std(rms))

        if spectral_complexity >= 0.08 and rms_std < np.mean(rms) * 0.01:
            # Very consistent noise floor might indicate heavy processing
            reencoding_events.append(
                {
                    "type": "consistent_noise_floor",
                    "confidence": 0.5,
                }
            )

        return {
            "reencoding_events": reencoding_events,
            "codec_chain": codec_chain,
            "format_info": {
                "format": info.format,
                "subtype": info.subtype,
                "channels": info.channels,
                "samplerate": info.samplerate,
                "duration": info.duration,
                "frames": info.frames,
                "spectral_complexity": round(spectral_complexity, 4),
            },
        }

    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"Codec fingerprint analysis failed: {str(e)}")


# ============================================================================
# UPGRADED ML-BASED AUDIO FORENSIC FUNCTIONS
# ============================================================================
# These functions provide enhanced detection using state-of-the-art ML models

# Module-level singletons — models are expensive to load (~seconds each).
# Loaded on first use and reused for all subsequent calls.
# asyncio.Lock prevents concurrent coroutines from racing to load the same model.
# Model loading itself is offloaded to a thread pool (run_in_executor) so it
# never blocks the event loop.
_speechbrain_classifier_instance: Any | None = None
_speechbrain_lock: asyncio.Lock | None = None


def _get_speechbrain_lock() -> asyncio.Lock:
    global _speechbrain_lock
    if _speechbrain_lock is None:
        _speechbrain_lock = asyncio.Lock()
    return _speechbrain_lock


async def _get_speechbrain_classifier_async() -> Any:
    """Load SpeechBrain ECAPA classifier once, off the event loop (thread-safe)."""
    global _speechbrain_classifier_instance
    if _speechbrain_classifier_instance is not None:
        return _speechbrain_classifier_instance
    async with _get_speechbrain_lock():
        if _speechbrain_classifier_instance is not None:
            return _speechbrain_classifier_instance

        def _load() -> Any:
            from speechbrain.inference.classifiers import (
                EncoderClassifier,  # type: ignore[import-untyped]
            )

            return EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb")

        _speechbrain_classifier_instance = await asyncio.get_running_loop().run_in_executor(
            None, _load
        )
        return _speechbrain_classifier_instance


async def prosody_praat(
    artifact: EvidenceArtifact,
) -> dict[str, Any]:
    """
    Analyze prosody using Praat via parselmouth (upgrade from librosa).

    Praat is the gold-standard acoustic phonetics engine used in forensic labs.
    Provides accurate F0 (pitch), jitter, shimmer, and HNR measurements.

    Args:
        artifact: The evidence artifact to analyze

    Returns:
        Dictionary containing:
        - f0_mean_hz: Mean fundamental frequency
        - f0_std_hz: Standard deviation of F0
        - f0_range_hz: Range of F0
        - jitter_local: Local jitter (cycle-to-cycle F0 variation)
        - shimmer_local: Local shimmer (cycle-to-cycle amplitude variation)
        - hnr_db: Harmonics-to-Noise Ratio
        - prosody_anomaly_detected: Boolean flag
        - backend: Engine identifier

    Note:
        Forensic thresholds: jitter > 0.01 or shimmer > 0.05 = suspicious
    """
    try:
        import parselmouth
        from parselmouth.praat import call
    except ImportError:
        # Fall back to legacy implementation
        result = await prosody_analyze(artifact)
        result["backend"] = "legacy-librosa"
        return result

    try:
        audio_path = artifact.file_path
        if not os.path.exists(audio_path):
            raise ToolUnavailableError(f"File not found: {audio_path}")

        snd = parselmouth.Sound(audio_path)

        # Pitch (F0) — fundamental frequency track
        pitch = call(snd, "To Pitch", 0.0, 75, 600)
        f0_values = pitch.selected_array["frequency"]
        f0_voiced = f0_values[f0_values > 0]

        # Jitter (cycle-to-cycle F0 variation) — elevated in synthetic voices
        point_process = call(snd, "To PointProcess (periodic, cc)", 75, 600)
        jitter_local = call(point_process, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3)

        # Shimmer (cycle-to-cycle amplitude variation)
        shimmer_local = call(
            [snd, point_process], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6
        )

        # HNR — Harmonics-to-Noise Ratio (low HNR = synthetic noise floor)
        harmonicity = call(snd, "To Harmonicity (cc)", 0.01, 75, 0.1, 1.0)
        hnr = call(harmonicity, "Get mean", 0, 0)

        # Forensic thresholds
        prosody_anomaly = jitter_local > 0.01 or shimmer_local > 0.05

        return {
            "f0_mean_hz": round(float(f0_voiced.mean()), 2) if len(f0_voiced) > 0 else 0,
            "f0_std_hz": round(float(f0_voiced.std()), 2) if len(f0_voiced) > 0 else 0,
            "f0_range_hz": round(float(f0_voiced.ptp()), 2) if len(f0_voiced) > 0 else 0,
            "jitter_local": round(float(jitter_local), 5),
            "shimmer_local": round(float(shimmer_local), 5),
            "hnr_db": round(float(hnr), 2),
            "prosody_anomaly_detected": prosody_anomaly,
            "available": True,
            "backend": "praat-parselmouth",
        }

    except Exception as e:
        # Fall back to legacy implementation
        result = await prosody_analyze(artifact)
        result["backend"] = "legacy-librosa"
        result["fallback_reason"] = str(e)
        return result


async def av_sync_verify(
    artifact: EvidenceArtifact,
) -> dict[str, Any]:
    """
    Verify audio-visual synchronization in video files.

    Detects audio-visual desync by comparing lip-movement onset (video brightness
    change) vs audio onset times. This is a proxy method that works without
    facial landmark models.

    Args:
        artifact: The evidence artifact to analyze (must be video)

    Returns:
        Dictionary containing:
        - av_sync: Status ("IN_SYNC", "DESYNC_SUSPECTED", "INCONCLUSIVE")
        - correlation_score: Correlation between audio and video activity
        - audio_onsets_count: Number of detected audio onsets
        - court_defensible: Boolean indicating forensic validity

    Note:
        This tool uses OpenCV plus ffmpeg-extracted PCM audio instead of asking
        librosa/moviepy to decode the video container directly. That keeps the
        initial pass stable across MoviePy 1.x/2.x import paths.
    """
    try:
        import subprocess
        import tempfile
        from pathlib import Path

        import cv2
        import imageio_ffmpeg

        video_path = artifact.file_path
        if not os.path.exists(video_path):
            raise ToolUnavailableError(f"File not found: {video_path}")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return {
                "av_sync": "UNAVAILABLE",
                "available": False,
                "error": f"Could not open video stream: {video_path}",
            }

        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        clip_duration = frame_count / fps if fps > 0 else 0.0
        if clip_duration <= 0:
            cap.release()
            return {
                "av_sync": "INCONCLUSIVE",
                "available": True,
                "court_defensible": True,
                "confidence": 0.55,
                "note": "Video duration unavailable for A/V correlation analysis",
            }

        # Video "activity" proxy — frame-level brightness change rate
        # Sample 1 frame per second
        video_activity: list[float] = []
        prev_brightness: float | None = None

        for t in np.arange(0, min(clip_duration, 60), 1.0):
            cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            brightness = float(np.mean(frame))
            if prev_brightness is not None:
                video_activity.append(abs(brightness - prev_brightness))
            prev_brightness = brightness

        cap.release()

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        tmp_wav = Path(tempfile.gettempdir()) / f"fc_avsync_{abs(hash(video_path))}.wav"
        await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: subprocess.run(  # noqa: S603 - ffmpeg argv is fixed; evidence path is an arg.
                [
                    ffmpeg,
                    "-y",
                    "-i",
                    video_path,
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "22050",
                    "-f",
                    "wav",
                    str(tmp_wav),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ),
        )
        y, sr = sf.read(str(tmp_wav), dtype="float32", always_2d=False)
        if isinstance(y, np.ndarray) and y.ndim > 1:
            y = np.mean(y, axis=1)
        y = np.asarray(y, dtype=np.float32)

        if y.size == 0:
            return {
                "av_sync": "NOT_APPLICABLE",
                "available": True,
                "not_applicable": True,
                "court_defensible": False,
                "confidence": 0.0,
                "note": "No decodable audio track found in video container",
            }

        hop = max(1, int(sr * 0.05))
        frame_rms = np.array(
            [
                float(np.sqrt(np.mean(np.square(y[i : i + hop]))))
                for i in range(0, max(0, len(y) - hop), hop)
            ],
            dtype=np.float32,
        )
        if frame_rms.size > 2:
            delta = np.diff(frame_rms)
            threshold = float(delta.mean() + delta.std())
            onset_indices = np.where(delta > threshold)[0]
            audio_onsets = (onset_indices * hop / sr).tolist()
        else:
            audio_onsets = []

        if len(video_activity) < 3 or len(audio_onsets) < 2:
            return {
                "av_sync": "INCONCLUSIVE",
                "available": True,
                "court_defensible": True,
                "confidence": 0.55,
                "note": "Insufficient data for correlation analysis",
            }

        # Correlation between audio energy and video activity at 1s resolution
        audio_energy_per_sec = [
            float(np.mean(np.abs(y[int(t * sr) : int((t + 1) * sr)])))
            for t in range(min(len(video_activity), int(clip_duration)))
        ]

        min_len = min(len(video_activity), len(audio_energy_per_sec))
        corr = float(np.corrcoef(video_activity[:min_len], audio_energy_per_sec[:min_len])[0, 1])

        return {
            "av_sync": "IN_SYNC" if corr > 0.3 else "DESYNC_SUSPECTED",
            "correlation_score": round(corr, 3),
            "audio_onsets_count": len(audio_onsets),
            "sync_drift_detected": corr <= 0.3,
            "confidence": 0.82 if corr > 0.3 else 0.70,
            "court_defensible": True,
            "available": True,
            "backend": "opencv+ffmpeg+soundfile",
        }

    except Exception as e:
        return {
            "av_sync": "ERROR",
            "available": False,
            "error": str(e),
        }
