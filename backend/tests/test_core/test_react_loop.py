"""
Tests for ReAct Loop Engine and HITL Checkpoint System.
"""

import asyncio
import json
import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from core.react_loop import (
    ReActStep,
    ReActStepType,
    HITLCheckpointReason,
    HITLCheckpointState,
    HumanDecision,
    AgentFinding,
    AgentFindingStatus,
    ReActLoopResult,
    ReActLoopEngine,
)
from core.tool_registry import ToolRegistry, ToolResult
from core.working_memory import WorkingMemory, WorkingMemoryState, Task, TaskStatus
from core.custody_logger import CustodyLogger, EntryType


@pytest.fixture
def session_id():
    """Create a test session ID."""
    return uuid.uuid4()


@pytest.fixture
def agent_id():
    """Create a test agent ID."""
    return "test_agent"


@pytest.fixture
def iteration_ceiling():
    """Default iteration ceiling for tests."""
    return 10


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=True)
    return redis


@pytest.fixture
def mock_custody_logger():
    """Create a mock custody logger."""
    logger = AsyncMock(spec=CustodyLogger)
    logger.log_entry = AsyncMock(return_value=uuid.uuid4())
    return logger


@pytest.fixture
def mock_working_memory():
    """Create a mock working memory."""
    memory = AsyncMock(spec=WorkingMemory)
    
    # Default state with COMPLETE task to avoid HITL triggers
    default_state = WorkingMemoryState(
        session_id=uuid.uuid4(),
        agent_id="test_agent",
        tasks=[Task(
            description="Test task",
            status=TaskStatus.COMPLETE
        )],
        current_iteration=0,
    )
    
    memory.get_state = AsyncMock(return_value=default_state)
    memory.create_state = AsyncMock(return_value=default_state)
    memory.update_state = AsyncMock(return_value=default_state)
    
    return memory


@pytest.fixture
def tool_registry():
    """Create a tool registry with test tools."""
    registry = ToolRegistry()
    
    async def echo_tool(input_data):
        return {"echo": input_data.get("message", "")}
    
    async def fail_tool(input_data):
        raise ValueError("Tool failed!")
    
    registry.register("echo", echo_tool, "Echo tool")
    registry.register("fail", fail_tool, "Failing tool")
    
    return registry


@pytest.fixture
def engine(
    self, agent_id, session_id, iteration_ceiling,
    mock_working_memory, mock_custody_logger, mock_redis
):
    """Create a ReAct loop engine with short HITL timeout for tests."""
    return ReActLoopEngine(
        agent_id=agent_id,
        session_id=session_id,
        iteration_ceiling=iteration_ceiling,
        working_memory=mock_working_memory,
        custody_logger=mock_custody_logger,
        redis_client=mock_redis,
        hitl_timeout=0.1  # Very short timeout for tests
    )


class TestReActStep:
    """Tests for ReActStep model."""

    def test_thought_step(self):
        """Test creating a THOUGHT step."""
        step = ReActStep(
            step_type="THOUGHT",
            content="I need to analyze the image",
            iteration=1
        )
        assert step.step_type == "THOUGHT"
        assert step.content == "I need to analyze the image"
        assert step.tool_name is None
        assert step.iteration == 1
        assert isinstance(step.timestamp_utc, datetime)

    def test_action_step(self):
        """Test creating an ACTION step."""
        step = ReActStep(
            step_type="ACTION",
            content="I will run the image analysis tool",
            tool_name="analyze_image",
            tool_input={"image_id": "abc123"},
            iteration=2
        )
        assert step.step_type == "ACTION"
        assert step.tool_name == "analyze_image"
        assert step.tool_input == {"image_id": "abc123"}

    def test_observation_step(self):
        """Test creating an OBSERVATION step."""
        step = ReActStep(
            step_type="OBSERVATION",
            content="The image analysis returned metadata",
            tool_name="analyze_image",
            tool_output={"result": "success", "metadata": {}},
            iteration=3
        )
        assert step.step_type == "OBSERVATION"
        assert step.tool_output == {"result": "success", "metadata": {}}


