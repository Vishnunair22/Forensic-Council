"""Shared image utility functions."""

_LOSSLESS_EXTS = frozenset({".png", ".bmp", ".tiff", ".tif", ".gif", ".webp"})
_LOSSLESS_PIL_FORMATS = frozenset({"PNG", "BMP", "TIFF", "GIF", "WEBP"})
_LOSSLESS_MIMES = frozenset(
    {"image/png", "image/bmp", "image/tiff", "image/gif", "image/webp"}
)


def is_lossless_image(file_path: str, mime_type: str | None = None) -> bool:
    """
    Determine if an image file uses a lossless format.

    Checks file extension, MIME type, and (optionally) PIL format header.
    Returns True if any check indicates a lossless format.
    """
    import os

    ext = os.path.splitext(file_path)[1].lower()
    if ext in _LOSSLESS_EXTS:
        return True

    if mime_type and mime_type.lower() in _LOSSLESS_MIMES:
        return True

    try:
        from PIL import Image

        pil_format = (Image.open(file_path).format or "").upper()
        if pil_format in _LOSSLESS_PIL_FORMATS:
            return True
    except Exception:
        pass

    return False
