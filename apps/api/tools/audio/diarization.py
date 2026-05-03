"""
Speaker Diarization
====================

Speaker segmentation using SpeechBrain ECAPA-TDNN.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

import numpy as np
import soundfile as sf

from core.evidence import EvidenceArtifact
from core.exceptions import ToolUnavailableError

_speechbrain_classifier: Any = None
_speechbrain_loaded: bool = False


def _load_audio_with_soundfile(audio_path: str) -> tuple[np.ndarray, int]:
    """Load mono audio without librosa/numba."""
    y, sr = sf.read(audio_path, dtype="float32")
    if getattr(y, "ndim", 1) > 1:
        y = y.mean(axis=1)
    y = np.asarray(y, dtype=np.float32)
    if y.size == 0:
        raise ToolUnavailableError("Audio stream is empty")
    return y, int(sr)


def _get_speechbrain_classifier_class() -> Any:
    """Return cached SpeechBrain ECAPA anti-spoofing classifier, or None."""
    global _speechbrain_classifier, _speechbrain_loaded
    if not _speechbrain_loaded:
        _speechbrain_loaded = True
        try:
            from speechbrain.pretrained import EncoderClassifier
            _speechbrain_classifier = EncoderClassifier
        except Exception:
            pass
    return _speechbrain_classifier


@dataclass
class AudioSegment:
    speaker_id: str
    start: float
    end: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "speaker_id": self.speaker_id,
            "start": self.start,
            "end": self.end,
        }


async def run_speaker_diarize(
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

        EncoderClassifier = _get_speechbrain_classifier_class()
        if EncoderClassifier is not None:
            try:
                import torch
                from sklearn.cluster import AgglomerativeClustering
                from core.config import get_settings
                settings = get_settings()

                if settings.offline_mode:
                    os.environ["HF_HUB_OFFLINE"] = "1"
                    os.environ["TRANSFORMERS_OFFLINE"] = "1"

                classifier = EncoderClassifier.from_hparams(
                    source="speechbrain/spkrec-ecapa-voxceleb",
                    run_opts={"device": "cpu"},
                )

                signal_np, fs = sf.read(audio_path, dtype="float32")
                if getattr(signal_np, "ndim", 1) > 1:
                    signal_np = signal_np.mean(axis=1)
                signal = torch.from_numpy(np.asarray(signal_np)).unsqueeze(0)

                window_size = int(1.5 * fs)
                step_size = int(0.5 * fs)
                total_samples = signal.shape[1]

                if total_samples < window_size:
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
                    rms = torch.sqrt(torch.mean(chunk**2))
                    if rms < 0.001:
                        continue

                    emb = classifier.encode_batch(chunk)
                    embeddings.append(emb.squeeze().numpy())
                    times.append(start_idx / fs)

                if len(embeddings) == 0:
                    return {
                        "speaker_count": 1,
                        "segments": [
                            AudioSegment(speaker_id="SPEAKER_00", start=0.0, end=duration).to_dict()
                        ],
                        "duration": duration,
                        "analysis_source": "speechbrain_ecapa_diarizer",
                        "model": "speechbrain/spkrec-ecapa-voxceleb",
                    }

                embeddings = np.array(embeddings)
                n_clusters = min(max_speakers, max(1, len(embeddings) // 10))
                clustering = AgglomerativeClustering(n_clusters=n_clusters)
                labels = clustering.fit_predict(embeddings)

                segments = []
                current_speaker = labels[0]
                segment_start = times[0]
                for i, label in enumerate(labels):
                    if label != current_speaker:
                        segments.append(
                            AudioSegment(
                                speaker_id=f"SPEAKER_{current_speaker:02d}",
                                start=segment_start,
                                end=times[i],
                            ).to_dict()
                        )
                        current_speaker = label
                        segment_start = times[i]

                if segments:
                    segments.append(
                        AudioSegment(
                            speaker_id=f"SPEAKER_{current_speaker:02d}",
                            start=segment_start,
                            end=duration,
                        ).to_dict()
                    )

                return {
                    "speaker_count": len(set(labels)),
                    "segments": segments,
                    "duration": duration,
                    "analysis_source": "speechbrain_ecapa_diarizer",
                    "model": "speechbrain/spkrec-ecapa-voxceleb",
                }
            except Exception as e:
                pass

        return {
            "speaker_count": 1,
            "segments": [
                AudioSegment(speaker_id="SPEAKER_00", start=0.0, end=duration).to_dict()
            ],
            "duration": duration,
            "analysis_source": "fallback_single_speaker",
        }
    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"Speaker diarization failed: {str(e)}")