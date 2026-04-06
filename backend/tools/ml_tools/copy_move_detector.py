#!/usr/bin/env python3
"""
copy_move_detector.py
=====================
Detects copy-move forgery using SIFT feature matching.

Copy-move forgery is when a region of an image is copied and pasted
elsewhere in the same image. This detector uses SIFT (Scale-Invariant
Feature Transform) to find matching keypoints at spatially distant
locations.

Usage:
    python copy_move_detector.py --input /path/to/image.jpg

Output JSON:
    {
        "copy_move_detected": true,
        "confidence": 0.85,
        "matched_pairs": 12,
        "top_pairs": [...],
        "available": true
    }
"""

import argparse
import json
import sys

import cv2
import numpy as np


def detect_copy_move(
    image_path: str,
    descriptor_distance_threshold: float = 50.0,
    spatial_distance_threshold: float = 30.0,
    min_pairs_for_detection: int = 5,
) -> dict:
    """
    Detect copy-move forgery in an image using SIFT feature matching.

    Args:
        image_path: Path to the image file
        descriptor_distance_threshold: Maximum descriptor distance for a match
        spatial_distance_threshold: Minimum spatial distance (pixels) to consider copy-move
        min_pairs_for_detection: Minimum matching pairs to flag as detected

    Returns:
        Dictionary with detection results
    """
    img = cv2.imread(image_path)
    if img is None:
        return {"error": "Cannot read image", "available": False}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Create SIFT detector
    try:
        sift = cv2.SIFT_create(nfeatures=2000)
    except cv2.error:
        # Fallback if SIFT is not available (patent issues in some OpenCV builds)
        return {
            "copy_move_detected": False,
            "confidence": 0.0,
            "matched_pairs": 0,
            "available": False,
            "error": "SIFT not available in this OpenCV build. Install opencv-contrib-python.",
        }

    kp, des = sift.detectAndCompute(gray, None)

    if des is None or len(kp) < 10:
        return {
            "copy_move_detected": False,
            "confidence": 0.0,
            "matched_pairs": 0,
            "available": True,
            "note": "Insufficient keypoints detected",
        }

    # Match descriptors against themselves using FLANN
    FLANN_INDEX_KDTREE = 1
    index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
    search_params = dict(checks=50)
    flann = cv2.FlannBasedMatcher(index_params, search_params)

    try:
        matches = flann.knnMatch(des, des, k=3)
    except Exception as e:
        return {
            "copy_move_detected": False,
            "confidence": 0.0,
            "matched_pairs": 0,
            "available": False,
            "error": f"FLANN matching failed: {str(e)}",
        }

    # Keep matches that are far spatially but close descriptively
    copy_move_pairs = []
    for m_list in matches:
        # Skip if we don't have enough matches
        if len(m_list) < 2:
            continue

        for m in m_list[1:]:  # skip self-match (index 0)
            if m.distance < descriptor_distance_threshold:
                pt1 = np.array(kp[m.queryIdx].pt)
                pt2 = np.array(kp[m.trainIdx].pt)
                spatial_dist = np.linalg.norm(pt1 - pt2)

                if spatial_dist > spatial_distance_threshold:
                    copy_move_pairs.append(
                        {
                            "from": [int(pt1[0]), int(pt1[1])],
                            "to": [int(pt2[0]), int(pt2[1])],
                            "descriptor_distance": float(m.distance),
                            "spatial_distance": float(spatial_dist),
                        }
                    )

    detected = len(copy_move_pairs) > min_pairs_for_detection
    confidence = min(0.95, len(copy_move_pairs) / 50.0)

    # Group pairs by spatial proximity to find copied regions
    if len(copy_move_pairs) > 0:
        # Sort by spatial distance to find the most significant matches
        copy_move_pairs.sort(key=lambda x: x["spatial_distance"], reverse=True)

    return {
        "copy_move_detected": detected,
        "confidence": round(confidence, 3),
        "matched_pairs": len(copy_move_pairs),
        "top_pairs": copy_move_pairs[:5],
        "descriptor_threshold": descriptor_distance_threshold,
        "spatial_threshold": spatial_distance_threshold,
        "available": True,
    }


def visualize_copy_move(image_path: str, output_path: str, pairs: list) -> bool:
    """
    Create a visualization of detected copy-move regions.

    Args:
        image_path: Path to input image
        output_path: Path to save visualization
        pairs: List of copy-move pairs from detect_copy_move()

    Returns:
        True if visualization was created successfully
    """
    img = cv2.imread(image_path)
    if img is None:
        return False

    # Draw lines between matched pairs
    vis_img = img.copy()
    colors = [
        (0, 0, 255),  # Red
        (0, 255, 0),  # Green
        (255, 0, 0),  # Blue
        (0, 255, 255),  # Yellow
        (255, 0, 255),  # Magenta
    ]

    for i, pair in enumerate(pairs[:10]):  # Visualize top 10 pairs
        color = colors[i % len(colors)]
        pt1 = tuple(pair["from"])
        pt2 = tuple(pair["to"])

        # Draw circles at keypoints
        cv2.circle(vis_img, pt1, 5, color, -1)
        cv2.circle(vis_img, pt2, 5, color, -1)

        # Draw line between them
        cv2.line(vis_img, pt1, pt2, color, 2)

    try:
        cv2.imwrite(output_path, vis_img)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Detect copy-move forgery")
    parser.add_argument("--input", type=str, help="Path to input image")
    parser.add_argument("--output", help="Path to save visualization")
    parser.add_argument(
        "--descriptor-threshold",
        type=float,
        default=50.0,
        help="Maximum descriptor distance for a match",
    )
    parser.add_argument(
        "--spatial-threshold",
        type=float,
        default=30.0,
        help="Minimum spatial distance (pixels) to consider copy-move",
    )
    parser.add_argument("--warmup", action="store_true", help="Warmup mode - preload dependencies")
    parser.add_argument("--worker", action="store_true", help="Worker mode - persistent process")
    args = parser.parse_args()

    # Warmup mode - verify dependencies load
    if args.warmup:
        try:
            import cv2
            import numpy as np
            print(json.dumps({
                "status": "warmed_up",
                "dependencies": ["cv2", "numpy"],
                "message": "Copy-move detector ready"
            }))
            sys.exit(0)
        except Exception as e:
            print(json.dumps({
                "status": "warmup_failed",
                "error": str(e)
            }))
            sys.exit(1)

    # Worker mode - persistent process reading from stdin
    if args.worker:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                input_path = request.get("input")

                if not input_path:
                    print(json.dumps({"error": "Missing input path", "available": False}))
                    sys.stdout.flush()
                    continue

                result = detect_copy_move(input_path)
                print(json.dumps(result))
                sys.stdout.flush()
            except Exception as e:
                print(json.dumps({"error": str(e), "available": False}))
                sys.stdout.flush()
        sys.exit(0)

    # Normal mode - single execution
    if not args.input:
        parser.print_help()
        sys.exit(1)

    try:
        result = detect_copy_move(
            args.input,
            descriptor_distance_threshold=args.descriptor_threshold,
            spatial_distance_threshold=args.spatial_threshold,
        )

        # Create visualization if requested and copy-move detected
        if args.output and result.get("copy_move_detected") and result.get("top_pairs"):
            success = visualize_copy_move(args.input, args.output, result["top_pairs"])
            result["visualization_created"] = success

    except Exception as e:
        result = {"error": str(e), "available": False}

    print(json.dumps(result))
