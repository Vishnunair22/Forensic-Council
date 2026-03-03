"""
Custody Logger Tests
====================

Tests for chain-of-custody logging and verification.
"""

import pytest
from uuid import uuid4, UUID

from core.custody_logger import (
    CustodyLogger,
    EntryType,
    ChainEntry,
    ChainVerificationReport,
)
from core.signing import KeyStore
from infra.postgres_client import PostgresClient


@pytest.fixture
async def custody_logger(postgres_client: PostgresClient) -> CustodyLogger:
    """Create a CustodyLogger with PostgreSQL client."""
    logger = CustodyLogger(postgres_client=postgres_client)
    return logger


class TestEntryType:
    """Tests for EntryType enum."""
    
    def test_all_entry_types_exist(self):
        """Test that all required entry types are defined."""
        expected_types = [
            "THOUGHT", "ACTION", "OBSERVATION", "TOOL_CALL",
            "INTER_AGENT_CALL", "HITL_CHECKPOINT", "HUMAN_INTERVENTION",
            "MEMORY_READ", "MEMORY_WRITE", "ARTIFACT_VERSION",
            "CALIBRATION", "SELF_REFLECTION", "FINAL_FINDING",
            "TRIBUNAL_JUDGMENT", "REPORT_SIGNED"
        ]
        
        for type_name in expected_types:
            assert hasattr(EntryType, type_name)
    
    def test_entry_type_values(self):
        """Test that entry type values match names."""
        assert EntryType.THOUGHT.value == "THOUGHT"
        assert EntryType.ACTION.value == "ACTION"
        assert EntryType.HITL_CHECKPOINT.value == "HITL_CHECKPOINT"


class TestCustodyLogger:
    """Tests for CustodyLogger class."""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_log_single_entry_returns_uuid(
        self, custody_logger: CustodyLogger
    ):
        """Test that logging an entry returns a UUID."""
        session_id = uuid4()
        
        entry_id = await custody_logger.log_entry(
            agent_id="test_agent",
            session_id=session_id,
            entry_type=EntryType.THOUGHT,
            content={"thought": "Analyzing evidence..."},
        )
        
        assert isinstance(entry_id, UUID)
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_chain_links_entries_by_prior_ref(
        self, custody_logger: CustodyLogger
    ):
        """Test that entries are linked via prior_entry_ref."""
        session_id = uuid4()
        
        # Log first entry
        entry_id_1 = await custody_logger.log_entry(
            agent_id="agent_1",
            session_id=session_id,
            entry_type=EntryType.THOUGHT,
            content={"thought": "First thought"},
        )
        
        # Log second entry
        entry_id_2 = await custody_logger.log_entry(
            agent_id="agent_1",
            session_id=session_id,
            entry_type=EntryType.ACTION,
            content={"action": "Run analysis"},
        )
        
        # Get chain
        chain = await custody_logger.get_session_chain(session_id)
        
        assert len(chain) == 2
        
        # First entry should have no prior
        assert chain[0].prior_entry_ref is None
        
        # Second entry should link to first
        assert chain[1].prior_entry_ref == chain[0].content_hash
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_verify_chain_passes_clean_chain(
        self, custody_logger: CustodyLogger
    ):
        """Test that verification passes for a valid chain."""
        session_id = uuid4()
        
        # Log several entries
        await custody_logger.log_entry(
            agent_id="agent_1",
            session_id=session_id,
            entry_type=EntryType.THOUGHT,
            content={"thought": "Starting analysis"},
        )
        
        await custody_logger.log_entry(
            agent_id="agent_1",
            session_id=session_id,
            entry_type=EntryType.ACTION,
            content={"action": "Running tool"},
        )
        
        await custody_logger.log_entry(
            agent_id="agent_1",
            session_id=session_id,
            entry_type=EntryType.OBSERVATION,
            content={"observation": "Tool result"},
        )
        
        # Verify chain
        report = await custody_logger.verify_chain(session_id)
        
        assert report.valid is True
        assert report.total_entries == 3
        assert report.broken_at is None
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_verify_chain_detects_tampered_entry(
        self, custody_logger: CustodyLogger
    ):
        """Test that verification detects a tampered entry."""
        session_id = uuid4()
        
        # Log entry
        entry_id = await custody_logger.log_entry(
            agent_id="agent_1",
            session_id=session_id,
            entry_type=EntryType.THOUGHT,
            content={"thought": "Original thought"},
        )
        
        # Tamper with the entry
        await custody_logger.tamper_entry(
            entry_id=entry_id,
            new_content={"thought": "TAMPERED CONTENT"},
        )
        
        # Verify chain
        report = await custody_logger.verify_chain(session_id)
        
        assert report.valid is False
        assert report.broken_at is not None
        assert report.broken_at == entry_id
        assert "Signature verification failed" in report.broken_reason
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_session_chain_returns_ordered_entries(
        self, custody_logger: CustodyLogger
    ):
        """Test that get_session_chain returns entries in order."""
        session_id = uuid4()
        
        # Log multiple entries
        await custody_logger.log_entry(
            agent_id="agent_1",
            session_id=session_id,
            entry_type=EntryType.THOUGHT,
            content={"order": 1},
        )
        
        await custody_logger.log_entry(
            agent_id="agent_1",
            session_id=session_id,
            entry_type=EntryType.ACTION,
            content={"order": 2},
        )
        
        await custody_logger.log_entry(
            agent_id="agent_1",
            session_id=session_id,
            entry_type=EntryType.OBSERVATION,
            content={"order": 3},
        )
        
        # Get chain
        chain = await custody_logger.get_session_chain(session_id)
        
        assert len(chain) == 3
        
        # Verify order
        assert chain[0].content["order"] == 1
        assert chain[1].content["order"] == 2
        assert chain[2].content["order"] == 3
        
        # Verify types
        assert chain[0].entry_type == EntryType.THOUGHT
        assert chain[1].entry_type == EntryType.ACTION
        assert chain[2].entry_type == EntryType.OBSERVATION
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_different_sessions_have_separate_chains(
        self, custody_logger: CustodyLogger
    ):
        """Test that different sessions have separate chains."""
        session_1 = uuid4()
        session_2 = uuid4()
        
        # Log to session 1
        await custody_logger.log_entry(
            agent_id="agent_1",
            session_id=session_1,
            entry_type=EntryType.THOUGHT,
            content={"session": 1},
        )
        
        # Log to session 2
        await custody_logger.log_entry(
            agent_id="agent_1",
            session_id=session_2,
            entry_type=EntryType.THOUGHT,
            content={"session": 2},
        )
        
        # Get chains
        chain_1 = await custody_logger.get_session_chain(session_1)
        chain_2 = await custody_logger.get_session_chain(session_2)
        
        assert len(chain_1) == 1
        assert len(chain_2) == 1
        assert chain_1[0].content["session"] == 1
        assert chain_2[0].content["session"] == 2
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_verify_empty_chain(self, custody_logger: CustodyLogger):
        """Test verification of empty chain returns valid."""
        session_id = uuid4()
        
        report = await custody_logger.verify_chain(session_id)
        
        assert report.valid is True
        assert report.total_entries == 0
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_entry(self, custody_logger: CustodyLogger):
        """Test retrieving a specific entry by ID."""
        session_id = uuid4()
        
        entry_id = await custody_logger.log_entry(
            agent_id="test_agent",
            session_id=session_id,
            entry_type=EntryType.ACTION,
            content={"action": "test"},
        )
        
        entry = await custody_logger.get_entry(entry_id)
        
        assert entry is not None
        assert entry.entry_id == entry_id
        assert entry.agent_id == "test_agent"
        assert entry.session_id == session_id
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_nonexistent_entry(self, custody_logger: CustodyLogger):
        """Test retrieving a non-existent entry returns None."""
        entry = await custody_logger.get_entry(uuid4())
        
        assert entry is None


