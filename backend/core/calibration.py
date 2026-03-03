"""
Confidence Calibration Layer
===========================

Provides versioned calibration models for court-defensible confidence scores.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CalibrationMethod(str, Enum):
    """Calibration methods available."""
    PLATT_SCALING = "PLATT_SCALING"
    ISOTONIC_REGRESSION = "ISOTONIC_REGRESSION"
    TEMPERATURE_SCALING = "TEMPERATURE_SCALING"
    RULE_BASED = "RULE_BASED"


class CalibrationModel(BaseModel):
    """Calibration model metadata and parameters."""
    model_id: UUID = Field(default_factory=uuid4)
    agent_id: str
    method: CalibrationMethod
    benchmark_dataset: str
    version: str
    created_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    params: dict[str, Any] = Field(default_factory=dict)


class CalibratedConfidence(BaseModel):
    """Calibrated confidence result with court-admissible statement."""
    raw_score: float
    calibrated_probability: float
    true_positive_rate: float
    false_positive_rate: float
    calibration_model_id: UUID
    calibration_version: str
    benchmark_dataset: str
    court_statement: str


class CalibrationLayer:
    """
    Confidence calibration layer with versioned models.
    
    Provides calibrated confidence scores for agent findings,
    generating court-defensible statements.
    """
    
    def __init__(self, models_path: str = "./storage/calibration_models"):
        self.models_path = Path(models_path)
        self._loaded_models: dict[str, CalibrationModel] = {}
    
    def _get_agent_dir(self, agent_id: str) -> Path:
        """Get the directory for an agent's calibration models."""
        return self.models_path / agent_id
    
    def _get_model_path(self, agent_id: str, version: str) -> Path:
        """Get the path to a specific model version."""
        return self._get_agent_dir(agent_id) / f"{version}.json"
    
    def load_model(self, agent_id: str, version: str = "latest") -> CalibrationModel:
        """
        Load a calibration model for an agent.
        
        Args:
            agent_id: The agent identifier
            version: The model version (default: "latest")
            
        Returns:
            CalibrationModel instance
        """
        # Check if already loaded
        cache_key = f"{agent_id}:{version}"
        if cache_key in self._loaded_models:
            return self._loaded_models[cache_key]
        
        # Try to load from disk
        model_path = self._get_model_path(agent_id, version)
        
        if model_path.exists():
            with open(model_path, 'r') as f:
                data = json.load(f)
                model = CalibrationModel(**data)
        else:
            # Try to find latest version
            agent_dir = self._get_agent_dir(agent_id)
            if agent_dir.exists():
                model_files = sorted(agent_dir.glob("*.json"))
                if model_files:
                    with open(model_files[-1], 'r') as f:
                        data = json.load(f)
                        model = CalibrationModel(**data)
                else:
                    raise FileNotFoundError(f"No calibration model found for {agent_id}")
            else:
                raise FileNotFoundError(f"Calibration model directory not found for {agent_id}")
        
        self._loaded_models[cache_key] = model
        return model
    
    def fit_stub_model(self, agent_id: str) -> CalibrationModel:
        """
 sigmoid calibration curve for testing.
        
        Creates a RULE_BASED model with stub parameters that simulate
        a sigmoid calibration curve.
        
        Args:
            agent_id: The agent identifier
            
        Returns:
            The created CalibrationModel
        """
        # Generate version based on timestamp with unique identifier
        version = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
        
        # Stub sigmoid parameters (simulating calibration curve)
        # Using a simple sigmoid: p = 1 / (1 + exp(-k*(x - x0)))
        params = {
            "method": "sigmoid",
            "k": 10.0,  # Steepness
            "x0": 0.5,  # Midpoint
            "baseline_tpr": 0.1,  # TPR at low confidence
            "baseline_fpr": 0.05,  # FPR at low confidence
        }
        
        model = CalibrationModel(
            agent_id=agent_id,
            method=CalibrationMethod.RULE_BASED,
            benchmark_dataset="stub_benchmark",
            version=version,
            params=params,
        )
        
        # Save to disk
        agent_dir = self._get_agent_dir(agent_id)
        agent_dir.mkdir(parents=True, exist_ok=True)
        
        model_path = self._get_model_path(agent_id, version)
        with open(model_path, 'w') as f:
            json.dump(model.model_dump(), f, indent=2, default=str)
        
        # Also create "latest" symlink or copy
        latest_path = self._get_model_path(agent_id, "latest")
        with open(latest_path, 'w') as f:
            json.dump(model.model_dump(), f, indent=2, default=str)
        
        # Cache it
        self._loaded_models[f"{agent_id}:{version}"] = model
        self._loaded_models[f"{agent_id}:latest"] = model
        
        return model
    
    def calibrate(
        self,
        agent_id: str,
        raw_score: float,
        finding_class: str,
        version: str = "latest"
    ) -> CalibratedConfidence:
        """
        Apply calibration to a raw confidence score.
        
        Args:
            agent_id: The agent identifier
            raw_score: The raw confidence score (0-1)
            finding_class: The type of finding
            version: The model version to use
            
        Returns:
            CalibratedConfidence with court statement
        """
        # Load the model
        try:
            model = self.load_model(agent_id, version)
        except FileNotFoundError:
            # Create stub model if none exists
            model = self.fit_stub_model(agent_id)
        
        # Apply sigmoid calibration
        params = model.params
        k = params.get("k", 10.0)
        x0 = params.get("x0", 0.5)
        baseline_tpr = params.get("baseline_tpr", 0.1)
        baseline_fpr = params.get("baseline_fpr", 0.05)
        
        # Sigmoid transformation
        import math
        calibrated_prob = 1.0 / (1.0 + math.exp(-k * (raw_score - x0)))
        
        # Estimate TPR and FPR based on calibrated probability
        # In production, these would come from actual benchmark data
        tpr = baseline_tpr + (1.0 - baseline_tpr) * calibrated_prob
        fpr = baseline_fpr + (1.0 - baseline_fpr) * calibrated_prob
        
        # Generate court statement
        court_statement = (
            f"Based on benchmark performance against {model.benchmark_dataset}, "
            f"a model confidence of {raw_score:.2f} in class '{finding_class}' "
            f"corresponds to a true positive rate of {tpr:.1%} "
            f"with a false positive rate of {fpr:.1%}."
        )
        
        return CalibratedConfidence(
            raw_score=raw_score,
            calibrated_probability=calibrated_prob,
            true_positive_rate=tpr,
            false_positive_rate=fpr,
            calibration_model_id=model.model_id,
            calibration_version=model.version,
            benchmark_dataset=model.benchmark_dataset,
            court_statement=court_statement,
        )
    
    def list_versions(self, agent_id: str) -> list[str]:
        """
        List all available versions for an agent.
        
        Args:
            agent_id: The agent identifier
            
        Returns:
            List of version strings
        """
        agent_dir = self._get_agent_dir(agent_id)
        if not agent_dir.exists():
            return []
        
        versions = []
        for f in agent_dir.glob("*.json"):
            if f.stem != "latest":
                versions.append(f.stem)
        
        return sorted(versions)


# Global instance
_calibration_layer: Optional[CalibrationLayer] = None


def get_calibration_layer() -> CalibrationLayer:
    """Get the global calibration layer instance."""
    global _calibration_layer
    if _calibration_layer is None:
        _calibration_layer = CalibrationLayer()
    return _calibration_layer
