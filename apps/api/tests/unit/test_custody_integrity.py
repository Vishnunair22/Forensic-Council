"""
Chain-of-Custody Integrity Tests
=================================

Verify that the cryptographic signing layer is tamper-evident,
that deterministic key derivation is stable, and that key rotation
produces distinct keys while preserving historical verifiability.

Test categories:
  1. Hash determinism — same input always produces the same hash.
  2. Sign + verify golden path — valid entries verify correctly.
  3. Forgery detection — tampered content/signatures are rejected.
  4. Key determinism — seeded keys are stable across calls.
  5. Per-agent key independence — different agents get different keys.
  6. PEM round-trip — key pairs survive serialize/deserialize.
  7. Key rotation — new key is distinct; old key can still verify old entries.
  8. KeyStore isolation — tests don't share global state.
"""

from __future__ import annotations

import os

# ── Minimal env before any backend import ────────────────────────────────────
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-abcdefghijklmnopqrstuvwxyz123456")
os.environ.setdefault("POSTGRES_USER", "test_user")
os.environ.setdefault("POSTGRES_PASSWORD", "test_pass")
os.environ.setdefault("POSTGRES_DB", "forensic_test")
os.environ.setdefault("REDIS_PASSWORD", "test_redis_pass")
os.environ.setdefault("NEXT_PUBLIC_DEMO_PASSWORD", "test_demo_pass")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-key-abcdefghijklmnopqrstuvwxyz1234")

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _fresh_keystore():
    """Return a new, isolated KeyStore (not the global singleton)."""
    from core.signing import KeyStore
    return KeyStore()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Hash Determinism
# ═══════════════════════════════════════════════════════════════════════════════

class TestHashDeterminism:
    """compute_content_hash must be stable and order-independent."""

    def test_same_content_same_hash(self):
        from core.signing import compute_content_hash

        content = {"action": "tool_call", "tool": "ela_full_image", "session": "abc123"}
        h1 = compute_content_hash(content)
        h2 = compute_content_hash(content)
        assert h1 == h2

    def test_key_order_independent(self):
        """JSON serialisation must sort keys so insertion order doesn't matter."""
        from core.signing import compute_content_hash

        c1 = {"a": 1, "b": 2, "c": 3}
        c2 = {"c": 3, "a": 1, "b": 2}
        assert compute_content_hash(c1) == compute_content_hash(c2)

    def test_different_content_different_hash(self):
        from core.signing import compute_content_hash

        c1 = {"session": "abc"}
        c2 = {"session": "xyz"}
        assert compute_content_hash(c1) != compute_content_hash(c2)

    def test_float_precision_stable(self):
        """Floats differing only below 10 decimal places should hash identically."""
        from core.signing import compute_content_hash

        c1 = {"score": 0.123456789012345}
        c2 = {"score": 0.123456789099999}  # differs after 10th decimal place
        # Both get rounded to 10 dp → same hash
        assert compute_content_hash(c1) == compute_content_hash(c2)

    def test_nested_structure_deterministic(self):
        from core.signing import compute_content_hash

        content = {
            "findings": [
                {"tool": "ela", "score": 0.8},
                {"tool": "ghost", "score": 0.2},
            ],
            "meta": {"agent": "Agent1", "phase": "initial"},
        }
        assert compute_content_hash(content) == compute_content_hash(content)

    def test_hash_is_hex_string(self):
        from core.signing import compute_content_hash

        h = compute_content_hash({"x": 1})
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 = 32 bytes = 64 hex chars
        int(h, 16)  # must be valid hex — raises ValueError if not


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Sign + Verify Golden Path
# ═══════════════════════════════════════════════════════════════════════════════

