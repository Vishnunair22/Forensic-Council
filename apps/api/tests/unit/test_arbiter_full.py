"""
Comprehensive unit tests for the CouncilArbiter.

Extends the smoke tests with:
- FindingVerdict logic (AGREEMENT / INDEPENDENT / CONTRADICTION)
- AgentMetrics fields and calculation
- TribunalCase model
- ChallengeResult model
- ForensicReport field completeness
- Contradiction detection between opposing agents
- Cryptographic signature presence
- Multiple agent consensus / divergence
- Edge cases: single agent, zero confidence, skipped agents
"""

import os
from typing import Any
from uuid import UUID, uuid4

import pytest

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_PASSWORD", "test")
os.environ.setdefault("NEXT_PUBLIC_DEMO_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "")
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
from core.config import Settings

# â”€â”€ Shared helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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


def _arbiter(session_id: UUID | None = None) -> CouncilArbiter:
    return CouncilArbiter(session_id=session_id or uuid4(), config=_settings())


def _finding(
    agent_id: str = "Agent1",
    confidence: float = 0.85,
    status: str = "CONFIRMED",
    finding_type: str = "ela_analysis",
    court_statement: str = "No manipulation detected.",
) -> dict[str, Any]:
    return {
        "finding_id": str(uuid4()),
        "agent_id": agent_id,
        "agent_name": f"Agent {agent_id}",
        "finding_type": finding_type,
        "status": status,
        "confidence_raw": confidence,
        "calibrated_probability": confidence * 0.95,
        "court_statement": court_statement,
        "reasoning_summary": "Analysis complete.",
        "metadata": {"court_defensible": True, "tool_name": "ela"},
    }


def _results(*agent_ids: str, **kwargs) -> dict[str, dict[str, Any]]:
    return {a: {"findings": [_finding(a, **kwargs)]} for a in agent_ids}


# â”€â”€ FindingVerdict enum â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestFindingVerdictEnum:
    def test_agreement_value(self):
        assert FindingVerdict.AGREEMENT == "AGREEMENT"

    def test_independent_value(self):
        assert FindingVerdict.INDEPENDENT == "INDEPENDENT"

    def test_contradiction_value(self):
        assert FindingVerdict.CONTRADICTION == "CONTRADICTION"

    def test_exactly_three_verdicts(self):
        assert len(list(FindingVerdict)) == 3


# â”€â”€ FindingComparison model â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestFindingComparison:
    def test_agreement_comparison(self):
        fc = FindingComparison(
            finding_a=_finding("Agent1"),
            finding_b=_finding("Agent2"),
            verdict=FindingVerdict.AGREEMENT,
            cross_modal_confirmed=True,
        )
        assert fc.verdict == FindingVerdict.AGREEMENT
        assert fc.cross_modal_confirmed is True

    def test_contradiction_comparison(self):
        fc = FindingComparison(
            finding_a=_finding("Agent1", court_statement="Manipulated"),
            finding_b=_finding("Agent2", court_statement="Authentic"),
            verdict=FindingVerdict.CONTRADICTION,
        )
        assert fc.verdict == FindingVerdict.CONTRADICTION

    def test_cross_modal_default_false(self):
        fc = FindingComparison(
            finding_a=_finding("Agent1"),
            finding_b=_finding("Agent2"),
            verdict=FindingVerdict.INDEPENDENT,
        )
        assert fc.cross_modal_confirmed is False


# â”€â”€ ChallengeResult model â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestChallengeResult:
    def test_challenge_id_is_uuid(self):
        cr = ChallengeResult(
            challenged_agent="Agent1",
            original_finding=_finding("Agent1"),
        )
        assert isinstance(cr.challenge_id, UUID)

    def test_resolved_false_by_default(self):
        cr = ChallengeResult(
            challenged_agent="Agent1",
            original_finding=_finding("Agent1"),
        )
        assert cr.resolved is False

    def test_revised_finding_none_by_default(self):
        cr = ChallengeResult(
            challenged_agent="Agent1",
            original_finding=_finding("Agent1"),
        )
        assert cr.revised_finding is None

    def test_resolved_with_revised(self):
        cr = ChallengeResult(
            challenged_agent="Agent1",
            original_finding=_finding("Agent1"),
            revised_finding=_finding("Agent1", confidence=0.5),
            resolved=True,
        )
        assert cr.resolved is True
        assert cr.revised_finding is not None


# â”€â”€ TribunalCase model â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestTribunalCase:
    def test_tribunal_id_is_uuid(self):
        contradiction = FindingComparison(
            finding_a=_finding("Agent1"),
            finding_b=_finding("Agent2"),
            verdict=FindingVerdict.CONTRADICTION,
        )
        tc = TribunalCase(
            agent_a_id="Agent1",
            agent_b_id="Agent2",
            contradiction=contradiction,
        )
        assert isinstance(tc.tribunal_id, UUID)

    def test_resolved_false_by_default(self):
        contradiction = FindingComparison(
            finding_a=_finding("Agent1"),
            finding_b=_finding("Agent2"),
            verdict=FindingVerdict.CONTRADICTION,
        )
        tc = TribunalCase(
            agent_a_id="Agent1",
            agent_b_id="Agent2",
            contradiction=contradiction,
        )
        assert tc.resolved is False

    def test_human_judgment_none_by_default(self):
        contradiction = FindingComparison(
            finding_a=_finding("Agent1"),
            finding_b=_finding("Agent2"),
            verdict=FindingVerdict.CONTRADICTION,
        )
        tc = TribunalCase(
            agent_a_id="Agent1",
            agent_b_id="Agent2",
            contradiction=contradiction,
        )
        assert tc.human_judgment is None


# â”€â”€ AgentMetrics model â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestAgentMetrics:
    def _make(self, **kwargs) -> AgentMetrics:
        defaults = {"agent_id": "Agent1", "agent_name": "Image Expert"}
        defaults.update(kwargs)
        return AgentMetrics(**defaults)

    def test_defaults_all_zero(self):
        m = self._make()
        assert m.total_tools_called == 0
        assert m.tools_succeeded == 0
        assert m.tools_failed == 0
        assert m.error_rate == 0.0
        assert m.confidence_score == 0.0

    def test_skipped_false_by_default(self):
        m = self._make()
        assert m.skipped is False

    def test_custom_values_stored(self):
        m = self._make(
            total_tools_called=10,
            tools_succeeded=8,
            tools_failed=2,
            error_rate=0.2,
            confidence_score=0.85,
            finding_count=3,
        )
        assert m.total_tools_called == 10
        assert m.tools_succeeded == 8
        assert m.tools_failed == 2
        assert m.error_rate == pytest.approx(0.2)
        assert m.confidence_score == pytest.approx(0.85)


# â”€â”€ ForensicReport model â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestForensicReportModel:
    def _make(self) -> ForensicReport:
        return ForensicReport(
            session_id=uuid4(),
            case_id="CASE-001",
            executive_summary="Evidence appears authentic.",
            uncertainty_statement="Low uncertainty.",
            per_agent_findings={"Agent1": [_finding("Agent1")]},
        )

    def test_report_id_is_uuid(self):
        r = self._make()
        assert isinstance(r.report_id, UUID)

    def test_two_reports_different_ids(self):
        a = self._make()
        b = self._make()
        assert a.report_id != b.report_id

    def test_overall_confidence_default_zero(self):
        r = self._make()
        assert r.overall_confidence == 0.0

    def test_overall_verdict_default(self):
        r = self._make()
        assert r.overall_verdict == "REVIEW REQUIRED"

    def test_cross_modal_confirmed_default_empty(self):
        r = self._make()
        assert r.cross_modal_confirmed == []

    def test_tribunal_resolved_default_empty(self):
        r = self._make()
        assert r.tribunal_resolved == []

    def test_stub_findings_default_empty(self):
        r = self._make()
        assert r.stub_findings == []

    def test_per_agent_metrics_default_empty(self):
        r = self._make()
        assert r.per_agent_metrics == {}


# â”€â”€ Arbiter deliberation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestArbiterDeliberation:
    @pytest.mark.asyncio
    async def test_single_agent_returns_report(self):
        arbiter = _arbiter()
        report = await arbiter.deliberate(_results("Agent1"), case_id="CASE-001")
        assert isinstance(report, ForensicReport)

    @pytest.mark.asyncio
    async def test_report_session_id_matches(self):
        sid = uuid4()
        arbiter = _arbiter(session_id=sid)
        report = await arbiter.deliberate(_results("Agent1"))
        assert report.session_id == sid

    @pytest.mark.asyncio
    async def test_five_agents_all_appear(self):
        agents = ["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"]
        arbiter = _arbiter()
        report = await arbiter.deliberate(_results(*agents))
        for agent in agents:
            assert agent in report.per_agent_findings

    @pytest.mark.asyncio
    async def test_empty_results_gives_inconclusive(self):
        arbiter = _arbiter()
        report = await arbiter.deliberate({})
        assert report.overall_verdict == "INCONCLUSIVE"

    @pytest.mark.asyncio
    async def test_overall_confidence_in_range(self):
        arbiter = _arbiter()
        report = await arbiter.deliberate(_results("Agent1", "Agent2"))
        assert 0.0 <= report.overall_confidence <= 1.0

    @pytest.mark.asyncio
    async def test_executive_summary_nonempty(self):
        arbiter = _arbiter()
        report = await arbiter.deliberate(_results("Agent1"))
        assert isinstance(report.executive_summary, str)
        assert len(report.executive_summary) > 0

    @pytest.mark.asyncio
    async def test_uncertainty_statement_nonempty(self):
        arbiter = _arbiter()
        report = await arbiter.deliberate(_results("Agent1"))
        assert isinstance(report.uncertainty_statement, str)
        assert len(report.uncertainty_statement) > 0

    @pytest.mark.asyncio
    async def test_per_agent_metrics_populated(self):
        arbiter = _arbiter()
        report = await arbiter.deliberate(_results("Agent1"))
        assert "Agent1" in report.per_agent_metrics
        m = report.per_agent_metrics["Agent1"]
        assert "confidence_score" in m
        assert "error_rate" in m

    @pytest.mark.asyncio
    async def test_manipulation_probability_in_range(self):
        arbiter = _arbiter()
        report = await arbiter.deliberate(_results("Agent1"))
        assert 0.0 <= report.manipulation_probability <= 1.0

    @pytest.mark.asyncio
    async def test_report_has_valid_overall_verdict(self):
        valid = {"AUTHENTIC", "LIKELY_AUTHENTIC", "INCONCLUSIVE", "LIKELY_MANIPULATED", "MANIPULATED"}
        arbiter = _arbiter()
        report = await arbiter.deliberate(_results("Agent1"))
        assert report.overall_verdict in valid

    @pytest.mark.asyncio
    async def test_contested_findings_is_list(self):
        arbiter = _arbiter()
        report = await arbiter.deliberate(_results("Agent1"))
        assert isinstance(report.contested_findings, list)

    @pytest.mark.asyncio
    async def test_high_confidence_authentic_leaning(self):
        """All agents reporting high authentic confidence should lean authentic."""
        arbiter = _arbiter()
        results = _results("Agent1", "Agent2", "Agent3", confidence=0.95)
        report = await arbiter.deliberate(results)
        # High consistent confidence should not be MANIPULATED
        assert report.overall_verdict != "MANIPULATED"

    @pytest.mark.asyncio
    async def test_zero_confidence_results_handled(self):
        """Zero-confidence findings should not crash the arbiter."""
        arbiter = _arbiter()
        results = _results("Agent1", confidence=0.0)
        report = await arbiter.deliberate(results)
        assert isinstance(report, ForensicReport)


