"""
Test HITL gate timeout behavior with short timeouts.
"""
import asyncio
import os, uuid, json

os.environ["APP_ENV"] = "testing"
os.environ["SIGNING_KEY"] = "test-signing-key-" + "x" * 32
os.environ["POSTGRES_USER"] = "test"
os.environ["POSTGRES_PASSWORD"] = "test"
os.environ["POSTGRES_DB"] = "test"
os.environ["REDIS_PASSWORD"] = "test"
os.environ["DEMO_PASSWORD"] = "test"
os.environ["LLM_PROVIDER"] = "none"
os.environ["LLM_API_KEY"] = ""

from unittest.mock import AsyncMock, patch, MagicMock
from uuid import UUID


def _patch_redis(redis_mock):
    """Patch get_redis_client with an async wrapper that returns redis_mock."""
    async def _get():
        return redis_mock
    return patch("core.persistence.redis_client.get_redis_client", new=_get)


def _make_pipeline_mock():
    """Create a mock pipeline for testing HITL gates."""
    pipeline = MagicMock()
    pipeline.config.hitl_decision_timeout = 10
    pipeline._redis = None
    pipeline._awaiting_user_decision = False
    pipeline.deep_analysis_decision_event = asyncio.Event()
    pipeline.run_deep_analysis_flag = False
    pipeline._session_id = uuid.uuid4()
    return pipeline


async def test_hitl_gate_times_out():
    """HITL gate should return False when timeout expires without decision."""
    from orchestration.pipeline_phases import _await_deep_analysis_decision

    pipeline = _make_pipeline_mock()
    pipeline.config.hitl_decision_timeout = 1

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.getdel = AsyncMock(return_value=None)

    with _patch_redis(mock_redis), \
         patch("api.routes._session_state.get_active_pipeline_metadata", return_value={}), \
         patch("api.routes._session_state.set_active_pipeline_metadata", return_value=None), \
         patch("api.routes._session_state.broadcast_update", return_value=None):

        start = asyncio.get_event_loop().time()
        result = await _await_deep_analysis_decision(pipeline, uuid.uuid4())
        elapsed = asyncio.get_event_loop().time() - start

        assert result is False, "HITL gate should return False on timeout"
        print(f"  HITL timeout test: result={result}, elapsed={elapsed:.2f}s")
        print(f"  Pipeline awaiting_decision: {pipeline._awaiting_user_decision}")
        print(f"  Pipeline deep_analysis_flag: {pipeline.run_deep_analysis_flag}")


async def test_hitl_decision_accepted():
    """HITL gate should return True when analyst accepts deep analysis."""
    from orchestration.pipeline_phases import _await_deep_analysis_decision

    pipeline = _make_pipeline_mock()
    pipeline.config.hitl_decision_timeout = 10

    decision_data = json.dumps({"deep_analysis": True})

    class RedisWithDecision:
        async def get(self, key):
            return decision_data
        async def getdel(self, key):
            return decision_data
        async def delete(self, key):
            pass

    mock_redis = RedisWithDecision()

    with _patch_redis(mock_redis), \
         patch("api.routes._session_state.get_active_pipeline_metadata", return_value={"status": "awaiting_decision"}), \
         patch("api.routes._session_state.set_active_pipeline_metadata", return_value=None), \
         patch("api.routes._session_state.broadcast_update", return_value=None):

        result = await _await_deep_analysis_decision(pipeline, uuid.uuid4())
        assert result is True, "HITL gate should return True for deep_analysis=True"
        print(f"  HITL decision accepted: result={result}")


async def test_hitl_decision_declined():
    """HITL gate should return False when analyst declines deep analysis."""
    from orchestration.pipeline_phases import _await_deep_analysis_decision

    pipeline = _make_pipeline_mock()
    pipeline.config.hitl_decision_timeout = 10

    decision_data = json.dumps({"deep_analysis": False})

    class RedisWithDecision:
        async def get(self, key):
            return decision_data
        async def getdel(self, key):
            return decision_data
        async def delete(self, key):
            pass

    mock_redis = RedisWithDecision()

    with _patch_redis(mock_redis), \
         patch("api.routes._session_state.get_active_pipeline_metadata", return_value={"status": "awaiting_decision"}), \
         patch("api.routes._session_state.set_active_pipeline_metadata", return_value=None), \
         patch("api.routes._session_state.broadcast_update", return_value=None):

        result = await _await_deep_analysis_decision(pipeline, uuid.uuid4())
        assert result is False, "HITL gate should return False for deep_analysis=False"
        print(f"  HITL decision declined: result={result}")


async def test_hitl_second_gate():
    """Second HITL gate (deep report request) should proceed on timeout."""
    from orchestration.pipeline_phases import _await_deep_report_request

    pipeline = _make_pipeline_mock()
    pipeline.config.hitl_decision_timeout = 1

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.getdel = AsyncMock(return_value=None)

    with _patch_redis(mock_redis), \
         patch("api.routes._session_state.get_active_pipeline_metadata", return_value={}), \
         patch("api.routes._session_state.set_active_pipeline_metadata", return_value=None), \
         patch("api.routes._session_state.broadcast_update", return_value=None):

        start = asyncio.get_event_loop().time()
        await _await_deep_report_request(pipeline, uuid.uuid4())
        elapsed = asyncio.get_event_loop().time() - start
        print(f"  HITL second gate: elapsed={elapsed:.2f}s (no exception means success)")


async def test_hitl_pre_gate_decision_consumption():
    """Pre-gate decision should be consumed before pause to avoid race condition."""
    from orchestration.pipeline_phases import _await_deep_analysis_decision

    pipeline = _make_pipeline_mock()
    pipeline.config.hitl_decision_timeout = 10

    decision_data = json.dumps({"deep_analysis": True})

    from types import SimpleNamespace
    tracker = SimpleNamespace(called=False)

    class RedisGetDel:
        async def getdel(self, key):
            tracker.called = True
            return decision_data
        async def get(self, key):
            return None
        async def delete(self, key):
            pass

    mock_redis = RedisGetDel()

    with _patch_redis(mock_redis), \
         patch("api.routes._session_state.get_active_pipeline_metadata", return_value={"status": "awaiting_decision"}), \
         patch("api.routes._session_state.set_active_pipeline_metadata", return_value=None), \
         patch("api.routes._session_state.broadcast_update", return_value=None):

        result = await _await_deep_analysis_decision(pipeline, uuid.uuid4())
        assert result is True
        assert tracker.called, "GETDEL should be called for pre-gate decision consumption"
        print(f"  Pre-gate decision consumption: result={result}, GETDEL called={tracker.called}")


async def test_all():
    await test_hitl_gate_times_out()
    await test_hitl_decision_accepted()
    await test_hitl_decision_declined()
    await test_hitl_second_gate()
    await test_hitl_pre_gate_decision_consumption()
    print()
    print(" All HITL gate tests passed!")

if __name__ == "__main__":
    asyncio.run(test_all())
