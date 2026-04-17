"""Shared image utility functions."""

_LOSSLESS_EXTS = frozenset(
    {".png", ".bmp", ".tiff", ".tif", ".gif", ".webp", ".heic", ".heif", ".avif", ".dng", ".nef", ".cr2"}
)
_LOSSLESS_PIL_FORMATS = frozenset({"PNG", "BMP", "TIFF", "GIF", "WEBP", "HEIC", "AVIF", "DNG"})
_LOSSLESS_MIMES = frozenset(
    {
        "image/png",
        "image/bmp",
        "image/tiff",
        "image/gif",
        "image/webp",
        "image/heic",
        "image/heif",
        "image/avif",
        "image/x-adobe-dng",
    }
)


def is_lossless_image(file_path: str, mime_type: str | None = None) -> bool:
    """
    Determine if an image file uses a lossless format.

    Checks file extension, MIME type, and PIL metadata.
    For WebP, it specifically checks the internal lossy/lossless flag.
    """
    import os

    ext = os.path.splitext(file_path)[1].lower()

    # Fast path: known lossless-only formats
    if ext in _LOSSLESS_EXTS and ext != ".webp":
        return True

    if mime_type and mime_type.lower() in _LOSSLESS_MIMES and "webp" not in mime_type.lower():
        return True

    try:
        from PIL import Image

        with Image.open(file_path) as img:
            pil_format = (img.format or "").upper()

            # Special case for WebP: can be lossy OR lossless
            if pil_format == "WEBP":
                # PIL info contains 'lossless' flag for WebP
                return bool(img.info.get("lossless", False))

            if pil_format in _LOSSLESS_PIL_FORMATS:
                return True
    except Exception:
        pass

    return False
