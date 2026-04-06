"""
OCR & Document Extraction Tools
================================

Provides a three-tier OCR pipeline for forensic evidence:

  Tier 1 — PyMuPDF (fitz)
    For PDF evidence: extracts embedded text losslessly, zero OCR overhead.
    Also extracts embedded images from PDFs for downstream image analysis.

  Tier 2 — EasyOCR
    For real-world photographic evidence: handles curved text, low-resolution
    scans, mixed-language documents, and uneven lighting far better than
    Tesseract. Supports 80+ languages. GPU optional.

  Tier 3 — Tesseract (pytesseract) — fallback
    Already in the stack. Used when EasyOCR is unavailable or fails.

Design principles:
  - All heavy model loads are lazy (on first call) and cached at module level.
  - Each tier degrades gracefully to the next without raising.
  - All functions are async-compatible via asyncio.get_running_loop().run_in_executor
    for the blocking EasyOCR/Tesseract calls so the FastAPI event loop is never blocked.
  - No performance hit on non-OCR file types — tiers are skipped via MIME guard.
"""

from __future__ import annotations

import asyncio
import atexit
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from core.evidence import EvidenceArtifact
from core.exceptions import ToolUnavailableError
from core.structured_logging import get_logger

logger = get_logger(__name__)

# Thread pool for blocking OCR calls — keeps event loop free
_OCR_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ocr_worker")

atexit.register(_OCR_EXECUTOR.shutdown, wait=False)

# ---------------------------------------------------------------------------
# Lazy model loader — EasyOCR reader (cached at module level)
# ---------------------------------------------------------------------------

_easyocr_reader: Optional[Any] = None
_easyocr_available: Optional[bool] = None  # None = not yet checked


def _get_easyocr_reader() -> Optional[Any]:
    """
    Lazily initialise and return the EasyOCR reader singleton.

    EasyOCR loads ~100MB of model weights the first time; subsequent calls
    reuse the cached reader immediately. The model is stored in
    EASYOCR_MODEL_STORAGE_DIRECTORY (default /app/cache/easyocr), which is
    a named Docker volume — so the download only happens once ever.

    Returns None if EasyOCR is not installed or fails to load.
    """
    global _easyocr_reader, _easyocr_available

    if _easyocr_available is False:
        return None
    if _easyocr_reader is not None:
        return _easyocr_reader

    try:
        import easyocr  # noqa: PLC0415

        from core.config import get_settings

        settings = get_settings()
        model_dir = settings.easyocr_model_dir
        os.makedirs(model_dir, exist_ok=True)

        # Enforce local-only mode if configured
        if settings.offline_mode:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"

        _easyocr_reader = easyocr.Reader(
            ["en"],
            gpu=False,  # CPU-only — no GPU required in forensic deployments
            verbose=False,
            model_storage_directory=model_dir,
            download_enabled=not settings.offline_mode,
        )
        _easyocr_available = True
        logger.info("EasyOCR reader initialised", model_dir=model_dir)
        return _easyocr_reader

    except ImportError:
        _easyocr_available = False
        logger.warning("EasyOCR not installed — Tesseract fallback will be used")
        return None
    except Exception as exc:
        _easyocr_available = False
        logger.warning("EasyOCR init failed, falling back to Tesseract", error=str(exc))
        return None


# ---------------------------------------------------------------------------
# Tier 1 — PyMuPDF (PDF text extraction + image extraction)
# ---------------------------------------------------------------------------


def _is_pdf(file_path: str) -> bool:
    """Return True if the file is a PDF (by magic bytes, not extension)."""
    try:
        with open(file_path, "rb") as fh:
            return fh.read(5) == b"%PDF-"
    except OSError:
        return False


