"""
Model Registry — versioned model management for ML tools.

Provides:
  - Model version pinning with checksum validation
  - Model cache management
  - Health checks for model availability
  - Warm-up coordination

This replaces the ad-hoc model loading in individual ML tool scripts.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.structured_logging import get_logger

logger = get_logger(__name__)

# Default model cache directory
_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "forensic_council" / "models"


@dataclass
class ModelSpec:
    """Specification for a versioned ML model."""

    name: str
    version: str
    source: str  # URL or local path
    checksum: str | None = None  # SHA-256 expected checksum
    framework: str = "pytorch"  # pytorch, onnx, tensorflow
    size_mb: float = 0.0
    warmup_required: bool = True
    loaded: bool = False
    load_time_s: float = 0.0
    error: str | None = None


class ModelRegistry:
    """
    Centralized model registry for all ML tools.

    Tracks model versions, validates checksums, and manages cache.
    """

    # Known models used by ML tools — pinned to specific versions
    KNOWN_MODELS: dict[str, ModelSpec] = {
        "yolo11n": ModelSpec(
            name="yolo11n",
            version="11.0",
            source="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt",
            checksum=None,  # Ultralytics handles its own checksums
            framework="pytorch",
            size_mb=6.2,
            warmup_required=True,
        ),
        "easyocr": ModelSpec(
            name="easyocr",
            version="1.7.2",
            source="pypi",
            framework="pytorch",
            size_mb=150.0,
            warmup_required=True,
        ),
        "openclip_vit_b_32": ModelSpec(
            name="openclip_vit_b_32",
            version="2.30.0",
            source="openclip:ViT-B-32",
            framework="pytorch",
            size_mb=338.0,
            warmup_required=True,
        ),
    }

    def __init__(self, cache_dir: Path | None = None):
        self._cache_dir = cache_dir or _DEFAULT_CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._models: dict[str, ModelSpec] = dict(self.KNOWN_MODELS)

    def get_model(self, name: str) -> ModelSpec | None:
        """Get model spec by name."""
        return self._models.get(name)

    def list_models(self) -> list[ModelSpec]:
        """List all registered models."""
        return list(self._models.values())

    def get_models_needing_warmup(self) -> list[ModelSpec]:
        """Return models that require warm-up and haven't been warmed up yet."""
        return [m for m in self._models.values() if m.warmup_required and not m.loaded]

    def mark_loaded(self, name: str, load_time_s: float = 0.0) -> None:
        """Mark a model as loaded."""
        if name in self._models:
            self._models[name].loaded = True
            self._models[name].load_time_s = load_time_s
            self._models[name].error = None

    def mark_error(self, name: str, error: str) -> None:
        """Mark a model as failed to load."""
        if name in self._models:
            self._models[name].error = error
            self._models[name].loaded = False

    def get_health_status(self) -> dict[str, dict[str, Any]]:
        """Return health status for all models."""
        status = {}
        for name, model in self._models.items():
            status[name] = {
                "version": model.version,
                "loaded": model.loaded,
                "load_time_s": round(model.load_time_s, 2),
                "error": model.error,
                "size_mb": model.size_mb,
            }
        return status

    @staticmethod
    def compute_file_checksum(file_path: Path) -> str:
        """Compute SHA-256 checksum of a file."""
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def validate_model(self, name: str, file_path: Path) -> bool:
        """Validate a model file against its expected checksum."""
        model = self._models.get(name)
        if model is None or model.checksum is None:
            return True  # No checksum to validate against
        actual = self.compute_file_checksum(file_path)
        if actual != model.checksum:
            logger.error(
                f"Model checksum mismatch for {name}",
                expected=model.checksum[:16],
                actual=actual[:16],
            )
            return False
        return True


# Global singleton
_registry: ModelRegistry | None = None


def get_model_registry() -> ModelRegistry:
    """Get or create the global model registry."""
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
