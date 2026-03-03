"""
Episodic Memory Tests
=====================

Tests for Qdrant-backed episodic memory.
"""

import random
import pytest
from uuid import uuid4

from core.episodic_memory import (
    EpisodicEntry,
    EpisodicMemory,
    ForensicSignatureType,
)
from core.custody_logger import CustodyLogger, EntryType
from infra.qdrant_client import QdrantClient
from infra.postgres_client import PostgresClient


def generate_random_embedding(dim: int = 768) -> list[float]:
    """Generate a random embedding vector for testing."""
    return [random.uniform(-1, 1) for _ in range(dim)]


@pytest.fixture
async def episodic_memory(
    qdrant_client: QdrantClient,
    postgres_client: PostgresClient,
) -> EpisodicMemory:
    """Create an EpisodicMemory with test dependencies."""
    custody_logger = CustodyLogger(postgres_client=postgres_client)
    return EpisodicMemory(
        qdrant_client=qdrant_client,
        custody_logger=custody_logger,
    )


class TestEpisodicEntry:
    """Tests for EpisodicEntry model."""
    
    def test_create_entry(self):
        """Test creating an entry."""
        session_id = uuid4()
        entry = EpisodicEntry(
            case_id="CASE-001",
            agent_id="image_agent",
            session_id=session_id,
            signature_type=ForensicSignatureType.DEVICE_FINGERPRINT,
            finding_type="camera_match",
            confidence=0.95,
            summary="Device fingerprint matches known camera model",
        )
        
        assert entry.case_id == "CASE-001"
        assert entry.agent_id == "image_agent"
        assert entry.signature_type == ForensicSignatureType.DEVICE_FINGERPRINT
        assert entry.confidence == 0.95
        assert entry.entry_id is not None
    
    def test_to_dict_and_from_dict(self):
        """Test serialization."""
        session_id = uuid4()
        entry = EpisodicEntry(
            case_id="CASE-001",
            agent_id="agent",
            session_id=session_id,
            signature_type=ForensicSignatureType.MANIPULATION_SIGNATURE,
            finding_type="ela_anomaly",
            confidence=0.87,
            summary="ELA detected potential manipulation",
        )
        
        data = entry.to_dict()
        restored = EpisodicEntry.from_dict(data)
        
        assert restored.entry_id == entry.entry_id
        assert restored.case_id == entry.case_id
        assert restored.agent_id == entry.agent_id
        assert restored.signature_type == entry.signature_type
        assert restored.finding_type == entry.finding_type
        assert restored.confidence == entry.confidence
        assert restored.summary == entry.summary


class TestForensicSignatureType:
    """Tests for ForensicSignatureType enum."""
    
    def test_all_types_exist(self):
        """Test that all required types are defined."""
        expected_types = [
            "DEVICE_FINGERPRINT",
            "METADATA_PATTERN",
            "OBJECT_DETECTION",
            "AUDIO_ARTIFACT",
            "VIDEO_ARTIFACT",
            "MANIPULATION_SIGNATURE",
        ]
        
        for type_name in expected_types:
            assert hasattr(ForensicSignatureType, type_name)
    
    def test_type_values(self):
        """Test that type values match names."""
        assert ForensicSignatureType.DEVICE_FINGERPRINT.value == "DEVICE_FINGERPRINT"
        assert ForensicSignatureType.MANIPULATION_SIGNATURE.value == "MANIPULATION_SIGNATURE"


