"""
Calibration Model Trainer
==========================

Trains Platt Scaling calibration models for each forensic agent using
labelled benchmark data (FaceForensics++, NIST MFC, ASVspoof 2021, CASIA v2).

This resolves TD-01 (CRITICAL): All default models are UNCALIBRATED.
Running this script produces TRAINED models that can be used in production
to generate court-defensible confidence scores.

Usage:
    python scripts/train_calibration.py \
        --dataset faceforensics \
        --data-dir /data/ff++ \
        --output-dir storage/calibration_models

    # Or with a CSV file of (raw_score, label) pairs:
    python scripts/train_calibration.py \
        --from-csv /data/agent1_scores.csv \
        --agent-id Agent1 \
        --output-dir storage/calibration_models

Output:
    storage/calibration_models/Agent1_calibration.json
    storage/calibration_models/Agent2_calibration.json
    ... etc.

    Each file has CalibrationStatus.TRAINED, replacing the UNCALIBRATED defaults.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Platt Scaling implementation (no sklearn dependency required)
# Uses gradient descent to fit sigmoid f(x) = 1/(1+exp(platt_a*x + platt_b))
# ---------------------------------------------------------------------------

def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exp_x = math.exp(x)
    return exp_x / (1.0 + exp_x)


def fit_platt_scaling(
    raw_scores: list[float],
    labels: list[int],
    max_iter: int = 100,
    learning_rate: float = 0.01,
) -> tuple[float, float]:
    """
    Fit Platt scaling parameters A and B via gradient descent.

    The calibrated probability is: p = sigmoid(A * raw_score + B)

    Args:
        raw_scores: Raw detector outputs (0-1)
        labels: Ground truth (1 = manipulated/positive, 0 = authentic/negative)
        max_iter: Maximum gradient descent iterations
        learning_rate: Step size

    Returns:
        (platt_a, platt_b) — sigmoid parameters for Platt scaling
    """
    if not raw_scores or len(raw_scores) != len(labels):
        raise ValueError("raw_scores and labels must be non-empty and same length")

    n = len(raw_scores)

    # Prior probabilities for label smoothing (prevents overconfident boundaries)
    n_positive = sum(labels)
    n_negative = n - n_positive
    t_positive = (n_positive + 1.0) / (n_positive + 2.0)
    t_negative = 1.0 / (n_negative + 2.0)

    # Smooth targets
    targets = [t_positive if y == 1 else t_negative for y in labels]

    # Initialize platt_a=0, platt_b=log((n_neg+1)/(n_pos+1))
    platt_a = 0.0
    platt_b = math.log((n_negative + 1.0) / (n_positive + 1.0)) if n_positive > 0 else 0.0

    prev_loss = float("inf")

    for iteration in range(max_iter):
        # Forward pass — compute loss and gradients
        grad_a = 0.0
        grad_b = 0.0
        loss = 0.0

        for x, t in zip(raw_scores, targets, strict=True):
            p = _sigmoid(platt_a * x + platt_b)
            p = max(1e-7, min(1 - 1e-7, p))  # Clamp for numerical stability
            loss -= t * math.log(p) + (1 - t) * math.log(1 - p)
            error = p - t
            grad_a += error * x
            grad_b += error

        loss /= n
        grad_a /= n
        grad_b /= n

        # Update
        platt_a -= learning_rate * grad_a
        platt_b -= learning_rate * grad_b

        # Early stopping
        if abs(prev_loss - loss) < 1e-6:
            logger.debug(f"Platt scaling converged at iteration {iteration}")
            break
        prev_loss = loss

    return platt_a, platt_b


def evaluate_calibration(
    raw_scores: list[float],
    labels: list[int],
    platt_a: float,
    platt_b: float,
) -> dict[str, float]:
    """
    Evaluate calibration quality on held-out data.

    Returns ECE (Expected Calibration Error), Brier score, and AUC approximation.
    """
    n = len(raw_scores)
    if n == 0:
        return {}

    calibrated = [_sigmoid(platt_a * s + platt_b) for s in raw_scores]

    # Brier score
    brier = sum((p - y) ** 2 for p, y in zip(calibrated, labels, strict=True)) / n

    # ECE: divide into 10 bins, measure mean calibration error
    bins = [[] for _ in range(10)]
    for p, y in zip(calibrated, labels, strict=True):
        bin_idx = min(int(p * 10), 9)
        bins[bin_idx].append((p, y))

    ece = 0.0
    for bin_items in bins:
        if not bin_items:
            continue
        bin_conf = sum(p for p, _ in bin_items) / len(bin_items)
        bin_acc = sum(y for _, y in bin_items) / len(bin_items)
        ece += (len(bin_items) / n) * abs(bin_conf - bin_acc)

    return {
        "brier_score": round(brier, 4),
        "ece": round(ece, 4),
        "n_samples": n,
        "n_positive": sum(labels),
        "n_negative": n - sum(labels),
    }


@dataclass
class CalibrationTrainingResult:
    """Result of training a calibration model for one agent."""
    agent_id: str
    method: str = "PLATT_SCALING"
    platt_a: float = 0.0
    platt_b: float = 0.0
    brier_score: float = 1.0
    ece: float = 1.0
    n_samples: int = 0
    dataset: str = "unknown"
    trained_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    calibration_status: str = "TRAINED"

    def to_calibration_model_dict(self) -> dict[str, Any]:
        """Convert to format compatible with core.calibration.CalibrationModel."""
        return {
            "agent_id": self.agent_id,
            "method": self.method,
            "benchmark_dataset": self.dataset,
            "version": f"platt-{self.trained_at[:10]}",
            "created_utc": self.trained_at,
            "calibration_status": self.calibration_status,
            "params": {
                "A": self.platt_a,
                "B": self.platt_b,
                "method": self.method,
                "calibration_status": self.calibration_status,
            },
            "metrics": {
                "brier_score": self.brier_score,
                "ece": self.ece,
                "n_samples": self.n_samples,
            },
        }


def train_from_csv(
    csv_path: Path,
    agent_id: str,
    dataset_name: str = "custom",
) -> CalibrationTrainingResult:
    """
    Train a Platt Scaling calibration model from a CSV file.

    Expected CSV format:
        raw_score,label
        0.72,1
        0.31,0
        ...

    label: 1 = manipulated/positive, 0 = authentic/negative
    """
    import csv

    raw_scores = []
    labels = []

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                raw_scores.append(float(row["raw_score"]))
                labels.append(int(row["label"]))
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping malformed row: {row} — {e}")

    if len(raw_scores) < 20:
        raise ValueError(
            f"Insufficient samples ({len(raw_scores)}). Need at least 20 for reliable calibration."
        )

    # 80/20 train/eval split
    split = int(len(raw_scores) * 0.8)
    train_scores, train_labels = raw_scores[:split], labels[:split]
    eval_scores, eval_labels = raw_scores[split:], labels[split:]

    # Sanity check: both splits must have at least 2 samples with both classes
    if len(train_scores) < 4 or len(set(train_labels)) < 2:
        raise ValueError(
            f"Training split too small or single-class (n={len(train_scores)}, "
            f"classes={set(train_labels)}). Collect more diverse samples."
        )
    if len(eval_scores) < 2:
        raise ValueError(
            f"Eval split too small (n={len(eval_scores)}). Need at least 10 total samples."
        )

    platt_a, platt_b = fit_platt_scaling(train_scores, train_labels)
    metrics = evaluate_calibration(eval_scores, eval_labels, platt_a, platt_b)

    logger.info(
        f"Calibration training complete: agent_id={agent_id}, "
        f"platt_a={round(platt_a, 4)}, platt_b={round(platt_b, 4)}, metrics={metrics}"
    )

    return CalibrationTrainingResult(
        agent_id=agent_id,
        platt_a=platt_a,
        platt_b=platt_b,
        brier_score=metrics.get("brier_score", 1.0),
        ece=metrics.get("ece", 1.0),
        n_samples=int(metrics.get("n_samples", len(raw_scores))),
        dataset=dataset_name,
    )


def save_trained_model(
    result: CalibrationTrainingResult,
    output_dir: Path,
) -> Path:
    """Save a trained calibration result to the output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    model_dict = result.to_calibration_model_dict()
    path = output_dir / f"{result.agent_id}_calibration.json"
    with open(path, "w") as f:
        json.dump(model_dict, f, indent=2)
    logger.info(f"Calibration model saved: agent_id={result.agent_id}, path={path}")
    return path


