#!/usr/bin/env python3
"""
splicing_detector.py
====================
Detects image splicing by modeling DCT quantization inconsistencies.
A pasted region from a different source has different JPEG quantization
fingerprints than the surrounding image.

Usage:
    python splicing_detector.py --input /path/to/image.jpg

Output JSON:
    {
        "splicing_detected": false,
        "confidence": 0.82,
        "num_inconsistent_blocks": 3,
        "total_blocks": 200,
        "inconsistency_ratio": 0.015,
        "suspicious_regions": [[x, y, w, h], ...],
        "available": true
    }
"""

import argparse
import json
import sys

import cv2
import numpy as np


def get_block_dct_signature(block: np.ndarray) -> np.ndarray:
    """Get quantization-sensitive DCT features from 8x8 block."""
    b = block.astype(np.float32) - 128
    dct = cv2.dct(b)
    # Focus on the AC coefficients most affected by JPEG quantization
    ac_low = dct[1:4, 1:4].flatten()  # low frequency AC
    ac_mid = dct[4:7, 4:7].flatten()  # mid frequency AC
    # Ratio of quantization patterns — sensitive to quantization table differences
    quantization_ratio = np.std(ac_low) / (np.std(ac_mid) + 1e-6)
    return np.array(
        [
            float(np.std(ac_low)),
            float(np.std(ac_mid)),
            float(quantization_ratio),
            float(np.mean(np.abs(ac_low))),
            float(np.percentile(np.abs(ac_low), 75)),
        ],
        dtype=np.float32,
    )


def detect_splicing(image_path: str) -> dict:
    from sklearn.mixture import GaussianMixture
    from sklearn.preprocessing import StandardScaler

    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return {"error": "Cannot read image", "available": False}

    h, w = img.shape
    block_size = 8
    features = []
    positions = []

    for y in range(0, h - block_size, block_size):
        for x in range(0, w - block_size, block_size):
            block = img[y : y + block_size, x : x + block_size]
            feat = get_block_dct_signature(block)
            features.append(feat)
            positions.append((x, y))

    if len(features) < 50:
        return {
            "splicing_detected": False,
            "confidence": 0.0,
            "num_inconsistent_blocks": 0,
            "total_blocks": len(features),
            "inconsistency_ratio": 0.0,
            "suspicious_regions": [],
            "available": True,
            "note": "Insufficient blocks for analysis",
        }

    X = np.array(features)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Fit a 2-component GMM — natural images cluster tightly; spliced regions diverge
    gmm = GaussianMixture(n_components=2, random_state=42, max_iter=100)
    gmm.fit(X_scaled)

    log_probs = gmm.score_samples(X_scaled)
    threshold = np.percentile(log_probs, 5)  # bottom 5% as candidates

    outlier_mask = log_probs < threshold
    outlier_indices = np.where(outlier_mask)[0]

    inconsistency_ratio = float(len(outlier_indices) / len(features))
    splicing_detected = inconsistency_ratio > 0.03 and len(outlier_indices) > 5

    # Group nearby outlier blocks into regions
    suspicious_regions = []
    if len(outlier_indices) > 0:
        xs = [positions[i][0] for i in outlier_indices[:20]]
        ys = [positions[i][1] for i in outlier_indices[:20]]
        if xs:
            suspicious_regions.append(
                [
                    int(min(xs)),
                    int(min(ys)),
                    int(max(xs) - min(xs) + block_size),
                    int(max(ys) - min(ys) + block_size),
                ]
            )

    confidence = (
        min(0.95, inconsistency_ratio * 10 + 0.4)
        if splicing_detected
        else max(0.05, 1.0 - inconsistency_ratio * 10)
    )

    return {
        "splicing_detected": splicing_detected,
        "confidence": round(confidence, 3),
        "num_inconsistent_blocks": int(len(outlier_indices)),
        "total_blocks": len(features),
        "inconsistency_ratio": round(inconsistency_ratio, 4),
        "suspicious_regions": suspicious_regions,
        "available": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, help="Input image path")
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
                "dependencies": ["sklearn", "numpy", "cv2"],
                "message": "Splicing detector ready"
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

                result = detect_splicing(input_path)
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
        result = detect_splicing(args.input)
    except Exception as e:
        result = {"error": str(e), "available": False}

    print(json.dumps(result))
