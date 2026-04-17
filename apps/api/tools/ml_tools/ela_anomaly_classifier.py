#!/usr/bin/env python3
"""
ela_anomaly_classifier.py
=========================
Classifies ELA anomaly regions using an IsolationForest trained on the
image's own DCT block statistics. No external model download required.

Usage:
    python ela_anomaly_classifier.py --input /path/to/image.jpg [--quality 95]

Output JSON:
    {
        "verdict": "SUSPICIOUS",          # NORMAL | SUSPICIOUS | HIGHLY_ANOMALOUS
        "anomaly_score": 0.73,            # 0-1, higher = more anomalous
        "num_anomalous_blocks": 12,
        "total_blocks_analyzed": 240,
        "anomalous_block_positions": [[x,y], ...],  # top 10
        "ela_max": 18.4,
        "ela_mean": 3.2,
        "available": true
    }
"""

import argparse
import io
import json
import sys

import cv2
import numpy as np
from PIL import Image


def extract_dct_features(block: np.ndarray) -> np.ndarray:
    """Extract DCT coefficient statistics from a 16x16 block."""
    if block.shape != (16, 16):
        block = cv2.resize(block, (16, 16))
    block_f = block.astype(np.float32)
    dct = cv2.dct(block_f)
    return np.array(
        [
            float(dct[0, 0]),  # DC coefficient
            float(np.mean(np.abs(dct[1:4, 1:4]))),  # low-freq AC
            float(np.mean(np.abs(dct[4:, 4:]))),  # high-freq AC
            float(np.std(dct)),
            float(np.max(np.abs(dct[1:, 1:]))),
        ],
        dtype=np.float32,
    )


def run_ela(image_path: str, quality: int = 95) -> np.ndarray:
    """Compute ELA array from image."""
    orig = Image.open(image_path).convert("RGB")
    buf = io.BytesIO()
    orig.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    recompressed = Image.open(buf).convert("RGB")

    orig_arr = np.array(orig, dtype=np.float32)
    recomp_arr = np.array(recompressed, dtype=np.float32)
    ela = np.abs(orig_arr - recomp_arr)
    return ela.mean(axis=2)  # average across RGB channels


def classify_ela(image_path: str, quality: int = 95) -> dict:
    from sklearn.ensemble import IsolationForest

    ela_map = run_ela(image_path, quality)
    h, w = ela_map.shape
    block_size = 16

    blocks = []
    positions = []

    for y in range(0, h - block_size, block_size):
        for x in range(0, w - block_size, block_size):
            block = ela_map[y : y + block_size, x : x + block_size]
            feats = extract_dct_features(block)
            blocks.append(feats)
            positions.append((x, y))

    if len(blocks) < 20:
        return {
            "verdict": "INCONCLUSIVE",
            "anomaly_score": 0.0,
            "num_anomalous_blocks": 0,
            "total_blocks_analyzed": len(blocks),
            "anomalous_block_positions": [],
            "ela_max": float(ela_map.max()),
            "ela_mean": float(ela_map.mean()),
            "available": True,
            "note": "Image too small for block analysis",
        }

    X = np.array(blocks)

    # Train on all blocks — outliers are the anomalous ones
    clf = IsolationForest(contamination=0.1, random_state=42, n_estimators=50)
    clf.fit(X)

    scores = clf.decision_function(X)  # lower = more anomalous
    labels = clf.predict(X)  # -1 = anomaly, 1 = normal

    anomalous_idx = np.where(labels == -1)[0]
    num_anomalous = len(anomalous_idx)

    # Normalize anomaly score to 0-1
    score_range = scores.max() - scores.min()
    if score_range > 0:
        normalized = 1.0 - (scores.min() - scores) / score_range
        anomaly_score = (
            float(np.mean(normalized[anomalous_idx])) if len(anomalous_idx) > 0 else 0.0
        )
    else:
        anomaly_score = 0.0

    ratio = num_anomalous / len(blocks)
    if ratio > 0.15 or (ela_map.max() > 25 and ratio > 0.05):
        verdict = "HIGHLY_ANOMALOUS"
    elif ratio > 0.05 or ela_map.max() > 12:
        verdict = "SUSPICIOUS"
    else:
        verdict = "NORMAL"

    top_positions = [list(positions[i]) for i in anomalous_idx[:10].tolist()]

    return {
        "verdict": verdict,
        "anomaly_score": round(anomaly_score, 4),
        "num_anomalous_blocks": int(num_anomalous),
        "total_blocks_analyzed": len(blocks),
        "anomalous_block_positions": top_positions,
        "ela_max": round(float(ela_map.max()), 3),
        "ela_mean": round(float(ela_map.mean()), 3),
        "available": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, help="Input image path")
    parser.add_argument("--quality", type=int, default=95, help="JPEG quality for ELA")
    parser.add_argument("--warmup", action="store_true", help="Warmup mode - preload dependencies")
    parser.add_argument("--worker", action="store_true", help="Worker mode - persistent process")
    args = parser.parse_args()

    # Warmup mode - just verify dependencies load
    if args.warmup:
        try:
            import cv2
            import numpy as np
            print(json.dumps({
                "status": "warmed_up",
                "dependencies": ["sklearn", "numpy", "cv2", "PIL"],
                "message": "ELA anomaly classifier ready"
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
                quality = request.get("extra_args", [95])[0] if request.get("extra_args") else 95

                if not input_path:
                    print(json.dumps({"error": "Missing input path", "available": False}))
                    sys.stdout.flush()
                    continue

                result = classify_ela(input_path, int(quality))
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
        result = classify_ela(args.input, args.quality)
    except Exception as e:
        result = {"error": str(e), "available": False}

    print(json.dumps(result))
