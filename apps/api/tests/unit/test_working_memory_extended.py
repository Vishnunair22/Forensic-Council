"""
Extended unit tests for core/working_memory.py.

Covers:
- Task / TaskStatus models
- WorkingMemoryState model
- WorkingMemory.initialize()
- WorkingMemory.get_state()
- WorkingMemory.update_task()
- WorkingMemory.update_state()
- WorkingMemory.increment_iteration()
- WAL read/write helpers
- Async context manager
"""

import json
import os
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_PASSWORD", "test")
os.environ.setdefault("NEXT_PUBLIC_DEMO_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")

from core.working_memory import (
    Task,
    TaskStatus,
    WorkingMemory,
    WorkingMemoryState,
)

# ── Task model ─────────────────────────────────────────────────────────────────


class TestTaskModel:
    def test_task_defaults(self):
        t = Task(description="Run ELA")
        assert t.description == "Run ELA"
        assert t.status == TaskStatus.PENDING
        assert t.result_ref is None
        assert t.task_id is not None

    def test_task_to_dict(self):
        t = Task(description="Test task", status=TaskStatus.IN_PROGRESS)
        d = t.to_dict()
        assert d["description"] == "Test task"
        assert d["status"] == "IN_PROGRESS"
        assert "task_id" in d

    def test_task_from_dict(self):
        original = Task(description="Analyze", status=TaskStatus.COMPLETE, result_ref="ref1")
        restored = Task.from_dict(original.to_dict())
        assert restored.description == "Analyze"
        assert restored.status == TaskStatus.COMPLETE
        assert restored.result_ref == "ref1"

    def test_task_from_dict_with_optional_fields(self):
        data = {
            "task_id": str(uuid4()),
            "description": "Test",
            "status": "BLOCKED",
            "result_ref": None,
            "blocked_reason": "Waiting on dep",
            "sub_task_info": "Step 2 of 3",
        }
        t = Task.from_dict(data)
        assert t.blocked_reason == "Waiting on dep"
        assert t.sub_task_info == "Step 2 of 3"


class TestTaskStatus:
    def test_all_statuses(self):
        statuses = {s.value for s in TaskStatus}
        assert "PENDING" in statuses
        assert "IN_PROGRESS" in statuses
        assert "COMPLETE" in statuses
        assert "BLOCKED" in statuses


# ── WorkingMemoryState model ───────────────────────────────────────────────────


class TestWorkingMemoryState:
    def test_state_defaults(self):
        sid = uuid4()
        state = WorkingMemoryState(session_id=sid, agent_id="Agent1")
        assert state.tasks == []
        assert state.current_iteration == 0
        assert state.iteration_ceiling == 10
        assert state.hitl_state is None

    def test_state_to_dict(self):
        sid = uuid4()
        state = WorkingMemoryState(
            session_id=sid,
            agent_id="Agent1",
            tasks=[Task(description="T1")],
            current_iteration=3,
        )
        d = state.to_dict()
        assert d["agent_id"] == "Agent1"
        assert len(d["tasks"]) == 1
        assert d["current_iteration"] == 3

    def test_state_from_dict_roundtrip(self):
        sid = uuid4()
        state = WorkingMemoryState(
            session_id=sid,
            agent_id="Agent2",
            tasks=[Task(description="T1"), Task(description="T2")],
            current_iteration=5,
            iteration_ceiling=20,
        )
        restored = WorkingMemoryState.from_dict(state.to_dict())
        assert restored.agent_id == "Agent2"
        assert len(restored.tasks) == 2
        assert restored.current_iteration == 5
        assert restored.iteration_ceiling == 20

    def test_state_from_dict_with_optional_fields(self):
        sid = uuid4()
        data = {
            "session_id": str(sid),
            "agent_id": "Agent3",
            "tasks": [],
            "current_iteration": 0,
            "iteration_ceiling": 10,
            "hitl_state": "PAUSED",
            "tool_registry_snapshot": [{"name": "ela_full_image"}],
            "last_tool_error": "Tool failed",
        }
        state = WorkingMemoryState.from_dict(data)
        assert state.hitl_state == "PAUSED"
        assert state.last_tool_error == "Tool failed"
        assert len(state.tool_registry_snapshot) == 1


# ── WorkingMemory with no Redis ────────────────────────────────────────────────


