#!/usr/bin/env python3
"""
Video-frame interpolation error mapper.

Estimates whether middle frames are unusually well predicted by neighboring
frames. Repeated low residuals can indicate frame interpolation or generated
motion smoothing; high residual spikes can indicate inserted/removed frames.
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


def map_vfi_errors(path: str, max_triplets: int = 48) -> dict[str, Any]:
    if cv2 is None:
        return {
            "error": "OpenCV is required for video frame decoding",
            "available": False,
            "degraded": True,
            "fallback_reason": "cv2 module unavailable",
        }

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return {"error": "Cannot open video", "available": False}
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    if total < 5:
        cap.release()
        return {
            "available": False,
            "not_applicable": True,
            "reason": "Too few frames for VFI analysis.",
        }

    positions = np.linspace(1, max(1, total - 2), num=min(max_triplets, total - 2), dtype=int)
    residuals: list[float] = []
    flagged: list[dict[str, Any]] = []
    try:
        for idx in positions:
            frames = []
            for frame_idx in (idx - 1, idx, idx + 1):
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
                ok, frame = cap.read()
                if not ok or frame is None:
                    frames = []
                    break
                gray = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2GRAY).astype(
                    np.float32
                )
                frames.append(gray)
            if len(frames) != 3:
                continue
            predicted = (frames[0] + frames[2]) / 2.0
            residual = float(np.mean(np.abs(frames[1] - predicted)) / 255.0)
            residuals.append(residual)
    finally:
        cap.release()

    if len(residuals) < 4:
        return {"available": False, "reason": "Could not sample enough readable frame triplets."}

    arr = np.asarray(residuals, dtype=np.float32)
    mean_res = float(np.mean(arr))
    std_res = float(np.std(arr))
    low_residual_ratio = float(np.mean(arr < 0.018))
    spike_ratio = float(np.mean(arr > mean_res + max(0.025, 2.0 * std_res)))

    score = min(
        1.0, low_residual_ratio * 0.65 + spike_ratio * 0.55 + max(0.0, 0.03 - mean_res) * 4.0
    )
    suspected = score >= 0.35
    for i, value in enumerate(arr):
        if value < 0.018 or value > mean_res + max(0.025, 2.0 * std_res):
            flagged.append({"sample_index": i, "residual": round(float(value), 5)})

    return {
        "available": True,
        "court_defensible": True,
        "backend": "neighbor-frame-residual-vfi-map",
        "vfi_suspected": suspected,
        "manipulation_detected": suspected,
        "verdict": "VFI_OR_GENERATED_MOTION_SUSPECTED" if suspected else "NO_VFI_PATTERN_DETECTED",
        "confidence": round(score if suspected else max(0.62, 1.0 - score), 3),
        "vfi_error_score": round(score, 3),
        "mean_prediction_residual": round(mean_res, 5),
        "std_prediction_residual": round(std_res, 5),
        "low_residual_ratio": round(low_residual_ratio, 3),
        "spike_ratio": round(spike_ratio, 3),
        "samples_analyzed": len(residuals),
        "flagged_samples": flagged[:20],
    }


def _worker() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            path = req.get("input")
            result = (
                map_vfi_errors(path)
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
        print(json.dumps(map_vfi_errors(args.input)))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "available": False}))
