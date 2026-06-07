#!/usr/bin/env python3
"""
Calibration score collector — the bridge between a LABELLED benchmark dataset and
``train_calibration.py``.

Runs a forensic *detector* over a labelled set of evidence files and emits the
``score,label`` CSV that ``train_calibration.py`` (Platt scaling) consumes. This
is the missing step that lets the calibration layer be fit on real ground-truth
data instead of engineering defaults.

Ground truth must be supplied two ways (pick one):
  • ``--real DIR --fake DIR``   (label 0 = authentic, label 1 = manipulated/AI)
  • ``--labels manifest.csv``   (CSV with columns: path,label)

Detectors (``--detector``):
  • ai_generation  → score = diffusion_probability   (AI-generated image P)
  • splicing       → score = splicing_score           (region tampering)
  • voice_clone    → score = clone_probability        (synthetic voice)
  (extend DETECTORS below as needed — each maps a runner to its score key.)

Usage (inside the worker container, where ML models are available):
    python scripts/collect_calibration_scores.py \
        --detector ai_generation \
        --real /data/genimage/real --fake /data/genimage/ai \
        --out /tmp/agent1_ai_scores.csv

The output feeds:
    python scripts/train_calibration.py --dataset /tmp/agent1_ai_scores.csv \
        --agent agent1_image --output-dir storage/calibration_models
Then validate + adopt with scripts/validate_calibration.py (never adopt blind).
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp", ".bmp", ".gif"}
_AUDIO_EXTS = {".wav", ".mp3", ".flac", ".aac", ".ogg", ".m4a"}


def _ai_generation_score(path: str) -> float | None:
    from tools.ml_tools.ai_generation_detector import detect

    res = detect(path)
    if not isinstance(res, dict) or res.get("error"):
        return None
    val = res.get("diffusion_probability")
    return float(val) if val is not None else None


def _splicing_score(path: str) -> float | None:
    from tools.ml_tools.splicing_detector import detect

    res = detect(path)
    if not isinstance(res, dict) or res.get("error"):
        return None
    val = res.get("splicing_score")
    return float(val) if val is not None else None


def _voice_clone_score(path: str) -> float | None:
    from tools.ml_tools.voice_clone_detector import detect

    res = detect(path)
    if not isinstance(res, dict) or res.get("error"):
        return None
    val = res.get("clone_probability", res.get("synthetic_probability"))
    return float(val) if val is not None else None


# detector name → (runner, allowed extensions)
DETECTORS = {
    "ai_generation": (_ai_generation_score, _IMAGE_EXTS),
    "splicing": (_splicing_score, _IMAGE_EXTS),
    "voice_clone": (_voice_clone_score, _AUDIO_EXTS),
}


def _iter_labelled(args: argparse.Namespace) -> list[tuple[str, int]]:
    items: list[tuple[str, int]] = []
    if args.labels:
        with open(args.labels, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                p, lab = row.get("path"), row.get("label")
                if p and lab in ("0", "1"):
                    items.append((p, int(lab)))
        return items
    for label, d in ((0, args.real), (1, args.fake)):
        if not d:
            continue
        for p in Path(d).rglob("*"):
            if p.is_file() and p.suffix.lower() in DETECTORS[args.detector][1]:
                items.append((str(p), label))
    return items


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--detector", required=True, choices=sorted(DETECTORS))
    ap.add_argument("--real", help="Directory of authentic samples (label 0)")
    ap.add_argument("--fake", help="Directory of manipulated/AI samples (label 1)")
    ap.add_argument("--labels", help="CSV manifest with columns: path,label")
    ap.add_argument("--out", required=True, help="Output score,label CSV path")
    args = ap.parse_args()

    if not args.labels and not (args.real or args.fake):
        print("ERROR: provide --labels OR --real/--fake", file=sys.stderr)
        return 1

    runner, _exts = DETECTORS[args.detector]
    items = _iter_labelled(args)
    if not items:
        print("ERROR: no labelled files found", file=sys.stderr)
        return 1

    rows: list[tuple[float, int]] = []
    skipped = 0
    for i, (path, label) in enumerate(items, 1):
        try:
            score = runner(path)
        except Exception as exc:  # noqa: BLE001 — per-sample robustness
            print(f"  skip {path}: {type(exc).__name__}: {exc}", file=sys.stderr)
            score = None
        if score is None or not (0.0 <= score <= 1.0):
            skipped += 1
            continue
        rows.append((score, label))
        if i % 25 == 0:
            print(f"  ...{i}/{len(items)} processed ({len(rows)} usable)")

    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["score", "label"])
        w.writerows(rows)

    pos = sum(1 for _, lab in rows if lab == 1)
    print(
        f"Wrote {len(rows)} rows to {args.out} "
        f"(pos={pos}, neg={len(rows) - pos}, skipped={skipped}). "
        f"Next: train_calibration.py then validate_calibration.py."
    )
    return 0 if len(rows) >= 10 else 2


if __name__ == "__main__":
    raise SystemExit(main())
