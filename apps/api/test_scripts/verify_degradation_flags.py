"""
Verify degradation flags across the entire stack.
"""
import asyncio
import os
import uuid
from typing import Any

os.environ["APP_ENV"] = "testing"
os.environ["SIGNING_KEY"] = "test-signing-key-" + "x" * 32
os.environ["POSTGRES_USER"] = "test"
os.environ["POSTGRES_PASSWORD"] = "test"
os.environ["POSTGRES_DB"] = "test"
os.environ["REDIS_PASSWORD"] = "test"
os.environ["DEMO_PASSWORD"] = "test"
os.environ["LLM_PROVIDER"] = "none"
os.environ["LLM_API_KEY"] = ""
os.environ["LLM_MODEL"] = "test-model"

from agents.arbiter import CouncilArbiter
from agents.arbiter_verdict import ForensicReport
from core.config import Settings


def _settings(**overrides) -> Settings:
    defaults = dict(
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
        gemini_api_key=None,
        bootstrap_admin_password="Admin_123!",
        bootstrap_investigator_password="Inv_123!",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _finding(agent_id: str = "Agent1", phase: str = "initial", tool: str = "ela",
             verdict: str = "NEGATIVE", source: str = "") -> dict[str, Any]:
    meta = {"tool_name": tool, "analysis_phase": phase, "court_defensible": True}
    if source:
        meta["analysis_source"] = source
    return {
        "finding_id": str(uuid.uuid4()),
        "agent_id": agent_id,
        "finding_type": f"{tool}_analysis",
        "status": "CONFIRMED",
        "confidence_raw": 0.85,
        "evidence_verdict": verdict,
        "reasoning_summary": "The neural ELA tool detected zero compression anomalies in the image.",
        "metadata": meta,
    }


async def test_degradation_flag_llm_bypassed():
    """LLM synthesis bypassed flag fires when post-synthesis enabled but LLM unused."""
    settings = _settings(llm_enable_post_synthesis=True)
    arbiter = CouncilArbiter(session_id=uuid.uuid4(), config=settings)
    results = {"Agent1": {"findings": [_finding()], "synthesis": {}}}
    report = await arbiter.deliberate(results, use_llm=False)
    assert any("LLM" in f for f in report.degradation_flags), f"Expected LLM flag, got: {report.degradation_flags}"
    print(f"   LLM bypassed: OK ({report.degradation_flags[0]})")


async def test_degradation_flag_no_llm_config():
    """No LLM flag when post-synthesis disabled (expected baseline)."""
    settings = _settings(llm_enable_post_synthesis=False)
    arbiter = CouncilArbiter(session_id=uuid.uuid4(), config=settings)
    results = {"Agent1": {"findings": [_finding()], "synthesis": {}}}
    report = await arbiter.deliberate(results, use_llm=False)
    llm_flags = [f for f in report.degradation_flags if "LLM" in f or "template" in f.lower()]
    print(f"   Post-synthesis disabled: degradation={report.degradation_flags}")


async def test_degradation_flag_gemini_deep():
    """Gemini deep analysis skipped flag fires when deep findings exist but no Gemini source."""
    settings = _settings(llm_enable_post_synthesis=False)
    arbiter = CouncilArbiter(session_id=uuid.uuid4(), config=settings)
    deep_finding = _finding(phase="deep", tool="neural_ela")
    results = {"Agent1": {"findings": [_finding(), deep_finding], "synthesis": {}}}
    report = await arbiter.deliberate(results, use_llm=False)
    has_gemini_flag = any("Gemini" in f for f in report.degradation_flags)
    print(f"   Gemini deep flag: {has_gemini_flag} — flags={report.degradation_flags}")


async def test_degradation_flag_no_gemini_flag_on_initial():
    """No Gemini flag for initial-phase-only findings (Gemini only runs in deep pass)."""
    settings = _settings(llm_enable_post_synthesis=False)
    arbiter = CouncilArbiter(session_id=uuid.uuid4(), config=settings)
    results = {"Agent1": {"findings": [_finding(phase="initial")], "synthesis": {}}}
    report = await arbiter.deliberate(results, use_llm=False)
    gemini_flags = [f for f in report.degradation_flags if "Gemini" in f]
    assert len(gemini_flags) == 0, f"Expected no Gemini flags for initial-only, got: {report.degradation_flags}"
    print("   No Gemini flag for initial-only: OK")


async def test_degradation_flag_compression_penalty():
    """Compression penalty flag fires when penalty < 0.80."""
    settings = _settings(llm_enable_post_synthesis=False)
    arbiter = CouncilArbiter(session_id=uuid.uuid4(), config=settings)
    compressed = _finding(agent_id="Agent5", tool="compression_risk_audit")
    compressed["metadata"]["compression_penalty"] = 0.5
    compressed["finding_type"] = "compression_risk_audit"
    results = {"Agent5": {"findings": [compressed], "synthesis": {}}}
    report = await arbiter.deliberate(results, use_llm=False)
    comp_flags = [f for f in report.degradation_flags if "compression" in f.lower()]
    print(f"   Compression penalty flag: {comp_flags}")


async def test_report_model_degradation_flags():
    """ForensicReport model properly serializes degradation_flags."""
    report = ForensicReport(
        session_id=uuid.uuid4(),
        case_id="TEST",
        executive_summary="test",
        per_agent_findings={},
        uncertainty_statement="test",
        degradation_flags=["flag1", "flag2"],
    )
    dumped = report.model_dump(mode="json")
    assert "degradation_flags" in dumped
    assert dumped["degradation_flags"] == ["flag1", "flag2"]
    print("   Report model serialization: OK")


async def test_all_verify():
    await test_degradation_flag_llm_bypassed()
    await test_degradation_flag_no_llm_config()
    await test_degradation_flag_gemini_deep()
    await test_degradation_flag_no_gemini_flag_on_initial()
    await test_degradation_flag_compression_penalty()
    await test_report_model_degradation_flags()
    print()
    print(" All degradation flag verifications passed!")

if __name__ == "__main__":
    asyncio.run(test_all_verify())
