"""
Cryptographic Signing Module
============================

Provides ECDSA P-256 signing and verification for chain-of-custody entries.
Ensures tamper-evident audit trail for all forensic operations.

Key Management Strategy
-----------------------
Two modes of operation:

1. DB-backed independent keys (preferred):
   Each agent gets its own randomly-generated ECDSA P-256 key pair.
   Private keys are stored in PostgreSQL (encrypted at rest via Fernet
   using SIGNING_KEY as the Fernet key). This means compromising one
   agent's key does NOT compromise the others.

2. Deterministic derivation (fallback):
   When PostgreSQL is unavailable, all agent keys are derived from a
   single SIGNING_KEY via HMAC-SHA256. This preserves the ability to
   sign entries but carries the single-key risk documented below.

Key Rotation:
   Call rotate_agent_key(agent_id) to generate a new key pair and log
   a "KEY_ROTATION" custody entry signed by both old and new keys.
   The old key is retired but kept for verifying historical entries.

⚠️  UPGRADE NOTICE (v1.3.0 → v1.4.0):
    The HKDF key derivation now uses an explicit domain-separation salt.
    This changes the Fernet encryption key used to protect DB-stored agent
    private keys. Any keys stored under v1.3.0 cannot be decrypted after
    upgrading.

    Migration steps (run BEFORE deploying v1.4.0):
      1. Back up the agent_signing_keys table:
           pg_dump -t agent_signing_keys forensic_council > keys_backup.sql
      2. After deploying, the KeyStore will fall back to deterministic derivation
         on startup (DB keys can't be decrypted).
      3. Force key rotation for all agents:
           python -c "
           import asyncio
           from core.signing import get_keystore
           ks = get_keystore()
           async def rotate():
               await ks.initialize()
               for aid in ks._AGENT_IDS:
                   await ks.rotate_key(aid)
           asyncio.run(rotate())
           "
      4. Verify: the agent_signing_keys table now has fresh rows with is_active=true.
"""

import base64
import hashlib
import hmac as _hmac
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from typing import Any, cast

from cryptography.exceptions import InvalidSignature
from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from core.structured_logging import get_logger

logger = get_logger(__name__)


@dataclass
class SignedEntry:
    """
    A signed content entry for chain-of-custody.

    Attributes:
        content: The original content dict
        content_hash: SHA-256 hash of JSON-serialized content
        signature: ECDSA signature of (content_hash + timestamp_utc)
        agent_id: Identifier of the agent that signed
        timestamp_utc: UTC timestamp when signed
    """

    content: dict[str, Any]
    content_hash: str
    signature: str
    agent_id: str
    timestamp_utc: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "content": self.content,
            "content_hash": self.content_hash,
            "signature": self.signature,
            "agent_id": self.agent_id,
            "timestamp_utc": self.timestamp_utc.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SignedEntry":
        """Create from dictionary."""
        return cls(
            content=data["content"],
            content_hash=data["content_hash"],
            signature=data["signature"],
            agent_id=data["agent_id"],
            timestamp_utc=datetime.fromisoformat(data["timestamp_utc"])
            if isinstance(data["timestamp_utc"], str)
            else data["timestamp_utc"],
        )


@dataclass
class AgentKeyPair:
    """
    ECDSA P-256 key pair for an agent.

    Attributes:
        agent_id: Unique identifier for the agent
        private_key: ECDSA private key
        public_key: ECDSA public key
    """

    agent_id: str
    private_key: ec.EllipticCurvePrivateKey
    public_key: ec.EllipticCurvePublicKey

    @classmethod
    def generate(cls, agent_id: str, seed: bytes | None = None) -> "AgentKeyPair":
        """Generate a new ECDSA P-256 key pair for an agent, optionally from a seed."""
        curve = ec.SECP256R1()
        if seed:
            # Deterministic generation from seed.
            # P-256 group order n — the private key must be in [1, n-1].
            # We reduce the seed modulo (n-1) then add 1 to guarantee this range.
            # Using the actual group order (not 2^key_size) is required for
            # correctness and avoids the operator-precedence pitfall in the
            # original  expression.
            _P256_ORDER = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
            private_value = (int.from_bytes(seed, "big") % (_P256_ORDER - 1)) + 1
            private_key = ec.derive_private_key(private_value, curve, default_backend())
        else:
            private_key = ec.generate_private_key(curve, default_backend())

        return cls(
            agent_id=agent_id,
            private_key=private_key,
            public_key=private_key.public_key(),
        )

    def get_public_key_pem(self) -> str:
        """Get public key in PEM format for storage/transmission."""
        pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return pem.decode("utf-8")

    def get_private_key_pem(self) -> str:
        """Get private key in PEM format (for encrypted storage)."""
        pem = self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return pem.decode("utf-8")

    @classmethod
    def from_pem(cls, agent_id: str, private_key_pem: str) -> "AgentKeyPair":
        """Reconstruct a key pair from a PEM-encoded private key."""
        _loaded = serialization.load_pem_private_key(
            private_key_pem.encode("utf-8"),
            password=None,
            backend=default_backend(),
        )
        # load_pem_private_key returns a union of key types; cast to the
        # concrete type expected by AgentKeyPair (ECDSA P-256).
        private_key = cast(ec.EllipticCurvePrivateKey, _loaded)
        return cls(
            agent_id=agent_id,
            private_key=private_key,
            public_key=private_key.public_key(),
        )


