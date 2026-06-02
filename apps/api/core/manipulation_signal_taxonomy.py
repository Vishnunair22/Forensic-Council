"""Deterministic taxonomy for visual "manipulation" signals.

Vision models and the local ensemble both emit free-text signal strings, but
they mix three fundamentally different axes that must NOT be collapsed into a
single "manipulation" verdict:

  - processing      : benign editing / packaging that does not imply deception
                      (background removed, cropped, re-saved, recompressed,
                      resized, watermarked, screenshot, color adjusted).
  - tampering       : signals consistent with deceptive alteration
                      (splice, clone, copy-move, inpaint, ELA/DCT/noise
                      inconsistency, inconsistent shadows/lighting, warping).
  - ai_generation   : signals consistent with synthetic/generated content
                      (GAN/diffusion artifacts, deepfake).

Classification is substring keyword matching on a lowercased string. A signal
that matches none of the buckets is reported as ``unknown`` so callers can
decide how conservatively to treat it (the local forensic ensemble treats an
unknown artifact as a real detection; a descriptive vision model does not).
"""

from __future__ import annotations

SignalClass = str  # "tampering" | "processing" | "ai_generation" | "unknown"

_AI_GENERATION_KEYWORDS = (
    "ai-generated", "ai generated", "ai-gen", "ai gen", "synthetic",
    "deepfake", "deep fake", "gan ", "gan-", "stylegan", "diffusion",
    "midjourney", "stable diffusion", "dall-e", "dalle", "generative",
    "neural generation", "machine-generated", "machine generated",
)

_TAMPERING_KEYWORDS = (
    "splice", "splic", "clone", "clonin", "copy-move", "copy move",
    "inpaint", "in-paint", "warp", "ghost", "double exposure",
    "ela anomaly", "ela hotspot", "error level", "dct", "quantization",
    "noise inconsistency", "noise inconsist", "sensor noise inconsist",
    "noise residual", "region tampering", "tamper", "forg", "fabricat",
    "manipulat", "resampl", "seam", "splice boundary", "altered region",
    "edited region", "inconsistent shadow", "inconsistent light",
    "inconsistent reflection", "inconsistent perspective",
    "perspective inconsist", "depth-of-field inconsist",
    "depth of field inconsist", "composit", "inserted object",
    "object inserted", "digitally inserted", "doctored", "photoshopp",
)

_PROCESSING_KEYWORDS = (
    "background removed", "background removal", "background has been removed",
    "transparent background", "checkerboard", "extracted from",
    "extracted onto", "isolated against", "isolated on", "cutout",
    "cut-out", "cut out", "crop", "resized", "resize", "downscal",
    "upscal", "rescal", "re-saved", "resaved", "re-save", "recompress",
    "re-compress", "recompression", "re-compression", "jpeg recompression",
    "filter applied", "color adjust", "color correct", "color grad",
    "saturation", "brightness", "contrast adjust", "watermark", "rotat",
    "exif strip", "metadata strip", "metadata removed", "screenshot",
    "screen capture", "retouch", "beautif",
)


def classify_manipulation_signal(signal: str) -> SignalClass:
    """Return the taxonomy bucket for a single signal string.

    Priority: ai_generation > tampering > processing > unknown. Tampering is
    checked before processing so a phrase that mentions both (e.g. "background
    spliced in") is treated as the more severe class.
    """
    s = (signal or "").strip().lower()
    if not s:
        return "unknown"
    if any(k in s for k in _AI_GENERATION_KEYWORDS):
        return "ai_generation"
    if any(k in s for k in _TAMPERING_KEYWORDS):
        return "tampering"
    if any(k in s for k in _PROCESSING_KEYWORDS):
        return "processing"
    return "unknown"


def partition_manipulation_signals(
    signals: list[str] | None,
) -> dict[str, list[str]]:
    """Partition a list of signal strings into the four taxonomy buckets."""
    buckets: dict[str, list[str]] = {
        "tampering": [],
        "processing": [],
        "ai_generation": [],
        "unknown": [],
    }
    for signal in signals or []:
        if not signal:
            continue
        buckets[classify_manipulation_signal(signal)].append(signal)
    return buckets
