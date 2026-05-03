"""
Prosody Analysis
==================

F0, jitter, shimmer analysis using librosa.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

import numpy as np

from core.evidence import EvidenceArtifact
from core.exceptions import ToolUnavailableError

try:
    import librosa
except Exception:
    librosa = None


@dataclass
class ProsodyAnomaly:
    timestamp: float
    type: str
    severity: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "type": self.type,
            "severity": self.severity,
        }


def _frame_rms(y: np.ndarray, frame_size: int, hop: int) -> np.ndarray:
    if len(y) < frame_size:
        frames = np.pad(y, (0, frame_size - len(y)))[None, :]
    else:
        frames = np.stack(
            [y[start : start + frame_size] for start in range(0, len(y) - frame_size + 1, hop)
        )
    return np.sqrt(np.mean(frames**2, axis=1))


async def run_prosody_analyze(
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

        loop = asyncio.get_running_loop()
        used_librosa = True
        try:
            y, sr = await loop.run_in_executor(None, lambda: librosa.load(audio_path, sr=None))
        except Exception:
            from tools.audio.diarization import _load_audio_with_soundfile
            used_librosa = False
            y, sr = await loop.run_in_executor(None, lambda: _load_audio_with_soundfile(audio_path))

        len(y) / sr

        anomalies = []

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

        f0_valid = f0[~np.isnan(f0)]
        if len(f0_valid) > 1:
            f0_diff = np.diff(f0_valid)
            pitch_threshold = np.std(f0_diff) * 3
            pitch_jumps = np.where(np.abs(f0_diff) > pitch_threshold)[0]

            for jump_idx in pitch_jumps:
                voiced_times = np.where(~np.isnan(f0))[0]
                if jump_idx < len(voiced_times):
                    frame_idx = voiced_times[jump_idx]
                    time = (
                        float(frame_idx * 512 / sr) if used_librosa 
                        else float(frame_idx * hop / sr)
                    )
                    anomalies.append(
                        ProsodyAnomaly(
                            timestamp=time,
                            type="pitch_discontinuity",
                            severity=min(1.0, abs(f0_diff[jump_idx]) / pitch_threshold / 3),
                        )
                    )

        rms = (
            librosa.feature.rms(y=y)[0]
            if used_librosa
            else _frame_rms(y, min(2048, len(y)), max(128, min(2048, len(y)) // 4))
        )
        rms_diff = np.diff(rms)
        energy_threshold = np.std(rms_diff) * 3
        energy_jumps = np.where(np.abs(rms_diff) > energy_threshold)[0]

        for jump_idx in energy_jumps:
            time = float(jump_idx * 512 / sr) if used_librosa else float(jump_idx * hop / sr)
            anomalies.append(
                ProsodyAnomaly(
                    timestamp=time,
                    type="energy_discontinuity",
                    severity=min(1.0, abs(rms_diff[jump_idx]) / energy_threshold / 3),
                )
            )

        return {
            "anomalies": [a.to_dict() for a in anomalies],
            "pitch_stats": {
                "mean_f0": float(np.nanmean(f0)) if len(f0_valid) > 0 else 0.0,
                "std_f0": float(np.nanstd(f0)) if len(f0_valid) > 0 else 0.0,
                "voiced_ratio": float(np.sum(~np.isnan(f0)) / len(f0)) if len(f0) > 0 else 0.0,
            },
            "energy_stats": {
                "mean_rms": float(np.mean(rms)),
                "std_rms": float(np.std(rms)),
            },
        }
    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"Prosody analysis failed: {str(e)}")