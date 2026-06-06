#!/usr/bin/env python3
"""
busternet_v2.py
===============
BusterNet dual-branch copy-move forgery detector.

BusterNet (Wu et al., 2018) uses two parallel CNN branches:
  • Manipulation branch — finds locally anomalous regions via self-correlation
  • Similarity branch  — finds self-similar (cloned) region pairs

This implementation replicates the two-branch logic using classical feature
descriptors + a dedicated noise-fingerprint cross-correlation branch:

  Branch A (Similarity): ORB feature matching + RANSAC homography verification.
    ORB is rotation/scale invariant and faster than SIFT for this task.
    RANSAC rejects random matches, leaving only geometrically consistent pairs.

  Branch B (Manipulation): Local noise self-correlation analysis.
    Computes Noise Consistency Map (NCM) — regions where the noise pattern
    correlates with another region of the same image signal copy-paste.

  Fusion: Both branches must agree (or one with very high confidence) to
  report a detection.  This dramatically reduces false-positive rate.

Output schema (compatible with neural_copy_move / copy_move_detect fallback):
    {
        "copy_move_detected": true,
        "confidence": 0.87,
        "matched_pairs": 18,
        "top_pairs": [{"from": [x1,y1], "to": [x2,y2], "distance": 12.3}, ...],
        "homography_inliers": 14,
        "noise_correlation_signal": 0.72,
        "branch_agreement": "BOTH",
        "available": true,
        "court_defensible": true,
        "model_version": "busternet_v2"
    }

Usage:
    python busternet_v2.py --input /path/to/image.jpg
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import cv2
import numpy as np
from scipy.signal import wiener

# ---------------------------------------------------------------------------
# Branch A: ORB + RANSAC similarity branch
# ---------------------------------------------------------------------------


def _branch_similarity(gray: np.ndarray) -> dict[str, Any]:
    """
    Find self-similar (copy-moved) region pairs via ORB + RANSAC.

    Returns dict with: matched_pairs, top_pairs, homography_inliers,
    copy_move_detected, confidence_a.
    """
    try:
        orb = cv2.ORB_create(nfeatures=3000, scaleFactor=1.2, nlevels=8)
    except Exception:
        return {
            "copy_move_detected": False,
            "matched_pairs": 0,
            "top_pairs": [],
            "homography_inliers": 0,
            "confidence_a": 0.0,
            "error": "ORB unavailable",
        }

    kp, des = orb.detectAndCompute(gray, None)

    if des is None or len(kp) < 15:
        return {
            "copy_move_detected": False,
            "matched_pairs": 0,
            "top_pairs": [],
            "homography_inliers": 0,
            "confidence_a": 0.0,
        }

    # BF matcher with Hamming distance for ORB binary descriptors
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    try:
        matches = bf.knnMatch(des, des, k=3)
    except Exception:
        return {
            "copy_move_detected": False,
            "matched_pairs": 0,
            "top_pairs": [],
            "homography_inliers": 0,
            "confidence_a": 0.0,
        }

    # Keep feature-similar, spatially-distant candidate pairs
    min_spatial_dist = max(40, min(gray.shape) * 0.08)
    candidate_pairs: list[dict] = []

    for m_list in matches:
        if len(m_list) < 2:
            continue
        for m in m_list[1:]:  # skip self-match (nearest neighbour is itself)
            if m.distance > 50:  # ORB Hamming: require tight descriptor similarity
                continue
            pt1 = np.array(kp[m.queryIdx].pt)
            pt2 = np.array(kp[m.trainIdx].pt)
            spatial_dist = float(np.linalg.norm(pt1 - pt2))
            if spatial_dist > min_spatial_dist:
                candidate_pairs.append(
                    {
                        "from": [int(pt1[0]), int(pt1[1])],
                        "to": [int(pt2[0]), int(pt2[1])],
                        "dx": int(pt2[0] - pt1[0]),
                        "dy": int(pt2[1] - pt1[1]),
                        "distance": round(float(m.distance), 2),
                        "spatial_dist": round(spatial_dist, 1),
                    }
                )

    # Offset-vector clustering. A genuine copy-move is a CLUSTER of matched pairs
    # that all share ONE translation offset (the clone displacement); random
    # self-similar-texture matches scatter across many offsets. The previous
    # method fit a single RANSAC homography to ALL candidate pairs, which fit
    # texture noise on clean images (false positives) yet missed small clones
    # (validated: it flagged a clean photo and missed an actual copy-move).
    # Clustering offsets is the standard, discriminative copy-move test.
    _OFFSET_BIN = 10  # px tolerance for treating two offsets as "the same"
    offset_clusters: dict[tuple[int, int], list[dict]] = {}
    for p in candidate_pairs:
        key = (round(p["dx"] / _OFFSET_BIN), round(p["dy"] / _OFFSET_BIN))
        offset_clusters.setdefault(key, []).append(p)
    dominant = max(offset_clusters.values(), key=len) if offset_clusters else []
    cluster_size = len(dominant)

    _MIN_OFFSET_CLUSTER = 8  # pairs sharing one offset to call a clone
    detected = cluster_size >= _MIN_OFFSET_CLUSTER
    dominant.sort(key=lambda x: -x["spatial_dist"])
    top_pairs = [
        {"from": p["from"], "to": p["to"], "distance": p["distance"]} for p in dominant[:8]
    ]
    conf_a = (
        min(1.0, 0.45 + cluster_size / 30.0)
        if detected
        else min(0.2, cluster_size / 40.0)
    )

    return {
        "copy_move_detected": detected,
        "matched_pairs": len(candidate_pairs),
        "offset_cluster_size": cluster_size,
        "top_pairs": top_pairs,
        "homography_inliers": cluster_size,  # consistent-offset pairs (fusion compat)
        "confidence_a": round(float(conf_a), 3),
    }


# ---------------------------------------------------------------------------
# Branch B: Noise self-correlation manipulation branch
# ---------------------------------------------------------------------------


def _branch_manipulation(gray: np.ndarray) -> dict[str, Any]:
    """
    Detect copy-move via noise self-correlation (Noise Consistency Map).

    A pasted region carries the noise fingerprint of its source, not the
    destination image.  Cross-correlating the Wiener residual of each tile
    against the full-image residual reveals anomalously high matches.
    """
    gray_f = gray.astype(np.float32)
    try:
        residual = gray_f - wiener(gray_f, mysize=5).astype(np.float32)
    except Exception:
        residual = gray_f - cv2.GaussianBlur(gray_f, (5, 5), 0)

    h, w = residual.shape
    tile_size = max(32, min(h, w) // 8)

    high_corr_tiles: list[tuple[int, int]] = []
    corr_values: list[float] = []

    # Full-image residual normalized
    res_norm = residual / (np.std(residual) + 1e-9)

    for r in range(0, h - tile_size + 1, tile_size):
        for c in range(0, w - tile_size + 1, tile_size):
            tile_res = residual[r : r + tile_size, c : c + tile_size]
            tile_norm = tile_res / (np.std(tile_res) + 1e-9)

            # Normalized cross-correlation between tile and full-image residual
            try:
                result = cv2.matchTemplate(
                    res_norm.astype(np.float32),
                    tile_norm.astype(np.float32),
                    cv2.TM_CCOEFF_NORMED,
                )
                _, max_val, _, max_loc = cv2.minMaxLoc(result)
                best_match_x, best_match_y = max_loc

                # Ignore self-match (same tile position)
                dist_to_self = float(np.sqrt((best_match_x - c) ** 2 + (best_match_y - r) ** 2))
                if dist_to_self > tile_size * 0.5 and max_val > 0.65:
                    high_corr_tiles.append((c, r))
                    corr_values.append(float(max_val))
            except Exception:
                continue

    correlation_signal = float(np.mean(corr_values)) if corr_values else 0.0
    detected_b = len(high_corr_tiles) >= 2 and correlation_signal > 0.70
    conf_b = min(1.0, correlation_signal * (len(high_corr_tiles) / max(5.0, 1.0)))

    return {
        "noise_correlation_signal": round(correlation_signal, 3),
        "high_corr_tile_count": len(high_corr_tiles),
        "copy_move_detected_b": detected_b,
        "confidence_b": round(float(conf_b), 3),
    }


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------


def analyze(image_path: str) -> dict[str, Any]:
    img = cv2.imread(image_path)
    if img is None:
        return {"error": "Cannot read image", "available": False}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    if h < 64 or w < 64:
        return {
            "copy_move_detected": False,
            "confidence": 0.0,
            "matched_pairs": 0,
            "top_pairs": [],
            "homography_inliers": 0,
            "noise_correlation_signal": 0.0,
            "branch_agreement": "NEITHER",
            "available": True,
            "court_defensible": False,
            "note": "Image too small",
            "model_version": "busternet_v2",
        }

    a = _branch_similarity(gray)
    b = _branch_manipulation(gray)
    det_a = a.get("copy_move_detected", False)
    det_b = b.get("copy_move_detected_b", False)

    # SCREENING-TIER, NON-ASSERTING. Classical keypoint/noise copy-move heuristics
    # provably cannot separate a clone from legitimate repeated content: validation
    # showed clean images with repeated structure (evenly-spaced objects, room
    # tiles) produce LARGER consistent-offset / self-correlation clusters than an
    # actual copy-move, at every threshold — so any standalone "detected=True" bar
    # false-positives on normal photos before it catches a real clone. Copy-move
    # localization is therefore delegated to the trained TruFor model (run as
    # neural_splicing, which localizes cloned regions too). This tool reports its
    # raw branch signals for transparency but does NOT assert a manipulation
    # verdict on its own and is not court-defensible.
    branch_agreement = "BOTH" if (det_a and det_b) else ("SIMILARITY" if det_a else ("NOISE" if det_b else "NEITHER"))
    copy_move_detected = False
    confidence = 0.0

    return {
        "copy_move_detected": copy_move_detected,
        "confidence": confidence,
        "matched_pairs": a.get("matched_pairs", 0),
        "offset_cluster_size": a.get("offset_cluster_size", 0),
        "top_pairs": a.get("top_pairs", []),
        "homography_inliers": a.get("homography_inliers", 0),
        "noise_correlation_signal": b.get("noise_correlation_signal", 0.0),
        "branch_agreement": branch_agreement,
        "screening_note": "Copy-move localization is provided by the TruFor model (neural_splicing); this classical heuristic is screening-only and does not assert a standalone verdict.",
        "available": True,
        "court_defensible": False,
        "model_version": "busternet_v3_screening",
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _run_worker() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            input_path = req.get("input")
            if not input_path:
                print(json.dumps({"error": "Missing input path", "available": False}))
                sys.stdout.flush()
                continue
            result = analyze(input_path)
        except Exception as exc:
            result = {"error": str(exc), "available": False}
        print(json.dumps(result))
        sys.stdout.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BusterNet v2 — dual-branch copy-move detector")
    parser.add_argument("--input", type=str, help="Path to input image")
    parser.add_argument("--warmup", action="store_true", help="Warmup mode")
    parser.add_argument(
        "--worker", action="store_true", help="Worker mode (persistent stdin/stdout)"
    )
    args = parser.parse_args()

    if args.warmup:
        try:
            import cv2  # noqa: F401
            import numpy  # noqa: F401
            from scipy.signal import wiener  # noqa: F401

            print(
                json.dumps(
                    {
                        "status": "warmed_up",
                        "dependencies": ["cv2", "numpy", "scipy"],
                        "message": "BusterNet v2 ready",
                    }
                )
            )
            sys.exit(0)
        except Exception as exc:
            print(json.dumps({"status": "warmup_failed", "error": str(exc)}))
            sys.exit(1)

    if args.worker:
        _run_worker()
        sys.exit(0)

    if not args.input:
        parser.print_help()
        sys.exit(1)

    try:
        result = analyze(args.input)
    except Exception as exc:
        result = {"error": str(exc), "available": False}

    print(json.dumps(result))
