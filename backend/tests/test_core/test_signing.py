"""
Signing Module Tests
====================

Tests for cryptographic signing and verification.
"""

import pytest
from datetime import datetime, timezone

from core.signing import (
    AgentKeyPair,
    KeyStore,
    SignedEntry,
    compute_content_hash,
    sign_content,
    verify_entry,
)


class TestAgentKeyPair:
    """Tests for AgentKeyPair class."""
    
    def test_generate_creates_key_pair(self):
        """Test that generate creates a valid key pair."""
        key_pair = AgentKeyPair.generate("test_agent")
        
        assert key_pair.agent_id == "test_agent"
        assert key_pair.private_key is not None
        assert key_pair.public_key is not None
    
    def test_get_public_key_pem(self):
        """Test getting public key in PEM format."""
        key_pair = AgentKeyPair.generate("test_agent")
        pem = key_pair.get_public_key_pem()
        
        assert "-----BEGIN PUBLIC KEY-----" in pem
        assert "-----END PUBLIC KEY-----" in pem
    
    def test_different_agents_have_different_keys(self):
        """Test that different agents get different keys."""
        key_pair_1 = AgentKeyPair.generate("agent_1")
        key_pair_2 = AgentKeyPair.generate("agent_2")
        
        pem_1 = key_pair_1.get_public_key_pem()
        pem_2 = key_pair_2.get_public_key_pem()
        
        assert pem_1 != pem_2


class TestKeyStore:
    """Tests for KeyStore class."""
    
    def test_get_or_create_creates_new_key(self):
        """Test get_or_create creates a new key for unknown agent."""
        keystore = KeyStore()
        key_pair = keystore.get_or_create("new_agent")
        
        assert key_pair is not None
        assert key_pair.agent_id == "new_agent"
    
    def test_get_or_create_returns_same_key(self):
        """Test get_or_create returns same key for same agent."""
        keystore = KeyStore()
        key_pair_1 = keystore.get_or_create("agent")
        key_pair_2 = keystore.get_or_create("agent")
        
        assert key_pair_1 is key_pair_2
        pem_1 = key_pair_1.get_public_key_pem()
        pem_2 = key_pair_2.get_public_key_pem()
        assert pem_1 == pem_2
    
    def test_get_returns_none_for_unknown_agent(self):
        """Test get returns None for unknown agent."""
        keystore = KeyStore()
        result = keystore.get("unknown_agent")
        
        assert result is None
    
    def test_clear_removes_all_keys(self):
        """Test clear removes all stored keys."""
        keystore = KeyStore()
        keystore.get_or_create("agent_1")
        keystore.get_or_create("agent_2")
        
        keystore.clear()
        
        assert keystore.get("agent_1") is None
        assert keystore.get("agent_2") is None


class TestComputeContentHash:
    """Tests for compute_content_hash function."""
    
    def test_hash_is_deterministic(self):
        """Test that same content produces same hash."""
        content = {"key": "value", "number": 42}
        
        hash_1 = compute_content_hash(content)
        hash_2 = compute_content_hash(content)
        
        assert hash_1 == hash_2
    
    def test_different_content_different_hash(self):
        """Test that different content produces different hash."""
        content_1 = {"key": "value1"}
        content_2 = {"key": "value2"}
        
        hash_1 = compute_content_hash(content_1)
        hash_2 = compute_content_hash(content_2)
        
        assert hash_1 != hash_2
    
    def test_key_order_doesnt_matter(self):
        """Test that key order doesn't affect hash."""
        content_1 = {"a": 1, "b": 2}
        content_2 = {"b": 2, "a": 1}
        
        hash_1 = compute_content_hash(content_1)
        hash_2 = compute_content_hash(content_2)
        
        assert hash_1 == hash_2
    
    def test_hash_is_sha256_hex(self):
        """Test that hash is 64 character hex string (SHA-256)."""
        content = {"test": "data"}
        hash_result = compute_content_hash(content)
        
        assert len(hash_result) == 64
        assert all(c in "0123456789abcdef" for c in hash_result)


