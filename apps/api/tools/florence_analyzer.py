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


def _legacy_cache_prepare_inputs(
    self,
    decoder_input_ids,
    past_key_values=None,
    attention_mask=None,
    decoder_attention_mask=None,
    head_mask=None,
    decoder_head_mask=None,
    cross_attn_head_mask=None,
    use_cache=None,
    encoder_outputs=None,
    **kwargs,
):
    """Drop-in replacement for the vendored Florence-2 language model's
    ``prepare_inputs_for_generation``.

    The vendored modeling code is written entirely against the legacy
    tuple-of-tuples KV-cache format, but transformers >=4.44 seeds
    ``generate()`` with a modern ``Cache`` object — so the original method
    crashes on ``past_key_values[0][0].shape`` and the model is forced to run
    with ``use_cache=False`` (O(n^2) decode, ~1s/token on CPU). Converting the
    Cache back to the legacy tuple at this boundary lets the unmodified
    attention code use the KV cache again — ~4x faster decode, identical output.
    """
    from transformers.cache_utils import Cache

    if isinstance(past_key_values, Cache):
        seq_len = past_key_values.get_seq_length()
        past_key_values = past_key_values.to_legacy_cache() if seq_len else None

    past_length = past_key_values[0][0].shape[2] if past_key_values is not None else 0
    if past_length:
        if decoder_input_ids.shape[1] > past_length:
            decoder_input_ids = decoder_input_ids[:, past_length:]
        else:
            decoder_input_ids = decoder_input_ids[:, -1:]

    return {
        "input_ids": None,
        "encoder_outputs": encoder_outputs,
        "past_key_values": past_key_values,
        "decoder_input_ids": decoder_input_ids,
        "attention_mask": attention_mask,
        "decoder_attention_mask": decoder_attention_mask,
        "head_mask": head_mask,
        "decoder_head_mask": decoder_head_mask,
        "cross_attn_head_mask": cross_attn_head_mask,
        "use_cache": use_cache,
    }


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
        self._cache_patched = False
        self._quantized = False

    @property
    def available(self) -> bool:
        return self._available

    def ensure_loaded(self) -> bool:
        """Public pre-warm entry point — load the model now (e.g. at worker boot)
        so the first investigation doesn't pay a cold load inside the ensemble's
        concurrent tool budget (where it silently timed out). Returns availability."""
        return self._load()

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

            # Re-enable the KV cache by converting the modern Cache object back to
            # the legacy tuple format the vendored attention code expects (see
            # _legacy_cache_prepare_inputs). This is what makes use_cache=True in
            # _run_task viable — without it generation crashes and falls back to
            # the ~5x slower no-cache path.
            import types

            lang_model = getattr(self._model, "language_model", None)
            if lang_model is not None:
                lang_model.prepare_inputs_for_generation = types.MethodType(
                    _legacy_cache_prepare_inputs, lang_model
                )
                self._cache_patched = True

            # int8 dynamic quantization of the Linear layers — CPU only, ~1.5x
            # faster decode with negligible caption-quality change. No-op/awkward
            # on CUDA, so gate on CPU. Best-effort: a quant failure must not make
            # the captioner unavailable.
            if self._device == "cpu":
                try:
                    self._model = torch.quantization.quantize_dynamic(
                        self._model, {torch.nn.Linear}, dtype=torch.qint8
                    )
                    qlm = getattr(self._model, "language_model", None)
                    if qlm is not None:
                        qlm.prepare_inputs_for_generation = types.MethodType(
                            _legacy_cache_prepare_inputs, qlm
                        )
                    self._quantized = True
                except Exception as qe:
                    logger.warning(f"Florence-2 dynamic quantization skipped: {qe}")

            self._available = True
            logger.info(
                "Florence-2 loaded "
                f"({self._model_name}) on {self._device} "
                f"[kv_cache={getattr(self, '_cache_patched', False)} "
                f"quantized={getattr(self, '_quantized', False)}]"
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
            # Run ONLY the detailed caption: it is the richest read and the one used
            # for the on-device description, and skipping the plain <CAPTION> pass
            # halves CPU inference time so Florence fits inside the ensemble's
            # concurrent tool budget instead of timing out and being dropped.
            detailed = self._run_task("<DETAILED_CAPTION>", image)
            return FlorenceResult(
                caption=detailed,
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
                # Greedy (num_beams=1) is ~30% faster than beam search here with
                # equal/better detail; detailed captions self-terminate well under
                # 256 tokens so the cap only bounds pathological runs; use_cache=True
                # is the dominant win (~4x), enabled by _legacy_cache_prepare_inputs.
                max_new_tokens=256,
                num_beams=1,
                use_cache=True,
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
