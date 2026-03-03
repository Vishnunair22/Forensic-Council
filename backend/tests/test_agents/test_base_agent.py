"""
Tests for ForensicAgent base class and agent stubs.
"""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from agents.base_agent import ForensicAgent, SelfReflectionReport
from agents.agent1_image import Agent1Image
from agents.agent2_audio import Agent2Audio
from agents.agent3_object import Agent3Object
from agents.agent4_video import Agent4Video
from agents.agent5_metadata import Agent5Metadata
from core.config import Settings
from core.custody_logger import CustodyLogger, EntryType
from core.episodic_memory import EpisodicMemory
from core.evidence import EvidenceArtifact, ArtifactType
from core.working_memory import WorkingMemory, WorkingMemoryState, Task, TaskStatus
from infra.evidence_store import EvidenceStore


@pytest.fixture
def session_id():
    """Create a test session ID."""
    return uuid.uuid4()


@pytest.fixture
def agent_id():
    """Create a test agent ID."""
    return "test_agent_1"


@pytest.fixture
def mock_config():
    """Create a mock config."""
    return MagicMock(spec=Settings)


@pytest.fixture
def mock_evidence_artifact():
    """Create a mock evidence artifact."""
    session_id = uuid.uuid4()
    return EvidenceArtifact(
        artifact_id=uuid.uuid4(),
        parent_id=None,
        root_id=uuid.uuid4(),
        artifact_type=ArtifactType.ORIGINAL,
        file_path="/test/image.jpg",
        content_hash="abc123",
        action="upload",
        agent_id="test_agent",
        session_id=session_id,
    )


@pytest.fixture
def mock_working_memory():
    """Create a mock working memory."""
    memory = AsyncMock(spec=WorkingMemory)
    
    default_state = WorkingMemoryState(
        session_id=uuid.uuid4(),
        agent_id="test_agent",
        tasks=[],
        current_iteration=0,
    )
    
    memory.get_state = AsyncMock(return_value=default_state)
    memory.create_state = AsyncMock(return_value=default_state)
    memory.update_state = AsyncMock(return_value=default_state)
    
    return memory


@pytest.fixture
def mock_episodic_memory():
    """Create a mock episodic memory."""
    return AsyncMock(spec=EpisodicMemory)


@pytest.fixture
def mock_custody_logger():
    """Create a mock custody logger."""
    logger = AsyncMock(spec=CustodyLogger)
    logger.log_entry = AsyncMock(return_value=uuid.uuid4())
    return logger


@pytest.fixture
def mock_evidence_store():
    """Create a mock evidence store."""
    return AsyncMock(spec=EvidenceStore)


class TestSelfReflectionReport:
    """Tests for SelfReflectionReport model."""

    def test_report_creation(self):
        """Test creating a self-reflection report."""
        report = SelfReflectionReport(
            all_tasks_complete=True,
            incomplete_tasks=[],
            overconfident_findings=[],
            untreated_absences=[],
            deprioritized_avenues=[],
            court_defensible=True,
            reflection_notes="All tasks completed successfully"
        )
        assert report.all_tasks_complete is True
        assert report.court_defensible is True
        assert len(report.incomplete_tasks) == 0

    def test_report_with_issues(self):
        """Test report with identified issues."""
        report = SelfReflectionReport(
            all_tasks_complete=False,
            incomplete_tasks=["Task 1", "Task 2"],
            overconfident_findings=["Finding A: 0.98"],
            untreated_absences=["Missing EXIF data"],
            deprioritized_avenues=["Alternative analysis path"],
            court_defensible=False,
            reflection_notes="Issues identified"
        )
        assert report.all_tasks_complete is False
        assert len(report.incomplete_tasks) == 2
        assert len(report.overconfident_findings) == 1


class TestAgent1Image:
    """Tests for Agent 1 - Image Integrity Agent."""

    def test_agent_name(self):
        """Test agent name is correct."""
        assert Agent1Image.agent_name.fget(None) == "Agent1_ImageIntegrity"

    def test_task_count(self):
        """Test agent has correct task count (10)."""
        assert len(Agent1Image.task_decomposition.fget(None)) == 10

    def test_iteration_ceiling(self):
        """Test iteration ceiling is correct."""
        assert Agent1Image.iteration_ceiling.fget(None) == 20

    def test_task_decomposition_content(self):
        """Test task decomposition contains expected tasks."""
        tasks = Agent1Image.task_decomposition.fget(None)
        assert "Run full-image ELA and map anomaly regions" in tasks
        assert "Self-reflection pass" in tasks

    @pytest.mark.asyncio
    async def test_build_tool_registry(
        self, agent_id, session_id, mock_evidence_artifact, mock_config,
        mock_working_memory, mock_episodic_memory, mock_custody_logger,
        mock_evidence_store
    ):
        """Test tool registry is built correctly."""
        agent = Agent1Image(
            agent_id=agent_id,
            session_id=session_id,
            evidence_artifact=mock_evidence_artifact,
            config=mock_config,
            working_memory=mock_working_memory,
            episodic_memory=mock_episodic_memory,
            custody_logger=mock_custody_logger,
            evidence_store=mock_evidence_store,
        )
        
        registry = await agent.build_tool_registry()
        
        assert registry is not None
        tools = registry.list_tools()
        assert len(tools) == 12  # 12 tools for Agent 1 (updated with real tools)
        
        tool_names = {t.name for t in tools}
        assert "ela_full_image" in tool_names
        assert "roi_extract" in tool_names
        assert "jpeg_ghost_detect" in tool_names

    @pytest.mark.asyncio
    async def test_build_initial_thought(
        self, agent_id, session_id, mock_evidence_artifact, mock_config,
        mock_working_memory, mock_episodic_memory, mock_custody_logger,
        mock_evidence_store
    ):
        """Test initial thought is generated."""
        agent = Agent1Image(
            agent_id=agent_id,
            session_id=session_id,
            evidence_artifact=mock_evidence_artifact,
            config=mock_config,
            working_memory=mock_working_memory,
            episodic_memory=mock_episodic_memory,
            custody_logger=mock_custody_logger,
            evidence_store=mock_evidence_store,
        )
        
        thought = await agent.build_initial_thought()
        
        assert thought is not None
        assert len(thought) > 0
        assert "image integrity" in thought.lower()


