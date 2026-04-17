"""
Unit tests for the cryptographic signing module.

All tests are synchronous and self-contained.  They exercise the public API of
core.signing using isolated KeyStore instances so they never touch disk, the
database, or the global singleton keystore.
"""

import os
from typing import Any

import pytest

# â”€â”€ Minimal env so config initialises without a .env file â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

from datetime import UTC

from core.signing import (
    AgentKeyPair,
    KeyStore,
    SignedEntry,
    compute_content_hash,
    sign_content,
    verify_entry,
)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Fixtures
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@pytest.fixture
def keystore() -> KeyStore:
    """
    A fresh KeyStore backed by the test SIGNING_KEY environment variable.
    Each test receives its own instance so there is no cross-test key pollution.
    """
    return KeyStore()


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Round-trip / verification
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_sign_and_verify_roundtrip(keystore: KeyStore) -> None:
    """Signing content and then verifying it must return True."""
    content = {"finding": "ela_analysis", "confidence": 0.87}
    entry: SignedEntry = sign_content("agent1_image", content, keystore=keystore)

    # The key was just created in sign_content â€” it must be in the store now
    assert verify_entry(entry, keystore=keystore) is True


def test_tampered_content_fails_verification(keystore: KeyStore) -> None:
    """
    After signing, changing the content dict must cause verify_entry to
    return False (hash mismatch detected).
    """
    content = {"finding": "ela_analysis", "confidence": 0.87}
    entry = sign_content("agent1_image", content, keystore=keystore)

    # Tamper: replace the content with something different
    tampered_entry = SignedEntry(
        content={"finding": "ela_analysis", "confidence": 0.99},  # changed
        content_hash=entry.content_hash,   # original hash â€” will mismatch
        signature=entry.signature,
        agent_id=entry.agent_id,
        timestamp_utc=entry.timestamp_utc,
    )

    assert verify_entry(tampered_entry, keystore=keystore) is False


def test_tampered_hash_fails_verification(keystore: KeyStore) -> None:
    """Replacing the content_hash with a wrong value must also fail verification."""
    content = {"finding": "noise_analysis", "score": 0.5}
    entry = sign_content("agent2_audio", content, keystore=keystore)

    wrong_hash_entry = SignedEntry(
        content=entry.content,
        content_hash="0" * 64,  # clearly wrong
        signature=entry.signature,
        agent_id=entry.agent_id,
        timestamp_utc=entry.timestamp_utc,
    )

    assert verify_entry(wrong_hash_entry, keystore=keystore) is False


def test_unknown_agent_fails_verification() -> None:
    """
    verify_entry should return False when the agent_id is not in the keystore
    (no key available to verify against).
    """
    ks_signer = KeyStore()
    content = {"data": "secret"}
    entry = sign_content("agent_known", content, keystore=ks_signer)

    # A different keystore that has never seen this agent
    ks_verifier = KeyStore()
    assert verify_entry(entry, keystore=ks_verifier) is False


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Determinism
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_deterministic_keys_same_signing_key() -> None:
    """
    Two KeyStore instances initialised from the same SIGNING_KEY env variable
    must produce identical public keys for the same agent_id.
    """
    ks1 = KeyStore()
    ks2 = KeyStore()

    kp1 = ks1.get_or_create("agent1_image")
    kp2 = ks2.get_or_create("agent1_image")

    pem1 = kp1.get_public_key_pem()
    pem2 = kp2.get_public_key_pem()

    assert pem1 == pem2, (
        "Two KeyStores with the same signing_key must derive identical keys"
    )


def test_deterministic_keys_cross_keystore_verification() -> None:
    """
    A signature produced by ks1 must verify correctly against the matching public
    key in ks2 (both derived from the same SIGNING_KEY env variable).

    Note: ECDSA P-256 signatures are probabilistic (random k-nonce per RFC 6979
    is library-optional), so raw signature bytes are NOT guaranteed to be equal
    across two separate sign() calls.  What IS deterministic is the key pair
    itself â€” so we test cross-keystore verification rather than byte equality.
    """
    from datetime import datetime
    ts = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

    ks1 = KeyStore()
    ks2 = KeyStore()
    content = {"check": "determinism", "value": 42}

    # Sign with ks1
    entry = sign_content("agent3_object", content, keystore=ks1, timestamp=ts)

    # Materialise the same key in ks2 (same seed â†’ same private/public key)
    ks2.get_or_create("agent3_object")

    # Verification with ks2 must succeed because the public key is identical
    assert verify_entry(entry, keystore=ks2) is True
    # And the content_hash is deterministic
    assert entry.content_hash == compute_content_hash(content)


