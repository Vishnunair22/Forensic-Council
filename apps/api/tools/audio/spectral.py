"""
Spectral Analysis
===================

ENF, FFT, spectrograms for audio forensics.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import numpy as np

from core.evidence import EvidenceArtifact
from core.exceptions import ToolUnavailableError


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


async def run_background_noise_consistency(
    artifact: EvidenceArtifact,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """
    Analyze background noise consistency across audio file.

    Uses FFT to extract spectral features from multiple windows,
    then computes similarity to detect splices or edits.

    Args:
        artifact: The evidence artifact to analyze

    Returns:
        Dictionary containing consistency_score, anomalies, segments_analyzed
    """
    try:
        audio_path = artifact.file_path
        if not os.path.exists(audio_path):
            raise ToolUnavailableError(f"File not found: {audio_path}")

        import soundfile as sf

        loop = asyncio.get_running_loop()
        signal_np, sr = await loop.run_in_executor(
            None, lambda: sf.read(audio_path, dtype="float32")
        )

        if getattr(signal_np, "ndim", 1) > 1:
            signal_np = signal_np.mean(axis=1)

        signal_np = np.asarray(signal_np, dtype=np.float32)

        window_size = int(0.5 * sr)
        hop = window_size // 2
        features = []
        times = []

        for start in range(0, len(signal_np) - window_size + 1, hop):
            segment = signal_np[start : start + window_size]
            rms = np.sqrt(np.mean(segment**2))
            if rms < 0.001:
                continue

            centroid = _spectral_centroid_np(segment, sr)
            features.append(centroid)
            times.append(start / sr)

        features = np.array(features)

        if len(features) < 2:
            return {
                "consistency_score": 1.0,
                "anomalies": [],
                "segments_analyzed": 0,
            }

        feature_diff = np.diff(features)
        threshold = np.std(feature_diff) * 3
        anomaly_indices = np.where(np.abs(feature_diff) > threshold)[0]

        anomalies = []
        for idx in anomaly_indices:
            anomalies.append(
                {
                    "timestamp": times[idx],
                    "type": "spectral_shift",
                    "severity": min(1.0, abs(feature_diff[idx]) / threshold / 3),
                }
            )

        mean_feat = np.mean(features)
        std_feat = np.std(features)
        coefficient_of_variation = std_feat / mean_feat if mean_feat > 0 else 0.0
        consistency_score = max(0.0, 1.0 - coefficient_of_variation)

        return {
            "consistency_score": round(consistency_score, 3),
            "anomalies": anomalies,
            "segments_analyzed": len(features),
        }
    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"Background noise consistency failed: {str(e)}") from e
