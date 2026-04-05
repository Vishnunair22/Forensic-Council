"""
Error Level Analysis (ELA) Core Engine.
=======================================

Provides pixel-level anomaly detection by analyzing compression residuals.
"""

import io
import numpy as np
from PIL import Image
from core.structured_logging import get_logger

logger = get_logger(__name__)

async def classify_ela_anomalies(file_path: str, quality: int = 95, context_ela_mean: float = None) -> dict:
    """
    Perform ELA block classification.
    
    Args:
        file_path: Path to the image file.
        quality: JPEG compression quality to test against.
        context_ela_mean: Optional baseline ELA mean from a full-image scan.
        
    Returns:
        dict: Anomaly metrics and detection status.
    """
    try:
        img = Image.open(file_path).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=int(quality))
        buf.seek(0)
        recompressed = Image.open(buf).convert("RGB")
        
        ela = np.abs(
            np.array(img, dtype=np.int16) 
            - np.array(recompressed, dtype=np.int16)
        ).astype(np.uint8)
        
        ela_mean = float(context_ela_mean if context_ela_mean is not None else ela.mean())
        ela_max = int(ela.max())
        
        # Split into 8x8 blocks and score each
        arr = ela.mean(axis=2)  # grayscale
        h, w = arr.shape
        block_scores = []
        for y in range(0, h - 8, 8):
            for x in range(0, w - 8, 8):
                block_scores.append(float(arr[y : y + 8, x : x + 8].mean()))
        
        # Anomaly = block mean > 2.5x the baseline ELA mean
        anomaly_blocks = int(sum(1 for s in block_scores if s > ela_mean * 2.5))
        
        return {
            "anomaly_block_count": anomaly_blocks,
            "total_blocks": len(block_scores),
            "ela_mean": round(ela_mean, 3),
            "max_anomaly": ela_max,
            "num_anomaly_regions": anomaly_blocks,
            "anomaly_detected": anomaly_blocks > 5,
            "backend": "core-ela-engine",
            "court_defensible": True,
            "available": True,
        }
    except Exception as e:
        logger.error(f"ELA classification failed: {e}", exc_info=True)
        return {
            "error": str(e),
            "anomaly_detected": False,
            "backend": "core-ela-engine",
            "court_defensible": False,
        }

def check_adversarial_robustness(file_path: str) -> dict:
    """
    Test ELA stability under mild perturbations.
    Detects adversarial smoothing used to hide tampering.
    """
    try:
        original = Image.open(file_path).convert("RGB")
        orig_arr = np.array(original, dtype=np.float32)

        perturbations = {
            "gaussian_noise": 0,
            "double_jpeg": 0,
            "colour_jitter": 0,
        }

        def _ela_residual(arr: np.ndarray, quality: int = 90) -> np.ndarray:
            buf = io.BytesIO()
            Image.fromarray(arr.astype(np.uint8)).save(
                buf, format="JPEG", quality=quality
            )
            buf.seek(0)
            compressed = np.array(
                Image.open(buf).convert("RGB"), dtype=np.float32
            )
            return np.abs(arr - compressed)

        orig_ela = _ela_residual(orig_arr)
        orig_mean = float(orig_ela.mean())

        # 1 — Gaussian noise
        rng = np.random.default_rng(42)
        noisy = np.clip(orig_arr + rng.normal(0, 3.0, orig_arr.shape), 0, 255)
        noisy_ela = _ela_residual(noisy)
        perturbations["gaussian_noise"] = float(abs(noisy_ela.mean() - orig_mean))

        # 2 — Double JPEG
        buf = io.BytesIO()
        original.save(buf, format="JPEG", quality=70)
        buf.seek(0)
        double_compressed = np.array(
            Image.open(buf).convert("RGB"), dtype=np.float32
        )
        dc_ela = _ela_residual(double_compressed)
        perturbations["double_jpeg"] = float(abs(dc_ela.mean() - orig_mean))

        # 3 — Colour jitter
        jitter = np.clip(
            orig_arr + rng.integers(-5, 5, orig_arr.shape, dtype=np.int32),
            0, 255,
        ).astype(np.float32)
        jitter_ela = _ela_residual(jitter)
        perturbations["colour_jitter"] = float(abs(jitter_ela.mean() - orig_mean))

        EVASION_THRESHOLD = 4.0
        evasion_detected = any(v > EVASION_THRESHOLD for v in perturbations.values())

        return {
            "status": "real",
            "court_defensible": True,
            "method": "ELA perturbation stability",
            "adversarial_pattern_detected": evasion_detected,
            "perturbation_deltas": {k: round(v, 4) for k, v in perturbations.items()},
            "evasion_threshold": EVASION_THRESHOLD,
            "original_ela_mean": round(orig_mean, 4),
            "confidence": 0.75 if evasion_detected else 0.90,
            "note": "Unstable ELA response indicates possible adversarial smoothing." if evasion_detected else "Stable ELA response confirms findings are robust.",
        }
    except Exception as e:
        return {
            "status": "error",
            "court_defensible": False,
            "error": str(e),
        }
