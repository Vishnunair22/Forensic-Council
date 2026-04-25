"""
Splicing Detection Core Engine.
===============================

Detects image splicing through DCT (Discrete Cosine Transform) inconsistency.
"""

import cv2
import numpy as np
from PIL import Image

from core.structured_logging import get_logger

logger = get_logger(__name__)


def detect_splicing(file_path: str) -> dict:
    """
    Detect image splicing via DCT block analysis.

    Args:
        file_path: Path to the image file.

    Returns:
        dict: Splicing metrics and detection status.
    """
    try:
        img = np.array(Image.open(file_path).convert("L"))
        h, w = img.shape
        q_vals = []
        for y in range(0, h - 8, 8):
            for x in range(0, w - 8, 8):
                block = img[y : y + 8, x : x + 8].astype(np.float32)
                dct = cv2.dct(block)
                # Analyzing high-frequency coefficients (bottom-right 4x4)
                q_vals.append(float(np.abs(dct[4:, 4:]).mean()))

        total_blocks = len(q_vals)
        if q_vals:
            mean_q = np.mean(q_vals)
            std_q = np.std(q_vals)
            # Inconsistent = block Q-value > 2x standard deviation from mean
            inconsistent = int(sum(1 for v in q_vals if abs(v - mean_q) > 2 * std_q))
        else:
            inconsistent = 0

        splicing_detected = total_blocks > 0 and (inconsistent / total_blocks) > 0.15

        return {
            "splicing_detected": splicing_detected,
            "num_inconsistent_blocks": inconsistent,
            "total_blocks": total_blocks,
            "inconsistency_ratio": round(inconsistent / total_blocks, 3) if total_blocks else 0,
            "backend": "core-dct-splicing-engine",
            "court_defensible": True,
            "available": True,
        }
    except Exception as e:
        logger.error(f"Splicing detection failed: {e}", exc_info=True)
        return {
            "splicing_detected": False,
            "error": str(e),
            "backend": "core-dct-splicing-engine",
            "court_defensible": False,
        }
