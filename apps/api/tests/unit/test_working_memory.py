"""
Unit tests for WorkingMemory and Task state management.

Covers:
- Task creation and status transitions (PENDING â†’ IN_PROGRESS â†’ COMPLETE / BLOCKED)
- Task serialization / deserialization round-trip
- WorkingMemoryState field defaults
- Iteration ceiling enforcement awareness
- HITL state field handling
"""

import os
from uuid import UUID, uuid4

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

from core.working_memory import Task, TaskStatus, WorkingMemoryState

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
