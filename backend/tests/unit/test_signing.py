"""
Unit tests for core/signing.py
"""

import pytest
from core.signing import KeyStore, sign_content, SignedEntry


class TestSigning:
    """Test cases for cryptographic signing."""

    def test_key_generation(self):
        """Test that keys are generated correctly from signing key."""
        keystore = KeyStore()
        
        # Test that private key is generated
        assert keystore.private_key is not None

    def test_sign_content(self):
        """Test content signing."""
        keystore = KeyStore()
        content = "test content for signing"
        
        signature = keystore.sign(content)
        
        assert signature is not None
        assert isinstance(signature, str)
        assert len(signature) > 0

    def test_verify_signature(self):
        """Test signature verification."""
        keystore = KeyStore()
        content = "test content for signing"
        
        signature = keystore.sign(content)
        
        # Verify with correct content
        assert keystore.verify(content, signature) is True
        
        # Verify with wrong content
        assert keystore.verify("wrong content", signature) is False

    def test_sign_content_function(self):
        """Test the sign_content function."""
        signing_key = "a" * 64
        content = "test content"
        
        signature = sign_content(content, signing_key)
        
        assert signature is not None
        assert isinstance(signature, str)

    def test_deterministic_signing(self):
        """Test that same content produces same signature."""
        signing_key = "a" * 64
        content = "deterministic test"
        
        sig1 = sign_content(content, signing_key)
        sig2 = sign_content(content, signing_key)
        
        assert sig1 == sig2

    def test_different_content_different_signature(self):
        """Test that different content produces different signatures."""
        signing_key = "a" * 64
        
        sig1 = sign_content("content 1", signing_key)
        sig2 = sign_content("content 2", signing_key)
        
        assert sig1 != sig2


class TestSignedEntry:
    """Test cases for SignedEntry."""

    def test_signed_entry_creation(self):
        """Test creating a signed entry."""
        entry = SignedEntry(
            content={"test": "data"},
            content_hash="abc123",
            signature="signature123",
            agent_id="Agent1",
        )
        
        assert entry.content["test"] == "data"
        assert entry.content_hash == "abc123"

    def test_signed_entry_to_dict(self):
        """Test signed entry serialization."""
        entry = SignedEntry(
            content={"test": "data"},
            content_hash="abc123",
            signature="signature123",
            agent_id="Agent1",
        )
        
        data = entry.to_dict()
        
        assert "content" in data
        assert "content_hash" in data
        assert "signature" in data
        assert "agent_id" in data