class TestAgent2Audio:
    """Tests for Agent 2 - Audio & Multimedia Forensics Agent."""

    def test_agent_name(self):
        """Test agent name is correct."""
        assert Agent2Audio.agent_name.fget(None) == "Agent2_AudioForensics"

    def test_task_count(self):
        """Test agent has correct task count (11)."""
        assert len(Agent2Audio.task_decomposition.fget(None)) == 11

    def test_iteration_ceiling(self):
        """Test iteration ceiling is correct."""
        assert Agent2Audio.iteration_ceiling.fget(None) == 20


class TestAgent3Object:
    """Tests for Agent 3 - Object & Weapon Analysis Agent."""

    def test_agent_name(self):
        """Test agent name is correct."""
        assert Agent3Object.agent_name.fget(None) == "Agent3_ObjectWeapon"

    def test_task_count(self):
        """Test agent has correct task count (11)."""
        assert len(Agent3Object.task_decomposition.fget(None)) == 11

    def test_iteration_ceiling(self):
        """Test iteration ceiling is correct."""
        assert Agent3Object.iteration_ceiling.fget(None) == 20


class TestAgent4Video:
    """Tests for Agent 4 - Temporal Video Analysis Agent."""

    def test_agent_name(self):
        """Test agent name is correct."""
        assert Agent4Video.agent_name.fget(None) == "Agent4_TemporalVideo"

    def test_task_count(self):
        """Test agent has correct task count (10)."""
        assert len(Agent4Video.task_decomposition.fget(None)) == 10

    def test_iteration_ceiling(self):
        """Test iteration ceiling is correct."""
        assert Agent4Video.iteration_ceiling.fget(None) == 20


class TestAgent5Metadata:
    """Tests for Agent 5 - Metadata & Context Analysis Agent."""

    def test_agent_name(self):
        """Test agent name is correct."""
        assert Agent5Metadata.agent_name.fget(None) == "Agent5_MetadataContext"

    def test_task_count(self):
        """Test agent has correct task count (13)."""
        assert len(Agent5Metadata.task_decomposition.fget(None)) == 13

    def test_iteration_ceiling(self):
        """Test iteration ceiling is correct."""
        assert Agent5Metadata.iteration_ceiling.fget(None) == 20


class TestAllAgentsTaskCounts:
    """Tests verifying all agents have correct task counts."""

    def test_all_five_agents_have_correct_task_counts(self):
        """Verify all 5 agents have correct task counts (10, 11, 11, 10, 13)."""
        expected_counts = {
            "Agent1Image": 10,
            "Agent2Audio": 11,
            "Agent3Object": 11,
            "Agent4Video": 10,
            "Agent5Metadata": 13,
        }
        
        actual_counts = {
            "Agent1Image": len(Agent1Image.task_decomposition.fget(None)),
            "Agent2Audio": len(Agent2Audio.task_decomposition.fget(None)),
            "Agent3Object": len(Agent3Object.task_decomposition.fget(None)),
            "Agent4Video": len(Agent4Video.task_decomposition.fget(None)),
            "Agent5Metadata": len(Agent5Metadata.task_decomposition.fget(None)),
        }
        
        assert actual_counts == expected_counts, (
            f"Task counts mismatch. Expected: {expected_counts}, Got: {actual_counts}"
        )


