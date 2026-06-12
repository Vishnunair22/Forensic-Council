from __future__ import annotations

import os

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_PASSWORD", "test")
os.environ.setdefault("DEMO_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "test-key-longer-than-20-chars")
os.environ.setdefault("LLM_MODEL", "test-model")

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from core.config import Settings
from core.evidence import ArtifactType, EvidenceArtifact
from core.react_loop import AgentFinding, AgentFindingStatus
from core.synthesis import SynthesisService


def _settings() -> Settings:
    return Settings(
        app_env="testing",
        signing_key="test-signing-key-" + "x" * 32,
        postgres_user="test",
        postgres_password="test",
        postgres_db="test",
        redis_password="test",
        DEMO_PASSWORD="test",
        llm_provider="groq",
        llm_api_key="test-key-longer-than-20-chars",
        llm_model="test-model",
        llm_timeout=12.0,
        bootstrap_admin_password="Admin_123!",
        bootstrap_investigator_password="Inv_123!",
    )


def _evidence(mime: str = "image/jpeg") -> EvidenceArtifact:
    return EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path="/tmp/test.jpg",
        content_hash="abc123",
        action="upload",
        agent_id="system",
        session_id=uuid4(),
        metadata={"mime_type": mime},
    )


def _finding(tool: str, status: str = "CONFIRMED", verdict: str = "NEGATIVE", confidence: float = 0.9) -> AgentFinding:
    f = MagicMock(spec=AgentFinding)
    f.metadata = {"tool_name": tool}
    f.finding_type = "test"
    f.confidence_raw = confidence
    f.status = AgentFindingStatus(status)
    f.evidence_verdict = verdict
    f.reasoning_summary = f"{tool} summary"
    return f


@pytest.fixture
def service():
    return SynthesisService(_settings())


class TestSynthesisPromptRoleSplit:
    @pytest.mark.asyncio
    async def test_system_prompt_contains_strict_instructions(self, service):
        with patch.object(service, "_ground_synthesis_response", return_value={"verdict": "AUTHENTIC", "narrative_summary": "", "sections": []}):
            llm_client = AsyncMock()
            llm_client.generate_synthesis = AsyncMock(return_value=json.dumps({
                "verdict": "AUTHENTIC", "narrative_summary": "Test", "sections": []
            }))
            findings = [_finding("file_hash_verify")]
            ev = _evidence()
            with patch.object(service, "_compact_metrics", return_value={}):
                service._llm_client = llm_client
                try:
                    await service.synthesize_findings(
                        agent_id="Agent1",
                        agent_name="Agent1_Image",
                        findings=findings,
                        evidence_artifact=ev,
                        tool_success_count=1,
                        tool_error_count=0,
                        phase="initial",
                    )
                except Exception:
                    pass
                call_kwargs = llm_client.generate_synthesis.call_args
                if call_kwargs:
                    kwargs = call_kwargs[1] if len(call_kwargs[1]) > 0 else call_kwargs[0]
                    system = kwargs.get("system_prompt", "")
                    user = kwargs.get("user_content", "")
                    assert "[STRICT INSTRUCTIONS]" in system
                    assert "[UNTRUSTED EVIDENCE START" in user

    @pytest.mark.asyncio
    async def test_gemini_context_injected_in_system_prompt(self, service):
        with patch.object(service, "_ground_synthesis_response", return_value={"verdict": "AUTHENTIC", "narrative_summary": "", "sections": []}):
            llm_client = AsyncMock()
            llm_client.generate_synthesis = MagicMock()
            llm_client.generate_synthesis.return_value = json.dumps({
                "verdict": "AUTHENTIC", "narrative_summary": "Test", "sections": []
            })
            findings = [_finding("file_hash_verify")]
            ev = _evidence()
            with patch.object(service, "_compact_metrics", return_value={}):
                service._llm_client = llm_client
                try:
                    await service.synthesize_findings(
                        agent_id="Agent1",
                        agent_name="Agent1_Image",
                        findings=findings,
                        evidence_artifact=ev,
                        tool_success_count=1,
                        tool_error_count=0,
                        phase="initial",
                        gemini_context={
                            "image_category": "screenshot",
                            "priority_signals": ["UI components", "Text alignment"],
                            "visual_verdict": "SUSPICIOUS",
                        }
                    )
                except Exception:
                    pass
                call_kwargs = llm_client.generate_synthesis.call_args
                if call_kwargs:
                    kwargs = call_kwargs[1] if len(call_kwargs[1]) > 0 else call_kwargs[0]
                    system = kwargs.get("system_prompt", "")
                    assert "[GEMINI UPFRONT VISION CONTEXT]" in system
                    assert "Content Category: screenshot" in system
                    assert "UI components, Text alignment" in system
                    assert "Visual Authenticity Verdict: SUSPICIOUS" in system

    @pytest.mark.asyncio
    async def test_user_content_contains_evidence_not_instructions(self, service):
        with patch.object(service, "_ground_synthesis_response", return_value={"verdict": "AUTHENTIC", "narrative_summary": "", "sections": []}):
            llm_client = AsyncMock()
            llm_client.generate_synthesis = AsyncMock(return_value=json.dumps({
                "verdict": "AUTHENTIC", "narrative_summary": "Test", "sections": []
            }))
            findings = [_finding("file_hash_verify")]
            ev = _evidence()
            service._llm_client = llm_client
            try:
                await service.synthesize_findings(
                    agent_id="Agent1",
                    agent_name="Agent1_Image",
                    findings=findings,
                    evidence_artifact=ev,
                    tool_success_count=1,
                    tool_error_count=0,
                    phase="initial",
                )
            except Exception:
                pass
            call_kwargs = llm_client.generate_synthesis.call_args
            if call_kwargs:
                kwargs = call_kwargs[1] if len(call_kwargs[1]) > 0 else call_kwargs[0]
                user = kwargs.get("user_content", "")
                assert "[EVIDENCE CONTEXT]" in user
                assert "[RAW TOOL RESULTS]" in user