class TestWorkingMemoryNoRedis:
    """Tests run without Redis – uses local in-memory cache as fallback."""

    def _make_wm(self):
        cl = AsyncMock()
        cl.log_entry = AsyncMock()
        return WorkingMemory(redis_client=None, custody_logger=cl)

    @pytest.mark.asyncio
    async def test_initialize_stores_in_local_cache(self):
        wm = self._make_wm()
        sid = uuid4()
        await wm.initialize(sid, "Agent1", ["Task A", "Task B"])
        key = wm._get_key(sid, "Agent1")
        assert key in wm._local_cache

    @pytest.mark.asyncio
    async def test_get_state_after_initialize(self):
        wm = self._make_wm()
        sid = uuid4()
        await wm.initialize(sid, "Agent1", ["ELA", "EXIF"])
        state = await wm.get_state(sid, "Agent1")
        assert len(state.tasks) == 2
        assert state.tasks[0].description == "ELA"

    @pytest.mark.asyncio
    async def test_get_state_raises_when_missing(self):
        wm = self._make_wm()
        sid = uuid4()
        with pytest.raises(ValueError, match="No working memory found"):
            await wm.get_state(sid, "Agent1")

    @pytest.mark.asyncio
    async def test_update_task_changes_status(self):
        wm = self._make_wm()
        sid = uuid4()
        await wm.initialize(sid, "Agent1", ["Task A"])
        state = await wm.get_state(sid, "Agent1")
        task_id = state.tasks[0].task_id

        await wm.update_task(sid, "Agent1", task_id, TaskStatus.COMPLETE, result_ref="r1")
        updated = await wm.get_state(sid, "Agent1")
        assert updated.tasks[0].status == TaskStatus.COMPLETE
        assert updated.tasks[0].result_ref == "r1"

    @pytest.mark.asyncio
    async def test_update_task_raises_when_task_missing(self):
        wm = self._make_wm()
        sid = uuid4()
        await wm.initialize(sid, "Agent1", ["Task A"])
        fake_task_id = uuid4()
        with pytest.raises(ValueError):
            await wm.update_task(sid, "Agent1", fake_task_id, TaskStatus.COMPLETE)

    @pytest.mark.asyncio
    async def test_update_state_merges_fields(self):
        wm = self._make_wm()
        sid = uuid4()
        await wm.initialize(sid, "Agent1", ["Task A"])
        await wm.update_state(sid, "Agent1", {"current_iteration": 5})
        state = await wm.get_state(sid, "Agent1")
        assert state.current_iteration == 5

    @pytest.mark.asyncio
    async def test_update_state_creates_if_missing(self):
        """update_state should create a new state if none exists."""
        wm = self._make_wm()
        sid = uuid4()
        state = await wm.update_state(sid, "Agent1", {"current_iteration": 3})
        assert state is not None

    @pytest.mark.asyncio
    async def test_increment_iteration(self):
        wm = self._make_wm()
        sid = uuid4()
        await wm.initialize(sid, "Agent1", ["Task A"])
        new_count = await wm.increment_iteration(sid, "Agent1")
        assert new_count == 1
        state = await wm.get_state(sid, "Agent1")
        assert state.current_iteration == 1

    @pytest.mark.asyncio
    async def test_initialize_without_custody_logger(self):
        wm = WorkingMemory(redis_client=None, custody_logger=None)
        sid = uuid4()
        await wm.initialize(sid, "Agent5", ["Single task"])
        state = await wm.get_state(sid, "Agent5")
        assert len(state.tasks) == 1


# ── WorkingMemory with mocked Redis ───────────────────────────────────────────


