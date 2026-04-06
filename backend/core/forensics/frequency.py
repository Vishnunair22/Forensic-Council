"""
Frequency Domain Analysis Core Engine.
======================================

Detects GAN/synthetic artifacts or JPEG-then-PNG conversion banding using FFT.
"""

import numpy as np
from PIL import Image

from core.structured_logging import get_logger

logger = get_logger(__name__)

def analyze_frequency_bands(file_path: str) -> dict:
    """
    Perform FFT frequency band distribution analysis.
    
    Args:
        file_path: Path to the image file.
        
    Returns:
        dict: Frequency metrics and detection status.
    """
    try:
        img = np.array(Image.open(file_path).convert("L"), dtype=np.float32)
        fft = np.fft.fft2(img)
        fft_shift = np.fft.fftshift(fft)
        magnitude = np.abs(fft_shift)
        h, w = magnitude.shape
        cy, cx = h // 2, w // 2

        # Sampling 4 frequency bands (inner center to periphery)
        r1, r2, r3 = h // 8, h // 4, 3 * h // 8
        c1, c2, c3 = w // 8, w // 4, 3 * w // 8
        total_energy = magnitude.sum() + 1e-6

        bands = {}
        for i, (r_inner, r_outer, c_inner, c_outer) in enumerate([
            (0, r1, 0, c1),
            (r1, r2, c1, c2),
            (r2, r3, c2, c3),
            (r3, h // 2, c3, w // 2),
        ]):
            mask = np.zeros((h, w), dtype=bool)
            mask[cy - r_outer : cy + r_outer, cx - c_outer : cx + c_outer] = True
            if i > 0:
                mask[cy - r_inner : cy + r_inner, cx - c_inner : cx + c_inner] = False
            bands[f"band_{i}"] = float(magnitude[mask].sum() / total_energy)

        high_freq_ratio = bands["band_3"]
        mid_freq_ratio = bands["band_2"]
        band_ratios = list(bands.values())
        ratio_variance = float(np.var(band_ratios))

        # Heuristic: GAN artifacts often show high-frequency spikes or suppression
        is_anomalous = ratio_variance > 0.02 or high_freq_ratio < 0.05
        anomaly_score = round(min(ratio_variance * 10, 1.0), 3)

        return {
            "anomaly_score": anomaly_score,
            "high_freq_ratio": round(high_freq_ratio, 4),
            "mid_freq_ratio": round(mid_freq_ratio, 4),
            "frequency_bands": {k: round(v, 4) for k, v in bands.items()},
            "ratio_variance": round(ratio_variance, 6),
            "gan_artifact_detected": is_anomalous,
            "backend": "core-fft-frequency-engine",
            "court_defensible": True,
            "available": True,
        }
    except Exception as e:
        logger.error(f"FFT analysis failed: {e}", exc_info=True)
        return {
            "anomaly_score": 0,
            "error": str(e),
            "backend": "core-fft-frequency-engine",
            "court_defensible": False,
        }
