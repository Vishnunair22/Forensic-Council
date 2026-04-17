"""
Model Cache Module
==================

Centralized caching for ML models to avoid repeated loading.
"""

from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def get_ela_classifier() -> Any:
    """Lazy-load and cache ELA classifier."""
    try:
        import pathlib

        import joblib
        model_path = pathlib.Path(__file__).parent.parent / "storage" / "calibration_models" / "ela_model.pkl"
        return joblib.load(model_path)
    except Exception as e:
        raise RuntimeError(f"Failed to load ELA classifier: {e}")


@lru_cache(maxsize=1)
def get_wav2vec2_model() -> Any:
    """Lazy-load and cache Wav2Vec2 deepfake detector."""
    try:
        import torch
        return torch.hub.load(
            "facebook/wav2vec2-large-xlsr-53-english",
            force_reload=False
        )
    except Exception as e:
        raise RuntimeError(f"Failed to load Wav2Vec2 model: {e}")


def clear_model_cache() -> None:
    """Clear all cached models."""
    get_ela_classifier.cache_clear()
    get_wav2vec2_model.cache_clear()

