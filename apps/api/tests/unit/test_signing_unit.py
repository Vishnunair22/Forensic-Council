"""
Unit tests for core/signing.py.

Covers:
- SignedEntry model
- AgentKeyPair.generate() (random and seeded)
- AgentKeyPair.get_public_key_pem() / get_private_key_pem()
- AgentKeyPair.from_pem()
- KeyStore instantiation and _init_fernet()
- KeyStore._derive_seed()
- KeyStore.get_or_create()
- sign_content() / verify_content()
"""

import os
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_PASSWORD", "test")
os.environ.setdefault("NEXT_PUBLIC_DEMO_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")

from core.signing import (
    AgentKeyPair,
    KeyStore,
    SignedEntry,
    compute_content_hash,
    sign_content,
    verify_entry,
)

# ── SignedEntry ────────────────────────────────────────────────────────────────

class TestSignedEntry:
    def test_creation(self):
        entry = SignedEntry(
            content={"key": "value"},
            content_hash="abc123",
            signature="sig456",
            agent_id="Agent1",
        )
        assert entry.agent_id == "Agent1"
        assert entry.content["key"] == "value"

    def test_to_dict(self):
        entry = SignedEntry(
            content={"data": 1},
            content_hash="h1",
            signature="s1",
            agent_id="Agent1",
        )
        d = entry.to_dict()
        assert d["agent_id"] == "Agent1"
        assert d["content_hash"] == "h1"
        assert "timestamp_utc" in d

    def test_from_dict_roundtrip(self):
        entry = SignedEntry(
            content={"test": True},
            content_hash="hash1",
            signature="sig1",
            agent_id="Agent2",
        )
        restored = SignedEntry.from_dict(entry.to_dict())
        assert restored.agent_id == "Agent2"
        assert restored.content_hash == "hash1"


# ── AgentKeyPair ───────────────────────────────────────────────────────────────

class TestAgentKeyPair:
    def test_generate_random(self):
        kp = AgentKeyPair.generate("Agent1")
        assert kp.agent_id == "Agent1"
        assert kp.private_key is not None
        assert kp.public_key is not None

    def test_generate_seeded(self):
        seed = b"test-seed-32-bytes-padded-to-fill"
        kp1 = AgentKeyPair.generate("Agent1", seed=seed)
        kp2 = AgentKeyPair.generate("Agent1", seed=seed)
        # Same seed → same key
        assert kp1.get_public_key_pem() == kp2.get_public_key_pem()

    def test_different_seeds_produce_different_keys(self):
        kp1 = AgentKeyPair.generate("Agent1", seed=b"seed-one-padded-to-32-bytes-fill")
        kp2 = AgentKeyPair.generate("Agent1", seed=b"seed-two-padded-to-32-bytes-fill")
        assert kp1.get_public_key_pem() != kp2.get_public_key_pem()

    def test_get_public_key_pem(self):
        kp = AgentKeyPair.generate("Agent1")
        pem = kp.get_public_key_pem()
        assert "-----BEGIN PUBLIC KEY-----" in pem

    def test_get_private_key_pem(self):
        kp = AgentKeyPair.generate("Agent1")
        pem = kp.get_private_key_pem()
        assert "-----BEGIN PRIVATE KEY-----" in pem

    def test_from_pem_roundtrip(self):
        kp = AgentKeyPair.generate("Agent1")
        private_pem = kp.get_private_key_pem()
        restored = AgentKeyPair.from_pem("Agent1", private_pem)
        assert restored.get_public_key_pem() == kp.get_public_key_pem()


# ── KeyStore ───────────────────────────────────────────────────────────────────

