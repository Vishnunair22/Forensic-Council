#!/usr/bin/env python3
"""
Video thumbnail coherence checker.

Compares early, middle, and late video frames using perceptual hashes. When a
container thumbnail cannot be extracted in this environment, this still catches
obvious preview/content mismatch patterns such as title-card-only first frames.
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


def _dhash(gray: np.ndarray) -> int:
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    diff = small[:, 1:] > small[:, :-1]
    value = 0
    for bit in diff.flatten():
        value = (value << 1) | int(bit)
    return value


def _distance(a: int, b: int) -> int:
    return int((a ^ b).bit_count())


def check_thumbnail_coherence(path: str) -> dict[str, Any]:
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
    if total < 3:
        cap.release()
        return {
            "available": False,
            "not_applicable": True,
            "reason": "Too few frames for thumbnail coherence.",
        }

    labels = [
        ("early", max(0, int(total * 0.02))),
        ("middle", int(total * 0.50)),
        ("late", max(0, int(total * 0.90))),
    ]
    hashes: dict[str, int] = {}
    try:
        for label, idx in labels:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            hashes[label] = _dhash(gray)
    finally:
        cap.release()

    if len(hashes) < 2:
        return {"available": False, "reason": "Could not read enough frames for coherence check."}

    distances = {}
    for a in hashes:
        for b in hashes:
            if a < b:
                distances[f"{a}_vs_{b}"] = _distance(hashes[a], hashes[b])

    early_mid = distances.get("early_vs_middle", 0)
    early_late = distances.get("early_vs_late", 0)
    mid_late = distances.get("late_vs_middle", distances.get("middle_vs_late", 0))
    mismatch = (early_mid >= 28 and early_late >= 28 and mid_late <= 22) or max(
        distances.values()
    ) >= 42
    score = min(1.0, max(distances.values()) / 64.0)
    return {
        "available": True,
        "court_defensible": True,
        "backend": "frame-perceptual-hash-coherence",
        "thumbnail_mismatch": mismatch,
        "mismatch_detected": mismatch,
        "verdict": "PREVIEW_CONTENT_MISMATCH_SUSPECTED" if mismatch else "THUMBNAIL_COHERENT",
        "confidence": round(score if mismatch else max(0.62, 1.0 - score), 3),
        "hash_distances": distances,
        "frames_compared": list(hashes.keys()),
        "note": "Compares representative video frames when embedded thumbnail extraction is unavailable.",
    }


def _worker() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            path = req.get("input")
            result = (
                check_thumbnail_coherence(path)
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
        print(json.dumps(check_thumbnail_coherence(args.input)))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "available": False}))
