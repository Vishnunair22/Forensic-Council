#!/usr/bin/env python3
"""
Calibration validation + adoption gate.

Calibration must NEVER be adopted blind — a model fit on too-small or
distribution-mismatched data can be WORSE than the conservative engineering
defaults. This script fits Platt scaling on a TRAIN split and compares it against
the current engineering default on a HELD-OUT TEST split, then prints a verdict:

    ADOPT      — trained model beats the default on BOTH ECE and Brier and does
                 NOT increase the false-positive rate (at the 0.5 decision point).
    KEEP_DEFAULT — otherwise; the conservative default stays.

It does not write anything; run train_calibration.py to persist a model only if
this gate returns ADOPT.

Usage:
    python scripts/validate_calibration.py \
        --dataset /tmp/agent1_ai_scores.csv --agent agent1_image [--test-frac 0.3]
"""

from __future__ import annotations

import argparse
import csv

import numpy as np


def _sigmoid(a: float, b: float, x: np.ndarray) -> np.ndarray:
    z = np.clip(a * x + b, -500, 500)
    return 1.0 / (1.0 + np.exp(z))


def _metrics(p: np.ndarray, y: np.ndarray) -> dict[str, float]:
    from scripts.train_calibration import expected_calibration_error

    brier = float(np.mean((p - y) ** 2))
    ece = float(expected_calibration_error(p, y))
    pred = (p >= 0.5).astype(int)
    # FPR at the 0.5 decision point — guards against the calibration making the
    # system flag authentic evidence more often.
    neg = y == 0
    fpr = float(np.mean(pred[neg] == 1)) if neg.any() else 0.0
    acc = float(np.mean(pred == y))
    return {"ece": ece, "brier": brier, "fpr": fpr, "acc": acc}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", required=True, help="score,label CSV")
    ap.add_argument("--agent", required=True, help="e.g. agent1_image")
    ap.add_argument("--test-frac", type=float, default=0.3)
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()

    scores, labels = [], []
    with open(args.dataset, newline="") as f:
        for row in csv.DictReader(f):
            try:
                s, lab = float(row["score"]), int(row["label"])
            except (KeyError, ValueError, TypeError):
                continue
            if 0.0 <= s <= 1.0 and lab in (0, 1):
                scores.append(s)
                labels.append(lab)
    x = np.asarray(scores, dtype=float)
    y = np.asarray(labels, dtype=int)
    if len(x) < 20 or y.sum() < 5 or (len(y) - y.sum()) < 5:
        print(
            f"INSUFFICIENT DATA: n={len(x)} pos={int(y.sum())} neg={int(len(y) - y.sum())}. "
            "Need >=20 samples with >=5 of each class for a trustworthy split. KEEP_DEFAULT.",
        )
        return 2

    rng = np.random.default_rng(args.seed)
    idx = rng.permutation(len(x))
    n_test = max(int(len(x) * args.test_frac), 6)
    te, tr = idx[:n_test], idx[n_test:]

    from core.calibration import CalibrationManager
    from scripts.train_calibration import fit_platt

    a_t, b_t = fit_platt(x[tr], y[tr])
    default = CalibrationManager().fit_default_model(args.agent)
    a_d = float(default.params["A"])
    b_d = float(default.params["B"])

    m_trained = _metrics(_sigmoid(a_t, b_t, x[te]), y[te])
    m_default = _metrics(_sigmoid(a_d, b_d, x[te]), y[te])

    print(f"Agent: {args.agent}  |  train={len(tr)} test={len(te)}")
    print(f"  trained  A={a_t:+.3f} B={b_t:+.3f}  ECE={m_trained['ece']:.4f} "
          f"Brier={m_trained['brier']:.4f} FPR={m_trained['fpr']:.3f} acc={m_trained['acc']:.3f}")
    print(f"  default  A={a_d:+.3f} B={b_d:+.3f}  ECE={m_default['ece']:.4f} "
          f"Brier={m_default['brier']:.4f} FPR={m_default['fpr']:.3f} acc={m_default['acc']:.3f}")

    beats_ece = m_trained["ece"] < m_default["ece"]
    beats_brier = m_trained["brier"] < m_default["brier"]
    no_worse_fpr = m_trained["fpr"] <= m_default["fpr"] + 1e-6
    adopt = beats_ece and beats_brier and no_worse_fpr

    if adopt:
        print(
            f"\nVERDICT: ADOPT — trained calibration improves ECE+Brier without raising FPR.\n"
            f"  Persist with: python scripts/train_calibration.py --dataset {args.dataset} "
            f"--agent {args.agent} --output-dir storage/calibration_models"
        )
        return 0
    print(
        "\nVERDICT: KEEP_DEFAULT — trained model does not strictly beat the conservative "
        "default (ECE/Brier/FPR). Do NOT adopt; gather more/closer-matched data."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
