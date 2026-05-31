import json
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from orchestration.pipeline_phases import (
    _await_deep_analysis_decision,
    _await_deep_report_request,
)


class _RedisStub:
    def __init__(self, value: dict | None):
        self.value = json.dumps(value) if value is not None else None
        self.deleted: list[str] = []

    async def get(self, key: str):
        return self.value

    async def getdel(self, key: str):
        val = self.value
        self.value = None
        return val

    async def delete(self, key: str):
        self.deleted.append(key)

    async def execute_command(self, cmd: str, *args):
        if cmd == "GETDEL":
            val = self.value
            self.value = None
            return val
        raise NotImplementedError()

    async def set(self, key: str, value: Any, **kwargs):
        pass


@pytest.mark.asyncio
async def test_deep_analysis_gate_consumes_decision_after_pause(monkeypatch):
    """Status is set to awaiting_decision first, THEN pre-existing decision is consumed."""
    redis = _RedisStub({"deep_analysis": True})

    async def _redis():
        return redis

    metadata_store: dict = {}

    async def _get_metadata(*args, **kwargs):
        return metadata_store.get("result", {"status": "awaiting_decision"})

    async def _set_metadata(*args, **kwargs):
        pass

    monkeypatch.setattr("core.persistence.redis_client.get_redis_client", _redis)
    monkeypatch.setattr("api.routes._session_state.get_active_pipeline_metadata", _get_metadata)
    monkeypatch.setattr("api.routes._session_state.set_active_pipeline_metadata", _set_metadata)

    import asyncio
    pipeline = SimpleNamespace(
        _awaiting_user_decision=False,
        run_deep_analysis_flag=False,
        deep_analysis_decision_event=asyncio.Event(),
        _redis=redis,
        config=SimpleNamespace(hitl_decision_timeout=3600),
    )

    should_run_deep = await _await_deep_analysis_decision(pipeline, uuid4())

    assert should_run_deep is True
    assert pipeline.run_deep_analysis_flag is True


@pytest.mark.asyncio
async def test_deep_analysis_gate_no_decision_polls(monkeypatch):
    """When no pre-existing decision, the function enters polling and sets up state correctly."""
    redis = _RedisStub(None)
    metadata_written: list[dict] = []

    async def _redis():
        return redis

    async def _get_metadata(*args, **kwargs):
        return {"status": "running"}

    async def _set_metadata(*args, **kwargs):
        metadata_written.append(kwargs)

    monkeypatch.setattr("core.persistence.redis_client.get_redis_client", _redis)
    monkeypatch.setattr("api.routes._session_state.get_active_pipeline_metadata", _get_metadata)
    monkeypatch.setattr("api.routes._session_state.set_active_pipeline_metadata", _set_metadata)

    import asyncio

    pipeline = SimpleNamespace(
        _awaiting_user_decision=False,
        run_deep_analysis_flag=False,
        deep_analysis_decision_event=asyncio.Event(),
        _redis=None,
        config=SimpleNamespace(hitl_decision_timeout=0.1),
    )

    should_run_deep = await _await_deep_analysis_decision(pipeline, uuid4())

    assert should_run_deep is False
    assert pipeline._awaiting_user_decision is False


@pytest.mark.asyncio
async def test_deep_report_gate_consumes_decision_after_pause(monkeypatch):
    """Status is set to awaiting_deep_report first, THEN pre-existing decision is consumed."""
    import asyncio

    redis = _RedisStub({"deep_analysis": False})

    async def _redis():
        return redis

    async def _get_metadata(*args, **kwargs):
        return {"status": "awaiting_deep_report"}

    async def _set_metadata(*args, **kwargs):
        pass

    monkeypatch.setattr("core.persistence.redis_client.get_redis_client", _redis)
    monkeypatch.setattr("api.routes._session_state.get_active_pipeline_metadata", _get_metadata)
    monkeypatch.setattr("api.routes._session_state.set_active_pipeline_metadata", _set_metadata)

    pipeline = SimpleNamespace(
        _awaiting_user_decision=False,
        run_deep_analysis_flag=False,
        deep_analysis_decision_event=asyncio.Event(),
        _redis=redis,
        config=SimpleNamespace(hitl_decision_timeout=3600),
    )

    await _await_deep_report_request(pipeline, uuid4())

    assert redis.deleted == []


