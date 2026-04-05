"""
Train Platt Scaling Calibration Parameters
==========================================

Fits per-agent Platt scaling parameters (A, B) on a labelled forensic dataset
and saves the resulting calibrated model to the calibration models directory.

Usage:
    python -m scripts.train_calibration \
        --dataset /path/to/labels.csv \
        --agent agent1_image \
        --output-dir ./calibration_models

CSV format:
    score,label
    0.85,1
    0.32,0
    ...

The script:
1. Loads raw detector scores + ground-truth labels
2. Fits Platt scaling via logistic regression on the logit transform
3. Evaluates calibration quality (ECE, reliability diagram)
4. Saves the trained model with TRAINED status and validation metrics

Exit codes:
    0  — success, model saved
    1  — argument error or missing data
    2  — training failed (e.g. degenerate data)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np


# ---------------------------------------------------------------------------
# Platt scaling fit (MLE on sigmoid)
# ---------------------------------------------------------------------------


def _sigmoid(a: float, b: float, x: float) -> float:
    """Platt sigmoid: 1 / (1 + exp(A*x + B))"""
    return 1.0 / (1.0 + math.exp(a * x + b))


def fit_platt(
    scores: np.ndarray,
    labels: np.ndarray,
    max_iter: int = 200,
    lr: float = 0.01,
) -> tuple[float, float]:
    """
    Fit Platt scaling parameters A, B via gradient descent on negative
    log-likelihood of Bernoulli(labels | sigmoid(A*score + B)).

    Args:
        scores: Raw detector scores, shape (N,), in [0, 1]
        labels: Ground-truth binary labels, shape (N,), {0, 1}
        max_iter: Maximum gradient descent iterations
        lr: Learning rate

    Returns:
        (A, B) tuple of fitted Platt parameters
    """
    a, b = 1.0, 0.0  # initialisation

    for _ in range(max_iter):
        # Forward pass
        z = a * scores + b
        z = np.clip(z, -500, 500)  # prevent overflow
        p = 1.0 / (1.0 + np.exp(z))

        # Gradients of negative log-likelihood
        error = p - labels  # (N,)
        grad_a = np.mean(error * scores)
        grad_b = np.mean(error)

        # Update
        a -= lr * grad_a
        b -= lr * grad_b

    return float(a), float(b)


# ---------------------------------------------------------------------------
# Calibration quality metrics
# ---------------------------------------------------------------------------


def expected_calibration_error(
    scores: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
) -> float:
    """
    Compute Expected Calibration Error (ECE).

    ECE = sum over bins of |bin_accuracy - bin_confidence| * bin_weight

    Lower is better.  ECE < 0.05 is considered well-calibrated.
    """
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(scores)

    for i in range(n_bins):
        mask = (scores >= bin_edges[i]) & (scores < bin_edges[i + 1])
        if i == n_bins - 1:  # include right edge in last bin
            mask = (scores >= bin_edges[i]) & (scores <= bin_edges[i + 1])

        count = mask.sum()
        if count == 0:
            continue

        bin_accuracy = labels[mask].mean()
        bin_confidence = scores[mask].mean()
        ece += (count / n) * abs(bin_accuracy - bin_confidence)

    return float(ece)


def reliability_data(
    scores: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
) -> list[dict]:
    """Return per-bin reliability data for plotting."""
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins = []

    for i in range(n_bins):
        mask = (scores >= bin_edges[i]) & (scores < bin_edges[i + 1])
        if i == n_bins - 1:
            mask = (scores >= bin_edges[i]) & (scores <= bin_edges[i + 1])

        count = mask.sum()
        if count == 0:
            bins.append(
                {
                    "bin_low": float(bin_edges[i]),
                    "bin_high": float(bin_edges[i + 1]),
                    "count": 0,
                    "mean_confidence": None,
                    "mean_accuracy": None,
                }
            )
        else:
            bins.append(
                {
                    "bin_low": float(bin_edges[i]),
                    "bin_high": float(bin_edges[i + 1]),
                    "count": int(count),
                    "mean_confidence": float(scores[mask].mean()),
                    "mean_accuracy": float(labels[mask].mean()),
                }
            )

    return bins


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Train Platt scaling calibration for a forensic agent."
    )
    parser.add_argument(
        "--dataset",
        required=True,
        help="Path to CSV with columns: score, label (0 or 1)",
    )
    parser.add_argument(
        "--agent",
        required=True,
        help="Agent ID, e.g. agent1_image",
    )
    parser.add_argument(
        "--output-dir",
        default="./calibration_models",
        help="Directory to write trained model JSON (default: ./calibration_models)",
    )
    parser.add_argument(
        "--method",
        default="platt",
        choices=["platt"],
        help="Calibration method (default: platt)",
    )
    args = parser.parse_args()

    # --- Load data -----------------------------------------------------------
    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"ERROR: Dataset not found: {dataset_path}", file=sys.stderr)
        return 1

    scores_list: list[float] = []
    labels_list: list[int] = []

    with open(dataset_path, newline="") as f:
        reader = csv.DictReader(f)
        if "score" not in reader.fieldnames or "label" not in reader.fieldnames:
            print("ERROR: CSV must have 'score' and 'label' columns.", file=sys.stderr)
            return 1

        for row in reader:
            try:
                s = float(row["score"])
                label = int(row["label"])
                if not (0.0 <= s <= 1.0):
                    continue
                if label not in (0, 1):
                    continue
                scores_list.append(s)
                labels_list.append(label)
            except (ValueError, KeyError):
                continue

    if len(scores_list) < 10:
        print(
            f"ERROR: Need at least 10 valid rows, got {len(scores_list)}.",
            file=sys.stderr,
        )
        return 1

    scores = np.array(scores_list, dtype=np.float64)
    labels = np.array(labels_list, dtype=np.float64)

    n_pos = int(labels.sum())
    n_neg = len(labels) - n_pos
    print(f"Loaded {len(scores)} samples ({n_pos} positive, {n_neg} negative)")

    if n_pos == 0 or n_neg == 0:
        print(
            "ERROR: Dataset must contain both positive and negative labels.",
            file=sys.stderr,
        )
        return 2

    # --- Fit Platt scaling ----------------------------------------------------
    print("Fitting Platt scaling parameters...")
    try:
        A, B = fit_platt(scores, labels)
    except Exception as e:
        print(f"ERROR: Platt fitting failed: {e}", file=sys.stderr)
        return 2

    print(f"  A = {A:.6f}")
    print(f"  B = {B:.6f}")

    # --- Evaluate calibration quality -----------------------------------------
    calibrated_scores = np.array([_sigmoid(A, B, float(s)) for s in scores])

    ece_before = expected_calibration_error(scores, labels)
    ece_after = expected_calibration_error(calibrated_scores, labels)

    print(f"  ECE before calibration: {ece_before:.4f}")
    print(f"  ECE after calibration:  {ece_after:.4f}")

    reliability = reliability_data(calibrated_scores, labels)

    # --- Compute TPR / FPR at median threshold --------------------------------
    median_threshold = float(np.median(calibrated_scores))
    tp = float(((calibrated_scores >= median_threshold) & (labels == 1)).sum())
    fp = float(((calibrated_scores >= median_threshold) & (labels == 0)).sum())
    fn = float(((calibrated_scores < median_threshold) & (labels == 1)).sum())
    tn = float(((calibrated_scores < median_threshold) & (labels == 0)).sum())

    tpr = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    print(f"  TPR at median threshold ({median_threshold:.3f}): {tpr:.3f}")
    print(f"  FPR at median threshold ({median_threshold:.3f}): {fpr:.3f}")

    # --- Build model ----------------------------------------------------------
    version = f"v1.0_trained_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    model = {
        "model_id": str(uuid4()),
        "agent_id": args.agent,
        "method": "PLATT_SCALING",
        "benchmark_dataset": str(dataset_path.name),
        "version": version,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "params": {
            "method": "platt",
            "A": round(A, 6),
            "B": round(B, 6),
            "baseline_tpr": round(tpr, 4),
            "baseline_fpr": round(fpr, 4),
        },
        "calibration_status": "TRAINED",
        "validation_metrics": {
            "ece_before": round(ece_before, 6),
            "ece_after": round(ece_after, 6),
            "n_samples": len(scores),
            "n_positive": n_pos,
            "n_negative": n_neg,
            "median_threshold": round(median_threshold, 6),
            "tpr_at_median": round(tpr, 4),
            "fpr_at_median": round(fpr, 4),
            "reliability_bins": reliability,
        },
    }

    # --- Save -----------------------------------------------------------------
    output_dir = Path(args.output_dir) / args.agent
    output_dir.mkdir(parents=True, exist_ok=True)

    model_path = output_dir / f"{version}.json"
    with open(model_path, "w") as f:
        json.dump(model, f, indent=2)

    latest_path = output_dir / "latest.json"
    with open(latest_path, "w") as f:
        json.dump(model, f, indent=2)

    print(f"\nModel saved to: {model_path}")
    print(f"Latest symlink: {latest_path}")
    print(f"\nTo use: set calibration_models_path={args.output_dir} in settings,")
    print(
        f"or copy {model_path} to your deployment's calibration_models/{args.agent}/ directory."
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
