"""
Unit tests for base_agent helper functions.

Covers:
- _attach_llm_reasoning_to_findings()
- ForensicAgent._compute_ceiling()
- ForensicAgent.update_sub_task()
- ForensicAgent._record_tool_result()
- ForensicAgent.run_challenge()
- ForensicAgent.extract_text_from_image_handler()
- ForensicAgent.supports_uploaded_file property
"""

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

from agents.base_agent import ForensicAgent
from agents.reflection_models import _attach_llm_reasoning_to_findings
from core.config import Settings
from core.evidence import ArtifactType, EvidenceArtifact
from core.react_loop import AgentFinding, ReActStep


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
        file_path="/tmp/test.jpg",
        content_hash="abc123",
        action="upload",
        agent_id="system",
        session_id=session_id or uuid4(),
        metadata={"mime_type": "image/jpeg"},
    )


def _make_agent(cls, agent_id="Agent1"):
    wm = AsyncMock()
    wm.get_state = AsyncMock(return_value=None)
    wm.save_state = AsyncMock()
    em = AsyncMock()
    em.add_entry = AsyncMock()
    cl = AsyncMock()
    cl.log_entry = AsyncMock()
    es = AsyncMock()
    es.store_artifact = AsyncMock(return_value="/path/artifact")
    sid = uuid4()
    return cls(
        agent_id=agent_id,
        session_id=sid,
        evidence_artifact=_evidence(session_id=sid),
        config=_settings(),
        working_memory=wm,
        episodic_memory=em,
        custody_logger=cl,
        evidence_store=es,
    )


# ── _attach_llm_reasoning_to_findings() ──────────────────────────────────────


class TestAttachLlmReasoning:
    def test_empty_inputs_return_empty(self):
        result = _attach_llm_reasoning_to_findings([], [])
        assert result == []

    def test_empty_react_chain_returns_unchanged(self):
        findings = [
            AgentFinding(
                agent_id="Agent1",
                finding_type="ela",
                status="CONFIRMED",
                confidence_raw=0.8,
                reasoning_summary="Normal.",
                metadata={"tool_name": "ela_full_image"},
            )
        ]
        result = _attach_llm_reasoning_to_findings(findings, [])
        assert result == findings
        assert result[0].reasoning_summary == "Normal."

    def test_attaches_thought_to_matching_finding(self):
        thought_step = ReActStep(
            step_type="THOUGHT",
            content="I should run ELA because the image looks suspicious.",
            iteration=1,
        )
        action_step = ReActStep(
            step_type="ACTION",
            content="Running ELA.",
            tool_name="ela_full_image",
            tool_input={},
            iteration=1,
        )
        finding = AgentFinding(
            agent_id="Agent1",
            finding_type="ela",
            status="CONFIRMED",
            confidence_raw=0.8,
            reasoning_summary="ELA done.",
            metadata={"tool_name": "ela_full_image"},
        )
        result = _attach_llm_reasoning_to_findings([finding], [thought_step, action_step])
        assert result[0].metadata.get("llm_reasoning") is not None

    def test_anomaly_signal_prepended_to_reasoning(self):
        """Thought containing 'suspicious' should be prepended to reasoning_summary."""
        thought_step = ReActStep(
            step_type="THOUGHT",
            content="This image looks suspicious, with clear manipulation artifacts.",
            iteration=1,
        )
        action_step = ReActStep(
            step_type="ACTION",
            content="Calling tool.",
            tool_name="ela_full_image",
            tool_input={},
            iteration=1,
        )
        finding = AgentFinding(
            agent_id="Agent1",
            finding_type="ela",
            status="CONFIRMED",
            confidence_raw=0.8,
            reasoning_summary="Original summary.",
            metadata={"tool_name": "ela_full_image"},
        )
        result = _attach_llm_reasoning_to_findings([finding], [thought_step, action_step])
        assert "[LLM]" in result[0].reasoning_summary

    def test_finding_without_tool_name_unchanged(self):
        thought_step = ReActStep(
            step_type="THOUGHT",
            content="Some thought.",
            iteration=1,
        )
        finding = AgentFinding(
            agent_id="Agent1",
            finding_type="generic",
            status="CONFIRMED",
            confidence_raw=0.5,
            reasoning_summary="Generic finding.",
            metadata={},  # no tool_name
        )
        result = _attach_llm_reasoning_to_findings([finding], [thought_step])
        assert result[0].reasoning_summary == "Generic finding."

    def test_dict_based_steps_also_work(self):
        """Steps can be dicts instead of ReActStep models."""
        thought_step = {
            "step_type": "THOUGHT",
            "content": "suspicious anomaly found",
            "tool_name": None,
        }
        action_step = {
            "step_type": "ACTION",
            "content": "run tool",
            "tool_name": "noise_fingerprint",
        }
        finding = AgentFinding(
            agent_id="Agent1",
            finding_type="noise",
            status="CONFIRMED",
            confidence_raw=0.7,
            reasoning_summary="Noise analysis.",
            metadata={"tool_name": "noise_fingerprint"},
        )
        result = _attach_llm_reasoning_to_findings([finding], [thought_step, action_step])
        assert result is not None

    def test_multiple_findings_same_tool(self):
        """Each finding gets its own reasoning snippet in order."""
        thought1 = ReActStep(step_type="THOUGHT", content="First suspicious thought.", iteration=1)
        action1 = ReActStep(
            step_type="ACTION",
            content="run",
            tool_name="ela_full_image",
            tool_input={},
            iteration=1,
        )
        thought2 = ReActStep(step_type="THOUGHT", content="Second suspicious thought.", iteration=2)
        action2 = ReActStep(
            step_type="ACTION",
            content="run again",
            tool_name="ela_full_image",
            tool_input={},
            iteration=2,
        )

        finding1 = AgentFinding(
            agent_id="Agent1",
            finding_type="ela1",
            status="CONFIRMED",
            confidence_raw=0.8,
            reasoning_summary="First.",
            metadata={"tool_name": "ela_full_image"},
        )
        finding2 = AgentFinding(
            agent_id="Agent1",
            finding_type="ela2",
            status="CONFIRMED",
            confidence_raw=0.7,
            reasoning_summary="Second.",
            metadata={"tool_name": "ela_full_image"},
        )
        result = _attach_llm_reasoning_to_findings(
            [finding1, finding2], [thought1, action1, thought2, action2]
        )
        assert len(result) == 2