class TestSynthesisTokenBudget:
    @pytest.mark.asyncio
    async def test_max_tokens_is_3200(self, service):
        llm_client = AsyncMock()
        llm_client.generate_synthesis = AsyncMock(return_value=json.dumps({
            "verdict": "AUTHENTIC", "narrative_summary": "ok", "sections": []
        }))
        findings = [_finding("file_hash_verify")]
        ev = _evidence()
        with patch.object(service, "_ground_synthesis_response", return_value={"verdict": "AUTHENTIC", "narrative_summary": "", "sections": []}):
            service._llm_client = llm_client
            try:
                await service.synthesize_findings(
                    agent_id="Agent1",
                    agent_name="Agent1_Image",
                    findings=findings,
                    evidence_artifact=ev,
                    tool_success_count=1,
                    tool_error_count=0,
                    phase="initial",
                )
            except Exception:
                pass
            call_kwargs = llm_client.generate_synthesis.call_args
            if call_kwargs:
                kwargs = call_kwargs[1] if len(call_kwargs[1]) > 0 else call_kwargs[0]
                assert kwargs.get("max_tokens") == 3200


class TestSynthesisPromptContent:
    def test_system_prompt_includes_timeout_coverage_rule(self):
        from core.synthesis import _SAFETY_PREAMBLE
        assert "coverage gaps" in _SAFETY_PREAMBLE

    def test_safety_preamble_has_injection_resistance(self):
        from core.synthesis import _SAFETY_PREAMBLE
        assert "PROMPT-INJECTION RESISTANCE" in _SAFETY_PREAMBLE


class TestCompactMetricsHeatmapIsolation:
    """Plan 3.4 — the base64 localization heatmap is a report/UI artifact and must
    never reach metric extraction, narrative prose, or LLM synthesis tuples."""

    def test_localization_map_excluded_from_metrics(self, service):
        f = MagicMock(spec=AgentFinding)
        f.metadata = {
            "tool_name": "neural_splicing",
            "splicing_detected": True,
            "detection_score": 0.91,
            "localization_map_png": "data:image/png;base64," + ("A" * 5000),
            "localization_map_caption": "TruFor forgery map.",
            "huge_blob": "z" * 1000,  # any oversized string is excluded defensively
        }
        f.finding_type = "test"
        f.confidence_raw = 0.91
        f.status = AgentFindingStatus("CONFIRMED")
        f.evidence_verdict = "POSITIVE"
        f.reasoning_summary = "splice"

        metrics = service._compact_metrics(f)

        assert "localization_map_png" not in metrics
        assert "localization_map_caption" not in metrics
        assert "huge_blob" not in metrics
        # The decisive numeric signals are still carried.
        assert metrics["splicing_detected"] is True
        assert metrics["detection_score"] == 0.91


