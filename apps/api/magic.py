from __future__ import annotations


def from_buffer(data: bytes, mime: bool = False) -> str:
    """Small libmagic-compatible fallback for common upload formats."""
    head = bytes(data or b"")
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg" if mime else "JPEG image data"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png" if mime else "PNG image data"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif" if mime else "GIF image data"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image/webp" if mime else "WebP image data"
    if head.startswith(b"%PDF"):
        return "application/pdf" if mime else "PDF document"
    if head.startswith(b"BM"):
        return "image/bmp" if mime else "BMP image data"
    return "application/octet-stream" if mime else "data"