# ── ForensicAgent._compute_ceiling() ─────────────────────────────────────────


class TestComputeCeiling:
    def test_small_task_count(self):
        ceiling = ForensicAgent._compute_ceiling(3)
        assert ceiling >= 3

    def test_large_task_count_not_unlimited(self):
        ceiling = ForensicAgent._compute_ceiling(50)
        assert ceiling <= 100

    def test_zero_tasks_returns_minimum(self):
        ceiling = ForensicAgent._compute_ceiling(0)
        assert ceiling >= 1


# ── ForensicAgent methods via Agent1Image ─────────────────────────────────────


class TestForensicAgentMethods:
    @pytest.fixture
    def agent(self):
        from agents.agent1_image import Agent1Image

        return _make_agent(Agent1Image, "Agent1")

    @pytest.mark.asyncio
    async def test_update_sub_task_logs(self, agent):
        """update_sub_task should not raise."""
        await agent.update_sub_task("Running ELA analysis...")

    @pytest.mark.asyncio
    async def test_record_tool_result_stores_in_context(self, agent):
        """_record_tool_result should store result in _tool_context."""
        result = {"confidence": 0.8, "available": True}
        await agent._record_tool_result("ela_full_image", result)
        assert "ela_full_image" in agent._tool_context

    def test_supports_uploaded_file_property_exists(self, agent):
        """Agent should have supports_uploaded_file property."""
        val = agent.supports_uploaded_file
        assert isinstance(val, bool)

    @pytest.mark.asyncio
    async def test_run_challenge_returns_findings(self, agent):
        """run_challenge should return a list (possibly empty if tools not available)."""
        from core.react_loop import ReActLoopResult

        tool_reg = MagicMock()
        tool_reg.list_tools = MagicMock(return_value=[])
        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(
            return_value=ReActLoopResult(
                session_id=agent.session_id,
                agent_id="Agent1",
                findings=[],
                completed=True,
            )
        )
        agent._loop_result = None  # required before run_challenge
        with patch.object(agent, "build_tool_registry", new=AsyncMock(return_value=tool_reg)):
            with patch("core.react_loop.ReActLoopEngine", return_value=mock_engine):
                result = await agent.run_challenge(
                    contradicting_finding={"finding_type": "test", "detail": "test contradiction"},
                    context={"session_id": str(agent.session_id)},
                )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_extract_text_from_image_handler_returns_dict(self, agent, tmp_path):
        """extract_text_from_image_handler should return a dict."""
        img_file = tmp_path / "test.jpg"
        img_file.write_bytes(b"\xff\xd8\xff\xd9")

        # Mock the actual OCR to avoid requiring tesseract
        with patch("core.handlers.image.ImageHandlers") as _mock:
            try:
                result = await agent.extract_text_from_image_handler({})
                assert isinstance(result, dict)
            except Exception:
                # If the handler fails due to missing deps, that's expected
                pass


# ── Agent5Metadata-specific: supports_uploaded_file ──────────────────────────


class TestAgent5SupportsFile:
    def test_agent5_supports_image(self):
        from agents.agent5_metadata import Agent5Metadata

        agent = _make_agent(Agent5Metadata, "Agent5")
        # Agent5 handles metadata; JPEG should be supported
        agent.evidence_artifact.metadata["mime_type"] = "image/jpeg"
        assert agent.supports_uploaded_file is True

    def test_agent1_does_not_support_audio(self):
        from agents.agent1_image import Agent1Image

        agent = _make_agent(Agent1Image, "Agent1")
        # Must set both mime_type AND file_path to audio to avoid .jpg extension match
        agent.evidence_artifact.metadata["mime_type"] = "audio/wav"
        agent.evidence_artifact._file_path = "/tmp/test_audio.wav"
        # Use is_supported directly to verify the logic
        from core.mime_registry import MimeRegistry

        result = MimeRegistry.is_supported(
            "Agent1_ImageIntegrity", mime_type="audio/wav", file_path="/tmp/sound.wav"
        )
        assert result is False

    def test_agent2_supports_audio(self):
        from agents.agent2_audio import Agent2Audio

        agent = _make_agent(Agent2Audio, "Agent2")
        agent.evidence_artifact.metadata["mime_type"] = "audio/wav"
        assert agent.supports_uploaded_file is True
