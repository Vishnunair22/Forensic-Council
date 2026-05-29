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

import hashlib
import threading
from dataclasses import dataclass
from typing import Any

from core.structured_logging import get_logger

logger = get_logger(__name__)

# Global singleton instance with thread-safe lock
_clip_analyzer_instance: CLIPImageAnalyzer | None = None
_clip_lock = threading.Lock()


@dataclass
class CLIPAnalysisResult:
    """Result from CLIP image analysis."""

    top_match: str
    top_confidence: float
    all_scores: list[tuple[str, float]]
    concern_flag: bool
    available: bool
    embedding: list[float] | None = None
    error: str | None = None


CASCADE_MODELS = [
    ("clip", "OpenCLIP ViT-B-32"),
    ("vit", "torchvision ViT-B-16"),
    ("efficientnet", "torchvision EfficientNet-B0"),
    ("resnet", "torchvision ResNet-18"),
]


class ImageClassifierBase:
    """Abstract base for any image classifier in the cascade."""

    name: str = "base"
    available: bool = False

    def analyze_image(
        self, image_path: str, categories: list[str] | None = None
    ) -> CLIPAnalysisResult:
        raise NotImplementedError


class TorchVisionClassifier(ImageClassifierBase):
    """
    Lightweight torchvision classifier (ViT, EfficientNet, or ResNet).

    Uses the model's own ImageNet prediction as the "top match" and
    extracts the feature embedding for fingerprint generation.
    Does NOT support zero-shot text categories — only predicts
    ImageNet class indices.
    """

    def __init__(self, model_type: str):
        self.name = model_type
        self.available = False
        self._model = None
        self._preprocess = None
        self._device = None
        self._imagenet_labels: list[str] | None = None

    def _load(self) -> bool:
        import torch

        try:
            import torchvision.models as tv_models
            from torchvision import transforms
        except ImportError:
            return False

        try:
            from core.config import get_settings

            self._device = torch.device("cpu")

            if self.name == "vit":
                weights = tv_models.ViT_B_16_Weights.IMAGENET1K_V1
                self._model = tv_models.vit_b_16(weights=weights)
                self._preprocess = weights.transforms()
            elif self.name == "efficientnet":
                weights = tv_models.EfficientNet_B0_Weights.IMAGENET1K_V1
                self._model = tv_models.efficientnet_b0(weights=weights)
                self._preprocess = weights.transforms()
            elif self.name == "resnet":
                weights = tv_models.ResNet18_Weights.IMAGENET1K_V1
                self._model = tv_models.resnet18(weights=weights)
                self._preprocess = weights.transforms()
            else:
                return False

            self._model = self._model.to(self._device)
            self._model.eval()

            # Load ImageNet labels
            self._imagenet_labels = _load_imagenet_labels()
            self.available = True
            logger.info(f"Loaded {self.name} classifier")
            return True

        except Exception as exc:
            logger.debug(f"Failed to load {self.name} classifier: {exc}")
            return False

    def analyze_image(
        self, image_path: str, categories: list[str] | None = None
    ) -> CLIPAnalysisResult:
        if not self.available:
            return CLIPAnalysisResult(
                top_match="unknown",
                top_confidence=0.0,
                all_scores=[],
                concern_flag=False,
                available=False,
                error=f"{self.name} not available",
            )

        import torch
        from PIL import Image as PILImage

        try:
            image = PILImage.open(image_path).convert("RGB")
            tensor = self._preprocess(image).unsqueeze(0).to(self._device)

            with torch.no_grad():
                output = self._model(tensor)
                probs = torch.nn.functional.softmax(output, dim=1)
                top5_idx = probs.topk(5).indices[0].tolist()
                top5_probs = probs.topk(5).values[0].tolist()

            scores = []
            for idx, prob in zip(top5_idx, top5_probs):
                label = self._imagenet_labels[idx] if self._imagenet_labels and idx < len(self._imagenet_labels) else f"class_{idx}"
                scores.append((label, round(float(prob), 4)))

            return CLIPAnalysisResult(
                top_match=scores[0][0] if scores else "unknown",
                top_confidence=scores[0][1] if scores else 0.0,
                all_scores=scores,
                concern_flag=False,
                available=True,
                embedding=output.cpu().numpy().flatten().tolist()[:512],
            )

        except Exception as exc:
            return CLIPAnalysisResult(
                top_match="unknown",
                top_confidence=0.0,
                all_scores=[],
                concern_flag=False,
                available=False,
                error=str(exc),
            )


