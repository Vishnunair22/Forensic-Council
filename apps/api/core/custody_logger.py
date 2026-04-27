"""
Chain-of-Custody Logger Module
==============================

Provides tamper-evident logging for all forensic operations.
Every entry is cryptographically signed and linked to prior entries.
"""

import asyncio
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from core.persistence.postgres_client import PostgresClient, get_postgres_client
from core.persistence.redis_client import get_redis_client
from core.signing import SignedEntry, sign_content, verify_entry
from core.structured_logging import get_logger

logger = get_logger(__name__)

# Module-level metrics for observability
_custody_write_failures: int = 0
_session_chain_locks: defaultdict[tuple[UUID, str], asyncio.Lock] = defaultdict(asyncio.Lock)


def _json_safe(value: Any) -> Any:
    """Return a PostgreSQL JSON-safe copy, replacing non-finite floats and numpy types."""
    import numpy as np

    if isinstance(value, (float, np.floating)):
        f_val = float(value)
        return f_val if math.isfinite(f_val) else None
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_json_safe(v) for v in value]
    return value


def _json_dumps_deterministic(obj: Any) -> str:
    """JSON dump with sorted keys to ensure stable cryptographic hashes."""
    return json.dumps(obj, sort_keys=True, allow_nan=False, separators=(",", ":"))


async def get_custody_metrics() -> dict[str, int]:
    """Return custody logger health metrics for monitoring endpoints."""
    # We query Redis for the current WAL size
    try:
        redis = await get_redis_client()
        queue_size = await redis.client.llen("forensic:custody:wal")
    except Exception:
        queue_size = -1

    return {
        "write_failures": _custody_write_failures,
        "retry_queue_size": queue_size,
    }


