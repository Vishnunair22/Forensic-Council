#!/usr/bin/env python3
"""
Grid-based lighting correlation scanner.

Compares dominant edge/shadow angles across image regions. It complements
lighting_analyzer.py by looking for local lighting disagreement rather than a
single whole-frame angle spread.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None


def _dominant_angle(gray: np.ndarray) -> float | None:
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=35, minLineLength=20, maxLineGap=8)
    if lines is None or len(lines) < 2:
        return None
    angles = []
    for line in lines[:40]:
        x1, y1, x2, y2 = line[0]
        angles.append(float(np.degrees(np.arctan2(y2 - y1, x2 - x1))))
    # Axial angle: shadows at theta and theta+180 are equivalent.
    doubled = np.radians(np.asarray(angles) * 2.0)
    mean = 0.5 * np.degrees(np.arctan2(np.mean(np.sin(doubled)), np.mean(np.cos(doubled))))
    return float(mean)


def correlate_lighting(path: str) -> dict[str, Any]:
    if cv2 is None:
        return _correlate_lighting_pil(path)

    img = cv2.imread(path)
    if img is None:
        return {"error": "Cannot read image", "available": False}
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    angles: list[dict[str, Any]] = []
    for gy in range(3):
        for gx in range(3):
            y1, y2 = gy * h // 3, (gy + 1) * h // 3
            x1, x2 = gx * w // 3, (gx + 1) * w // 3
            roi = gray[y1:y2, x1:x2]
            angle = _dominant_angle(roi)
            if angle is not None:
                angles.append({"cell": [gx, gy], "angle_deg": round(angle, 2)})

    if len(angles) < 3:
        return {
            "available": True,
            "court_defensible": False,
            "lighting_consistent": True,
            "mismatch_detected": False,
            "confidence": 0.42,
            "reason": "Insufficient regional edge structure for correlation.",
            "regional_angles": angles,
        }

    vals = np.asarray([a["angle_deg"] for a in angles], dtype=float)
    doubled = np.radians(vals * 2.0)
    r = float(np.sqrt(np.mean(np.cos(doubled)) ** 2 + np.mean(np.sin(doubled)) ** 2))
    dispersion = float(1.0 - r)
    mismatch = dispersion >= 0.42
    return {
        "available": True,
        "court_defensible": True,
        "backend": "regional-hough-lighting-correlation",
        "lighting_consistent": not mismatch,
        "mismatch_detected": mismatch,
        "correlation_score": round(max(0.0, min(1.0, r)), 3),
        "dispersion_score": round(dispersion, 3),
        "confidence": round(dispersion if mismatch else max(0.62, r), 3),
        "regional_angles": angles,
        "regions_analyzed": len(angles),
    }


def _cell_gradient_angle(cell: np.ndarray) -> float | None:
    gy, gx = np.gradient(cell.astype(np.float32))
    mag = np.sqrt(gx * gx + gy * gy)
    strong = mag > np.percentile(mag, 80)
    if int(np.sum(strong)) < 20:
        return None
    angle = np.degrees(np.arctan2(gy[strong], gx[strong]))
    doubled = np.radians(angle * 2.0)
    return float(0.5 * np.degrees(np.arctan2(np.mean(np.sin(doubled)), np.mean(np.cos(doubled)))))


def _correlate_lighting_pil(path: str) -> dict[str, Any]:
    try:
        from PIL import Image

        with Image.open(path) as img:
            gray = np.asarray(img.convert("L"), dtype=np.float32)
    except Exception as exc:
        return {"error": f"Cannot read image: {exc}", "available": False}

    h, w = gray.shape
    angles: list[dict[str, Any]] = []
    for gy in range(3):
        for gx in range(3):
            y1, y2 = gy * h // 3, (gy + 1) * h // 3
            x1, x2 = gx * w // 3, (gx + 1) * w // 3
            angle = _cell_gradient_angle(gray[y1:y2, x1:x2])
            if angle is not None:
                angles.append({"cell": [gx, gy], "angle_deg": round(angle, 2)})

    if len(angles) < 3:
        return {
            "available": True,
            "court_defensible": False,
            "lighting_consistent": True,
            "mismatch_detected": False,
            "confidence": 0.40,
            "backend": "pil-gradient-lighting-correlation",
            "reason": "Insufficient regional gradient structure for correlation.",
            "regional_angles": angles,
        }

    vals = np.asarray([a["angle_deg"] for a in angles], dtype=float)
    doubled = np.radians(vals * 2.0)
    r = float(np.sqrt(np.mean(np.cos(doubled)) ** 2 + np.mean(np.sin(doubled)) ** 2))
    dispersion = float(1.0 - r)
    mismatch = dispersion >= 0.46
    return {
        "available": True,
        "court_defensible": False,
        "backend": "pil-gradient-lighting-correlation",
        "lighting_consistent": not mismatch,
        "mismatch_detected": mismatch,
        "correlation_score": round(max(0.0, min(1.0, r)), 3),
        "dispersion_score": round(dispersion, 3),
        "confidence": round(dispersion if mismatch else max(0.58, r), 3),
        "regional_angles": angles,
        "regions_analyzed": len(angles),
        "degraded": True,
        "fallback_reason": "OpenCV unavailable; used PIL/numpy gradient fallback.",
    }


def _worker() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            path = req.get("input")
            result = (
                correlate_lighting(path)
                if path
                else {"error": "Missing input path", "available": False}
            )
        except Exception as exc:
            result = {"error": str(exc), "available": False}
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--warmup", action="store_true")
    args = parser.parse_args()
    if args.warmup:
        print(json.dumps({"status": "warmed_up", "available": True}))
        sys.exit(0)
    if args.worker:
        _worker()
        sys.exit(0)
    if not args.input:
        parser.print_help()
        sys.exit(1)
    try:
        print(json.dumps(correlate_lighting(args.input)))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "available": False}))
