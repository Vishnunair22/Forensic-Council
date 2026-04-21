"""
Smoke tests for the Council Arbiter.

All tests run without a live LLM API key: when llm_api_key is None the arbiter
falls back to template-based summaries, so these tests cover the full deliberate()
code path without any network calls.

No database, Redis, or Qdrant is required.
"""

import os
from typing import Any
from uuid import UUID, uuid4

import pytest

# ── Minimal env so config initializes without a .env file ────────────────────
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

from agents.arbiter import CouncilArbiter, ForensicReport
from core.config import Settings

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Helpers
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_VALID_VERDICTS = frozenset({
    "AUTHENTIC",
    "LIKELY_AUTHENTIC",
    "INCONCLUSIVE",
    "LIKELY_MANIPULATED",
    "MANIPULATED",
})


def _make_config() -> Settings:
    """Return a minimal Settings object with no LLM key (forces template fallback)."""
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


def _make_arbiter(session_id: UUID | None = None) -> CouncilArbiter:
    """Construct an arbiter with no external dependencies."""
    sid = session_id or uuid4()
    cfg = _make_config()
    return CouncilArbiter(session_id=sid, config=cfg)


def _minimal_finding(agent_id: str = "Agent1") -> dict[str, Any]:
    """
    Build the minimum finding dict that is treated as a real (non-stub,
    non-skipped) finding by the arbiter.
    """
    return {
        "finding_id": str(uuid4()),
        "agent_id": agent_id,
        "agent_name": "Image Forensics",
        "finding_type": "ela_analysis",
        "status": "CONFIRMED",
        "confidence_raw": 0.80,
        "calibrated_probability": 0.78,
        "court_statement": "No pixel-level manipulation detected.",
        "reasoning_summary": "ELA map is uniform.",
        "metadata": {
            "court_defensible": True,
            "tool_name": "ela",
        },
    }


def _minimal_agent_results(agent_id: str = "Agent1") -> dict[str, dict[str, Any]]:
    return {agent_id: {"findings": [_minimal_finding(agent_id)]}}


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Tests
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@pytest.mark.asyncio
async def test_deliberate_returns_forensic_report() -> None:
    """deliberate() with a single valid agent result must return a ForensicReport."""
    arbiter = _make_arbiter()
    agent_results = _minimal_agent_results()

    report = await arbiter.deliberate(agent_results, case_id="SMOKE-001")

    assert isinstance(report, ForensicReport)


@pytest.mark.asyncio
async def test_report_has_session_id() -> None:
    """The returned report's session_id must match the arbiter's session_id."""
    sid = uuid4()
    arbiter = _make_arbiter(session_id=sid)
    report = await arbiter.deliberate(_minimal_agent_results())

    assert report.session_id == sid


@pytest.mark.asyncio
async def test_report_has_valid_verdict() -> None:
    """overall_verdict must be one of the five canonical verdicts."""
    arbiter = _make_arbiter()
    report = await arbiter.deliberate(_minimal_agent_results())

    assert report.overall_verdict in _VALID_VERDICTS, (
        f"Unexpected verdict: {report.overall_verdict!r}"
    )


@pytest.mark.asyncio
async def test_empty_agent_results_returns_inconclusive() -> None:
    """
    When agent_results is empty (no active agents), the arbiter must return
    overall_verdict == 'INCONCLUSIVE'.
    """
    arbiter = _make_arbiter()
    report = await arbiter.deliberate({})

    assert report.overall_verdict == "INCONCLUSIVE"


@pytest.mark.asyncio
async def test_report_has_executive_summary() -> None:
    """executive_summary must be a non-empty string."""
    arbiter = _make_arbiter()
    report = await arbiter.deliberate(_minimal_agent_results())

    assert isinstance(report.executive_summary, str)
    assert len(report.executive_summary) > 0


@pytest.mark.asyncio
async def test_report_per_agent_findings_matches_input() -> None:
    """per_agent_findings must contain a key for every agent in agent_results."""
    arbiter = _make_arbiter()
    agent_results = _minimal_agent_results("Agent1")
    report = await arbiter.deliberate(agent_results)

    assert "Agent1" in report.per_agent_findings


@pytest.mark.asyncio
async def test_report_overall_confidence_in_range() -> None:
    """overall_confidence must be a float in [0.0, 1.0]."""
    arbiter = _make_arbiter()
    report = await arbiter.deliberate(_minimal_agent_results())

    assert isinstance(report.overall_confidence, float)
    assert 0.0 <= report.overall_confidence <= 1.0


@pytest.mark.asyncio
async def test_report_has_uncertainty_statement() -> None:
    """uncertainty_statement must be present and non-empty."""
    arbiter = _make_arbiter()
    report = await arbiter.deliberate(_minimal_agent_results())

    assert isinstance(report.uncertainty_statement, str)
    assert len(report.uncertainty_statement) > 0


@pytest.mark.asyncio
async def test_report_contested_findings_is_list() -> None:
    """contested_findings must be a list (may be empty)."""
    arbiter = _make_arbiter()
    report = await arbiter.deliberate(_minimal_agent_results())

    assert isinstance(report.contested_findings, list)


@pytest.mark.asyncio
async def test_report_per_agent_metrics_present() -> None:
    """per_agent_metrics must be populated for every submitted agent."""
    arbiter = _make_arbiter()
    agent_results = _minimal_agent_results("Agent1")
    report = await arbiter.deliberate(agent_results)

    assert "Agent1" in report.per_agent_metrics
    metrics = report.per_agent_metrics["Agent1"]
    assert "confidence_score" in metrics
    assert "error_rate" in metrics


@pytest.mark.asyncio
async def test_manipulation_probability_in_range() -> None:
    """manipulation_probability must be a float in [0.0, 1.0]."""
    arbiter = _make_arbiter()
    report = await arbiter.deliberate(_minimal_agent_results())

    assert isinstance(report.manipulation_probability, float)
    assert 0.0 <= report.manipulation_probability <= 1.0


@pytest.mark.asyncio
async def test_multiple_agents_all_appear_in_findings() -> None:
    """All agents' findings should appear in per_agent_findings."""
    arbiter = _make_arbiter()
    agent_results = {
        "Agent1": {"findings": [_minimal_finding("Agent1")]},
        "Agent2": {"findings": [_minimal_finding("Agent2")]},
    }
    report = await arbiter.deliberate(agent_results)

    assert "Agent1" in report.per_agent_findings
    assert "Agent2" in report.per_agent_findings


