"""
Model Cache Module
==================

Centralized caching for ML models to avoid repeated loading.
"""

from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def get_ela_classifier() -> Any:
    """Lazy-load and cache ELA classifier from the configured calibration models volume."""
    try:
        import pathlib

        import joblib

        from core.config import get_settings

        model_path = pathlib.Path(get_settings().calibration_models_path) / "ela_model.pkl"
        return joblib.load(model_path)
    except Exception as e:
        raise RuntimeError(f"Failed to load ELA classifier: {e}")


def clear_model_cache() -> None:
    """Clear all cached models."""
    get_ela_classifier.cache_clear()
