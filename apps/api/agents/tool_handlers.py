"""
Shared tool handler utilities for forensic agents.
Contains reusable forensic tool logic wrappers.
"""

from typing import Any

import numpy as np

from core.evidence import EvidenceArtifact
from core.ml_subprocess import run_ml_tool
from core.structured_logging import get_logger

logger = get_logger(__name__)

# Hardcoded seed for reproducible adversarial perturbation checks.
_ADVERSARIAL_RNG_SEED: int = 42


async def run_ml_safe(
    tool_script: str,
    file_path: str,
    extra_args: list[str] | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Wrapper for run_ml_tool with logging and consistent error handling."""
    try:
        result = await run_ml_tool(tool_script, file_path, extra_args=extra_args, timeout=timeout)
        if result.get("error"):
            logger.warning(f"ML tool {tool_script} failed: {result['error']}")
        return result
    except Exception as e:
        logger.error(f"Execution of {tool_script} failed: {e}")
        return {"error": str(e), "available": False}


async def audio_adversarial_check(artifact: EvidenceArtifact) -> dict[str, Any]:
    """Adversarial robustness check for audio anti-spoofing evasion."""
    try:
        import librosa
        from scipy.signal import butter, sosfilt

        y, sr = librosa.load(artifact.file_path, sr=None, mono=True, duration=10.0)

        def _get_feats(signal, sample_rate):
            flux = float(np.mean(np.diff(np.abs(librosa.stft(signal)), axis=1) ** 2))
            zcr = float(np.mean(librosa.feature.zero_crossing_rate(signal)))
            centroid = float(np.mean(librosa.feature.spectral_centroid(y=signal, sr=sample_rate)))
            return {"flux": flux, "zcr": zcr, "centroid": centroid}

        orig = _get_feats(y, sr)
        deltas = {}

        # Low-pass filter
        sos = butter(6, 4000.0 / (sr / 2), btype="low", output="sos")
        lp_y = sosfilt(sos, y).astype(np.float32)
        lp_feats = _get_feats(lp_y, sr)
        deltas["low_pass_4khz"] = round(abs(lp_feats["flux"] - orig["flux"]) / (orig["flux"] + 1e-9), 4)

        # Noise injection
        rng = np.random.default_rng(_ADVERSARIAL_RNG_SEED)
        noise_power = float(np.mean(y**2)) / (10**4)
        noisy_y = (y + rng.normal(0, np.sqrt(noise_power), y.shape)).astype(np.float32)
        noisy_feats = _get_feats(noisy_y, sr)
        deltas["white_noise_-40db"] = round(abs(noisy_feats["zcr"] - orig["zcr"]) / (orig["zcr"] + 1e-9), 4)

        evasion_detected = any(v > 0.50 for v in deltas.values())

        return {
            "status": "real",
            "court_defensible": True,
            "adversarial_pattern_detected": evasion_detected,
            "perturbation_deltas": deltas,
            "confidence": 0.70 if evasion_detected else 0.88
        }
    except Exception as e:
        return {"error": str(e), "available": False}


async def image_ela_handler(artifact: EvidenceArtifact, quality: int = 95) -> dict[str, Any]:
    """Common ELA handler wrapper."""
    from tools.image_tools import ela_full_image
    return await ela_full_image(artifact=artifact, quality=quality)