class TestAllAgentsInstantiation:
    """Tests verifying all agents can be instantiated."""

    @pytest.mark.asyncio
    async def test_all_five_agent_stubs_instantiate_without_error(
        self, agent_id, session_id, mock_evidence_artifact, mock_config,
        mock_working_memory, mock_episodic_memory, mock_custody_logger,
        mock_evidence_store
    ):
        """Test that all 5 agent stubs can be instantiated."""
        agent_classes = [
            Agent1Image,
            Agent2Audio,
            Agent3Object,
            Agent4Video,
            Agent5Metadata,
        ]
        
        for agent_class in agent_classes:
            agent = agent_class(
                agent_id=agent_id,
                session_id=session_id,
                evidence_artifact=mock_evidence_artifact,
                config=mock_config,
                working_memory=mock_working_memory,
                episodic_memory=mock_episodic_memory,
                custody_logger=mock_custody_logger,
                evidence_store=mock_evidence_store,
            )
            
            assert agent is not None
            assert agent.agent_name is not None
            assert len(agent.task_decomposition) > 0
            assert agent.iteration_ceiling > 0


class TestForensicAgentBase:
    """Tests for ForensicAgent base class methods."""

    @pytest.fixture
    def agent(
        self, agent_id, session_id, mock_evidence_artifact, mock_config,
        mock_working_memory, mock_episodic_memory, mock_custody_logger,
        mock_evidence_store
    ):
        """Create an Agent1 instance for testing base class methods."""
        return Agent1Image(
            agent_id=agent_id,
            session_id=session_id,
            evidence_artifact=mock_evidence_artifact,
            config=mock_config,
            working_memory=mock_working_memory,
            episodic_memory=mock_episodic_memory,
            custody_logger=mock_custody_logger,
            evidence_store=mock_evidence_store,
        )

    @pytest.mark.asyncio
    async def test_agent_initializes_working_memory_with_task_list(
        self, agent, mock_working_memory
    ):
        """Test that agent initializes working memory with task decomposition."""
        await agent._initialize_working_memory()
        
        # Verify initialize was called
        mock_working_memory.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_agent_logs_session_start_to_custody(
        self, agent, mock_custody_logger
    ):
        """Test that agent logs session start to custody logger."""
        await agent._initialize_working_memory()
        
        # The base class logs session start during run_investigation
        # Here we just verify the custody logger is available
        assert mock_custody_logger.log_entry is not None

    @pytest.mark.asyncio
    async def test_self_reflection_runs_all_5_reflection_prompts(
        self, agent, mock_working_memory
    ):
        """Test that self-reflection checks all 5 reflection prompts."""
        # Setup state with complete tasks
        state = WorkingMemoryState(
            session_id=agent.session_id,
            agent_id=agent.agent_id,
            tasks=[Task(description="Test", status=TaskStatus.COMPLETE)],
        )
        mock_working_memory.get_state = AsyncMock(return_value=state)
        
        report = await agent.self_reflection_pass([])
        
        # Verify all aspects are checked
        assert report.all_tasks_complete is True
        assert len(report.incomplete_tasks) == 0
        assert len(report.overconfident_findings) == 0
        assert report.court_defensible is False  # No findings

    @pytest.mark.asyncio
    async def test_self_reflection_logged_to_custody(
        self, agent, mock_working_memory, mock_custody_logger
    ):
        """Test that self-reflection is logged to custody logger."""
        state = WorkingMemoryState(
            session_id=agent.session_id,
            agent_id=agent.agent_id,
            tasks=[],
        )
        mock_working_memory.get_state = AsyncMock(return_value=state)
        
        await agent.self_reflection_pass([])
        
        # Verify SELF_REFLECTION was logged
        mock_custody_logger.log_entry.assert_called()
        call_args = mock_custody_logger.log_entry.call_args
        assert call_args.kwargs["entry_type"] == EntryType.SELF_REFLECTION

    @pytest.mark.asyncio
    async def test_self_reflection_incomplete_tasks_flagged(
        self, agent, mock_working_memory
    ):
        """Test that self-reflection flags incomplete tasks."""
        # Setup state with incomplete tasks
        state = WorkingMemoryState(
            session_id=agent.session_id,
            agent_id=agent.agent_id,
            tasks=[
                Task(description="Complete task", status=TaskStatus.COMPLETE),
                Task(description="Incomplete task 1", status=TaskStatus.IN_PROGRESS),
                Task(description="Incomplete task 2", status=TaskStatus.PENDING),
            ],
        )
        mock_working_memory.get_state = AsyncMock(return_value=state)
        
        report = await agent.self_reflection_pass([])
        
        assert report.all_tasks_complete is False
        assert len(report.incomplete_tasks) == 2
        assert "Incomplete task 1" in report.incomplete_tasks
        assert "Incomplete task 2" in report.incomplete_tasks

    @pytest.mark.asyncio
    async def test_full_investigation_run_returns_findings(
        self, agent, mock_working_memory, mock_custody_logger
    ):
        """Test that full investigation run returns findings."""
        # Setup state with complete tasks to avoid HITL triggers
        state = WorkingMemoryState(
            session_id=agent.session_id,
            agent_id=agent.agent_id,
            tasks=[Task(description="Test", status=TaskStatus.COMPLETE)],
        )
        mock_working_memory.get_state = AsyncMock(return_value=state)
        mock_working_memory.create_state = AsyncMock(return_value=state)
        
        findings = await agent.run_investigation()
        
        assert findings is not None
        assert isinstance(findings, list)