class TestWorkingMemoryWithRedis:
    def _make_wm_with_redis(self):
        redis = AsyncMock()
        redis.set = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.client = AsyncMock()
        redis.client.eval = AsyncMock(return_value=None)
        cl = AsyncMock()
        cl.log_entry = AsyncMock()
        return WorkingMemory(redis_client=redis, custody_logger=cl), redis

    @pytest.mark.asyncio
    async def test_initialize_writes_to_redis(self):
        wm, redis = self._make_wm_with_redis()
        sid = uuid4()
        await wm.initialize(sid, "Agent1", ["Task A"])
        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_state_reads_from_redis(self):
        wm, redis = self._make_wm_with_redis()
        sid = uuid4()
        await wm.initialize(sid, "Agent1", ["Task A"])
        # Now Redis mock returns the JSON we stored in local cache
        key = wm._get_key(sid, "Agent1")
        stored_json = wm._local_cache[key]
        redis.get = AsyncMock(return_value=stored_json)

        state = await wm.get_state(sid, "Agent1")
        assert len(state.tasks) == 1

    @pytest.mark.asyncio
    async def test_get_state_falls_back_to_local_cache_on_redis_error(self):
        wm, redis = self._make_wm_with_redis()
        sid = uuid4()
        await wm.initialize(sid, "Agent1", ["Task A"])
        # Redis fails on get
        redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))

        state = await wm.get_state(sid, "Agent1")
        assert state is not None

    @pytest.mark.asyncio
    async def test_update_task_uses_lua_script(self):
        wm, redis = self._make_wm_with_redis()
        sid = uuid4()
        await wm.initialize(sid, "Agent1", ["Task A"])
        key = wm._get_key(sid, "Agent1")
        state_json = wm._local_cache[key]

        # Simulate Lua script returning updated state
        state_data = json.loads(state_json)
        state_data["tasks"][0]["status"] = "COMPLETE"
        redis.client.eval = AsyncMock(return_value=json.dumps(state_data))

        state = await wm.get_state(sid, "Agent1")
        task_id = state.tasks[0].task_id
        await wm.update_task(sid, "Agent1", task_id, TaskStatus.COMPLETE)
        redis.client.eval.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_task_falls_back_on_redis_error(self):
        wm, redis = self._make_wm_with_redis()
        sid = uuid4()
        await wm.initialize(sid, "Agent1", ["Task A"])
        redis.client.eval = AsyncMock(side_effect=Exception("Lua error"))
        redis.get = AsyncMock(return_value=wm._local_cache[wm._get_key(sid, "Agent1")])

        state = await wm.get_state(sid, "Agent1")
        task_id = state.tasks[0].task_id
        # Should fall back to legacy update
        await wm.update_task(sid, "Agent1", task_id, TaskStatus.BLOCKED, blocked_reason="reason")

    @pytest.mark.asyncio
    async def test_update_state_uses_lua_when_redis_available(self):
        wm, redis = self._make_wm_with_redis()
        sid = uuid4()
        await wm.initialize(sid, "Agent1", ["Task A"])
        key = wm._get_key(sid, "Agent1")
        state_data = json.loads(wm._local_cache[key])
        state_data["current_iteration"] = 7
        redis.client.eval = AsyncMock(return_value=json.dumps(state_data))

        state = await wm.update_state(sid, "Agent1", {"current_iteration": 7})
        assert state.current_iteration == 7

    @pytest.mark.asyncio
    async def test_initialize_handles_redis_failure_gracefully(self):
        wm, redis = self._make_wm_with_redis()
        redis.set = AsyncMock(side_effect=ConnectionError("Redis down"))
        sid = uuid4()
        # Should not raise; falls back to local cache
        await wm.initialize(sid, "Agent1", ["Task A"])
        key = wm._get_key(sid, "Agent1")
        assert key in wm._local_cache


# ── WAL read/write ─────────────────────────────────────────────────────────────


class TestWorkingMemoryWAL:
    def test_wal_write_and_read(self, tmp_path):
        wm = WorkingMemory(redis_client=None)
        wm._wal_dir = tmp_path
        key = "wm:test_session:Agent1"
        data = '{"session_id": "abc", "agent_id": "Agent1", "tasks": []}'
        wm._wal_write(key, data)
        result = wm._wal_read(key)
        assert result == data

    def test_wal_read_missing_key_returns_none(self, tmp_path):
        wm = WorkingMemory(redis_client=None)
        wm._wal_dir = tmp_path
        result = wm._wal_read("nonexistent:key")
        assert result is None

    def test_wal_write_handles_permission_error(self, tmp_path, monkeypatch):
        wm = WorkingMemory(redis_client=None)
        wm._wal_dir = tmp_path
        # Patch write_text to raise PermissionError
        from pathlib import Path

        monkeypatch.setattr(
            Path, "write_text", lambda *a, **kw: (_ for _ in ()).throw(PermissionError("no write"))
        )
        # Should not raise
        wm._wal_write("key", "data")


# ── Async context manager ──────────────────────────────────────────────────────


class TestWorkingMemoryContextManager:
    @pytest.mark.asyncio
    async def test_context_manager_acquires_and_releases(self):
        with patch("core.working_memory.get_redis_client") as mock_get:
            mock_redis = AsyncMock()
            mock_redis.disconnect = AsyncMock()
            mock_get.return_value = mock_redis
            wm = WorkingMemory(redis_client=None)
            async with wm:
                assert wm._redis is not None
            # disconnect called since we own the client
            mock_redis.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_with_provided_redis_does_not_disconnect(self):
        mock_redis = AsyncMock()
        mock_redis.disconnect = AsyncMock()
        wm = WorkingMemory(redis_client=mock_redis)
        async with wm:
            pass
        # We don't own the client — should not disconnect
        mock_redis.disconnect.assert_not_called()


# ── get_key helper ──────────────────────────────────────────────────────────────


class TestGetKey:
    def test_get_key_format(self):
        wm = WorkingMemory(redis_client=None)
        sid = uuid4()
        key = wm._get_key(sid, "Agent1")
        assert key == f"wm:{sid}:Agent1"
