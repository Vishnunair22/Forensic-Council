"""
SIFT Core Engine.
================

Detects copy-move forgery through SIFT (Scale-Invariant Feature Transform) matching.
"""

import cv2
import numpy as np
from PIL import Image

from core.structured_logging import get_logger

logger = get_logger(__name__)

def detect_copy_move(file_path: str, n_features: int = 500) -> dict:
    """
    Detect image copy-move forgery via SIFT feature matching.

    Args:
        file_path: Path to the image file.
        n_features: Number of SIFT features to extract (default 500).

    Returns:
        dict: Copy-move metrics and detection status.
    """
    try:
        img = np.array(Image.open(file_path).convert("L"))
        sift = cv2.SIFT_create(nfeatures=n_features)
        kp, des = sift.detectAndCompute(img, None)

        if des is None or len(des) < 10:
            return {
                "copy_move_detected": False,
                "match_count": 0,
                "num_matches": 0,
                "keypoints_found": 0,
                "backend": "core-sift-engine",
                "court_defensible": True,
                "available": True,
            }

        # Simple BFMatcher (L2 distance) with crossCheck for duplicate detection
        bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=True)
        # Match features against themselves to find repetitive regions
        matches = bf.match(des, des)

        # Filter:
        # 1. queryIdx != trainIdx (not matching the same keypoint)
        # 2. Euclidean distance between pts > 30px (not a localized texture match)
        good_matches = [
            m for m in matches
            if m.queryIdx != m.trainIdx and
            np.linalg.norm(np.array(kp[m.queryIdx].pt) - np.array(kp[m.trainIdx].pt)) > 30
        ]

        # Threshold: if more than 10 non-localized matches, flag as potential copy-move
        copy_move_detected = len(good_matches) > 10

        return {
            "copy_move_detected": copy_move_detected,
            "match_count": len(good_matches),
            "num_matches": len(good_matches),
            "keypoints_found": len(kp),
            "backend": "core-sift-engine",
            "court_defensible": True,
            "available": True,
        }
    except Exception as e:
        logger.error(f"Copy-move detection failed: {e}", exc_info=True)
        return {
            "copy_move_detected": False,
            "match_count": 0,
            "error": str(e),
            "backend": "core-sift-engine",
            "court_defensible": False,
        }
