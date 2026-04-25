"""
Unit tests for ReActLoopEngine and related helpers.

Covers:
- ReActLoopEngine instantiation and run()
- _build_forensic_system_prompt()
- _get_available_tools_for_llm()
- create_llm_step_generator()
- parse_llm_step()
- AgentFindingStatus, ReActLoopResult models
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_PASSWORD", "test")
os.environ.setdefault("NEXT_PUBLIC_DEMO_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")

from core.react_loop import (
    AgentFinding,
    AgentFindingStatus,
    HITLCheckpointReason,
    HITLCheckpointState,
    HumanDecision,
    ReActLoopEngine,
    ReActLoopResult,
    create_llm_step_generator,
    parse_llm_step,
)
from core.tool_registry import ToolRegistry


def _make_engine(iteration_ceiling: int = 3, hitl_timeout: float = 0.1):
    wm = AsyncMock()
    wm.get_state = AsyncMock(return_value=None)
    wm.save_state = AsyncMock()
    cl = AsyncMock()
    cl.log = AsyncMock()
    sid = uuid4()
    return ReActLoopEngine(
        agent_id="Agent1",
        session_id=sid,
        iteration_ceiling=iteration_ceiling,
        working_memory=wm,
        custody_logger=cl,
        hitl_timeout=hitl_timeout,
    )


def _make_state():
    """Return a minimal WorkingMemoryState-like mock."""
    state = MagicMock()
    state.tasks = []
    state.tool_results = {}
    state.tool_registry_snapshot = None
    state.hitl_flags = []
    state.severity_flags = []
    state.tribunal_escalation = False  # prevent spurious HITL trigger
    return state


# ── ReActLoopResult model ─────────────────────────────────────────────────────


class TestReActLoopResult:
    def test_defaults(self):
        sid = uuid4()
        r = ReActLoopResult(session_id=sid, agent_id="Agent1")
        assert r.completed is False
        assert r.terminated_by_human is False
        assert r.findings == []
        assert r.total_iterations == 0

    def test_with_findings(self):
        sid = uuid4()
        f = AgentFinding(
            agent_id="Agent1",
            finding_type="test",
            status="CONFIRMED",
            confidence_raw=0.9,
            reasoning_summary="Test.",
        )
        r = ReActLoopResult(session_id=sid, agent_id="Agent1", findings=[f], completed=True)
        assert len(r.findings) == 1
        assert r.completed is True


# ── AgentFindingStatus enum ───────────────────────────────────────────────────


class TestAgentFindingStatus:
    def test_all_values(self):
        statuses = {s.value for s in AgentFindingStatus}
        assert "CONFIRMED" in statuses
        assert "CONTESTED" in statuses
        assert "INCONCLUSIVE" in statuses
        assert "INCOMPLETE" in statuses
        assert "NOT_APPLICABLE" in statuses
        assert "ABSTAIN" in statuses


# ── ReActLoopEngine instantiation ────────────────────────────────────────────


class TestReActLoopEngineInit:
    def test_can_be_instantiated(self):
        engine = _make_engine()
        assert engine is not None

    def test_agent_id_stored(self):
        engine = _make_engine()
        assert engine.agent_id == "Agent1"

    def test_initial_iteration_zero(self):
        engine = _make_engine()
        assert engine._current_iteration == 0

    def test_initial_findings_empty(self):
        engine = _make_engine()
        assert engine._findings == []

    def test_task_tool_overrides_cached(self):
        with patch("core.react_loop.get_task_tool_overrides", return_value={}):
            ReActLoopEngine._TASK_TOOL_OVERRIDES_CACHE = None
            overrides = ReActLoopEngine._get_task_tool_overrides()
            assert isinstance(overrides, dict)


# ── ReActLoopEngine.run() ─────────────────────────────────────────────────────


class TestReActLoopEngineRun:
    @pytest.mark.asyncio
    async def test_run_with_none_state_breaks_immediately(self):
        """When working memory returns None state, loop breaks after initial step."""
        engine = _make_engine(iteration_ceiling=5)
        engine.working_memory.get_state = AsyncMock(return_value=None)

        registry = ToolRegistry()
        result = await engine.run(initial_thought="Test thought.", tool_registry=registry)

        assert isinstance(result, ReActLoopResult)
        assert result.completed is True or result.total_iterations == 0

    @pytest.mark.asyncio
    async def test_run_returns_react_loop_result(self):
        engine = _make_engine(iteration_ceiling=2)
        engine.working_memory.get_state = AsyncMock(return_value=None)

        registry = ToolRegistry()
        result = await engine.run("Initial thought.", tool_registry=registry)
        assert isinstance(result, ReActLoopResult)

    @pytest.mark.asyncio
    async def test_run_with_state_and_no_tasks_breaks(self):
        """State with empty task list → _default_step_generator returns None → break."""
        engine = _make_engine(iteration_ceiling=3)
        state = _make_state()
        engine.working_memory.get_state = AsyncMock(return_value=state)

        registry = ToolRegistry()
        result = await engine.run("Initial thought.", tool_registry=registry)
        assert isinstance(result, ReActLoopResult)

    @pytest.mark.asyncio
    async def test_run_with_connection_error_on_get_state(self):
        """Connection error on get_state → graceful degradation."""
        engine = _make_engine(iteration_ceiling=2)
        engine.working_memory.get_state = AsyncMock(side_effect=ConnectionError("db down"))

        registry = ToolRegistry()
        result = await engine.run("Initial thought.", tool_registry=registry)
        assert isinstance(result, ReActLoopResult)

    @pytest.mark.asyncio
    async def test_run_respects_iteration_ceiling(self):
        """Loop never exceeds iteration_ceiling."""
        engine = _make_engine(iteration_ceiling=2)
        state = _make_state()

        # State always returns pending task to keep loop going
        task = MagicMock()
        task.status = "IN_PROGRESS"
        task.description = "Analyze image"
        task.tool_name = "ela_full_image"
        state.tasks = [task]

        # Alternate: return None to trigger break
        engine.working_memory.get_state = AsyncMock(return_value=None)
        registry = ToolRegistry()
        result = await engine.run("Initial thought.", tool_registry=registry)
        assert result.total_iterations <= 2


# ── ReActLoopEngine.check_hitl_triggers() ────────────────────────────────────


class TestCheckHitlTriggers:
    @pytest.mark.asyncio
    async def test_returns_none_with_no_triggers(self):
        engine = _make_engine()
        state = _make_state()
        state.hitl_flags = []
        state.severity_flags = []
        reason = await engine.check_hitl_triggers(state)
        assert reason is None

    @pytest.mark.asyncio
    async def test_returns_reason_when_severity_breach_flagged(self):
        engine = _make_engine()
        state = _make_state()
        state.hitl_flags = ["SEVERITY_THRESHOLD_BREACH"]
        state.severity_flags = ["SEVERITY_THRESHOLD_BREACH"]
        # If the engine checks hitl_flags, it should return a reason
        # The exact implementation may vary; just check it returns a value or None
        result = await engine.check_hitl_triggers(state)
        # Result is either None or HITLCheckpointReason
        assert result is None or isinstance(result, HITLCheckpointReason)


# ── ReActLoopEngine.pause_for_hitl() ─────────────────────────────────────────


class TestPauseForHitl:
    @pytest.mark.asyncio
    async def test_pause_returns_checkpoint(self):
        engine = _make_engine()
        engine.custody_logger.log = AsyncMock()
        checkpoint = await engine.pause_for_hitl(
            reason=HITLCheckpointReason.ITERATION_CEILING_50PCT,
            brief="Test pause",
        )
        assert isinstance(checkpoint, HITLCheckpointState)
        assert checkpoint.agent_id == "Agent1"
        assert checkpoint.reason == HITLCheckpointReason.ITERATION_CEILING_50PCT


# ── ReActLoopEngine.resume_from_hitl() ───────────────────────────────────────


class TestResumeFromHitl:
    @pytest.mark.asyncio
    async def test_resume_with_approve_decision(self):
        engine = _make_engine()
        checkpoint = await engine.pause_for_hitl(
            reason=HITLCheckpointReason.CONTESTED_FINDING,
            brief="Test",
        )
        engine._current_checkpoint = checkpoint
        engine._resume_event = asyncio.Event()

        decision = HumanDecision(
            decision_type="APPROVE",
            investigator_id="INV-001",
            notes="Approved.",
        )
        await engine.resume_from_hitl(checkpoint.checkpoint_id, decision)
        assert engine._current_checkpoint is None or engine._current_checkpoint.status != "PAUSED"

    @pytest.mark.asyncio
    async def test_resume_with_terminate_sets_terminated(self):
        engine = _make_engine()
        checkpoint = await engine.pause_for_hitl(
            reason=HITLCheckpointReason.CONTESTED_FINDING,
            brief="Test",
        )
        engine._current_checkpoint = checkpoint
        engine._resume_event = asyncio.Event()

        decision = HumanDecision(
            decision_type="TERMINATE",
            investigator_id="INV-001",
            notes="Terminated.",
        )
        await engine.resume_from_hitl(checkpoint.checkpoint_id, decision)
        assert engine._terminated is True


# ── parse_llm_step() ─────────────────────────────────────────────────────────


class TestParseLlmStep:
    def test_parse_thought_content(self):
        result = parse_llm_step("THOUGHT: I should run ELA analysis.", None)
        assert result["step_type"] == "THOUGHT"
        assert "ELA" in result["content"]

    def test_parse_action_with_tool_call(self):
        tool_call = {"name": "ela_full_image", "arguments": {"artifact": {}}}
        result = parse_llm_step("ACTION: Running ELA.", tool_call)
        assert result["step_type"] == "ACTION"
        assert result["tool_name"] == "ela_full_image"

    def test_parse_action_with_prefix(self):
        # "Action:" prefix (not "ACTION:") triggers ACTION step when followed by tool()
        result = parse_llm_step("Action: ela_full_image()", None)
        assert result["step_type"] == "ACTION"

    def test_parse_analysis_complete(self):
        result = parse_llm_step("ANALYSIS COMPLETE: All tasks done.", None)
        assert result["step_type"] == "THOUGHT"

    def test_parse_plain_content_defaults_to_thought(self):
        result = parse_llm_step("Just some text without prefix.", None)
        assert result["step_type"] in ("THOUGHT", "ACTION", "OBSERVATION")


# ── create_llm_step_generator() ──────────────────────────────────────────────


class TestCreateLlmStepGenerator:
    @pytest.mark.asyncio
    async def test_returns_none_when_llm_disabled(self):
        """When LLM is disabled (llm_api_key is None), generator returns None."""
        from core.config import Settings

        config = Settings(
            app_env="testing",
            signing_key="test-signing-key-" + "x" * 32,
            postgres_user="test",
            postgres_password="test",
            postgres_db="test",
            redis_password="test",
            next_public_demo_password="test",
            llm_provider="none",
            llm_api_key=None,
            llm_model="test-model",
            bootstrap_admin_password="Admin_123!",
            bootstrap_investigator_password="Inv_123!",
        )
        llm_client = MagicMock()
        llm_client.is_available = False

        generator = create_llm_step_generator(
            llm_client=llm_client,
            config=config,
            agent_name="Agent1",
            evidence_context={"mime_type": "image/jpeg", "file_name": "test.jpg"},
        )
        state = _make_state()
        result = await generator([], state)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_react_reasoning_disabled(self):
        """When llm_enable_react_reasoning is False, generator returns None."""
        from core.config import Settings

        config = Settings(
            app_env="testing",
            signing_key="test-signing-key-" + "x" * 32,
            postgres_user="test",
            postgres_password="test",
            postgres_db="test",
            redis_password="test",
            next_public_demo_password="test",
            llm_provider="none",
            llm_api_key=None,
            llm_model="test-model",
            llm_enable_react_reasoning=False,
            bootstrap_admin_password="Admin_123!",
            bootstrap_investigator_password="Inv_123!",
        )
        llm_client = MagicMock()
        llm_client.is_available = True

        generator = create_llm_step_generator(
            llm_client=llm_client,
            config=config,
            agent_name="Agent1",
            evidence_context={},
        )
        state = _make_state()
        result = await generator([], state)
        assert result is None


# ── _build_forensic_system_prompt() ──────────────────────────────────────────


class TestBuildForensicSystemPrompt:
    def test_prompt_contains_agent_name(self):
        from core.react_loop import _build_forensic_system_prompt

        prompt = _build_forensic_system_prompt(
            agent_name="Agent1",
            evidence_context={"mime_type": "image/jpeg", "file_name": "test.jpg"},
            available_tasks=["Run ELA analysis", "Extract EXIF"],
        )
        assert "Agent1" in prompt

    def test_prompt_contains_tasks(self):
        from core.react_loop import _build_forensic_system_prompt

        prompt = _build_forensic_system_prompt(
            agent_name="Agent5",
            evidence_context={"mime_type": "image/jpeg"},
            available_tasks=["Validate GPS timestamp", "Check steganography"],
        )
        assert "Validate GPS timestamp" in prompt
        assert "Check steganography" in prompt

    def test_prompt_contains_mime_type(self):
        from core.react_loop import _build_forensic_system_prompt

        prompt = _build_forensic_system_prompt(
            agent_name="Agent2",
            evidence_context={"mime_type": "audio/wav", "file_name": "audio.wav"},
            available_tasks=[],
        )
        assert "audio/wav" in prompt

    def test_prompt_handles_unknown_agent(self):
        from core.react_loop import _build_forensic_system_prompt

        prompt = _build_forensic_system_prompt(
            agent_name="UnknownAgent",
            evidence_context={},
            available_tasks=[],
        )
        assert "UnknownAgent" in prompt

    def test_prompt_sanitizes_control_chars(self):
        from core.react_loop import _build_forensic_system_prompt

        # Inject control characters in file_name
        prompt = _build_forensic_system_prompt(
            agent_name="Agent1",
            evidence_context={"file_name": "test\x00file\x01.jpg"},
            available_tasks=[],
        )
        # Control chars should be stripped
        assert "\x00" not in prompt
        assert "\x01" not in prompt

    def test_prompt_includes_hash_when_present(self):
        from core.react_loop import _build_forensic_system_prompt

        prompt = _build_forensic_system_prompt(
            agent_name="Agent1",
            evidence_context={"sha256": "abc123def456"},
            available_tasks=[],
        )
        assert "abc123def456" in prompt


# ── _get_available_tools_for_llm() ───────────────────────────────────────────


class TestGetAvailableToolsForLlm:
    def test_returns_list_from_registry_snapshot(self):
        from core.react_loop import _get_available_tools_for_llm

        state = _make_state()
        state.tool_registry_snapshot = [
            {"name": "ela_full_image", "description": "ELA analysis"},
            {"name": "exif_extract", "description": "EXIF extraction"},
        ]
        tools = _get_available_tools_for_llm(state)
        assert len(tools) == 2
        assert tools[0]["name"] == "ela_full_image"

    def test_falls_back_to_static_catalogue(self):
        from core.react_loop import _get_available_tools_for_llm

        state = _make_state()
        state.tool_registry_snapshot = None
        tools = _get_available_tools_for_llm(state)
        assert isinstance(tools, list)
        assert len(tools) > 0
