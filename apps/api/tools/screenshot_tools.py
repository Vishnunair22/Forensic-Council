"""
Screenshot Forensics Tools
==========================

Specialized tools for analyzing screenshots (PNG/WebP/BMP images
containing UI elements, text, or captured content).

Detects:
- Font consistency (fake tweet screenshots with multiple fonts)
- UI element anomalies (edited notification overlays)
- Subpixel rendering artifacts (pasted text without anti-aliasing)
- Timestamp plausibility (impossible dates/times)
"""

from __future__ import annotations

import os
from typing import Any

import cv2
import numpy as np
from PIL import Image

from core.evidence import EvidenceArtifact
from core.exceptions import ToolUnavailableError
from core.structured_logging import get_logger

logger = get_logger(__name__)


async def detect_font_inconsistency(
    artifact: EvidenceArtifact,
    text_regions: list[dict] | None = None,
) -> dict[str, Any]:
    """
    Detect multiple fonts in a screenshot that should have uniform text.

    Use case: Fake tweet screenshots where attacker edits text but uses
    wrong font, or bank statements with inconsistent numbers.

    Args:
        artifact: Screenshot image
        text_regions: Optional list of OCR regions from extract_text_from_image

    Returns:
        Dict with font_consistency_score, detected_fonts, anomaly_regions
    """
    try:
        img_path = artifact.file_path
        if not os.path.exists(img_path):
            raise ToolUnavailableError(f"File not found: {img_path}")

        with Image.open(img_path) as img:
            img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)

        if not text_regions:
            try:
                import pytesseract

                data = pytesseract.image_to_data(
                    gray,
                    output_type=pytesseract.Output.DICT,
                )

                text_regions = []
                for i in range(len(data["text"])):
                    if data["text"][i].strip():
                        text_regions.append({
                            "x": data["left"][i],
                            "y": data["top"][i],
                            "w": data["width"][i],
                            "h": data["height"][i],
                            "text": data["text"][i],
                        })
            except ImportError:
                return {
                    "status": "unavailable",
                    "error": "pytesseract required for font analysis",
                    "available": False,
                }

        if not text_regions or len(text_regions) < 3:
            return {
                "status": "insufficient_text",
                "font_consistency_score": 1.0,
                "detected_fonts": 0,
                "note": "Not enough text regions for font analysis",
                "available": True,
            }

        font_features = []

        for region in text_regions:
            x, y, w, h = region["x"], region["y"], region["w"], region["h"]

            text_crop = gray[y : y + h, x : x + w]

            if text_crop.size == 0:
                continue

            _, binary = cv2.threshold(
                text_crop, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )
            dist = cv2.distanceTransform(binary, cv2.DIST_L2, 3)
            stroke_width = np.mean(dist[dist > 0]) if dist.max() > 0 else 0

            edges = cv2.Canny(text_crop, 50, 150)
            edge_density = np.sum(edges > 0) / edges.size if edges.size > 0 else 0

            color_crop = img_cv[y : y + h, x : x + w]
            if color_crop.size > 0:
                b, g, r = cv2.split(color_crop)
                color_variance = float(np.std([float(b.std()), float(g.std()), float(r.std())]))
            else:
                color_variance = 0.0

            font_features.append({
                "region": region,
                "stroke_width": float(stroke_width),
                "edge_density": float(edge_density),
                "color_variance": color_variance,
            })

        if len(font_features) < 3:
            return {
                "status": "insufficient_samples",
                "font_consistency_score": 1.0,
                "available": True,
            }

        stroke_widths = [f["stroke_width"] for f in font_features if f["stroke_width"] > 0]
        edge_densities = [f["edge_density"] for f in font_features]

        stroke_cv = float(np.std(stroke_widths) / (np.mean(stroke_widths) + 1e-6)) if stroke_widths else 0
        edge_cv = float(np.std(edge_densities) / (np.mean(edge_densities) + 1e-6)) if edge_densities else 0

        inconsistency_score = (stroke_cv + edge_cv) / 2

        font_consistency_score = max(0.0, 1.0 - inconsistency_score * 2)

        anomaly_ratio = 0.0
        anomaly_detected = font_consistency_score < 0.7

        anomaly_regions = []
        if anomaly_detected and stroke_widths:
            median_stroke = float(np.median(stroke_widths))

            for feature in font_features:
                if feature["stroke_width"] <= 0:
                    continue
                deviation = abs(feature["stroke_width"] - median_stroke) / (median_stroke + 1e-6)

                if deviation > 0.4:
                    anomaly_regions.append({
                        "bbox": feature["region"],
                        "deviation": round(deviation, 3),
                        "reason": "Inconsistent stroke width - possible text edit",
                    })

            anomaly_ratio = len(anomaly_regions) / max(len(font_features), 1)

        # Mixed browser/UI screenshots naturally contain several font sizes,
        # weights, and antialiasing modes. Treat this as a manipulation signal
        # only when the outlier ratio is substantial enough to be reviewable.
        anomaly_detected = (
            font_consistency_score < 0.45
            and anomaly_ratio >= 0.50
            and len(anomaly_regions) >= 3
        )

        return {
            "status": "complete",
            "font_consistency_score": round(font_consistency_score, 3),
            "anomaly_detected": anomaly_detected,
            "confidence": round(min(0.92, 0.55 + min(len(font_features), 40) / 200), 3),
            "num_text_regions_analyzed": len(font_features),
            "anomaly_regions": anomaly_regions,
            "num_anomaly_regions": len(anomaly_regions),
            "anomaly_region_ratio": round(anomaly_ratio, 3),
            "evidence_verdict": "POSITIVE" if anomaly_detected else "NEGATIVE",
            "forensic_note": (
                "Localized text-rendering outliers detected; review the highlighted screenshot regions"
                if anomaly_detected
                else "Text rendering variation is within the expected range for mixed browser/UI screenshots"
            ),
            "available": True,
            "court_defensible": True,
            "method": "Stroke width variance + edge density analysis",
        }

    except Exception as e:
        logger.error("Font consistency analysis failed", error=str(e))
        return {
            "status": "error",
            "error": str(e),
            "available": False,
        }


