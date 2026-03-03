"""
Episodic Memory Module
======================

Qdrant-backed episodic memory for forensic signature storage.
Part of the dual-layer memory architecture.
"""

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from core.logging import get_logger
from core.custody_logger import CustodyLogger, EntryType
from infra.qdrant_client import QdrantClient, get_qdrant_client, EPISODIC_MEMORY_COLLECTION

logger = get_logger(__name__)


class ForensicSignatureType(str, Enum):
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
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
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
        qdrant_client: Optional[QdrantClient] = None,
        custody_logger: Optional[CustodyLogger] = None,
        vector_size: int = 768,
    ) -> None:
        """
        Initialize episodic memory.
        
        Args:
            qdrant_client: Optional Qdrant client
            custody_logger: Optional custody logger
            vector_size: Vector embedding dimension (default 768)
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
    
    async def ensure_collection(self) -> None:
        """Ensure the collection exists."""
        await self._qdrant.create_collection(
            collection_name=EPISODIC_MEMORY_COLLECTION,
            vector_size=self._vector_size,
        )
    
    async def store(
        self,
        entry: EpisodicEntry,
        embedding: list[float],
    ) -> None:
        """
        Store an entry with its embedding.
        
        Args:
            entry: EpisodicEntry to store
            embedding: Vector embedding (768 dimensions)
        """
        # Ensure collection exists
        await self.ensure_collection()
        
        # Upsert to Qdrant
        await self._qdrant.upsert(
            collection_name=EPISODIC_MEMORY_COLLECTION,
            point_id=entry.entry_id,
            vector=embedding,
            payload=entry.to_dict(),
        )
        
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
        signature_type: Optional[ForensicSignatureType] = None,
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
        # Ensure collection exists
        await self.ensure_collection()
        
        # Build filter conditions
        filter_conditions = None
        if signature_type:
            filter_conditions = {"signature_type": signature_type.value}
        
        # Query Qdrant
        results = await self._qdrant.query(
            collection_name=EPISODIC_MEMORY_COLLECTION,
            query_vector=query_embedding,
            top_k=top_k,
            filter_conditions=filter_conditions,
        )
        
        # Convert to EpisodicEntry
        entries = [
            EpisodicEntry.from_dict(result["payload"])
            for result in results
        ]
        
        # Log to custody logger
        if self._custody_logger and entries:
            await self._custody_logger.log_entry(
                agent_id="episodic_memory",
                session_id=entries[0].session_id,  # Use first entry's session
                entry_type=EntryType.MEMORY_READ,
                content={
                    "operation": "query_episodic",
                    "signature_type_filter": signature_type.value if signature_type else None,
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
        # Ensure collection exists
        await self.ensure_collection()
        
        # Query with case_id filter
        results = await self._qdrant.query(
            collection_name=EPISODIC_MEMORY_COLLECTION,
            query_vector=[0.0] * self._vector_size,  # Dummy vector for filter-only query
            top_k=100,  # Get all entries for case
            filter_conditions={"case_id": case_id},
        )
        
        # Convert to EpisodicEntry
        entries = [
            EpisodicEntry.from_dict(result["payload"])
            for result in results
        ]
        
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
        # Ensure collection exists
        await self.ensure_collection()
        
        # Query with session_id filter
        results = await self._qdrant.query(
            collection_name=EPISODIC_MEMORY_COLLECTION,
            query_vector=[0.0] * self._vector_size,  # Dummy vector for filter-only query
            top_k=100,
            filter_conditions={"session_id": str(session_id)},
        )
        
        # Convert to EpisodicEntry
        entries = [
            EpisodicEntry.from_dict(result["payload"])
            for result in results
        ]
        
        return entries


# Singleton instance
_episodic_memory: Optional[EpisodicMemory] = None


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
