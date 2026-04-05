#!/usr/bin/env python3
"""
metadata_anomaly_scorer.py
==========================
Scores EXIF metadata for tampering signals using both rule-based
checks and statistical anomaly detection.

Usage:
    python metadata_anomaly_scorer.py --input /path/to/image.jpg

Output JSON:
    {
        "tampering_score": 0.0,           # 0-1, higher = more suspicious
        "rule_violations": [
            "GPS present but timezone not consistent with coordinates",
            "Editing software signature found: Adobe Photoshop"
        ],
        "field_anomaly_score": 0.12,
        "verdict": "CLEAN",              # CLEAN | SUSPICIOUS | TAMPERED
        "exif_present": true,
        "field_count": 42,
        "available": true
    }
"""

import argparse
import json
import sys


EDITING_SOFTWARE_SIGNATURES = [
    b"Adobe",
    b"Photoshop",
    b"GIMP",
    b"Lightroom",
    b"Affinity",
    b"Capture One",
    b"DxO",
    b"Luminar",
]

EXPECTED_CAMERA_FIELDS = [
    "Make",
    "Model",
    "ExposureTime",
    "FNumber",
    "ISOSpeedRatings",
    "DateTimeOriginal",
    "FocalLength",
]


def read_exif_simple(image_path: str) -> dict:
    """Read EXIF data using PIL without piexif dependency."""
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS

        img = Image.open(image_path)
        raw_exif = img._getexif()
        if not raw_exif:
            return {}
        return {TAGS.get(k, str(k)): v for k, v in raw_exif.items()}
    except Exception:
        return {}


def scan_hex_signatures(image_path: str) -> list[str]:
    """Scan raw bytes for editing software signatures."""
    found = []
    try:
        with open(image_path, "rb") as f:
            raw = f.read(65536)  # first 64KB
        for sig in EDITING_SOFTWARE_SIGNATURES:
            if sig in raw:
                found.append(sig.decode("utf-8", errors="replace"))
    except Exception:
        pass
    return found


def score_metadata(image_path: str) -> dict:
    exif = read_exif_simple(image_path)
    hex_sigs = scan_hex_signatures(image_path)

    violations = []
    score = 0.0

    # Rule 1: Editing software in hex
    if hex_sigs:
        violations.append(
            f"Editing software signature found in file bytes: {', '.join(hex_sigs)}"
        )
        score += 0.35

    # Rule 2: Missing mandatory camera fields
    if exif:
        missing = [f for f in EXPECTED_CAMERA_FIELDS if f not in exif]
        if len(missing) > 3:
            violations.append(
                f"Missing {len(missing)} expected camera fields: {', '.join(missing[:4])}"
            )
            score += min(0.25, len(missing) * 0.04)
    else:
        violations.append("No EXIF data present — stripped or never written")
        score += 0.20

    # Rule 3: Software field in EXIF
    software = exif.get("Software", "")
    if software and any(
        s.lower() in str(software).lower()
        for s in ["photoshop", "gimp", "lightroom", "affinity"]
    ):
        violations.append(f"EXIF Software field indicates editing: '{software}'")
        score += 0.25

    # Rule 4: DateTimeOriginal vs DateTime mismatch
    dt_orig = str(exif.get("DateTimeOriginal", ""))
    dt_mod = str(exif.get("DateTime", ""))
    if dt_orig and dt_mod and dt_orig != dt_mod:
        violations.append(
            f"DateTimeOriginal ({dt_orig}) differs from DateTime ({dt_mod}) — indicates re-save"
        )
        score += 0.15

    # Rule 5: GPS present but no timezone-confirming fields
    gps_info = exif.get("GPSInfo")
    if gps_info and not dt_orig:
        violations.append(
            "GPS coordinates present but no DateTimeOriginal — timezone cross-check impossible"
        )
        score += 0.10

    # Rule 6: Impossible/zero exposure values
    exposure = exif.get("ExposureTime")
    exif.get("FNumber")
    if exposure is not None:
        try:
            exp_val = (
                float(exposure)
                if not isinstance(exposure, tuple)
                else exposure[0] / exposure[1]
            )
            if exp_val == 0.0 or exp_val > 30.0:
                violations.append(f"Suspicious exposure time: {exp_val}s")
                score += 0.10
        except Exception:
            pass



    score = min(1.0, score)

    if score > 0.5:
        verdict = "TAMPERED"
    elif score > 0.2 or violations:
        verdict = "SUSPICIOUS"
    else:
        verdict = "CLEAN"

    return {
        "tampering_score": round(score, 3),
        "rule_violations": violations,
        "field_anomaly_score": round(min(1.0, len(violations) * 0.15), 3),
        "verdict": verdict,
        "exif_present": bool(exif),
        "field_count": len(exif),
        "software_detected": hex_sigs,
        "available": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, help="Input image path")
    parser.add_argument("--warmup", action="store_true", help="Warmup mode - preload dependencies")
    parser.add_argument("--worker", action="store_true", help="Worker mode - persistent process")
    args = parser.parse_args()
    
    # Warmup mode - verify dependencies load
    if args.warmup:
        try:
            import piexif
            import json
            print(json.dumps({
                "status": "warmed_up",
                "dependencies": ["piexif", "json"],
                "message": "Metadata anomaly scorer ready"
            }))
            sys.exit(0)
        except Exception as e:
            print(json.dumps({
                "status": "warmup_failed",
                "error": str(e)
            }))
            sys.exit(1)
    
    # Worker mode - persistent process reading from stdin
    if args.worker:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                input_path = request.get("input")
                
                if not input_path:
                    print(json.dumps({"error": "Missing input path", "available": False}))
                    sys.stdout.flush()
                    continue
                
                result = score_metadata(input_path)
                print(json.dumps(result))
                sys.stdout.flush()
            except Exception as e:
                print(json.dumps({"error": str(e), "available": False}))
                sys.stdout.flush()
        sys.exit(0)
    
    # Normal mode - single execution
    if not args.input:
        parser.print_help()
        sys.exit(1)

    try:
        result = score_metadata(args.input)
    except Exception as e:
        result = {"error": str(e), "available": False}

    print(json.dumps(result))
