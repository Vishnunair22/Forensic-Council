"""
Reverse Image Search Tool (local, chain-of-custody-safe)
========================================================

IMPORTANT: This tool no longer scrapes Google Lens / Search-by-Image.

The previous implementation uploaded the evidence image (as base64) to
``lens.google.com`` with spoofed browser User-Agents. For a forensic tool that
is a disqualifying problem on three counts:
  1. Chain of custody — the evidence leaves operator control and is cached by a
     third party.
  2. ToS-violating scraping that gets blocked and is non-reproducible (results
     change between runs, so they cannot be cited in a report).
  3. Non-court-defensible.

It now delegates to the local, offline provenance screen
(:func:`core.perceptual_provenance.analyze_provenance` — perceptual hash + C2PA
manifest check). Nothing is transmitted off-device, the perceptual fingerprint
is reproducible, and matches against the operator-curated index are reported as
screening-tier OSINT leads.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from core.evidence import EvidenceArtifact
from core.structured_logging import get_logger

logger = get_logger(__name__)


async def reverse_image_search(
    artifact: EvidenceArtifact,
    evidence_store=None,
) -> dict[str, Any]:
    """Local provenance screen (perceptual hash + C2PA) in place of online
    reverse image search. Never transmits the evidence off-device.

    Return shape is kept backward-compatible (``matches``/``match_count``) for
    existing callers, but results come from the local provenance index.
    """
    local_path = getattr(artifact, "local_path", None) or getattr(artifact, "file_path", None) or ""
    if not local_path or not os.path.isfile(local_path):
        return {
            "tool": "reverse_image_search",
            "status": "error",
            "error": "No local file path available for provenance screen",
            "matches": [],
            "match_count": 0,
            "available": False,
        }

    try:
        from core.perceptual_provenance import analyze_provenance

        prov = await asyncio.to_thread(analyze_provenance, local_path)
    except Exception as exc:
        logger.debug("local provenance screen failed", error=str(exc))
        return {
            "tool": "reverse_image_search",
            "status": "error",
            "error": str(exc),
            "matches": [],
            "match_count": 0,
            "available": False,
        }

    match = prov.get("known_match") or None
    matches: list[str] = []
    if match:
        matches = [str(match.get("source") or match.get("label") or "local index match")]

    return {
        "tool": "reverse_image_search",
        "status": "success",
        "method": "local_provenance",
        "court_defensible": False,  # screening / OSINT tier
        "perceptual_hash": prov.get("perceptual_hash"),
        "hash_algorithm": prov.get("hash_algorithm"),
        "c2pa_present": prov.get("c2pa_present"),
        "c2pa_manifest_count": prov.get("c2pa_manifest_count"),
        "matches": matches,
        "match_count": len(matches),
        "match_distance": prov.get("match_distance"),
        "provenance_clues": prov.get("provenance_clues", []),
        "available": bool(prov.get("available", True)),
        "note": (
            "Online reverse search disabled for chain-of-custody integrity; "
            "local perceptual-hash + C2PA provenance screen performed instead."
        ),
    }
