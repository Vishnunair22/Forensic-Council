"""
Test 4: Arbiter Verdict (Deterministic - No LLM)
Tests calculate_manipulation_probability and CouncilArbiter deliberation.
"""
import asyncio
import uuid
from typing import Any


def _make_finding(
    agent_id: str = "Agent1",
    confidence: float = 0.85,
    verdict: str = "NEGATIVE",
    tool_name: str = "ela_full_image",
    finding_type: str = "ela_analysis",
    metadata: dict | None = None,
) -> dict[str, Any]:
    base_meta = {"tool_name": tool_name, "analysis_phase": "initial", "court_defensible": True}
    if metadata:
        base_meta.update(metadata)
    return {
        "finding_id": str(uuid.uuid4()),
        "agent_id": agent_id,
        "finding_type": finding_type,
        "status": "CONFIRMED",
        "confidence_raw": confidence,
        "calibrated_probability": confidence * 0.95,
        "evidence_verdict": verdict,
        "reasoning_summary": "Analysis complete.",
        "metadata": base_meta,
    }


async def test_manipulation_probability():
    from agents.arbiter_verdict import calculate_manipulation_probability

    # Test 1: No manipulation signals → probability 0
    clean_findings = [
        _make_finding("Agent1", 0.90, "NEGATIVE", "ela_full_image"),
        _make_finding("Agent2", 0.85, "NEGATIVE", "speaker_diarize"),
        _make_finding("Agent3", 0.80, "NEGATIVE", "object_detection"),
    ]
    prob, count = calculate_manipulation_probability(clean_findings)
    assert prob == 0.0, f"Expected 0.0, got {prob}"
    assert count == 0, f"Expected 0 signals, got {count}"
    print(f"  Clean findings: prob={prob}, signals={count}")

    # Test 2: Single manipulation signal
    manip_findings = [
        _make_finding("Agent1", 0.92, "POSITIVE", "neural_ela",
                       metadata={"manipulation_detected": True}),
        _make_finding("Agent3", 0.80, "NEGATIVE", "object_detection"),
    ]
    prob, count = calculate_manipulation_probability(manip_findings)
    assert prob > 0.0, f"Expected > 0.0, got {prob}"
    assert count >= 1, f"Expected >= 1 signal, got {count}"
    print(f"  Single signal: prob={prob:.4f}, signals={count}")

    # Test 3: Cross-agent corroboration (stronger signal)
    multi_manip = [
        _make_finding("Agent1", 0.90, "POSITIVE", "neural_ela",
                       metadata={"manipulation_detected": True}),
        _make_finding("Agent3", 0.85, "POSITIVE", "lighting_consistency",
                       metadata={"scene_incongruent": True}),
        _make_finding("Agent5", 0.95, "POSITIVE", "timestamp_analysis",
                       metadata={"mismatch_detected": True}),
    ]
    prob, count = calculate_manipulation_probability(multi_manip)
    assert prob > 0.3, f"Expected > 0.3 for multi-signal, got {prob}"
    assert count >= 3, f"Expected >= 3 signals, got {count}"
    print(f"  Multi-agent corroboration: prob={prob:.4f}, signals={count}")


async def test_arbiter_deliberation():
    from agents.arbiter import CouncilArbiter
    from core.config import Settings

    settings = Settings(
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
        llm_enable_post_synthesis=False,
    )

    arbiter = CouncilArbiter(session_id=uuid.uuid4(), config=settings)

    agent_results = {
        "Agent1": {
            "findings": [
                _make_finding("Agent1", 0.90, "NEGATIVE", "file_hash_verify"),
                _make_finding("Agent1", 0.85, "NEGATIVE", "neural_ela"),
                _make_finding("Agent1", 0.80, "NEGATIVE", "frequency_domain_analysis"),
            ],
            "synthesis": {},
        },
        "Agent3": {
            "findings": [
                _make_finding("Agent3", 0.75, "NEGATIVE", "object_detection"),
                _make_finding("Agent3", 0.70, "NEGATIVE", "scene_incongruence"),
            ],
            "synthesis": {},
        },
        "Agent5": {
            "findings": [
                _make_finding("Agent5", 0.95, "NEGATIVE", "exif_extract"),
                _make_finding("Agent5", 0.90, "NEGATIVE", "file_structure_analysis"),
            ],
            "synthesis": {},
        },
    }

    report = await arbiter.deliberate(
        agent_results=agent_results,
        case_id="CASE-TEST-001",
        use_llm=False,
    )

    assert report is not None
    assert report.overall_verdict in [
        "AUTHENTIC", "LIKELY_AUTHENTIC", "INCONCLUSIVE",
        "SUSPICIOUS", "LIKELY_MANIPULATED", "MANIPULATED", "ABSTAIN",
    ]
    assert report.executive_summary
    assert report.uncertainty_statement
    assert report.verdict_sentence
    assert report.key_findings
    assert report.reliability_note

    print(f"  Verdict: {report.overall_verdict}")
    print(f"  Confidence: {report.overall_confidence:.2%}")
    print(f"  Error Rate: {report.overall_error_rate:.2%}")
    print(f"  Manipulation Prob: {report.manipulation_probability:.2%}")
    print(f"  Active Agents: {report.applicable_agent_count}")
    print(f"  Degradation Flags: {report.degradation_flags}")


async def test_arbiter_degradation_flags():
    from agents.arbiter import CouncilArbiter
    from core.config import Settings

    settings = Settings(
        app_env="testing",
        signing_key="test-signing-key-" + "x" * 32,
        postgres_user="test",
        postgres_password="test",
        postgres_db="test",
        redis_password="test",
        DEMO_PASSWORD="test",
        llm_provider="groq",
        llm_api_key="gsk_test_key_that_is_long_enough_20_chars",
        llm_model="llama-3.3-70b-versatile",
        bootstrap_admin_password="Admin_123!",
        bootstrap_investigator_password="Inv_123!",
        llm_enable_post_synthesis=True,
    )

    arbiter = CouncilArbiter(session_id=uuid.uuid4(), config=settings)

    agent_results = {
        "Agent1": {
            "findings": [
                _make_finding("Agent1", 0.90, "NEGATIVE", "file_hash_verify"),
            ],
            "synthesis": {},
        },
    }

    report = await arbiter.deliberate(
        agent_results=agent_results,
        case_id="CASE-DEGRADE-001",
        use_llm=False,
    )

    # With llm_enable_post_synthesis=True but use_llm=False, degradation flag should fire
    has_llm_flag = any("LLM" in f for f in report.degradation_flags)
    print(f"  Degradation flags: {report.degradation_flags}")
    print(f"  LLM degradation detected: {has_llm_flag}")


if __name__ == "__main__":
    print("Test 4a: Manipulation Probability Calculation")
    asyncio.run(test_manipulation_probability())
    print()
    print("Test 4b: Full Arbiter Deliberation (No LLM)")
    asyncio.run(test_arbiter_deliberation())
    print()
    print("Test 4c: Arbiter Degradation Flags")
    asyncio.run(test_arbiter_degradation_flags())
    print()
    print(" All Arbiter tests passed!")