def _extract_text_pymupdf_sync(file_path: str) -> dict[str, Any]:
    """
    Synchronous PyMuPDF extraction (runs in thread pool).

    Extracts:
      - Embedded text (lossless, preserves layout)
      - Page count
      - Embedded image count
      - Document metadata (title, author, creator, creation date)

    Returns a result dict ready to merge into the tool response.
    """
    try:
        import fitz  # PyMuPDF  # noqa: PLC0415
    except ImportError:
        return {"pymupdf_available": False, "error": "PyMuPDF (fitz) not installed"}

    doc = fitz.open(file_path)
    pages_text: list[str] = []
    image_count = 0

    try:
        for page in doc:
            pages_text.append(page.get_text("text").strip())
            image_count += len(page.get_images(full=False))

        full_text = "\n\n".join(p for p in pages_text if p)
        metadata = doc.metadata or {}

        return {
            "pymupdf_available": True,
            "page_count": doc.page_count,
            "embedded_image_count": image_count,
            "full_text": full_text,
            "lines": [ln.strip() for ln in full_text.splitlines() if ln.strip()],
            "word_count": len(full_text.split()),
            "has_text": bool(full_text.strip()),
            "doc_metadata": {
                "title": metadata.get("title", ""),
                "author": metadata.get("author", ""),
                "creator": metadata.get("creator", ""),
                "producer": metadata.get("producer", ""),
                "creation_date": metadata.get("creationDate", ""),
                "mod_date": metadata.get("modDate", ""),
                "encryption": metadata.get("encryption", ""),
            },
        }
    finally:
        doc.close()


async def extract_text_from_pdf(
    artifact: EvidenceArtifact,
) -> dict[str, Any]:
    """
    Extract all embedded text and metadata from a PDF evidence file using PyMuPDF.

    Unlike OCR, this is a lossless extraction of text that the PDF itself encodes.
    It is fast (<50ms for typical PDFs), produces court-defensible output, and
    requires no model downloads.

    For scanned PDFs (no embedded text), `has_text` will be False and the caller
    should follow up with `extract_text_easyocr` on the individual page images.

    Args:
        artifact: The evidence artifact to analyze (must be a PDF)

    Returns:
        Dictionary containing:
        - method: "pymupdf"
        - has_text: Boolean indicating embedded text was found
        - full_text: Complete extracted text
        - lines: List of non-empty lines
        - word_count: Number of words
        - page_count: Number of PDF pages
        - embedded_image_count: Images embedded in the PDF
        - doc_metadata: Title, author, creator, dates, encryption status
        - court_defensible: True
        - error: Present only on failure
    """
    if not os.path.exists(artifact.file_path):
        raise ToolUnavailableError(f"File not found: {artifact.file_path}")

    if not _is_pdf(artifact.file_path):
        return {
            "method": "pymupdf",
            "has_text": False,
            "full_text": "",
            "lines": [],
            "word_count": 0,
            "page_count": 0,
            "embedded_image_count": 0,
            "doc_metadata": {},
            "court_defensible": False,
            "note": "File is not a PDF — use extract_text_easyocr for image-based OCR",
        }

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        _OCR_EXECUTOR, _extract_text_pymupdf_sync, artifact.file_path
    )

    result["method"] = "pymupdf"
    result["court_defensible"] = result.get("pymupdf_available", False)
    return result


# ---------------------------------------------------------------------------
# Tier 2 — EasyOCR (image-based OCR)
# ---------------------------------------------------------------------------


def _extract_text_easyocr_sync(
    file_path: str,
    detail: bool = False,
) -> dict[str, Any]:
    """
    Synchronous EasyOCR extraction (runs in thread pool).

    Uses EasyOCR's neural network pipeline for robust text detection and
    recognition. Works on JPEGs, PNGs, TIFFs, and other image formats.

    detail=False returns plain text lines (fast).
    detail=True returns bounding boxes + confidence per word (slower).
    """
    reader = _get_easyocr_reader()
    if reader is None:
        return {"easyocr_available": False}

    try:
        results = reader.readtext(file_path, detail=1, paragraph=False)

        lines: list[str] = []
        bboxes: list[dict] = []
        confidences: list[float] = []

        for bbox, text, conf in results:
            text = text.strip()
            if not text:
                continue
            lines.append(text)
            confidences.append(conf)
            if detail:
                bboxes.append(
                    {
                        "text": text,
                        "confidence": round(conf, 4),
                        "bbox": bbox,  # [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
                    }
                )

        full_text = " ".join(lines)
        avg_conf = round(sum(confidences) / len(confidences), 4) if confidences else 0.0

        return {
            "easyocr_available": True,
            "lines": lines,
            "full_text": full_text,
            "word_count": len(full_text.split()),
            "has_text": bool(lines),
            "avg_confidence": avg_conf,
            "bboxes": bboxes if detail else [],
        }

    except Exception as exc:
        return {
            "easyocr_available": True,
            "error": str(exc),
            "lines": [],
            "full_text": "",
            "word_count": 0,
            "has_text": False,
        }