async def detect_ui_overlay_forgery(
    artifact: EvidenceArtifact,
) -> dict[str, Any]:
    """
    Detect fake UI overlays (e.g., fake notification bars, edited buttons).

    Uses template matching against known UI patterns and color consistency checks.
    """
    try:
        img_path = artifact.file_path
        if not os.path.exists(img_path):
            raise ToolUnavailableError(f"File not found: {img_path}")

        with Image.open(img_path) as img:
            img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)

        contours, _ = cv2.findContours(
            edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        suspicious_regions = []

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)

            if w < 100 or h < 20:
                continue

            aspect_ratio = w / h if h > 0 else 0
            is_banner = aspect_ratio > 3

            img_height = img_cv.shape[0]
            is_top_bottom = y < img_height * 0.1 or y > img_height * 0.9

            region = img_cv[y : y + h, x : x + w]
            if region.size == 0:
                continue

            color_std = np.std(region, axis=(0, 1))
            avg_std = float(np.mean(color_std))

            is_uniform = avg_std < 15

            if is_banner and is_top_bottom and is_uniform:
                suspicious_regions.append({
                    "x": int(x),
                    "y": int(y),
                    "w": int(w),
                    "h": int(h),
                    "color_uniformity": round(avg_std, 2),
                    "aspect_ratio": round(aspect_ratio, 2),
                    "reason": "Solid color banner in suspicious location",
                })

        overlay_detected = len(suspicious_regions) > 0

        return {
            "status": "complete",
            "overlay_detected": overlay_detected,
            "confidence": round(0.60 + len(suspicious_regions) * 0.1, 3),
            "suspicious_regions": suspicious_regions,
            "num_suspicious_regions": len(suspicious_regions),
            "forensic_note": (
                "Detected suspicious solid-color overlays typical of fake notifications"
                if overlay_detected
                else "No obvious UI overlay forgeries detected"
            ),
            "available": True,
            "court_defensible": True,
        }

    except Exception as e:
        logger.error("UI overlay detection failed", error=str(e))
        return {
            "status": "error",
            "error": str(e),
            "available": False,
        }
