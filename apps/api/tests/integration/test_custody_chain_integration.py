"""
Integration tests verifying chain-of-custody integrity end-to-end.
Critical for legal admissibility of forensic reports.
"""
import hashlib
import pytest
from datetime import UTC, datetime
from uuid import uuid4
from unittest.mock import AsyncMock

from core.custody_logger import CustodyLogger, EntryType
from core.evidence import EvidenceArtifact, ArtifactType

@pytest.mark.integration
class TestCustodyChainIntegrity:
    """Verify custody entries are immutable and cryptographically linked."""
    
    @pytest.fixture
    def custody_logger(self, mock_postgres):
        # We need to ensure mock_postgres has 'fetch' method which is used by CustodyLogger.get_session_chain
        if not hasattr(mock_postgres, "fetch"):
            mock_postgres.fetch = mock_postgres.fetch_all
        return CustodyLogger(postgres_client=mock_postgres)
    
    @pytest.fixture
    def evidence_artifact(self):
        # EvidenceArtifact.create_root takes session_id as UUID
        session_id = uuid4()
        return EvidenceArtifact.create_root(
            artifact_type=ArtifactType.ORIGINAL,
            file_path="/evidence/sample.jpg",
            content_hash=hashlib.sha256(b"test").hexdigest(),
            action="upload",
            agent_id="system",
            session_id=session_id,
            metadata={"original_filename": "sample.jpg"}
        )
    
    @pytest.mark.asyncio
    async def test_custody_entry_creates_linked_hash(self, custody_logger, evidence_artifact):
        """Each custody entry should include hash of previous entry."""
        # Mock fetch_one for _get_last_entry_hash
        custody_logger._postgres.fetch_one.side_effect = [None, None] # Initial check and first get_last_entry_hash
        
        # First entry
        entry1_id = await custody_logger.log_entry(
            agent_id="agent-img",
            session_id=evidence_artifact.session_id,
            entry_type=EntryType.ACTION,
            content={"action": "analysis_start"}
        )
        assert entry1_id is not None
        
        # Capture the call to execute to verify prior_entry_ref
        # query, entry_id, entry_type, agent_id, session_id, timestamp, content, content_hash, signature, prior_entry_ref
        call_args = custody_logger._postgres.execute.call_args[0]
        assert call_args[9] is None  # prior_entry_ref for first entry
        
        # Second entry should reference first
        first_entry_hash = call_args[7]
        custody_logger._postgres.fetch_one.side_effect = [{"content_hash": first_entry_hash}]
        
        entry2_id = await custody_logger.log_entry(
            agent_id="agent-img",
            session_id=evidence_artifact.session_id,
            entry_type=EntryType.ACTION,
            content={"finding_id": "f123"}
        )
        assert entry2_id is not None
        
        call_args2 = custody_logger._postgres.execute.call_args[0]
        assert call_args2[9] == first_entry_hash

    @pytest.mark.asyncio
    async def test_custody_chain_verification(self, custody_logger, evidence_artifact):
        """Verify entire chain cryptographically."""
        from core.custody_logger import ChainEntry
        from core.signing import sign_content
        
        session_id = evidence_artifact.session_id
        
        # Create real signed entries for verification to pass
        content1 = {"step": 0}
        signed1 = sign_content("agent-0", content1)
        
        entry1 = ChainEntry(
            entry_id=uuid4(),
            entry_type=EntryType.ACTION,
            agent_id="agent-0",
            session_id=session_id,
            timestamp_utc=signed1.timestamp_utc,
            content=content1,
            content_hash=signed1.content_hash,
            signature=signed1.signature,
            prior_entry_ref=None
        )
        
        content2 = {"step": 1}
        signed2 = sign_content("agent-1", content2)
        entry2 = ChainEntry(
            entry_id=uuid4(),
            entry_type=EntryType.ACTION,
            agent_id="agent-1",
            session_id=session_id,
            timestamp_utc=signed2.timestamp_utc,
            content=content2,
            content_hash=signed2.content_hash,
            signature=signed2.signature,
            prior_entry_ref=entry1.content_hash
        )
        
        # Mock get_session_chain
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(custody_logger, "get_session_chain", AsyncMock(return_value=[entry1, entry2]))
            
            report = await custody_logger.verify_chain(session_id=session_id)
            assert report.valid is True
            assert report.total_entries == 2

    @pytest.mark.asyncio
    async def test_custody_chain_verification_failure(self, custody_logger, evidence_artifact):
        """Verify chain verification fails when a link is broken."""
        from core.custody_logger import ChainEntry
        from core.signing import sign_content
        
        session_id = evidence_artifact.session_id
        
        signed1 = sign_content("agent-0", {"step": 0})
        entry1 = ChainEntry(
            entry_id=uuid4(),
            entry_type=EntryType.ACTION,
            agent_id="agent-0",
            session_id=session_id,
            timestamp_utc=signed1.timestamp_utc,
            content={"step": 0},
            content_hash=signed1.content_hash,
            signature=signed1.signature,
            prior_entry_ref=None
        )
        
        signed2 = sign_content("agent-1", {"step": 1})
        entry2 = ChainEntry(
            entry_id=uuid4(),
            entry_type=EntryType.ACTION,
            agent_id="agent-1",
            session_id=session_id,
            timestamp_utc=signed2.timestamp_utc,
            content={"step": 1},
            content_hash=signed2.content_hash,
            signature=signed2.signature,
            prior_entry_ref="WRONG_HASH"  # Broken link
        )
        
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(custody_logger, "get_session_chain", AsyncMock(return_value=[entry1, entry2]))
            
            report = await custody_logger.verify_chain(session_id=session_id)
            assert report.valid is False
            assert report.broken_reason == "Chain link broken - prior_entry_ref mismatch"
