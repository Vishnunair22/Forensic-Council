"""
Perceptual-hash + C2PA provenance (free, offline, court-defensible-aware)
========================================================================

Strengthens the no-Gemini local ensemble with two provenance signals that are
fully local, cost nothing, never send the evidence to a third party (no
chain-of-custody risk), and are reproducible:

  1. **Perceptual hash matching** — a 64-bit dHash of the image is compared
     (Hamming distance) against a local, operator-curated index of known
     images (stock photos, known AI-generated samples, previously-seen
     evidence). A match is an OSINT *lead*, not proof: it is reported at the
     screening tier (``court_defensible=False``). The hash itself is always
     returned as a reproducible fingerprint, even when the index is empty.

  2. **C2PA / Content Credentials** — reuses the existing JUMBF manifest
     scanner. Presence of a valid manifest is a genuine provenance signal.

Honesty contract: no match / no index / no manifest are reported plainly as
"no provenance signal", never as authenticity. The function never raises — on
any failure it returns ``available: False`` with a reason so the ensemble
degrades to a coverage gap.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from core.structured_logging import get_logger

logger = get_logger(__name__)

# Hamming distance (out of 64 bits) under which two dHashes are "the same image".
# 0 = byte-identical resize; <=10 tolerates re-compression/minor edits.
_MATCH_THRESHOLD = 10

# Labels in the index that denote a non-authentic provenance — when matched,
# these become forensic signals rather than mere context.
_ALERT_LABELS = ("ai_generated", "manipulated", "deepfake", "synthetic", "known_fake")


def _index_path() -> str:
    try:
        from core.config import get_settings

        return str(getattr(get_settings(), "perceptual_hash_index_path", "") or "")
    except Exception:
        return os.getenv("PERCEPTUAL_HASH_INDEX_PATH", "")


def compute_dhash(image_path: str) -> str | None:
    """64-bit difference hash as a 16-char hex string. Prefers the imagehash
    library; falls back to a dependency-free numpy implementation."""
    try:
        from PIL import Image

        with Image.open(image_path) as im:
            img = im.convert("L")
            try:
                import imagehash  # type: ignore

                return str(imagehash.dhash(img, hash_size=8))
            except Exception:
                # Dependency-free dHash: 9x8 grayscale, compare adjacent columns.
                import numpy as np

                small = img.resize((9, 8))
                arr = np.asarray(small, dtype=np.int16)
                diff = arr[:, 1:] > arr[:, :-1]  # 8x8 booleans
                bits = 0
                for b in diff.flatten():
                    bits = (bits << 1) | int(bool(b))
                return f"{bits:016x}"
    except Exception as exc:
        logger.debug("dhash computation failed", error=str(exc))
        return None


def _hamming_hex(a: str, b: str) -> int | None:
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except (ValueError, TypeError):
        return None


def _load_index(path: str) -> list[dict]:
    """Load the operator-curated known-image index. Returns [] if absent/invalid.

    Expected JSON: a list of {"hash": "<hex>", "label": "...", "source": "...",
    "note": "..."} objects, or an object with a top-level "entries" list.
    """
    if not path:
        return []
    p = Path(path)
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        entries = data.get("entries", data) if isinstance(data, dict) else data
        return [e for e in entries if isinstance(e, dict) and e.get("hash")]
    except Exception as exc:
        logger.warning("perceptual-hash index unreadable", path=path, error=str(exc))
        return []


def match_known_hash(image_path: str) -> dict[str, Any]:
    """Compute the image's dHash and find the closest known-index match."""
    digest = compute_dhash(image_path)
    if digest is None:
        return {"available": False, "error": "could not compute perceptual hash"}

    index = _load_index(_index_path())
    best: dict | None = None
    best_dist: int | None = None
    for entry in index:
        dist = _hamming_hex(digest, str(entry.get("hash", "")))
        if dist is None:
            continue
        if best_dist is None or dist < best_dist:
            best_dist, best = dist, entry

    matched = best is not None and best_dist is not None and best_dist <= _MATCH_THRESHOLD
    return {
        "available": True,
        "perceptual_hash": digest,
        "hash_algorithm": "dhash64",
        "index_size": len(index),
        "match": best if matched else None,
        "match_distance": best_dist if matched else None,
    }


def check_c2pa(image_path: str) -> dict[str, Any]:
    """Presence/validity of a C2PA Content Credentials manifest (reuses the
    existing JUMBF scanner). Never raises."""
    try:
        from tools.ml_tools.c2pa_validator import scan_jumbf_manifest

        res = scan_jumbf_manifest(image_path)
        if not isinstance(res, dict):
            return {"available": False}
        return {
            "available": res.get("available", True) and "error" not in res,
            "c2pa_present": bool(res.get("c2pa_present")),
            "manifest_count": int(res.get("manifest_count") or 0),
        }
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def analyze_provenance(image_path: str) -> dict[str, Any]:
    """Combined local provenance screen. Always returns a dict; never raises.

    The result is screening-tier (``court_defensible=False``): a perceptual
    match or a C2PA manifest is an investigative lead/metadata fact, not a
    standalone court-defensible determination.
    """
    hash_res = match_known_hash(image_path)
    c2pa_res = check_c2pa(image_path)

    clues: list[str] = []
    signals: list[str] = []

    # NOTE: the raw perceptual-hash digest is recorded in metadata (below) for
    # matching, but is NOT surfaced as a user-facing provenance clue — a bare 64-bit
    # hash ("Perceptual fingerprint (dHash): 4373...") is internal plumbing, not an
    # informative provenance fact. Only actual matches / C2PA credentials are shown.
    digest = hash_res.get("perceptual_hash")
    match = hash_res.get("match")
    if match:
        label = str(match.get("label") or "known image")
        source = str(match.get("source") or "local index")
        dist = hash_res.get("match_distance")
        clues.append(
            f"Perceptual hash matches a {label} entry (source: {source}, "
            f"distance {dist}) — OSINT lead, not court-defensible."
        )
        if any(tok in label.lower() for tok in _ALERT_LABELS):
            signals.append(
                f"Image matches a known {label} reference (perceptual hash, distance {dist})"
            )

    if c2pa_res.get("c2pa_present"):
        clues.append(
            f"Content Credentials (C2PA) manifest present "
            f"({c2pa_res.get('manifest_count', 0)}) — provenance metadata available."
        )

    return {
        "available": bool(hash_res.get("available") or c2pa_res.get("available")),
        "method": "perceptual_hash+c2pa",
        "court_defensible": False,
        "perceptual_hash": digest,
        "hash_algorithm": hash_res.get("hash_algorithm"),
        "known_match": match,
        "match_distance": hash_res.get("match_distance"),
        "index_size": hash_res.get("index_size", 0),
        "c2pa_present": bool(c2pa_res.get("c2pa_present")),
        "c2pa_manifest_count": c2pa_res.get("manifest_count", 0),
        "provenance_clues": clues,
        "signals": signals,
    }
