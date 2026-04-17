"""
Episodic Memory Module
======================

Qdrant-backed episodic memory for forensic signature storage.
Part of the dual-layer memory architecture.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from core.custody_logger import CustodyLogger, EntryType
from core.persistence.qdrant_client import (
    EPISODIC_MEMORY_COLLECTION,
    QdrantClient,
    get_qdrant_client,
)
from core.structured_logging import get_logger

logger = get_logger(__name__)


class ForensicSignatureType(StrEnum):
    """Types of forensic signatures stored in episodic memory."""

    DEVICE_FINGERPRINT = "DEVICE_FINGERPRINT"
    METADATA_PATTERN = "METADATA_PATTERN"
    OBJECT_DETECTION = "OBJECT_DETECTION"
    AUDIO_ARTIFACT = "AUDIO_ARTIFACT"
    VIDEO_ARTIFACT = "VIDEO_ARTIFACT"
    MANIPULATION_SIGNATURE = "MANIPULATION_SIGNATURE"


class EpisodicEntry(BaseModel):
    """An entry in episodic memory."""

    entry_id: UUID = Field(default_factory=uuid4)
    case_id: str
    agent_id: str
    session_id: UUID
    signature_type: ForensicSignatureType
    finding_type: str
    confidence: float
    summary: str
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for Qdrant payload."""
        return {
            "entry_id": str(self.entry_id),
            "case_id": self.case_id,
            "agent_id": self.agent_id,
            "session_id": str(self.session_id),
            "signature_type": self.signature_type.value,
            "finding_type": self.finding_type,
            "confidence": self.confidence,
            "summary": self.summary,
            "timestamp_utc": self.timestamp_utc.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EpisodicEntry":
        """Create from dictionary (Qdrant payload)."""
        return cls(
            entry_id=UUID(data["entry_id"]),
            case_id=data["case_id"],
            agent_id=data["agent_id"],
            session_id=UUID(data["session_id"]),
            signature_type=ForensicSignatureType(data["signature_type"]),
            finding_type=data["finding_type"],
            confidence=data["confidence"],
            summary=data["summary"],
            timestamp_utc=datetime.fromisoformat(data["timestamp_utc"])
            if isinstance(data["timestamp_utc"], str)
            else data["timestamp_utc"],
        )


class EpisodicMemory:
    """
    Qdrant-backed episodic memory for forensic signature storage.

    Provides:
    - Vector similarity search for forensic patterns
    - Case-based retrieval
    - Chain-of-custody logging

    Usage:
        async with EpisodicMemory() as memory:
            entry = EpisodicEntry(...)
            await memory.store(entry, embedding_vector)

            results = await memory.query(
                query_embedding=embedding,
                signature_type=ForensicSignatureType.DEVICE_FINGERPRINT,
            )
    """

    def __init__(
        self,
        qdrant_client: QdrantClient | None = None,
        custody_logger: CustodyLogger | None = None,
        vector_size: int = 512,
    ) -> None:
        """
        Initialize episodic memory.

        Args:
            qdrant_client: Optional Qdrant client
            custody_logger: Optional custody logger
            vector_size: Vector embedding dimension (default 512 — CLIP ViT-B-32 output size)
        """
        self._qdrant = qdrant_client
        self._custody_logger = custody_logger
        self._vector_size = vector_size
        self._owned_client = qdrant_client is None

    async def __aenter__(self) -> "EpisodicMemory":
        """Async context manager entry."""
        if self._qdrant is None:
            self._qdrant = await get_qdrant_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        if self._owned_client and self._qdrant:
            await self._qdrant.disconnect()
            self._qdrant = None

    async def ensure_collection(self) -> bool:
        """Ensure the collection exists. Returns False if Qdrant is unavailable."""
        if self._qdrant is None:
            logger.warning(
                "EpisodicMemory: Qdrant unavailable, skipping ensure_collection"
            )
            return False
        try:
            await self._qdrant.create_collection(
                collection_name=EPISODIC_MEMORY_COLLECTION,
                vector_size=self._vector_size,
            )
            return True
        except Exception as e:
            logger.warning("EpisodicMemory: ensure_collection failed", error=str(e))
            return False

    async def store(
        self,
        entry: EpisodicEntry,
        embedding: list[float],
    ) -> None:
        """
        Store an entry with its embedding.

        Args:
            entry: EpisodicEntry to store
            embedding: Vector embedding (512 dimensions — CLIP ViT-B-32)
        """
        # Ensure collection exists — bail out if Qdrant is unavailable
        if not await self.ensure_collection():
            logger.warning(
                "EpisodicMemory.store: skipped — Qdrant unavailable",
                entry_id=str(entry.entry_id),
            )
            return

        # Upsert to Qdrant
        if self._qdrant is None:
            raise RuntimeError("Qdrant client not initialized")
        try:
            await self._qdrant.upsert(
                collection_name=EPISODIC_MEMORY_COLLECTION,
                point_id=entry.entry_id,
                vector=embedding,
                payload=entry.to_dict(),
            )
        except Exception as e:
            logger.warning("EpisodicMemory.store: upsert failed", error=str(e))
            return

        # Log to custody logger
        if self._custody_logger:
            await self._custody_logger.log_entry(
                agent_id=entry.agent_id,
                session_id=entry.session_id,
                entry_type=EntryType.MEMORY_WRITE,
                content={
                    "operation": "store_episodic",
                    "entry_id": str(entry.entry_id),
                    "case_id": entry.case_id,
                    "signature_type": entry.signature_type.value,
                    "finding_type": entry.finding_type,
                    "confidence": entry.confidence,
                },
            )

        logger.info(
            "Stored episodic entry",
            entry_id=str(entry.entry_id),
            case_id=entry.case_id,
            signature_type=entry.signature_type.value,
        )

    async def query(
        self,
        query_embedding: list[float],
        signature_type: ForensicSignatureType | None = None,
        top_k: int = 5,
    ) -> list[EpisodicEntry]:
        """
        Query for similar entries.

        Args:
            query_embedding: Query vector embedding
            signature_type: Optional filter by signature type
            top_k: Number of results to return

        Returns:
            List of matching EpisodicEntry objects
        """
        # Ensure collection exists — return empty list if Qdrant is unavailable
        if not await self.ensure_collection():
            logger.warning("EpisodicMemory.query: skipped — Qdrant unavailable")
            return []

        # Build filter conditions
        filter_conditions = None
        if signature_type:
            filter_conditions = {"signature_type": signature_type.value}

        # Query Qdrant
        if self._qdrant is None:
            raise RuntimeError("Qdrant client not initialized")
        try:
            results = await self._qdrant.query(
                collection_name=EPISODIC_MEMORY_COLLECTION,
                query_vector=query_embedding,
                top_k=top_k,
                filter_conditions=filter_conditions,
            )
        except Exception as e:
            logger.warning("EpisodicMemory.query: failed", error=str(e))
            return []

        # Convert to EpisodicEntry
        entries = [EpisodicEntry.from_dict(result["payload"]) for result in results]

        # Log to custody logger
        if self._custody_logger and entries:
            await self._custody_logger.log_entry(
                agent_id="episodic_memory",
                session_id=entries[0].session_id,  # Use first entry's session
                entry_type=EntryType.MEMORY_READ,
                content={
                    "operation": "query_episodic",
                    "signature_type_filter": signature_type.value
                    if signature_type
                    else None,
                    "top_k": top_k,
                    "result_count": len(entries),
                },
            )

        logger.debug(
            "Queried episodic memory",
            signature_type=signature_type.value if signature_type else "any",
            result_count=len(entries),
        )

        return entries

    async def get_by_case(
        self,
        case_id: str,
    ) -> list[EpisodicEntry]:
        """
        Get all entries for a case.

        Args:
            case_id: Case identifier

        Returns:
            List of EpisodicEntry objects for the case
        """
        # Ensure collection exists — return empty list if Qdrant is unavailable
        if not await self.ensure_collection():
            logger.warning("EpisodicMemory.get_by_case: skipped — Qdrant unavailable")
            return []

        # Query with case_id filter using scroll (filter-only query)
        if self._qdrant is None:
            raise RuntimeError("Qdrant client not initialized")
        try:
            results = await self._qdrant.scroll(
                collection_name=EPISODIC_MEMORY_COLLECTION,
                filter_conditions={"case_id": case_id},
                limit=100,  # Get all entries for case
            )
        except Exception as e:
            logger.warning("EpisodicMemory.get_by_case: scroll failed", error=str(e))
            return []

        # Convert to EpisodicEntry
        entries = [EpisodicEntry.from_dict(result["payload"]) for result in results]

        logger.debug(
            "Retrieved case entries",
            case_id=case_id,
            entry_count=len(entries),
        )

        return entries

    async def get_by_session(
        self,
        session_id: UUID,
    ) -> list[EpisodicEntry]:
        """
        Get all entries for a session.

        Args:
            session_id: Session UUID

        Returns:
            List of EpisodicEntry objects for the session
        """
        # Ensure collection exists — return empty list if Qdrant is unavailable
        if not await self.ensure_collection():
            logger.warning(
                "EpisodicMemory.get_by_session: skipped — Qdrant unavailable"
            )
            return []

        # Query with session_id filter using scroll (filter-only query)
        if self._qdrant is None:
            logger.warning("EpisodicMemory.get_by_session: skipped — Qdrant not initialized")
            return []
        try:
            results = await self._qdrant.scroll(
                collection_name=EPISODIC_MEMORY_COLLECTION,
                filter_conditions={"session_id": str(session_id)},
                limit=100,
            )
        except Exception as e:
            logger.warning("EpisodicMemory.get_by_session: scroll failed", error=str(e))
            return []

        # Convert to EpisodicEntry
        entries = [EpisodicEntry.from_dict(result["payload"]) for result in results]

        return entries

    async def retrieve_similar_cases(
        self,
        signature_type: ForensicSignatureType | None = None,
        finding_type: str | None = None,
        exclude_session_id: UUID | None = None,
        top_k: int = 5,
    ) -> list[EpisodicEntry]:
        """
        Retrieve similar past forensic entries for context injection.

        Uses filter-based scroll (no vector query needed) to find entries
        matching the given signature_type and/or finding_type from previous
        investigations. Excludes entries from the current session.

        Args:
            signature_type: Filter by forensic signature type
            finding_type: Filter by finding type substring match
            exclude_session_id: Exclude entries from this session (current investigation)
            top_k: Maximum number of results

        Returns:
            List of matching EpisodicEntry objects from past investigations
        """
        if not await self.ensure_collection():
            return []

        if self._qdrant is None:
            raise RuntimeError("Qdrant client not initialized")

        # Build filter conditions
        conditions: dict[str, Any] = {}
        if signature_type:
            conditions["signature_type"] = signature_type.value

        try:
            results = await self._qdrant.scroll(
                collection_name=EPISODIC_MEMORY_COLLECTION,
                filter_conditions=conditions if conditions else None,
                limit=top_k * 3,  # Over-fetch to account for filtering
            )
        except Exception as e:
            logger.debug(
                "EpisodicMemory.retrieve_similar_cases: scroll failed", error=str(e)
            )
            return []

        entries = []
        for result in results:
            payload = result.get("payload", {})
            # Skip entries from current session
            if exclude_session_id and payload.get("session_id") == str(
                exclude_session_id
            ):
                continue
            # Optional finding_type substring match
            if (
                finding_type
                and finding_type.lower() not in payload.get("finding_type", "").lower()
            ):
                continue
            try:
                entries.append(EpisodicEntry.from_dict(payload))
            except Exception:
                continue
            if len(entries) >= top_k:
                break

        if entries:
            logger.info(
                "Retrieved similar cases from episodic memory",
                result_count=len(entries),
                signature_type=signature_type.value if signature_type else None,
            )

        return entries


# Singleton instance
_episodic_memory: EpisodicMemory | None = None


async def get_episodic_memory() -> EpisodicMemory:
    """
    Get or create the episodic memory singleton.

    Returns:
        EpisodicMemory instance
    """
    global _episodic_memory
    if _episodic_memory is None:
        qdrant = await get_qdrant_client()
        _episodic_memory = EpisodicMemory(qdrant_client=qdrant)
    return _episodic_memory


async def close_episodic_memory() -> None:
    """Close the episodic memory singleton."""
    global _episodic_memory
    if _episodic_memory is not None:
        if _episodic_memory._qdrant:
            await _episodic_memory._qdrant.disconnect()
        _episodic_memory = None
