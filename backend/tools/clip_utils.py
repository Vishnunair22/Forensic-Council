"""
CLIP Shared Utility
===================

Singleton wrapper for OpenCLIP model to avoid loading the ~300MB model
multiple times across different agents.

Usage:
    from tools.clip_utils import get_clip_analyzer

    analyzer = get_clip_analyzer()
    result = analyzer.analyze_image("path/to/image.jpg", categories=[...])
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional

from core.structured_logging import get_logger

logger = get_logger(__name__)

# Global singleton instance with thread-safe lock
_clip_analyzer_instance: Optional[CLIPImageAnalyzer] = None
_clip_lock = threading.Lock()


@dataclass
class CLIPAnalysisResult:
    """Result from CLIP image analysis."""

    top_match: str
    top_confidence: float
    all_scores: list[tuple[str, float]]
    concern_flag: bool
    available: bool
    embedding: Optional[list[float]] = None
    error: Optional[str] = None


class CLIPImageAnalyzer:
    """
    Singleton CLIP image analyzer for zero-shot image classification.

    Lazily loads the model on first use to avoid unnecessary memory
    consumption when CLIP features are not needed.
    """

    # Default forensic-relevant image categories
    DEFAULT_IMAGE_CATEGORIES = [
        "a screenshot of a document",
        "an outdoor photograph",
        "an indoor photograph",
        "a social media post",
        "a surveillance camera frame",
        "a digitally generated or AI image",
        "a scanned photograph",
        "a news article image",
        "a passport or identification document",
        "a screenshot of a chat conversation",
        "a forensic evidence photograph",
        "a product or commercial image",
    ]

    # Categories for contraband/concern detection
    CONCERN_CATEGORIES = [
        "a firearm or weapon",
        "an explosive device",
        "drug paraphernalia",
        "a knife or bladed weapon",
        "a safe everyday object",
        "a person",
        "a vehicle",
    ]

    def __init__(self):
        """Initialize analyzer (does not load model yet)."""
        self._model = None
        self._preprocess = None
        self._tokenizer = None
        self._device = None
        self._model_name = "ViT-B-32"
        self._pretrained = "openai"

    def _load_model(self) -> bool:
        """
        Lazily load the CLIP model.

        Returns:
            True if model loaded successfully, False otherwise.
        """
        if self._model is not None:
            return True

        try:
            import open_clip
            import torch
            import os
            from core.config import get_settings

            settings = get_settings()
            # Enforce local-only mode if configured to prevent internet pings at runtime
            if settings.offline_mode:
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["TRANSFORMERS_OFFLINE"] = "1"

            logger.info(f"Loading CLIP model {self._model_name}/{self._pretrained}...")

            self._model, _, self._preprocess = open_clip.create_model_and_transforms(
                self._model_name, pretrained=self._pretrained
            )
            self._tokenizer = open_clip.get_tokenizer(self._model_name)

            # Use CPU to avoid GPU memory issues
            self._device = "cpu"
            self._model = self._model.to(self._device)
            self._model.eval()

            logger.info("CLIP model loaded successfully")
            return True

        except ImportError as e:
            logger.error(f"Failed to import CLIP dependencies: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to load CLIP model: {e}")
            return False

    def analyze_image(
        self,
        image_path: str,
        categories: Optional[list[str]] = None,
        check_concerns: bool = False,
    ) -> CLIPAnalysisResult:
        """
        Analyze an image using CLIP zero-shot classification.

        Args:
            image_path: Path to the image file
            categories: List of category descriptions to classify against.
                       Defaults to DEFAULT_IMAGE_CATEGORIES if not provided.
            check_concerns: Also check for contraband/concern categories

        Returns:
            CLIPAnalysisResult with classification results
        """
        if not self._load_model():
            return CLIPAnalysisResult(
                top_match="unknown",
                top_confidence=0.0,
                all_scores=[],
                concern_flag=False,
                available=False,
                error="CLIP model not available - dependencies missing",
            )

        try:
            import torch
            from PIL import Image as PILImage

            # Use default categories if none provided
            if categories is None:
                categories = self.DEFAULT_IMAGE_CATEGORIES.copy()

            # Add concern categories if requested
            if check_concerns:
                categories = categories + self.CONCERN_CATEGORIES

            # Load and preprocess image
            image = PILImage.open(image_path).convert("RGB")
            image_tensor = self._preprocess(image).unsqueeze(0).to(self._device)

            # Tokenize category descriptions
            text_tokens = self._tokenizer(categories).to(self._device)

            # Compute features
            with torch.no_grad():
                image_features = self._model.encode_image(image_tensor)
                text_features = self._model.encode_text(text_tokens)

                # Normalize features
                image_features = image_features / image_features.norm(
                    dim=-1, keepdim=True
                )
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)

                # Compute similarity scores
                similarities = (image_features @ text_features.T).squeeze(0)
                probs = similarities.softmax(dim=-1)

            # Convert to Python types
            scores = [
                (cat, float(prob)) for cat, prob in zip(categories, probs.tolist())
            ]
            scores.sort(key=lambda x: x[1], reverse=True)

            top_match, top_confidence = scores[0]

            # Check for concern flag if concern categories were included
            concern_flag = False
            if check_concerns:
                concern_scores = [
                    (cat, score)
                    for cat, score in scores
                    if cat in self.CONCERN_CATEGORIES
                ]
                if concern_scores:
                    top_concern, concern_score = max(concern_scores, key=lambda x: x[1])
                    # Flag if top concern is not "safe everyday object" and score is significantly
                    # above the mean concern score (relative threshold instead of absolute 0.4)
                    concern_mean = sum(s for _, s in concern_scores) / len(
                        concern_scores
                    )
                    if (
                        top_concern != "a safe everyday object"
                        and concern_score > concern_mean * 1.15
                    ):
                        concern_flag = True

            return CLIPAnalysisResult(
                top_match=top_match,
                top_confidence=round(top_confidence, 4),
                all_scores=[(cat, round(score, 4)) for cat, score in scores],
                concern_flag=concern_flag,
                available=True,
                embedding=image_features.cpu().numpy().flatten().tolist(),
            )

        except Exception as e:
            logger.error(f"CLIP analysis failed: {e}")
            return CLIPAnalysisResult(
                top_match="unknown",
                top_confidence=0.0,
                all_scores=[],
                concern_flag=False,
                available=False,
                error=str(e),
            )

    def get_image_type(self, image_path: str) -> str:
        """
        Get a simple image type classification.

        Args:
            image_path: Path to the image file

        Returns:
            String description of the image type
        """
        result = self.analyze_image(
            image_path, categories=self.DEFAULT_IMAGE_CATEGORIES
        )
        if result.available:
            return result.top_match
        return "unknown"


def get_clip_analyzer() -> CLIPImageAnalyzer:
    """
    Get the global singleton CLIP analyzer instance.

    Returns:
        CLIPImageAnalyzer singleton instance
    """
    global _clip_analyzer_instance
    if _clip_analyzer_instance is None:
        with _clip_lock:
            if _clip_analyzer_instance is None:
                _clip_analyzer_instance = CLIPImageAnalyzer()
    return _clip_analyzer_instance


def reset_clip_analyzer() -> None:
    """Reset the global singleton (useful for testing)."""
    global _clip_analyzer_instance
    _clip_analyzer_instance = None
