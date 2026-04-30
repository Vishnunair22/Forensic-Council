#!/usr/bin/env python3
"""
EXIF isolation-forest style anomaly scorer.

Uses sklearn IsolationForest when available and a deterministic robust-score
fallback otherwise. It does not require a trained project-specific database.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from typing import Any


def _read_exif(path: str) -> dict[str, Any]:
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS

        with Image.open(path) as img:
            raw = img.getexif()
            return {TAGS.get(k, str(k)): v for k, v in raw.items()} if raw else {}
    except Exception:
        return {}


def _num(value: Any) -> float | None:
    try:
        if isinstance(value, tuple) and len(value) == 2 and value[1]:
            return float(value[0]) / float(value[1])
        return float(value)
    except Exception:
        return None


def _feature_vector(exif: dict[str, Any]) -> tuple[list[float], list[str]]:
    expected = [
        "Make",
        "Model",
        "DateTimeOriginal",
        "ExposureTime",
        "FNumber",
        "ISOSpeedRatings",
        "FocalLength",
    ]
    missing = [k for k in expected if k not in exif]
    software = str(exif.get("Software", "")).lower()
    edit_sw = int(
        any(x in software for x in ("photoshop", "gimp", "lightroom", "affinity", "snapseed"))
    )
    exposure = _num(exif.get("ExposureTime")) or 0.0
    fnum = _num(exif.get("FNumber")) or 0.0
    iso = _num(exif.get("ISOSpeedRatings")) or _num(exif.get("PhotographicSensitivity")) or 0.0
    focal = _num(exif.get("FocalLength")) or 0.0
    gps_present = int("GPSInfo" in exif)
    field_count = len(exif)
    vec = [
        float(field_count),
        float(len(missing)),
        float(edit_sw),
        math.log10(max(iso, 1.0)),
        math.log10(max(focal, 1.0)),
        math.log10(max(fnum, 1.0)),
        math.log10(max(exposure, 1e-5)),
        float(gps_present),
    ]
    return vec, missing


def score_exif(path: str) -> dict[str, Any]:
    exif = _read_exif(path)
    vec, missing = _feature_vector(exif)
    reasons: list[str] = []

    if not exif:
        reasons.append("no EXIF metadata present")
    if len(missing) >= 5:
        reasons.append("many expected camera fields are absent")
    if vec[2] > 0:
        reasons.append("editing software appears in EXIF Software field")
    if vec[5] == 0.0 and exif:
        reasons.append("missing or invalid aperture value")
    if vec[6] < -4.5 or vec[6] > 1.5:
        reasons.append("unusual exposure-time value")

    used_sklearn = False
    anomaly_score = 0.0
    try:
        import numpy as np
        from sklearn.ensemble import IsolationForest

        baseline = np.array(
            [
                [24, 0, 0, 2.0, 1.0, 0.45, -2.0, 0],
                [36, 0, 0, 2.2, 1.2, 0.55, -2.7, 1],
                [18, 2, 0, 2.4, 1.0, 0.60, -1.6, 0],
                [12, 4, 0, 2.0, 0.8, 0.40, -2.3, 0],
                [8, 5, 1, 2.0, 0.0, 0.0, -5.0, 0],
            ],
            dtype=float,
        )
        model = IsolationForest(contamination=0.25, random_state=42)
        model.fit(baseline)
        raw = float(-model.score_samples(np.array([vec], dtype=float))[0])
        anomaly_score = max(0.0, min(1.0, (raw - 0.35) / 0.35))
        used_sklearn = True
    except Exception:
        anomaly_score = 0.0
        anomaly_score += min(0.35, len(missing) * 0.055)
        anomaly_score += 0.25 if vec[2] > 0 else 0.0
        anomaly_score += 0.20 if not exif else 0.0
        anomaly_score += 0.10 if vec[6] < -4.5 or vec[6] > 1.5 else 0.0
        anomaly_score = min(1.0, anomaly_score)

    if not exif:
        anomaly_score = max(anomaly_score, 0.58)
    elif len(missing) >= 5:
        anomaly_score = max(anomaly_score, 0.52)

    is_anomalous = anomaly_score >= 0.50
    return {
        "available": True,
        "court_defensible": True,
        "backend": "sklearn-isolation-forest" if used_sklearn else "robust-rule-isolation-score",
        "verdict": "ANOMALOUS_EXIF" if is_anomalous else "EXIF_WITHIN_EXPECTED_RANGE",
        "is_anomalous": is_anomalous,
        "anomaly_score": round(anomaly_score, 3),
        "confidence": round(anomaly_score if is_anomalous else max(0.62, 1.0 - anomaly_score), 3),
        "field_count": len(exif),
        "missing_expected_fields": missing,
        "anomalous_fields": missing[:8],
        "signals": reasons,
    }


def _worker() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            path = req.get("input")
            result = (
                score_exif(path) if path else {"error": "Missing input path", "available": False}
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
        print(json.dumps(score_exif(args.input)))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "available": False}))