class TestSignContent:
    """Tests for sign_content function."""
    
    def test_sign_content_returns_signed_entry(self):
        """Test that sign_content returns a valid SignedEntry."""
        keystore = KeyStore()
        content = {"action": "analyze", "target": "image.jpg"}
        
        entry = sign_content("test_agent", content, keystore=keystore)
        
        assert isinstance(entry, SignedEntry)
        assert entry.content == content
        assert entry.agent_id == "test_agent"
        assert entry.content_hash == compute_content_hash(content)
        assert len(entry.signature) > 0
        assert isinstance(entry.timestamp_utc, datetime)
    
    def test_sign_content_uses_provided_timestamp(self):
        """Test that sign_content uses provided timestamp."""
        keystore = KeyStore()
        content = {"test": "data"}
        timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        entry = sign_content("agent", content, keystore=keystore, timestamp=timestamp)
        
        assert entry.timestamp_utc == timestamp


class TestVerifyEntry:
    """Tests for verify_entry function."""
    
    def test_sign_and_verify_valid_entry(self):
        """Test that a valid entry verifies successfully."""
        keystore = KeyStore()
        content = {"action": "analyze", "data": "test"}
        
        entry = sign_content("test_agent", content, keystore=keystore)
        result = verify_entry(entry, keystore=keystore)
        
        assert result is True
    
    def test_tampered_content_fails_verification(self):
        """Test that tampered content fails verification."""
        keystore = KeyStore()
        content = {"action": "analyze"}
        
        entry = sign_content("test_agent", content, keystore=keystore)
        
        # Tamper with content
        entry.content["action"] = "modified"
        
        result = verify_entry(entry, keystore=keystore)
        
        assert result is False
    
    def test_tampered_signature_fails_verification(self):
        """Test that a tampered signature fails verification."""
        keystore = KeyStore()
        content = {"action": "analyze"}
        
        entry = sign_content("test_agent", content, keystore=keystore)
        
        # Tamper with signature
        entry.signature = "0" * 128
        
        result = verify_entry(entry, keystore=keystore)
        
        assert result is False
    
    def test_different_agent_key_fails_verification(self):
        """Test that verification fails if agent key is not in keystore."""
        keystore_1 = KeyStore()
        keystore_2 = KeyStore()  # Different keystore
        
        content = {"action": "analyze"}
        
        # Sign with one keystore
        entry = sign_content("test_agent", content, keystore=keystore_1)
        
        # Verify with different keystore (no key for agent)
        result = verify_entry(entry, keystore=keystore_2)
        
        assert result is False
    
    def test_tampered_content_hash_fails_verification(self):
        """Test that tampered content_hash fails verification."""
        keystore = KeyStore()
        content = {"action": "analyze"}
        
        entry = sign_content("test_agent", content, keystore=keystore)
        
        # Tamper with content_hash
        entry.content_hash = "0" * 64
        
        result = verify_entry(entry, keystore=keystore)
        
        assert result is False
    
    def test_tampered_timestamp_fails_verification(self):
        """Test that tampered timestamp fails verification."""
        keystore = KeyStore()
        content = {"action": "analyze"}
        
        entry = sign_content("test_agent", content, keystore=keystore)
        
        # Tamper with timestamp
        entry.timestamp_utc = datetime(2020, 1, 1, tzinfo=timezone.utc)
        
        result = verify_entry(entry, keystore=keystore)
        
        assert result is False


class TestSignedEntry:
    """Tests for SignedEntry dataclass."""
    
    def test_to_dict_and_from_dict(self):
        """Test serialization and deserialization."""
        keystore = KeyStore()
        content = {"test": "data"}
        
        entry = sign_content("agent", content, keystore=keystore)
        
        # Convert to dict and back
        entry_dict = entry.to_dict()
        restored = SignedEntry.from_dict(entry_dict)
        
        assert restored.content == entry.content
        assert restored.content_hash == entry.content_hash
        assert restored.signature == entry.signature
        assert restored.agent_id == entry.agent_id
        assert restored.timestamp_utc == entry.timestamp_utc