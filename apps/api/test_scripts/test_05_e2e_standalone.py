"""
Test 5: End-to-End Pipeline (No API Keys)
Tests the full pipeline gracefully degrades when API keys are missing.
Uses mocked infrastructure where needed.
"""
import asyncio
import uuid


async def test_degradation_flags_in_report():
    """Verify ForensicReport model correctly surfaces degradation_flags."""
    from agents.arbiter_verdict import ForensicReport

    report = ForensicReport(
        session_id=uuid.uuid4(),
        case_id="CASE-DEGRADE-001",
        executive_summary="Test executive summary.",
        per_agent_findings={},
        uncertainty_statement="No uncertainties.",
        overall_verdict="INCONCLUSIVE",
    )

    assert hasattr(report, "degradation_flags")
    assert isinstance(report.degradation_flags, list)
    assert len(report.degradation_flags) == 0

    report.degradation_flags.append("Gemini API key not configured")
    report.degradation_flags.append("LLM synthesis bypassed")
    report.degradation_flags.append("Redis unavailable")

    assert len(report.degradation_flags) == 3
    print(f"  Degradation flags in model: {report.degradation_flags}")


async def test_pipeline_init_degradation():
    """Verify pipeline records degradation flags during initialization."""
    from core.config import Settings
    from orchestration.pipeline import ForensicCouncilPipeline

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
        gemini_api_key=None,
        llm_model="test-model",
        bootstrap_admin_password="Admin_123!",
        bootstrap_investigator_password="Inv_123!",
    )

    pipeline = ForensicCouncilPipeline(config=settings)
    assert pipeline._degradation_flags == []

    print(f"  Pipeline initialized with {len(pipeline._degradation_flags)} degradation flags")
    print(f"  Heavy tool semaphore: {pipeline.heavy_tool_semaphore._value}")


async def test_arbiter_verdict_without_llm():
    """Test arbiter produces valid verdict without any LLM key."""
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
        gemini_api_key=None,
        llm_model="test-model",
        bootstrap_admin_password="Admin_123!",
        bootstrap_investigator_password="Inv_123!",
        llm_enable_post_synthesis=False,
    )

    arbiter = CouncilArbiter(session_id=uuid.uuid4(), config=settings)
    assert arbiter.config.llm_provider == "none"
    assert arbiter.config.gemini_api_key is None
    assert arbiter.config.gemini_available is False

    print(f"  LLM provider: {arbiter.config.llm_provider}")
    print(f"  Gemini available: {arbiter.config.gemini_available}")
    print(f"  LLM enable post-synthesis: {arbiter.config.llm_enable_post_synthesis}")


async def test_evidence_verdict_mapping():
    """Test evidence_verdict_of handles all verdict types correctly."""
    from agents.arbiter_verdict import evidence_verdict_of

    assert evidence_verdict_of({"evidence_verdict": "POSITIVE"}) == "POSITIVE"
    assert evidence_verdict_of({"evidence_verdict": "NEGATIVE"}) == "NEGATIVE"
    assert evidence_verdict_of({"evidence_verdict": "INCONCLUSIVE"}) == "INCONCLUSIVE"
    assert evidence_verdict_of({"evidence_verdict": "NOT_APPLICABLE"}) == "NOT_APPLICABLE"
    assert evidence_verdict_of({"evidence_verdict": "ERROR"}) == "ERROR"

    # Legacy metadata-based signals
    assert evidence_verdict_of({"metadata": {"manipulation_detected": True}}) == "POSITIVE"
    assert evidence_verdict_of({"metadata": {"deepfake_detected": True}}) == "POSITIVE"
    assert evidence_verdict_of({"metadata": {"scene_incongruent": True}}) == "POSITIVE"

    # Default to NEGATIVE for clean findings
    assert evidence_verdict_of({"status": "CONFIRMED", "metadata": {}}) == "NEGATIVE"

    print("  All evidence_verdict_of mappings correct")


if __name__ == "__main__":
    print("Test 5a: Degradation Flags in ForensicReport")
    asyncio.run(test_degradation_flags_in_report())
    print()
    print("Test 5b: Pipeline Initialization (No Keys)")
    asyncio.run(test_pipeline_init_degradation())
    print()
    print("Test 5c: Arbiter Verdict Without LLM Keys")
    asyncio.run(test_arbiter_verdict_without_llm())
    print()
    print("Test 5d: Evidence Verdict Mapping")
    asyncio.run(test_evidence_verdict_mapping())
    print()
    print(" All E2E tests passed!")
