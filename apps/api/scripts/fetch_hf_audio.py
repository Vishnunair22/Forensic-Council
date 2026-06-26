#!/usr/bin/env python3
"""Fetch a small, balanced, LABELLED bonafide-vs-spoof audio set from a HuggingFace dataset.

Pulls row slices from the HF datasets-server (audio cells come back as short-lived
signed URLs) and downloads just N-per-class — NO full dataset clone. Writes into the
layout the calibration collector expects:

    <out>/real/*.wav   bonafide / authentic speech   (label 0)
    <out>/fake/*.wav   spoofed / synthetic / VC       (label 1)

Labels are read from a STRING field (default 'label'); a row is FAKE if any
--fake-kw substring is present (e.g. 'spoof'), else REAL.

Default dataset: DynamicSuperb/SpoofDetection_ASVspoof2015  (TTS/VC synthesis vs bonafide)

Usage (inside the worker — it can reach huggingface.co):
    python scripts/fetch_hf_audio.py --split test --per-class 90 --out /tmp/calib/audio
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

_ROWS_API = "https://datasets-server.huggingface.co/rows"


def _get(url: str, timeout: int = 45) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "forensic-council-calib/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed HTTPS host
        return resp.read()


def _rows(dataset: str, config: str, split: str, offset: int, length: int) -> list[dict]:
    q = urllib.parse.quote(dataset, safe="")
    url = f"{_ROWS_API}?dataset={q}&config={config}&split={split}&offset={offset}&length={length}"
    return [r.get("row", {}) for r in json.loads(_get(url)).get("rows", [])]


def _audio_url(cell: object) -> str | None:
    # Audio cells are usually a list of {src,type}; sometimes a bare dict.
    if isinstance(cell, list) and cell:
        cell = cell[0]
    if isinstance(cell, dict):
        return cell.get("src") or cell.get("url")
    if isinstance(cell, str):
        return cell
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default="DynamicSuperb/SpoofDetection_ASVspoof2015")
    ap.add_argument("--config", default="default")
    ap.add_argument("--split", default="test")
    ap.add_argument("--label-field", default="label")
    ap.add_argument("--audio-field", default="audio")
    ap.add_argument("--fake-kw", default="spoof,fake,synthetic,convert,clone,artificial",
                    help="substrings (lower) in the label field meaning FAKE/spoof")
    ap.add_argument("--per-class", type=int, default=90)
    ap.add_argument("--out", default="/tmp/calib/audio")  # noqa: S108 - container-local calibration scratch path
    ap.add_argument("--start-offset", type=int, default=0)
    ap.add_argument("--max-pages", type=int, default=80)
    args = ap.parse_args()

    fake_kw = [s.strip().lower() for s in args.fake_kw.split(",") if s.strip()]
    real_dir = Path(args.out) / "real"
    real_dir.mkdir(parents=True, exist_ok=True)
    fake_dir = Path(args.out) / "fake"
    fake_dir.mkdir(parents=True, exist_ok=True)
    n_real = n_fake = 0
    offset = args.start_offset
    page = 100
    pages = 0
    target = args.per_class

    while (n_real < target or n_fake < target) and pages < args.max_pages:
        try:
            rows = _rows(args.dataset, args.config, args.split, offset, page)
        except Exception as exc:  # noqa: BLE001
            print(f"  rows@{offset}: {type(exc).__name__}: {exc}")
            break
        if not rows:
            break
        pages += 1
        for row in rows:
            lab = str(row.get(args.label_field, "")).lower()
            if not lab:
                continue
            is_fake = any(k in lab for k in fake_kw)
            url = _audio_url(row.get(args.audio_field))
            if url is None:
                continue
            if is_fake and n_fake >= target:
                continue
            if not is_fake and n_real >= target:
                continue
            try:
                data = _get(url, timeout=45)
            except Exception:  # noqa: BLE001 — skip unfetchable cells
                continue
            if is_fake:
                (fake_dir / f"aud_fake_{n_fake:04d}.wav").write_bytes(data)
                n_fake += 1
            else:
                (real_dir / f"aud_real_{n_real:04d}.wav").write_bytes(data)
                n_real += 1
        offset += page
        print(f"  real={n_real} fake={n_fake} (offset={offset})")

    print(f"Wrote {n_real} real + {n_fake} fake audio files to {args.out}")
    return 0 if min(n_real, n_fake) >= 10 else 2


if __name__ == "__main__":
    raise SystemExit(main())
