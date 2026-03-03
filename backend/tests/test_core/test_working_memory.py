"""
Working Memory Tests
====================

Tests for Redis-backed working memory.
"""

import json
import pytest
from uuid import uuid4

from core.working_memory import (
    Task,
    TaskStatus,
    WorkingMemory,
    WorkingMemoryState,
)
from core.custody_logger import CustodyLogger, EntryType
from infra.redis_client import RedisClient
from infra.postgres_client import PostgresClient


@pytest.fixture
async def working_memory(
    redis_client: RedisClient,
    postgres_client: PostgresClient,
) -> WorkingMemory:
    """Create a WorkingMemory with test dependencies."""
    custody_logger = CustodyLogger(postgres_client=postgres_client)
    return WorkingMemory(
        redis_client=redis_client,
        custody_logger=custody_logger,
    )


class TestTask:
    """Tests for Task model."""
    
    def test_create_task(self):
        """Test creating a task."""
        task = Task(description="Analyze image")
        
        assert task.description == "Analyze image"
        assert task.status == TaskStatus.PENDING
        assert task.task_id is not None
        assert task.result_ref is None
        assert task.blocked_reason is None
    
    def test_to_dict_and_from_dict(self):
        """Test serialization."""
        task = Task(
            description="Test task",
            status=TaskStatus.IN_PROGRESS,
            result_ref="result_123",
        )
        
        data = task.to_dict()
        restored = Task.from_dict(data)
        
        assert restored.task_id == task.task_id
        assert restored.description == task.description
        assert restored.status == task.status
        assert restored.result_ref == task.result_ref


class TestWorkingMemoryState:
    """Tests for WorkingMemoryState model."""
    
    def test_create_state(self):
        """Test creating a state."""
        session_id = uuid4()
        state = WorkingMemoryState(
            session_id=session_id,
            agent_id="test_agent",
            tasks=[Task(description="Task 1")],
        )
        
        assert state.session_id == session_id
        assert state.agent_id == "test_agent"
        assert len(state.tasks) == 1
        assert state.current_iteration == 0
        assert state.iteration_ceiling == 10
    
    def test_to_dict_and_from_dict(self):
        """Test serialization."""
        session_id = uuid4()
        state = WorkingMemoryState(
            session_id=session_id,
            agent_id="agent",
            tasks=[
                Task(description="Task 1"),
                Task(description="Task 2", status=TaskStatus.COMPLETE),
            ],
            current_iteration=5,
            iteration_ceiling=20,
            hitl_state="PAUSED",
        )
        
        data = state.to_dict()
        restored = WorkingMemoryState.from_dict(data)
        
        assert restored.session_id == state.session_id
        assert restored.agent_id == state.agent_id
        assert len(restored.tasks) == 2
        assert restored.current_iteration == 5
        assert restored.iteration_ceiling == 20
        assert restored.hitl_state == "PAUSED"


