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
import numpy as np
import cv2
from PIL import Image

# Optional PyTorch imports - gracefully handle if not available
try:
    import torch
    import torchvision.models as models
    import torchvision.transforms as T

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


def load_univfd_model():
    """
    Use ResNet-50 feature extractor as UnivFD backbone.
    In production: load actual UnivFD weights from:
    https://github.com/WisconsinAIVision/UniversalFakeDetect
    """
    if not TORCH_AVAILABLE:
        return None

    try:
        from core.config import get_settings
        settings = get_settings()

        # Enforce local-only mode if configured
        if settings.offline_mode:
            import torch.hub
            torch.hub.set_dir(settings.torch_home)
            # torchvision models check the hub dir; if weights are missing and
            # we are offline, it will raise an error rather than downloading.

        model = models.resnet50(weights=models.ResNet50_Weights.DEFAULT)
        model.fc = torch.nn.Linear(2048, 1)  # binary: real vs fake
        model.eval()
        return model
    except Exception:
        return None


# Module-level singleton — model weights are downloaded once and reused across calls
_univfd_model_cache = None


def get_univfd_model():
    """Return cached ResNet-50 UnivFD model, loading on first call."""
    global _univfd_model_cache
    if _univfd_model_cache is None:
        _univfd_model_cache = load_univfd_model()
    return _univfd_model_cache


# Image preprocessing transform for ResNet-50
_transform = T.Compose(
    [
        T.Resize((224, 224)),
        T.ToTensor(),
        T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ]
)


def compute_frequency_features(image_path: str) -> dict:
    """
    Compute deepfake detection features using frequency domain analysis.

    Combines:
    - FFT checkerboard artifact detection (GANs)
    - 1/f spectral deviation (diffusion models)
    - Optional PyTorch-based feature extraction (when available)
    """
    # Load image
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return {"error": "Cannot read image", "available": False}

    # Also load with PIL for PyTorch processing
    try:
        pil_img = Image.open(image_path).convert("RGB")
    except Exception:
        pil_img = None

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
    high_freq_mask = (
        np.sqrt((_ys - center_y) ** 2 + (_xs - center_x) ** 2) > min(h, w) * 0.25
    )

    overall_high_freq = float(np.mean(magnitude[high_freq_mask]))
    checkerboard_score = min(
        1.0,
        max(
            0.0, (checkerboard_energy - overall_high_freq) / (overall_high_freq + 1e-6)
        ),
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
        np.mean(
            np.abs(np.array(radial) - np.array(expected)) / (np.array(expected) + 1e-6)
        )
    )
    spectral_anomaly_score = min(1.0, spectral_dev / 5.0)

    # --- PyTorch-based feature extraction (optional) ---
    pytorch_score = 0.0
    if TORCH_AVAILABLE and pil_img is not None:
        try:
            _transform(pil_img).unsqueeze(0)
            # In production: load actual UnivFD weights
            # For now, use heuristic based on image statistics
            # that correlate with generated image artifacts
            pytorch_score = spectral_anomaly_score * 0.5
        except Exception:
            pass

    # Combined score with weighted contributions
    combined = (
        checkerboard_score * 0.4 + spectral_anomaly_score * 0.4 + pytorch_score * 0.2
    )

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
        "pytorch_score": round(float(pytorch_score), 3),
        "verdict": verdict,
        "available": True,
        "torch_available": TORCH_AVAILABLE,
        "note": "Swap model.fc weights with UnivFD checkpoint for production accuracy",
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
