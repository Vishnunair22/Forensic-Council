"""
Image Forensic Tools
====================

Real forensic tool handlers for image integrity analysis.
Implements ELA, ROI extraction, JPEG ghost detection, and hash verification.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from typing import Any

import imagehash
import numpy as np
from PIL import Image
from scipy import ndimage

from core.evidence import ArtifactType, EvidenceArtifact
from core.exceptions import ToolUnavailableError
from core.image_utils import is_lossless_image
from core.persistence.evidence_store import EvidenceStore

# OCR imports


@dataclass
class BoundingBox:
    """Bounding box for region of interest."""

    x: int
    y: int
    w: int
    h: int

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}


def ela_full_image(
    artifact: EvidenceArtifact,
    evidence_store: EvidenceStore | None = None,
    quality: int = 95,
    anomaly_threshold: float = 10.0,
    multi_quality: bool = True,
) -> dict[str, Any]:
    """
    Perform Error Level Analysis (ELA) on an image.

    Opens image with Pillow, saves at specified quality, reloads,
    and computes pixel difference to create ELA map.

    Multi-quality sweep: When enabled, re-saves at multiple quality levels
    (70, 80, 90, 95) and fuses results by taking the maximum ELA across
    all quality levels. This catches splices that may have survived
    single re-compression.

    Args:
        artifact: The evidence artifact to analyze
        evidence_store: Optional evidence store for creating derivative artifacts
        quality: JPEG quality level for re-saving (default 95, used when multi_quality=False)
        anomaly_threshold: Threshold for flagging anomaly regions (default 10.0)
        multi_quality: Enable multi-quality sweep for enhanced detection (default True)

    Returns:
        Dictionary containing:
        - ela_map_array: 2D numpy array of ELA values (as list for serialization)
        - max_anomaly: Maximum anomaly value detected
        - anomaly_regions: List of BoundingBox regions with elevated anomaly
        - mean_ela: Mean ELA value across image
        - std_ela: Standard deviation of ELA values
        - quality_levels: List of quality levels used in analysis
        - multi_quality_fusion: Whether multi-quality fusion was applied

    Raises:
        ToolUnavailableError: If file cannot be opened or processed
    """
    try:
        # Open the original image
        original_path = artifact.file_path
        if not os.path.exists(original_path):
            raise ToolUnavailableError(f"File not found: {original_path}")

        # ELA is only meaningful for JPEG images — it measures the residual error
        # introduced by re-compression at a slightly lower quality level.  For
        # lossless formats (PNG, BMP, TIFF) the first JPEG re-save introduces
        # compression artefacts across the ENTIRE image, so every pixel shows a
        # large ELA deviation.  Reporting those as "anomaly regions" would produce
        # thousands of false positives and mislead any downstream analysis.
        #
        # NOTE: Evidence files are stored under UUID paths with a generic .bin
        # extension, so extension-based checks alone are insufficient.  We open
        # the file first so PIL reads the magic bytes, then check the reported
        # format.  The extension check is kept as a fast-path for named files.
        # Open image now so we can inspect the PIL-detected format
        with Image.open(original_path) as _probe:
            pil_format = (_probe.format or "").upper()

        mime_type = getattr(artifact, "mime_type", None) or ""
        is_lossless = is_lossless_image(original_path, mime_type)
        ext = os.path.splitext(original_path)[1].lower()
        lossless_label = pil_format or ext.lstrip(".").upper() or "LOSSLESS"

        if is_lossless:
            return {
                "max_anomaly": None,
                "anomaly_regions": [],
                "num_anomaly_regions": 0,
                "mean_ela": None,
                "std_ela": None,
                "quality_levels": [],
                "multi_quality_fusion": False,
                "ela_not_applicable": True,
                "ela_limitation_note": (
                    f"ELA is not applicable to lossless {lossless_label} files. "
                    "Standard ELA measures JPEG re-compression residuals — applying it "
                    "to a lossless source produces artefacts across the entire image "
                    "that are indistinguishable from manipulation signals. "
                    "Use frequency-domain analysis, noise fingerprinting, or CFA "
                    "demosaicing checks instead for this file type."
                ),
                "court_defensible": False,
                "available": True,
            }

        # ── blocking PIL/numpy multi-quality sweep ──────────

        # Capture parameters for the closure
        _quality = quality
        _multi_quality = multi_quality
        _anomaly_threshold = anomaly_threshold
        _evidence_store = evidence_store
        _artifact = artifact

        def _blocking_ela_compute() -> dict:
            quality_levels_used = [70, 80, 90, 95] if _multi_quality else [_quality]

            with Image.open(original_path) as _img:
                original = _img.convert("RGB") if _img.mode != "RGB" else _img.copy()
            original_array = np.array(original, dtype=np.float64)

            ela_maps: list = []
            temp_files_ela: list[str] = []

            try:
                for q in quality_levels_used:
                    with tempfile.NamedTemporaryFile(
                        suffix=".jpg", delete=False
                    ) as tmp:
                        tmp_path_ela = tmp.name
                        temp_files_ela.append(tmp_path_ela)

                    original.save(tmp_path_ela, "JPEG", quality=q)
                    with Image.open(tmp_path_ela) as _resaved:
                        resaved_array = np.array(_resaved, dtype=np.float64)

                    ela_map = np.abs(original_array - resaved_array)
                    ela_gray = np.mean(ela_map, axis=2)
                    ela_maps.append(ela_gray)

                # Fuse: take max across quality levels — maximises sensitivity
                combined_ela = (
                    np.max(np.stack(ela_maps, axis=0), axis=0)
                    if len(ela_maps) > 1
                    else ela_maps[0]
                )

                max_anomaly = float(np.max(combined_ela))
                mean_ela = float(np.mean(combined_ela))
                std_ela = float(np.std(combined_ela))

                anomaly_mask = combined_ela > _anomaly_threshold
                labeled_array, num_features = ndimage.label(anomaly_mask)

                anomaly_regions: list[BoundingBox] = []
                for i in range(1, num_features + 1):
                    region_mask = labeled_array == i
                    rows = np.any(region_mask, axis=1)
                    cols = np.any(region_mask, axis=0)
                    if np.any(rows) and np.any(cols):
                        y_min, y_max = np.where(rows)[0][[0, -1]]
                        x_min, x_max = np.where(cols)[0][[0, -1]]
                        anomaly_regions.append(
                            BoundingBox(
                                x=int(x_min),
                                y=int(y_min),
                                w=int(x_max - x_min + 1),
                                h=int(y_max - y_min + 1),
                            )
                        )

                # Optional derivative artifact (sync-safe: just file write + object construction)
                derivative_artifact = None
                if _evidence_store:
                    ela_image = Image.fromarray(
                        (combined_ela / max(max_anomaly, 1) * 255).astype(np.uint8)
                    )
                    ela_path = os.path.join(
                        os.path.dirname(original_path),
                        f"ela_{_artifact.artifact_id}.jpg",
                    )
                    ela_image.save(ela_path, "JPEG", quality=95)
                    with open(ela_path, "rb") as f:
                        ela_hash = hashlib.sha256(f.read()).hexdigest()
                    derivative_artifact = EvidenceArtifact.create_derivative(
                        parent=_artifact,
                        artifact_type=ArtifactType.ELA_OUTPUT,
                        file_path=ela_path,
                        content_hash=ela_hash,
                        action="ela_analysis",
                        agent_id="image_tools",
                        metadata={
                            "quality": _quality,
                            "quality_levels": quality_levels_used,
                            "multi_quality_fusion": _multi_quality,
                            "max_anomaly": max_anomaly,
                            "anomaly_threshold": _anomaly_threshold,
                        },
                    )

                return {
                    "max_anomaly": max_anomaly,
                    "anomaly_regions": [r.to_dict() for r in anomaly_regions],
                    "num_anomaly_regions": len(anomaly_regions),
                    "mean_ela": mean_ela,
                    "std_ela": std_ela,
                    "ela_mean": mean_ela,
                    "quality_levels": quality_levels_used,
                    "multi_quality_fusion": _multi_quality,
                    "derivative_artifact": derivative_artifact.to_dict()
                    if derivative_artifact
                    else None,
                    "court_defensible": True,
                    "available": True,
                }

            finally:
                for _tp in temp_files_ela:
                    try:
                        if os.path.exists(_tp):
                            os.unlink(_tp)
                    except OSError:
                        pass

        return _blocking_ela_compute()

    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"ELA analysis failed: {str(e)}") from e


async def roi_extract(
    artifact: EvidenceArtifact,
    bounding_box: dict[str, int],
    evidence_store: EvidenceStore | None = None,
) -> dict[str, Any]:
    """
    Extract a Region of Interest (ROI) from an image.

    Crops the image to the specified bounding box and creates
    a derivative artifact.

    Args:
        artifact: The evidence artifact to crop
        bounding_box: Dictionary with x, y, w, h keys
        evidence_store: Optional evidence store for creating derivative

    Returns:
        Dictionary containing:
        - roi_artifact: New derivative EvidenceArtifact
        - roi_path: Path to the cropped image
        - dimensions: Width and height of ROI

    Raises:
        ToolUnavailableError: If file cannot be opened or crop fails
    """
    try:
        original_path = artifact.file_path
        if not os.path.exists(original_path):
            raise ToolUnavailableError(f"File not found: {original_path}")

        with Image.open(original_path) as _img:
            original = _img.convert("RGB") if _img.mode != "RGB" else _img.copy()

        # Extract bounding box parameters
        x = bounding_box.get("x", 0)
        y = bounding_box.get("y", 0)
        w = bounding_box.get("w", 100)
        h = bounding_box.get("h", 100)

        # Validate bounds
        img_w, img_h = original.size
        x = max(0, min(x, img_w - 1))
        y = max(0, min(y, img_h - 1))
        w = min(w, img_w - x)
        h = min(h, img_h - y)

        # Crop using PIL (left, upper, right, lower)
        roi = original.crop((x, y, x + w, y + h))

        # Save ROI
        roi_path = os.path.join(
            os.path.dirname(original_path),
            f"roi_{artifact.artifact_id}_{x}_{y}_{w}x{h}.jpg",
        )
        roi.save(roi_path, "JPEG", quality=95)

        # Compute hash
        with open(roi_path, "rb") as f:
            roi_hash = hashlib.sha256(f.read()).hexdigest()

        # Create derivative artifact
        derivative_artifact = EvidenceArtifact.create_derivative(
            parent=artifact,
            artifact_type=ArtifactType.ROI_CROP,
            file_path=roi_path,
            content_hash=roi_hash,
            action="roi_extract",
            agent_id="image_tools",
            metadata={
                "bounding_box": bounding_box,
                "dimensions": {"width": w, "height": h},
            },
        )

        return {
            "roi_artifact": derivative_artifact.to_dict()
            if derivative_artifact
            else None,
            "roi_path": roi_path,
            "dimensions": {"width": w, "height": h},
        }

    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"ROI extraction failed: {str(e)}") from e


async def jpeg_ghost_detect(
    artifact: EvidenceArtifact,
    quality_levels: list[int] | None = None,
    ghost_threshold: float = 5.0,
) -> dict[str, Any]:
    """
    Detect JPEG ghost artifacts indicating double compression.

    Saves image at multiple quality levels and computes variance map
    to detect regions with inconsistent compression history.

    Args:
        artifact: The evidence artifact to analyze
        quality_levels: List of quality levels to test (default [50,60,70,80,90])
        ghost_threshold: Threshold for ghost detection confidence

    Returns:
        Dictionary containing:
        - ghost_detected: Boolean indicating if ghost artifacts found
        - confidence: Confidence level (0.0 to 1.0)
        - ghost_regions: List of BoundingBox regions with ghost artifacts
        - variance_map: Variance map across quality levels
    """
    # Three quality levels cover the forensically important range (low/mid/high)
    # while saving two full-image re-saves versus the previous five-level default.
    if quality_levels is None:
        quality_levels = [60, 80, 95]

    import asyncio as _asyncio

    try:
        original_path = artifact.file_path
        if not os.path.exists(original_path):
            raise ToolUnavailableError(f"File not found: {original_path}")

        # JPEG ghost detection requires a JPEG source — it looks for the
        # characteristic variance pattern left when a JPEG is re-saved at a
        # different quality.  A lossless PNG has no prior JPEG compression
        # history, so this test will always return zero variance everywhere
        # and cannot distinguish authentic files from manipulated ones.
        #
        # NOTE: Evidence files use UUID .bin paths — check PIL magic bytes too.
        with Image.open(original_path) as _probe:
            pil_format = (_probe.format or "").upper()
        mime_type = getattr(artifact, "mime_type", None) or ""
        is_lossless = is_lossless_image(original_path, mime_type)
        ext = os.path.splitext(original_path)[1].lower()
        lossless_label = pil_format or ext.lstrip(".").upper() or "LOSSLESS"

        if is_lossless:
            return {
                "ghost_detected": False,
                "confidence": 0.0,
                "ghost_regions": [],
                "max_variance": None,
                "mean_variance": None,
                "ghost_not_applicable": True,
                "ghost_limitation_note": (
                    f"JPEG ghost detection is not applicable to lossless {lossless_label} files. "
                    "This technique detects double-JPEG-compression artefacts — a lossless "
                    "source has no prior JPEG compression history to compare against."
                ),
                "court_defensible": False,
                "available": True,
            }

        # ── offload all blocking PIL/numpy work to a thread so the event loop
        # stays responsive during compression sweeps.
        def _blocking_ghost_compute() -> dict:
            # Open, convert to RGB, extract array, then close immediately
            with Image.open(original_path) as _img:
                original = _img.convert("RGB") if _img.mode != "RGB" else _img.copy()
            np.array(original, dtype=np.float64)

            # Create compressed versions at different quality levels
            compressed_arrays = []
            temp_files_inner: list[str] = []

            try:
                for quality in quality_levels:
                    with tempfile.NamedTemporaryFile(
                        suffix=".jpg", delete=False
                    ) as tmp:
                        tmp_path_inner = tmp.name
                        temp_files_inner.append(tmp_path_inner)

                    original.save(tmp_path_inner, "JPEG", quality=quality)
                    with Image.open(tmp_path_inner) as _compressed:
                        compressed_arrays.append(
                            np.array(_compressed, dtype=np.float64)
                        )

                # Stack all compressed versions
                stacked = np.stack(compressed_arrays, axis=0)

                # Compute variance across quality levels for each pixel
                variance_map_arr = np.var(stacked, axis=0)

                # Convert to grayscale — summary statistics only (no full-array serialisation)
                variance_gray = np.mean(variance_map_arr, axis=2)

                max_variance = float(np.max(variance_gray))
                mean_variance = float(np.mean(variance_gray))

                # Detect ghost regions (high variance indicates double compression)
                ghost_mask = variance_gray > ghost_threshold

                # Label connected regions
                labeled_array, num_features = ndimage.label(ghost_mask)

                ghost_regions: list[BoundingBox] = []
                for i in range(1, num_features + 1):
                    region_mask = labeled_array == i
                    rows = np.any(region_mask, axis=1)
                    cols = np.any(region_mask, axis=0)

                    if np.any(rows) and np.any(cols):
                        y_min, y_max = np.where(rows)[0][[0, -1]]
                        x_min, x_max = np.where(cols)[0][[0, -1]]

                        ghost_regions.append(
                            BoundingBox(
                                x=int(x_min),
                                y=int(y_min),
                                w=int(x_max - x_min + 1),
                                h=int(y_max - y_min + 1),
                            )
                        )

                ghost_detected = len(ghost_regions) > 0

                # NEW (clear semantics: confidence = detection reliability):
                if ghost_detected:
                    # High variance = stronger ghost signal = more reliable detection of manipulation
                    confidence = round(min(0.95, max(0.60, 0.60 + (max_variance / 100.0))), 3)
                else:
                    # No ghosts detected: high confidence the image is authentic (for this test)
                    # But cap at 0.90 since absence of evidence ≠ evidence of absence
                    confidence = round(min(0.90, 0.75 + (mean_variance / 20.0)), 3)

                return {
                    "ghost_detected": ghost_detected,
                    "confidence": confidence,  # Now clearly means: "how reliable is this result?"
                    "ghost_regions": [r.to_dict() for r in ghost_regions],
                    "num_ghost_regions": len(ghost_regions),
                    "max_variance": max_variance,
                    "mean_variance": mean_variance,
                    "quality_levels_tested": quality_levels,
                    "court_defensible": True,
                    "available": True,
                }

            finally:
                for _tp in temp_files_inner:
                    try:
                        if os.path.exists(_tp):
                            os.unlink(_tp)
                    except OSError:
                        pass

        loop = _asyncio.get_running_loop()
        return await loop.run_in_executor(None, _blocking_ghost_compute)

    except ToolUnavailableError:
        raise
    except Exception as e:
        raise ToolUnavailableError(f"JPEG ghost detection failed: {str(e)}") from e


async def file_hash_verify(
    artifact: EvidenceArtifact,
    evidence_store: EvidenceStore,
) -> dict[str, Any]:
    """
    Verify file hash against stored hash in evidence store.

    Args:
        artifact: The evidence artifact to verify
        evidence_store: Evidence store containing the original hash

    Returns:
        Dictionary containing:
        - hash_matches: Boolean indicating if hashes match
        - original_hash: The stored hash
        - current_hash: The computed hash
    """
    try:
        # Verify integrity using evidence store
        hash_matches = await evidence_store.verify_artifact_integrity(artifact)

        # Compute current hash for reporting
        original_path = artifact.file_path
        if os.path.exists(original_path):
            with open(original_path, "rb") as f:
                current_hash = hashlib.sha256(f.read()).hexdigest()
        else:
            current_hash = "file_not_found"

        return {
            "hash_matches": hash_matches,
            "original_hash": artifact.content_hash,
            "current_hash": current_hash,
        }

    except Exception as e:
        return {
            "hash_matches": False,
            "original_hash": artifact.content_hash,
            "current_hash": f"error: {str(e)}",
        }


async def compute_perceptual_hash(
    artifact: EvidenceArtifact,
    hash_size: int = 8,
) -> dict[str, Any]:
    """
    Compute perceptual hash for image comparison.

    Uses multiple hash algorithms for robust comparison.

    Args:
        artifact: The evidence artifact to hash
        hash_size: Size of the hash (default 8 for 64-bit hash)

    Returns:
        Dictionary containing:
        - phash: Perceptual hash
        - ahash: Average hash
        - dhash: Difference hash
        - whash: Wavelet hash
    """
    try:
        original_path = artifact.file_path
        if not os.path.exists(original_path):
            raise ToolUnavailableError(f"File not found: {original_path}")

        with Image.open(original_path) as _img:
            original = _img.convert("RGB") if _img.mode != "RGB" else _img.copy()

        # Compute various perceptual hashes
        phash = str(imagehash.phash(original, hash_size=hash_size))
        ahash = str(imagehash.average_hash(original, hash_size=hash_size))
        dhash = str(imagehash.dhash(original, hash_size=hash_size))
        whash = str(imagehash.whash(original, hash_size=hash_size))

        return {
            "phash": phash,
            "ahash": ahash,
            "dhash": dhash,
            "whash": whash,
            # 0.85: hash successfully computed, tool is reliable.
            # None is intentionally avoided — _wrap_tool only injects a default when the
            # key is absent, so None would propagate and break downstream calibration.
            "confidence": 0.85,
            "note": "Hash computed. No reference hash available — similarity requires a second image.",
            "court_defensible": True,
            "available": True,
        }

    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"Perceptual hash computation failed: {str(e)}") from e


async def frequency_domain_analysis(
    artifact: EvidenceArtifact,
) -> dict[str, Any]:  # noqa: C901
    """
    Perform frequency domain analysis using DFT.

    Analyzes the Discrete Fourier Transform of the image to detect
    anomalies that may indicate manipulation.

    Args:
        artifact: The evidence artifact to analyze

    Returns:
        Dictionary containing:
        - frequency_spectrum: 2D frequency spectrum (as list)
        - dominant_frequencies: List of dominant frequency components
        - anomaly_score: Score indicating frequency domain anomalies
    """
    try:
        original_path = artifact.file_path
        if not os.path.exists(original_path):
            raise ToolUnavailableError(f"File not found: {original_path}")

        # ── offload blocking FFT computation to a thread ──────────────────────
        import asyncio as _asyncio

        def _blocking_fft_compute() -> dict:
            with Image.open(original_path) as _img:
                original = _img.convert("L") if _img.mode != "L" else _img.copy()
            img_array = np.array(original, dtype=np.float64)

            # Apply 2D DFT
            dft = np.fft.fft2(img_array)
            dft_shift = np.fft.fftshift(dft)
            magnitude_spectrum = np.abs(dft_shift)

            # Calculate anomaly score based on frequency distribution.
            # Natural images follow a 1/f^2 power spectrum — most squared energy
            # concentrates in the inscribed-circle low-frequency region.
            # Empirically the corners contain ~5–15% for real photos.
            center = np.array(magnitude_spectrum.shape) // 2
            y, x = np.ogrid[
                : magnitude_spectrum.shape[0], : magnitude_spectrum.shape[1]
            ]
            distances = np.sqrt((x - center[1]) ** 2 + (y - center[0]) ** 2)

            low_freq_mask = distances < min(center)
            high_freq_mask = ~low_freq_mask

            low_freq_energy = float(np.sum(magnitude_spectrum[low_freq_mask] ** 2))
            high_freq_energy = float(np.sum(magnitude_spectrum[high_freq_mask] ** 2))
            total_energy = low_freq_energy + high_freq_energy + 1e-10

            high_freq_ratio = high_freq_energy / total_energy
            natural_ceil = 0.20
            anomaly_score = round(
                min(1.0, max(0.0, (high_freq_ratio - natural_ceil) / natural_ceil)), 3
            )
            anomaly_detected = anomaly_score >= 0.4
            confidence = (
                round(0.55 + (anomaly_score * 0.35), 3)
                if anomaly_detected
                else round(0.70 - (anomaly_score * 0.25), 3)
            )

            # Return summary statistics only — omit frequency_spectrum / dominant_frequencies
            # arrays (W×H floats ≈ 16 MB for 1080p) to prevent memory and serialisation pressure.
            return {
                "anomaly_score": anomaly_score,
                "anomaly_detected": anomaly_detected,
                "confidence": confidence,
                "low_freq_ratio": round(low_freq_energy / total_energy, 4),
                "high_freq_ratio": round(high_freq_ratio, 4),
                "court_defensible": False,
                "available": True,
                "limitation_note": (
                    "Basic DFT high-frequency ratio — supporting signal only, "
                    "not a standalone manipulation indicator."
                ),
            }

        loop = _asyncio.get_running_loop()
        return await loop.run_in_executor(None, _blocking_fft_compute)

    except ToolUnavailableError:
        raise
    except Exception as e:
        raise ToolUnavailableError(f"Frequency domain analysis failed: {str(e)}") from e


async def extract_text_from_image(
    artifact: EvidenceArtifact,
    timeout: float | None = None,
) -> dict[str, Any]:
    """
    Extract visible text from an image using OCR (Tesseract/pytesseract).

    Uses OpenCV for preprocessing to improve OCR accuracy on forensic images,
    including adaptive thresholding for handling varied lighting conditions.
    Runs blocking OCR in a thread executor with a timeout to prevent hangs.
    """
    import asyncio as _asyncio
    from core.config import get_settings
    _timeout = timeout or get_settings().ocr_tool_timeout

    def _run_ocr():
        import cv2
        import numpy as np
        import pytesseract
        from PIL import Image as PILImage

        original_path = artifact.file_path
        if not os.path.exists(original_path):
            raise ToolUnavailableError(f"File not found: {original_path}")

        # Load image with PIL and convert to OpenCV format
        with PILImage.open(original_path) as _pil:
            pil_image = _pil.convert("RGB") if _pil.mode != "RGB" else _pil.copy()

        # Convert PIL to OpenCV (RGB to BGR)
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

        # Preprocess for better OCR
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )

        _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        custom_config = r"--oem 3 --psm 6 -l eng"

        text_adaptive = pytesseract.image_to_string(thresh, config=custom_config)
        text_otsu = pytesseract.image_to_string(otsu, config=custom_config)
        text_original = pytesseract.image_to_string(gray, config=custom_config)

        texts = [text_adaptive, text_otsu, text_original]
        best_text = max(texts, key=lambda t: len(t.strip()))
        lines = [line.strip() for line in best_text.split("\n") if line.strip()]

        data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
        word_count = sum(1 for text in data["text"] if text.strip())

        confidences = [conf for conf in data["conf"] if conf > 0]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0

        return {
            "status": "real",
            "court_defensible": True,
            "method": "Tesseract OCR v4+ with adaptive preprocessing",
            "extracted_text": lines,
            "raw_text": best_text,
            "word_count": word_count,
            "has_text": word_count > 0,
            "success": True,
            "confidence": round(avg_confidence / 100, 4)
            if avg_confidence > 0
            else None,
        }

    try:
        loop = _asyncio.get_running_loop()
        return await _asyncio.wait_for(
            loop.run_in_executor(None, _run_ocr),
            timeout=_timeout,
        )
    except TimeoutError:
        return {
            "status": "timeout",
            "court_defensible": False,
            "error": f"OCR timed out after {_timeout}s",
            "extracted_text": [],
            "raw_text": "",
            "word_count": 0,
            "has_text": False,
            "success": False,
        }
    except ImportError:
        return {
            "status": "unavailable",
            "court_defensible": False,
            "error": "pytesseract not installed. Install with: pip install pytesseract",
            "extracted_text": [],
            "raw_text": "",
            "word_count": 0,
            "has_text": False,
            "success": False,
        }
    except ToolUnavailableError:
        raise
    except Exception as e:
        return {
            "status": "error",
            "court_defensible": False,
            "error": f"OCR extraction failed: {str(e)}",
            "extracted_text": [],
            "raw_text": "",
            "word_count": 0,
            "has_text": False,
            "success": False,
        }


async def analyze_image_content(
    artifact: EvidenceArtifact,
    custom_categories: list[str] | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """
    Analyze image content using CLIP for semantic understanding.

    Uses zero-shot classification to determine what type of image this is,
    providing context for forensic analysis. This helps the agent understand
    whether it's analyzing a document screenshot, surveillance footage,
    social media post, etc.

    Args:
        artifact: The evidence artifact to analyze
        custom_categories: Optional list of custom category descriptions.
                          If not provided, uses default forensic categories.

    Returns:
        Dictionary containing:
        - image_type: Top classification result (what the image depicts)
        - confidence: Confidence score for the top classification
        - all_classifications: List of all category scores
        - semantic_context: Human-readable description of image type
        - available: Whether CLIP analysis was available
        - court_defensible: Whether this method is court-defensible
        - error: Error message if analysis failed
    """
    try:
        from core.config import get_settings
        _timeout = timeout or get_settings().clip_analysis_timeout
        from tools.clip_utils import get_clip_analyzer

        original_path = artifact.file_path
        if not os.path.exists(original_path):
            raise ToolUnavailableError(f"File not found: {original_path}")

        analyzer = get_clip_analyzer()

        categories = custom_categories if custom_categories else None
        # Run blocking CLIP inference in a thread executor so it doesn't stall
        # the asyncio event loop (first call loads ~300 MB model from disk).
        # Wrap with a timeout to prevent indefinite hangs.
        import asyncio as _asyncio

        loop = _asyncio.get_running_loop()
        result = await _asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: analyzer.analyze_image(original_path, categories=categories),
            ),
            timeout=_timeout,
        )

        if not result.available:
            return {
                "status": "unavailable",
                "image_type": "unknown",
                "confidence": 0.0,
                "all_classifications": [],
                "semantic_context": "Image content analysis unavailable",
                "available": False,
                "court_defensible": False,
                "error": result.error or "CLIP model unavailable",
            }

        # Generate semantic context based on top match
        semantic_templates = {
            "a screenshot of a document": "Document screenshot - text content expected",
            "an outdoor photograph": "Outdoor scene - natural lighting analysis relevant",
            "an indoor photograph": "Indoor scene - artificial lighting patterns",
            "a social media post": "Social media content - metadata gaps expected",
            "a surveillance camera frame": "Surveillance footage - low quality expected",
            "a digitally generated or AI image": "Potentially AI-generated - deepfake check recommended",
            "a scanned photograph": "Scanned photo - print artifacts may be present",
            "a news article image": "News media - editorial context relevant",
            "a passport or identification document": "Identity document - security features expected",
            "a screenshot of a chat conversation": "Chat/messaging screenshot - authenticity check",
            "a forensic evidence photograph": "Evidence photo - chain of custody critical",
            "a product or commercial image": "Commercial image - possible manipulation for marketing",
        }

        semantic_context = semantic_templates.get(
            result.top_match, f"Image classified as: {result.top_match}"
        )

        return {
            "status": "real",
            "image_type": result.top_match,
            "confidence": result.top_confidence,
            "all_classifications": [
                {"category": cat, "score": score} for cat, score in result.all_scores
            ],
            "semantic_context": semantic_context,
            "available": True,
            "court_defensible": True,
            "method": "CLIP ViT-B-32 zero-shot classification",
            "error": None,
        }

    except ToolUnavailableError:
        raise
    except Exception as e:
        return {
            "status": "error",
            "image_type": "unknown",
            "confidence": 0.0,
            "all_classifications": [],
            "semantic_context": "Image content analysis failed",
            "available": False,
            "court_defensible": False,
            "error": str(e),
        }
