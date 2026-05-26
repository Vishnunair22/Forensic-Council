"""
Unit tests for WorkingMemory and Task state management.

Covers:
- Task creation and status transitions (PENDING â†’ IN_PROGRESS â†’ COMPLETE / BLOCKED)
- Task serialization / deserialization round-trip
- WorkingMemoryState field defaults
- Iteration ceiling enforcement awareness
- HITL state field handling
"""

import json
import os
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_PASSWORD", "test")
os.environ.setdefault("DEMO_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")

from core.working_memory import Task, TaskStatus, WorkingMemory, WorkingMemoryState

# â”€â”€ TaskStatus enum â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestTaskStatusEnum:
    def test_all_statuses_defined(self):
        assert {s.value for s in TaskStatus} == {"PENDING", "IN_PROGRESS", "COMPLETE", "BLOCKED"}

    def test_status_values_are_strings(self):
        for s in TaskStatus:
            assert isinstance(s.value, str)


# â”€â”€ Task model â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestTask:
    def test_default_status_is_pending(self):
        t = Task(description="Run ELA analysis")
        assert t.status == TaskStatus.PENDING

    def test_task_id_is_uuid(self):
        t = Task(description="Run ELA analysis")
        assert isinstance(t.task_id, UUID)

    def test_two_tasks_different_ids(self):
        a = Task(description="task a")
        b = Task(description="task b")
        assert a.task_id != b.task_id

    def test_description_stored(self):
        t = Task(description="Detect JPEG ghosts")
        assert t.description == "Detect JPEG ghosts"

    def test_result_ref_none_by_default(self):
        t = Task(description="test")
        assert t.result_ref is None

    def test_blocked_reason_none_by_default(self):
        t = Task(description="test")
        assert t.blocked_reason is None

    def test_task_to_dict_round_trip(self):
        t = Task(
            description="ELA pass",
            status=TaskStatus.IN_PROGRESS,
            result_ref="ref-001",
        )
        d = t.to_dict()
        assert d["description"] == "ELA pass"
        assert d["status"] == "IN_PROGRESS"
        assert d["result_ref"] == "ref-001"
        assert isinstance(d["task_id"], str)

    def test_task_from_dict_restores_status(self):
        t = Task(description="test", status=TaskStatus.COMPLETE)
        d = t.to_dict()
        restored = Task.from_dict(d)
        assert restored.status == TaskStatus.COMPLETE
        assert restored.description == "test"
        assert restored.task_id == t.task_id

    def test_task_from_dict_blocked_reason(self):
        t = Task(
            description="stalled task",
            status=TaskStatus.BLOCKED,
            blocked_reason="model unavailable",
        )
        d = t.to_dict()
        restored = Task.from_dict(d)
        assert restored.blocked_reason == "model unavailable"
        assert restored.status == TaskStatus.BLOCKED

    @pytest.mark.parametrize("status", list(TaskStatus))
    def test_task_all_statuses_round_trip(self, status):
        t = Task(description="test", status=status)
        d = t.to_dict()
        restored = Task.from_dict(d)
        assert restored.status == status


# â”€â”€ WorkingMemoryState model â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestWorkingMemoryState:
    def _make(self, **kwargs) -> WorkingMemoryState:
        defaults = {"session_id": uuid4(), "agent_id": "Agent1"}
        defaults.update(kwargs)
        return WorkingMemoryState(**defaults)

    def test_tasks_default_empty(self):
        s = self._make()
        assert s.tasks == []

    def test_current_iteration_starts_at_zero(self):
        s = self._make()
        assert s.current_iteration == 0

    def test_iteration_ceiling_default_ten(self):
        s = self._make()
        assert s.iteration_ceiling == 10

    def test_hitl_state_default_none(self):
        s = self._make()
        assert s.hitl_state is None

    def test_session_id_stored(self):
        sid = uuid4()
        s = self._make(session_id=sid)
        assert s.session_id == sid

    def test_agent_id_stored(self):
        s = self._make(agent_id="Agent3")
        assert s.agent_id == "Agent3"

    def test_tool_registry_snapshot_default_none(self):
        s = self._make()
        assert s.tool_registry_snapshot is None

    def test_custom_iteration_ceiling(self):
        s = self._make(iteration_ceiling=20)
        assert s.iteration_ceiling == 20

    def test_adding_task_mutates_list(self):
        s = self._make()
        t = Task(description="new task")
        s.tasks.append(t)
        assert len(s.tasks) == 1
        assert s.tasks[0].description == "new task"

    def test_multiple_tasks_stored(self):
        tasks = [Task(description=f"task {i}") for i in range(5)]
        s = self._make(tasks=tasks)
        assert len(s.tasks) == 5


# ── WorkingMemory class tests (from test_working_memory_extended.py) ─────────────────


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
        redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))

        state = await wm.get_state(sid, "Agent1")
        assert state is not None

    @pytest.mark.asyncio
    async def test_update_task_uses_lua_script(self):
        import json
        wm, redis = self._make_wm_with_redis()
        sid = uuid4()
        await wm.initialize(sid, "Agent1", ["Task A"])
        key = wm._get_key(sid, "Agent1")
        state_json = wm._local_cache[key]

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
        await wm.update_task(sid, "Agent1", task_id, TaskStatus.BLOCKED, blocked_reason="reason")

    @pytest.mark.asyncio
    async def test_update_state_uses_lua_when_redis_available(self):
        import json
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
        await wm.initialize(sid, "Agent1", ["Task A"])
        key = wm._get_key(sid, "Agent1")
        assert key in wm._local_cache


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
        from pathlib import Path
        wm = WorkingMemory(redis_client=None)
        wm._wal_dir = tmp_path
        monkeypatch.setattr(Path, "write_text", lambda *a, **kw: (_ for _ in ()).throw(PermissionError("no write")))
        wm._wal_write("key", "data")


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
            mock_redis.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_with_provided_redis_does_not_disconnect(self):
        mock_redis = AsyncMock()
        mock_redis.disconnect = AsyncMock()
        wm = WorkingMemory(redis_client=mock_redis)
        async with wm:
            pass
        mock_redis.disconnect.assert_not_called()


class TestGetKey:
    def test_get_key_format(self):
        wm = WorkingMemory(redis_client=None)
        sid = uuid4()
        key = wm._get_key(sid, "Agent1")
        assert key == f"wm:{sid}:Agent1"