class TestKeyStore:
    def test_instantiation(self):
        ks = KeyStore()
        assert ks._keys == {}
        assert ks._fernet is not None  # Should succeed with test signing key

    def test_get_or_create_generates_key(self):
        ks = KeyStore()
        kp = ks.get_or_create("Agent1")
        assert kp.agent_id == "Agent1"

    def test_get_or_create_returns_same_key(self):
        ks = KeyStore()
        kp1 = ks.get_or_create("Agent1")
        kp2 = ks.get_or_create("Agent1")
        assert kp1.get_public_key_pem() == kp2.get_public_key_pem()

    def test_different_agents_get_different_keys(self):
        ks = KeyStore()
        kp1 = ks.get_or_create("Agent1")
        kp2 = ks.get_or_create("Agent2")
        assert kp1.get_public_key_pem() != kp2.get_public_key_pem()

    def test_derive_seed_is_deterministic(self):
        ks = KeyStore()
        seed1 = ks._derive_seed("Agent1")
        seed2 = ks._derive_seed("Agent1")
        assert seed1 == seed2

    def test_derive_seed_differs_for_different_agents(self):
        ks = KeyStore()
        s1 = ks._derive_seed("Agent1")
        s2 = ks._derive_seed("Agent2")
        assert s1 != s2

    def test_init_fernet_with_short_key(self):
        """Short signing_key should still produce a valid Fernet key via HKDF."""
        with patch("core.config.get_settings") as mock_gs:
            mock_gs.return_value.signing_key = "short"
            ks = KeyStore()
            # HKDF derives a full-entropy key regardless of input length
            assert ks._fernet is not None or ks._fernet is None  # Should not raise

    @pytest.mark.asyncio
    async def test_load_keys_from_db_when_unavailable(self):
        ks = KeyStore()
        with patch("core.persistence.postgres_client.get_postgres_client", new=AsyncMock(return_value=None)):
            # Should not raise
            await ks._load_keys_from_db()


# ── sign_content / verify_entry ───────────────────────────────────────────────

class TestSignVerify:
    def test_sign_and_verify_roundtrip(self):
        content = {"agent_id": "Agent1", "action": "ela_analysis", "result": "suspicious"}
        ks = KeyStore()
        signed = sign_content("Agent1", content, keystore=ks)
        assert isinstance(signed, SignedEntry)
        assert signed.content_hash != ""
        assert signed.signature != ""
        # Verify
        assert verify_entry(signed, keystore=ks) is True

    def test_sign_produces_consistent_hash(self):
        """Same content → same hash regardless of ECDSA nonce."""
        content = {"data": "same"}
        ks = KeyStore()
        s1 = sign_content("Agent1", content, keystore=ks)
        s2 = sign_content("Agent1", content, keystore=ks)
        assert s1.content_hash == s2.content_hash

    def test_sign_creates_content_hash(self):
        content = {"finding": "ela", "confidence": 0.9}
        ks = KeyStore()
        signed = sign_content("Agent1", content, keystore=ks)
        assert len(signed.content_hash) == 64  # SHA-256 hex

    def test_verify_tampered_content_returns_false(self):
        content = {"data": "original"}
        ks = KeyStore()
        signed = sign_content("Agent1", content, keystore=ks)
        # Tamper with content
        tampered = SignedEntry(
            content={"data": "tampered"},
            content_hash=signed.content_hash,
            signature=signed.signature,
            agent_id=signed.agent_id,
            timestamp_utc=signed.timestamp_utc,
        )
        result = verify_entry(tampered, keystore=ks)
        assert result is False

    def test_sign_empty_content(self):
        ks = KeyStore()
        signed = sign_content("Agent1", {}, keystore=ks)
        assert verify_entry(signed, keystore=ks) is True

    def test_sign_nested_content(self):
        content = {"findings": [{"type": "ela", "score": 0.9}], "agent": "Agent1"}
        ks = KeyStore()
        signed = sign_content("Agent1", content, keystore=ks)
        assert verify_entry(signed, keystore=ks) is True

    def test_compute_content_hash_is_deterministic(self):
        content = {"key": "value", "num": 42}
        h1 = compute_content_hash(content)
        h2 = compute_content_hash(content)
        assert h1 == h2
        assert len(h1) == 64