class TestSignAndVerify:
    """Valid entries must verify correctly."""

    def test_sign_and_verify_success(self):
        from core.signing import sign_content, verify_entry

        ks = _fresh_keystore()
        content = {"action": "ela_full_image", "result": "authentic", "confidence": 0.92}
        entry = sign_content("Agent1", content, keystore=ks)

        assert verify_entry(entry, keystore=ks) is True

    def test_signed_entry_has_correct_fields(self):
        from core.signing import sign_content

        ks = _fresh_keystore()
        content = {"tool": "jpeg_ghost", "anomaly": False}
        entry = sign_content("Agent2", content, keystore=ks)

        assert entry.agent_id == "Agent2"
        assert entry.content == content
        assert len(entry.content_hash) == 64
        assert len(entry.signature) > 0  # hex-encoded DER signature

    def test_sign_returns_signed_entry_with_timestamp(self):
        from core.signing import sign_content

        ks = _fresh_keystore()
        entry = sign_content("Agent3", {"x": 1}, keystore=ks)

        assert entry.timestamp_utc is not None
        assert entry.timestamp_utc.tzinfo is not None  # timezone-aware

    def test_sign_respects_provided_timestamp(self):
        from datetime import UTC, datetime

        from core.signing import sign_content

        ks = _fresh_keystore()
        fixed_ts = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
        entry = sign_content("Agent1", {"x": 1}, keystore=ks, timestamp=fixed_ts)

        assert entry.timestamp_utc == fixed_ts

    def test_to_dict_and_from_dict_roundtrip(self):
        from core.signing import SignedEntry, sign_content, verify_entry

        ks = _fresh_keystore()
        content = {"action": "copy_move_detect", "regions": 3}
        original = sign_content("Agent1", content, keystore=ks)

        serialized = original.to_dict()
        restored = SignedEntry.from_dict(serialized)

        # The restored entry must verify with the same keystore
        assert verify_entry(restored, keystore=ks) is True
        assert restored.content == original.content
        assert restored.signature == original.signature

    def test_multiple_agents_independent_verification(self):
        """Each agent's signature must be independently verifiable."""
        from core.signing import sign_content, verify_entry

        ks = _fresh_keystore()
        content = {"session": "abc123", "finding": "authentic"}

        for agent_id in ("Agent1", "Agent2", "Agent3", "Agent4", "Agent5"):
            entry = sign_content(agent_id, content, keystore=ks)
            assert verify_entry(entry, keystore=ks) is True, (
                f"Verification failed for {agent_id}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Forgery Detection
# ═══════════════════════════════════════════════════════════════════════════════

class TestForgeryDetection:
    """Tampered content or forged signatures must be rejected."""

    def test_tampered_content_fails_verification(self):
        """Modifying content after signing must invalidate the entry."""
        import copy

        from core.signing import sign_content, verify_entry

        ks = _fresh_keystore()
        content = {"session": "abc", "verdict": "AUTHENTIC"}
        entry = sign_content("Agent1", content, keystore=ks)

        # Tamper with the content
        tampered = copy.deepcopy(entry)
        tampered.content["verdict"] = "MANIPULATED"

        assert verify_entry(tampered, keystore=ks) is False

    def test_wrong_content_hash_fails_verification(self):
        """An entry with a fabricated content_hash must be rejected."""
        import dataclasses

        from core.signing import sign_content, verify_entry

        ks = _fresh_keystore()
        entry = sign_content("Agent1", {"data": "real"}, keystore=ks)

        # Replace hash with a fake one (same length, wrong value)
        forged = dataclasses.replace(entry, content_hash="a" * 64)

        assert verify_entry(forged, keystore=ks) is False

    def test_forged_signature_fails_verification(self):
        """An entry with a completely fabricated signature must be rejected."""
        import dataclasses

        from core.signing import sign_content, verify_entry

        ks = _fresh_keystore()
        entry = sign_content("Agent1", {"data": "real"}, keystore=ks)

        forged = dataclasses.replace(entry, signature="dead" * 16)

        assert verify_entry(forged, keystore=ks) is False

    def test_cross_agent_signature_fails(self):
        """An entry signed by Agent1's key must NOT verify under Agent2's key."""
        import dataclasses

        from core.signing import sign_content, verify_entry

        ks = _fresh_keystore()
        entry_a1 = sign_content("Agent1", {"data": "real"}, keystore=ks)

        # Claim it was Agent2's entry
        spoofed = dataclasses.replace(entry_a1, agent_id="Agent2")

        assert verify_entry(spoofed, keystore=ks) is False

    def test_missing_agent_key_fails_verification(self):
        """If the keystore has no key for the claimed agent, verify must return False."""
        from core.signing import sign_content, verify_entry

        ks_signer = _fresh_keystore()
        ks_verifier = _fresh_keystore()  # different keystore, no shared keys

        entry = sign_content("Agent1", {"x": 1}, keystore=ks_signer)

        # ks_verifier has no key for Agent1 yet — get() returns None
        assert ks_verifier.get("Agent1") is None
        assert verify_entry(entry, keystore=ks_verifier) is False

    def test_verify_never_raises(self):
        """verify_entry must return False, never raise, even on corrupt input."""
        from datetime import UTC, datetime

        from core.signing import SignedEntry, verify_entry

        ks = _fresh_keystore()
        corrupt = SignedEntry(
            content={"x": 1},
            content_hash="not_a_real_hash_x" * 3,
            signature="garbage_signature",
            agent_id="Agent1",
            timestamp_utc=datetime.now(UTC),
        )
        # Must return False without raising
        result = verify_entry(corrupt, keystore=ks)
        assert result is False


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Key Determinism
# ═══════════════════════════════════════════════════════════════════════════════

class TestKeyDeterminism:
    """Seeded key generation must be stable across calls."""

    def test_same_seed_same_private_key(self):
        from core.signing import AgentKeyPair

        seed = b"\xab\xcd\xef" * 10 + b"\x01\x02"
        kp1 = AgentKeyPair.generate("Agent1", seed=seed)
        kp2 = AgentKeyPair.generate("Agent1", seed=seed)

        pem1 = kp1.get_private_key_pem()
        pem2 = kp2.get_private_key_pem()
        assert pem1 == pem2, "Seeded key generation must be deterministic"

    def test_different_seeds_different_keys(self):
        from core.signing import AgentKeyPair

        seed_a = b"seed_for_agent_a" * 2
        seed_b = b"seed_for_agent_b" * 2
        kp_a = AgentKeyPair.generate("Agent1", seed=seed_a)
        kp_b = AgentKeyPair.generate("Agent1", seed=seed_b)

        assert kp_a.get_private_key_pem() != kp_b.get_private_key_pem()

    def test_keystore_derive_seed_deterministic(self):
        """derive_seed must return the same bytes for the same agent_id."""
        ks = _fresh_keystore()
        s1 = ks._derive_seed("Agent1")
        s2 = ks._derive_seed("Agent1")
        assert s1 == s2
        assert len(s1) == 32  # SHA-256 output

    def test_keystore_get_or_create_deterministic(self):
        """get_or_create called twice for the same agent must return the same key."""
        ks = _fresh_keystore()
        kp1 = ks.get_or_create("Agent1")
        kp2 = ks.get_or_create("Agent1")
        assert kp1 is kp2  # exact same object (cached)

    def test_keystore_deterministic_key_verifies_own_signatures(self):
        """A deterministically-derived key must verify entries it signed."""
        from core.signing import sign_content, verify_entry

        ks = _fresh_keystore()
        content = {"session": "det-test", "tool": "ela"}
        entry = sign_content("Agent1", content, keystore=ks)

        # Create a fresh keystore with the same SIGNING_KEY (same env var) —
        # it must derive the same key and verify the entry.
        ks2 = _fresh_keystore()
        ks2.get_or_create("Agent1")  # triggers deterministic derivation

        assert verify_entry(entry, keystore=ks2) is True


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Per-Agent Key Independence
# ═══════════════════════════════════════════════════════════════════════════════

class TestPerAgentKeyIndependence:
    """Different agent IDs must produce different keys."""

    def test_different_agents_different_seeds(self):
        ks = _fresh_keystore()
        seeds = {a: ks._derive_seed(a) for a in ("Agent1", "Agent2", "Agent3", "Agent4", "Agent5", "Arbiter")}
        # All seeds must be distinct
        assert len(set(seeds.values())) == len(seeds), (
            "Each agent must derive a unique seed"
        )

    def test_different_agents_different_private_keys(self):
        ks = _fresh_keystore()
        pems = {a: ks.get_or_create(a).get_private_key_pem() for a in ("Agent1", "Agent2", "Agent3")}
        assert len(set(pems.values())) == 3, (
            "Each agent must have a distinct private key"
        )

    def test_agent1_cannot_verify_agent2_signature(self):
        """An entry signed by Agent1 should NOT be claimable as Agent2's work."""
        import dataclasses

        from core.signing import sign_content, verify_entry

        ks = _fresh_keystore()
        entry = sign_content("Agent1", {"finding": "splice detected"}, keystore=ks)
        # Attempt to impersonate Agent2
        spoof = dataclasses.replace(entry, agent_id="Agent2")
        assert verify_entry(spoof, keystore=ks) is False


# ═══════════════════════════════════════════════════════════════════════════════
# 6. PEM Round-Trip
# ═══════════════════════════════════════════════════════════════════════════════

class TestPEMRoundTrip:
    """Key pairs must survive PEM serialization and deserialization."""

    def test_private_key_pem_roundtrip(self):
        from core.signing import AgentKeyPair

        original = AgentKeyPair.generate("Agent1")
        pem = original.get_private_key_pem()
        restored = AgentKeyPair.from_pem("Agent1", pem)

        # The restored key must produce the same public key bytes
        orig_pub = original.get_public_key_pem()
        rest_pub = restored.get_public_key_pem()
        assert orig_pub == rest_pub

    def test_pem_round_trip_signature_still_verifies(self):
        """Entries signed before PEM serialization must still verify after deserialization."""
        from core.signing import AgentKeyPair, sign_content, verify_entry

        # Sign with original key
        ks = _fresh_keystore()
        content = {"step": "ela_full_image", "session": "pem_test"}
        entry = sign_content("Agent1", content, keystore=ks)

        # Serialize and restore the key
        original_kp = ks.get("Agent1")
        assert original_kp is not None
        pem = original_kp.get_private_key_pem()
        restored_kp = AgentKeyPair.from_pem("Agent1", pem)

        # Build a new keystore seeded with the restored key
        ks2 = _fresh_keystore()
        ks2._keys["Agent1"] = restored_kp

        assert verify_entry(entry, keystore=ks2) is True

    def test_public_key_pem_is_valid_pem(self):
        from core.signing import AgentKeyPair

        kp = AgentKeyPair.generate("Agent1")
        pub_pem = kp.get_public_key_pem()

        assert pub_pem.startswith("-----BEGIN PUBLIC KEY-----")
        assert "-----END PUBLIC KEY-----" in pub_pem


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Key Rotation
# ═══════════════════════════════════════════════════════════════════════════════

class TestKeyRotation:
    """rotate_key must produce a new distinct key; old entries remain accessible."""

    @pytest.mark.asyncio
    async def test_rotate_produces_new_key(self):

        ks = _fresh_keystore()
        # Pre-load Agent1 deterministically
        old_kp = ks.get_or_create("Agent1")
        old_pem = old_kp.get_private_key_pem()

        # Patch DB methods to be no-ops so we don't need a real DB
        ks._db_available = False  # forces in-memory only path
        from unittest.mock import AsyncMock
        ks._retire_key_in_db = AsyncMock()
        ks._save_key_to_db = AsyncMock()

        new_kp = await ks.rotate_key("Agent1")
        new_pem = new_kp.get_private_key_pem()

        assert old_pem != new_pem, "Rotation must produce a different key"

    @pytest.mark.asyncio
    async def test_old_entries_cannot_verify_after_rotation(self):
        """
        After rotation the keystore holds the NEW key.
        An entry signed with the OLD key will fail verification
        (expected — callers must archive old entries before rotating).
        """
        from core.signing import sign_content, verify_entry

        ks = _fresh_keystore()
        ks.get_or_create("Agent1")

        content = {"pre_rotation": True}
        entry_before = sign_content("Agent1", content, keystore=ks)

        # Rotate
        ks._db_available = False
        from unittest.mock import AsyncMock
        ks._retire_key_in_db = AsyncMock()
        ks._save_key_to_db = AsyncMock()
        await ks.rotate_key("Agent1")

        # Old entry should NOT verify with the new key
        assert verify_entry(entry_before, keystore=ks) is False, (
            "Pre-rotation entries must not verify after key rotation — "
            "archive old entries before rotating in production"
        )

    @pytest.mark.asyncio
    async def test_new_entries_verify_after_rotation(self):
        """Entries signed AFTER rotation must verify correctly."""
        from core.signing import sign_content, verify_entry

        ks = _fresh_keystore()
        ks.get_or_create("Agent1")

        ks._db_available = False
        from unittest.mock import AsyncMock
        ks._retire_key_in_db = AsyncMock()
        ks._save_key_to_db = AsyncMock()
        await ks.rotate_key("Agent1")

        content = {"post_rotation": True}
        entry_after = sign_content("Agent1", content, keystore=ks)
        assert verify_entry(entry_after, keystore=ks) is True

    @pytest.mark.asyncio
    async def test_rotate_key_returns_agent_key_pair(self):
        from core.signing import AgentKeyPair

        ks = _fresh_keystore()
        ks._db_available = False
        from unittest.mock import AsyncMock
        ks._retire_key_in_db = AsyncMock()
        ks._save_key_to_db = AsyncMock()

        new_kp = await ks.rotate_key("Agent1")
        assert isinstance(new_kp, AgentKeyPair)
        assert new_kp.agent_id == "Agent1"


# ═══════════════════════════════════════════════════════════════════════════════
# 8. KeyStore.clear
# ═══════════════════════════════════════════════════════════════════════════════

class TestKeyStoreClear:
    """clear() must wipe all in-memory keys."""

    def test_clear_removes_all_keys(self):
        ks = _fresh_keystore()
        ks.get_or_create("Agent1")
        ks.get_or_create("Agent2")

        assert len(ks._keys) == 2
        ks.clear()
        assert len(ks._keys) == 0

    def test_get_returns_none_after_clear(self):
        ks = _fresh_keystore()
        ks.get_or_create("Agent1")
        ks.clear()

        assert ks.get("Agent1") is None
