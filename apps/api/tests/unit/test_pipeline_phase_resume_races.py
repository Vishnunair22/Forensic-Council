import json
from types import SimpleNamespace
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

    async def delete(self, key: str):
        self.deleted.append(key)


@pytest.mark.asyncio
async def test_deep_analysis_gate_consumes_pre_gate_resume_decision(monkeypatch):
    redis = _RedisStub({"deep_analysis": True})

    async def _redis():
        return redis

    monkeypatch.setattr("core.persistence.redis_client.get_redis_client", _redis)
    pipeline = SimpleNamespace(run_deep_analysis_flag=False)

    should_run_deep = await _await_deep_analysis_decision(pipeline, uuid4())

    assert should_run_deep is True
    assert pipeline.run_deep_analysis_flag is True
    assert redis.deleted == []


@pytest.mark.asyncio
async def test_deep_report_gate_consumes_pre_gate_report_request(monkeypatch):
    redis = _RedisStub({"deep_analysis": False})

    async def _redis():
        return redis

    monkeypatch.setattr("core.persistence.redis_client.get_redis_client", _redis)
    pipeline = SimpleNamespace()

    await _await_deep_report_request(pipeline, uuid4())

    assert redis.deleted == []
