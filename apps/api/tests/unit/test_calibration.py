"""
Unit tests for the confidence calibration layer.

All tests use tmp_path for model storage so they are hermetic and leave no
files on disk after the test run.  No real database or external service is
required.
"""

import json
import math
import os
from pathlib import Path
from typing import Any

import pytest

# ── Minimal env so config initializes without a .env file ────────────────────
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_PASSWORD", "test")
os.environ.setdefault("NEXT_PUBLIC_DEMO_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")

from datetime import UTC

from core.calibration import (
    CalibratedConfidence,
    CalibrationLayer,
    CalibrationMethod,
)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Fixtures
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@pytest.fixture
def layer(tmp_path: Path) -> CalibrationLayer:
    """A CalibrationLayer backed by a temporary directory."""
    return CalibrationLayer(models_path=str(tmp_path))


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Tests
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@pytest.mark.parametrize(
    ("agent_id", "raw_score"),
    [
        ("agent1_image", 0.0),
        ("agent1_image", 0.5),
        ("agent1_image", 1.0),
        ("agent2_audio", 0.3),
        ("agent3_object", 0.7),
        ("unknown_agent", 0.5),
    ],
)
def test_calibrate_returns_float_in_range(
    layer: CalibrationLayer,
    agent_id: str,
    raw_score: float,
) -> None:
    """
    calibrate() must always return a CalibratedConfidence whose
    calibrated_probability is a float in [0.0, 1.0].
    """
    result: CalibratedConfidence = layer.calibrate(
        agent_id=agent_id,
        raw_score=raw_score,
        finding_class="test_finding",
    )

    assert isinstance(result, CalibratedConfidence)
    assert isinstance(result.raw_confidence_score, float)
    assert 0.0 <= result.raw_confidence_score <= 1.0


def test_default_calibration_court_statement_warns_uncalibrated(
    layer: CalibrationLayer,
) -> None:
    """
    When no site-specific model exists, fit_default_model is used and the
    court_statement should clearly communicate the calibration is from
    published defaults (not site-specific data), which is NOT fully
    court-admissible.

    Accepted phrases (case-insensitive): 'recommended', 'default', 'published'
    """
    result = layer.calibrate(
        agent_id="agent1_image",
        raw_score=0.6,
        finding_class="ela",
    )
    court = result.court_statement.lower()
    # The default statement should mention that site-specific calibration is
    # recommended, i.e. it's not yet court-admissible production quality.
    has_warning = (
        "recommended" in court
        or "default" in court
        or "published" in court
        or "not court" in court
        or "uncalibrated" in court
    )
    assert has_warning, (
        f"Court statement for default calibration did not contain the expected "
        f"disclaimer. Got: {result.court_statement!r}"
    )


def test_default_calibration_calibrated_flag_is_false(
    layer: CalibrationLayer,
) -> None:
    """
    When the default model is auto-created because no saved model exists,
    the CalibratedConfidence.calibrated field must be False.
    """
    result = layer.calibrate(
        agent_id="agent2_audio",
        raw_score=0.5,
        finding_class="audio_deepfake",
    )
    assert result.calibrated is False


def test_trained_model_produces_calibrated_true(
    layer: CalibrationLayer,
    tmp_path: Path,
) -> None:
    """
    When a model is explicitly saved to disk (simulating a site-specific
    trained model), calibrate() should set calibrated=True.
    """
    agent_id = "agent1_image"
    version = "v1.0_site_specific"

    # Write a model file that does NOT carry the 'is_default' flag
    from datetime import datetime
    from uuid import uuid4 as _uuid4

    model_data: dict[str, Any] = {
        "model_id": str(_uuid4()),
        "agent_id": agent_id,
        "method": CalibrationMethod.PLATT_SCALING,
        "benchmark_dataset": "local_benchmark_v1",
        "version": version,
        "created_utc": datetime.now(UTC).isoformat(),
        "params": {
            "method": "platt",
            "A": 2.5,
            "B": -1.2,
            "baseline_tpr": 0.82,
            "baseline_fpr": 0.08,
        },
        "calibration_status": "TRAINED",
    }

    agent_dir = tmp_path / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    model_path = agent_dir / f"{version}.json"
    with open(model_path, "w") as f:
        json.dump(model_data, f)

    result = layer.calibrate(
        agent_id=agent_id,
        raw_score=0.7,
        finding_class="ela",
        version=version,
    )

    assert result.calibrated is True


def test_platt_math_correct(layer: CalibrationLayer) -> None:
    """
    Platt scaling formula: p = 1 / (1 + exp(A*x + B))
    For A=2.0, B=-1.0, raw_score=0.5:
        exponent = 2.0*0.5 + (-1.0) = 0.0
        p = 1 / (1 + exp(0)) = 1 / 2 = 0.5
    """
    # Use the default model for agent2_audio which has A=2.0, B=-1.0
    result = layer.calibrate(
        agent_id="agent2_audio",
        raw_score=0.5,
        finding_class="audio_test",
    )
    expected = 1.0 / (1.0 + math.exp(2.0 * 0.5 + (-1.0)))
    assert abs(result.raw_confidence_score - expected) < 1e-9, (
        f"Expected {expected}, got {result.raw_confidence_score}"
    )


def test_list_versions_empty_when_no_models(layer: CalibrationLayer) -> None:
    """list_versions returns an empty list for an agent with no saved models."""
    versions = layer.list_versions("nonexistent_agent")
    assert versions == []


def test_list_versions_after_fit_default(
    layer: CalibrationLayer,
) -> None:
    """
    After fit_default_model the version string is stored and list_versions
    returns at least one entry.
    """
    layer.fit_default_model("agent3_object")
    versions = layer.list_versions("agent3_object")
    assert len(versions) >= 1


def test_none_raw_score_defaults_to_neutral(layer: CalibrationLayer) -> None:
    """A None raw_score should be treated as 0.5 (neutral) without raising."""
    result = layer.calibrate(
        agent_id="agent1_image",
        raw_score=None,  # type: ignore[arg-type]
        finding_class="test",
    )
    assert isinstance(result.raw_confidence_score, float)
    assert 0.0 <= result.raw_confidence_score <= 1.0


def test_calibrated_confidence_has_required_fields(layer: CalibrationLayer) -> None:
    """CalibratedConfidence must expose all fields needed for court reporting."""
    result = layer.calibrate("agent5_metadata", 0.8, "exif_anomaly")
    assert hasattr(result, "raw_confidence_score")
    assert hasattr(result, "true_positive_rate")
    assert hasattr(result, "false_positive_rate")
    assert hasattr(result, "court_statement")
    assert hasattr(result, "calibration_model_id")
    assert hasattr(result, "calibration_version")
    assert hasattr(result, "benchmark_dataset")
    assert hasattr(result, "calibration_status")
    assert hasattr(result, "confidence_interval")
    assert hasattr(result, "uncertainty")
    assert isinstance(result.court_statement, str)
    assert len(result.court_statement) > 0
