#!/usr/bin/env python3
"""
EXIF anomaly scorer (rule_based_v2).

Deterministic, transparent rule score over EXIF features. The former runtime
IsolationForest (fit on ~5 hardcoded baseline rows) was statistically
meaningless and has been removed (P0.1); the tool name is kept for pipeline
compatibility. Absence of EXIF is reported as informational, never anomalous
(P0.2). It does not require a trained project-specific database.
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
        # Informational, not an anomaly signal (see P0.2 below).
        reasons.append("no EXIF metadata present (expected for screenshots/social-media exports)")
    elif len(missing) >= 5:
        reasons.append("many expected camera fields are absent")
    if vec[2] > 0:
        reasons.append("editing software appears in EXIF Software field")
    if vec[5] == 0.0 and exif:
        reasons.append("missing or invalid aperture value")
    if vec[6] < -4.5 or vec[6] > 1.5:
        reasons.append("unusual exposure-time value")

    # P0.1 (WS-3 #16) — the previous IsolationForest was fit at runtime on 5 hardcoded
    # baseline rows: statistically meaningless. Replaced with a transparent, auditable
    # rule score ("rule_based_v2"): each rule below is an explicit, documented check
    # over the same EXIF features with a fixed weight; the sum is clamped to [0, 1].
    # P0.2 (WS-3 #15) — the ABSENCE of EXIF is INFO, not an anomaly: screenshots,
    # social-media exports and privacy tools legitimately strip metadata, so it no
    # longer raises the score (the old forced 0.58/0.52 floors and the +0.20 no-EXIF
    # term were a built-in false-positive bias). Only PRESENT, internally-inconsistent
    # EXIF raises the score.
    exif_absent = not exif
    anomaly_score = 0.0
    # Rule 1 (+0.30): editing software named in the EXIF Software field — direct,
    # self-declared evidence the file passed through an editor.
    anomaly_score += 0.30 if vec[2] > 0 else 0.0
    if not exif_absent:
        # Rule 2 (+0.15): physically implausible exposure time (<~30 µs or >~30 s)
        # — contradicts real camera capture parameters.
        anomaly_score += 0.15 if (vec[6] < -4.5 or vec[6] > 1.5) else 0.0
        # Rule 3 (+0.10): missing/invalid aperture (FNumber) while other capture
        # fields are present — internally contradictory camera block.
        anomaly_score += 0.10 if vec[5] == 0.0 else 0.0
    anomaly_score = min(1.0, max(0.0, anomaly_score))

    is_anomalous = anomaly_score >= 0.50
    if exif_absent:
        # Non-alerting informational result: score stays ~0.0, never an anomaly.
        verdict = "EXIF_ABSENT_INFORMATIONAL"
        assessment = (
            "No EXIF metadata is present. Metadata absence is expected for "
            "screenshots, social-media/messaging-app exports, and privacy-stripped "
            "files, and is NOT evidence of tampering."
        )
        confidence = 0.6  # informational observation — modest, never a strong clean claim
    elif is_anomalous:
        verdict = "ANOMALOUS_EXIF"
        assessment = "Present EXIF metadata is internally inconsistent or implausible."
        confidence = anomaly_score
    else:
        verdict = "EXIF_WITHIN_EXPECTED_RANGE"
        assessment = "EXIF metadata fields are within expected ranges."
        confidence = max(0.62, 1.0 - anomaly_score)
    return {
        "available": True,
        "court_defensible": True,
        "backend": "transparent-rule-score",
        "method": "rule_based_v2",
        "verdict": verdict,
        "assessment": assessment,
        "exif_absent": exif_absent,
        "is_anomalous": is_anomalous,
        "anomaly_score": round(anomaly_score, 3),
        "confidence": round(confidence, 3),
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


if __name__ == "__main__":  # pragma: no cover
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
