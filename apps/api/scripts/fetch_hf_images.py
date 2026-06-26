#!/usr/bin/env python3
"""Fetch a small, balanced, LABELLED real-vs-AI image set from a HuggingFace dataset.

Pulls row slices from the HF datasets-server (image cells come back as short-lived
signed URLs) and downloads just N-per-class — NO full dataset clone. Writes into the
layout the calibration collector expects:

    <out>/real/*.jpg   authentic images   (label 0)
    <out>/fake/*.jpg   AI-generated       (label 1)

The dataset's own ClassLabel polarity is mapped to OUR convention via --real-names
(the ClassLabel name(s) that mean "authentic"); everything else is treated as AI/fake.

Default dataset: Hemg/AI-Generated-vs-Real-Images-Datasets
  ClassLabel names = ['AiArtData', 'RealArt']  ->  --real-names RealArt
  (NOTE: this is AI-art vs real-art, a narrower domain than general photographs.)

Usage (inside the worker — it can reach huggingface.co):
    python scripts/fetch_hf_images.py --per-class 150 --out /tmp/calib/img
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

_ROWS_API = "https://datasets-server.huggingface.co/rows"


def _get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "forensic-council-calib/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed HTTPS host
        return resp.read()


def _rows(dataset: str, config: str, split: str, offset: int, length: int) -> list[dict]:
    q = urllib.parse.quote(dataset, safe="")
    url = f"{_ROWS_API}?dataset={q}&config={config}&split={split}&offset={offset}&length={length}"
    payload = json.loads(_get(url))
    return [r.get("row", {}) for r in payload.get("rows", [])]


def _img_url(cell: object) -> str | None:
    if isinstance(cell, str):
        return cell
    if isinstance(cell, dict):
        return cell.get("src") or cell.get("url")
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default="Hemg/AI-Generated-vs-Real-Images-Datasets")
    ap.add_argument("--config", default="default")
    ap.add_argument("--split", default="train")
    ap.add_argument("--real-names", default="RealArt",
                    help="comma-sep ClassLabel name(s) meaning AUTHENTIC (label 0)")
    ap.add_argument("--caption-field", default=None,
                    help="if set, derive labels from this free-text field instead of a ClassLabel")
    ap.add_argument("--real-kw", default="genuine,unaltered,original,unedited,no evidence,authentic",
                    help="caption substrings (lower) meaning AUTHENTIC")
    ap.add_argument("--fake-kw", default="fake,inserted,manipulat,altered,spliced,tamper,artificial",
                    help="caption substrings (lower) meaning FAKE")
    ap.add_argument("--per-class", type=int, default=150)
    ap.add_argument("--out", default="/tmp/calib/img")  # noqa: S108 - container-local calibration scratch path
    ap.add_argument("--start-offset", type=int, default=0,
                    help="row offset to start paging from (sorted datasets: jump to a class region)")
    ap.add_argument("--only-label", choices=["real", "fake"], default=None,
                    help="collect only this class (the other is skipped/left untouched)")
    ap.add_argument("--max-pages", type=int, default=60)
    args = ap.parse_args()

    real_names = {s.strip() for s in args.real_names.split(",")}
    real_kw = [s.strip().lower() for s in args.real_kw.split(",") if s.strip()]
    fake_kw = [s.strip().lower() for s in args.fake_kw.split(",") if s.strip()]
    real_idx: set[int] = set()
    if not args.caption_field:
        # Resolve ClassLabel int->name so we can map polarity from the label index.
        q = urllib.parse.quote(args.dataset, safe="")
        info = json.loads(_get(f"https://datasets-server.huggingface.co/rows?dataset={q}"
                               f"&config={args.config}&split={args.split}&offset=0&length=1"))
        names = None
        for feat in info.get("features", []):
            t = feat.get("type", {})
            if feat.get("name") == "label" and isinstance(t.get("names"), list):
                names = t["names"]
        if not names:
            print("ERROR: dataset has no 'label' ClassLabel; use --caption-field")
            return 1
        real_idx = {i for i, nm in enumerate(names) if nm in real_names}
        print(f"label names={names}  authentic indices={sorted(real_idx)}")
    else:
        print(f"caption mode: field={args.caption_field}  real_kw={real_kw}  fake_kw={fake_kw}")

    def _is_real(row: dict) -> bool | None:
        """Return True=authentic, False=fake, None=skip (ambiguous/missing)."""
        if args.caption_field:
            cap = str(row.get(args.caption_field, "")).lower()
            r = any(k in cap for k in real_kw)
            f = any(k in cap for k in fake_kw)
            if r == f:  # neither or both -> ambiguous
                return None
            return r
        lab = row.get("label")
        return None if lab is None else (int(lab) in real_idx)

    real_dir = Path(args.out) / "real"
    real_dir.mkdir(parents=True, exist_ok=True)
    fake_dir = Path(args.out) / "fake"
    fake_dir.mkdir(parents=True, exist_ok=True)
    n_real = n_fake = 0
    offset = args.start_offset
    page = 100
    pages = 0
    target = args.per_class
    want_real = args.only_label != "fake"
    want_fake = args.only_label != "real"

    def _done() -> bool:
        return (n_real >= target or not want_real) and (n_fake >= target or not want_fake)

    while not _done() and pages < args.max_pages:
        try:
            rows = _rows(args.dataset, args.config, args.split, offset, page)
        except Exception as exc:  # noqa: BLE001
            print(f"  rows@{offset}: {type(exc).__name__}: {exc}")
            break
        if not rows:
            break
        pages += 1
        for row in rows:
            url = _img_url(row.get("image"))
            is_real = _is_real(row)
            if url is None or is_real is None:
                continue
            if is_real and (not want_real or n_real >= target):
                continue
            if not is_real and (not want_fake or n_fake >= target):
                continue
            try:
                data = _get(url, timeout=30)
            except Exception:  # noqa: BLE001 — skip unfetchable cells
                continue
            if is_real:
                (real_dir / f"img_real_{n_real:04d}.jpg").write_bytes(data)
                n_real += 1
            else:
                (fake_dir / f"img_fake_{n_fake:04d}.jpg").write_bytes(data)
                n_fake += 1
        offset += page
        print(f"  real={n_real} fake={n_fake} (offset={offset})")

    print(f"Wrote {n_real} real + {n_fake} fake images to {args.out}")
    got = (n_real if want_real else 1_000_000), (n_fake if want_fake else 1_000_000)
    return 0 if min(got) >= 10 else 2


if __name__ == "__main__":
    raise SystemExit(main())
