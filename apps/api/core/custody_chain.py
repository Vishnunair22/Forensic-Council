"""DEPRECATED: Compatibility helpers for legacy custody-chain tests.

Production code should use core.signing directly.

This module exists solely for backward compatibility with existing test suites
that import sign_entry(). New code should import from core.signing instead:

    from core.signing import sign_content, compute_content_hash

The sign_entry() wrapper here is maintained because:
1. Migration of historical tests would be disruptive
2. The signing module provides the canonical implementation
3. Deprecation warnings are avoided to keep test output clean
"""

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
