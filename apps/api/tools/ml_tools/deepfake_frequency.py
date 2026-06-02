#!/usr/bin/env python3
"""
deepfake_frequency.py
=====================
Detects GAN/deepfake generation artifacts using combined frequency analysis
and PyTorch-based feature extraction.

The current checkerboard GAN detector is enhanced with:
1. FFT checkerboard detection (catches transposed-convolution GAN artifacts)
2. 1/f spectral deviation analysis (detects diffusion model signals)
3. PyTorch ResNet-50 backbone ready for UnivFD weights

Usage:
    python deepfake_frequency.py --input /path/to/image.jpg

Output JSON:
    {
        "deepfake_suspected": false,
        "confidence": 0.12,
        "checkerboard_score": 0.08,     # 0-1, >0.3 suggests GAN
        "spectral_anomaly_score": 0.15,  # diffusion model signal
        "verdict": "LIKELY_AUTHENTIC",  # LIKELY_AUTHENTIC | SUSPICIOUS | LIKELY_SYNTHETIC
        "available": true,
        "note": "Swap model.fc weights with UnivFD checkpoint for production accuracy"
    }
"""

import argparse
import json
import sys

import cv2
import numpy as np

# NOTE: This tool is a frequency-domain SCREENING heuristic (FFT checkerboard +
# 1/f spectral deviation). The real, trained AI-generation classifier lives in
# ai_generation_detector.py and is the primary signal via the
# diffusion_artifact_detector handler. A prior version loaded a ResNet-50 with an
# *untrained* classification head whose output was never actually used — that
# dead, misleading code has been removed so this tool reports only the real
# signal-processing measurements it actually computes.


def compute_frequency_features(image_path: str) -> dict:
    """
    Compute AI-generation screening features using frequency-domain analysis.

    Combines two real signal-processing measurements:
    - FFT checkerboard artifact detection (GAN upsampling)
    - 1/f spectral deviation (diffusion models)

    This is a SCREENING heuristic. The primary AI-generation signal is the
    trained ViT classifier in ai_generation_detector.py.
    """
    from core.config import get_settings

    settings = get_settings()
    if not settings.enable_research_models:
        return {
            "deepfake_suspected": False,
            "confidence": 0.0,
            "verdict": "SKIPPED",
            "available": False,
            "degraded": True,
            "reason": "research_model_license_gate",
        }

    # Load image
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return {"error": "Cannot read image", "available": False}

    # Resize to standard size for FFT analysis
    img_resized = cv2.resize(img, (256, 256)).astype(np.float32)

    # 2D DFT
    dft = np.fft.fft2(img_resized)
    dft_shift = np.fft.fftshift(dft)
    magnitude = 20 * np.log(np.abs(dft_shift) + 1)

    h, w = magnitude.shape
    center_y, center_x = h // 2, w // 2

    # --- Existing FFT checkerboard detection (keep as secondary signal) ---
    quarter_y = center_y // 2
    quarter_x = center_x // 2

    checkerboard_positions = [
        magnitude[quarter_y, quarter_x],
        magnitude[h - quarter_y, quarter_x],
        magnitude[quarter_y, w - quarter_x],
        magnitude[h - quarter_y, w - quarter_x],
    ]
    checkerboard_energy = float(np.mean(checkerboard_positions))

    # Compare to overall high-frequency energy (vectorized — avoids O(h×w) Python loops)
    _ys, _xs = np.ogrid[:h, :w]
    high_freq_mask = np.sqrt((_ys - center_y) ** 2 + (_xs - center_x) ** 2) > min(h, w) * 0.25

    overall_high_freq = float(np.mean(magnitude[high_freq_mask]))
    checkerboard_score = min(
        1.0,
        max(0.0, (checkerboard_energy - overall_high_freq) / (overall_high_freq + 1e-6)),
    )

    # --- 1/f spectral deviation (diffusion model signal) ---
    radial = []
    num_bands = 16
    for band in range(num_bands):
        r0 = band * min(center_y, center_x) / num_bands
        r1 = (band + 1) * min(center_y, center_x) / num_bands

        # Create ring mask efficiently
        ys, xs = np.ogrid[:h, :w]
        ring = (np.sqrt((ys - center_y) ** 2 + (xs - center_x) ** 2) >= r0) & (
            np.sqrt((ys - center_y) ** 2 + (xs - center_x) ** 2) < r1
        )

        if ring.any():
            radial.append(float(np.mean(magnitude[ring])))
        else:
            radial.append(0.0)

    expected = [radial[0] / (i + 1) for i in range(num_bands)]
    spectral_dev = float(
        np.mean(np.abs(np.array(radial) - np.array(expected)) / (np.array(expected) + 1e-6))
    )
    spectral_anomaly_score = min(1.0, spectral_dev / 5.0)

    # Combined score from the two real frequency-domain measurements.
    combined = checkerboard_score * 0.5 + spectral_anomaly_score * 0.5

    # Determine verdict
    if combined > 0.4:
        verdict = "LIKELY_SYNTHETIC"
    elif combined > 0.2:
        verdict = "SUSPICIOUS"
    else:
        verdict = "LIKELY_AUTHENTIC"

    return {
        "deepfake_suspected": combined > 0.25,
        "confidence": round(float(combined), 3),
        "checkerboard_score": round(float(checkerboard_score), 3),
        "spectral_anomaly_score": round(float(spectral_anomaly_score), 3),
        "verdict": verdict,
        "available": True,
        "method": "frequency_domain_screening",
        # Screening heuristic — not a standalone court-defensible determination.
        "court_defensible": False,
        "note": "Frequency-domain screening signal; primary AI-generation verdict is the trained ViT classifier.",
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

            print(
                json.dumps(
                    {
                        "status": "warmed_up",
                        "dependencies": ["cv2", "numpy"],
                        "message": "Deepfake frequency detector ready",
                    }
                )
            )
            sys.exit(0)
        except Exception as e:
            print(json.dumps({"status": "warmup_failed", "error": str(e)}))
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

                result = compute_frequency_features(input_path)
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
        result = compute_frequency_features(args.input)
    except Exception as e:
        result = {"error": str(e), "available": False}

    print(json.dumps(result))