class TestChainEntry:
    """Tests for ChainEntry dataclass."""
    
    def test_from_row(self):
        """Test creating ChainEntry from database row."""
        from datetime import datetime, timezone
        
        row = {
            "entry_id": uuid4(),
            "entry_type": "THOUGHT",
            "agent_id": "test_agent",
            "session_id": uuid4(),
            "timestamp_utc": datetime.now(timezone.utc),
            "content": {"test": "data"},
            "content_hash": "abc123",
            "signature": "sig456",
            "prior_entry_ref": "prev789",
        }
        
        entry = ChainEntry.from_row(row)
        
        assert entry.entry_id == row["entry_id"]
        assert entry.entry_type == EntryType.THOUGHT
        assert entry.agent_id == "test_agent"
        assert entry.content == {"test": "data"}
    
    def test_to_signed_entry(self):
        """Test converting ChainEntry to SignedEntry."""
        from datetime import datetime, timezone
        
        entry = ChainEntry(
            entry_id=uuid4(),
            entry_type=EntryType.ACTION,
            agent_id="agent",
            session_id=uuid4(),
            timestamp_utc=datetime.now(timezone.utc),
            content={"action": "test"},
            content_hash="hash123",
            signature="sig456",
        )
        
        signed = entry.to_signed_entry()
        
        assert signed.content == entry.content
        assert signed.content_hash == entry.content_hash
        assert signed.signature == entry.signature
        assert signed.agent_id == entry.agent_id


class TestChainVerificationReport:
    """Tests for ChainVerificationReport dataclass."""
    
    def test_valid_report(self):
        """Test creating a valid report."""
        report = ChainVerificationReport(
            session_id=uuid4(),
            total_entries=5,
            valid=True,
        )
        
        assert report.valid is True
        assert report.broken_at is None
        assert report.broken_reason is None
    
    def test_invalid_report(self):
        """Test creating an invalid report."""
        entry_id = uuid4()
        report = ChainVerificationReport(
            session_id=uuid4(),
            total_entries=5,
            valid=False,
            broken_at=entry_id,
            broken_reason="Signature verification failed",
        )
        
        assert report.valid is False
        assert report.broken_at == entry_id
        assert "Signature" in report.broken_reason