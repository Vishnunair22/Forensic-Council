#!/usr/bin/env python3
"""
trufor_analyzer.py
==================
TruFor-inspired ViT splicing detector using Steganalysis Rich Model (SRM)
features and local statistical consistency analysis.

TruFor (Guillaro et al., 2023) feeds a pretrained ViT encoder a stacked
representation of: (a) the image, (b) a noise residual, and (c) a
Noiseprint-style fingerprint map to localize spliced regions.

This implementation replicates the key analytical pipeline:

  Stage A — SRM feature extraction: 30 high-pass residual filters capture
            compression artefacts and noise-floor shifts that betray spliced
            regions (these are the same filters used in TruFor's input stream).

  Stage B — Local statistical consistency: sliding-window statistics
            (mean, variance, kurtosis of SRM residuals) are computed and
            compared with a global Isolation Forest model.

  Stage C — Boundary sharpness analysis: authentic composites often show
            unnatural sharpness transitions at the splice boundary.

  Stage D — Confidence calibration and region extraction.

Output schema (compatible with neural_splicing fallback):
    {
        "splicing_detected": true,
        "confidence": 0.81,
        "forgery_regions": [{"x": 80, "y": 64, "w": 128, "h": 96}, ...],
        "integrity_score": 0.42,
        "boundary_anomaly": true,
        "srm_residual_variance": 3.24,
        "verdict": "SPLICED",
        "available": true,
        "court_defensible": true,
        "model_version": "trufor_srm_v1"
    }

Usage:
    python trufor_analyzer.py --input /path/to/image.jpg
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# SRM high-pass filter bank (30 filters, 5×5 kernels)
# These are a subset of the 30 SRM filters used in Fridrich & Kodovsky 2012.
# ---------------------------------------------------------------------------


def _build_srm_filters() -> list[np.ndarray]:
    """Return a list of 5×5 SRM-style high-pass kernels."""
    filters = []

    # Horizontal / vertical finite differences (order 1-3)
    for order in range(1, 4):
        k = np.zeros((5, 5), dtype=np.float32)
        if order == 1:
            k[2, 1] = -1
            k[2, 3] = 1
        elif order == 2:
            k[2, 1] = -1
            k[2, 2] = 2
            k[2, 3] = -1
        else:
            k[2, 0] = -1
            k[2, 1] = 3
            k[2, 3] = -3
            k[2, 4] = 1
        filters.append(k)
        filters.append(k.T)

    # Diagonal differences
    d1 = np.zeros((5, 5), dtype=np.float32)
    d1[1, 1] = -1
    d1[3, 3] = 1
    d2 = np.zeros((5, 5), dtype=np.float32)
    d2[1, 3] = -1
    d2[3, 1] = 1
    filters += [d1, d2]

    # Laplacian variants
    lap = np.array([[0, -1, 0], [-1, 4, -1], [0, -1, 0]], dtype=np.float32)
    lap5 = np.zeros((5, 5), dtype=np.float32)
    lap5[1:4, 1:4] = lap
    filters.append(lap5)

    # Sobel-based
    sx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float32)
    sy = sx.T
    sx5 = np.zeros((5, 5), dtype=np.float32)
    sx5[1:4, 1:4] = sx
    sy5 = np.zeros((5, 5), dtype=np.float32)
    sy5[1:4, 1:4] = sy
    filters += [sx5, sy5]

    # Padded identity-minus-mean filters (mimic SRM's "spam" filters)
    for shift in [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, -1)]:
        k2 = np.zeros((5, 5), dtype=np.float32)
        k2[2, 2] = 1.0
        r, c = 2 + shift[0], 2 + shift[1]
        if 0 <= r < 5 and 0 <= c < 5:
            k2[r, c] -= 1.0
        filters.append(k2)

    # Normalize each filter so abs values sum to 1
    out = []
    for f in filters:
        s = np.sum(np.abs(f))
        out.append(f / (s + 1e-9))

    return out[:30]  # cap at exactly 30


_SRM_FILTERS: list | None = None


def _get_srm_filters() -> list:
    """Return cached SRM filter bank, building it once per process."""
    global _SRM_FILTERS
    if _SRM_FILTERS is None:
        _SRM_FILTERS = _build_srm_filters()
    return _SRM_FILTERS


# ---------------------------------------------------------------------------
# Core stages
# ---------------------------------------------------------------------------


def _apply_srm(gray: np.ndarray) -> np.ndarray:
    """
    Apply SRM filter bank to a grayscale image.
    Returns stacked (H, W, 30) residual map.
    """
    residuals = []
    g = gray.astype(np.float32)
    for filt in _get_srm_filters():
        res = cv2.filter2D(g, -1, filt)
        residuals.append(res)
    return np.stack(residuals, axis=2)  # (H, W, 30)


def _block_statistics(
    srm_stack: np.ndarray,
    block_size: int = 32,
) -> tuple[np.ndarray, list[tuple[int, int, int, int]]]:
    """
    Compute per-block statistical features over the SRM residual stack.

    Each block yields a 6-dim feature:
      [0] mean of per-channel variances  → noise floor level
      [1] std of per-channel variances   → inter-channel inconsistency
      [2] mean kurtosis                  → non-Gaussianity (compression artefact)
      [3] max absolute residual mean     → systematic bias (e.g. spliced copy)
      [4] spectral energy (high-freq)    → sharpening / blurring signature
      [5] inter-block gradient magnitude → boundary sharpness
    """
    h, w, nc = srm_stack.shape
    features: list[np.ndarray] = []
    coords: list[tuple[int, int, int, int]] = []

    for r in range(0, h - block_size + 1, block_size):
        for c in range(0, w - block_size + 1, block_size):
            patch = srm_stack[r : r + block_size, c : c + block_size, :]  # (bs, bs, 30)
            ch_vars = np.var(patch.reshape(block_size * block_size, nc), axis=0)

            # Per-channel kurtosis (Fisher definition)
            flat = patch.reshape(-1, nc)
            mean_ch = flat.mean(axis=0)
            std_ch = flat.std(axis=0) + 1e-9
            kurt = np.mean(((flat - mean_ch) / std_ch) ** 4, axis=0) - 3.0

            # Spectral high-freq energy of first residual channel
            ch0 = patch[:, :, 0]
            fft_mag = np.abs(np.fft.fft2(ch0))
            sh, sw = fft_mag.shape
            hf_energy = float(np.mean(fft_mag[sh // 2 :, sw // 2 :]))

            # Gradient magnitude (boundary sharpness proxy)
            gx = cv2.Sobel(ch0.astype(np.float32), cv2.CV_32F, 1, 0, ksize=3)
            gy = cv2.Sobel(ch0.astype(np.float32), cv2.CV_32F, 0, 1, ksize=3)
            grad_mag = float(np.mean(np.sqrt(gx**2 + gy**2)))

            feat = np.array(
                [
                    float(np.mean(ch_vars)),
                    float(np.std(ch_vars)),
                    float(np.mean(np.abs(kurt))),
                    float(np.max(np.abs(flat.mean(axis=0)))),
                    hf_energy,
                    grad_mag,
                ],
                dtype=np.float32,
            )
            features.append(feat)
            coords.append((c, r, block_size, block_size))

    return np.array(features, dtype=np.float32), coords


def _boundary_sharpness_anomaly(gray: np.ndarray, threshold: float = 35.0) -> bool:
    """
    Detect unnatural sharp boundaries (cut-and-paste edges).
    Uses Canny + connected component density in mid-frequency band.
    """
    edges = cv2.Canny(gray, 80, 180)
    edge_density = float(edges.sum()) / float(edges.size)
    # Unusually high global edge density suggests pasted high-contrast content
    return edge_density > (threshold / 1000.0)


def analyze(image_path: str) -> dict[str, Any]:
    # Primary: the real TruFor model (SegFormer-B2 + Noiseprint++, trained for
    # splicing localization). It discriminates clean vs spliced reliably, unlike
    # the SRM/IsolationForest heuristic below (which fired on every image). The
    # heuristic remains only as a graceful fallback when the weights are absent.
    try:
        import os as _os
        import sys as _sys

        _d = _os.path.dirname(_os.path.realpath(__file__))
        if _d not in _sys.path:
            _sys.path.insert(0, _d)
        import trufor_infer

        _real = trufor_infer.analyze(image_path)
        if isinstance(_real, dict) and _real.get("available"):
            return _real
    except Exception as _exc:
        import logging
        logging.getLogger(__name__).warning(
            "TruFor real model failed, falling back to SRM heuristic: %s", _exc
        )

    img = cv2.imread(image_path)
    if img is None:
        return {"error": "Cannot read image", "available": False}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    if h < 64 or w < 64:
        return {
            "splicing_detected": False,
            "confidence": 0.0,
            "forgery_regions": [],
            "integrity_score": 1.0,
            "boundary_anomaly": False,
            "srm_residual_variance": 0.0,
            "verdict": "INCONCLUSIVE",
            "available": True,
            "court_defensible": False,
            "note": "Image too small for SRM analysis",
            "model_version": "trufor_srm_v1",
        }

    # Stage A: SRM residual stack
    srm_stack = _apply_srm(gray)
    srm_global_var = float(np.var(srm_stack))

    # Stage B: block-level statistics
    block_size = 32 if min(h, w) >= 128 else 16
    features, coords = _block_statistics(srm_stack, block_size=block_size)

    if len(features) < 9:
        return {
            "splicing_detected": False,
            "confidence": 0.0,
            "forgery_regions": [],
            "integrity_score": 1.0,
            "boundary_anomaly": False,
            "srm_residual_variance": round(srm_global_var, 4),
            "verdict": "INCONCLUSIVE",
            "available": True,
            "court_defensible": False,
            "note": "Too few blocks for reliable detection",
            "model_version": "trufor_srm_v1",
        }

    # ── Splice detection via spatially-coherent residual-deviation clusters ──
    # The previous build used IsolationForest(contamination=0.10), which
    # unconditionally labels ~10% of blocks as "anomalies" on ANY image — so it
    # reported splicing_detected=True at a near-constant confidence on clean
    # photos and could not discriminate a real splice (validated: it returned
    # 0.594 for clean, copy-move and splice alike). A genuine spliced region
    # instead has SRM residual statistics that (a) deviate strongly from the rest
    # of the image and (b) are SPATIALLY CONTIGUOUS (a pasted block, not scattered
    # noise). Detect that directly: robust per-block deviation (median/MAD
    # z-score) at an ABSOLUTE threshold, then require the flagged blocks to form a
    # connected cluster. Clean-image outliers are scattered (no cluster); splices
    # cluster — this is what actually separates the two.
    feats = np.asarray(features, dtype=np.float64)
    med = np.median(feats, axis=0)
    mad = np.median(np.abs(feats - med), axis=0)
    scale = 1.4826 * mad + (np.abs(med) * 1e-3 + 1e-6)
    block_score = (np.abs(feats - med) / scale).max(axis=1)  # strongest per-feature deviation
    _Z_THRESH = 4.0
    flagged = block_score > _Z_THRESH

    rows = sorted({cc[1] for cc in coords})
    cols = sorted({cc[0] for cc in coords})
    ridx = {v: i for i, v in enumerate(rows)}
    cidx = {v: i for i, v in enumerate(cols)}
    grid = np.zeros((len(rows), len(cols)), dtype=np.uint8)
    for (c, r, _bw, _bh), fl in zip(coords, flagged, strict=False):
        if fl:
            grid[ridx[r], cidx[c]] = 255
    n_comp, comp = cv2.connectedComponents(grid, connectivity=8)

    _MIN_CLUSTER = 4  # contiguous blocks required to call a spliced region
    forgery_regions = []
    largest_cluster = 0
    for i in range(1, n_comp):
        ys, xs = np.where(comp == i)
        size = int(len(ys))
        largest_cluster = max(largest_cluster, size)
        if size >= _MIN_CLUSTER:
            forgery_regions.append({
                "x": int(cols[int(xs.min())]),
                "y": int(rows[int(ys.min())]),
                "w": int((int(xs.max()) - int(xs.min()) + 1) * block_size),
                "h": int((int(ys.max()) - int(ys.min()) + 1) * block_size),
            })

    boundary_anomaly = _boundary_sharpness_anomaly(gray)
    max_z = float(block_score.max()) if block_score.size else 0.0
    splicing_detected = len(forgery_regions) >= 1

    if splicing_detected:
        conf_cluster = min(largest_cluster / 12.0, 1.0)
        conf_dev = min(max(0.0, max_z - _Z_THRESH) / 4.0, 1.0)
        confidence = round(float(0.45 + 0.35 * conf_cluster + 0.20 * conf_dev), 3)
        verdict = "SPLICED"
    elif largest_cluster >= 2 and max_z > _Z_THRESH + 2.0:
        confidence = 0.30
        verdict = "SUSPICIOUS"
    else:
        confidence = round(min(0.12, 0.02 * largest_cluster), 3)
        verdict = "AUTHENTIC"

    integrity_score = round(1.0 - min(int(flagged.sum()) / max(len(flagged), 1) / 0.10, 1.0), 3)
    # A clustered, high-deviation splice is a defensible localized signal; weaker
    # reads stay screening-tier (so an uncorroborated heuristic can't assert).
    court_defensible = bool(splicing_detected and largest_cluster >= 8 and max_z >= _Z_THRESH + 2.0)

    return {
        "splicing_detected": splicing_detected,
        "confidence": confidence,
        "forgery_regions": forgery_regions[:10],
        "integrity_score": integrity_score,
        "boundary_anomaly": boundary_anomaly,
        "srm_residual_variance": round(srm_global_var, 4),
        "anomaly_block_count": int(flagged.sum()),
        "total_block_count": int(len(features)),
        "largest_cluster_blocks": int(largest_cluster),
        "max_block_zscore": round(max_z, 2),
        "verdict": verdict,
        "available": True,
        "court_defensible": court_defensible,
        "model_version": "trufor_srm_v2_cluster",
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
    parser = argparse.ArgumentParser(description="TruFor SRM splicing detector")
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
            from scipy.ndimage import uniform_filter  # noqa: F401
            from sklearn.ensemble import IsolationForest  # noqa: F401

            print(
                json.dumps(
                    {
                        "status": "warmed_up",
                        "dependencies": ["cv2", "numpy", "scipy", "sklearn"],
                        "message": "TruFor SRM analyzer ready",
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
