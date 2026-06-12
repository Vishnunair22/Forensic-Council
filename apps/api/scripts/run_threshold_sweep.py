#!/usr/bin/env python3
"""
Generic per-detector threshold sweep (calibration Phase 1b; see docs/CALIBRATION_RUNBOOK.md).

Takes a collector CSV (``score,label`` — the exact format emitted by
``scripts/collect_calibration_scores.py``) and sweeps the decision threshold
across the observed score range, reporting:

  • a (threshold, TPR, FPR) operating table,
  • AUC (rank-based Mann-Whitney, tie-aware),
  • suggested operating thresholds at FPR <= 0.05 (alert signals) and
    FPR <= 0.01 ("strong" signals), per the plan's recommended operating points.

The result is saved as JSON next to the CSV (``<csv stem>_sweep.json`` by
default) so the measured (threshold, TPR, FPR) can be recorded in the
capability manifest / report disclosures. This harness is detector-agnostic:
run it on any agent's collector output (Agents 1-5) after scoring a labelled
benchmark.

Usage:
    python scripts/run_threshold_sweep.py --csv /tmp/agent1_ai_scores.csv
    python scripts/run_threshold_sweep.py --csv calibration_data/agent5_hc3.csv \
        --detector ai_text --out calibration_data/agent5_hc3_sweep.json

Exit codes: 0 success, 1 argument/data error.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np


def load_scores(csv_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Load a score,label CSV (same parsing rules as validate_calibration.py)."""
    scores: list[float] = []
    labels: list[int] = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                s, lab = float(row["score"]), int(row["label"])
            except (KeyError, ValueError, TypeError):
                continue
            if 0.0 <= s <= 1.0 and lab in (0, 1):
                scores.append(s)
                labels.append(lab)
    return np.asarray(scores, dtype=float), np.asarray(labels, dtype=int)


def auc_mann_whitney(scores: np.ndarray, labels: np.ndarray) -> float:
    """Rank-based AUC (equals ROC AUC), with average ranks for ties."""
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(len(scores), dtype=float)
    sorted_scores = scores[order]
    i = 0
    while i < len(sorted_scores):
        j = i
        while j + 1 < len(sorted_scores) and sorted_scores[j + 1] == sorted_scores[i]:
            j += 1
        # average rank for the tie block (1-based ranks)
        ranks[order[i : j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    n_pos = int(labels.sum())
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    rank_sum_pos = float(ranks[labels == 1].sum())
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def sweep(scores: np.ndarray, labels: np.ndarray, max_points: int) -> list[dict]:
    """Compute (threshold, TPR, FPR) at every distinct operating point."""
    thresholds = np.unique(scores)
    # Add an above-max threshold so the (TPR=0, FPR=0) corner is represented.
    thresholds = np.concatenate([thresholds, [thresholds[-1] + 1e-9]])
    if len(thresholds) > max_points:
        idx = np.linspace(0, len(thresholds) - 1, max_points).round().astype(int)
        thresholds = thresholds[np.unique(idx)]

    pos = labels == 1
    neg = labels == 0
    n_pos = int(pos.sum())
    n_neg = int(neg.sum())
    table = []
    for thr in thresholds:
        pred = scores >= thr
        tpr = float(pred[pos].sum() / n_pos) if n_pos else 0.0
        fpr = float(pred[neg].sum() / n_neg) if n_neg else 0.0
        table.append({"threshold": round(float(thr), 6), "tpr": round(tpr, 4), "fpr": round(fpr, 4)})
    return table


def suggest_threshold(table: list[dict], fpr_target: float) -> dict:
    """Highest-TPR operating point whose FPR does not exceed the target."""
    feasible = [row for row in table if row["fpr"] <= fpr_target + 1e-12]
    if not feasible:
        return {
            "fpr_target": fpr_target,
            "threshold": None,
            "tpr": None,
            "fpr": None,
            "note": "no threshold meets this FPR target on this dataset",
        }
    best = max(feasible, key=lambda r: (r["tpr"], -r["threshold"]))
    return {
        "fpr_target": fpr_target,
        "threshold": best["threshold"],
        "tpr": best["tpr"],
        "fpr": best["fpr"],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", required=True, help="score,label CSV from the collector")
    ap.add_argument("--detector", default=None, help="optional detector name recorded in the JSON")
    ap.add_argument("--out", default=None, help="output JSON path (default: <csv stem>_sweep.json)")
    ap.add_argument(
        "--max-points", type=int, default=512,
        help="cap on operating points kept in the table (default 512)",
    )
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"ERROR: CSV not found: {csv_path}", file=sys.stderr)
        return 1

    scores, labels = load_scores(csv_path)
    n_pos = int(labels.sum()) if len(labels) else 0
    n_neg = len(labels) - n_pos
    if len(scores) < 10 or n_pos == 0 or n_neg == 0:
        print(
            f"ERROR: need >=10 rows with both classes (got n={len(scores)} "
            f"pos={n_pos} neg={n_neg}).",
            file=sys.stderr,
        )
        return 1

    auc = auc_mann_whitney(scores, labels)
    table = sweep(scores, labels, args.max_points)
    suggestions = [suggest_threshold(table, t) for t in (0.05, 0.01)]

    result = {
        "source_csv": str(csv_path),
        "detector": args.detector,
        "generated_utc": datetime.now(UTC).isoformat(),
        "n_samples": int(len(scores)),
        "n_positive": n_pos,
        "n_negative": n_neg,
        "auc": round(float(auc), 4),
        "suggested_thresholds": suggestions,
        "roc_table": table,
        "note": (
            "TPR/FPR measured on the supplied labelled benchmark at each score "
            "threshold (prediction = score >= threshold). Record the chosen "
            "operating point in the capability manifest so reports disclose "
            "per-tool error rates (calibration Phase 1b)."
        ),
    }

    out_path = Path(args.out) if args.out else csv_path.with_name(csv_path.stem + "_sweep.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Samples: {len(scores)} (pos={n_pos}, neg={n_neg})")
    print(f"AUC: {auc:.4f}")
    for s in suggestions:
        if s["threshold"] is None:
            print(f"  FPR<={s['fpr_target']}: no feasible threshold")
        else:
            print(
                f"  FPR<={s['fpr_target']}: threshold={s['threshold']:.4f} "
                f"-> TPR={s['tpr']:.3f} FPR={s['fpr']:.3f}"
            )
    print(f"Sweep JSON written to: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
