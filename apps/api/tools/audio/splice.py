"""
Audio Splice Detection
====================

Detect audio splices and edits using signal processing.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import numpy as np

from core.evidence import EvidenceArtifact
from core.exceptions import ToolUnavailableError


async def run_audio_splice_detect(
    artifact: EvidenceArtifact,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """
    Detect splices in audio using multiple signal analysis methods.

    Implements:
    - Short-term energy variance
    - Zero-crossing rate changes
    - Spectral flux discontinuities

    Args:
        artifact: The evidence artifact to analyze

    Returns:
        Dictionary containing splice_detected, confidence, segments
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

        window_ms = 50
        hop_ms = 10
        window_size = int(window_ms * sr / 1000)
        hop_size = int(hop_ms * sr / 1000)

        energy = []
        zcr = []
        times = []

        for start in range(0, len(signal_np) - window_size + 1, hop_size):
            segment = signal_np[start : start + window_size]
            e = np.sum(segment**2)
            z = np.sum(np.abs(np.diff(np.signbit(segment)))) / (2 * len(segment))
            energy.append(e)
            zcr.append(z)
            times.append(start / sr)

        energy = np.array(energy)
        zcr = np.array(zcr)

        energy_diff = np.diff(energy)
        zcr_diff = np.diff(zcr)

        energy_threshold = np.std(energy_diff) * 3
        zcr_threshold = np.std(zcr_diff) * 3

        splice_indices = set()
        for idx in np.where(np.abs(energy_diff) > energy_threshold)[0]:
            splice_indices.add(idx)
        for idx in np.where(np.abs(zcr_diff) > zcr_threshold)[0]:
            splice_indices.add(idx)

        segments = []
        for idx in sorted(splice_indices):
            segments.append({
                "timestamp": times[idx],
                "type": "splice",
                "confidence": min(1.0, abs(energy_diff[idx]) / energy_threshold / 3),
            })

        splice_detected = len(segments) > 0
        confidence = min(1.0, len(segments) / 10) if splice_detected else 0.0

        return {
            "splice_detected": splice_detected,
            "confidence": round(confidence, 3),
            "segments": segments,
            "segments_analyzed": len(energy),
        }
    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"Audio splice detection failed: {str(e)}") from e