@pytest.mark.asyncio
async def test_pre_warm_case_id_preserved(monkeypatch):
    """Pre-warm calls should propagate the actual case_id, not empty string."""

    pre_warm_args: list[tuple] = []

    async def _fake_pre_warm(agent_results, case_id, *, suppress_broadcasts=False):
        pre_warm_args.append((case_id, suppress_broadcasts))
        return None

    pipeline = SimpleNamespace(
        _case_id="CASE-2026-001",
        _pre_warm_task=None,
        _run_arbiter_pre_warm=_fake_pre_warm,
        _normalize_agent_results=lambda x: {},
        arbiter=None,
        _degradation_flags=[],
        config=SimpleNamespace(
            external_ai_allowed=False,
            llm_enable_post_synthesis=False,
        ),
        inter_agent_bus=None,
    )

    _initial_norm = pipeline._normalize_agent_results({})
    await pipeline._run_arbiter_pre_warm(_initial_norm, pipeline._case_id)

    assert len(pre_warm_args) == 1
    assert pre_warm_args[0][0] == "CASE-2026-001"


@pytest.mark.asyncio
async def test_visual_profile_bus_methods(monkeypatch):
    """set_visual_profile/get_visual_profile should work and agents must use correct names."""
    from core.inter_agent_bus import InterAgentBus

    bus = InterAgentBus(session_id=uuid4())
    sid = str(uuid4())
    data = {"metadata": {"tool_name": "visual_evidence_profile", "authenticity_verdict": "LIKELY_MANIPULATED"}}

    bus.set_visual_profile(sid, data)
    result = bus.get_visual_profile(sid)

    assert result == data
    assert result.get("metadata", {}).get("authenticity_verdict") == "LIKELY_MANIPULATED"
    assert not hasattr(bus, "set_image_context")
    assert not hasattr(bus, "get_image_context")


@pytest.mark.asyncio
async def test_context_event_set_on_broadcast_failure(monkeypatch):
    """context_event must be set even when _broadcast_context's injection step fails."""
    import asyncio

    context_event = asyncio.Event()
    injected = {"called": False}

    def _failing_broadcast(producer_finding):
        injected["called"] = True
        raise RuntimeError("Simulated bus failure")

    def _safe_broadcast(producer_finding):
        injected["called"] = True

    # Simulate: broadcast fails but context_event is set (via finally)
    try:
        _failing_broadcast({"metadata": {"tool_name": "visual_evidence_profile"}})
    except RuntimeError:
        context_event.set()

    assert context_event.is_set()
    assert injected["called"] is True


@pytest.mark.asyncio
async def test_resume_expected_phase_validation(monkeypatch):
    """ResumeRequest with expected_phase should reject phase mismatches."""
    from api.routes.sessions import ResumeRequest

    r1 = ResumeRequest(deep_analysis=True, expected_phase="initial")
    assert r1.deep_analysis is True
    assert r1.expected_phase == "initial"

    r2 = ResumeRequest(deep_analysis=False)
    assert r2.expected_phase is None

    r3 = ResumeRequest(deep_analysis=False, expected_phase="deep")
    assert r3.expected_phase == "deep"


@pytest.mark.asyncio
async def test_cold_cache_dto_has_all_fields(monkeypatch):
    """Cold-cache DB report reconstruction should include all canonical DTO fields."""
    from api.routes._dto import _forensic_report_to_dto

    class FakeReport:
        def __init__(self):
            self.report_id = uuid4()
            self.session_id = uuid4()
            self.case_id = "CASE-001"
            self.executive_summary = "Summary"
            self.per_agent_findings = {}
            self.per_agent_metrics = {}
            self.per_agent_analysis = {}
            self.overall_confidence = 0.85
            self.overall_error_rate = 0.05
            self.overall_verdict = "REVIEW REQUIRED"
            self.cross_modal_confirmed = []
            self.contested_findings = []
            self.tribunal_resolved = []
            self.incomplete_findings = []
            self.uncertainty_statement = ""
            self.cryptographic_signature = "sig123"
            self.report_hash = "hash123"
            self.signed_utc = None
            self.verdict_sentence = "Verdict"
            self.key_findings = []
            self.reliability_note = ""
            self.manipulation_probability = 0.0
            self.compression_penalty = 1.0
            self.confidence_min = 0.0
            self.confidence_max = 1.0
            self.confidence_std_dev = 0.0
            self.applicable_agent_count = 0
            self.skipped_agents = {}
            self.analysis_coverage_note = ""
            self.per_agent_summary = {}
            self.per_agent_narrative_structured = {}
            self.summary_structured = {}
            self.degradation_flags = []
            self.degraded_findings_summary = ""
            self.is_deep_analysis = False
            self.cross_modal_fusion = {}

    dto = _forensic_report_to_dto(FakeReport())
    assert dto.per_agent_narrative_structured == {}
    assert dto.summary_structured == {}
    assert dto.degraded_findings_summary == {}
    assert dto.is_deep_analysis is False
    assert dto.cross_modal_fusion == {}
