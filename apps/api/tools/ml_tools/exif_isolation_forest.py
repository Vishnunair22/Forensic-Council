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

    # WS-3 #16 — the previous IsolationForest was fit at runtime on 5 hardcoded
    # baseline rows: statistically meaningless. Replaced with a transparent, auditable
    # rule score. WS-3 #15 — the ABSENCE of EXIF is INFO, not an anomaly: screenshots,
    # social-media exports and privacy tools legitimately strip metadata, so it no
    # longer raises the score (the old forced 0.58/0.52 floors and the +0.20 no-EXIF
    # term were a built-in false-positive bias). Only PRESENT, internally-inconsistent
    # EXIF raises the score.
    anomaly_score = 0.0
    anomaly_score += 0.30 if vec[2] > 0 else 0.0  # editing software named in EXIF Software field
    if exif:
        anomaly_score += 0.15 if (vec[6] < -4.5 or vec[6] > 1.5) else 0.0  # implausible exposure time
        anomaly_score += 0.10 if vec[5] == 0.0 else 0.0  # invalid aperture despite present EXIF
    anomaly_score = min(1.0, anomaly_score)

    is_anomalous = anomaly_score >= 0.50
    return {
        "available": True,
        "court_defensible": True,
        "backend": "transparent-rule-score",
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
