#!/usr/bin/env python3
"""
noise_fingerprint.py
====================
Detects camera noise fingerprint inconsistencies across image regions.
A region from a different source will have a different PRNU signature.

Usage:
    python noise_fingerprint.py --input /path/to/image.jpg [--regions 6]

Output JSON:
    {
        "inconsistent_regions": [[x, y, w, h], ...],
        "noise_consistency_score": 0.91,   # 1.0 = perfectly consistent
        "outlier_region_count": 0,
        "total_regions": 6,
        "verdict": "CONSISTENT",            # CONSISTENT | INCONSISTENT | INCONCLUSIVE
        "available": true
    }
"""

import argparse
import json
import numpy as np
import cv2
from scipy.signal import wiener


def extract_noise_residual(region: np.ndarray) -> np.ndarray:
    """Extract noise residual using Wiener filter denoising."""
    region_f = region.astype(np.float32)
    # Wiener filter as denoising model — residual is noise fingerprint
    try:
        denoised = wiener(region_f, mysize=3)
        noise = region_f - denoised
    except Exception:
        noise = region_f - cv2.GaussianBlur(region_f, (3, 3), 0)
    return noise


def get_noise_features(region: np.ndarray) -> np.ndarray:
    """Summarize PRNU noise pattern of a region."""
    noise = extract_noise_residual(region)
    return np.array([
        float(np.mean(noise)),
        float(np.std(noise)),
        float(np.mean(np.abs(noise))),
        float(np.percentile(noise, 25)),
        float(np.percentile(noise, 75)),
        float(np.mean(noise ** 2)),            # noise power
        float(np.corrcoef(noise.flatten()[:100], noise.flatten()[1:101])[0, 1] if len(noise.flatten()) > 101 else 0.0),
    ], dtype=np.float32)


def analyze_noise_fingerprint(image_path: str, num_regions: int = 6) -> dict:
    from sklearn.ensemble import IsolationForest

    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return {"error": "Cannot read image", "available": False}

    h, w = img.shape
    if h < 100 or w < 100:
        return {
            "inconsistent_regions": [], "noise_consistency_score": 1.0,
            "outlier_region_count": 0, "total_regions": 0,
            "verdict": "INCONCLUSIVE", "available": True,
            "note": "Image too small",
        }

    # Divide image into a grid of regions
    rows = int(num_regions ** 0.5)
    cols = (num_regions + rows - 1) // rows
    rh, rw = h // rows, w // cols

    region_features = []
    region_coords = []

    for r in range(rows):
        for c in range(cols):
            y0, x0 = r * rh, c * rw
            region = img[y0:y0+rh, x0:x0+rw]
            if region.size > 0:
                feats = get_noise_features(region)
                region_features.append(feats)
                region_coords.append((int(x0), int(y0), int(rw), int(rh)))

    if len(region_features) < 4:
        return {
            "inconsistent_regions": [], "noise_consistency_score": 1.0,
            "outlier_region_count": 0, "total_regions": len(region_features),
            "verdict": "INCONCLUSIVE", "available": True,
        }

    X = np.array(region_features)
    clf = IsolationForest(contamination=0.15, random_state=42, n_estimators=30)
    clf.fit(X)
    labels = clf.predict(X)
    scores = clf.decision_function(X)

    outlier_idx = [i for i, l in enumerate(labels) if l == -1]
    inconsistent_regions = [list(region_coords[i]) for i in outlier_idx]

    consistency_score = 1.0 - (len(outlier_idx) / len(region_features))

    if len(outlier_idx) == 0:
        verdict = "CONSISTENT"
    elif len(outlier_idx) <= 1:
        verdict = "INCONCLUSIVE"   # borderline — single outlier region
    else:
        verdict = "INCONSISTENT"   # multiple outlier regions = clear tampering signal

    return {
        "inconsistent_regions": inconsistent_regions,
        "noise_consistency_score": round(consistency_score, 3),
        "outlier_region_count": len(outlier_idx),
        "total_regions": len(region_features),
        "verdict": verdict,
        "available": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--regions", type=int, default=6)
    args = parser.parse_args()

    try:
        result = analyze_noise_fingerprint(args.input, args.regions)
    except Exception as e:
        result = {"error": str(e), "available": False}

    print(json.dumps(result))
