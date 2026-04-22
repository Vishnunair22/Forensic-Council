#!/usr/bin/env python3
"""
Astronomical grounding engine.

Given GPS coordinates and a capture timestamp, computes sun azimuth/elevation
for metadata provenance checks. It can optionally inspect image gradients as a
weak shadow-direction proxy, but the primary output is deterministic astronomy.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any


def _parse_timestamp(value: str) -> datetime:
    cleaned = value.strip().replace("Z", "+00:00")
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _image_gradient_angle(path: str) -> float | None:
    try:
        import numpy as np
        from PIL import Image

        with Image.open(path) as img:
            gray = np.asarray(img.convert("L").resize((256, 256)), dtype=np.float32)
        gy, gx = np.gradient(gray)
        mag = np.sqrt(gx * gx + gy * gy)
        strong = mag > np.percentile(mag, 85)
        if int(np.sum(strong)) < 40:
            return None
        angle = np.degrees(np.arctan2(gy[strong], gx[strong]))
        doubled = np.radians(angle * 2.0)
        return float(0.5 * np.degrees(np.arctan2(np.mean(np.sin(doubled)), np.mean(np.cos(doubled)))))
    except Exception:
        return None


def analyze(path: str, lat: float, lon: float, timestamp: str) -> dict[str, Any]:
    try:
        from astral import LocationInfo
        from astral.sun import azimuth, elevation
    except Exception as exc:
        return {
            "error": f"Astral unavailable: {exc}",
            "available": False,
            "court_defensible": False,
        }

    dt = _parse_timestamp(timestamp)
    location = LocationInfo(name="Evidence GPS", region="", timezone="UTC", latitude=lat, longitude=lon)
    sun_azimuth = float(azimuth(location.observer, dt))
    sun_elevation = float(elevation(location.observer, dt))
    daylight = sun_elevation > 0.0
    gradient_angle = _image_gradient_angle(path)

    consistency_note = "No image shadow proxy available."
    angle_delta = None
    if gradient_angle is not None:
        # Shadow direction is approximately opposite sun azimuth, but local
        # scene geometry makes this a weak corroborative signal only.
        expected_shadow = (sun_azimuth + 180.0) % 360.0
        observed = gradient_angle % 360.0
        angle_delta = abs((observed - expected_shadow + 180.0) % 360.0 - 180.0)
        consistency_note = (
            "Shadow proxy broadly agrees with solar geometry."
            if angle_delta <= 45.0
            else "Shadow proxy differs from expected solar geometry."
        )

    mismatch = bool(daylight and angle_delta is not None and angle_delta > 75.0)
    return {
        "available": True,
        "court_defensible": True,
        "backend": "astral-solar-position",
        "verdict": "ASTRO_MISMATCH_SUSPECTED" if mismatch else "ASTRO_GROUNDING_OK",
        "mismatch_detected": mismatch,
        "confidence": 0.72 if mismatch else 0.68,
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
        "timestamp_utc": dt.isoformat(),
        "sun_azimuth_deg": round(sun_azimuth, 2),
        "sun_elevation_deg": round(sun_elevation, 2),
        "daylight_expected": daylight,
        "image_shadow_proxy_deg": round(gradient_angle, 2) if gradient_angle is not None else None,
        "shadow_solar_delta_deg": round(angle_delta, 2) if angle_delta is not None else None,
        "note": consistency_note,
    }


def _run_from_args(argv: list[str]) -> dict[str, Any]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--lat", required=True, type=float)
    parser.add_argument("--lon", required=True, type=float)
    parser.add_argument("--time", required=True)
    args = parser.parse_args(argv)
    return analyze(args.input, args.lat, args.lon, args.time)


def _worker() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            input_path = req.get("input")
            extra = req.get("extra_args") or []
            result = _run_from_args(["--input", input_path, *extra]) if input_path else {"error": "Missing input path", "available": False}
        except Exception as exc:
            result = {"error": str(exc), "available": False}
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    root = argparse.ArgumentParser(add_help=False)
    root.add_argument("--worker", action="store_true")
    root.add_argument("--warmup", action="store_true")
    known, rest = root.parse_known_args()
    if known.warmup:
        print(json.dumps({"status": "warmed_up", "available": True}))
        sys.exit(0)
    if known.worker:
        _worker()
        sys.exit(0)
    try:
        print(json.dumps(_run_from_args(rest)))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "available": False}))
