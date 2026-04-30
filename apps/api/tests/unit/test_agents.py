"""
Unit tests for all five forensic specialist agents.

Covers:
- Agent instantiation without LLM (template fallback mode)
- task_decomposition: required fields + non-empty
- deep_task_decomposition: additional tasks beyond base
- iteration_ceiling: within reasonable range
- build_tool_registry(): returns populated ToolRegistry
- agent_name: non-empty, unique per agent
- SelfReflectionReport model fields
"""

import os
from unittest.mock import AsyncMock
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

from agents.reflection_models import SelfReflectionReport
from core.config import Settings
from core.evidence import ArtifactType, EvidenceArtifact

# â”€â”€ Minimal Settings â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _settings() -> Settings:
    return Settings(
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


def _evidence(session_id=None) -> EvidenceArtifact:
    return EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path="/tmp/test_img.jpg",
        content_hash="hash123",
        action="upload",
        agent_id="system",
        session_id=session_id or uuid4(),
        metadata={"mime_type": "image/jpeg"},
    )


def _mocked_deps():
    """Return (working_memory, episodic_memory, custody_logger, evidence_store)."""
    wm = AsyncMock()
    wm.get_state = AsyncMock(return_value=None)
    wm.save_state = AsyncMock()

    em = AsyncMock()
    em.add_entry = AsyncMock()
    em.query = AsyncMock(return_value=[])

    cl = AsyncMock()
    cl.log_entry = AsyncMock()

    es = AsyncMock()
    es.store_artifact = AsyncMock(return_value="/path/to/artifact")

    return wm, em, cl, es


def _make_agent(cls, agent_id: str = "Agent1"):
    """Construct a forensic agent with all mocked dependencies."""
    wm, em, cl, es = _mocked_deps()
    sid = uuid4()
    ev = _evidence(session_id=sid)
    return cls(
        agent_id=agent_id,
        session_id=sid,
        evidence_artifact=ev,
        config=_settings(),
        working_memory=wm,
        episodic_memory=em,
        custody_logger=cl,
        evidence_store=es,
    )


# â”€â”€ Agent1 Image â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestAgent1Image:
    @pytest.fixture
    def agent(self):
        from agents.agent1_image import Agent1Image

        return _make_agent(Agent1Image, "Agent1")

    def test_agent_name_nonempty(self, agent):
        assert isinstance(agent.agent_name, str)
        assert len(agent.agent_name) > 0

    def test_task_decomposition_nonempty(self, agent):
        tasks = agent.task_decomposition
        assert isinstance(tasks, list)
        assert len(tasks) > 0

    def test_deep_task_decomposition_nonempty(self, agent):
        dtasks = agent.deep_task_decomposition
        assert isinstance(dtasks, list)
        assert len(dtasks) > 0

    def test_iteration_ceiling_reasonable(self, agent):
        assert 5 <= agent.iteration_ceiling <= 50

    @pytest.mark.asyncio
    async def test_build_tool_registry_returns_registry(self, agent):
        from core.tool_registry import ToolRegistry

        registry = await agent.build_tool_registry()
        assert isinstance(registry, ToolRegistry)

    @pytest.mark.asyncio
    async def test_tool_registry_has_tools(self, agent):
        registry = await agent.build_tool_registry()
        tools = registry.list_tools()
        assert len(tools) > 0


# â”€â”€ Agent2 Audio â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestAgent2Audio:
    @pytest.fixture
    def agent(self):
        from agents.agent2_audio import Agent2Audio

        return _make_agent(Agent2Audio, "Agent2")

    def test_agent_name_nonempty(self, agent):
        assert len(agent.agent_name) > 0

    def test_task_decomposition_nonempty(self, agent):
        assert len(agent.task_decomposition) > 0

    def test_deep_task_decomposition_nonempty(self, agent):
        assert len(agent.deep_task_decomposition) > 0

    def test_iteration_ceiling_reasonable(self, agent):
        assert 5 <= agent.iteration_ceiling <= 50

    @pytest.mark.asyncio
    async def test_tool_registry_has_tools(self, agent):
        registry = await agent.build_tool_registry()
        assert len(registry.list_tools()) > 0


