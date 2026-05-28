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
import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import fitz

from core.evidence import EvidenceArtifact
from core.exceptions import ToolUnavailableError
from core.media_kind import is_screen_capture_like
from core.structured_logging import get_logger

logger = get_logger(__name__)

# Shared executor for CPU-bound OCR tasks to avoid blocking the event loop
_OCR_EXECUTOR = ThreadPoolExecutor(max_workers=min(32, (os.cpu_count() or 1) * 4))

# M-H-8: per-process Gemini OCR cache — keyed by SHA-256 of file content,
# not the file path. Same path can refer to a different binary across
# investigations; hash-keying prevents stale hits on re-uploaded files.
# Capped to 64 entries with FIFO eviction so memory stays bounded.
_GEMINI_OCR_CACHE: dict[str, dict] = {}
_GEMINI_OCR_CACHE_MAX = 64


def _gemini_ocr_cache_key(file_path: str) -> str | None:
    """Return a SHA-256 hex digest of file contents, or None if unreadable."""
    if not file_path or not os.path.isabs(file_path):
        return None
    try:
        import hashlib

        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _gemini_ocr_cache_put(key: str, value: dict) -> None:
    """Insert with FIFO eviction so the cache cannot grow unbounded."""
    if len(_GEMINI_OCR_CACHE) >= _GEMINI_OCR_CACHE_MAX:
        try:
            _GEMINI_OCR_CACHE.pop(next(iter(_GEMINI_OCR_CACHE)))
        except StopIteration:
            pass
    _GEMINI_OCR_CACHE[key] = value

# Thread-local storage for EasyOCR readers to avoid re-init overhead
_EASYOCR_READER = None


def _coerce_gemini_ocr_lines(raw_result: Any) -> tuple[list[str], dict[str, Any], float]:
    """Normalize Gemini OCR responses across JSON, text JSON, and line-object variants."""
    parsed = raw_result
    if isinstance(parsed, str):
        text = parsed.strip()
        if text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return ([line.strip() for line in text.splitlines() if line.strip()], {}, 0.90)

    metadata: dict[str, Any] = {}
    confidence = 0.98
    lines: list[str] = []

    if isinstance(parsed, dict):
        metadata = parsed.get("structured_metadata", {}) or parsed.get("metadata", {}) or {}
        try:
            confidence = float(
                parsed.get("ocr_confidence")
                or parsed.get("confidence")
                or parsed.get("avg_confidence")
                or confidence
            )
        except (TypeError, ValueError):
            confidence = 0.98

        raw_lines = (
            parsed.get("lines")
            or parsed.get("text_lines")
            or parsed.get("ocr_lines")
            or parsed.get("items")
            or []
        )
        if isinstance(raw_lines, str):
            raw_lines = [line.strip() for line in raw_lines.splitlines() if line.strip()]
        if isinstance(raw_lines, list):
            for item in raw_lines:
                if isinstance(item, str):
                    value = item
                elif isinstance(item, dict):
                    value = (
                        item.get("text")
                        or item.get("line")
                        or item.get("content")
                        or item.get("value")
                        or ""
                    )
                else:
                    value = str(item)
                value = " ".join(str(value).split())
                if value:
                    lines.append(value)

        if not lines:
            text_value = parsed.get("full_text") or parsed.get("text") or parsed.get("ocr_text") or ""
            lines = [line.strip() for line in str(text_value).splitlines() if line.strip()]
            if not lines and str(text_value).strip():
                lines = [" ".join(str(text_value).split())]
    elif isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, str):
                value = item
            elif isinstance(item, dict):
                value = item.get("text") or item.get("line") or item.get("content") or ""
            else:
                value = str(item)
            value = " ".join(str(value).split())
            if value:
                lines.append(value)

    # Deduplicate adjacent repeats without changing the model's reading order.
    deduped: list[str] = []
    for line in lines:
        if not deduped or deduped[-1] != line:
            deduped.append(line)
    return deduped, metadata if isinstance(metadata, dict) else {}, max(0.0, min(1.0, confidence))