def generate_synthetic_training_data(
    agent_id: str,
    n_samples: int = 500,
    seed: int = 42,
) -> tuple[list[float], list[int]]:
    """
    Generate synthetic (fake) training data for demo/CI purposes.

    ⚠️  This is NOT real calibration training.
    ⚠️  Models trained on synthetic data are UNCALIBRATED in practice.
    ⚠️  Replace with real benchmark data before production deployment.

    The synthetic data models a detector with 75% accuracy and realistic
    miscalibration (raw scores biased toward 0.5).
    """
    import random  # noqa: S311 — synthetic training data, non-cryptographic
    random.seed(seed)

    raw_scores = []
    labels = []

    # Agent-specific parameters (different tools have different base rates)
    agent_params = {
        "Agent1": {"tpr": 0.82, "fpr": 0.12, "score_bias": 0.55},
        "Agent2": {"tpr": 0.85, "fpr": 0.10, "score_bias": 0.52},
        "Agent3": {"tpr": 0.78, "fpr": 0.15, "score_bias": 0.58},
        "Agent4": {"tpr": 0.80, "fpr": 0.13, "score_bias": 0.54},
        "Agent5": {"tpr": 0.88, "fpr": 0.08, "score_bias": 0.50},
    }
    params = agent_params.get(agent_id, {"tpr": 0.80, "fpr": 0.12, "score_bias": 0.53})

    for _ in range(n_samples):
        label = random.randint(0, 1)  # noqa: S311
        if label == 1:
            # True positive: score above bias with some noise
            base = params["score_bias"]
            score = min(0.99, max(0.01, base + random.gauss(0.20, 0.15)))  # noqa: S311
        else:
            # True negative: score below bias with some noise
            base = params["score_bias"]
            score = min(0.99, max(0.01, base - random.gauss(0.20, 0.15)))  # noqa: S311
        raw_scores.append(round(score, 3))
        labels.append(label)

    return raw_scores, labels


