"""
Florence-2 Vision Analyzer (Tier 3)
====================================
Wrapper around Microsoft Florence-2 for local image captioning.

Used as Tier 3 fallback when Gemini is unavailable — generates a natural
language description of image content using a tiny local VLM (0.23B params).

Requires: torch, transformers (available in Docker ml image, MIT license).

Usage:
    from tools.florence_analyzer import get_florence_analyzer
    analyzer = get_florence_analyzer()
    result = analyzer.analyze("path/to/image.jpg")
    print(result.detailed_caption)  # "A screenshot of a Gmail login page..."
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from core.structured_logging import get_logger

logger = get_logger(__name__)

_florence_instance: FlorenceAnalyzer | None = None
_florence_lock = threading.Lock()


@dataclass
class FlorenceResult:
    caption: str
    detailed_caption: str
    available: bool
    error: str | None = None

    def best_description(self) -> str:
        return self.detailed_caption or self.caption or ""


class FlorenceAnalyzer:
    """Singleton analyzer wrapping Microsoft Florence-2."""

    def __init__(self, model_name: str = "microsoft/Florence-2-base") -> None:
        self._model = None
        self._processor = None
        self._device = None
        self._available = False
        self._model_name = model_name
        self._loaded = False

    @property
    def available(self) -> bool:
        return self._available

    def _load(self) -> bool:
        if self._loaded:
            return self._available
        self._loaded = True
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoProcessor

            from core.model_guard import guarded_load

            self._device = "cuda" if torch.cuda.is_available() else "cpu"

            # Memory-guard + serialise the load. On a constrained container this
            # raises ModelMemoryError (caught below → unavailable) rather than
            # risking an OOM SIGKILL that would crash the whole process.
            from core.config import get_settings
            _offline = get_settings().offline_mode

            with guarded_load("florence2"):
                self._processor = AutoProcessor.from_pretrained(
                    self._model_name,
                    trust_remote_code=True,
                    local_files_only=_offline,
                )
                self._model = AutoModelForCausalLM.from_pretrained(
                    self._model_name,
                    trust_remote_code=True,
                    attn_implementation="eager",
                    local_files_only=_offline,
                ).to(self._device)
            self._model.eval()
            self._available = True
            logger.info(
                f"Florence-2 loaded ({self._model_name}) on {self._device}"
            )
            return True
        except Exception as e:
            logger.warning(f"Florence-2 load failed: {e}")
            return False

    def analyze(self, image_path: str) -> FlorenceResult:
        """Run Florence-2 captioning on an image file."""
        if not self._load():
            return FlorenceResult(
                caption="",
                detailed_caption="",
                available=False,
                error="Florence-2 model not available",
            )

        try:
            from PIL import Image

            from core.model_guard import cap_image_dimension

            image = cap_image_dimension(Image.open(image_path).convert("RGB"))
            caption = self._run_task("<CAPTION>", image)
            detailed = self._run_task("<DETAILED_CAPTION>", image)
            return FlorenceResult(
                caption=caption,
                detailed_caption=detailed,
                available=True,
            )
        except Exception as e:
            return FlorenceResult(
                caption="",
                detailed_caption="",
                available=False,
                error=str(e),
            )

    def _run_task(self, task_prompt: str, image) -> str:
        import torch
        inputs = self._processor(
            text=task_prompt, images=image, return_tensors="pt"
        )
        inputs = {k: v.to(self._device) if isinstance(v, torch.Tensor) else v for k, v in inputs.items()}

        with torch.no_grad():
            generated_ids = self._model.generate(
                input_ids=inputs["input_ids"],
                pixel_values=inputs["pixel_values"],
                max_new_tokens=512,
                num_beams=3,
                use_cache=False,
            )

        generated_text = self._processor.batch_decode(
            generated_ids, skip_special_tokens=False
        )[0]

        parsed = self._processor.post_process_generation(
            generated_text,
            task=task_prompt,
            image_size=(image.width, image.height),
        )

        result = parsed.get(task_prompt, "")
        return result.strip() if result else ""


def get_florence_analyzer() -> FlorenceAnalyzer:
    """Get the global singleton Florence-2 analyzer instance."""
    global _florence_instance
    if _florence_instance is None:
        with _florence_lock:
            if _florence_instance is None:
                _florence_instance = FlorenceAnalyzer()
    return _florence_instance


def reset_florence_analyzer() -> None:
    """Reset the global singleton (useful for testing)."""
    global _florence_instance
    _florence_instance = None