def _get_easyocr_reader():
    """Get or initialize the EasyOCR reader (cached in thread pool)."""
    global _EASYOCR_READER
    if _EASYOCR_READER is None:
        try:
            import warnings  # noqa: PLC0415

            import easyocr  # noqa: PLC0415
            warnings.filterwarnings("ignore", message=".*pin_memory.*", category=UserWarning)

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
    full_text = str(result.get("full_text") or result.get("text") or "").strip()
    lines = result.get("lines")
    if not full_text and isinstance(lines, list):
        full_text = "\n".join(str(line).strip() for line in lines if str(line).strip())
    preview = str(result.get("ocr_text_preview") or result.get("text_preview") or "").strip()
    if not preview and full_text:
        preview = " | ".join(line.strip() for line in full_text.splitlines() if line.strip())[:240]
    if full_text:
        result.setdefault("full_text", full_text)
        result.setdefault("text", full_text)
        result.setdefault("has_text", True)
        result.setdefault("word_count", len(full_text.split()))
    if preview:
        result.setdefault("ocr_text_preview", preview)
        result.setdefault("text_preview", preview)
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
    import time
    logger.info(f"[OCR] Starting EasyOCR sync text extraction for {file_path}")
    start_time = time.time()

    logger.info("[OCR] Fetching EasyOCR reader instance...")
    reader_start = time.time()
    reader = _get_easyocr_reader()
    reader_duration = time.time() - reader_start
    logger.info(f"[OCR] EasyOCR reader fetched in {reader_duration:.3f}s")

    if reader is None:
        logger.warning("[OCR] EasyOCR reader is not available")
        return {"easyocr_available": False}

    try:
        logger.info(f"[OCR] Running EasyOCR readtext on {file_path}")
        inference_start = time.time()
        results = reader.readtext(file_path, detail=1, paragraph=False)
        inference_duration = time.time() - inference_start
        logger.info(f"[OCR] EasyOCR readtext inference completed in {inference_duration:.3f}s")

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

        total_duration = time.time() - start_time
        logger.info(f"[OCR] EasyOCR sync pipeline completed successfully in {total_duration:.3f}s. Words extracted: {len(full_text.split())}")

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
        logger.error(f"[OCR] Exception in EasyOCR readtext on {file_path}: {exc}", exc_info=True)
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

    from core.config import get_settings
    settings = get_settings()
    total_timeout = getattr(settings, "ocr_tool_timeout", 60.0)

    # Allocate 70% to EasyOCR and 30% to Tesseract fallback
    easyocr_timeout = max(30.0, total_timeout * 0.7)
    tesseract_timeout = max(20.0, total_timeout * 0.3)

    logger.info(
        f"[OCR] Starting extract_text_easyocr with total_timeout={total_timeout}s. "
        f"EasyOCR timeout={easyocr_timeout:.1f}s, Tesseract fallback timeout={tesseract_timeout:.1f}s."
    )

    loop = asyncio.get_running_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(
                _OCR_EXECUTOR,
                lambda: _extract_text_easyocr_sync(artifact.file_path, detail=detail),
            ),
            timeout=easyocr_timeout,
        )
    except TimeoutError:
        logger.warning(f"[OCR] EasyOCR extraction timed out after {easyocr_timeout:.1f}s — falling back to Tesseract")
        return await _extract_text_tesseract_fallback(artifact, timeout=tesseract_timeout)
    except Exception as exc:
        logger.error(f"[OCR] EasyOCR extraction failed: {exc}")
        return await _extract_text_tesseract_fallback(artifact, timeout=tesseract_timeout)

    if not result.get("easyocr_available"):
        # Graceful fallback to Tesseract
        logger.debug("[OCR] EasyOCR unavailable — falling back to Tesseract")
        return await _extract_text_tesseract_fallback(artifact, timeout=tesseract_timeout)

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
    timeout: float = 20.0,
) -> dict[str, Any]:
    """Internal Tesseract fallback used by extract_text_easyocr."""
    logger.info(f"[OCR] Running Tesseract fallback for {artifact.file_path} with timeout={timeout:.1f}s")
    loop = asyncio.get_running_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(_OCR_EXECUTOR, _extract_text_tesseract_sync, artifact.file_path),
            timeout=timeout,
        )
    except TimeoutError:
        logger.warning(f"[OCR] Tesseract fallback timed out after {timeout:.1f}s")
        result = {
            "tesseract_available": True,
            "error": f"Tesseract timed out after {timeout:.1f}s",
            "lines": [],
            "full_text": "",
            "word_count": 0,
            "has_text": False,
        }
    result["method"] = "tesseract_fallback"
    result["court_defensible"] = result.get("tesseract_available", False) and not result.get("error")
    return result


