"""
Unit tests for core/working_memory.py
"""

import pytest
from core.working_memory import WorkingMemory, WorkingMemoryState, Task, TaskStatus


class TestWorkingMemory:
    """Test cases for WorkingMemory."""

    @pytest.fixture
    def session_id(self):
        """Create a test session ID."""
        return "test-session-12345"

    @pytest.fixture
    def working_memory(self, session_id):
        """Create a working memory instance."""
        return WorkingMemory(session_id=session_id)

    def test_initialization(self, working_memory, session_id):
        """Test that working memory initializes correctly."""
        assert working_memory.session_id == session_id
        assert working_memory.state == WorkingMemoryState.IDLE

    def test_add_observation(self, working_memory):
        """Test adding observations."""
        working_memory.add_observation("Test observation 1")
        working_memory.add_observation("Test observation 2")
        
        observations = working_memory.get_observations()
        
        assert len(observations) == 2
        assert "Test observation 1" in observations
        assert "Test observation 2" in observations

    def test_add_task(self, working_memory):
        """Test adding tasks."""
        task = Task(
            task_id="task-1",
            description="Test task",
            status=TaskStatus.PENDING,
        )
        
        working_memory.add_task(task)
        
        tasks = working_memory.get_tasks()
        
        assert len(tasks) == 1
        assert tasks[0].task_id == "task-1"

    def test_update_task_status(self, working_memory):
        """Test updating task status."""
        task = Task(
            task_id="task-1",
            description="Test task",
            status=TaskStatus.PENDING,
        )
        
        working_memory.add_task(task)
        working_memory.update_task_status("task-1", TaskStatus.COMPLETED)
        
        tasks = working_memory.get_tasks()
        
        assert tasks[0].status == TaskStatus.COMPLETED

    def test_clear(self, working_memory):
        """Test clearing working memory."""
        working_memory.add_observation("Test observation")
        task = Task(
            task_id="task-1",
            description="Test task",
            status=TaskStatus.PENDING,
        )
        working_memory.add_task(task)
        
        working_memory.clear()
        
        assert len(working_memory.get_observations()) == 0
        assert len(working_memory.get_tasks()) == 0

    def test_serialization(self, working_memory):
        """Test serialization/deserialization."""
        working_memory.add_observation("Test observation")
        task = Task(
            task_id="task-1",
            description="Test task",
            status=TaskStatus.PENDING,
        )
        working_memory.add_task(task)
        
        # Serialize
        data = working_memory.to_dict()
        
        assert "session_id" in data
        assert "observations" in data
        assert "tasks" in data
        
        # Deserialize
        new_memory = WorkingMemory.from_dict(data)
        
        assert new_memory.session_id == working_memory.session_id
        assert len(new_memory.get_observations()) == 1
        assert len(new_memory.get_tasks()) == 1


class TestTask:
    """Test cases for Task model."""

    def test_task_creation(self):
        """Test task creation."""
        task = Task(
            task_id="task-1",
            description="Test task",
            status=TaskStatus.PENDING,
        )
        
        assert task.task_id == "task-1"
        assert task.description == "Test task"
        assert task.status == TaskStatus.PENDING

    def test_task_status_transitions(self):
        """Test task status transitions."""
        task = Task(
            task_id="task-1",
            description="Test task",
            status=TaskStatus.PENDING,
        )
        
        task.status = TaskStatus.RUNNING
        assert task.status == TaskStatus.RUNNING
        
        task.status = TaskStatus.COMPLETED
        assert task.status == TaskStatus.COMPLETED