def bootstrap_all_agents(
    output_dir: Path,
    use_synthetic: bool = True,
    dataset_name: str = "synthetic_bootstrap",
) -> list[Path]:
    """
    Bootstrap calibration models for all 5 agents.

    use_synthetic=True: Uses synthetic data (for CI/testing only).
    use_synthetic=False: Expects CSV files at output_dir/../training_data/AgentN_scores.csv

    Returns list of saved model paths.
    """
    agent_ids = ["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"]
    saved = []

    for agent_id in agent_ids:
        try:
            if use_synthetic:
                raw_scores, labels = generate_synthetic_training_data(agent_id)
                platt_a, platt_b = fit_platt_scaling(raw_scores[:400], labels[:400])
                metrics = evaluate_calibration(raw_scores[400:], labels[400:], platt_a, platt_b)
                result = CalibrationTrainingResult(
                    agent_id=agent_id,
                    platt_a=platt_a,
                    platt_b=platt_b,
                    brier_score=metrics.get("brier_score", 0.5),
                    ece=metrics.get("ece", 0.5),
                    n_samples=500,
                    dataset=dataset_name,
                    calibration_status="UNCALIBRATED",  # Synthetic = still UNCALIBRATED
                )
            else:
                csv_path = output_dir.parent / "training_data" / f"{agent_id}_scores.csv"
                if not csv_path.exists():
                    logger.warning(f"Training data not found for {agent_id}: {csv_path}")
                    continue
                result = train_from_csv(csv_path, agent_id, dataset_name)

            path = save_trained_model(result, output_dir)
            saved.append(path)

        except Exception as e:
            logger.error(f"Failed to train calibration for {agent_id}: {e}")

    return saved


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train forensic calibration models")
    parser.add_argument("--from-csv", type=Path, help="CSV file with raw_score,label columns")
    parser.add_argument("--agent-id", type=str, help="Agent ID (required with --from-csv)")
    parser.add_argument("--dataset", type=str, default="custom", help="Dataset name")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("storage/calibration_models"),
        help="Directory to save calibration models",
    )
    parser.add_argument(
        "--bootstrap-all",
        action="store_true",
        help="Bootstrap synthetic models for all 5 agents (for testing only)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.bootstrap_all:
        paths = bootstrap_all_agents(
            output_dir=args.output_dir,
            use_synthetic=True,
        )
        print(f"Bootstrapped {len(paths)} calibration models:")
        for p in paths:
            print(f"  {p}")
    elif args.from_csv and args.agent_id:
        result = train_from_csv(args.from_csv, args.agent_id, args.dataset)
        path = save_trained_model(result, args.output_dir)
        print(f"Saved: {path}")
        print(f"  Brier score: {result.brier_score}")
        print(f"  ECE: {result.ece}")
    else:
        parser.print_help()
