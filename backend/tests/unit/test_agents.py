"""
Unit tests for agents
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4


class TestBaseAgent:
    """Test cases for base agent."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.app_env = "development"
        settings.debug = True
        settings.signing_key = "a" * 64
        settings.groq_api_key = "test-key"
        return settings

    def test_agent_properties(self):
        """Test agent has required properties."""
        from agents.base_agent import ForensicAgent
        
        # Create a concrete implementation for testing
        class TestAgent(ForensicAgent):
            @property
            def agent_name(self) -> str:
                return "TestAgent"
            
            @property
            def task_decomposition(self) -> list[str]:
                return ["Task 1", "Task 2"]
            
            @property
            def iteration_ceiling(self) -> int:
                return 10
            
            async def build_tool_registry(self):
                return MagicMock()
        
        # Test instantiation
        session_id = str(uuid4())
        agent = TestAgent(
            session_id=session_id,
            evidence=MagicMock(),
            custody_logger=MagicMock(),
            settings=self.mock_settings,
        )
        
        assert agent.agent_name == "TestAgent"
        assert len(agent.task_decomposition) == 2
        assert agent.iteration_ceiling == 10


class TestAgent1Image:
    """Test cases for Agent 1 - Image Forensics."""

    def test_agent_name(self):
        """Test agent 1 has correct name."""
        from agents.agent1_image import Agent1Image
        
        agent = Agent1Image(
            session_id=str(uuid4()),
            evidence=MagicMock(),
            custody_logger=MagicMock(),
            settings=MagicMock(),
        )
        
        assert agent.agent_name == "Agent1_ImageIntegrity"

    def test_task_decomposition(self):
        """Test agent 1 task decomposition."""
        from agents.agent1_image import Agent1Image
        
        agent = Agent1Image(
            session_id=str(uuid4()),
            evidence=MagicMock(),
            custody_logger=MagicMock(),
            settings=MagicMock(),
        )
        
        tasks = agent.task_decomposition
        assert "Run full-image ELA" in tasks[0]
        assert "Self-reflection pass" in tasks

    def test_iteration_ceiling(self):
        """Test agent 1 iteration ceiling."""
        from agents.agent1_image import Agent1Image
        
        agent = Agent1Image(
            session_id=str(uuid4()),
            evidence=MagicMock(),
            custody_logger=MagicMock(),
            settings=MagicMock(),
        )
        
        assert agent.iteration_ceiling == 15


class TestCouncilArbiter:
    """Test cases for Council Arbiter."""

    def test_finding_verdict_enum(self):
        """Test finding verdict enum values."""
        from agents.arbiter import FindingVerdict
        
        assert FindingVerdict.AGREEMENT.value == "AGREEMENT"
        assert FindingVerdict.INDEPENDENT.value == "INDEPENDENT"
        assert FindingVerdict.CONTRADICTION.value == "CONTRADICTION"

    def test_forensic_report_creation(self):
        """Test creating a forensic report."""
        from agents.arbiter import ForensicReport
        from uuid import uuid4
        
        report = ForensicReport(
            session_id=uuid4(),
            case_id="CASE-001",
            executive_summary="Test summary",
            per_agent_findings={},
            uncertainty_statement="No uncertainty",
        )
        
        assert report.session_id is not None
        assert report.case_id == "CASE-001"
        assert report.executive_summary == "Test summary"

    def test_report_signing_fields(self):
        """Test report has signing fields."""
        from agents.arbiter import ForensicReport
        from uuid import uuid4
        
        report = ForensicReport(
            session_id=uuid4(),
            case_id="CASE-001",
            executive_summary="Test summary",
            per_agent_findings={},
            uncertainty_statement="No uncertainty",
        )
        
        assert hasattr(report, "cryptographic_signature")
        assert hasattr(report, "report_hash")
        assert hasattr(report, "signed_utc")
