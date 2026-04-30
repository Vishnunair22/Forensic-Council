"""Compatibility helpers for legacy custody-chain tests."""

from __future__ import annotations

from typing import Any

from core.signing import compute_content_hash, sign_content


def sign_entry(entry: dict[str, Any], agent_id: str = "Arbiter") -> dict[str, Any]:
    """Return a signed copy of a custody entry."""
    signed = sign_content(agent_id, entry)
    data = dict(entry)
    data["content_hash"] = compute_content_hash(entry)
    data["signature"] = signed.signature
    data["agent_id"] = agent_id
    data["timestamp_utc"] = signed.timestamp_utc.isoformat()
    return data
