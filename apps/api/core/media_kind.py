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
    """
    file_path = str(getattr(artifact, "file_path", "") or "")
    ext = os.path.splitext(file_path)[1].lower()
    mime = _artifact_mime(artifact)
    probe = _image_probe(file_path)
    if not probe:
        return False

    width = int(probe.get("width") or 0)
    height = int(probe.get("height") or 0)

    # Special Case: Large JPEGs that are clearly screenshots (phone exports)
    if is_camera_still_candidate(artifact) and mime == "image/jpeg":
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
    monitor_like = 1.15 <= aspect <= 2.5
    metadata_hint = bool(
        set(probe.get("info_keys") or ()) & {"software", "source", "screen", "creation time", "dpi"}
    )
    common_axis = any(
        v in {720, 768, 800, 900, 1024, 1080, 1200, 1440, 1600, 2160} for v in (width, height)
    )
    return monitor_like and (metadata_hint or common_axis or width >= 1000)


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
