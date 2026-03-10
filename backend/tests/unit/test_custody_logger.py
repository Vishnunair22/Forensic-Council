"""
Unit tests for core/custody_logger.py
"""

import pytest
from datetime import datetime, timezone
from core.custody_logger import CustodyLogger, EntryType


class TestCustodyLogger:
    """Test cases for CustodyLogger."""

    @pytest.fixture
    def session_id(self):
        """Create a test session ID."""
        return "test-session-12345"

    @pytest.fixture
    def custody_logger(self, session_id):
        """Create a custody logger instance."""
        return CustodyLogger(session_id=session_id)

    def test_initialization(self, custody_logger, session_id):
        """Test custody logger initialization."""
        assert custody_logger.session_id == session_id
        assert custody_logger.entries == []

    def test_log_action(self, custody_logger):
        """Test logging an action."""
        custody_logger.log_action(
            action="UPLOAD",
            actor="system",
            details={"file": "test.jpg"},
        )
        
        assert len(custody_logger.entries) == 1
        entry = custody_logger.entries[0]
        assert entry.entry_type == EntryType.ACTION
        assert entry.action == "UPLOAD"
        assert entry.actor == "system"

    def test_log_observation(self, custody_logger):
        """Test logging an observation."""
        custody_logger.log_observation(
            observation="File hash verified",
            agent_id="Agent1",
        )
        
        assert len(custody_logger.entries) == 1
        entry = custody_logger.entries[0]
        assert entry.entry_type == EntryType.OBSERVATION
        assert entry.observation == "File hash verified"

    def test_log_agent_thinking(self, custody_logger):
        """Test logging agent thinking."""
        custody_logger.log_agent_thinking(
            agent_id="Agent1",
            thought="Analyzing image metadata",
        )
        
        assert len(custody_logger.entries) == 1
        entry = custody_logger.entries[0]
        assert entry.agent_id == "Agent1"

    def test_get_entries(self, custody_logger):
        """Test getting all entries."""
        custody_logger.log_action("ACTION1", "system")
        custody_logger.log_action("ACTION2", "user")
        
        entries = custody_logger.get_entries()
        
        assert len(entries) == 2

    def test_get_entries_by_type(self, custody_logger):
        """Test filtering entries by type."""
        custody_logger.log_action("ACTION1", "system")
        custody_logger.log_observation("OBS1", "Agent1")
        
        actions = custody_logger.get_entries(entry_type=EntryType.ACTION)
        
        assert len(actions) == 1
        assert actions[0].action == "ACTION1"

    def test_get_chain_of_custody(self, custody_logger):
        """Test getting chain of custody."""
        custody_logger.log_action("UPLOAD", "system", {"file": "test.jpg"})
        custody_logger.log_action("ANALYZE", "Agent1", {"tool": "ELA"})
        
        chain = custody_logger.get_chain_of_custody()
        
        assert len(chain) == 2

    def test_serialization(self, custody_logger):
        """Test serialization."""
        custody_logger.log_action("ACTION1", "system", {"key": "value"})
        
        data = custody_logger.to_dict()
        
        assert "session_id" in data
        assert "entries" in data
        assert len(data["entries"]) == 1
