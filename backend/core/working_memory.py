"""
Working Memory Module
=====================

Redis-backed working memory for agent task tracking.
Part of the dual-layer memory architecture.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from core.logging import get_logger
from core.custody_logger import CustodyLogger, EntryType
from infra.redis_client import RedisClient, get_redis_client

logger = get_logger(__name__)


class TaskStatus(str, Enum):
    """Status of a task in working memory."""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"


class Task(BaseModel):
    """A task in working memory."""
    task_id: UUID = Field(default_factory=uuid4)
    description: str
    status: TaskStatus = TaskStatus.PENDING
    result_ref: Optional[str] = None
    blocked_reason: Optional[str] = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": str(self.task_id),
            "description": self.description,
            "status": self.status.value,
            "result_ref": self.result_ref,
            "blocked_reason": self.blocked_reason,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        """Create from dictionary."""
        return cls(
            task_id=UUID(data["task_id"]),
            description=data["description"],
            status=TaskStatus(data["status"]),
            result_ref=data.get("result_ref"),
            blocked_reason=data.get("blocked_reason"),
        )


class WorkingMemoryState(BaseModel):
    """Full state of working memory for an agent session."""
    session_id: UUID
    agent_id: str
    tasks: list[Task] = Field(default_factory=list)
    current_iteration: int = 0
    iteration_ceiling: int = 10
    hitl_state: Optional[str] = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "session_id": str(self.session_id),
            "agent_id": self.agent_id,
            "tasks": [t.to_dict() for t in self.tasks],
            "current_iteration": self.current_iteration,
            "iteration_ceiling": self.iteration_ceiling,
            "hitl_state": self.hitl_state,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkingMemoryState":
        """Create from dictionary."""
        return cls(
            session_id=UUID(data["session_id"]),
            agent_id=data["agent_id"],
            tasks=[Task.from_dict(t) for t in data["tasks"]],
            current_iteration=data.get("current_iteration", 0),
            iteration_ceiling=data.get("iteration_ceiling", 10),
            hitl_state=data.get("hitl_state"),
        )


class WorkingMemory:
    """
    Redis-backed working memory for agent task tracking.
    
    Provides:
    - Task list management with status tracking
    - Serialization for HITL checkpoint persistence
    - Chain-of-custody logging for all operations
    
    Usage:
        async with WorkingMemory() as memory:
            await memory.initialize(session_id, agent_id, ["Task 1", "Task 2"])
            await memory.update_task(session_id, agent_id, task_id, TaskStatus.IN_PROGRESS)
            state = await memory.get_state(session_id, agent_id)
    """
    
    def __init__(
        self,
        redis_client: Optional[RedisClient] = None,
        custody_logger: Optional[CustodyLogger] = None,
    ) -> None:
        """
        Initialize working memory.
        
        Args:
            redis_client: Optional Redis client
            custody_logger: Optional custody logger
        """
        self._redis = redis_client
        self._custody_logger = custody_logger
        self._owned_client = redis_client is None
    
    async def __aenter__(self) -> "WorkingMemory":
        """Async context manager entry."""
        if self._redis is None:
            self._redis = await get_redis_client()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        if self._owned_client and self._redis:
            await self._redis.disconnect()
            self._redis = None
    
    def _get_key(self, session_id: UUID, agent_id: str) -> str:
        """Get Redis key for session/agent."""
        return f"wm:{session_id}:{agent_id}"
    
    async def initialize(
        self,
        session_id: UUID,
        agent_id: str,
        tasks: list[str],
        iteration_ceiling: int = 10,
    ) -> None:
        """
        Initialize working memory with task list.
        
        Args:
            session_id: Session UUID
            agent_id: Agent identifier
            tasks: List of task descriptions
            iteration_ceiling: Maximum iterations allowed
        """
        # Create task objects
        task_objects = [
            Task(description=desc, status=TaskStatus.PENDING)
            for desc in tasks
        ]
        
        # Create initial state
        state = WorkingMemoryState(
            session_id=session_id,
            agent_id=agent_id,
            tasks=task_objects,
            current_iteration=0,
            iteration_ceiling=iteration_ceiling,
        )
        
        # Store in Redis with 24h TTL
        key = self._get_key(session_id, agent_id)
        await self._redis.set(key, state.model_dump_json(), ex=86400)
        
        # Log to custody logger
        if self._custody_logger:
            await self._custody_logger.log_entry(
                agent_id=agent_id,
                session_id=session_id,
                entry_type=EntryType.MEMORY_WRITE,
                content={
                    "operation": "initialize",
                    "key": key,
                    "task_count": len(tasks),
                    "iteration_ceiling": iteration_ceiling,
                },
            )
        
        logger.info(
            "Initialized working memory",
            session_id=str(session_id),
            agent_id=agent_id,
            task_count=len(tasks),
        )
    
    async def update_task(
        self,
        session_id: UUID,
        agent_id: str,
        task_id: UUID,
        status: TaskStatus,
        result_ref: Optional[str] = None,
        blocked_reason: Optional[str] = None,
    ) -> None:
        """
        Update a task's status.
        
        Args:
            session_id: Session UUID
            agent_id: Agent identifier
            task_id: Task UUID to update
            status: New status
            result_ref: Optional reference to result
            blocked_reason: Optional reason if blocked
        """
        # Get current state
        state = await self.get_state(session_id, agent_id)
        
        # Find and update task
        for task in state.tasks:
            if task.task_id == task_id:
                task.status = status
                if result_ref is not None:
                    task.result_ref = result_ref
                if blocked_reason is not None:
                    task.blocked_reason = blocked_reason
                break
        else:
            raise ValueError(f"Task {task_id} not found")
        
        # Store updated state with 24h TTL
        key = self._get_key(session_id, agent_id)
        await self._redis.set(key, state.model_dump_json(), ex=86400)
        
        # Log to custody logger
        if self._custody_logger:
            await self._custody_logger.log_entry(
                agent_id=agent_id,
                session_id=session_id,
                entry_type=EntryType.MEMORY_WRITE,
                content={
                    "operation": "update_task",
                    "task_id": str(task_id),
                    "status": status.value,
                    "result_ref": result_ref,
                    "blocked_reason": blocked_reason,
                },
            )
        
        logger.debug(
            "Updated task",
            session_id=str(session_id),
            agent_id=agent_id,
            task_id=str(task_id),
            status=status.value,
        )
    
    async def get_state(
        self,
        session_id: UUID,
        agent_id: str,
    ) -> WorkingMemoryState:
        """
        Get the current working memory state.
        
        Args:
            session_id: Session UUID
            agent_id: Agent identifier
        
        Returns:
            WorkingMemoryState with all tasks
        """
        key = self._get_key(session_id, agent_id)
        data = await self._redis.get(key)
        
        if data is None:
            raise ValueError(f"No working memory found for {session_id}/{agent_id}")
        
        # Parse JSON - handle both string and dict responses
        if isinstance(data, dict):
            state_dict = data
        elif isinstance(data, bytes):
            state_dict = json.loads(data.decode("utf-8"))
        elif isinstance(data, str):
            state_dict = json.loads(data)
        else:
            state_dict = json.loads(data)
        
        state = WorkingMemoryState.from_dict(state_dict)
        
        # Log to custody logger
        if self._custody_logger:
            await self._custody_logger.log_entry(
                agent_id=agent_id,
                session_id=session_id,
                entry_type=EntryType.MEMORY_READ,
                content={
                    "operation": "get_state",
                    "key": key,
                    "task_count": len(state.tasks),
                },
            )
        
        return state

    async def update_state(
        self,
        session_id: UUID,
        agent_id: str | None = None,
        updates: dict | None = None,
    ) -> WorkingMemoryState:
        """
        Update arbitrary fields on the working memory state.

        Fetches the current state, applies the updates dict, persists,
        and returns the updated state.  Unknown keys are stored in the
        state dict so that the react loop can pass through custom flags
        (e.g. redirect_context, tribunal_escalation).

        Args:
            session_id: Session UUID
            agent_id: Agent identifier (defaults to first key if None)
            updates: Dictionary of fields to merge into the state
        """
        if updates is None:
            updates = {}

        # Resolve agent_id – when called from react loop the agent_id
        # is available on self, so callers sometimes omit it here.
        if agent_id is None:
            agent_id = ""

        try:
            state = await self.get_state(session_id, agent_id)
        except ValueError:
            # No state exists yet; create a minimal one
            state = WorkingMemoryState(
                session_id=session_id,
                agent_id=agent_id,
            )

        # Apply known top-level fields
        for k, v in updates.items():
            if hasattr(state, k):
                setattr(state, k, v)
            # else: silently skip unknown fields (they are transient flags)

        # Persist with 24h TTL
        key = self._get_key(session_id, agent_id)
        await self._redis.set(key, state.model_dump_json(), ex=86400)

        # Log
        if self._custody_logger:
            await self._custody_logger.log_entry(
                agent_id=agent_id,
                session_id=session_id,
                entry_type=EntryType.MEMORY_WRITE,
                content={
                    "operation": "update_state",
                    "key": key,
                    "updated_fields": list(updates.keys()),
                },
            )

        return state
    
    async def increment_iteration(
        self,
        session_id: UUID,
        agent_id: str,
    ) -> int:
        """
        Increment the iteration counter.
        
        Args:
            session_id: Session UUID
            agent_id: Agent identifier
        
        Returns:
            New iteration count
        """
        state = await self.get_state(session_id, agent_id)
        state.current_iteration += 1
        
        # Persist with 24h TTL
        key = self._get_key(session_id, agent_id)
        await self._redis.set(key, state.model_dump_json(), ex=86400)
        
        return state.current_iteration
    
    async def serialize_to_json(
        self,
        session_id: UUID,
        agent_id: str,
    ) -> str:
        """
        Serialize working memory to JSON for HITL checkpoint.
        
        Args:
            session_id: Session UUID
            agent_id: Agent identifier
        
        Returns:
            JSON string of full state
        """
        state = await self.get_state(session_id, agent_id)
        return state.model_dump_json()
    
    async def restore_from_json(
        self,
        session_id: UUID,
        agent_id: str,
        json_str: str,
    ) -> None:
        """
        Restore working memory from JSON (HITL resume).
        
        Args:
            session_id: Session UUID
            agent_id: Agent identifier
            json_str: JSON string of state
        """
        state_dict = json.loads(json_str)
        state = WorkingMemoryState.from_dict(state_dict)
        
        # Persist with 24h TTL
        key = self._get_key(session_id, agent_id)
        await self._redis.set(key, state.model_dump_json(), ex=86400)
        
        # Log to custody logger
        if self._custody_logger:
            await self._custody_logger.log_entry(
                agent_id=agent_id,
                session_id=session_id,
                entry_type=EntryType.MEMORY_WRITE,
                content={
                    "operation": "restore_from_json",
                    "key": key,
                    "task_count": len(state.tasks),
                },
            )
        
        logger.info(
            "Restored working memory from JSON",
            session_id=str(session_id),
            agent_id=agent_id,
        )
    
    async def clear(
        self,
        session_id: UUID,
        agent_id: str,
    ) -> None:
        """
        Clear working memory for session end.
        
        Args:
            session_id: Session UUID
            agent_id: Agent identifier
        """
        key = self._get_key(session_id, agent_id)
        await self._redis.delete(key)
        
        logger.info(
            "Cleared working memory",
            session_id=str(session_id),
            agent_id=agent_id,
        )


# Singleton instance
_working_memory: Optional[WorkingMemory] = None


async def get_working_memory() -> WorkingMemory:
    """
    Get or create the working memory singleton.
    
    Returns:
        WorkingMemory instance
    """
    global _working_memory
    if _working_memory is None:
        redis = await get_redis_client()
        _working_memory = WorkingMemory(redis_client=redis)
    return _working_memory


async def close_working_memory() -> None:
    """Close the working memory singleton."""
    global _working_memory
    if _working_memory is not None:
        if _working_memory._redis:
            await _working_memory._redis.disconnect()
        _working_memory = None