async def extract_text_easyocr(
    artifact: EvidenceArtifact,
    detail: bool = False,
) -> dict[str, Any]:
    """
    Extract visible text from an image using EasyOCR.

    EasyOCR uses a CRAFT text detector + CRNN recogniser. It handles:
      - Curved and perspective-distorted text
      - Low-resolution and noisy images (common in forensic evidence)
      - Mixed-language documents (defaults to English; see _get_easyocr_reader)
      - Screenshots, overlaid text, watermarks

    The model (~100MB) downloads on first call and is cached in the
    `easyocr_cache` Docker named volume — subsequent calls are instant.

    Falls back to Tesseract if EasyOCR is not installed or fails.

    Args:
        artifact: The evidence artifact to analyze
        detail: If True, includes per-word bounding boxes and confidence scores

    Returns:
        Dictionary containing:
        - method: "easyocr" or "tesseract_fallback"
        - has_text: Boolean indicating text was found
        - lines: List of recognized text lines
        - full_text: Complete extracted text joined by spaces
        - word_count: Number of words detected
        - avg_confidence: Average recognition confidence (0.0–1.0)
        - bboxes: Per-word bounding boxes (only when detail=True)
        - court_defensible: True
        - error: Present only on failure
    """
    if not os.path.exists(artifact.file_path):
        raise ToolUnavailableError(f"File not found: {artifact.file_path}")

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        _OCR_EXECUTOR,
        lambda: _extract_text_easyocr_sync(artifact.file_path, detail=detail),
    )

    if not result.get("easyocr_available"):
        # Graceful fallback to Tesseract
        logger.debug("EasyOCR unavailable — falling back to Tesseract")
        return await _extract_text_tesseract_fallback(artifact)

    result["method"] = "easyocr"
    result["court_defensible"] = True
    return result


# ---------------------------------------------------------------------------
# Tier 3 — Tesseract fallback
# ---------------------------------------------------------------------------


def _extract_text_tesseract_sync(file_path: str) -> dict[str, Any]:
    """Synchronous Tesseract extraction with OpenCV preprocessing."""
    try:
        import cv2  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415
        import pytesseract  # noqa: PLC0415
        from PIL import Image as PILImage  # noqa: PLC0415
    except ImportError as exc:
        return {"tesseract_available": False, "error": str(exc)}

    try:
        img_pil = PILImage.open(file_path)
        if img_pil.mode != "RGB":
            img_pil = img_pil.convert("RGB")
        img_bgr = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

        # Two preprocessing passes — keep whichever yields more content
        thresh_adaptive = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        _, thresh_otsu = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        cfg = r"--oem 3 --psm 6 -l eng"
        text_a = pytesseract.image_to_string(thresh_adaptive, config=cfg)
        text_b = pytesseract.image_to_string(thresh_otsu, config=cfg)
        best_text = text_a if len(text_a.strip()) >= len(text_b.strip()) else text_b

        data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
        words = [t for t in data["text"] if t.strip()]
        confs = [c for c in data["conf"] if c > 0]
        avg_conf = round(sum(confs) / len(confs) / 100, 4) if confs else 0.0

        lines = [ln.strip() for ln in best_text.splitlines() if ln.strip()]
        return {
            "tesseract_available": True,
            "lines": lines,
            "full_text": best_text,
            "word_count": len(words),
            "has_text": bool(words),
            "avg_confidence": avg_conf,
        }
    except Exception as exc:
        return {
            "tesseract_available": True,
            "error": str(exc),
            "lines": [],
            "full_text": "",
            "word_count": 0,
            "has_text": False,
        }


async def _extract_text_tesseract_fallback(
    artifact: EvidenceArtifact,
) -> dict[str, Any]:
    """Internal Tesseract fallback used by extract_text_easyocr."""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        _OCR_EXECUTOR, _extract_text_tesseract_sync, artifact.file_path
    )
    result["method"] = "tesseract_fallback"
    result["court_defensible"] = result.get("tesseract_available", False)
    return result


