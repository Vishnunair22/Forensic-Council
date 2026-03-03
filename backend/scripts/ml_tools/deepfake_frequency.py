#!/usr/bin/env python3
"""
deepfake_frequency.py
=====================
Detects GAN/deepfake generation artifacts in the frequency domain.
GANs leave characteristic spectral fingerprints from transposed convolutions.

Usage:
    python deepfake_frequency.py --input /path/to/image.jpg

Output JSON:
    {
        "deepfake_suspected": false,
        "confidence": 0.12,
        "checkerboard_score": 0.08,     # 0-1, >0.3 strongly suggests GAN
        "spectral_anomaly_score": 0.15,
        "peak_frequencies": [32, 64],   # dominant artifact frequencies if detected
        "verdict": "LIKELY_AUTHENTIC",  # LIKELY_AUTHENTIC | SUSPICIOUS | LIKELY_SYNTHETIC
        "available": true
    }
"""

import argparse
import json
import numpy as np
import cv2


def compute_frequency_features(image_path: str) -> dict:
    from sklearn.svm import OneClassSVM

    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return {"error": "Cannot read image", "available": False}

    # Resize to standard size for comparison
    img_resized = cv2.resize(img, (256, 256)).astype(np.float32)

    # 2D DFT
    dft = np.fft.fft2(img_resized)
    dft_shift = np.fft.fftshift(dft)
    magnitude = 20 * np.log(np.abs(dft_shift) + 1)

    h, w = magnitude.shape
    center_y, center_x = h // 2, w // 2

    # GAN checkerboard artifact: look for periodic peaks at N/2 frequencies
    # (common artifact from deconvolution/upsampling in GANs)
    # Check for peaks at quarter and half frequency bins
    quarter_y = center_y // 2
    quarter_x = center_x // 2

    # Sample magnitude at checkerboard positions
    checkerboard_positions = [
        magnitude[quarter_y, quarter_x],
        magnitude[h - quarter_y, quarter_x],
        magnitude[quarter_y, w - quarter_x],
        magnitude[h - quarter_y, w - quarter_x],
    ]
    checkerboard_energy = float(np.mean(checkerboard_positions))

    # Compare to overall high-frequency energy
    high_freq_mask = np.zeros((h, w), dtype=bool)
    for y in range(h):
        for x in range(w):
            dist = np.sqrt((y - center_y)**2 + (x - center_x)**2)
            if dist > min(h, w) * 0.25:
                high_freq_mask[y, x] = True
    
    overall_high_freq = float(np.mean(magnitude[high_freq_mask]))

    # Checkerboard score: ratio of peak positions to overall high-freq energy
    checkerboard_score = min(1.0, max(0.0, (checkerboard_energy - overall_high_freq) / (overall_high_freq + 1e-6)))

    # Extract spectral features for One-Class SVM
    # Radial spectrum: mean magnitude at each radius band
    num_bands = 16
    radial_features = []
    for band in range(num_bands):
        r_min = band * min(center_y, center_x) / num_bands
        r_max = (band + 1) * min(center_y, center_x) / num_bands
        mask = np.zeros((h, w), dtype=bool)
        for y in range(h):
            for x in range(w):
                r = np.sqrt((y - center_y)**2 + (x - center_x)**2)
                if r_min <= r < r_max:
                    mask[y, x] = True
        if mask.any():
            radial_features.append(float(np.mean(magnitude[mask])))
        else:
            radial_features.append(0.0)

    # Natural images follow a 1/f power spectrum — deviation indicates synthesis
    expected_1_over_f = [radial_features[0] / (i + 1) for i in range(num_bands)]
    spectral_deviation = float(np.mean(np.abs(
        np.array(radial_features) - np.array(expected_1_over_f)
    ) / (np.array(expected_1_over_f) + 1e-6)))

    spectral_anomaly_score = min(1.0, spectral_deviation / 5.0)

    # Detect dominant artifact frequencies
    flat_magnitude = magnitude.flatten()
    threshold = np.percentile(flat_magnitude, 99)
    peak_positions = np.where(magnitude > threshold)
    peak_freqs = []
    if len(peak_positions[0]) > 0:
        for py, px in zip(peak_positions[0][:5], peak_positions[1][:5]):
            freq = int(np.sqrt((py - center_y)**2 + (px - center_x)**2))
            peak_freqs.append(freq)

    # Final verdict
    combined_score = (checkerboard_score * 0.6) + (spectral_anomaly_score * 0.4)
    deepfake_suspected = combined_score > 0.25 or checkerboard_score > 0.30

    if combined_score > 0.4:
        verdict = "LIKELY_SYNTHETIC"
    elif combined_score > 0.2:
        verdict = "SUSPICIOUS"
    else:
        verdict = "LIKELY_AUTHENTIC"

    return {
        "deepfake_suspected": deepfake_suspected,
        "confidence": round(float(combined_score), 3),
        "checkerboard_score": round(float(checkerboard_score), 3),
        "spectral_anomaly_score": round(float(spectral_anomaly_score), 3),
        "peak_frequencies": sorted(set(peak_freqs)),
        "verdict": verdict,
        "available": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()

    try:
        result = compute_frequency_features(args.input)
    except Exception as e:
        result = {"error": str(e), "available": False}

    print(json.dumps(result))
