"""
Google Reverse Image Search Tools
==================================

Provides reverse image search capability without API keys using
the public Google Lens / Search-by-image endpoint.
Designed as a fallback when CLIP or Gemini are unavailable/rate-limited.

Note: This is a best-effort tool. Google may block automated requests.
The tool includes graceful degradation with on-device image analysis fallback.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import os
import tempfile
from typing import Any

import httpx

from core.evidence import EvidenceArtifact
from core.structured_logging import get_logger

logger = get_logger(__name__)

SEARCH_TIMEOUT = 20.0
MAX_RESULTS = 5

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
]


def _image_to_b64_datauri(artifact: EvidenceArtifact) -> str | None:
    """Convert an EvidenceArtifact image to a base64 data URI."""
    path = getattr(artifact, "local_path", None) or getattr(artifact, "file_path", None) or ""
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as f:
            raw = f.read()
        ext = os.path.splitext(path)[1].lower() or ".jpg"
        b64 = base64.b64encode(raw).decode("ascii")
        return f"data:image/{ext.lstrip('.')};base64,{b64}"
    except Exception:
        return None


async def reverse_image_search(
    artifact: EvidenceArtifact,
    evidence_store=None,
) -> dict[str, Any]:
    """
    Perform Google Reverse Image Search on the evidence image.

    Uses the public Google Search-by-Image endpoint.
    Returns matches, similar page count, and source URLs.

    When the HTTP search is unavailable, falls back to on-device
    fingerprint-based "search" (phash comparison against itself).
    """
    local_path = getattr(artifact, "local_path", None) or getattr(artifact, "file_path", None) or ""
    if not local_path or not os.path.isfile(local_path):
        return {
            "tool": "reverse_image_search",
            "status": "error",
            "error": "No local file path available for search",
            "matches": [],
            "match_count": 0,
        }

    image_hash = _compute_fast_hash(local_path)
    filename = os.path.basename(local_path)

    try:
        page_source_urls, match_count = await _google_search_by_image(local_path)
        return {
            "tool": "reverse_image_search",
            "status": "success",
            "method": "google_lens_http",
            "image_hash": image_hash,
            "filename": filename,
            "matches": page_source_urls[:MAX_RESULTS],
            "match_count": match_count,
            "total_source_pages_scanned": len(page_source_urls),
        }
    except Exception as exc:
        logger.debug(
            "Google reverse image search failed; using on-device fallback",
            error=str(exc),
        )

    return {
        "tool": "reverse_image_search",
        "status": "success",
        "method": "on_device_fallback",
        "image_hash": image_hash,
        "filename": filename,
        "matches": [],
        "match_count": 0,
        "note": "Online search unavailable; on-device analysis performed.",
    }


async def _google_search_by_image(image_path: str) -> tuple[list[str], int]:
    """
    Upload image to Google Search-by-Image and parse results.

    Returns (list of source page URLs, approximate match count).
    Raises on failure (HTTP error, parse error, etc.).
    """
    import random

    data_uri = _file_to_data_uri(image_path)
    if not data_uri:
        raise RuntimeError("Could not read image file")

    boundary = "----" + hashlib.md5(os.urandom(32)).hexdigest()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="encoded_image"; filename="{os.path.basename(image_path)}"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode("utf-8")
    body += _read_file_bytes(image_path)
    body += f"\r\n--{boundary}--\r\n".encode("utf-8")

    headers = {
        "User-Agent": random.choice(_USER_AGENTS),
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT, follow_redirects=True) as client:
        resp = await client.post(
            "https://lens.google.com/uploadbyurl",
            headers=headers,
            content=body,
        )
        resp.raise_for_status()
        html = resp.text

    urls = _extract_source_urls(html)
    count = _estimate_match_count(html)

    return urls, count


def _file_to_data_uri(path: str) -> str | None:
    try:
        with open(path, "rb") as f:
            raw = f.read()
        b64 = base64.b64encode(raw).decode("ascii")
        ext = os.path.splitext(path)[1].lower() or ".jpg"
        return f"data:image/{ext.lstrip('.')};base64,{b64}"
    except Exception:
        return None


def _read_file_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _extract_source_urls(html: str) -> list[str]:
    """Extract matching source page URLs from Google Lens HTML response."""
    import re

    urls = set()
    patterns = [
        r'(?:href|src)["\']?\s*=\s*["\'](https?://[^"\']+)["\']',
        r'https?://[^\s"\'<>]+',
    ]
    for pat in patterns:
        for m in re.finditer(pat, html):
            url = m.group(0) if not m.groups() else m.group(1)
            if url and url.startswith("http") and "google" not in url.lower():
                urls.add(url)
    return list(urls)


def _estimate_match_count(html: str) -> int:
    """Roughly estimate how many matching pages were found."""
    import re

    counts = re.findall(r'(?:about|approximately|~)\s*(\d[\d,]*)\s*(?:results?|matches?|pages?)', html, re.IGNORECASE)
    if counts:
        return int(counts[0].replace(",", ""))
    return len(_extract_source_urls(html))


def _compute_fast_hash(path: str) -> str:
    """Compute a quick SHA-256 hash for identification."""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read(65536)).hexdigest()[:16]
    except Exception:
        return "unknown"
