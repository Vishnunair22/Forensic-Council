#!/usr/bin/env python3
"""Fetch a small, balanced, LABELLED human-vs-ChatGPT text set from HC3.

Pulls JSON row slices from the HuggingFace datasets-server (NO full dataset
download — a few MB total) and writes plain ``.txt`` files in the layout the
calibration collector expects:

    <out>/real/*.txt   human-written answers   (label 0)
    <out>/fake/*.txt   ChatGPT answers         (label 1)

Source: Hello-SimpleAI/HC3 (human/ChatGPT answer pairs across 6 domains).
This is the lightweight, network-frugal way to obtain Agent 5 (AI-text)
ground truth when full benchmark downloads are infeasible. Calibration still
goes through collect -> validate (gate) -> train; nothing is adopted here.

Usage (inside the worker container — it can reach huggingface.co):
    python scripts/fetch_hc3_text.py --per-class 400 --out /tmp/calib/text
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

_ROWS_API = "https://datasets-server.huggingface.co/rows"
_DATASET = "Hello-SimpleAI/HC3"
# Domains pulled in round-robin so the calibration set isn't single-topic.
_CONFIGS = ("reddit_eli5", "open_qa", "wiki_csai", "medicine", "finance", "all")
_WORD = re.compile(r"[A-Za-z']+")
_MIN_WORDS = 45  # margin above the detector's 40-word floor


def _fetch_rows(config: str, offset: int, length: int) -> list[dict]:
    url = f"{_ROWS_API}?dataset={_DATASET}&config={config}&split=train&offset={offset}&length={length}"
    req = urllib.request.Request(url, headers={"User-Agent": "forensic-council-calib/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 — fixed HTTPS host
        payload = json.load(resp)
    return [r.get("row", {}) for r in payload.get("rows", [])]


def _clean(text: str) -> str | None:
    text = (text or "").strip()
    if len(_WORD.findall(text)) < _MIN_WORDS:
        return None
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--per-class", type=int, default=400, help="target samples per class")
    ap.add_argument("--out", default="/tmp/calib/text", help="output dir (gets real/ and fake/)")  # noqa: S108 - container-local calibration scratch path
    args = ap.parse_args()

    real_dir = Path(args.out) / "real"
    fake_dir = Path(args.out) / "fake"
    real_dir.mkdir(parents=True, exist_ok=True)
    fake_dir.mkdir(parents=True, exist_ok=True)

    human: list[str] = []
    chatgpt: list[str] = []
    seen_h: set[str] = set()
    seen_c: set[str] = set()

    target = args.per_class
    # Round-robin across domains, paginating, until both classes hit target.
    offset = 0
    page = 100
    stale_passes = 0
    while (len(human) < target or len(chatgpt) < target) and stale_passes < 3:
        progressed = False
        for cfg in _CONFIGS:
            if len(human) >= target and len(chatgpt) >= target:
                break
            try:
                rows = _fetch_rows(cfg, offset, page)
            except Exception as exc:  # noqa: BLE001 — per-config robustness
                print(f"  {cfg}@{offset}: {type(exc).__name__}: {exc}")
                continue
            for row in rows:
                for ans in (row.get("human_answers") or []):
                    c = _clean(ans)
                    if c and c[:120] not in seen_h and len(human) < target:
                        seen_h.add(c[:120])
                        human.append(c)
                        progressed = True
                for ans in (row.get("chatgpt_answers") or []):
                    c = _clean(ans)
                    if c and c[:120] not in seen_c and len(chatgpt) < target:
                        seen_c.add(c[:120])
                        chatgpt.append(c)
                        progressed = True
        offset += page
        stale_passes = 0 if progressed else stale_passes + 1
        print(f"  collected human={len(human)} chatgpt={len(chatgpt)} (offset={offset})")

    # Balance to the smaller class so the gate sees an even split.
    n = min(len(human), len(chatgpt))
    for i in range(n):
        (real_dir / f"hc3_human_{i:04d}.txt").write_text(human[i], encoding="utf-8")
        (fake_dir / f"hc3_chatgpt_{i:04d}.txt").write_text(chatgpt[i], encoding="utf-8")

    print(f"Wrote {n} real + {n} fake .txt files to {args.out}")
    print(f"Next: collect_calibration_scores.py --detector ai_text --real {real_dir} --fake {fake_dir} --out /tmp/agent5_hc3.csv")
    return 0 if n >= 20 else 2


if __name__ == "__main__":
    raise SystemExit(main())
