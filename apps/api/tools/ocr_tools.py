"""
OCR Forensic Tools
==================

Real forensic tool handlers for OCR and text extraction.
Implements a three-tier pipeline:
1. PyMuPDF (Tier 1) — Fast, lossless embedded text extraction for PDFs.
2. EasyOCR (Tier 2) — Robust neural OCR for scanned documents and images.
3. Tesseract (Tier 3) — Fast, deterministic fallback OCR.
"""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from core.evidence import EvidenceArtifact
from core.exceptions import ToolUnavailableError
from core.structured_logging import get_logger

logger = get_logger(__name__)

# Shared executor for CPU-bound OCR tasks to avoid blocking the event loop
_OCR_EXECUTOR = ThreadPoolExecutor(max_workers=min(32, (os.cpu_count() or 1) * 4))

# Thread-local storage for EasyOCR readers to avoid re-init overhead
_EASYOCR_READER = None


def _get_easyocr_reader():
    """Get or initialize the EasyOCR reader (cached in thread pool)."""
    global _EASYOCR_READER
    if _EASYOCR_READER is None:
        try:
            import easyocr  # noqa: PLC0415

            model_dir = os.getenv("EASYOCR_MODEL_DIR", "/app/cache/easyocr")
            os.makedirs(model_dir, exist_ok=True)
            os.environ.setdefault("HOME", model_dir)
            _EASYOCR_READER = easyocr.Reader(
                ["en"],
                gpu=False,
                model_storage_directory=model_dir,
                user_network_directory=model_dir,
                download_enabled=True,
            )
        except (ImportError, Exception) as exc:
            logger.warning(f"EasyOCR initialization failed: {str(exc)}")
            return None
    return _EASYOCR_READER