class TestEpisodicMemory:
    """Tests for EpisodicMemory class."""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_store_entry_persists_to_qdrant(
        self,
        episodic_memory: EpisodicMemory,
    ):
        """Test that store persists entry to Qdrant."""
        session_id = uuid4()
        entry = EpisodicEntry(
            case_id="CASE-STORE-001",
            agent_id="test_agent",
            session_id=session_id,
            signature_type=ForensicSignatureType.DEVICE_FINGERPRINT,
            finding_type="test_finding",
            confidence=0.9,
            summary="Test summary",
        )
        
        embedding = generate_random_embedding()
        
        await episodic_memory.store(entry, embedding)
        
        # Query to verify stored
        results = await episodic_memory.query(
            query_embedding=embedding,
            top_k=1,
        )
        
        assert len(results) >= 1
        assert results[0].case_id == "CASE-STORE-001"
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_query_returns_matching_entries(
        self,
        episodic_memory: EpisodicMemory,
    ):
        """Test that query returns matching entries."""
        session_id = uuid4()
        
        # Store multiple entries with similar embeddings
        base_embedding = generate_random_embedding()
        
        for i in range(3):
            entry = EpisodicEntry(
                case_id=f"CASE-QUERY-{i}",
                agent_id="test_agent",
                session_id=session_id,
                signature_type=ForensicSignatureType.DEVICE_FINGERPRINT,
                finding_type=f"finding_{i}",
                confidence=0.8 + i * 0.05,
                summary=f"Summary {i}",
            )
            
            # Slightly modify embedding for variety
            embedding = base_embedding.copy()
            embedding[i] += 0.1
            
            await episodic_memory.store(entry, embedding)
        
        # Query with base embedding
        results = await episodic_memory.query(
            query_embedding=base_embedding,
            top_k=3,
        )
        
        assert len(results) >= 3
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_query_filters_by_signature_type(
        self,
        episodic_memory: EpisodicMemory,
    ):
        """Test that query filters by signature type."""
        session_id = uuid4()
        
        # Store entries with different signature types
        embedding = generate_random_embedding()
        
        entry1 = EpisodicEntry(
            case_id="CASE-FILTER-1",
            agent_id="test_agent",
            session_id=session_id,
            signature_type=ForensicSignatureType.DEVICE_FINGERPRINT,
            finding_type="device",
            confidence=0.9,
            summary="Device finding",
        )
        
        entry2 = EpisodicEntry(
            case_id="CASE-FILTER-2",
            agent_id="test_agent",
            session_id=session_id,
            signature_type=ForensicSignatureType.AUDIO_ARTIFACT,
            finding_type="audio",
            confidence=0.85,
            summary="Audio finding",
        )
        
        await episodic_memory.store(entry1, embedding.copy())
        await episodic_memory.store(entry2, embedding.copy())
        
        # Query with filter
        results = await episodic_memory.query(
            query_embedding=embedding,
            signature_type=ForensicSignatureType.DEVICE_FINGERPRINT,
            top_k=10,
        )
        
        # All results should be DEVICE_FINGERPRINT
        for result in results:
            assert result.signature_type == ForensicSignatureType.DEVICE_FINGERPRINT
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_by_case_returns_all_case_entries(
        self,
        episodic_memory: EpisodicMemory,
    ):
        """Test that get_by_case returns all entries for a case."""
        case_id = f"CASE-GET-{uuid4().hex[:8]}"
        session_id = uuid4()
        
        # Store multiple entries for same case
        embedding = generate_random_embedding()
        
        for i in range(3):
            entry = EpisodicEntry(
                case_id=case_id,
                agent_id="test_agent",
                session_id=session_id,
                signature_type=ForensicSignatureType.METADATA_PATTERN,
                finding_type=f"finding_{i}",
                confidence=0.8,
                summary=f"Summary {i}",
            )
            await episodic_memory.store(entry, embedding.copy())
        
        # Get by case
        results = await episodic_memory.get_by_case(case_id)
        
        assert len(results) >= 3
        for result in results:
            assert result.case_id == case_id
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_store_logs_memory_write_to_custody_logger(
        self,
        episodic_memory: EpisodicMemory,
    ):
        """Test that store logs to custody logger."""
        session_id = uuid4()
        
        entry = EpisodicEntry(
            case_id="CASE-LOG-001",
            agent_id="test_agent",
            session_id=session_id,
            signature_type=ForensicSignatureType.OBJECT_DETECTION,
            finding_type="weapon_detected",
            confidence=0.92,
            summary="Weapon detected in image",
        )
        
        embedding = generate_random_embedding()
        
        await episodic_memory.store(entry, embedding)
        
        # Get chain
        chain = await episodic_memory._custody_logger.get_session_chain(session_id)
        
        # Find MEMORY_WRITE
        memory_writes = [e for e in chain if e.entry_type == EntryType.MEMORY_WRITE]
        
        assert len(memory_writes) >= 1
        
        # Verify content
        store_log = memory_writes[0]
        assert store_log.content["operation"] == "store_episodic"
        assert store_log.content["case_id"] == "CASE-LOG-001"
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_query_logs_memory_read_to_custody_logger(
        self,
        episodic_memory: EpisodicMemory,
    ):
        """Test that query logs to custody logger."""
        session_id = uuid4()
        
        # Store an entry first
        entry = EpisodicEntry(
            case_id="CASE-QUERY-LOG",
            agent_id="test_agent",
            session_id=session_id,
            signature_type=ForensicSignatureType.VIDEO_ARTIFACT,
            finding_type="frame_drop",
            confidence=0.75,
            summary="Frame drop detected",
        )
        
        embedding = generate_random_embedding()
        await episodic_memory.store(entry, embedding)
        
        # Clear chain for cleaner test
        # Query
        results = await episodic_memory.query(
            query_embedding=embedding,
            top_k=5,
        )
        
        # Get chain
        chain = await episodic_memory._custody_logger.get_session_chain(session_id)
        
        # Find MEMORY_READ
        memory_reads = [e for e in chain if e.entry_type == EntryType.MEMORY_READ]
        
        # Should have at least one read from query
        assert len(memory_reads) >= 1
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_by_session(
        self,
        episodic_memory: EpisodicMemory,
    ):
        """Test getting entries by session."""
        session_id = uuid4()
        
        # Store entries for session
        embedding = generate_random_embedding()
        
        for i in range(2):
            entry = EpisodicEntry(
                case_id=f"CASE-SESSION-{i}",
                agent_id="test_agent",
                session_id=session_id,
                signature_type=ForensicSignatureType.MANIPULATION_SIGNATURE,
                finding_type=f"finding_{i}",
                confidence=0.85,
                summary=f"Summary {i}",
            )
            await episodic_memory.store(entry, embedding.copy())
        
        # Get by session
        results = await episodic_memory.get_by_session(session_id)
        
        assert len(results) >= 2
        for result in results:
            assert result.session_id == session_id
