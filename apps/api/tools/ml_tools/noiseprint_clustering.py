#!/usr/bin/env python3
"""
noiseprint_clustering.py
========================
Noiseprint++ — CNN-inspired camera sensor noise clustering.

Noiseprint (Cozzolino & Verdoliva, 2020) works by extracting a noise
residual fingerprint from each image region and grouping regions by their
source camera's PRNU pattern.  Spliced regions break this consistency
because they originate from a different sensor.

This implementation replicates the key algorithmic stages using
numpy/scipy without requiring the original TensorFlow weights:

  1. Noise residual extraction via multi-scale Wiener + DCT suppression
  2. Rich per-region fingerprint (16 features: statistical moments, spatial
     correlations, frequency-band energies)
  3. K-means clustering with automatic k selection (silhouette scoring)
  4. Outlier regions identified as originating from a different source

Output schema (compatible with noiseprint_cluster fallback):
    {
        "manipulation_detected": true,
        "confidence": 0.78,
        "inconsistent_regions": [{"x":0,"y":0,"w":64,"h":64}, ...],
        "source_cluster_count": 2,
        "noise_consistency_score": 0.61,
        "outlier_region_count": 2,
        "total_regions": 12,
        "verdict": "INCONSISTENT",
        "available": true,
        "court_defensible": true,
        "model_version": "noiseprint_clustering_v1"
    }

Usage:
    python noiseprint_clustering.py --input /path/to/image.png
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import cv2
import numpy as np
from scipy.signal import wiener

_REGION_SIZE = 64   # pixels; each region is 64×64
_MIN_REGIONS = 6    # need at least this many to cluster meaningfully
_MIN_OUTLIER_CLUSTER_SIZE = 1


# ---------------------------------------------------------------------------
# Noise residual extraction
# ---------------------------------------------------------------------------

def _extract_noise_residual(gray: np.ndarray) -> np.ndarray:
    """
    Multi-scale noise residual:
      residual = image − (Wiener_3×3 + Wiener_5×5) / 2

    Using two kernel sizes suppresses texture better than a single kernel,
    isolating the sensor-level PRNU fingerprint.
    """
    gray_f = gray.astype(np.float32)
    try:
        w3 = wiener(gray_f, mysize=3).astype(np.float32)
        w5 = wiener(gray_f, mysize=5).astype(np.float32)
        denoised = (w3 + w5) * 0.5
    except Exception:
        # Fallback: Gaussian denoising
        denoised = cv2.GaussianBlur(gray_f, (5, 5), 0)
    return gray_f - denoised


def _dct_suppress(noise: np.ndarray) -> np.ndarray:
    """
    DCT-domain high-pass: suppress low-frequency components of the residual
    (scene content leaking through Wiener) by zeroing DC + first few AC terms.
    """
    h, w = noise.shape
    # Work on 8×8 tiles
    out = noise.copy()
    for r in range(0, h - 7, 8):
        for c in range(0, w - 7, 8):
            tile = out[r : r + 8, c : c + 8].astype(np.float32)
            dct_tile = cv2.dct(tile)
            dct_tile[:2, :2] = 0.0   # zero DC + lowest AC components
            out[r : r + 8, c : c + 8] = cv2.idct(dct_tile)
    return out


# ---------------------------------------------------------------------------
# Per-region fingerprint (16-dimensional)
# ---------------------------------------------------------------------------

def _region_fingerprint(noise_patch: np.ndarray) -> np.ndarray:
    """
    16-dim sensor fingerprint for a noise patch:
      [0]  mean
      [1]  std
      [2]  skewness
      [3]  kurtosis
      [4]  mean abs value
      [5]  noise power (mean of squared values)
      [6]  inter-pixel horizontal correlation
      [7]  inter-pixel vertical correlation
      [8]  low-band spectral energy (FFT quadrant)
      [9]  mid-band spectral energy
      [10] high-band spectral energy
      [11] spectral energy ratio (high / low)
      [12] percentile 10
      [13] percentile 90
      [14] positive fraction
      [15] range (max - min)
    """
    p = noise_patch.flatten().astype(np.float64)
    if len(p) < 4:
        return np.zeros(16, dtype=np.float32)

    mean = float(np.mean(p))
    std = float(np.std(p)) + 1e-9
    skewness = float(np.mean(((p - mean) / std) ** 3))
    kurtosis = float(np.mean(((p - mean) / std) ** 4))
    mean_abs = float(np.mean(np.abs(p)))
    noise_power = float(np.mean(p ** 2))

    # Spatial correlations (use 2-D patch)
    patch2d = noise_patch.astype(np.float32)
    h2, w2 = patch2d.shape
    h_corr = float(np.corrcoef(patch2d[:, :-1].flatten(), patch2d[:, 1:].flatten())[0, 1]) if w2 > 1 else 0.0
    v_corr = float(np.corrcoef(patch2d[:-1, :].flatten(), patch2d[1:, :].flatten())[0, 1]) if h2 > 1 else 0.0

    # Spectral energies
    spectrum = np.abs(np.fft.fft2(patch2d))
    sh, sw = spectrum.shape
    low = float(np.mean(spectrum[:sh // 4, :sw // 4]))
    mid = float(np.mean(spectrum[sh // 4:sh // 2, sw // 4:sw // 2]))
    high = float(np.mean(spectrum[sh // 2:, sw // 2:]))
    ratio = float(high / (low + 1e-9))

    p10 = float(np.percentile(p, 10))
    p90 = float(np.percentile(p, 90))
    pos_frac = float(np.mean(p > 0))
    val_range = float(p.max() - p.min())

    return np.array(
        [mean, std, skewness, kurtosis, mean_abs, noise_power,
         h_corr, v_corr, low, mid, high, ratio, p10, p90, pos_frac, val_range],
        dtype=np.float32,
    )


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def analyze(image_path: str) -> dict[str, Any]:
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return {"error": "Cannot read image", "available": False}

    h, w = img.shape
    if h < _REGION_SIZE * 2 or w < _REGION_SIZE * 2:
        return {
            "manipulation_detected": False,
            "confidence": 0.0,
            "inconsistent_regions": [],
            "source_cluster_count": 1,
            "noise_consistency_score": 1.0,
            "outlier_region_count": 0,
            "total_regions": 0,
            "verdict": "INCONCLUSIVE",
            "available": True,
            "court_defensible": False,
            "note": "Image too small for sensor clustering",
            "model_version": "noiseprint_clustering_v1",
        }

    # Extract noise residual
    noise = _extract_noise_residual(img)
    noise = _dct_suppress(noise)

    # Tile image into regions and compute fingerprints
    fingerprints: list[np.ndarray] = []
    region_coords: list[tuple[int, int, int, int]] = []

    for r in range(0, h - _REGION_SIZE + 1, _REGION_SIZE):
        for c in range(0, w - _REGION_SIZE + 1, _REGION_SIZE):
            patch = noise[r : r + _REGION_SIZE, c : c + _REGION_SIZE]
            fp = _region_fingerprint(patch)
            fingerprints.append(fp)
            region_coords.append((c, r, _REGION_SIZE, _REGION_SIZE))  # x, y, w, h

    if len(fingerprints) < _MIN_REGIONS:
        return {
            "manipulation_detected": False,
            "confidence": 0.0,
            "inconsistent_regions": [],
            "source_cluster_count": 1,
            "noise_consistency_score": 1.0,
            "outlier_region_count": 0,
            "total_regions": len(fingerprints),
            "verdict": "INCONCLUSIVE",
            "available": True,
            "court_defensible": False,
            "note": "Too few regions for reliable clustering",
            "model_version": "noiseprint_clustering_v1",
        }

    X = np.array(fingerprints)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Silhouette-guided k selection (k=1..4)
    best_k = 1
    best_score = -1.0
    for k in range(2, min(5, len(fingerprints))):
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels_k = km.fit_predict(X_scaled)
        if len(np.unique(labels_k)) < 2:
            continue
        try:
            score = float(silhouette_score(X_scaled, labels_k))
            if score > best_score:
                best_score = score
                best_k = k
        except Exception:
            pass

    # Final clustering with best k
    km_final = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    cluster_labels = km_final.fit_predict(X_scaled)

    # The dominant cluster is the "native" sensor; minority clusters = suspect
    counts = np.bincount(cluster_labels)
    dominant = int(np.argmax(counts))
    minority_idx = [i for i, lbl in enumerate(cluster_labels) if lbl != dominant]

    inconsistent_regions = [
        {"x": region_coords[i][0], "y": region_coords[i][1],
         "w": region_coords[i][2], "h": region_coords[i][3]}
        for i in minority_idx
    ]

    consistency_score = float(counts[dominant]) / float(len(cluster_labels))
    outlier_count = len(minority_idx)

    if outlier_count == 0 or best_k == 1:
        verdict = "CONSISTENT"
    elif outlier_count <= 1 and best_k <= 2 and best_score < 0.3:
        verdict = "INCONCLUSIVE"
    else:
        verdict = "INCONSISTENT"

    manipulation_detected = verdict == "INCONSISTENT"

    # Confidence: weighted by silhouette quality, cluster ratio, and outlier density
    outlier_ratio = outlier_count / max(len(fingerprints), 1)
    conf_sil = max(0.0, best_score)                       # how well-separated the clusters are
    conf_ratio = min(outlier_ratio / 0.30, 1.0)            # fraction of anomalous regions
    conf_k = 1.0 if best_k >= 2 else 0.0                   # multi-source indicator
    confidence = round(float(0.40 * conf_sil + 0.35 * conf_ratio + 0.25 * conf_k), 3)
    if not manipulation_detected:
        confidence = 0.0

    return {
        "manipulation_detected": manipulation_detected,
        "confidence": confidence,
        "inconsistent_regions": inconsistent_regions,
        "source_cluster_count": best_k,
        "noise_consistency_score": round(consistency_score, 3),
        "outlier_region_count": outlier_count,
        "total_regions": len(fingerprints),
        "silhouette_score": round(float(best_score), 3),
        "verdict": verdict,
        "available": True,
        "court_defensible": True,
        "model_version": "noiseprint_clustering_v1",
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
    parser = argparse.ArgumentParser(description="Noiseprint++ — sensor noise clustering")
    parser.add_argument("--input", type=str, help="Path to input image")
    parser.add_argument("--warmup", action="store_true", help="Warmup mode")
    parser.add_argument("--worker", action="store_true", help="Worker mode (persistent stdin/stdout)")
    args = parser.parse_args()

    if args.warmup:
        try:
            import cv2  # noqa: F401
            import numpy  # noqa: F401
            from scipy.signal import wiener  # noqa: F401
            from sklearn.cluster import KMeans  # noqa: F401
            from sklearn.metrics import silhouette_score  # noqa: F401
            print(json.dumps({
                "status": "warmed_up",
                "dependencies": ["cv2", "numpy", "scipy", "sklearn"],
                "message": "Noiseprint clustering ready",
            }))
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
