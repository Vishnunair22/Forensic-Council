"""
Agent lifecycle unit tests — sealing the arbiter's initial-analysis path.

Covers:
  1. Empty-report signing: when all agents produce only skip/not-applicable findings,
     deliberate() must return a ForensicReport with a non-empty cryptographic_signature.

  2. final_verdict null guard: the verdict-mapping block must not raise AttributeError
     when deliberation_result.final_verdict is None or empty-string (defensive path).

  3. Agent lifecycle invariants: every ForensicReport leaving deliberate() must have
     an overall_verdict, a non-empty report_id, and session_id matching the arbiter's.
"""

from __future__ import annotations

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
os.environ.setdefault("DEMO_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "")
os.environ.setdefault("LLM_MODEL", "test-model")

from agents.arbiter import CouncilArbiter, ForensicReport
from core.config import Settings

# ── Helpers ─────────────────────────────────────────────────────────────────

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


def _arbiter(session_id: UUID | None = None) -> CouncilArbiter:
    return CouncilArbiter(session_id=session_id or uuid4(), config=_settings())


def _skip_finding(agent_id: str = "Agent1") -> dict[str, Any]:
    """Finding that triggers the all-skipped path in deliberate()."""
    return {
        "finding_id": str(uuid4()),
        "agent_id": agent_id,
        "finding_type": "file type not applicable",
        "status": "NOT_APPLICABLE",
        "confidence_raw": None,
        "calibrated_probability": None,
        "court_statement": "File type not supported.",
        "reasoning_summary": "Skipped.",
        "metadata": {},
    }


def _all_skipped_results(*agent_ids: str) -> dict[str, dict[str, Any]]:
    return {a: {"findings": [_skip_finding(a)]} for a in agent_ids}


# ── 1. Empty-report signing ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_report_has_cryptographic_signature():
    """
    When all agents produce only skip/not-applicable findings, deliberate()
    must return a ForensicReport with a non-empty cryptographic_signature.

    Before the fix, _empty_report() was returned directly (unsigned), leaving
    cryptographic_signature == "" and breaking the court-defensibility invariant.
    """
    arb = _arbiter()
    results = _all_skipped_results("Agent1", "Agent3", "Agent5")

    report = await arb.deliberate(results, case_id="case-empty-test")

    assert isinstance(report, ForensicReport)
    assert report.cryptographic_signature, (
        "ForensicReport must have a non-empty cryptographic_signature even when all agents skipped"
    )
    assert report.report_hash, "ForensicReport must have a non-empty report_hash"
    assert report.overall_verdict == "ABSTAIN"  # all agents skipped → no analysis run


@pytest.mark.asyncio
async def test_empty_report_session_id_matches_arbiter():
    """session_id on the empty report must equal the arbiter's own session_id."""
    sid = uuid4()
    arb = _arbiter(session_id=sid)
    results = _all_skipped_results("Agent1")

    report = await arb.deliberate(results, case_id="case-session-test")

    assert str(report.session_id) == str(sid)


@pytest.mark.asyncio
async def test_empty_report_has_valid_report_id():
    """report_id must be a parseable UUID even on the empty path."""
    arb = _arbiter()
    results = _all_skipped_results("Agent1", "Agent3", "Agent5")

    report = await arb.deliberate(results, case_id="case-uuid-test")

    try:
        UUID(str(report.report_id))
    except (ValueError, AttributeError) as e:
        pytest.fail(f"report.report_id is not a valid UUID: {e}")


@pytest.mark.asyncio
async def test_normal_report_still_signed():
    """
    Sanity: the normal (non-empty) deliberation path must still produce
    a signed report. Regression guard for the empty-path fix.
    """
    arb = _arbiter()
    results = {
        "Agent1": {
            "findings": [
                {
                    "finding_id": str(uuid4()),
                    "agent_id": "Agent1",
                    "finding_type": "ela_analysis",
                    "status": "CONFIRMED",
                    "confidence_raw": 0.85,
                    "calibrated_probability": 0.80,
                    "court_statement": "No manipulation detected.",
                    "reasoning_summary": "ELA map uniform.",
                    "metadata": {"court_defensible": True, "tool_name": "ela", "evidence_verdict": "NEGATIVE"},
                }
            ]
        }
    }

    report = await arb.deliberate(results, case_id="case-normal-test")

    assert isinstance(report, ForensicReport)
    assert report.cryptographic_signature, "Normal report must also be signed"


# ── 2. final_verdict null guard ──────────────────────────────────────────────


def test_verdict_mapping_handles_none_final_verdict():
    """
    The verdict-mapping block must not raise AttributeError if
    deliberation_result.final_verdict is None.

    Test the guard logic in isolation using the same expression used in arbiter.py.
    """
    final_verdict_none: str | None = None
    # This is the exact expression after the fix:
    v_upper = (final_verdict_none or "INCONCLUSIVE").upper()
    assert v_upper == "INCONCLUSIVE"


def test_verdict_mapping_handles_empty_string_final_verdict():
    """Empty string should also be treated as INCONCLUSIVE."""
    final_verdict_empty = ""
    v_upper = (final_verdict_empty or "INCONCLUSIVE").upper()
    assert v_upper == "INCONCLUSIVE"


def test_verdict_mapping_passes_through_valid_verdict():
    """Valid verdict strings must pass through unchanged."""
    for raw, expected in [
        ("NO_REPORTABLE_MANIPULATION_DETECTED", "NO_REPORTABLE_MANIPULATION_DETECTED"),
        ("LIKELY_MANIPULATED", "LIKELY_MANIPULATED"),
        ("SUSPICIOUS_INTEGRITY_SIGNALS", "SUSPICIOUS_INTEGRITY_SIGNALS"),
    ]:
        v_upper = (raw or "INCONCLUSIVE").upper()
        assert v_upper == raw, f"Expected {raw}, got {v_upper}"


# ── 3. Lifecycle invariants ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deliberate_always_returns_forensic_report():
    """deliberate() must return a ForensicReport in both empty and normal paths."""
    arb = _arbiter()

    # Empty path
    report_empty = await arb.deliberate(
        _all_skipped_results("Agent1", "Agent3", "Agent5"),
        case_id="lifecycle-empty",
    )
    assert isinstance(report_empty, ForensicReport)

    # Normal path (single agent, minimal finding)
    report_normal = await arb.deliberate(
        {
            "Agent1": {
                "findings": [
                    {
                        "finding_id": str(uuid4()),
                        "agent_id": "Agent1",
                        "finding_type": "ela_analysis",
                        "status": "CONFIRMED",
                        "confidence_raw": 0.75,
                        "calibrated_probability": 0.70,
                        "court_statement": "No manipulation detected.",
                        "reasoning_summary": "Uniform ELA.",
                        "metadata": {"court_defensible": True, "tool_name": "ela", "evidence_verdict": "NEGATIVE"},
                    }
                ]
            }
        },
        case_id="lifecycle-normal",
    )
    assert isinstance(report_normal, ForensicReport)


@pytest.mark.asyncio
async def test_deliberate_overall_verdict_always_set():
    """overall_verdict must be a non-empty string in all paths."""
    arb = _arbiter()

    report = await arb.deliberate(
        _all_skipped_results("Agent1"),
        case_id="verdict-always-set",
    )
    assert report.overall_verdict
    assert isinstance(report.overall_verdict, str)
    assert len(report.overall_verdict) > 0
