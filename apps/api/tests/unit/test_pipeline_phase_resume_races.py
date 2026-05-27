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


class _MetadataStub:
    def __init__(self, status: str = "awaiting_decision"):
        self._status = status

    def get(self, key: str, default=None):
        return self._status if key == "status" else default


@pytest.mark.asyncio
async def test_deep_analysis_gate_consumes_pre_gate_resume_decision(monkeypatch):
    redis = _RedisStub({"deep_analysis": True})

    async def _redis():
        return redis

    async def _metadata(*args, **kwargs):
        return _MetadataStub("awaiting_decision")

    monkeypatch.setattr("core.persistence.redis_client.get_redis_client", _redis)
    monkeypatch.setattr("api.routes._session_state.get_active_pipeline_metadata", _metadata)
    
    import asyncio
    pipeline = SimpleNamespace(
        run_deep_analysis_flag=False,
        deep_analysis_decision_event=asyncio.Event(),
        _redis=redis,
        config=SimpleNamespace(hitl_decision_timeout=3600),
    )

    should_run_deep = await _await_deep_analysis_decision(pipeline, uuid4())

    assert should_run_deep is True
    assert pipeline.run_deep_analysis_flag is True


@pytest.mark.asyncio
async def test_deep_report_gate_consumes_pre_gate_report_request(monkeypatch):
    redis = _RedisStub({"deep_analysis": False})

    async def _redis():
        return redis

    monkeypatch.setattr("core.persistence.redis_client.get_redis_client", _redis)
    pipeline = SimpleNamespace()

    await _await_deep_report_request(pipeline, uuid4())

    assert redis.deleted == []