class KeyStore:
    """
    Store for agent key pairs.

    Prefers DB-backed independent keys (PostgreSQL + Fernet encryption).
    Falls back to deterministic derivation from SIGNING_KEY when DB is
    unavailable (single-key risk — see module docstring).
    """

    _AGENT_IDS = ("Arbiter", "Agent1", "Agent2", "Agent3", "Agent4", "Agent5")

    def __init__(self) -> None:
        """Initialize the key store."""
        from core.config import get_settings

        self._settings = get_settings()
        self._keys: dict[str, AgentKeyPair] = {}
        self._db_available: bool = False
        self._fernet: Fernet | None = None
        self._init_fernet()

    def _init_fernet(self) -> None:
        """Initialize Fernet cipher from SIGNING_KEY for encrypting private keys at rest.

        Issue 2.2: Use HKDF (proper KDF with domain separation) instead of a
        single-round SHA-256, which provides no salt or iteration count.
        """
        try:
            raw = self._settings.signing_key.encode("utf-8")
            # HKDF gives us a proper 32-byte derived key with domain separation.
            # Even a short SIGNING_KEY produces a full-entropy Fernet key.
            derived = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b"forensic-council-keystore-v1-salt",  # Fixed domain-separation salt
                info=b"forensic-council-keystore-v1",
                backend=default_backend(),
            ).derive(raw)
            fernet_key = base64.urlsafe_b64encode(derived)
            self._fernet = Fernet(fernet_key)
        except Exception as e:
            logger.warning("Failed to initialize Fernet cipher for key encryption", error=str(e))
            self._fernet = None

    def _derive_seed(self, agent_id: str) -> bytes:
        """Derive a deterministic seed for an agent's key (fallback mode).

        Issue 2.1: Use explicit _hmac alias (imported at module level as
        `import hmac as _hmac`) to ensure correct name resolution.
        """
        master_key = self._settings.signing_key.encode("utf-8")
        return _hmac.new(master_key, agent_id.encode("utf-8"), hashlib.sha256).digest()

    # ------------------------------------------------------------------
    # DB-backed key storage
    # ------------------------------------------------------------------

    async def _load_keys_from_db(self) -> None:
        """Load all agent keys from PostgreSQL (encrypted with Fernet).

        Issue 2.3: Retry up to 3 times on transient errors before falling back
        to deterministic derivation, and emit a CRITICAL log so operators are
        notified of the degraded key-separation mode.
        """
        import asyncio

        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                from core.persistence.postgres_client import get_postgres_client

                pg = await get_postgres_client()
                if pg is None:
                    return

                rows = await pg.fetch(
                    "SELECT agent_id, encrypted_private_key_pem, is_active "
                    "FROM agent_signing_keys WHERE is_active = true"
                )
                if not rows:
                    return

                for row in rows:
                    agent_id = row["agent_id"]
                    encrypted_pem = row["encrypted_private_key_pem"]
                    try:
                        if self._fernet:
                            pem_bytes = self._fernet.decrypt(encrypted_pem.encode("utf-8"))
                        else:
                            logger.warning(
                                "Fernet unavailable, skipping stored key for agent",
                                agent_id=agent_id,
                            )
                            continue
                        key_pair = AgentKeyPair.from_pem(agent_id, pem_bytes.decode("utf-8"))
                        self._keys[agent_id] = key_pair
                    except Exception as e:
                        logger.warning(
                            "Failed to decrypt stored key for agent",
                            agent_id=agent_id,
                            error=str(e),
                        )

                self._db_available = True
                logger.info("Loaded agent keys from PostgreSQL", loaded=len(self._keys))
                return  # success — exit retry loop

            except Exception as e:
                last_error = e
                if attempt < 3:
                    logger.warning(
                        "PostgreSQL key load attempt failed, retrying",
                        attempt=attempt,
                        error=str(e),
                    )
                    await asyncio.sleep(0.5 * attempt)

        # All retries exhausted — fall back to deterministic derivation
        logger.critical(
            "Issue 2.3: All DB key-load attempts failed — falling back to deterministic "
            "key derivation from SIGNING_KEY. Key independence is REDUCED until the DB "
            "connection is restored and the key store is re-initialized.",
            error=str(last_error),
        )
        self._db_available = False

    async def _save_key_to_db(self, agent_id: str, key_pair: AgentKeyPair) -> None:
        """Save a single agent key to PostgreSQL (encrypted with Fernet)."""
        try:
            from core.persistence.postgres_client import get_postgres_client

            pg = await get_postgres_client()
            if pg is None or self._fernet is None:
                return

            pem = key_pair.get_private_key_pem()
            encrypted_pem = self._fernet.encrypt(pem.encode("utf-8")).decode("utf-8")

            await pg.execute(
                """
                INSERT INTO agent_signing_keys (agent_id, encrypted_private_key_pem, public_key_pem, is_active, created_at)
                VALUES ($1, $2, $3, true, NOW())
                ON CONFLICT (agent_id) WHERE is_active = true
                DO UPDATE SET
                    encrypted_private_key_pem = EXCLUDED.encrypted_private_key_pem,
                    public_key_pem = EXCLUDED.public_key_pem,
                    created_at = NOW()
                """,
                agent_id,
                encrypted_pem,
                key_pair.get_public_key_pem(),
            )
            logger.info("Saved key to PostgreSQL", agent_id=agent_id)
        except Exception as e:
            logger.warning("Could not save key to PostgreSQL — key is in-memory only and will be lost on restart", agent_id=agent_id, error=str(e))

    async def _retire_key_in_db(self, agent_id: str) -> None:
        """Mark the current active key for an agent as retired (is_active=false)."""
        try:
            from core.persistence.postgres_client import get_postgres_client

            pg = await get_postgres_client()
            if pg is None:
                return
            await pg.execute(
                "UPDATE agent_signing_keys SET is_active = false WHERE agent_id = $1 AND is_active = true",
                agent_id,
            )
        except Exception as e:
            logger.debug("Could not retire key in DB", agent_id=agent_id, error=str(e))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """
        Initialize the key store — attempt DB load first, generate keys as needed.

        Call this once at application startup.
        """
        await self._load_keys_from_db()

        # Generate any missing keys
        for agent_id in self._AGENT_IDS:
            if agent_id not in self._keys:
                if self._db_available:
                    # Generate independent random key pair
                    key_pair = AgentKeyPair.generate(agent_id)
                    self._keys[agent_id] = key_pair
                    await self._save_key_to_db(agent_id, key_pair)
                    logger.info("Generated independent key pair for agent", agent_id=agent_id)
                else:
                    # Deterministic fallback
                    seed = self._derive_seed(agent_id)
                    self._keys[agent_id] = AgentKeyPair.generate(agent_id, seed=seed)
                    logger.info(
                        "Derived deterministic key pair (DB unavailable) — "
                        "all agent keys share a single master SIGNING_KEY",
                        agent_id=agent_id,
                    )

    def get_or_create(self, agent_id: str) -> AgentKeyPair:
        """
        Get existing key pair for agent, or derive it deterministically.

        This synchronous fallback is used when initialize() has not been
        called (e.g. in unit tests or stateless environments).

        Args:
            agent_id: Unique identifier for the agent

        Returns:
            AgentKeyPair for the agent
        """
        if agent_id not in self._keys:
            seed = self._derive_seed(agent_id)
            self._keys[agent_id] = AgentKeyPair.generate(agent_id, seed=seed)
            logger.info(
                "Derived deterministic key pair for agent (sync fallback) — "
                "DB-backed keys not loaded; all agents share one master SIGNING_KEY",
                agent_id=agent_id,
            )
        return self._keys[agent_id]

    def get(self, agent_id: str) -> AgentKeyPair | None:
        """
        Get existing key pair for agent without creating.

        Args:
            agent_id: Unique identifier for the agent

        Returns:
            AgentKeyPair if exists, None otherwise
        """
        return self._keys.get(agent_id)

    async def rotate_key(self, agent_id: str) -> AgentKeyPair:
        """
        Rotate the signing key for an agent.

        Generates a new independent ECDSA P-256 key pair, retires the old key
        in the DB, saves the new key, and returns the new key pair.

        Args:
            agent_id: Agent whose key to rotate

        Returns:
            The new AgentKeyPair
        """
        old_key = self._keys.get(agent_id)

        # Retire old key in DB
        await self._retire_key_in_db(agent_id)

        # Generate new independent key
        new_key = AgentKeyPair.generate(agent_id)
        self._keys[agent_id] = new_key

        if self._db_available:
            await self._save_key_to_db(agent_id, new_key)

        logger.info(
            "Rotated signing key for agent",
            agent_id=agent_id,
            had_previous_key=old_key is not None,
            db_backed=self._db_available,
        )
        return new_key

    def clear(self) -> None:
        """Clear all stored keys (for testing)."""
        self._keys.clear()