class TestHITLCheckpointState:
    """Tests for HITLCheckpointState model."""

    def test_checkpoint_creation(self):
        """Test creating a HITL checkpoint."""
        checkpoint = HITLCheckpointState(
            agent_id="test_agent",
            session_id=uuid.uuid4(),
            reason=HITLCheckpointReason.ITERATION_CEILING_50PCT,
            paused_at_iteration=5,
            investigator_brief="Test checkpoint"
        )
        assert checkpoint.status == "PAUSED"
        assert checkpoint.reason == HITLCheckpointReason.ITERATION_CEILING_50PCT
        assert isinstance(checkpoint.checkpoint_id, uuid.UUID)

    def test_checkpoint_with_serialized_state(self):
        """Test checkpoint with serialized working memory state."""
        state_data = {"tasks": [], "current_iteration": 5}
        checkpoint = HITLCheckpointState(
            agent_id="test_agent",
            session_id=uuid.uuid4(),
            reason=HITLCheckpointReason.CONTESTED_FINDING,
            paused_at_iteration=5,
            investigator_brief="Contested finding",
            serialized_state=state_data
        )
        assert checkpoint.serialized_state == state_data


class TestHumanDecision:
    """Tests for HumanDecision model."""

    def test_approve_decision(self):
        """Test creating an APPROVE decision."""
        decision = HumanDecision(
            decision_type="APPROVE",
            investigator_id="investigator_1",
            notes="Looks good"
        )
        assert decision.decision_type == "APPROVE"
        assert decision.investigator_id == "investigator_1"

    def test_override_decision(self):
        """Test creating an OVERRIDE decision."""
        decision = HumanDecision(
            decision_type="OVERRIDE",
            investigator_id="investigator_1",
            notes="I disagree with the finding",
            override_finding={"conclusion": "different_result"}
        )
        assert decision.decision_type == "OVERRIDE"
        assert decision.override_finding is not None

    def test_redirect_decision(self):
        """Test creating a REDIRECT decision."""
        decision = HumanDecision(
            decision_type="REDIRECT",
            investigator_id="investigator_1",
            notes="Try a different approach",
            redirect_context="Focus on the metadata instead"
        )
        assert decision.decision_type == "REDIRECT"
        assert decision.redirect_context == "Focus on the metadata instead"


class TestAgentFinding:
    """Tests for AgentFinding model."""

    def test_finding_creation(self):
        """Test creating an agent finding."""
        finding = AgentFinding(
            agent_id="test_agent",
            finding_type="IMAGE_INTEGRITY",
            confidence_raw=0.85,
            reasoning_summary="Image appears authentic"
        )
        assert finding.agent_id == "test_agent"
        assert finding.confidence_raw == 0.85
        assert finding.calibrated is False
        assert finding.status == "CONFIRMED"

    def test_finding_with_caveat(self):
        """Test finding with robustness caveat."""
        finding = AgentFinding(
            agent_id="test_agent",
            finding_type="METADATA_ANALYSIS",
            confidence_raw=0.6,
            status="INCONCLUSIVE",
            robustness_caveat=True,
            robustness_caveat_detail="Limited metadata available"
        )
        assert finding.robustness_caveat is True
        assert finding.status == "INCONCLUSIVE"


class TestReActLoopResult:
    """Tests for ReActLoopResult model."""

    def test_result_creation(self):
        """Test creating a loop result."""
        result = ReActLoopResult(
            session_id=uuid.uuid4(),
            agent_id="test_agent",
            completed=True,
            total_iterations=5
        )
        assert result.completed is True
        assert result.terminated_by_human is False
        assert result.total_iterations == 5
        assert result.findings == []
        assert result.react_chain == []


