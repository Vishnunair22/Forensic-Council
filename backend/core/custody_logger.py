"""
Chain-of-Custody Logger Module
==============================

Provides tamper-evident logging for all forensic operations.
Every entry is cryptographically signed and linked to prior entries.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from core.structured_logging import get_logger
from core.signing import SignedEntry, sign_content, verify_entry
from infra.postgres_client import PostgresClient, get_postgres_client

logger = get_logger(__name__)


class EntryType(str, Enum):
    """Types of chain-of-custody entries."""
    THOUGHT = "THOUGHT"
    ACTION = "ACTION"
    OBSERVATION = "OBSERVATION"
    TOOL_CALL = "TOOL_CALL"
    INTER_AGENT_CALL = "INTER_AGENT_CALL"
    HITL_CHECKPOINT = "HITL_CHECKPOINT"
    HUMAN_INTERVENTION = "HUMAN_INTERVENTION"
    MEMORY_READ = "MEMORY_READ"
    MEMORY_WRITE = "MEMORY_WRITE"
    ARTIFACT_VERSION = "ARTIFACT_VERSION"
    HITL_DECISION = "HITL_DECISION"
    CALIBRATION = "CALIBRATION"
    SELF_REFLECTION = "SELF_REFLECTION"
    FINAL_FINDING = "FINAL_FINDING"
    TRIBUNAL_JUDGMENT = "TRIBUNAL_JUDGMENT"
    REPORT_SIGNED = "REPORT_SIGNED"
    ERROR = "ERROR"


@dataclass
class ChainEntry:
    """
    A chain-of-custody entry from the database.
    
    Attributes:
        entry_id: Unique identifier for this entry
        entry_type: Type of operation
        agent_id: Agent that performed the operation
        session_id: Session this entry belongs to
        timestamp_utc: When the entry was created
        content: The content that was signed
        content_hash: SHA-256 hash of content
        signature: Cryptographic signature
        prior_entry_ref: Hash of the previous entry (chain link)
    """
    entry_id: UUID
    entry_type: EntryType
    agent_id: str
    session_id: UUID
    timestamp_utc: datetime
    content: dict[str, Any]
    content_hash: str
    signature: str
    prior_entry_ref: Optional[str] = None
    
    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ChainEntry":
        """Create ChainEntry from database row."""
        return cls(
            entry_id=row["entry_id"],
            entry_type=EntryType(row["entry_type"]),
            agent_id=row["agent_id"],
            session_id=row["session_id"],
            timestamp_utc=row["timestamp_utc"],
            content=row["content"],
            content_hash=row["content_hash"],
            signature=row["signature"],
            prior_entry_ref=row.get("prior_entry_ref"),
        )
    
    def to_signed_entry(self) -> SignedEntry:
        """Convert to SignedEntry for verification."""
        return SignedEntry(
            content=self.content,
            content_hash=self.content_hash,
            signature=self.signature,
            agent_id=self.agent_id,
            timestamp_utc=self.timestamp_utc,
        )


@dataclass
class ChainVerificationReport:
    """
    Report from verifying a chain of custody.
    
    Attributes:
        session_id: Session that was verified
        total_entries: Total number of entries in chain
        valid: True if all entries verified successfully
        broken_at: Entry ID where chain is broken (if any)
        broken_reason: Reason for chain break (if any)
    """
    session_id: UUID
    total_entries: int
    valid: bool
    broken_at: Optional[UUID] = None
    broken_reason: Optional[str] = None


class CustodyLogger:
    """
    Async chain-of-custody logger backed by PostgreSQL.
    
    Provides tamper-evident logging where each entry is:
    1. Cryptographically signed by the agent
    2. Linked to the previous entry via prior_entry_ref
    3. Stored in an append-only database table
    
    Usage:
        async with CustodyLogger() as logger:
            entry_id = await logger.log_entry(
                agent_id="image_integrity_agent",
                session_id=session_uuid,
                entry_type=EntryType.THOUGHT,
                content={"thought": "Analyzing image..."}
            )
    """
    
    def __init__(self, postgres_client: Optional[PostgresClient] = None) -> None:
        """
        Initialize the custody logger.
        
        Args:
            postgres_client: Optional PostgreSQL client (uses singleton if not provided)
        """
        self._postgres = postgres_client
        self._owned_client = False  # Never own — always use singleton
    
    async def __aenter__(self) -> "CustodyLogger":
        """Async context manager entry."""
        if self._postgres is None:
            self._postgres = await get_postgres_client()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit — never close the shared pool."""
        pass
    
    async def _get_last_entry_hash(self, session_id: UUID) -> Optional[str]:
        """
        Get the content_hash of the last entry for a session.
        
        Args:
            session_id: Session to query
        
        Returns:
            Content hash of last entry, or None if no entries
        """
        if self._postgres is None:
            return None
            
        query = """
            SELECT content_hash
            FROM chain_of_custody
            WHERE session_id = $1
            ORDER BY timestamp_utc DESC
            LIMIT 1
        """
        result = await self._postgres.fetch_one(query, session_id)
        if result:
            return result["content_hash"]
        return None
    
    async def log_entry(
        self,
        agent_id: str,
        session_id: UUID,
        entry_type: EntryType,
        content: dict[str, Any],
    ) -> UUID:
        """
        Log a signed entry to the chain of custody.
        
        Signs the content, links to prior entry, and inserts into database.
        
        Args:
            agent_id: Identifier of the agent making the entry
            session_id: Session this entry belongs to
            entry_type: Type of operation being logged
            content: Content to log and sign
        
        Returns:
            UUID of the created entry
        """
        if self._postgres is None:
            logger.warning("CustodyLogger: no postgres client, skipping entry")
            return uuid4()
            
        # Sign the content
        signed = sign_content(agent_id, content)
        
        # Get prior entry hash for chain linking
        prior_entry_ref = await self._get_last_entry_hash(session_id)
        
        # Generate entry ID
        entry_id = uuid4()
        
        # Insert into database
        query = """
            INSERT INTO chain_of_custody (
                entry_id, entry_type, agent_id, session_id,
                timestamp_utc, content, content_hash, signature, prior_entry_ref
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """
        
        try:
            await self._postgres.execute(
                query,
                entry_id,
                entry_type.value,
                agent_id,
                session_id,
                signed.timestamp_utc,
                content,  # JSONB - will be converted to JSON string
                signed.content_hash,
                signed.signature,
                prior_entry_ref,
            )
        except Exception as db_err:
            # Custody logging must NEVER crash the investigation pipeline.
            # Log the failure but return the entry_id so callers don't break.
            logger.error(
                "CustodyLogger: failed to persist chain entry",
                entry_id=str(entry_id),
                entry_type=entry_type.value,
                agent_id=agent_id,
                session_id=str(session_id),
                error=str(db_err),
            )
            return entry_id
        
        logger.info(
            "Logged chain entry",
            entry_id=str(entry_id),
            entry_type=entry_type.value,
            agent_id=agent_id,
            session_id=str(session_id),
            has_prior=prior_entry_ref is not None,
        )
        
        return entry_id
    
    async def get_session_chain(self, session_id: UUID) -> list[ChainEntry]:
        """
        Get all entries for a session, ordered by timestamp.
        
        Args:
            session_id: Session to query
        
        Returns:
            List of ChainEntry objects in chronological order
        """
        assert self._postgres is not None, "CustodyLogger must be used as async context manager"
        query = """
            SELECT entry_id, entry_type, agent_id, session_id,
                   timestamp_utc, content, content_hash, signature, prior_entry_ref
            FROM chain_of_custody
            WHERE session_id = $1
            ORDER BY timestamp_utc ASC
        """
        
        rows = await self._postgres.fetch(query, session_id)
        
        entries = [ChainEntry.from_row(row) for row in rows]
        
        logger.debug(
            "Retrieved session chain",
            session_id=str(session_id),
            entry_count=len(entries),
        )
        
        return entries
    
    async def verify_chain(self, session_id: UUID) -> ChainVerificationReport:
        """
        Verify the integrity of a session's chain of custody.
        
        Checks:
        1. Every entry's signature is valid
        2. Every prior_entry_ref correctly links to the previous entry
        
        Args:
            session_id: Session to verify
        
        Returns:
            ChainVerificationReport with results
        """
        entries = await self.get_session_chain(session_id)
        
        if not entries:
            return ChainVerificationReport(
                session_id=session_id,
                total_entries=0,
                valid=True,  # Empty chain is valid
            )
        
        # Verify each entry
        for i, entry in enumerate(entries):
            # Verify signature
            signed_entry = entry.to_signed_entry()
            if not verify_entry(signed_entry):
                return ChainVerificationReport(
                    session_id=session_id,
                    total_entries=len(entries),
                    valid=False,
                    broken_at=entry.entry_id,
                    broken_reason="Signature verification failed",
                )
            
            # Verify chain link (prior_entry_ref)
            if i == 0:
                # First entry should have no prior
                if entry.prior_entry_ref is not None:
                    return ChainVerificationReport(
                        session_id=session_id,
                        total_entries=len(entries),
                        valid=False,
                        broken_at=entry.entry_id,
                        broken_reason="First entry has prior_entry_ref",
                    )
            else:
                # Subsequent entries should link to previous
                expected_prior = entries[i - 1].content_hash
                if entry.prior_entry_ref != expected_prior:
                    return ChainVerificationReport(
                        session_id=session_id,
                        total_entries=len(entries),
                        valid=False,
                        broken_at=entry.entry_id,
                        broken_reason="Chain link broken - prior_entry_ref mismatch",
                    )
        
        logger.info(
            "Chain verification complete",
            session_id=str(session_id),
            total_entries=len(entries),
            valid=True,
        )
        
        return ChainVerificationReport(
            session_id=session_id,
            total_entries=len(entries),
            valid=True,
        )
    
    async def get_entry(self, entry_id: UUID) -> Optional[ChainEntry]:
        """
        Get a specific entry by ID.
        
        Args:
            entry_id: Entry UUID to retrieve
        
        Returns:
            ChainEntry if found, None otherwise
        """
        assert self._postgres is not None, "CustodyLogger must be used as async context manager"
        query = """
            SELECT entry_id, entry_type, agent_id, session_id,
                   timestamp_utc, content, content_hash, signature, prior_entry_ref
            FROM chain_of_custody
            WHERE entry_id = $1
        """
        
        row = await self._postgres.fetch_one(query, entry_id)
        
        if row is None:
            return None
        
        return ChainEntry.from_row(row)
    
    async def tamper_entry(self, entry_id: UUID, new_content: dict[str, Any]) -> None:
        """
        Tamper with an entry's content (for testing tamper detection).
        
        This deliberately corrupts an entry to test verification.
        DO NOT USE in production code.
        
        Args:
            entry_id: Entry to tamper with
            new_content: New content to inject
        """
        assert self._postgres is not None, "CustodyLogger must be used as async context manager"
        query = """
            UPDATE chain_of_custody
            SET content = $1
            WHERE entry_id = $2
        """
        
        await self._postgres.execute(query, new_content, entry_id)
        
        logger.warning(
            "TAMPERED with entry (testing only)",
            entry_id=str(entry_id),
        )


# Singleton instance
_custody_logger: Optional[CustodyLogger] = None


async def get_custody_logger() -> CustodyLogger:
    """
    Get or create the custody logger singleton.
    
    Returns:
        CustodyLogger instance
    """
    global _custody_logger
    if _custody_logger is None:
        postgres = await get_postgres_client()
        _custody_logger = CustodyLogger(postgres)
    return _custody_logger


async def close_custody_logger() -> None:
    """Reset the custody logger singleton reference (does not close the shared pool)."""
    global _custody_logger
    _custody_logger = None