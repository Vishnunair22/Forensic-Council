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

Preferred path: schema-locked LLM responses already deliver the signals in
STRUCTURED per-class arrays (``manipulation_signals`` / ``ai_generation_signals``
/ ``editing_signals`` / ``compression_signals``) — ``classify_structured_signals``
and the ``structured_section`` argument of ``partition_manipulation_signals``
bucket those directly with no text scraping.

LEGACY fallback: substring keyword matching on a lowercased string, used ONLY
when no structured section is available or a signal is absent from it. A
signal that matches none of the buckets is reported as ``unknown`` so callers
can decide how conservatively to treat it (the local forensic ensemble treats
an unknown artifact as a real detection; a descriptive vision model does not).
"""

from __future__ import annotations

SignalClass = str  # "tampering" | "processing" | "ai_generation" | "unknown"

# Cap applied by consumers to any confidence derived from an LLM's own
# self-assessment: it is an UNCALIBRATED LLM SIGNAL (not a measured error
# rate) and must never outweigh deterministic tool evidence.
LLM_DERIVED_CONFIDENCE_CAP = 0.6

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
    # NB: only noise *inconsistency* is tampering. A high global "noise residual"
    # LEVEL is normal for real (esp. lossless) photos — keying tampering on the
    # bare phrase flagged every clean lossless image as SUSPICIOUS.
    "region tampering", "tamper", "forg", "fabricat",
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
    """LEGACY FALLBACK: keyword-bucket a single free-text signal string.

    Prefer ``classify_structured_signals`` / the ``structured_section`` argument
    of ``partition_manipulation_signals`` — schema-locked LLM responses carry
    the class directly, so this substring scrape runs only when the structured
    fields are unavailable or do not cover a signal.

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


# Structured field name → taxonomy bucket. Covers both the raw Gemini response
# section names and the VisualContext/ImageIntegrityContext model field names.
_STRUCTURED_FIELD_BUCKETS: tuple[tuple[str, str], ...] = (
    ("ai_generation_signals", "ai_generation"),
    ("manipulation_signals", "tampering"),
    ("visible_manipulation_signals", "tampering"),
    ("editing_signals", "processing"),
    ("editing_or_compositing_signals", "processing"),
    ("compression_signals", "processing"),
    ("compression_or_reupload_signals", "processing"),
)


def _structured_lookup(structured_section: dict | None) -> dict[str, SignalClass]:
    """Map normalized signal string → bucket from a structured LLM section."""
    lookup: dict[str, SignalClass] = {}
    if not isinstance(structured_section, dict):
        return lookup
    # ai_generation first so it wins ties (mirrors the legacy priority order).
    for field, bucket in _STRUCTURED_FIELD_BUCKETS:
        for item in structured_section.get(field) or []:
            key = str(item or "").strip().lower()
            if key and key not in lookup:
                lookup[key] = bucket
    return lookup


def classify_structured_signals(structured_section: dict | None) -> dict[str, list[str]]:
    """Partition a schema-locked LLM section directly from its structured fields.

    The model already classified each signal into a per-class array, so no
    text scraping is needed — this is the preferred path for any output
    produced under a responseSchema.
    """
    buckets: dict[str, list[str]] = {
        "tampering": [],
        "processing": [],
        "ai_generation": [],
        "unknown": [],
    }
    if not isinstance(structured_section, dict):
        return buckets
    for field, bucket in _STRUCTURED_FIELD_BUCKETS:
        for item in structured_section.get(field) or []:
            text = str(item or "").strip()
            if text and text not in buckets[bucket]:
                buckets[bucket].append(text)
    return buckets


def partition_manipulation_signals(
    signals: list[str] | None,
    structured_section: dict | None = None,
) -> dict[str, list[str]]:
    """Partition a list of signal strings into the four taxonomy buckets.

    When ``structured_section`` (a schema-locked LLM section carrying the
    per-class arrays) is provided, signals found there are bucketed by the
    model's own structured classification; the legacy keyword scrape applies
    ONLY to signals the structured fields do not cover.
    """
    buckets: dict[str, list[str]] = {
        "tampering": [],
        "processing": [],
        "ai_generation": [],
        "unknown": [],
    }
    lookup = _structured_lookup(structured_section)
    for signal in signals or []:
        if not signal:
            continue
        bucket = lookup.get(str(signal).strip().lower())
        if bucket is None:
            # LEGACY keyword fallback: structured parse did not cover this signal.
            bucket = classify_manipulation_signal(signal)
        buckets[bucket].append(signal)
    return buckets
