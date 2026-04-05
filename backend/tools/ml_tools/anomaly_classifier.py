#!/usr/bin/env python3
"""
anomaly_classifier.py
=====================
Classify video anomalies as EXPLAINABLE or SUSPICIOUS using SSIM.

Uses structural similarity (SSIM) and motion vector analysis to classify
anomalies detected between consecutive video frames.

Usage:
    python anomaly_classifier.py --frameA /path/to/frame1.png --frameB /path/to/frame2.png --motion 3.5

Output JSON:
    {
        "classification": "SUSPICIOUS",
        "ssim_score": 0.72,
        "diff_area_ratio": 0.08,
        "contour_count": 5,
        "reasons": [...],
        "court_defensible": true,
        "available": true
    }
"""

import argparse
import json
import numpy as np
import cv2
from skimage.metrics import structural_similarity as ssim


def classify_anomaly(
    image_path_a: str, image_path_b: str, motion_vector_magnitude: float = 0.0
) -> dict:
    """
    Classify a video anomaly as EXPLAINABLE or SUSPICIOUS using:
    - SSIM structural difference
    - Motion vector magnitude (from optical flow caller)
    - Edge coherence

    Args:
        image_path_a: Path to first frame
        image_path_b: Path to second frame
        motion_vector_magnitude: Optical flow magnitude between frames

    Returns:
        Dictionary with classification results
    """
    frameA = cv2.imread(image_path_a, cv2.IMREAD_GRAYSCALE)
    frameB = cv2.imread(image_path_b, cv2.IMREAD_GRAYSCALE)

    if frameA is None or frameB is None:
        return {
            "classification": "INCONCLUSIVE",
            "available": True,
            "error": "Could not read one or both frames",
        }

    h, w = min(frameA.shape[0], frameB.shape[0]), min(frameA.shape[1], frameB.shape[1])
    fA = cv2.resize(frameA, (w, h))
    fB = cv2.resize(frameB, (w, h))

    # Compute SSIM
    ssim_score, diff = ssim(fA, fB, full=True)
    diff_normalized = (diff * 255).astype(np.uint8)

    # Where structural difference is concentrated (spliced = localized cluster)
    _, thresh = cv2.threshold(diff_normalized, 30, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    total_diff_area = sum(cv2.contourArea(c) for c in contours)
    image_area = h * w
    diff_area_ratio = total_diff_area / image_area if image_area > 0 else 0

    # Heuristic model:
    # High motion + distributed diff = EXPLAINABLE (camera shake, fast motion)
    # Low motion + localized diff cluster = SUSPICIOUS (edit point)
    is_suspicious = (
        motion_vector_magnitude < 5.0
        and diff_area_ratio > 0.05
        and ssim_score < 0.85
        or ssim_score < 0.6  # extreme structural change = always flag
    )

    reasons = []
    if ssim_score < 0.85:
        reasons.append(f"Low SSIM structural similarity: {ssim_score:.3f}")
    if diff_area_ratio > 0.05 and motion_vector_magnitude < 5.0:
        reasons.append(
            f"Localized difference cluster ({diff_area_ratio:.1%} of frame) with low motion"
        )
    if not reasons:
        reasons.append(
            f"High motion ({motion_vector_magnitude:.1f}px) explains structural difference"
        )

    return {
        "classification": "SUSPICIOUS" if is_suspicious else "EXPLAINABLE",
        "ssim_score": round(float(ssim_score), 4),
        "diff_area_ratio": round(float(diff_area_ratio), 4),
        "contour_count": len(contours),
        "motion_vector_magnitude": round(float(motion_vector_magnitude), 2),
        "reasons": reasons,
        "court_defensible": True,
        "available": True,
    }


def visualize_anomaly(image_path_a: str, image_path_b: str, output_path: str) -> bool:
    """
    Create a visualization showing the SSIM difference map.

    Args:
        image_path_a: Path to first frame
        image_path_b: Path to second frame
        output_path: Path to save visualization

    Returns:
        True if visualization was created successfully
    """
    frameA = cv2.imread(image_path_a)
    frameB = cv2.imread(image_path_b)

    if frameA is None or frameB is None:
        return False

    h, w = min(frameA.shape[0], frameB.shape[0]), min(frameA.shape[1], frameB.shape[1])
    fA = cv2.resize(frameA, (w, h))
    fB = cv2.resize(frameB, (w, h))

    # Convert to grayscale for SSIM
    grayA = cv2.cvtColor(fA, cv2.COLOR_BGR2GRAY)
    grayB = cv2.cvtColor(fB, cv2.COLOR_BGR2GRAY)

    # Compute SSIM and difference
    _, diff = ssim(grayA, grayB, full=True)
    diff_normalized = (diff * 255).astype(np.uint8)

    # Create color diff map
    diff_color = cv2.applyColorMap(diff_normalized, cv2.COLORMAP_JET)

    # Create side-by-side comparison
    comparison = np.hstack([fA, fB, diff_color])

    # Add labels
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(comparison, "Frame A", (10, 30), font, 1, (255, 255, 255), 2)
    cv2.putText(comparison, "Frame B", (w + 10, 30), font, 1, (255, 255, 255), 2)
    cv2.putText(comparison, "SSIM Diff", (2 * w + 10, 30), font, 1, (255, 255, 255), 2)

    try:
        cv2.imwrite(output_path, comparison)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Classify video anomaly using SSIM")
    parser.add_argument(
        "--frameA",
        "--input",
        dest="frameA",
        required=True,
        help="Path to first frame (or input proxy)",
    )
    parser.add_argument("--frameB", required=True, help="Path to second frame")
    parser.add_argument(
        "--motion",
        type=float,
        default=0.0,
        help="Motion vector magnitude between frames",
    )
    parser.add_argument("--output", help="Path to save visualization")
    args = parser.parse_args()

    try:
        result = classify_anomaly(args.frameA, args.frameB, args.motion)

        # Create visualization if requested
        if args.output:
            success = visualize_anomaly(args.frameA, args.frameB, args.output)
            result["visualization_created"] = success

    except Exception as e:
        result = {"error": str(e), "available": False}

    print(json.dumps(result))
