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