# Global keystore instance
_keystore: KeyStore | None = None


def get_keystore() -> KeyStore:
    """Get or create the global keystore instance."""
    global _keystore
    if _keystore is None:
        _keystore = KeyStore()
    return _keystore


def compute_content_hash(content: dict[str, Any]) -> str:
    """
    Compute SHA-256 hash of JSON-serialized content.

    Args:
        content: Dictionary to hash

    Returns:
        Hex-encoded SHA-256 hash
    """

    # Sort keys for deterministic serialization
    # Use default=str to handle datetime and other non-JSON types,
    # and round floats to 10 decimal places to avoid PostgreSQL JSONB
    # float precision changes breaking hash verification.
    def _normalize(obj: Any) -> Any:
        if isinstance(obj, float):
            return float(Decimal(str(obj)).quantize(Decimal("0.0000000001"), rounding=ROUND_DOWN))
        if isinstance(obj, dict):
            return {k: _normalize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_normalize(v) for v in obj]
        return obj

    normalized = _normalize(content)
    content_json = json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(content_json.encode("utf-8")).hexdigest()


def sign_content(
    agent_id: str,
    content: dict[str, Any],
    keystore: KeyStore | None = None,
    timestamp: datetime | None = None,
) -> SignedEntry:
    """
    Sign content with agent's private key.

    Computes SHA-256 hash of content, then signs (hash + timestamp) with
    the agent's ECDSA private key.

    Args:
        agent_id: Identifier of the signing agent
        content: Content dictionary to sign
        keystore: Optional keystore (uses global if not provided)
        timestamp: Optional timestamp (uses current UTC if not provided)

    Returns:
        SignedEntry with content, hash, signature, and metadata
    """
    if keystore is None:
        keystore = get_keystore()

    key_pair = keystore.get_or_create(agent_id)

    # Compute content hash
    content_hash = compute_content_hash(content)

    # Use provided timestamp or current UTC
    if timestamp is None:
        timestamp = datetime.now(UTC)

    # Create message to sign: content_hash + timestamp_iso
    timestamp_iso = timestamp.isoformat()
    message = f"{content_hash}:{timestamp_iso}".encode()

    # Sign with ECDSA
    signature = key_pair.private_key.sign(
        message,
        ec.ECDSA(hashes.SHA256()),
    )

    # Encode signature as hex for storage
    signature_hex = signature.hex()

    logger.debug(
        "Signed content",
        agent_id=agent_id,
        content_hash=content_hash[:16] + "...",
    )

    return SignedEntry(
        content=content,
        content_hash=content_hash,
        signature=signature_hex,
        agent_id=agent_id,
        timestamp_utc=timestamp,
    )


