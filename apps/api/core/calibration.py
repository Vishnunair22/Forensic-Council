"""
Confidence Calibration Layer
===========================

Provides versioned calibration models for forensic confidence scores.

IMPORTANT — Calibration Honesty Policy
---------------------------------------
Two calibration states exist:

  CalibrationStatus.TRAINED   — Parameters were fitted on a labelled forensic
                                 dataset (e.g. FaceForensics++, NIST MFC).
                                 Scores carry evidential weight.

  CalibrationStatus.UNCALIBRATED — Parameters are engineering defaults, NOT
                                    fitted to data.  Scores are raw detector
                                    outputs rescaled through an arbitrary sigmoid.
                                    These MUST NOT be presented as calibrated
                                    probabilities in court proceedings.

All default models produced by fit_default_model() are UNCALIBRATED.
Replace them by running a real calibration training script against a labelled
dataset and saving the resulting parameters via save_trained_model().
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from core.config import get_settings


class CalibrationMethod(StrEnum):
    """Calibration methods available."""

    PLATT_SCALING = "PLATT_SCALING"
    ISOTONIC_REGRESSION = "ISOTONIC_REGRESSION"
    TEMPERATURE_SCALING = "TEMPERATURE_SCALING"
    RULE_BASED = "RULE_BASED"


class CalibrationStatus(StrEnum):
    """Whether the calibration parameters were fitted to real data."""

    TRAINED = "TRAINED"
    UNCALIBRATED = "UNCALIBRATED"


class CalibrationModel(BaseModel):
    """Calibration model metadata and parameters."""

    model_id: UUID = Field(default_factory=uuid4)
    agent_id: str
    method: CalibrationMethod
    benchmark_dataset: str
    version: str
    created_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    params: dict[str, Any] = Field(default_factory=dict)
    calibration_status: CalibrationStatus = CalibrationStatus.UNCALIBRATED


class CalibratedConfidence(BaseModel):
    """Confidence result with honest calibration status disclosure."""

    raw_score: float
    raw_confidence_score: float  # Rescaled score (Platt sigmoid or engineering default)
    true_positive_rate: float
    false_positive_rate: float
    calibration_model_id: UUID
    calibration_version: str
    benchmark_dataset: str
    court_statement: str
    calibrated: bool = False
    calibration_status: CalibrationStatus = CalibrationStatus.UNCALIBRATED
    confidence_interval: dict[str, Any] | None = Field(
        default=None,
        description="Bootstrap 95% CI: {'lower': float, 'upper': float, 'method': str}",
    )
    uncertainty: UncertaintyDecomposition | None = Field(
        default=None,
        description="Epistemic/aleatoric uncertainty decomposition",
    )


class UncertaintyDecomposition(BaseModel):
    """
    Decomposition of total uncertainty into epistemic and aleatoric components.

    Based on arXiv:2512.16614 ("Don't Guess, Escalate"):
    - Epistemic uncertainty: model uncertainty — the calibration parameters may
      be wrong. High epistemic uncertainty means the model doesn't have enough
      information to be confident. This is the signal that should trigger HITL
      escalation.
    - Aleatoric uncertainty: inherent data noise — the evidence itself is
      ambiguous. This cannot be reduced by more data or better models.

    The escalation_threshold is exceeded when epistemic uncertainty dominates,
    meaning the agent should NOT proceed autonomously.
    """

    total_uncertainty: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Total uncertainty (CI width)",
    )
    epistemic_uncertainty: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model/parameter uncertainty — reducible with better calibration",
    )
    aleatoric_uncertainty: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Inherent data noise — irreducible",
    )
    epistemic_fraction: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Fraction of total uncertainty that is epistemic",
    )
    should_escalate: bool = Field(
        default=False,
        description="True when epistemic uncertainty exceeds escalation threshold",
    )
    escalation_reason: str | None = Field(
        default=None,
        description="Human-readable reason for escalation recommendation",
    )


class CalibrationLayer:
    """
    Confidence calibration layer with versioned models.

    Applies sigmoid/Platt rescaling to raw detector scores.
    All default models are UNCALIBRATED — see module docstring.
    """

    def __init__(self, models_path: str | None = None):
        if models_path is None:
            settings = get_settings()
            models_path = settings.calibration_models_path
        self.models_path = Path(models_path)
        self._loaded_models: dict[str, CalibrationModel] = {}

    def _get_agent_dir(self, agent_id: str) -> Path:
        return self.models_path / agent_id

    def _get_model_path(self, agent_id: str, version: str) -> Path:
        return self._get_agent_dir(agent_id) / f"{version}.json"

    def load_model(self, agent_id: str, version: str = "latest") -> CalibrationModel:
        cache_key = f"{agent_id}:{version}"
        if cache_key in self._loaded_models:
            return self._loaded_models[cache_key]

        model_path = self._get_model_path(agent_id, version)

        if model_path.exists():
            with open(model_path) as f:
                data = json.load(f)
                model = CalibrationModel(**data)
        else:
            agent_dir = self._get_agent_dir(agent_id)
            if agent_dir.exists():
                model_files = sorted(agent_dir.glob("*.json"))
                if model_files:
                    with open(model_files[-1]) as f:
                        data = json.load(f)
                        model = CalibrationModel(**data)
                else:
                    raise FileNotFoundError(
                        f"No calibration model found for {agent_id}"
                    )
            else:
                raise FileNotFoundError(
                    f"Calibration model directory not found for {agent_id}"
                )

        self._loaded_models[cache_key] = model
        return model

    def fit_default_model(self, agent_id: str) -> CalibrationModel:
        """
        Create a default (UNCALIBRATED) model using engineering-chosen sigmoid
        parameters.

        These values were chosen to produce a conservative output distribution
        for the relevant detector type.  They are NOT derived from any labelled
        forensic dataset and have NOT been validated against published benchmarks.

        The resulting model carries CalibrationStatus.UNCALIBRATED.  It MUST NOT
        be cited in court as a "calibrated probability".  To produce a trained
        model, run a calibration script against a labelled dataset (e.g.
        FaceForensics++, NIST MFC 2019) and call save_trained_model().

        Returns:
            CalibrationModel with status=UNCALIBRATED
        """
        version = f"v1.0_default_{datetime.now(UTC).strftime('%Y%m%d')}"

        # Per-agent sigmoid parameters (A*x + B in logit space).
        # THESE ARE ENGINEERING DEFAULTS, NOT BENCHMARK-DERIVED VALUES.
        # Conservative (erring toward lower output) to reduce false-positive rate.
        _DEFAULT_PARAMS: dict[str, dict[str, Any]] = {
            "agent1_image": {
                "method": "platt",
                "A": 2.5,
                "B": -1.2,
                "baseline_tpr": 0.80,
                "baseline_fpr": 0.10,
            },
            "agent2_audio": {
                "method": "platt",
                "A": 2.0,
                "B": -1.0,
                "baseline_tpr": 0.75,
                "baseline_fpr": 0.12,
            },
            "agent3_object": {
                "method": "platt",
                "A": 1.8,
                "B": -0.9,
                "baseline_tpr": 0.72,
                "baseline_fpr": 0.15,
            },
            "agent4_video": {
                "method": "platt",
                "A": 2.2,
                "B": -1.1,
                "baseline_tpr": 0.78,
                "baseline_fpr": 0.11,
            },
            "agent5_metadata": {
                "method": "platt",
                "A": 3.0,
                "B": -1.5,
                "baseline_tpr": 0.82,
                "baseline_fpr": 0.08,
            },
        }

        normalized_agent_id = agent_id.lower()
        params = _DEFAULT_PARAMS.get(
            normalized_agent_id,
            {
                "method": "platt",
                "A": 2.0,
                "B": -1.0,
                "baseline_tpr": 0.75,
                "baseline_fpr": 0.12,
            },
        )

        model = CalibrationModel(
            agent_id=agent_id,
            method=CalibrationMethod.PLATT_SCALING,
            benchmark_dataset="engineering_defaults_not_validated",
            version=version,
            params=params,
            calibration_status=CalibrationStatus.UNCALIBRATED,
        )

        try:
            agent_dir = self._get_agent_dir(agent_id)
            agent_dir.mkdir(parents=True, exist_ok=True)

            model_path = self._get_model_path(agent_id, version)
            with open(model_path, "w") as f:
                json.dump(model.model_dump(), f, indent=2, default=str)

            latest_path = self._get_model_path(agent_id, "latest")
            with open(latest_path, "w") as f:
                json.dump(model.model_dump(), f, indent=2, default=str)
        except OSError:
            # Runtime containers may mount calibration storage read-only or with
            # host-owned permissions. Defaults remain valid in memory; trained
            # calibration persistence is handled through save_trained_model().
            pass

        self._loaded_models[f"{agent_id}:{version}"] = model
        self._loaded_models[f"{agent_id}:latest"] = model

        return model

    def _decompose_uncertainty(
        self,
        raw_score: float,
        params: dict[str, Any],
        method: str,
        ci: dict[str, Any],
        is_uncalibrated: bool,
    ) -> UncertaintyDecomposition:
        """
        Decompose total uncertainty into epistemic and aleatoric components.

        Epistemic uncertainty (EU) is estimated from the bootstrap CI width,
        which captures parameter uncertainty. Aleatoric uncertainty (AU) is
        estimated from the raw score's distance from 0.5 — scores near 0.5
        are inherently ambiguous regardless of calibration quality.

        Escalation is recommended when:
        - EU > 0.15 (absolute) AND EU > 60% of total uncertainty, OR
        - The calibration is UNCALIBRATED and total uncertainty > 0.30

        Args:
            raw_score: Raw detector score
            params: Calibration parameters
            method: Calibration method
            ci: Bootstrap confidence interval dict
            is_uncalibrated: Whether calibration uses engineering defaults

        Returns:
            UncertaintyDecomposition with escalation recommendation
        """
        total = ci["upper"] - ci["lower"]
        total = max(0.0, min(1.0, total))

        # Aleatoric: inherent ambiguity of the raw score.
        # Scores near 0.5 are maximally ambiguous; scores near 0 or 1 are certain.
        aleatoric = 1.0 - 2.0 * abs(raw_score - 0.5)
        aleatoric = max(0.0, min(1.0, aleatoric))

        # Epistemic: whatever remains after subtracting aleatoric from total.
        # Clamp to non-negative.
        epistemic = max(0.0, total - aleatoric * 0.3)
        epistemic = min(1.0, epistemic)

        epistemic_frac = epistemic / total if total > 1e-6 else 0.0

        # Escalation logic per "Don't Guess, Escalate" (arXiv:2512.16614)
        should_escalate = False
        reason = None

        if is_uncalibrated and total > 0.30:
            should_escalate = True
            reason = (
                f"UNCALIBRATED model with high total uncertainty ({total:.3f}). "
                f"Epistemic fraction: {epistemic_frac:.1%}. "
                f"Calibration parameters are engineering defaults — confidence is unreliable. "
                f"Human review recommended before proceeding."
            )
        elif epistemic > 0.15 and epistemic_frac > 0.60:
            should_escalate = True
            reason = (
                f"High epistemic uncertainty ({epistemic:.3f}, {epistemic_frac:.1%} of total). "
                f"Model uncertainty dominates — the detector lacks sufficient information. "
                f"Escalating to human-in-the-loop review per 'Don't Guess, Escalate' protocol."
            )

        return UncertaintyDecomposition(
            total_uncertainty=round(total, 4),
            epistemic_uncertainty=round(epistemic, 4),
            aleatoric_uncertainty=round(aleatoric, 4),
            epistemic_fraction=round(epistemic_frac, 4),
            should_escalate=should_escalate,
            escalation_reason=reason,
        )

    def _bootstrap_ci(
        self,
        raw_score: float,
        params: dict[str, Any],
        method: str,
        n_bootstrap: int = 1000,
        confidence: float = 0.95,
    ) -> dict[str, Any]:
        """
        Compute parametric bootstrap confidence interval for the calibrated score.

        Perturbs the Platt scaling parameters (A, B) by their estimated standard
        errors and recomputes the calibrated probability for each bootstrap
        sample.  Returns the lower and upper bounds of the percentile CI.

        For UNCALIBRATED (engineering-default) models, a wider perturbation
        is applied (±20% of parameter value) to reflect genuine uncertainty
        about parameter correctness.

        Args:
            raw_score: Raw detector score
            params: Calibration parameters dict
            method: Calibration method ('platt' or sigmoid)
            n_bootstrap: Number of bootstrap samples
            confidence: Confidence level (default 0.95)

        Returns:
            Dict with 'lower', 'upper', and 'method' keys
        """
        import math
        import random

        alpha = 1.0 - confidence
        samples: list[float] = []

        if method == "platt":
            A = params.get("A", 2.0)
            B = params.get("B", -1.0)
            # Perturbation std: 20% of parameter value for uncalibrated, 10% for trained
            is_uncal = (
                params.get("calibration_status", "UNCALIBRATED") == "UNCALIBRATED"
            )
            scale = 0.20 if is_uncal else 0.10
            A_std = abs(A) * scale
            B_std = abs(B) * scale

            for _ in range(n_bootstrap):
                A_sample = random.gauss(A, A_std) if A_std > 0 else A
                B_sample = random.gauss(B, B_std) if B_std > 0 else B
                p = 1.0 / (1.0 + math.exp(A_sample * raw_score + B_sample))
                samples.append(p)
        else:
            k = params.get("k", 10.0)
            x0 = params.get("x0", 0.5)
            k_std = abs(k) * 0.20
            x0_std = abs(x0) * 0.20

            for _ in range(n_bootstrap):
                k_sample = random.gauss(k, k_std) if k_std > 0 else k
                x0_sample = random.gauss(x0, x0_std) if x0_std > 0 else x0
                p = 1.0 / (1.0 + math.exp(-k_sample * (raw_score - x0_sample)))
                samples.append(p)

        samples.sort()
        lower_idx = int(math.floor(alpha / 2.0 * n_bootstrap))
        upper_idx = int(math.ceil((1.0 - alpha / 2.0) * n_bootstrap)) - 1
        lower_idx = max(0, min(lower_idx, n_bootstrap - 1))
        upper_idx = max(0, min(upper_idx, n_bootstrap - 1))

        return {
            "lower": round(samples[lower_idx], 4),
            "upper": round(samples[upper_idx], 4),
            "method": f"parametric_bootstrap_{method}",
        }

    def calibrate(
        self,
        agent_id: str,
        raw_score: float,
        finding_class: str,
        version: str = "latest",
    ) -> CalibratedConfidence:
        """
        Apply sigmoid rescaling to a raw confidence score.

        If no trained model exists, a default (UNCALIBRATED) model is used.
        The returned CalibratedConfidence.calibration_status reflects which
        case applied — check it before presenting scores in any legal context.

        Returns:
            CalibratedConfidence with honest calibration_status
        """
        is_default = False
        try:
            model = self.load_model(agent_id, version)
            is_default = model.calibration_status == CalibrationStatus.UNCALIBRATED
        except FileNotFoundError:
            model = self.fit_default_model(agent_id)
            is_default = True

        params = model.params
        method = params.get("method", "sigmoid")

        if raw_score is None:
            raw_score = 0.5

        if method == "platt":
            import math

            A = params.get("A", 2.0)
            B = params.get("B", -1.0)
            calibrated_prob = 1.0 / (1.0 + math.exp(A * raw_score + B))
        else:
            import math

            k = params.get("k", 10.0)
            x0 = params.get("x0", 0.5)
            calibrated_prob = 1.0 / (1.0 + math.exp(-k * (raw_score - x0)))

        baseline_tpr = params.get("baseline_tpr", 0.75)
        baseline_fpr = params.get("baseline_fpr", 0.12)
        tpr = baseline_tpr + (1.0 - baseline_tpr) * calibrated_prob
        fpr = baseline_fpr * (1.0 - calibrated_prob)

        cal_status = (
            CalibrationStatus.UNCALIBRATED if is_default else model.calibration_status
        )

        if cal_status == CalibrationStatus.UNCALIBRATED:
            court_statement = (
                f"[NOT court-admissible — UNCALIBRATED] "
                f"Raw score {raw_score:.2f} for '{finding_class}' was rescaled through "
                f"an engineering-default sigmoid (A={params.get('A', 2.0):.1f}, "
                f"B={params.get('B', -1.0):.1f}). "
                f"These parameters were NOT fitted to any labelled forensic dataset. "
                f"The resulting value ({calibrated_prob:.2f}) is an indicative score only "
                f"and MUST NOT be cited as a calibrated probability in legal proceedings. "
                f"To produce court-admissible scores, run site-specific calibration against "
                f"a validated forensic benchmark dataset."
            )
        else:
            court_statement = (
                f"[TRAINED calibration — {model.benchmark_dataset}] "
                f"A detector score of {raw_score:.2f} for '{finding_class}' corresponds "
                f"to an estimated true-positive rate of {tpr:.1%} "
                f"and false-positive rate of {fpr:.1%}, "
                f"as measured on {model.benchmark_dataset} (model v{model.version})."
            )

        # Compute bootstrap confidence interval
        ci = self._bootstrap_ci(raw_score, params, method)

        # Decompose uncertainty into epistemic/aleatoric components
        uncertainty = self._decompose_uncertainty(
            raw_score,
            params,
            method,
            ci,
            is_default,
        )

        return CalibratedConfidence(
            raw_score=raw_score,
            raw_confidence_score=calibrated_prob,
            true_positive_rate=tpr,
            false_positive_rate=fpr,
            calibration_model_id=model.model_id,
            calibration_version=model.version,
            benchmark_dataset=model.benchmark_dataset,
            court_statement=court_statement,
            calibrated=cal_status == CalibrationStatus.TRAINED,
            calibration_status=cal_status,
            confidence_interval=ci,
            uncertainty=uncertainty,
        )

    def list_versions(self, agent_id: str) -> list[str]:
        agent_dir = self._get_agent_dir(agent_id)
        if not agent_dir.exists():
            return []
        return sorted(f.stem for f in agent_dir.glob("*.json") if f.stem != "latest")


# Global instance
_calibration_layer: CalibrationLayer | None = None


def get_calibration_layer() -> CalibrationLayer:
    global _calibration_layer
    if _calibration_layer is None:
        _calibration_layer = CalibrationLayer()
    return _calibration_layer