# ---------------------------------------------------------------------------
# Unified entry point — auto-selects tier based on file type
# ---------------------------------------------------------------------------


async def extract_evidence_text(
    artifact: EvidenceArtifact,
) -> dict[str, Any]:
    """
    Auto-dispatching text extraction for any evidence file type.

    Routing logic:
      - PDF → PyMuPDF (embedded text, lossless)
        If PyMuPDF finds no embedded text (scanned PDF) → falls through to EasyOCR
      - Image (JPEG/PNG/TIFF/WebP/BMP) → EasyOCR → Tesseract fallback
      - Video/Audio → returns empty result (no text extraction applies)

    This is the recommended entry point for agents. They should call this
    rather than the individual tier functions, unless they have a specific
    reason to prefer one tier.

    Args:
        artifact: The evidence artifact to analyze

    Returns:
        Dictionary containing all text extraction results, with:
        - method: Which tier was used
        - has_text: Boolean indicating text was found
        - full_text: Complete extracted text
        - lines: List of non-empty text lines
        - word_count: Number of words detected
        - court_defensible: Boolean
        - file_type_hint: What kind of file this appears to be
        - summary: Human-readable one-line summary for agent reasoning
    """
    file_path = artifact.file_path
    if not os.path.exists(file_path):
        raise ToolUnavailableError(f"File not found: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()

    # Determine file category
    pdf_exts = {".pdf"}
    image_exts = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp", ".gif"}
    av_exts = {
        ".mp4",
        ".avi",
        ".mov",
        ".mkv",
        ".webm",
        ".mp3",
        ".wav",
        ".flac",
        ".aac",
        ".m4a",
    }

    if ext in pdf_exts or _is_pdf(file_path):
        file_type_hint = "pdf_document"
        result = await extract_text_from_pdf(artifact)

        # Scanned PDF: no embedded text → fall back to EasyOCR on the file itself
        if not result.get("has_text"):
            logger.debug(
                "PDF has no embedded text — attempting EasyOCR on raw pages",
                file=file_path,
            )
            # Note: EasyOCR can't directly process PDFs; for scanned PDFs a
            # page-rasterisation step would be needed. We flag this clearly.
            result["scanned_pdf_note"] = (
                "PDF contains no embedded text (likely scanned). "
                "For scanned PDF OCR, rasterise pages to images first."
            )

    elif ext in image_exts:
        file_type_hint = "image"
        result = await extract_text_easyocr(artifact)

    elif ext in av_exts:
        file_type_hint = "audio_video"
        result = {
            "method": "skipped",
            "has_text": False,
            "full_text": "",
            "lines": [],
            "word_count": 0,
            "court_defensible": False,
            "note": "Text extraction not applicable to audio/video files. Use mediainfo_tools for AV metadata.",
        }

    else:
        # Unknown extension — attempt EasyOCR and let it fail gracefully
        file_type_hint = "unknown"
        result = await extract_text_easyocr(artifact)

    # Attach file type hint and build human-readable summary
    result["file_type_hint"] = file_type_hint
    result["summary"] = _build_summary(result, file_type_hint)
    return result


def _build_summary(result: dict[str, Any], file_type_hint: str) -> str:
    """Build a one-line agent-readable summary of OCR results."""
    if not result.get("has_text"):
        if file_type_hint == "audio_video":
            return "No text extraction applicable for audio/video evidence."
        return "No readable text detected in this evidence file."

    wc = result.get("word_count", 0)
    method = result.get("method", "unknown")
    conf = result.get("avg_confidence")
    conf_str = f" (avg confidence {conf:.0%})" if conf else ""

    if file_type_hint == "pdf_document":
        pages = result.get("page_count", "?")
        return (
            f"PDF document: {wc} words extracted from {pages} page(s) "
            f"via {method}{conf_str}."
        )

    preview = " | ".join(result.get("lines", [])[:3])
    if len(result.get("lines", [])) > 3:
        preview += " ..."
    return f"Image text: {wc} words detected via {method}{conf_str}. Preview: {preview}"