def verify_entry(
    entry: SignedEntry,
    keystore: KeyStore | None = None,
) -> bool:
    """
    Verify a signed entry's signature.

    Recomputes content hash and verifies the signature using the agent's
    public key. Returns False on any verification failure (never raises).

    Args:
        entry: SignedEntry to verify
        keystore: Optional keystore (uses global if not provided)

    Returns:
        True if signature is valid, False otherwise
    """
    try:
        if keystore is None:
            keystore = get_keystore()

        # Get the agent's key pair
        key_pair = keystore.get(entry.agent_id)
        if key_pair is None:
            logger.warning(
                "Verification failed: no key for agent",
                agent_id=entry.agent_id,
            )
            return False

        # Recompute content hash
        expected_hash = compute_content_hash(entry.content)
        if expected_hash != entry.content_hash:
            logger.warning(
                "Verification failed: content hash mismatch",
                expected=expected_hash[:16] + "...",
                actual=entry.content_hash[:16] + "...",
            )
            return False

        # Reconstruct message
        timestamp_iso = entry.timestamp_utc.isoformat()
        message = f"{entry.content_hash}:{timestamp_iso}".encode()

        # Decode signature from hex
        signature_bytes = bytes.fromhex(entry.signature)

        # Verify signature
        key_pair.public_key.verify(
            signature_bytes,
            message,
            ec.ECDSA(hashes.SHA256()),
        )

        logger.debug(
            "Verified entry signature",
            agent_id=entry.agent_id,
            content_hash=entry.content_hash[:16] + "...",
        )
        return True

    except InvalidSignature:
        logger.warning(
            "Verification failed: invalid signature",
            agent_id=entry.agent_id,
        )
        return False
    except Exception as e:
        logger.warning(
            "Verification failed with exception",
            agent_id=entry.agent_id,
            error=str(e),
        )
        return False