def test_different_agents_different_keys() -> None:
    """
    The keys derived for Agent1 and Agent2 must be distinct (different seeds).
    """
    ks = KeyStore()
    kp1 = ks.get_or_create("agent1_image")
    kp2 = ks.get_or_create("agent2_audio")

    assert kp1.get_public_key_pem() != kp2.get_public_key_pem()


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# compute_content_hash
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_compute_content_hash_is_deterministic() -> None:
    """The same dict must always produce the same hex hash."""
    content = {"alpha": 1, "beta": "two", "gamma": [3, 4]}
    h1 = compute_content_hash(content)
    h2 = compute_content_hash(content)
    assert h1 == h2


def test_compute_content_hash_is_hex_string() -> None:
    """compute_content_hash must return a 64-character lowercase hex string (SHA-256)."""
    h = compute_content_hash({"x": 1})
    assert isinstance(h, str)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


@pytest.mark.parametrize(("content_a", "content_b"), [
    ({"key": "value1"}, {"key": "value2"}),
    ({"a": 1}, {"b": 1}),
    ({"nested": {"x": 1}}, {"nested": {"x": 2}}),
    ({}, {"key": "nonempty"}),
])
def test_compute_content_hash_different_for_different_content(
    content_a: dict[str, Any],
    content_b: dict[str, Any],
) -> None:
    """Different dicts must produce different hashes."""
    assert compute_content_hash(content_a) != compute_content_hash(content_b)


def test_compute_content_hash_key_order_independent() -> None:
    """
    Hash must be the same regardless of Python dict insertion order,
    because JSON serialisation uses sort_keys=True.
    """
    d1 = {"z": 1, "a": 2}
    d2 = {"a": 2, "z": 1}
    assert compute_content_hash(d1) == compute_content_hash(d2)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# SignedEntry structure
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_signed_entry_has_expected_fields(keystore: KeyStore) -> None:
    """sign_content must return a SignedEntry with all required fields populated."""
    content = {"agent": "test", "result": "pass"}
    entry = sign_content("agent5_metadata", content, keystore=keystore)

    assert entry.content == content
    assert isinstance(entry.content_hash, str)
    assert len(entry.content_hash) == 64
    assert isinstance(entry.signature, str)
    assert len(entry.signature) > 0
    assert entry.agent_id == "agent5_metadata"
    assert entry.timestamp_utc is not None


def test_signed_entry_roundtrip_dict_serialisation(keystore: KeyStore) -> None:
    """SignedEntry.to_dict() and SignedEntry.from_dict() must roundtrip correctly."""
    content = {"payload": "roundtrip_test"}
    entry = sign_content("agent1_image", content, keystore=keystore)

    as_dict = entry.to_dict()
    restored = SignedEntry.from_dict(as_dict)

    assert restored.content == entry.content
    assert restored.content_hash == entry.content_hash
    assert restored.signature == entry.signature
    assert restored.agent_id == entry.agent_id


def test_agent_key_pair_generate_is_unique() -> None:
    """Two randomly generated key pairs must differ."""
    kp1 = AgentKeyPair.generate("agent_r1")
    kp2 = AgentKeyPair.generate("agent_r2")
    assert kp1.get_public_key_pem() != kp2.get_public_key_pem()


def test_agent_key_pair_generate_from_same_seed_is_identical() -> None:
    """Two AgentKeyPairs generated from the same seed must be identical."""
    seed = b"\xab" * 32
    kp1 = AgentKeyPair.generate("agent_s", seed=seed)
    kp2 = AgentKeyPair.generate("agent_s", seed=seed)
    assert kp1.get_public_key_pem() == kp2.get_public_key_pem()