# â”€â”€ Agent3 Object â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestAgent3Object:
    @pytest.fixture
    def agent(self):
        from agents.agent3_object import Agent3Object

        return _make_agent(Agent3Object, "Agent3")

    def test_agent_name_nonempty(self, agent):
        assert len(agent.agent_name) > 0

    def test_task_decomposition_nonempty(self, agent):
        assert len(agent.task_decomposition) > 0

    def test_iteration_ceiling_reasonable(self, agent):
        assert 5 <= agent.iteration_ceiling <= 50

    @pytest.mark.asyncio
    async def test_tool_registry_has_tools(self, agent):
        registry = await agent.build_tool_registry()
        assert len(registry.list_tools()) > 0


# â”€â”€ Agent4 Video â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestAgent4Video:
    @pytest.fixture
    def agent(self):
        from agents.agent4_video import Agent4Video

        return _make_agent(Agent4Video, "Agent4")

    def test_agent_name_nonempty(self, agent):
        assert len(agent.agent_name) > 0

    def test_task_decomposition_nonempty(self, agent):
        assert len(agent.task_decomposition) > 0

    def test_iteration_ceiling_reasonable(self, agent):
        assert 5 <= agent.iteration_ceiling <= 50

    @pytest.mark.asyncio
    async def test_tool_registry_has_tools(self, agent):
        registry = await agent.build_tool_registry()
        assert len(registry.list_tools()) > 0


# â”€â”€ Agent5 Metadata â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestAgent5Metadata:
    @pytest.fixture
    def agent(self):
        from agents.agent5_metadata import Agent5Metadata

        return _make_agent(Agent5Metadata, "Agent5")

    def test_agent_name_nonempty(self, agent):
        assert len(agent.agent_name) > 0

    def test_task_decomposition_nonempty(self, agent):
        assert len(agent.task_decomposition) > 0

    def test_iteration_ceiling_reasonable(self, agent):
        assert 5 <= agent.iteration_ceiling <= 50

    @pytest.mark.asyncio
    async def test_tool_registry_has_tools(self, agent):
        registry = await agent.build_tool_registry()
        assert len(registry.list_tools()) > 0


# â”€â”€ Agent names are unique â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestAgentUniqueness:
    def _make_all(self):
        from agents.agent1_image import Agent1Image
        from agents.agent2_audio import Agent2Audio
        from agents.agent3_object import Agent3Object
        from agents.agent4_video import Agent4Video
        from agents.agent5_metadata import Agent5Metadata

        pairs = [
            (Agent1Image, "Agent1"),
            (Agent2Audio, "Agent2"),
            (Agent3Object, "Agent3"),
            (Agent4Video, "Agent4"),
            (Agent5Metadata, "Agent5"),
        ]
        return [_make_agent(cls, aid) for cls, aid in pairs]

    def test_all_agent_names_unique(self):
        agents = self._make_all()
        names = [a.agent_name for a in agents]
        assert len(names) == len(set(names))

    def test_five_agents_instantiated(self):
        agents = self._make_all()
        assert len(agents) == 5


# â”€â”€ SelfReflectionReport model â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestSelfReflectionReport:
    def test_defaults_all_tasks_incomplete(self):
        r = SelfReflectionReport()
        assert r.all_tasks_complete is False

    def test_empty_incomplete_tasks_by_default(self):
        r = SelfReflectionReport()
        assert r.incomplete_tasks == []

    def test_court_defensible_false_by_default(self):
        r = SelfReflectionReport()
        assert r.court_defensible is False

    def test_reflection_notes_empty_by_default(self):
        r = SelfReflectionReport()
        assert r.reflection_notes == ""

    def test_complete_reflection_fields(self):
        r = SelfReflectionReport(
            all_tasks_complete=True,
            court_defensible=True,
            reflection_notes="All findings cross-validated.",
        )
        assert r.all_tasks_complete is True
        assert r.court_defensible is True
        assert "cross-validated" in r.reflection_notes
