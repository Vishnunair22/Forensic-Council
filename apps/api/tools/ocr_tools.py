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

            from core.model_guard import guarded_load  # noqa: PLC0415
            # Suppress known informational noise from EasyOCR in CPU-only environments
            warnings.filterwarnings("ignore", message=".*pin_memory.*", category=UserWarning)
            warnings.filterwarnings("ignore", message=".*Using CPU.*faster with a GPU.*", category=UserWarning, module="easyocr")

            from core.config import get_settings  # noqa: PLC0415

            model_dir = os.getenv("EASYOCR_MODEL_DIR", "/app/cache/easyocr")
            os.makedirs(model_dir, exist_ok=True)
            # Memory-guard the load: if the container lacks headroom, refuse here
            # so the caller falls back to lightweight Tesseract instead of risking
            # an OOM SIGKILL that would crash the worker.
            with guarded_load("easyocr"):
                _EASYOCR_READER = easyocr.Reader(
                    ["en"],
                    gpu=False,
                    model_storage_directory=model_dir,
                    user_network_directory=model_dir,
                    download_enabled=not get_settings().offline_mode,
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
        
    # Cap massive text payloads to prevent ReAct loop LLM OOM/Timeout (the cause of the PDF delay)
    MAX_CHARS = 4000
    if len(full_text) > MAX_CHARS:
        original_len = len(full_text)
        full_text = full_text[:MAX_CHARS] + f"\n... [Text truncated: original was {original_len} chars]"
    
    if isinstance(lines, list) and len(lines) > 200:
        lines = lines[:200]
        lines.append("... [lines truncated]")
        result["lines"] = lines

    if full_text:
        result.setdefault("full_text", full_text)
        result.setdefault("text", full_text)
        result.setdefault("has_text", True)
        result.setdefault("word_count", len(full_text.split()))
        
    # Ensure truncated text replaces any massive raw text
    if "full_text" in result:
        result["full_text"] = full_text
    if "text" in result:
        result["text"] = full_text
        
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
    text_length = 0

    try:
        for i, page in enumerate(doc):
            # Limit to 50 pages or 50k chars to prevent CPU/memory spikes on huge PDFs
            if i >= 50 or text_length > 50000:
                pages_text.append("\n... [Further pages truncated for performance]")
                break
            
            # Extract plain text for simplicity and performance as Tier 1
            text = str(page.get_text("text")).strip()
            if text:
                pages_text.append(text)
                text_length += len(text)
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


def _ocr_pdf_pages_sync(file_path: str, max_pages: int = 8) -> dict[str, Any]:
    """Rasterise PDF pages and OCR them — the fallback for SCANNED / image-only PDFs
    that carry no embedded text layer (pymupdf get_text returns nothing). Reuses the
    shared EasyOCR reader; runs in the OCR thread pool. Court-defensible local
    extraction that does not depend on the cloud model."""
    try:
        import numpy as np  # noqa: PLC0415

        reader = _get_easyocr_reader()
        if reader is None:
            return {"easyocr_available": False, "has_text": False}
        doc = fitz.open(file_path)
    except Exception as exc:
        return {"easyocr_available": False, "has_text": False, "error": str(exc)}

    pages_text: list[str] = []
    try:
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            # 200 DPI is a good legibility/cost trade-off for document OCR.
            pix = page.get_pixmap(dpi=200)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            if pix.n == 4:  # drop alpha — EasyOCR wants 3-channel
                img = img[:, :, :3]
            try:
                lines = reader.readtext(img, detail=0)
            except Exception as ocr_exc:
                logger.debug("EasyOCR page OCR failed", page=i, error=str(ocr_exc))
                continue
            page_text = "\n".join(str(ln).strip() for ln in (lines or []) if str(ln).strip())
            if page_text:
                pages_text.append(page_text)
        full_text = "\n\n".join(pages_text)
        return {
            "easyocr_available": True,
            "page_count": doc.page_count,
            "full_text": full_text,
            "lines": [ln for ln in full_text.splitlines() if ln.strip()],
            "word_count": len(full_text.split()),
            "has_text": bool(full_text.strip()),
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
        # Cap input resolution so an oversized image can't OOM CPU inference.
        ocr_input: Any = file_path
        try:
            import numpy as np  # noqa: PLC0415
            from PIL import Image as PILImage  # noqa: PLC0415

            from core.model_guard import cap_image_dimension  # noqa: PLC0415

            with PILImage.open(file_path) as _img:
                _capped = cap_image_dimension(_img.convert("RGB"))
                if _capped is not _img:
                    ocr_input = np.asarray(_capped)
        except Exception as _resize_err:
            logger.debug(f"[OCR] input downscale skipped: {_resize_err}")
            ocr_input = file_path
        results = reader.readtext(ocr_input, detail=1, paragraph=False)
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
    total_timeout = getattr(settings, "ocr_tool_timeout", 120.0)

    # Allocate 70% to EasyOCR and 30% to Tesseract fallback
    easyocr_timeout = max(60.0, total_timeout * 0.7)
    tesseract_timeout = max(30.0, total_timeout * 0.3)

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
    # Gemini is reserved for the single Agent 1 visual evidence probe.
    # OCR consumes that profile when routed through agents, then falls back
    # to EasyOCR/Tesseract here. This function remains as a compatibility
    # shim for callers/tests but never makes an API request.
    return {
        "gemini_available": False,
        "method": "agent1_visual_profile_or_local_ocr",
        "reason": "Gemini OCR disabled; Gemini quota is reserved for Agent 1 visual profile.",
    }

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

    logger.debug("Gemini OCR skipped — using Agent 1 visual profile plus EasyOCR/Tesseract")

    if file_type_hint == "pdf_document":
        result = await extract_text_from_pdf(artifact)
        if result.get("has_text"):
            return _finalize_result(result, file_type_hint)
        # Scanned / image-only PDF — no embedded text layer. Rasterise the pages and
        # OCR them so the document text is still recovered locally (previously this
        # path only left a note and returned empty).
        loop = asyncio.get_running_loop()
        ocr_result = await loop.run_in_executor(
            _OCR_EXECUTOR, _ocr_pdf_pages_sync, artifact.file_path
        )
        if ocr_result.get("has_text"):
            ocr_result["method"] = "pymupdf_rasterize+easyocr"
            ocr_result["court_defensible"] = True
            ocr_result["scanned_pdf"] = True
            # Preserve the pymupdf document metadata (producer/dates) for provenance.
            ocr_result["doc_metadata"] = result.get("doc_metadata", {})
            ocr_result["embedded_image_count"] = result.get("embedded_image_count", 0)
            return _finalize_result(ocr_result, file_type_hint)
        result.setdefault(
            "scanned_pdf_note",
            "PDF has no embedded text layer and page OCR recovered no legible text.",
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
