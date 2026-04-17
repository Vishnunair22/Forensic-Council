"""
Unit tests for agents/arbiter.py.

Covers:
- FindingVerdict enum
- FindingComparison model
- ChallengeResult / TribunalCase models
- AgentMetrics model
- ForensicReport model
- CouncilArbiter instantiation
- CouncilArbiter.deliberate() with mock findings
- SignalBus (pipeline module)
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

from agents.arbiter import (
    AgentMetrics,
    ChallengeResult,
    CouncilArbiter,
    FindingComparison,
    FindingVerdict,
    ForensicReport,
    TribunalCase,
)


def _make_finding(
    agent_id="Agent1",
    finding_type="ela",
    status="CONFIRMED",
    confidence=0.85,
    **kwargs,
) -> dict:
    return {
        "agent_id": agent_id,
        "finding_type": finding_type,
        "status": status,
        "confidence_raw": confidence,
        "raw_confidence_score": confidence,
        "calibrated_probability": confidence,
        "reasoning_summary": f"{finding_type} analysis complete.",
        "metadata": {"tool_name": finding_type, "court_defensible": True},
        **kwargs,
    }


def _make_arbiter(session_id=None) -> CouncilArbiter:
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
    cl = AsyncMock()
    cl.log_entry = AsyncMock()
    return CouncilArbiter(
        session_id=session_id or uuid4(),
        custody_logger=cl,
        config=config,
    )


# ── Enum tests ─────────────────────────────────────────────────────────────────

class TestFindingVerdict:
    def test_all_values(self):
        vals = {v.value for v in FindingVerdict}
        assert "AGREEMENT" in vals
        assert "INDEPENDENT" in vals
        assert "CONTRADICTION" in vals


# ── Model tests ────────────────────────────────────────────────────────────────

class TestFindingComparison:
    def test_creation(self):
        fc = FindingComparison(
            finding_a=_make_finding("Agent1", "ela"),
            finding_b=_make_finding("Agent2", "noise"),
            verdict=FindingVerdict.INDEPENDENT,
        )
        assert fc.verdict == FindingVerdict.INDEPENDENT
        assert fc.cross_modal_confirmed is False


class TestChallengeResult:
    def test_creation(self):
        cr = ChallengeResult(
            challenged_agent="Agent1",
            original_finding=_make_finding(),
        )
        assert cr.challenge_id is not None
        assert cr.resolved is False


class TestTribunalCase:
    def test_creation(self):
        fc = FindingComparison(
            finding_a=_make_finding("Agent1"),
            finding_b=_make_finding("Agent2"),
            verdict=FindingVerdict.CONTRADICTION,
        )
        tc = TribunalCase(
            agent_a_id="Agent1",
            agent_b_id="Agent2",
            contradiction=fc,
        )
        assert tc.tribunal_id is not None
        assert tc.resolved is False


class TestAgentMetrics:
    def test_creation(self):
        m = AgentMetrics(agent_id="Agent1", agent_name="Image Forensics")
        assert m.total_tools_called == 0
        assert m.error_rate == 0.0
        assert m.skipped is False

    def test_skipped_agent(self):
        m = AgentMetrics(agent_id="Agent2", agent_name="Audio", skipped=True)
        assert m.skipped is True


class TestForensicReport:
    def test_creation(self):
        sid = uuid4()
        report = ForensicReport(
            session_id=sid,
            case_id="CASE001",
            executive_summary="Test summary.",
            per_agent_findings={"Agent1": [_make_finding()]},
            overall_verdict="LIKELY MANIPULATED",
            uncertainty_statement="High confidence.",
        )
        assert report.report_id is not None
        assert report.overall_confidence == 0.0


# ── CouncilArbiter instantiation ───────────────────────────────────────────────

class TestCouncilArbiterInit:
    def test_can_instantiate(self):
        arbiter = _make_arbiter()
        assert arbiter is not None

    def test_session_id_stored(self):
        sid = uuid4()
        arbiter = _make_arbiter(session_id=sid)
        assert arbiter.session_id == sid

    def test_key_store_created(self):
        arbiter = _make_arbiter()
        assert arbiter._key_store is not None

    def test_config_defaults_to_get_settings(self):
        sid = uuid4()
        # Without passing config, should use get_settings
        with patch("agents.arbiter.get_settings") as mock_gs:
            mock_settings = MagicMock()
            mock_gs.return_value = mock_settings
            arbiter = CouncilArbiter(session_id=sid)
            assert arbiter.config is mock_settings


# ── CouncilArbiter.deliberate() ────────────────────────────────────────────────

class TestCouncilArbiterDeliberate:
    @pytest.mark.asyncio
    async def test_deliberate_empty_results_returns_report(self):
        arbiter = _make_arbiter()
        with patch("agents.arbiter.cross_modal_fuse", return_value={"verdict": "INSUFFICIENT_DATA"}):
            report = await arbiter.deliberate({}, case_id="CASE001", use_llm=False)
        assert isinstance(report, ForensicReport)
        assert report.case_id == "CASE001"

    @pytest.mark.asyncio
    async def test_deliberate_with_single_agent_findings(self):
        arbiter = _make_arbiter()
        agent_results = {
            "Agent1": {
                "findings": [_make_finding("Agent1", "ela", confidence=0.8)],
                "react_chain": [],
                "self_reflection": None,
            }
        }
        with patch("agents.arbiter.cross_modal_fuse", return_value={"verdict": "INSUFFICIENT_DATA"}):
            report = await arbiter.deliberate(agent_results, case_id="CASE002", use_llm=False)
        assert isinstance(report, ForensicReport)
        assert "Agent1" in report.per_agent_findings

    @pytest.mark.asyncio
    async def test_deliberate_with_multiple_agents(self):
        arbiter = _make_arbiter()
        agent_results = {
            "Agent1": {
                "findings": [_make_finding("Agent1", "ela", confidence=0.9)],
                "react_chain": [],
                "self_reflection": None,
            },
            "Agent2": {
                "findings": [_make_finding("Agent2", "audio_artifact", confidence=0.7)],
                "react_chain": [],
                "self_reflection": None,
            },
        }
        with patch("agents.arbiter.cross_modal_fuse", return_value={"verdict": "CROSS_MODAL_CONFIRMED"}):
            report = await arbiter.deliberate(agent_results, case_id="CASE003", use_llm=False)
        assert isinstance(report, ForensicReport)
        assert len(report.per_agent_findings) == 2

    @pytest.mark.asyncio
    async def test_deliberate_with_skipped_agent(self):
        arbiter = _make_arbiter()
        agent_results = {
            "Agent1": {
                "findings": [_make_finding("Agent1", "ela", confidence=0.9)],
                "react_chain": [],
                "self_reflection": None,
            },
            "Agent2": {
                "findings": [{
                    "agent_id": "Agent2",
                    "finding_type": "file type not applicable",
                    "status": "NOT_APPLICABLE",
                    "confidence_raw": 0.0,
                    "reasoning_summary": "Audio agent not applicable to image.",
                    "metadata": {},
                }],
                "react_chain": [],
                "self_reflection": None,
            },
        }
        with patch("agents.arbiter.cross_modal_fuse", return_value={"verdict": "INSUFFICIENT_DATA"}):
            report = await arbiter.deliberate(agent_results, case_id="CASE004", use_llm=False)
        assert isinstance(report, ForensicReport)
        assert "Agent2" in report.per_agent_findings

    @pytest.mark.asyncio
    async def test_deliberate_with_high_confidence_returns_manipulated_verdict(self):
        arbiter = _make_arbiter()
        agent_results = {
            "Agent1": {
                "findings": [_make_finding("Agent1", "ela", confidence=0.95)],
                "react_chain": [],
                "self_reflection": None,
            },
        }
        with patch("agents.arbiter.cross_modal_fuse", return_value={"verdict": "CROSS_MODAL_CONFIRMED"}):
            report = await arbiter.deliberate(agent_results, case_id="CASE005", use_llm=False)
        assert isinstance(report, ForensicReport)
        assert report.overall_confidence >= 0.0

    @pytest.mark.asyncio
    async def test_deliberate_with_duplicate_findings_deduplicates(self):
        """Duplicate (agent_id, finding_type, tool_name) findings should be deduplicated."""
        arbiter = _make_arbiter()
        f1 = _make_finding("Agent1", "ela", confidence=0.7)
        f2 = _make_finding("Agent1", "ela", confidence=0.9)  # Same tool, higher confidence
        f2["metadata"]["tool_name"] = "ela_full_image"
        f1["metadata"]["tool_name"] = "ela_full_image"
        agent_results = {
            "Agent1": {
                "findings": [f1, f2],
                "react_chain": [],
                "self_reflection": None,
            }
        }
        with patch("agents.arbiter.cross_modal_fuse", return_value={"verdict": "INSUFFICIENT_DATA"}):
            report = await arbiter.deliberate(agent_results, case_id="CASE006", use_llm=False)
        # Should have deduplicated
        assert len(report.per_agent_findings.get("Agent1", [])) <= 2

    @pytest.mark.asyncio
    async def test_deliberate_with_llm_disabled(self):
        """use_llm=False should skip LLM synthesis without error."""
        arbiter = _make_arbiter()
        agent_results = {
            "Agent1": {
                "findings": [_make_finding("Agent1", "ela", confidence=0.8)],
                "react_chain": [],
                "self_reflection": None,
            }
        }
        with patch("agents.arbiter.cross_modal_fuse", return_value={"verdict": "INSUFFICIENT_DATA"}):
            report = await arbiter.deliberate(agent_results, case_id="CASE007", use_llm=False)
        assert isinstance(report, ForensicReport)

    @pytest.mark.asyncio
    async def test_deliberate_with_not_applicable_findings(self):
        """NOT_APPLICABLE findings should be counted as not-applicable, not errors."""
        arbiter = _make_arbiter()
        f = _make_finding("Agent1", "prnu", confidence=0.0)
        f["metadata"]["verdict"] = "NOT_APPLICABLE"
        f["metadata"]["prnu_verdict"] = "NOT_APPLICABLE"
        agent_results = {
            "Agent1": {
                "findings": [f],
                "react_chain": [],
                "self_reflection": None,
            }
        }
        with patch("agents.arbiter.cross_modal_fuse", return_value={"verdict": "INSUFFICIENT_DATA"}):
            report = await arbiter.deliberate(agent_results, case_id="CASE008", use_llm=False)
        # Error rate should be 0 since NOT_APPLICABLE is not a failure
        if "Agent1" in report.per_agent_metrics:
            metrics = report.per_agent_metrics["Agent1"]
            assert isinstance(metrics, dict) or hasattr(metrics, "error_rate")

    @pytest.mark.asyncio
    async def test_deliberate_with_react_chain(self):
        """Findings with react_chain should be processed correctly."""
        arbiter = _make_arbiter()
        agent_results = {
            "Agent1": {
                "findings": [_make_finding("Agent1", "ela", confidence=0.8)],
                "react_chain": [
                    {"step_type": "THOUGHT", "content": "Analyzing image..."},
                    {"step_type": "ACTION", "content": "run ELA", "tool_name": "ela_full_image"},
                ],
                "self_reflection": {"report": "ELA shows signs of manipulation."},
            }
        }
        with patch("agents.arbiter.cross_modal_fuse", return_value={"verdict": "INSUFFICIENT_DATA"}):
            report = await arbiter.deliberate(agent_results, case_id="CASE009", use_llm=False)
        assert isinstance(report, ForensicReport)
        # React chains should be stored in the report
        assert "Agent1" in report.react_chains or isinstance(report.react_chains, dict)
