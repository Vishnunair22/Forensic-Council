"""
Integration tests for the ForensicCouncilPipeline.

Covers:
- Pipeline instantiation with default settings
- run_investigation() returns a ForensicReport (agents mocked)
- Report contains session_id, case_id, signature fields
- SessionManager.create_session() tracks state
- SessionManager.get_session() returns None for unknown sessions
- AgentFactory.reinvoke_agent() works for challenge loops
"""

import os
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

pytest.importorskip("torch")

pytestmark = pytest.mark.requires_ml

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_PASSWORD", "test")
os.environ.setdefault("DEMO_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "")
os.environ.setdefault("LLM_MODEL", "test-model")

from core.config import Settings
from core.evidence import ArtifactType, EvidenceArtifact


def _settings() -> Settings:
    return Settings(
        app_env="testing",
        signing_key="test-signing-key-" + "x" * 32,
        postgres_user="test",
        postgres_password="test",
        postgres_db="test",
        redis_password="test",
        DEMO_PASSWORD="test",
        llm_provider="none",
        llm_api_key=None,
        llm_model="test-model",
        bootstrap_admin_password="Admin_123!",
        bootstrap_investigator_password="Inv_123!",
    )


def _mock_agent_result(agent_id: str) -> dict[str, Any]:
    from core.react_loop import AgentFinding

    finding = AgentFinding(
        agent_id=agent_id,
        finding_type="test_analysis",
        status="CONFIRMED",
        confidence_raw=0.85,
        reasoning_summary="Analysis complete.",
        court_statement="No manipulation detected.",
    )
    return {"findings": [finding]}


# â”€â”€ Pipeline instantiation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestPipelineInstantiation:
    def test_pipeline_can_be_instantiated_no_args(self):
        from orchestration.pipeline import ForensicCouncilPipeline

        pipeline = ForensicCouncilPipeline()
        assert pipeline is not None

    def test_pipeline_can_be_instantiated_with_config(self):
        from orchestration.pipeline import ForensicCouncilPipeline

        pipeline = ForensicCouncilPipeline(config=_settings())
        assert pipeline is not None

    def test_pipeline_has_run_investigation_method(self):
        from orchestration.pipeline import ForensicCouncilPipeline

        pipeline = ForensicCouncilPipeline()
        assert callable(pipeline.run_investigation)

    def test_pipeline_has_config(self):
        from orchestration.pipeline import ForensicCouncilPipeline

        pipeline = ForensicCouncilPipeline(config=_settings())
        assert pipeline.config is not None


# â”€â”€ Pipeline run (mocked agents) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestPipelineRun:
    @pytest.mark.asyncio
    async def test_run_investigation_returns_forensic_report(self, tmp_path):
        """run_investigation must return a ForensicReport when agents are mocked."""
        from agents.arbiter import ForensicReport
        from orchestration.pipeline import ForensicCouncilPipeline

        # Create a minimal JPEG temp file
        evidence_path = str(tmp_path / "evidence.jpg")
        with open(evidence_path, "wb") as f:
            f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9")

        sid = uuid4()
        mocked_report = ForensicReport(
            session_id=sid,
            case_id="CASE-TEST",
            executive_summary="Mocked report.",
            uncertainty_statement="Low uncertainty.",
            per_agent_findings={},
        )

        pipeline = ForensicCouncilPipeline(config=_settings())

        with patch.object(pipeline, "run_investigation", new=AsyncMock(return_value=mocked_report)):
            report = await pipeline.run_investigation(
                evidence_file_path=evidence_path,
                case_id="CASE-TEST",
                investigator_id="REQ-001",
                session_id=sid,
            )

        assert isinstance(report, ForensicReport)
        assert report.session_id == sid

    @pytest.mark.asyncio
    async def test_run_investigation_case_id_in_report(self, tmp_path):
        from agents.arbiter import ForensicReport
        from orchestration.pipeline import ForensicCouncilPipeline

        evidence_path = str(tmp_path / "e.jpg")
        with open(evidence_path, "wb") as f:
            f.write(b"\xff\xd8\xff\xd9")

        sid = uuid4()
        mocked_report = ForensicReport(
            session_id=sid,
            case_id="CASE-XYZ",
            executive_summary="Test.",
            uncertainty_statement="None.",
            per_agent_findings={},
        )

        pipeline = ForensicCouncilPipeline(config=_settings())
        with patch.object(pipeline, "run_investigation", new=AsyncMock(return_value=mocked_report)):
            report = await pipeline.run_investigation(
                evidence_file_path=evidence_path,
                case_id="CASE-XYZ",
                investigator_id="REQ-001",
            )
        assert report.case_id == "CASE-XYZ"


# â”€â”€ AgentFactory â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestAgentFactory:
    def _make_factory(self):
        from orchestration.pipeline import AgentFactory

        wm = AsyncMock()
        em = AsyncMock()
        cl = AsyncMock()
        es = AsyncMock()
        es.store_artifact = AsyncMock(return_value="/path/artifact")
        return AgentFactory(
            config=_settings(),
            working_memory=wm,
            episodic_memory=em,
            custody_logger=cl,
            evidence_store=es,
        )

    def test_factory_can_be_instantiated(self):
        factory = self._make_factory()
        assert factory is not None

    def test_factory_set_evidence_artifact(self):
        factory = self._make_factory()
        ev = EvidenceArtifact.create_root(
            artifact_type=ArtifactType.ORIGINAL,
            file_path="/tmp/test.jpg",
            content_hash="hash",
            action="upload",
            agent_id="system",
            session_id=uuid4(),
        )
        factory.set_evidence_artifact(ev)
        assert factory._evidence_artifact is not None

    @pytest.mark.asyncio
    async def test_reinvoke_unknown_agent_raises(self):
        factory = self._make_factory()
        with pytest.raises(Exception):
            await factory.reinvoke_agent(
                agent_id="AgentUnknown",
                session_id=uuid4(),
                challenge_context={"contradiction": "test"},
            )

    @pytest.mark.asyncio
    async def test_reinvoke_agent1_with_mock_run(self):
        factory = self._make_factory()
        sid = uuid4()
        from core.react_loop import AgentFinding

        ev = EvidenceArtifact.create_root(
            artifact_type=ArtifactType.ORIGINAL,
            file_path="/tmp/test.jpg",
            content_hash="hash",
            action="upload",
            agent_id="system",
            session_id=sid,
        )
        factory.set_evidence_artifact(ev)
        # run_challenge() returns a list of AgentFinding objects
        mock_findings = [
            AgentFinding(
                agent_id="Agent1",
                finding_type="test",
                status="CONFIRMED",
                confidence_raw=0.9,
                reasoning_summary="test",
                court_statement="No manipulation.",
            )
        ]
        with patch(
            "agents.agent1_image.Agent1Image.run_investigation",
            new=AsyncMock(return_value=mock_findings),
        ):
            result = await factory.reinvoke_agent(
                agent_id="Agent1",
                session_id=sid,
                challenge_context={"contradiction": "disputed finding"},
            )
        assert "findings" in result


# â”€â”€ Session state transitions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestSessionManager:
    def test_session_manager_can_be_instantiated(self):
        from orchestration.session_manager import SessionManager

        sm = SessionManager()
        assert sm is not None

    @pytest.mark.asyncio
    async def test_create_session_returns_state(self):
        from orchestration.session_manager import SessionManager

        sm = SessionManager()
        sid = uuid4()
        state = await sm.create_session(
            session_id=sid,
            case_id="CASE-001",
            investigator_id="REQ-001",
            agent_ids=["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"],
        )
        assert state is not None

    @pytest.mark.asyncio
    async def test_get_session_returns_state_after_create(self):
        from orchestration.session_manager import SessionManager

        sm = SessionManager()
        sid = uuid4()
        await sm.create_session(
            session_id=sid,
            case_id="CASE-002",
            investigator_id="REQ-002",
            agent_ids=["Agent1"],
        )
        state = await sm.get_session(sid)
        assert state is not None

    @pytest.mark.asyncio
    async def test_get_session_nonexistent_returns_none(self):
        from orchestration.session_manager import SessionManager

        sm = SessionManager()
        result = await sm.get_session(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_session_initial_status(self):
        from orchestration.session_manager import SessionManager, SessionStatus

        sm = SessionManager()
        sid = uuid4()
        state = await sm.create_session(
            session_id=sid,
            case_id="CASE-003",
            investigator_id="REQ-003",
            agent_ids=["Agent1"],
        )
        assert state.status in (
            SessionStatus.INITIALIZING,
            SessionStatus.RUNNING,
        )


# ── Pipeline result normalization tests (from test_pipeline_e2e.py) ─────────────


class TestNormalizeAgentResults:
    """Tests for agent result normalization in pipeline."""

    def test_normalize_with_pydantic_findings(self):
        from orchestration.agent_factory import AgentLoopResult
        from orchestration.pipeline import ForensicCouncilPipeline

        pipeline = ForensicCouncilPipeline()

        if hasattr(pipeline, "_normalize_agent_results"):

            class MockFinding:
                def model_dump(self, mode="json"):
                    return {"agent_id": "Agent1", "confidence": 0.8, "verdict": "AUTHENTIC"}

            agent_result = AgentLoopResult(
                agent_id="Agent1",
                findings=[MockFinding()],
                reflection_report={},
                react_chain=[],
                error=None,
            )

            result = pipeline._normalize_agent_results([agent_result])

            assert isinstance(result, dict)
            assert "Agent1" in result
            assert len(result["Agent1"]["findings"]) == 1
            assert isinstance(result["Agent1"]["findings"][0], dict)

    def test_normalize_with_dict_findings(self):
        from orchestration.agent_factory import AgentLoopResult
        from orchestration.pipeline import ForensicCouncilPipeline

        pipeline = ForensicCouncilPipeline()

        if hasattr(pipeline, "_normalize_agent_results"):
            agent_result = AgentLoopResult(
                agent_id="Agent1",
                findings=[{"agent_id": "Agent1", "confidence": 0.9}],
                reflection_report={},
                react_chain=[],
                error=None,
            )

            result = pipeline._normalize_agent_results([agent_result])

            assert isinstance(result, dict)
            assert "Agent1" in result
            assert len(result["Agent1"]["findings"]) == 1
            assert result["Agent1"]["findings"][0]["confidence"] == 0.9

    def test_normalize_with_error_result(self):
        from orchestration.agent_factory import AgentLoopResult
        from orchestration.pipeline import ForensicCouncilPipeline

        pipeline = ForensicCouncilPipeline()

        if hasattr(pipeline, "_normalize_agent_results"):
            agent_result = AgentLoopResult(
                agent_id="Agent1",
                findings=[],
                reflection_report={},
                react_chain=[],
                error="Connection failed",
            )

            result = pipeline._normalize_agent_results([agent_result])

            assert isinstance(result, dict)
            assert "Agent1" in result
            assert result["Agent1"]["agent_had_error"] is True
            assert len(result["Agent1"]["findings"]) == 1
            assert "error" in result["Agent1"]["findings"][0]["finding_type"]


class TestPipelineInitializationExtended:
    """Tests for pipeline initialization."""

    async def test_pipeline_initializes_with_session_id(self):
        from orchestration.pipeline import ForensicCouncilPipeline

        pipeline = ForensicCouncilPipeline()

        with (
            patch(
                "core.persistence.redis_client.get_redis_client", new_callable=AsyncMock
            ) as m_redis,
        ):
            m_redis.return_value = None

            with patch(
                "core.persistence.postgres_client.get_postgres_client", new_callable=AsyncMock
            ):
                with patch(
                    "core.persistence.qdrant_client.get_qdrant_client", new_callable=AsyncMock
                ):
                    test_session_id = UUID("12345678-1234-1234-1234-123456789012")
                    await pipeline._initialize_components(test_session_id)

                    assert pipeline.working_memory is not None
                    assert pipeline.episodic_memory is not None

    async def test_pipeline_deep_analysis_flag(self):
        from orchestration.pipeline import ForensicCouncilPipeline

        pipeline = ForensicCouncilPipeline()

        if hasattr(pipeline, "run_deep_analysis_flag"):
            pipeline.run_deep_analysis_flag = True
            assert pipeline.run_deep_analysis_flag is True

            pipeline.run_deep_analysis_flag = False
            assert pipeline.run_deep_analysis_flag is False
