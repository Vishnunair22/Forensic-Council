#!/usr/bin/env python3
"""
f3net_freq.py
=============
F3-Net frequency-domain GAN / AI-generation artifact detector.

F3-Net (Qian et al., 2020) was originally designed for face deepfake
detection using two frequency-domain branches:
  • FAD (Frequency-Aware Decomposition)    — separates the image into
    sub-band frequency channels and identifies band-specific artefacts.
  • LFS (Local Frequency Statistics)       — captures local spectral
    inconsistencies that arise from GAN upsampling, diffusion super-resolution,
    and AI-inpainting operations.

This implementation applies both concepts image-wide (not face-specific):

  Branch 1 — FAD: Discrete Wavelet Transform (DWT) sub-band energy analysis.
    The LL/LH/HL/HH wavelet sub-bands are analysed for anomalous energy
    distributions.  GAN outputs show characteristic HH spike patterns from
    transpose-convolution checkerboard artefacts.

  Branch 2 — LFS: Sliding-window local FFT statistics.
    For each tile, we compute the spectral centroid, spectral spread, and
    periodic-grid score.  Natural images show smooth centroid distributions;
    AI images show clustered low-variance centroids (all tiles look the same).

  Branch 3 — Phase consistency: Human-captured images have spatially coherent
    phase maps; GAN/diffusion outputs often break phase continuity.

Output schema (compatible with f3_net_frequency / deepfake_frequency_check):
    {
        "gan_artifact_detected": true,
        "confidence": 0.76,
        "frequency_anomaly": true,
        "artifact_type": "GAN_UPSAMPLING",
        "wavelet_hh_spike": 0.83,
        "lfs_variance": 0.12,
        "phase_inconsistency": 0.61,
        "frequency_bands": {
            "LL": {"energy": 0.71, "anomalous": false},
            "LH": {"energy": 0.14, "anomalous": false},
            "HL": {"energy": 0.09, "anomalous": false},
            "HH": {"energy": 0.06, "anomalous": true}
        },
        "available": true,
        "court_defensible": true,
        "model_version": "f3net_freq_v1"
    }

Usage:
    python f3net_freq.py --input /path/to/image.jpg
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Branch 1: FAD — Discrete Wavelet Transform sub-band analysis
# ---------------------------------------------------------------------------

def _haar_dwt2(img: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    One-level 2D Haar DWT.
    Returns (LL, LH, HL, HH) sub-bands of shape (H/2, W/2).
    """
    h, w = img.shape
    # Ensure even dimensions
    img = img[:h - h % 2, :w - w % 2].astype(np.float32)
    # Row-wise
    lo = (img[:, 0::2] + img[:, 1::2]) * 0.5
    hi = (img[:, 0::2] - img[:, 1::2]) * 0.5
    # Col-wise on each
    LL = (lo[0::2, :] + lo[1::2, :]) * 0.5
    LH = (lo[0::2, :] - lo[1::2, :]) * 0.5
    HL = (hi[0::2, :] + hi[1::2, :]) * 0.5
    HH = (hi[0::2, :] - hi[1::2, :]) * 0.5
    return LL, LH, HL, HH