def _is_pdf(file_path: str) -> bool:
    """Check if file is a PDF via magic bytes."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(5)
            return header == b"%PDF-"
    except Exception:
        return False


def _file_type_hint(artifact: EvidenceArtifact) -> str:
    """Return a coarse file-type hint for OCR routing."""
    file_path = str(getattr(artifact, "file_path", "") or "").lower()
    mime = str(getattr(artifact, "mime_type", "") or "").lower()
    ext = os.path.splitext(file_path)[1]
    if _is_pdf(file_path) or mime == "application/pdf" or ext == ".pdf":
        return "pdf_document"
    if mime.startswith("image/") or ext in {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".bmp",
        ".tif",
        ".tiff",
    }:
        return "image"
    if mime.startswith(("audio/", "video/")) or ext in {
        ".wav",
        ".mp3",
        ".m4a",
        ".flac",
        ".mp4",
        ".mov",
        ".avi",
        ".mkv",
        ".webm",
    }:
        return "audio_video"
    return "unknown"


def _build_summary(result: dict[str, Any], file_type_hint: str) -> str:
    """Build a compact OCR summary for reports and tests."""
    word_count = int(result.get("word_count") or 0)
    method = str(result.get("method") or "ocr")
    if file_type_hint == "pdf_document":
        page_count = int(result.get("page_count") or 0)
        return f"PDF document: {word_count} words via {method}; {page_count} page(s)."
    if file_type_hint == "image":
        confidence = result.get("avg_confidence", result.get("confidence", 0.0)) or 0.0
        try:
            confidence_pct = int(round(float(confidence) * 100))
        except (TypeError, ValueError):
            confidence_pct = 0
        lines = [str(line) for line in result.get("lines", []) if str(line).strip()]
        preview = ""
        if lines:
            preview = " Preview: " + " | ".join(lines[:3])
            if len(lines) > 3:
                preview += " ..."
        return (
            f"Image text: {word_count} words via {method} ({confidence_pct}% confidence).{preview}"
        )
    if file_type_hint == "audio_video":
        return "Audio/video file: OCR skipped; no static image text layer to extract."
    return f"OCR text extraction: {word_count} words via {method}."


def _finalize_result(result: dict[str, Any], file_type_hint: str) -> dict[str, Any]:
    result["file_type_hint"] = file_type_hint
    result["summary"] = _build_summary(result, file_type_hint)
    return result


# ---------------------------------------------------------------------------
# Tier 1 — PyMuPDF (lossless document extraction)
# ---------------------------------------------------------------------------


def _extract_text_pymupdf_sync(file_path: str) -> dict[str, Any]:
    """
    Synchronous PyMuPDF extraction (runs in thread pool).

    Extracts embedded text, font metadata, and images from PDF without OCR.
    """
    try:
        doc = fitz.open(file_path)
    except Exception as exc:
        return {"pymupdf_available": False, "error": str(exc)}

    pages_text: list[str] = []
    image_count = 0

    try:
        for page in doc:
            # Extract plain text for simplicity and performance as Tier 1
            text = str(page.get_text("text")).strip()
            if text:
                pages_text.append(text)
            image_count += len(page.get_images(full=False))

        full_text = "\n\n".join(pages_text)
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
            lines.append(str(text))
            confidences.append(float(conf))
            if detail:
                bboxes.append(
                    {
                        "text": text,
                        "confidence": round(float(conf), 4),
                        "bbox": bbox,  # [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
                    }
                )

        full_text = " ".join(lines)
        avg_conf = round(float(sum(confidences)) / len(confidences), 4) if confidences else 0.0

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
        _, thresh_otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        cfg = r"--oem 3 --psm 6 -l eng"
        text_a = pytesseract.image_to_string(thresh_adaptive, config=cfg)
        text_b = pytesseract.image_to_string(thresh_otsu, config=cfg)
        best_text = text_a if len(text_a.strip()) >= len(text_b.strip()) else text_b

        data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
        words = [t for t in data["text"] if t and str(t).strip()]
        confs = [c for c in data["conf"] if c > 0]
        avg_conf = round(sum(confs) / len(confs) / 100, 4) if confs else 0.0

        return {
            "tesseract_available": True,
            "lines": [ln.strip() for ln in best_text.splitlines() if ln.strip()],
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


async def _extract_evidence_text_legacy_unused(
    artifact: EvidenceArtifact,
) -> dict[str, Any]:
    """
    Auto-dispatching text extraction for any evidence file type.
    """
    # PDF → PyMuPDF (embedded text)
    if _is_pdf(artifact.file_path):
        result = await extract_text_from_pdf(artifact)
        if result.get("has_text"):
            return result
        # Fall through to EasyOCR for scanned PDFs
        logger.info("PDF has no embedded text — falling back to OCR")

    # All images and scanned PDFs → EasyOCR
    if is_screen_capture_like(artifact):
        result = await _extract_text_tesseract_fallback(artifact)
        result["screen_capture_fast_path"] = True
        result.setdefault(
            "note",
            "Screen-capture-like image processed with fast OCR path.",
        )
        return result

    return await extract_text_easyocr(artifact)


async def extract_evidence_text(
    artifact: EvidenceArtifact,
) -> dict[str, Any]:
    """Auto-dispatching text extraction for any evidence file type."""
    file_type_hint = _file_type_hint(artifact)

    if file_type_hint == "audio_video":
        return _finalize_result(
            {
                "method": "skipped",
                "has_text": False,
                "full_text": "",
                "lines": [],
                "word_count": 0,
                "court_defensible": True,
                "note": "OCR is not applicable to audio/video evidence.",
            },
            file_type_hint,
        )

    if file_type_hint == "pdf_document":
        result = await extract_text_from_pdf(artifact)
        if result.get("has_text"):
            return _finalize_result(result, file_type_hint)
        result.setdefault(
            "scanned_pdf_note",
            "PDF has no embedded text; rasterise pages before image OCR.",
        )
        return _finalize_result(result, file_type_hint)

    if is_screen_capture_like(artifact):
        result = await _extract_text_tesseract_fallback(artifact)
        result["screen_capture_fast_path"] = True
        result.setdefault(
            "note",
            "Screen-capture-like image processed with fast OCR path.",
        )
        return _finalize_result(result, "image")

    result = await extract_text_easyocr(artifact)
    return _finalize_result(result, "image")
