"""
Lightweight media characterization helpers.

These helpers intentionally use only local file/container facts.  They are used
to keep the initial pass from applying camera-specific tools to screen captures
and other digitally-created images.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from PIL import Image

from core.structured_logging import get_logger

logger = get_logger(__name__)


def _artifact_mime(artifact: Any) -> str:
    return (getattr(artifact, "mime_type", "") or "").lower()


@lru_cache(maxsize=512)
def _image_probe(file_path: str) -> dict[str, Any]:
    try:
        with Image.open(file_path) as img:
            exif = img.getexif()
            has_camera_tags = False
            if exif:
                # 271: Make, 272: Model
                has_camera_tags = any(exif.get(tag) for tag in (271, 272))

            return {
                "format": (img.format or "").lower(),
                "width": int(img.width),
                "height": int(img.height),
                "has_exif": bool(exif),
                "has_camera_tags": has_camera_tags,
                "info_keys": tuple(str(k).lower() for k in (img.info or {}).keys()),
            }
    except Exception:
        return {}


def is_camera_still_candidate(artifact: Any) -> bool:
    """Return True for formats that normally originate from cameras."""
    file_path = str(getattr(artifact, "file_path", "") or "")
    ext = os.path.splitext(file_path)[1].lower()
    mime = _artifact_mime(artifact)
    return ext in {
        ".jpg",
        ".jpeg",
        ".tiff",
        ".tif",
        ".heic",
        ".heif",
        ".raw",
        ".cr2",
        ".nef",
        ".arw",
        ".dng",
        ".orf",
    } or mime in {
        "image/jpeg",
        "image/tiff",
        "image/heic",
        "image/heif",
        "image/x-adobe-dng",
    }


def is_screen_capture_like(artifact: Any) -> bool:
    """
    Heuristic screen-capture detector.

    A PNG/WebP/BMP with no EXIF, monitor-like dimensions, and no camera format
    signature is usually a screenshot or digitally-created image.  The check is
    conservative enough to avoid affecting JPEG/HEIC camera uploads.

    Evidence files are stored under UUID paths with a .bin extension; PIL-detected
    format from magic bytes is used as the authoritative extension in that case.
    """
    file_path = str(getattr(artifact, "file_path", "") or "")
    ext = os.path.splitext(file_path)[1].lower()
    mime = _artifact_mime(artifact)
    probe = _image_probe(file_path)
    if not probe:
        return False

    # Use PIL-detected format when the stored path carries a generic extension
    # (.bin, .tmp, or no extension) so the format checks below work correctly.
    pil_fmt = str(probe.get("format") or "").lower()
    if ext in {"", ".bin", ".tmp"} and pil_fmt:
        ext = {"jpeg": ".jpg"}.get(pil_fmt, f".{pil_fmt}")

    width = int(probe.get("width") or 0)
    height = int(probe.get("height") or 0)

    # Special Case: Large JPEGs that are clearly screenshots (phone exports)
    if ext == ".jpg" and (mime in {"image/jpeg", ""} or is_camera_still_candidate(artifact)):
        filename = os.path.basename(file_path).lower()
        screenshot_keywords = {"screenshot", "screen", "capture", "snap", "export"}
        has_keyword = any(k in filename for k in screenshot_keywords)
        if width >= 1080 and not probe.get("has_camera_tags") and has_keyword:
            return True
        return False

    if ext not in {".png", ".webp", ".bmp"} and mime not in {
        "image/png",
        "image/webp",
        "image/bmp",
    }:
        return False

    if probe.get("has_exif"):
        return False

    if width < 600 or height < 350:
        return False

    aspect = width / max(height, 1)
    # Accept both landscape (monitor) and portrait (phone) screenshots
    monitor_like = (1.15 <= aspect <= 2.5) or (0.4 <= aspect <= 0.75)
    metadata_hint = bool(
        set(probe.get("info_keys") or ()) & {"software", "source", "screen", "creation time", "dpi"}
    )
    common_axis = any(
        v in {720, 768, 800, 900, 1024, 1080, 1170, 1179, 1200, 1284, 1290,
              1440, 1600, 2160, 2340, 2400, 2532, 2556, 2664, 2796, 3088}
        for v in (width, height)
    )
    return monitor_like and (metadata_hint or common_axis)


def is_digitally_created_image(artifact: Any) -> bool:
    """Return True for images whose container does not normally carry camera provenance."""
    if is_screen_capture_like(artifact):
        return True
    if is_camera_still_candidate(artifact):
        return False
    file_path = str(getattr(artifact, "file_path", "") or "")
    ext = os.path.splitext(file_path)[1].lower()
    mime = _artifact_mime(artifact)
    return ext in {".png", ".webp", ".bmp", ".gif", ".svg", ".avif"} or mime in {
        "image/png",
        "image/webp",
        "image/bmp",
        "image/gif",
        "image/svg+xml",
        "image/avif",
    }


def is_document_like(artifact: Any) -> bool:
    """Return True if the image is characterizable as a scanned or digital document."""
    file_path = str(getattr(artifact, "file_path", "") or "")
    probe = _image_probe(file_path)
    if not probe:
        return False

    has_no_camera_tags = not probe.get("has_camera_tags")
    info_keys = set(probe.get("info_keys") or ())
    has_text_hints = has_no_camera_tags and bool(info_keys & {"software", "dpi", "description", "document"})

    orig_name = str(getattr(artifact, "original_filename", "") or "").lower()
    filename = os.path.basename(file_path).lower()
    doc_keywords = {"scan", "document", "receipt", "invoice", "letter", "form", "id", "passport", "certificate"}
    has_keyword = any(k in filename or k in orig_name for k in doc_keywords)

    return has_text_hints or has_keyword


def is_recompressed_web_image(artifact: Any) -> bool:
    """Return True if the image is classified as a recompressed web/social media download."""
    file_path = str(getattr(artifact, "file_path", "") or "")
    probe = _image_probe(file_path)
    if not probe:
        return False

    fmt = str(probe.get("format") or "").lower()
    # Accept both jpeg format label and standard extensions
    is_jpg = fmt in {"jpeg", "jpg"} or os.path.splitext(file_path)[1].lower() in {".jpg", ".jpeg"}
    if not is_jpg:
        return False

    # Camera-originated files are never recompressed web images
    if probe.get("has_camera_tags"):
        return False

    orig_name = str(getattr(artifact, "original_filename", "") or "").lower()
    filename = os.path.basename(file_path).lower()
    web_keywords = {"web", "download", "img", "photo_", "facebook", "instagram", "whatsapp", "twitter", "reddit"}
    has_web_keyword = any(k in filename or k in orig_name for k in web_keywords)

    has_quantization = False
    try:
        with Image.open(file_path) as img:
            has_quantization = bool(getattr(img, "quantization", None))
    except Exception as exc:
        logger.debug("Could not inspect JPEG quantization", file_path=file_path, error=str(exc))

    return has_quantization or has_web_keyword