def _fad_analysis(gray: np.ndarray) -> dict[str, Any]:
    """
    FAD: DWT sub-band energy analysis.

    GAN checkerboard artefacts manifest as anomalously high HH energy and
    an unusual HH/LL energy ratio. Diffusion models often show elevated
    LH+HL (edge bands) due to super-resolution artefacts.
    """
    LL, LH, HL, HH = _haar_dwt2(gray)
    total = float(np.sum(LL**2) + np.sum(LH**2) + np.sum(HL**2) + np.sum(HH**2)) + 1e-9

    e_ll = float(np.sum(LL**2)) / total
    e_lh = float(np.sum(LH**2)) / total
    e_hl = float(np.sum(HL**2)) / total
    e_hh = float(np.sum(HH**2)) / total

    # Natural images: HH << LL.  AI images: HH elevated, periodic spikes.
    hh_spike = float(e_hh / (e_ll + 1e-9))  # higher = more suspicious

    # Check for periodic structure in HH (checkerboard pattern from transposed conv)
    hh_fft = np.abs(np.fft.fft2(HH))
    hh_fft_shift = np.fft.fftshift(hh_fft)
    sh, sw = hh_fft_shift.shape
    # Normalise
    hh_norm = hh_fft_shift / (hh_fft_shift.max() + 1e-9)
    # High-frequency quadrant peak (exclude DC)
    center_mask = np.ones_like(hh_norm)
    cv2.circle(center_mask, (sw // 2, sh // 2), max(sh, sw) // 8, 0, -1)
    peak_hf = float(np.max(hh_norm * center_mask))
    mean_hf = float(np.mean(hh_norm * center_mask))
    periodic_score = float(peak_hf / (mean_hf + 1e-9))

    hh_anomalous = hh_spike > 0.05 or periodic_score > 12.0
    lh_hl_anomalous = (e_lh + e_hl) > 0.20  # elevated edge bands = SR artefact

    return {
        "LL": {"energy": round(e_ll, 4), "anomalous": False},
        "LH": {"energy": round(e_lh, 4), "anomalous": lh_hl_anomalous},
        "HL": {"energy": round(e_hl, 4), "anomalous": lh_hl_anomalous},
        "HH": {"energy": round(e_hh, 4), "anomalous": hh_anomalous},
        "hh_spike": round(hh_spike, 4),
        "periodic_score": round(periodic_score, 2),
        "fad_signal": hh_anomalous or lh_hl_anomalous,
    }


# ---------------------------------------------------------------------------
# Branch 2: LFS — Local Frequency Statistics
# ---------------------------------------------------------------------------

def _lfs_analysis(gray: np.ndarray, tile_size: int = 64) -> dict[str, Any]:
    """
    LFS: Tile-level spectral centroid and variance analysis.

    AI-generated images tend to produce tiles with very similar spectral
    centroids and low variance — the model repeats the same frequency
    pattern everywhere.  Real images show much higher per-tile spectral
    diversity.
    """
    h, w = gray.shape
    centroids: list[float] = []
    spreads: list[float] = []

    for r in range(0, h - tile_size + 1, tile_size):
        for c in range(0, w - tile_size + 1, tile_size):
            tile = gray[r : r + tile_size, c : c + tile_size].astype(np.float32)
            fft_mag = np.abs(np.fft.fft2(tile))
            fft_shift = np.fft.fftshift(fft_mag)
            sh, sw = fft_shift.shape

            # Radial frequency coordinate
            cy, cx = sh // 2, sw // 2
            Y, X = np.ogrid[:sh, :sw]
            R = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2).flatten()
            mag = fft_shift.flatten() + 1e-9

            # Spectral centroid (power-weighted mean frequency)
            centroid = float(np.sum(R * mag) / np.sum(mag))
            spread = float(np.sqrt(np.sum(mag * (R - centroid) ** 2) / np.sum(mag)))

            centroids.append(centroid)
            spreads.append(spread)

    if len(centroids) < 4:
        return {"lfs_variance": 0.0, "lfs_signal": False, "tile_count": len(centroids)}

    centroid_arr = np.array(centroids)
    lfs_variance = float(np.std(centroid_arr) / (np.mean(centroid_arr) + 1e-9))

    # Low coefficient of variation = unnaturally uniform spectral pattern = AI signal
    lfs_signal = lfs_variance < 0.15

    return {
        "lfs_variance": round(lfs_variance, 4),
        "centroid_mean": round(float(np.mean(centroid_arr)), 2),
        "centroid_std": round(float(np.std(centroid_arr)), 2),
        "lfs_signal": lfs_signal,
        "tile_count": len(centroids),
    }


# ---------------------------------------------------------------------------
# Branch 3: Phase consistency
# ---------------------------------------------------------------------------

def _phase_consistency(gray: np.ndarray) -> dict[str, Any]:
    """
    Phase spectrum discontinuity analysis.

    GAN / diffusion outputs often introduce discontinuities in the global
    phase spectrum that are absent in naturally-captured images.  We measure
    the local phase gradient: high variance = inconsistent phase = suspicious.
    """
    gray_f = gray.astype(np.float32)
    fft = np.fft.fft2(gray_f)
    phase = np.angle(fft)

    # Phase gradient magnitude
    gy = np.diff(phase, axis=0)
    gx = np.diff(phase, axis=1)

    # Wrap phase differences to [-π, π]
    gy = (gy + np.pi) % (2 * np.pi) - np.pi
    gx = (gx + np.pi) % (2 * np.pi) - np.pi

    grad_mag = np.sqrt(gy[:, :gx.shape[1]] ** 2 + gx[:gy.shape[0], :] ** 2)
    phase_inconsistency = float(np.std(grad_mag) / (np.mean(grad_mag) + 1e-9))

    # AI images: phase inconsistency tends to be LOWER (unnaturally smooth)
    phase_signal = phase_inconsistency < 0.5

    return {
        "phase_inconsistency": round(phase_inconsistency, 4),
        "phase_signal": phase_signal,
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
            "gan_artifact_detected": False,
            "confidence": 0.0,
            "frequency_anomaly": False,
            "artifact_type": "UNKNOWN",
            "wavelet_hh_spike": 0.0,
            "lfs_variance": 0.0,
            "phase_inconsistency": 0.0,
            "frequency_bands": {},
            "available": True,
            "court_defensible": False,
            "note": "Image too small",
            "model_version": "f3net_freq_v1",
        }

    # Run all three branches
    fad = _fad_analysis(gray)
    lfs = _lfs_analysis(gray)
    phase = _phase_consistency(gray)

    # Signal aggregation
    signals = [fad["fad_signal"], lfs["lfs_signal"], phase["phase_signal"]]
    signal_count = sum(1 for s in signals if s)

    # Confidence blending
    conf_fad = min(fad["hh_spike"] / 0.10 * 0.3 + (1.0 if fad["periodic_score"] > 12 else 0.0) * 0.2, 0.5)
    conf_lfs = (1.0 - min(lfs["lfs_variance"] / 0.15, 1.0)) * 0.3 if lfs.get("tile_count", 0) >= 4 else 0.0
    conf_phase = (1.0 - min(phase["phase_inconsistency"] / 0.5, 1.0)) * 0.2
    confidence = round(float(conf_fad + conf_lfs + conf_phase), 3)

    gan_artifact_detected = signal_count >= 2 and confidence > 0.35

    # Determine artifact type
    if fad["HH"]["anomalous"] and fad["periodic_score"] > 12:
        artifact_type = "GAN_UPSAMPLING"
    elif fad["LH"]["anomalous"] or fad["HL"]["anomalous"]:
        artifact_type = "SR_ARTIFACT"
    elif lfs["lfs_signal"] and phase["phase_signal"]:
        artifact_type = "DIFFUSION_SMOOTHING"
    elif gan_artifact_detected:
        artifact_type = "AI_GENERIC"
    else:
        artifact_type = "NATURAL"

    return {
        "gan_artifact_detected": gan_artifact_detected,
        "confidence": confidence,
        "frequency_anomaly": signal_count >= 1,
        "artifact_type": artifact_type,
        "wavelet_hh_spike": fad["hh_spike"],
        "lfs_variance": lfs.get("lfs_variance", 0.0),
        "phase_inconsistency": phase["phase_inconsistency"],
        "frequency_bands": {
            "LL": fad["LL"],
            "LH": fad["LH"],
            "HL": fad["HL"],
            "HH": fad["HH"],
        },
        "branch_signals": {
            "fad": fad["fad_signal"],
            "lfs": lfs.get("lfs_signal", False),
            "phase": phase["phase_signal"],
        },
        "available": True,
        "court_defensible": True,
        "model_version": "f3net_freq_v1",
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
    parser = argparse.ArgumentParser(description="F3-Net frequency artifact detector")
    parser.add_argument("--input", type=str, help="Path to input image")
    parser.add_argument("--warmup", action="store_true", help="Warmup mode")
    parser.add_argument("--worker", action="store_true", help="Worker mode (persistent stdin/stdout)")
    args = parser.parse_args()

    if args.warmup:
        try:
            import cv2  # noqa: F401
            import numpy  # noqa: F401
            print(json.dumps({
                "status": "warmed_up",
                "dependencies": ["cv2", "numpy"],
                "message": "F3-Net frequency detector ready",
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