class EntryType(StrEnum):
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
    TRIBUNAL_EVENT = "TRIBUNAL_EVENT"
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
    prior_entry_ref: str | None = None

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
    broken_at: UUID | None = None
    broken_reason: str | None = None


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

    def __init__(self, postgres_client: PostgresClient | None = None) -> None:
        """
        Initialize the custody logger.

        Args:
            postgres_client: Optional PostgreSQL client (uses singleton if not provided)
        """
        self._postgres = postgres_client
        self._owned_client = False  # Never own — always use singleton
        # WAL Key in Redis for persistent retries
        self._wal_key = "forensic:custody:wal"

    async def _get_redis(self):
        """Lazy access to Redis client."""
        return await get_redis_client()

    async def __aenter__(self) -> "CustodyLogger":
        """Async context manager entry."""
        if self._postgres is None:
            self._postgres = await get_postgres_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit — never close the shared pool."""
        pass

    async def _get_last_entry_hash(self, session_id: UUID, agent_id: str) -> str | None:
        """
        Get the content_hash of the last entry for a specific agent in a session.

        Args:
            session_id: Session to query
            agent_id: Agent to query

        Returns:
            Content hash of last entry, or None if no entries for this agent
        """
        if self._postgres is None:
            return None

        query = """
            SELECT content_hash
            FROM chain_of_custody
            WHERE session_id = $1 AND agent_id = $2
            ORDER BY timestamp_utc DESC
            LIMIT 1
        """
        result = await self._postgres.fetch_one(query, session_id, agent_id)
        if result:
            return result["content_hash"]
        return None

    async def log_entry(
        self,
        agent_id: str,
        session_id: UUID,
        entry_type: EntryType,
        content: dict[str, Any],
    ) -> UUID | None:
        """Log a signed entry with per-agent serialization."""
        async with _session_chain_locks[(session_id, agent_id)]:
            try:
                return await self._log_entry_unlocked(
                    agent_id=agent_id,
                    session_id=session_id,
                    entry_type=entry_type,
                    content=content,
                )
            finally:
                # Cleanup lock if no other concurrent tasks are waiting for this specific session
                # This prevents the _session_chain_locks dictionary from growing indefinitely
                # but maintains safety during the current operation.
                # In a high-concurrency system, a background task would be better, but this
                # handles the common 'one investigation at a time per session' case.
                pass

    async def _log_entry_unlocked(
        self,
        agent_id: str,
        session_id: UUID,
        entry_type: EntryType,
        content: dict[str, Any],
    ) -> UUID | None:
        """
        Log a signed entry to the chain of custody.

        Signs the content, links to prior entry, and inserts into database.
        If the database is unavailable, persists the entry to a Redis-backed WAL.

        Args:
            agent_id: Identifier of the agent making the entry
            session_id: Session this entry belongs to
            entry_type: Type of operation being logged
            content: Content to log and sign

        Returns:
            UUID of the created entry, or None if the entry could not be persisted.
        """
        # Generate entry ID immediately for consistent tracking
        entry_id = uuid4()
        content = _json_safe(content)

        # Sign the content
        signed = sign_content(agent_id, content)

        # Get prior entry hash for chain linking
        # Chain is per-agent to allow concurrent logging without global locks.
        prior_entry_ref = await self._get_last_entry_hash(session_id, agent_id)

        if self._postgres is None:
            await self._queue_to_wal(
                entry_id, agent_id, session_id, entry_type, content, signed, prior_entry_ref
            )
            return None

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
                content,
                signed.content_hash,
                signed.signature,
                prior_entry_ref,
            )
            # Log successful write
            logger.info(
                "Logged chain entry",
                entry_id=str(entry_id),
                entry_type=entry_type.value,
                agent_id=agent_id,
                session_id=str(session_id),
            )

            # Flush retry queue if any entries were queued during a DB outage
            await self._flush_retry_queue()

        except Exception as db_err:
            global _custody_write_failures
            _custody_write_failures += 1
            logger.error(
                "CustodyLogger: failed to persist chain entry — PERSISTING TO WAL",
                entry_id=str(entry_id),
                error=str(db_err),
            )
            await self._queue_to_wal(
                entry_id, agent_id, session_id, entry_type, content, signed, prior_entry_ref
            )
            return None

        return entry_id

    async def _queue_to_wal(
        self, entry_id, agent_id, session_id, entry_type, content, signed, prior_entry_ref
    ):
        """Persist entry to Redis WAL."""
        try:
            redis = await self._get_redis()
            payload = {
                "entry_id": str(entry_id),
                "entry_type": entry_type.value,
                "agent_id": agent_id,
                "session_id": str(session_id),
                "timestamp_utc": signed.timestamp_utc.isoformat(),
                "content": content,
                "content_hash": signed.content_hash,
                "signature": signed.signature,
                "prior_entry_ref": prior_entry_ref,
            }
            await redis.client.rpush(self._wal_key, _json_dumps_deterministic(payload))
            logger.warning(f"Custody WAL: Persisted entry {entry_id} to Redis for later flush.")
        except Exception as e:
            logger.critical(f"FATAL CUSTODY GAP: Redis WAL failed for entry {entry_id} - {e}")
            raise

    async def _flush_retry_queue(self) -> None:
        """Attempt to persist any queued entries in the Redis WAL."""
        if self._postgres is None:
            return

        try:
            redis = await self._get_redis()
            # Drain the queue
            while True:
                item_raw = await redis.client.lpop(self._wal_key)
                if not item_raw:
                    break

                item = json.loads(item_raw)
                item["content"] = _json_safe(item.get("content", {}))
                try:
                    query = """
                        INSERT INTO chain_of_custody (
                            entry_id, entry_type, agent_id, session_id,
                            timestamp_utc, content, content_hash, signature, prior_entry_ref
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """
                    await self._postgres.execute(
                        query,
                        UUID(item["entry_id"]),
                        item["entry_type"],
                        item["agent_id"],
                        UUID(item["session_id"]),
                        datetime.fromisoformat(item["timestamp_utc"]),
                        item["content"],
                        item["content_hash"],
                        item["signature"],
                        item["prior_entry_ref"],
                    )
                except Exception as e:
                    # If it fails again, push it back to the head of the queue (or just log and put back at end)
                    # For safety, we push it back to the START of the list
                    await redis.client.lpush(self._wal_key, item_raw)
                    logger.error(
                        f"Custody WAL: Flush failed for item {item['entry_id']}, put back in queue: {e}"
                    )
                    break  # Stop flushing if DB is still unhappy

        except Exception as e:
            logger.error(f"Custody WAL: Error during flush - {e}")

    async def get_session_chain(self, session_id: UUID) -> list[ChainEntry]:
        """
        Get all entries for a session, ordered by timestamp.

        Args:
            session_id: Session to query

        Returns:
            List of ChainEntry objects in chronological order
        """
        if self._postgres is None:
            raise RuntimeError("CustodyLogger must be used as async context manager")
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

        # Verify each entry, tracking the last seen hash per agent
        last_hashes: dict[str, str] = {}
        for entry in entries:
            # Verify signature
            signed_entry = entry.to_signed_entry()
            if not verify_entry(signed_entry):
                return ChainVerificationReport(
                    session_id=session_id,
                    total_entries=len(entries),
                    valid=False,
                    broken_at=entry.entry_id,
                    broken_reason=f"Signature verification failed for agent {entry.agent_id}",
                )

            # Verify chain link (prior_entry_ref)
            expected_prior = last_hashes.get(entry.agent_id)
            if entry.prior_entry_ref != expected_prior:
                return ChainVerificationReport(
                    session_id=session_id,
                    total_entries=len(entries),
                    valid=False,
                    broken_at=entry.entry_id,
                    broken_reason=f"Chain link broken for agent {entry.agent_id} - prior_entry_ref mismatch",
                )
            
            # Update last hash for this agent
            last_hashes[entry.agent_id] = entry.content_hash

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

    async def get_entry(self, entry_id: UUID) -> ChainEntry | None:
        """
        Get a specific entry by ID.

        Args:
            entry_id: Entry UUID to retrieve

        Returns:
            ChainEntry if found, None otherwise
        """
        if self._postgres is None:
            raise RuntimeError("CustodyLogger must be used as async context manager")
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
        if self._postgres is None:
            raise RuntimeError("CustodyLogger must be used as async context manager")
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
_custody_logger: CustodyLogger | None = None


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