class TestWorkingMemory:
    """Tests for WorkingMemory class."""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_initialize_creates_all_tasks_as_pending(
        self,
        working_memory: WorkingMemory,
    ):
        """Test that initialize creates all tasks as pending."""
        session_id = uuid4()
        agent_id = "test_agent"
        tasks = ["Task 1", "Task 2", "Task 3"]
        
        await working_memory.initialize(
            session_id=session_id,
            agent_id=agent_id,
            tasks=tasks,
        )
        
        state = await working_memory.get_state(session_id, agent_id)
        
        assert len(state.tasks) == 3
        for task in state.tasks:
            assert task.status == TaskStatus.PENDING
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_update_task_to_in_progress(
        self,
        working_memory: WorkingMemory,
    ):
        """Test updating task to in progress."""
        session_id = uuid4()
        agent_id = "test_agent"
        
        await working_memory.initialize(
            session_id=session_id,
            agent_id=agent_id,
            tasks=["Task 1"],
        )
        
        state = await working_memory.get_state(session_id, agent_id)
        task_id = state.tasks[0].task_id
        
        await working_memory.update_task(
            session_id=session_id,
            agent_id=agent_id,
            task_id=task_id,
            status=TaskStatus.IN_PROGRESS,
        )
        
        state = await working_memory.get_state(session_id, agent_id)
        assert state.tasks[0].status == TaskStatus.IN_PROGRESS
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_update_task_to_complete_with_result_ref(
        self,
        working_memory: WorkingMemory,
    ):
        """Test updating task to complete with result reference."""
        session_id = uuid4()
        agent_id = "test_agent"
        
        await working_memory.initialize(
            session_id=session_id,
            agent_id=agent_id,
            tasks=["Task 1"],
        )
        
        state = await working_memory.get_state(session_id, agent_id)
        task_id = state.tasks[0].task_id
        
        await working_memory.update_task(
            session_id=session_id,
            agent_id=agent_id,
            task_id=task_id,
            status=TaskStatus.COMPLETE,
            result_ref="artifact_123",
        )
        
        state = await working_memory.get_state(session_id, agent_id)
        assert state.tasks[0].status == TaskStatus.COMPLETE
        assert state.tasks[0].result_ref == "artifact_123"
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_update_task_to_blocked_with_reason(
        self,
        working_memory: WorkingMemory,
    ):
        """Test updating task to blocked with reason."""
        session_id = uuid4()
        agent_id = "test_agent"
        
        await working_memory.initialize(
            session_id=session_id,
            agent_id=agent_id,
            tasks=["Task 1"],
        )
        
        state = await working_memory.get_state(session_id, agent_id)
        task_id = state.tasks[0].task_id
        
        await working_memory.update_task(
            session_id=session_id,
            agent_id=agent_id,
            task_id=task_id,
            status=TaskStatus.BLOCKED,
            blocked_reason="Tool unavailable",
        )
        
        state = await working_memory.get_state(session_id, agent_id)
        assert state.tasks[0].status == TaskStatus.BLOCKED
        assert state.tasks[0].blocked_reason == "Tool unavailable"
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_state_returns_current_status(
        self,
        working_memory: WorkingMemory,
    ):
        """Test that get_state returns current status."""
        session_id = uuid4()
        agent_id = "test_agent"
        
        await working_memory.initialize(
            session_id=session_id,
            agent_id=agent_id,
            tasks=["Task 1", "Task 2"],
            iteration_ceiling=15,
        )
        
        state = await working_memory.get_state(session_id, agent_id)
        
        assert state.session_id == session_id
        assert state.agent_id == agent_id
        assert len(state.tasks) == 2
        assert state.iteration_ceiling == 15
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_serialize_restore_roundtrip_preserves_state(
        self,
        working_memory: WorkingMemory,
    ):
        """Test that serialize/restore roundtrip preserves state."""
        session_id = uuid4()
        agent_id = "test_agent"
        
        # Initialize and modify state
        await working_memory.initialize(
            session_id=session_id,
            agent_id=agent_id,
            tasks=["Task 1", "Task 2"],
            iteration_ceiling=20,
        )
        
        state = await working_memory.get_state(session_id, agent_id)
        task_id = state.tasks[0].task_id
        
        await working_memory.update_task(
            session_id=session_id,
            agent_id=agent_id,
            task_id=task_id,
            status=TaskStatus.COMPLETE,
            result_ref="result_1",
        )
        
        # Serialize
        json_str = await working_memory.serialize_to_json(session_id, agent_id)
        
        # Clear
        await working_memory.clear(session_id, agent_id)
        
        # Restore
        await working_memory.restore_from_json(session_id, agent_id, json_str)
        
        # Verify state preserved
        restored_state = await working_memory.get_state(session_id, agent_id)
        
        assert len(restored_state.tasks) == 2
        assert restored_state.tasks[0].status == TaskStatus.COMPLETE
        assert restored_state.tasks[0].result_ref == "result_1"
        assert restored_state.tasks[1].status == TaskStatus.PENDING
        assert restored_state.iteration_ceiling == 20
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_clear_removes_redis_keys(
        self,
        working_memory: WorkingMemory,
    ):
        """Test that clear removes Redis keys."""
        session_id = uuid4()
        agent_id = "test_agent"
        
        await working_memory.initialize(
            session_id=session_id,
            agent_id=agent_id,
            tasks=["Task 1"],
        )
        
        # Verify key exists
        state = await working_memory.get_state(session_id, agent_id)
        assert state is not None
        
        # Clear
        await working_memory.clear(session_id, agent_id)
        
        # Verify key removed
        with pytest.raises(ValueError):
            await working_memory.get_state(session_id, agent_id)
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_all_memory_operations_log_to_custody_logger(
        self,
        working_memory: WorkingMemory,
    ):
        """Test that all memory operations log to custody logger."""
        session_id = uuid4()
        agent_id = "test_agent"
        
        # Initialize (MEMORY_WRITE)
        await working_memory.initialize(
            session_id=session_id,
            agent_id=agent_id,
            tasks=["Task 1"],
        )
        
        # Get state (MEMORY_READ)
        state = await working_memory.get_state(session_id, agent_id)
        task_id = state.tasks[0].task_id
        
        # Update task (MEMORY_WRITE)
        await working_memory.update_task(
            session_id=session_id,
            agent_id=agent_id,
            task_id=task_id,
            status=TaskStatus.IN_PROGRESS,
        )
        
        # Get chain
        chain = await working_memory._custody_logger.get_session_chain(session_id)
        
        # Verify logs
        memory_writes = [e for e in chain if e.entry_type == EntryType.MEMORY_WRITE]
        memory_reads = [e for e in chain if e.entry_type == EntryType.MEMORY_READ]
        
        # Initialize, update_task = 2 writes
        assert len(memory_writes) >= 2
        # get_state = 1 read (but update_task also calls get_state internally)
        assert len(memory_reads) >= 1
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_increment_iteration(
        self,
        working_memory: WorkingMemory,
    ):
        """Test incrementing iteration counter."""
        session_id = uuid4()
        agent_id = "test_agent"
        
        await working_memory.initialize(
            session_id=session_id,
            agent_id=agent_id,
            tasks=["Task 1"],
        )
        
        # Increment several times
        iter1 = await working_memory.increment_iteration(session_id, agent_id)
        iter2 = await working_memory.increment_iteration(session_id, agent_id)
        iter3 = await working_memory.increment_iteration(session_id, agent_id)
        
        assert iter1 == 1
        assert iter2 == 2
        assert iter3 == 3
        
        # Verify in state
        state = await working_memory.get_state(session_id, agent_id)
        assert state.current_iteration == 3