def _load_imagenet_labels() -> list[str] | None:
    """Load ImageNet class labels."""
    try:
        import urllib.request

        url = "https://raw.githubusercontent.com/pytorch/hub/master/imagenet_classes.txt"
        with urllib.request.urlopen(url, timeout=5) as f:
            return [line.decode("utf-8").strip() for line in f.readlines()]
    except Exception:
        return None


class CLIPImageAnalyzer:
    """
    Singleton CLIP image analyzer for zero-shot image classification.

    Implements multi-tier cascade: CLIP → ViT → EfficientNet → ResNet.
    Each tier is attempted lazily; the first available model is used.
    This ensures forensic analysis proceeds even when CLIP or PyTorch
    are partially installed.
    """

    def __init__(self):
        """Initialize analyzer (does not load model yet)."""
        self._model = None
        self._preprocess = None
        self._tokenizer = None
        self._device = None
        self._model_name = "unknown"
        self._pretrained = "openai"
        self._fallback_classifiers: list[TorchVisionClassifier] = []
        self._active_model_name: str = "none"

    @property
    def available(self) -> bool:
        """Check if any classifier is available."""
        return self._model is not None or any(c.available for c in self._fallback_classifiers)

    # Default forensic-relevant image categories
    # Weapon/contraband categories are listed first to ensure they are prioritized
    # in zero-shot classification — critical for forensic evidence screening.
    DEFAULT_IMAGE_CATEGORIES = [
        # Weapons / contraband (highest priority)
        "a photograph of a weapon or knife",
        "a photograph of a firearm or gun",
        "a photograph of ammunition or bullets",
        # Screen captures
        "a screenshot of a document",
        "a screenshot of a chat conversation",
        "a screenshot of a mobile phone screen",
        "a screenshot of a desktop application",
        "a screenshot of a web browser",
        # Camera/phone photos
        "an outdoor photograph taken with a camera",
        "an indoor photograph taken with a camera",
        "a portrait photograph of a person or face",
        "a photograph of a crowd or public gathering",
        "a nighttime or low-light photograph",
        "a close-up photograph of an object or item",
        "a photograph of a street scene or cityscape",
        "a photograph of a vehicle or car",
        "a photograph of a building or structure",
        # Crime / forensic
        "a crime scene photograph",
        "a forensic evidence photograph",
        "a surveillance camera frame",
        # Documents / handwritten
        "a scanned handwritten document or note",
        "a printed document or form",
        "a passport or identification document",
        "a receipt or invoice",
        "a handwritten letter or message",
        # Object-focused
        "a photograph of a vehicle",
        # AI / synthetic
        "a digitally generated or AI-generated image",
        "a social media post",
        "a news article image",
        "a medical or scientific imaging scan",
        "a product or commercial image",
        "a scanned photograph or printed photo",
    ]

    # Categories for contraband/concern detection
    CONCERN_CATEGORIES = [
        "a firearm or gun",
        "a knife or bladed weapon",
        "an explosive device or bomb",
        "drug paraphernalia or controlled substances",
        "a safe everyday object",
        "a person or face",
        "a vehicle or car",
        "a crime scene",
        "blood or bodily injury",
        "currency or cash",
        "a document or ID card",
    ]

    def _load_model(self) -> bool:
        """
        Lazily load the best available model via multi-tier cascade.

        Cascade order: CLIP (zero-shot) → ViT → EfficientNet → ResNet.
        Each tier is tried only if the previous one fails.
        """
        if self._model is not None:
            return True

        # Tier 1: OpenCLIP (full zero-shot semantic understanding)
        if self._try_load_clip():
            self._active_model_name = f"clip_{self._model_name}"
            return True

        # Tier 2-4: torchvision classifiers (ImageNet prediction only)
        for model_type in ("vit", "efficientnet", "resnet"):
            classifier = TorchVisionClassifier(model_type)
            if classifier._load():
                self._fallback_classifiers.append(classifier)
                self._active_model_name = model_type
                logger.info(f"CLIP cascade using {model_type} as active classifier")
                return True

        logger.error("All CLIP cascade models failed to load")
        return False

    def _try_load_clip(self) -> bool:
        """
        Try to load the OpenCLIP model.

        Returns:
            True if CLIP model loaded successfully, False otherwise.
        """
        try:
            import os

            import open_clip

            from core.config import get_settings

            settings = get_settings()
            # Enforce local-only mode if configured to prevent internet pings at runtime
            if settings.offline_mode:
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["TRANSFORMERS_OFFLINE"] = "1"

            # Fetch SOTA model name from settings
            self._model_name = settings.siglip_model_name
            # Handle both open_clip names and HuggingFace hub names
            _pretrained = "webli" if "siglip" in self._model_name.lower() else self._pretrained
            if "/" in self._model_name:  # Handle HF names like "google/siglip-..."
                _pretrained = "hf-hub"

            logger.info(f"Loading Vision-Language model {self._model_name}...")

            self._model, _, self._preprocess = open_clip.create_model_and_transforms(
                self._model_name,
                pretrained=_pretrained,
                cache_dir=os.path.join(settings.hf_home, "open_clip"),
            )
            self._tokenizer = open_clip.get_tokenizer(self._model_name)

            # Use CPU to avoid GPU memory issues
            self._device = "cpu"
            self._model = self._model.to(self._device)
            self._model.eval()

            logger.info("CLIP model loaded successfully")
            return True

        except ImportError as e:
            logger.debug(f"CLIP dependencies unavailable: {e}")
            return False
        except Exception as e:
            logger.debug(f"Failed to load CLIP model: {e}")
            return False

    def analyze_image(
        self,
        image_path: str,
        categories: list[str] | None = None,
        check_concerns: bool = False,
    ) -> CLIPAnalysisResult:
        """
        Analyze an image using the best available classifier.

        Cascade: CLIP (zero-shot) → ViT → EfficientNet → ResNet.
        Falls through tiers until one succeeds.

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
                error="All cascade models unavailable",
            )

        # If a fallback classifier is active, delegate to it
        if self._model is None and self._fallback_classifiers:
            classifier = self._fallback_classifiers[0]
            return classifier.analyze_image(image_path, categories)

        # CLIP path
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
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)

                # Compute similarity scores
                similarities = (image_features @ text_features.T).squeeze(0)
                probs = similarities.softmax(dim=-1)

            # Convert to Python types
            scores = [
                (cat, float(prob)) for cat, prob in zip(categories, probs.tolist(), strict=False)
            ]
            scores.sort(key=lambda x: x[1], reverse=True)

            top_match, top_confidence = scores[0]

            # Check for concern flag if concern categories were included
            concern_flag = False
            if check_concerns:
                concern_scores = [
                    (cat, score) for cat, score in scores if cat in self.CONCERN_CATEGORIES
                ]
                if concern_scores:
                    top_concern, concern_score = max(concern_scores, key=lambda x: x[1])
                    concern_mean = sum(s for _, s in concern_scores) / len(concern_scores)
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
            # Fall through to cascade classifiers
            if self._fallback_classifiers:
                logger.info("Falling back to cascade classifier")
                return self._fallback_classifiers[0].analyze_image(image_path, categories)
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
        result = self.analyze_image(image_path, categories=self.DEFAULT_IMAGE_CATEGORIES)
        if result.available:
            return result.top_match
        return "unknown"

    def generate_fingerprint(self, image_path: str, projection_dims: int = 64) -> dict[str, Any]:
        """
        Generate a deterministic neural perceptual fingerprint from the image embedding.

        The analyzer already computes a normalized vision embedding for semantic
        classification.  This method reuses that embedding, quantizes its first
        dimensions into a compact bit signature, and includes a SHA-256 digest of
        the quantized vector for stable storage/comparison.
        """
        result = self.analyze_image(image_path, categories=self.DEFAULT_IMAGE_CATEGORIES)
        if not result.available or not result.embedding:
            return {
                "available": False,
                "error": result.error or "embedding unavailable",
                "method": "clip_embedding_projection",
            }

        embedding = result.embedding
        dims = max(8, min(projection_dims, len(embedding)))
        projection = embedding[:dims]

        # Quantize to signed 16-bit buckets so tiny floating-point differences
        # do not produce wildly different fingerprints across CPU/library builds.
        quantized = [max(-32768, min(32767, int(round(value * 1000)))) for value in projection]
        bitstring = "".join("1" if value >= 0 else "0" for value in quantized)
        digest_input = ",".join(str(value) for value in quantized).encode("ascii")

        return {
            "available": True,
            "method": "clip_embedding_projection",
            "model": self._model_name,
            "pretrained": self._pretrained,
            "dimensions": len(embedding),
            "projection_dimensions": dims,
            "bit_fingerprint": bitstring,
            "sha256": hashlib.sha256(digest_input).hexdigest(),
            "projection": quantized,
            "top_match": result.top_match,
            "top_confidence": result.top_confidence,
        }


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
