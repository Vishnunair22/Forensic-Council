"""Plan 3.3 — positive calibration disclosure for TRAINED contributing agents.

Verifies the report builder's `_trained_contributors` helper selects only
TRAINED-status agents and surfaces the benchmark dataset + model version that
were persisted alongside the calibrated model.
"""

from __future__ import annotations

from types import SimpleNamespace

import core.deterministic_report_builder as drb
from core.calibration import CalibrationStatus


class _StubLayer:
    def __init__(self, models: dict[str, SimpleNamespace]):
        self._models = models

    def load_model(self, agent_id: str):
        model = self._models.get(agent_id)
        if model is None:
            raise KeyError(agent_id)
        return model


def _model(status, dataset="", version=""):
    return SimpleNamespace(
        calibration_status=status,
        benchmark_dataset=dataset,
        version=version,
    )


def test_trained_contributors_selects_only_trained(monkeypatch):
    layer = _StubLayer(
        {
            "Agent1": _model(CalibrationStatus.UNCALIBRATED, "engineering_defaults_not_validated", "v1.0_default"),
            "Agent3": _model(CalibrationStatus.UNCALIBRATED),
            "Agent5": _model(CalibrationStatus.TRAINED, "HC3 human-vs-ChatGPT, 400/400", "v1.0_trained_20260611"),
        }
    )
    monkeypatch.setattr(drb, "get_calibration_layer", lambda: layer)

    trained = drb._trained_contributors(["Agent1", "Agent3", "Agent5"])

    assert trained == [("Agent5", "HC3 human-vs-ChatGPT, 400/400", "v1.0_trained_20260611")]


def test_trained_contributors_handles_unreadable_model(monkeypatch):
    layer = _StubLayer({"Agent5": _model(CalibrationStatus.TRAINED, "HC3", "v1.0")})
    monkeypatch.setattr(drb, "get_calibration_layer", lambda: layer)

    # Agent2 is absent -> load_model raises -> skipped, never raises out.
    trained = drb._trained_contributors(["Agent2", "Agent5"])

    assert trained == [("Agent5", "HC3", "v1.0")]


def test_trained_contributors_blank_dataset_falls_back(monkeypatch):
    layer = _StubLayer({"Agent5": _model(CalibrationStatus.TRAINED, "", "")})
    monkeypatch.setattr(drb, "get_calibration_layer", lambda: layer)

    trained = drb._trained_contributors(["Agent5"])

    assert trained == [("Agent5", "labelled benchmark", "")]
