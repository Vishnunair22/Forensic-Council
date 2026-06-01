"""
File Type Policy
================

Single source of truth for supported MIME types, file extensions, and
agent-level file-type capabilities across the Forensic Council product.

Current scope: JPEG, PNG, TIFF, WEBP, GIF, BMP (image-only). Audio/video
agent capabilities are wired but empty — AV support is inactive until
AGENT_FILE_CAPABILITIES is populated for Agent2/Agent4.
"""

from __future__ import annotations

from typing import Any


# ── Supported MIME types (the authoritative allow-list) ──────────────────
SUPPORTED_MIME_TYPES: frozenset[str] = frozenset({
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
    "image/gif",
    "image/bmp",
})


# ── Extension-to-MIME mapping ────────────────────────────────────────────
_EXTENSION_MAP: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(_EXTENSION_MAP.keys())


# ── Exact MIME → valid-extension set (for content-vs-extension mismatch check) ──
EXACT_MIME_EXT_MAP: dict[str, frozenset[str]] = {
    "image/jpeg": frozenset({".jpg", ".jpeg"}),
    "image/png": frozenset({".png"}),
    "image/gif": frozenset({".gif"}),
    "image/webp": frozenset({".webp"}),
    "image/bmp": frozenset({".bmp"}),
    "image/tiff": frozenset({".tif", ".tiff"}),
}


def get_mime_for_extension(ext: str) -> str | None:
    """Return the authoritative MIME type for a lowercased extension (with dot)."""
    return _EXTENSION_MAP.get(ext.lower())


# ── Agent-level file-type capabilities ───────────────────────────────────
AGENT_FILE_CAPABILITIES: dict[str, dict[str, Any]] = {
    "Agent1": {"mime_prefixes": ["image/"], "extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp"]},
    "Agent2": {"mime_prefixes": [], "extensions": []},
    "Agent3": {"mime_prefixes": ["image/"], "extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp"]},
    "Agent4": {"mime_prefixes": [], "extensions": []},
    "Agent5": {"mime_prefixes": ["image/"], "extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp"]},
}


def get_applicable_agents(mime_type: str) -> list[str]:
    """Return ordered list of agent IDs that support the given MIME type."""
    applicable: list[str] = []
    for agent_id, caps in AGENT_FILE_CAPABILITIES.items():
        mime_prefixes: list[str] = caps["mime_prefixes"]
        if any(mime_type.lower().startswith(p) for p in mime_prefixes):
            applicable.append(agent_id)
    return applicable


# ── Human-readable description ──────────────────────────────────────────
def describe_file_type(ext: str, mime_type: str) -> str:
    """Return a short human-readable description for the given ext/MIME pair."""
    descriptions: dict[str, str] = {
        "image/jpeg": "JPEG image",
        "image/png": "PNG image",
        "image/tiff": "TIFF image",
        "image/webp": "WebP image",
        "image/gif": "GIF image",
        "image/bmp": "BMP image",
    }
    name = descriptions.get(mime_type, f"file (.{ext.lstrip('.')})")
    return f"{name} (.{ext.lstrip('.')})"