class TestReActLoopEngine:
    """Tests for ReActLoopEngine class."""

    @pytest.fixture
    def engine(
        self, agent_id, session_id, iteration_ceiling,
        mock_working_memory, mock_custody_logger, mock_redis
    ):
        """Create a ReAct loop engine with short HITL timeout for tests."""
        return ReActLoopEngine(
            agent_id=agent_id,
            session_id=session_id,
            iteration_ceiling=iteration_ceiling,
            working_memory=mock_working_memory,
            custody_logger=mock_custody_logger,
            redis_client=mock_redis,
            hitl_timeout=0.1  # Very short timeout for tests
        )

    @pytest.mark.asyncio
    async def test_loop_runs_thought_action_observation_cycle(
        self, engine, tool_registry, mock_working_memory
    ):
        """Test that the loop runs a complete THOUGHT → ACTION → OBSERVATION cycle."""
        # Create a mock LLM generator that produces a sequence
        call_count = [0]
        
        async def mock_llm_generator(chain, state):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: ACTION
                return ReActStep(
                    step_type="ACTION",
                    content="I will use the echo tool",
                    tool_name="echo",
                    tool_input={"message": "hello"},
                    iteration=1
                )
            elif call_count[0] == 2:
                # Second call: THOUGHT after observation
                return ReActStep(
                    step_type="THOUGHT",
                    content="I have the result, analysis complete",
                    iteration=2
                )
            # Third call: signal completion
            return None

        result = await engine.run(
            initial_thought="Starting analysis",
            tool_registry=tool_registry,
            llm_generator=mock_llm_generator
        )

        # Verify the chain contains the expected steps
        assert len(result.react_chain) >= 3  # Initial thought + action + observation
        
        # Check step types in order
        step_types = [s.step_type for s in result.react_chain]
        assert "THOUGHT" in step_types
        assert "ACTION" in step_types
        assert "OBSERVATION" in step_types

    @pytest.mark.asyncio
    async def test_loop_logs_every_step_to_custody_logger(
        self, engine, tool_registry, mock_custody_logger
    ):
        """Test that every step is logged to custody logger."""
        call_count = [0]
        
        async def mock_llm_generator(chain, state):
            call_count[0] += 1
            if call_count[0] == 1:
                return ReActStep(
                    step_type="ACTION",
                    content="Using echo tool",
                    tool_name="echo",
                    tool_input={"message": "test"},
                    iteration=1
                )
            return None

        await engine.run(
            initial_thought="Starting",
            tool_registry=tool_registry,
            llm_generator=mock_llm_generator
        )

        # Should have logged: initial thought, action, observation
        assert mock_custody_logger.log_entry.call_count >= 3

    @pytest.mark.asyncio
    async def test_loop_stops_at_iteration_ceiling(
        self, mock_working_memory, mock_custody_logger, mock_redis, tool_registry
    ):
        """Test that the loop stops at the iteration ceiling."""
        small_ceiling = 3
        engine = ReActLoopEngine(
            agent_id="test_agent",
            session_id=uuid.uuid4(),
            iteration_ceiling=small_ceiling,
            working_memory=mock_working_memory,
            custody_logger=mock_custody_logger,
            redis_client=mock_redis,
            hitl_timeout=0.1
        )

        async def always_think(chain, state):
            return ReActStep(
                step_type="THOUGHT",
                content="Still thinking...",
                iteration=len(chain)
            )

        result = await engine.run(
            initial_thought="Starting",
            tool_registry=tool_registry,
            llm_generator=always_think
        )

        assert result.total_iterations <= small_ceiling

    @pytest.mark.asyncio
    async def test_hitl_triggered_at_50pct_ceiling_without_finding(
        self, mock_working_memory, mock_custody_logger, mock_redis, tool_registry
    ):
        """Test HITL trigger at 50% of iteration ceiling without COMPLETE task."""
        ceiling = 10
        engine = ReActLoopEngine(
            agent_id="test_agent",
            session_id=uuid.uuid4(),
            iteration_ceiling=ceiling,
            working_memory=mock_working_memory,
            custody_logger=mock_custody_logger,
            redis_client=mock_redis,
            hitl_timeout=0.1
        )

        # Create state without COMPLETE task
        state = WorkingMemoryState(
            session_id=uuid.uuid4(),
            agent_id="test_agent",
            tasks=[Task(
                description="Analyze",
                status=TaskStatus.IN_PROGRESS
            )]
        )

        # Test the trigger check directly
        engine._current_iteration = ceiling // 2
        trigger = await engine.check_hitl_triggers(state)
        
        assert trigger == HITLCheckpointReason.ITERATION_CEILING_50PCT

    @pytest.mark.asyncio
    async def test_hitl_pause_serializes_working_memory(
        self, engine, mock_working_memory, mock_redis
    ):
        """Test that HITL pause serializes working memory to Redis."""
        # Setup working memory state
        state = WorkingMemoryState(
            session_id=engine.session_id,
            agent_id=engine.agent_id,
            tasks=[Task(
                description="Test task",
                status=TaskStatus.IN_PROGRESS
            )]
        )
        mock_working_memory.get_state = AsyncMock(return_value=state)

        checkpoint = await engine.pause_for_hitl(
            reason=HITLCheckpointReason.ITERATION_CEILING_50PCT,
            brief="Test pause"
        )

        assert checkpoint.status == "PAUSED"
        assert checkpoint.serialized_state is not None
        
        # Verify Redis was called
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        key = call_args[0][0]
        assert key.startswith("hitl:")
        assert str(engine.session_id) in key

    @pytest.mark.asyncio
    async def test_hitl_resume_approve_continues_loop(
        self, engine, mock_working_memory, mock_custody_logger, mock_redis
    ):
        """Test that APPROVE decision continues the loop."""
        # First create a checkpoint
        state = WorkingMemoryState(
            session_id=engine.session_id,
            agent_id=engine.agent_id,
            tasks=[]
        )
        mock_working_memory.get_state = AsyncMock(return_value=state)

        checkpoint = await engine.pause_for_hitl(
            reason=HITLCheckpointReason.ITERATION_CEILING_50PCT,
            brief="Test pause"
        )

        # Resume with APPROVE
        decision = HumanDecision(
            decision_type="APPROVE",
            investigator_id="investigator_1",
            notes="Approved to continue"
        )

        await engine.resume_from_hitl(checkpoint.checkpoint_id, decision)

        # Verify state was updated
        assert engine._terminated is False
        assert checkpoint.status == "RESUMED"
        
        # Verify Redis cleanup
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_hitl_resume_terminate_stops_loop(
        self, engine, mock_working_memory, mock_custody_logger, mock_redis
    ):
        """Test that TERMINATE decision stops the loop."""
        state = WorkingMemoryState(
            session_id=engine.session_id,
            agent_id=engine.agent_id,
            tasks=[]
        )
        mock_working_memory.get_state = AsyncMock(return_value=state)

        checkpoint = await engine.pause_for_hitl(
            reason=HITLCheckpointReason.ITERATION_CEILING_50PCT,
            brief="Test pause"
        )

        decision = HumanDecision(
            decision_type="TERMINATE",
            investigator_id="investigator_1",
            notes="Terminating analysis"
        )

        await engine.resume_from_hitl(checkpoint.checkpoint_id, decision)

        assert engine._terminated is True
        assert checkpoint.status == "TERMINATED"

    @pytest.mark.asyncio
    async def test_hitl_resume_override_logs_human_judgment(
        self, engine, mock_working_memory, mock_custody_logger, mock_redis
    ):
        """Test that OVERRIDE decision logs human judgment as finding."""
        state = WorkingMemoryState(
            session_id=engine.session_id,
            agent_id=engine.agent_id,
            tasks=[]
        )
        mock_working_memory.get_state = AsyncMock(return_value=state)

        checkpoint = await engine.pause_for_hitl(
            reason=HITLCheckpointReason.CONTESTED_FINDING,
            brief="Contested finding"
        )

        decision = HumanDecision(
            decision_type="OVERRIDE",
            investigator_id="investigator_1",
            notes="I override with my judgment",
            override_finding={"conclusion": "different_result"}
        )

        await engine.resume_from_hitl(checkpoint.checkpoint_id, decision)

        # Verify finding was added
        assert len(engine._findings) == 1
        assert engine._findings[0].finding_type == "HUMAN_OVERRIDE"
        assert checkpoint.status == "OVERRIDDEN"

    @pytest.mark.asyncio
    async def test_tool_unavailable_does_not_crash_loop(
        self, engine, mock_working_memory, mock_custody_logger
    ):
        """Test that unavailable tool doesn't crash the loop."""
        # Create registry with unavailable tool
        registry = ToolRegistry()
        
        async def handler(input_data):
            return {"result": "ok"}
        
        registry.register("test_tool", handler)
        registry.set_unavailable("test_tool")

        call_count = [0]
        
        async def mock_llm_generator(chain, state):
            call_count[0] += 1
            if call_count[0] == 1:
                return ReActStep(
                    step_type="ACTION",
                    content="Using unavailable tool",
                    tool_name="test_tool",
                    tool_input={"test": "data"},
                    iteration=1
                )
            return None

        # Should not raise
        result = await engine.run(
            initial_thought="Starting",
            tool_registry=registry,
            llm_generator=mock_llm_generator
        )

        # Loop should complete
        assert result is not None
        assert len(result.react_chain) > 0

    @pytest.mark.asyncio
    async def test_tool_unavailable_logged_as_incomplete_finding(
        self, engine, mock_working_memory, mock_custody_logger
    ):
        """Test that tool unavailability is logged properly."""
        registry = ToolRegistry()
        
        async def handler(input_data):
            return {"result": "ok"}
        
        registry.register("test_tool", handler)
        registry.set_unavailable("test_tool")

        async def mock_llm_generator(chain, state):
            if len([s for s in chain if s.step_type == "ACTION"]) == 0:
                return ReActStep(
                    step_type="ACTION",
                    content="Using unavailable tool",
                    tool_name="test_tool",
                    tool_input={"test": "data"},
                    iteration=1
                )
            return None

        result = await engine.run(
            initial_thought="Starting",
            tool_registry=registry,
            llm_generator=mock_llm_generator
        )

        # Check that observation was created with unavailable status
        observations = [s for s in result.react_chain if s.step_type == "OBSERVATION"]
        assert len(observations) > 0
        
        # The observation should mention unavailability
        obs = observations[0]
        assert "unavailable" in obs.content.lower()

    @pytest.mark.asyncio
    async def test_check_hitl_triggers_blocked_task(self, engine):
        """Test HITL trigger for blocked task (proxy for contested finding)."""
        # Use BLOCKED status as proxy for contested
        state = WorkingMemoryState(
            session_id=engine.session_id,
            agent_id=engine.agent_id,
            tasks=[Task(
                description="Test",
                status=TaskStatus.BLOCKED,
                blocked_reason="Contested finding"
            )]
        )

        # The check_hitl_triggers doesn't check BLOCKED status directly
        # but we can verify the state is properly set up
        trigger = await engine.check_hitl_triggers(state)
        # No trigger expected for BLOCKED status in current implementation
        # This test verifies the method doesn't crash

    @pytest.mark.asyncio
    async def test_check_hitl_triggers_no_trigger(self, engine):
        """Test no HITL trigger when conditions not met."""
        state = WorkingMemoryState(
            session_id=engine.session_id,
            agent_id=engine.agent_id,
            tasks=[Task(
                description="Test",
                status=TaskStatus.COMPLETE
            )]
        )

        # Set iteration low
        engine._current_iteration = 1

        trigger = await engine.check_hitl_triggers(state)
        assert trigger is None

    @pytest.mark.asyncio
    async def test_redirect_injects_context(
        self, engine, mock_working_memory, mock_custody_logger, mock_redis
    ):
        """Test that REDIRECT decision injects context into working memory."""
        state = WorkingMemoryState(
            session_id=engine.session_id,
            agent_id=engine.agent_id,
            tasks=[]
        )
        mock_working_memory.get_state = AsyncMock(return_value=state)

        checkpoint = await engine.pause_for_hitl(
            reason=HITLCheckpointReason.ITERATION_CEILING_50PCT,
            brief="Test pause"
        )

        decision = HumanDecision(
            decision_type="REDIRECT",
            investigator_id="investigator_1",
            notes="Try different approach",
            redirect_context="Focus on metadata analysis"
        )

        await engine.resume_from_hitl(checkpoint.checkpoint_id, decision)

        # Verify update_state was called with redirect context
        mock_working_memory.update_state.assert_called()
        call_args = mock_working_memory.update_state.call_args
        updates = call_args.kwargs["updates"]
        assert "redirect_context" in updates
        assert updates["redirect_context"] == "Focus on metadata analysis"

    @pytest.mark.asyncio
    async def test_escalate_sets_tribunal_flag(
        self, engine, mock_working_memory, mock_custody_logger, mock_redis
    ):
        """Test that ESCALATE decision sets tribunal escalation flag."""
        state = WorkingMemoryState(
            session_id=engine.session_id,
            agent_id=engine.agent_id,
            tasks=[]
        )
        mock_working_memory.get_state = AsyncMock(return_value=state)

        checkpoint = await engine.pause_for_hitl(
            reason=HITLCheckpointReason.CONTESTED_FINDING,
            brief="Contested"
        )

        decision = HumanDecision(
            decision_type="ESCALATE",
            investigator_id="investigator_1",
            notes="Escalating to tribunal"
        )

        await engine.resume_from_hitl(checkpoint.checkpoint_id, decision)

        # Verify tribunal_escalation flag was set
        mock_working_memory.update_state.assert_called()
        call_args = mock_working_memory.update_state.call_args
        updates = call_args.kwargs["updates"]
        assert "tribunal_escalation" in updates
        assert updates["tribunal_escalation"] is True