async def _extract_text_gemini(
    artifact: EvidenceArtifact,
) -> dict[str, Any]:
    """
    Tier 0 — Gemini Unified Vision OCR.

    Single Gemini call that extracts text AND identifies image content.
    Results are cached per file_path so subsequent tool calls (analyze_image_content,
    screenshot_layout_forensics, etc.) reuse the same response without a second API hit.
    """
    # M-H-8: cache key is content-hash, not path. Test fixtures with
    # relative paths are still skipped (hash helper returns None).
    file_path = str(getattr(artifact, "file_path", "") or "")
    cache_key = _gemini_ocr_cache_key(file_path)
    use_cache = bool(cache_key)
    if use_cache and cache_key in _GEMINI_OCR_CACHE:
        logger.info("Gemini OCR cache hit", file_path=file_path)
        return _GEMINI_OCR_CACHE[cache_key]

    try:
        from core.config import get_settings
        from core.llm_client import LLMClient

        settings = get_settings()
        gemini_api_key = str(getattr(settings, "gemini_api_key", "") or "").strip()
        if not gemini_api_key or gemini_api_key.lower() in {"none", "placeholder"}:
            return {"gemini_available": False}

        client = LLMClient(settings)
        is_screenshot = is_screen_capture_like(artifact)

        if is_screenshot:
            prompt = """You are a forensic analyst examining a screenshot for evidentiary purposes.
Perform two tasks in one pass:

TASK 1 — CONTENT IDENTIFICATION:
Identify exactly what this screenshot shows: the application name (if recognisable), the type of
interface (web browser, mobile app, desktop GUI, messaging app, email, social media, document, etc.),
and a 1-sentence description of what action or data is displayed.

TASK 2 — PRECISION OCR:
Extract every visible text item verbatim, preserving reading order and UI grouping.
Include: system clock/date, app/window titles, browser address bar, tab labels, menu items,
buttons, form field labels and values, table headers and cell content, usernames, @handles,
post text, message content, IDs, filenames, notification text, status bar items,
error messages, captions, watermarks, and any footer/header text.
Do NOT summarise, paraphrase, or correct spelling. Transcribe partially occluded text and flag it.

Return ONLY valid JSON — no markdown, no preamble:
{
  "content_type": "precise type, e.g. screenshot of WhatsApp conversation on Android",
  "content_description": "one sentence describing what is shown",
  "lines": ["verbatim text line 1", "verbatim text line 2"],
  "structured_metadata": {
    "timestamps": ["exact timestamp strings found"],
    "identifiers": ["usernames, handles, IDs, phone numbers found"],
    "urls": ["full URLs found"],
    "ui_elements": ["button labels, menu items, headings found"],
    "document_fields": ["form labels and values found"],
    "suspicious_elements": ["partially occluded or anomalous text"]
  },
  "ocr_confidence": 0.97
}
If no text is visible, return empty lists and an empty content_description."""
        else:
            prompt = """You are a forensic analyst examining an image file for evidentiary purposes.
Perform two tasks in one pass:

TASK 1 — CONTENT IDENTIFICATION:
Identify exactly what this image shows: photograph, scanned document, handwritten note/letter,
AI-generated image, printed form, ID document, receipt, etc.
Provide a 1-2 sentence description of the content and its forensic context.

TASK 2 — PRECISION OCR (including handwriting):
Extract all visible text exactly as it appears. For HANDWRITTEN content: transcribe each
word individually even if uncertain — mark uncertain transcriptions with [?].
Focus on:
- Timestamps, dates, times (exact format as written)
- Names, signatures, initials
- Addresses, phone numbers, account numbers
- Any text that appears inconsistent in pressure, ink, or style (potential forgery indicator)
- Printed labels, stamps, or overlays on top of handwritten content
- Document headers, form field labels and their values

Return ONLY valid JSON — no markdown, no preamble:
{
  "content_type": "precise description, e.g. handwritten letter on lined paper",
  "content_description": "1-2 sentence forensic description",
  "lines": ["verbatim text line 1 [? uncertain word]", ...],
  "structured_metadata": {
    "timestamps": ["exact timestamp strings"],
    "identifiers": ["names, signatures, IDs, account numbers"],
    "urls": [],
    "ui_elements": [],
    "document_fields": ["form field: value pairs"],
    "suspicious_elements": ["text that appears inconsistent in style/ink/pressure"]
  },
  "ocr_confidence": 0.0,
  "handwriting_detected": true
}
If no text is visible, return empty lists."""

        raw_result = await client.generate_multimodal_synthesis(
            artifact=artifact,
            prompt=prompt,
            max_tokens=1536,
            json_mode=True,
        )

        lines, metadata, ocr_confidence = _coerce_gemini_ocr_lines(raw_result)
        full_text = "\n".join(lines)
        preview = " | ".join(lines[:5])

        # Extract content description and type from the raw response
        content_type = ""
        content_description = ""
        try:
            import json as _json
            if isinstance(raw_result, dict):
                content_type = str(raw_result.get("content_type") or "")
                content_description = str(raw_result.get("content_description") or "")
            elif isinstance(raw_result, str):
                text = raw_result.strip()
                # Strip optional markdown code fence
                if text.startswith("```"):
                    text = text.split("```", 2)[-1].lstrip("json").strip()
                    if text.endswith("```"):
                        text = text[:-3].strip()
                parsed = _json.loads(text)
                if isinstance(parsed, dict):
                    content_type = str(parsed.get("content_type") or "")
                    content_description = str(parsed.get("content_description") or "")
        except Exception as _parse_err:
            logger.debug("OCR response JSON parse failed (non-fatal)", error=str(_parse_err))

        result = {
            "gemini_available": True,
            "method": "gemini_multimodal",
            "lines": lines,
            "full_text": full_text,
            "word_count": len(full_text.split()),
            "has_text": bool(lines),
            "structured_metadata": metadata,
            "avg_confidence": max(0.0, min(1.0, ocr_confidence)),
            "ocr_text_preview": preview,
            "screenshot_optimized": is_screenshot,
            "court_defensible": True,
            "content_type": content_type,
            "content_description": content_description,
        }
        if use_cache and cache_key is not None:
            _gemini_ocr_cache_put(cache_key, result)
        return result
    except Exception as exc:
        logger.warning("Gemini OCR unavailable, falling back to EasyOCR", error=str(exc))
        return {"gemini_available": False, "error": str(exc)}


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

    # Tier 0: Gemini Multimodal OCR (if enabled)
    # We prefer Gemini for screenshots and documents as it understands layout better
    gemini_res = await _extract_text_gemini(artifact)
    if gemini_res.get("gemini_available") and (
        gemini_res.get("has_text") or is_screen_capture_like(artifact)
    ):
        logger.info("Gemini OCR succeeded", word_count=gemini_res.get("word_count", 0))
        return _finalize_result(gemini_res, file_type_hint)
    else:
        logger.info("Gemini OCR unavailable or empty, falling back to EasyOCR")

    if file_type_hint == "pdf_document":
        result = await extract_text_from_pdf(artifact)
        if result.get("has_text"):
            return _finalize_result(result, file_type_hint)
        result.setdefault(
            "scanned_pdf_note",
            "PDF has no embedded text; rasterise pages before image OCR.",
        )
        return _finalize_result(result, file_type_hint)


    result = await extract_text_easyocr(artifact)

    # Tesseract fallback for document/handwritten images when EasyOCR yields nothing
    if not result.get("has_text") or int(result.get("word_count") or 0) < 3:
        from core.media_kind import is_document_like
        if is_document_like(artifact):
            tess_result = await _extract_text_tesseract_fallback(artifact)
            if tess_result.get("has_text") and int(tess_result.get("word_count") or 0) > int(result.get("word_count") or 0):
                result = {**tess_result, "method": "Tesseract adaptive (document fallback)", "ocr_tier": "tesseract"}

    return _finalize_result(result, "image")