class TestSynthesisSource:
    @pytest.mark.asyncio
    async def test_batch_only_default_skips_individual_groq_call(self, service):
        """Default routing: per-agent Groq narration is consolidated into the
        arbiter's refine_synthesis_batch call — the individual path must not
        spend quota and falls back to the deterministic grounded synthesis."""
        called = {"n": 0}

        class FakeLLMClient:
            provider = "groq"

            async def generate_synthesis(self, **kwargs):
                called["n"] += 1
                return ""

        findings = [_finding("file_hash_verify", verdict="SUSPICIOUS")]
        ev = _evidence()

        with patch("core.synthesis.LLMClient", return_value=FakeLLMClient()):
            result = await service.synthesize_findings(
                agent_id="Agent1",
                agent_name="Agent1_Image",
                findings=findings,
                evidence_artifact=ev,
                tool_success_count=1,
                tool_error_count=0,
                phase="initial",
            )

        assert called["n"] == 0
        assert result["synthesis_source"] == "tool_grounded_fallback"

    @pytest.mark.asyncio
    async def test_successful_llm_synthesis_marks_source(self, service, monkeypatch):
        # Individual Groq path is an explicit opt-out of batch-only routing.
        monkeypatch.setenv("SYNTHESIS_BATCH_ONLY", "0")
        class FakeLLMClient:
            provider = "groq"

            async def generate_synthesis(self, **kwargs):
                return json.dumps({
                    "verdict": "AUTHENTIC",
                    "confidence": 0.82,
                    "narrative_summary": "Hash and frequency checks produced clean, tool-grounded signals for this evidence.",
                    "agent_brief": "Gemini identified the evidence context; tools found no manipulation indicators; verdict authentic at 82%.",
                    "key_findings": ["file_hash_verify: matched intake custody."],
                    "signal_weight": {},
                    "sections": [
                        {
                            "id": "chain_of_custody",
                            "label": "Chain of Custody",
                            "key_signal": "hash matched",
                            "opinion": "SHA-256 matched the intake record.",
                            "severity": "LOW",
                            "refined_findings": [
                                {
                                    "tool": "file_hash_verify",
                                    "user_friendly_summary": "file_hash_verify matched intake custody.",
                                }
                            ],
                        }
                    ],
                })

        # An alert-verdict finding is required to exercise the LLM path: clean
        # evidence intentionally skips Groq synthesis (deterministic is sufficient).
        findings = [_finding("file_hash_verify", verdict="SUSPICIOUS")]
        ev = _evidence()

        with patch("core.synthesis.LLMClient", return_value=FakeLLMClient()):
            result = await service.synthesize_findings(
                agent_id="Agent1",
                agent_name="Agent1_Image",
                findings=findings,
                evidence_artifact=ev,
                tool_success_count=1,
                tool_error_count=0,
                phase="initial",
            )

        assert result["synthesis_source"] == "groq_llm"

    @pytest.mark.asyncio
    async def test_arbiter_uses_agent_llm_brief_when_source_is_marked(self):
        from agents.arbiter import CouncilArbiter

        arbiter = CouncilArbiter(session_id=uuid4(), config=_settings())
        narrative = await arbiter._generate_agent_narrative(
            "Agent1",
            findings=[
                {
                    "agent_id": "Agent1",
                    "finding_type": "Hash Verify",
                    "status": "CONFIRMED",
                    "evidence_verdict": "NEGATIVE",
                    "confidence_raw": 0.82,
                    "reasoning_summary": "Hash matched intake custody.",
                    "metadata": {"tool_name": "file_hash_verify"},
                }
            ],
            metrics={
                "confidence_score": 0.82,
                "error_rate": 0.0,
                "tools_succeeded": 1,
                "total_tools_called": 1,
                "tools_not_applicable": 0,
            },
            agent_data={
                "synthesis": {
                    "synthesis_source": "groq_llm",
                    "agent_brief": "Groq-grounded agent brief.",
                    "key_findings": ["Hash matched intake custody."],
                }
            },
        )

        parsed = json.loads(narrative)
        assert parsed["synthesis_source"] == "groq_llm"
        assert parsed["agent_brief"] == "Groq-grounded agent brief."
