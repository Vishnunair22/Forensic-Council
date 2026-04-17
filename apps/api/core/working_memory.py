"""
Working Memory Module
=====================

Redis-backed working memory for agent task tracking.
Part of the dual-layer memory architecture.
"""

import asyncio
import json
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from core.custody_logger import CustodyLogger, EntryType
from core.persistence.redis_client import RedisClient, get_redis_client
from core.structured_logging import get_logger

logger = get_logger(__name__)


class TaskStatus(StrEnum):
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
    result_ref: str | None = None
    blocked_reason: str | None = None
    sub_task_info: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": str(self.task_id),
            "description": self.description,
            "status": self.status.value,
            "result_ref": self.result_ref,
            "blocked_reason": self.blocked_reason,
            "sub_task_info": self.sub_task_info,
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
            sub_task_info=data.get("sub_task_info"),
        )


class WorkingMemoryState(BaseModel):
    """Full state of working memory for an agent session."""

    session_id: UUID
    agent_id: str
    tasks: list[Task] = Field(default_factory=list)
    current_iteration: int = 0
    iteration_ceiling: int = 10
    hitl_state: str | None = None
    # Live tool catalogue injected by base_agent before loop starts.
    # Each entry: {name, description, available, parameters}.
    # Passed to _get_available_tools_for_llm() so the LLM sees the
    # actual registered tools (not the static fallback catalogue).
    tool_registry_snapshot: list | None = Field(
        default=None, description="Live tool catalogue from this agent's ToolRegistry"
    )
    # Last tool error message — written by base_agent when a tool fails,
    # read by the heartbeat in investigation.py to surface ⚠️ progress text.
    last_tool_error: str | None = Field(
        default=None,
        description="Last tool failure message for live progress broadcasting",
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "session_id": str(self.session_id),
            "agent_id": self.agent_id,
            "tasks": [t.to_dict() for t in self.tasks],
            "current_iteration": self.current_iteration,
            "iteration_ceiling": self.iteration_ceiling,
            "hitl_state": self.hitl_state,
            "tool_registry_snapshot": self.tool_registry_snapshot,
            "last_tool_error": self.last_tool_error,
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
            tool_registry_snapshot=data.get("tool_registry_snapshot"),
            # Issue 4.2: Restore last_tool_error so heartbeat broadcasts
            # can surface tool errors after a Redis round-trip.
            last_tool_error=data.get("last_tool_error"),
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
        redis_client: RedisClient | None = None,
        custody_logger: CustodyLogger | None = None,
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
        # In-memory fallback: stores state when Redis is unavailable.
        # Keyed by the same "wm:{session_id}:{agent_id}" string.
        self._local_cache: dict[str, str] = {}
        # File-based WAL for crash recovery when Redis is unavailable
        self._wal_dir = Path(tempfile.gettempdir()) / "forensic_council_wal"
        self._wal_dir.mkdir(parents=True, exist_ok=True)

        # Lua script for atomic state updates
        self._lua_update_state = """
            local key = KEYS[1]
            local updates_json = ARGV[1]
            local expire = tonumber(ARGV[2]) or 86400
            local session_id = ARGV[3]
            local agent_id = ARGV[4]

            local current = redis.call('GET', key)
            local state
            if current then
                state = cjson.decode(current)
            else
                state = {
                    session_id = session_id,
                    agent_id = agent_id,
                    tasks = {},
                    current_iteration = 0,
                    iteration_ceiling = 10
                }
            end

            local updates = cjson.decode(updates_json)
            for k, v in pairs(updates) do
                state[k] = v
            end

            local new_json = cjson.encode(state)
            redis.call('SET', key, new_json, 'EX', expire)
            return new_json
        """

        # Lua script for atomic task updates
        self._lua_update_task = """
            local key = KEYS[1]
            local task_id = ARGV[1]
            local new_status = ARGV[2]
            local res_ref = ARGV[3]
            local blk_reason = ARGV[4]
            local sub_info = ARGV[5]

            local current = redis.call('GET', key)
            if not current then return nil end

            local state = cjson.decode(current)
            local tasks = state.tasks
            local found = false
            for i, task in ipairs(tasks) do
                if task.task_id == task_id then
                    task.status = new_status
                    if res_ref ~= "" then task.result_ref = res_ref end
                    if blk_reason ~= "" then task.blocked_reason = blk_reason end
                    if sub_info ~= "" then task.sub_task_info = sub_info end
                    found = true
                    break
                end
            end

            if not found then return nil end

            local new_json = cjson.encode(state)
            redis.call('SET', key, new_json, 'EX', 86400)
            return new_json
        """

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

    def _wal_write(self, key: str, state_json: str) -> None:
        """Write state to file-based WAL for crash recovery."""
        try:
            wal_path = self._wal_dir / f"{key.replace(':', '_')}.json"
            wal_path.write_text(state_json, encoding="utf-8")
        except (OSError, PermissionError) as e:
            logger.debug("WAL write failed (disk/permissions)", key=key, error=str(e))
        except Exception as e:
            logger.debug("WAL write failed (unexpected)", key=key, error=str(e))

    def _wal_read(self, key: str) -> str | None:
        """Read state from WAL file if it exists."""
        try:
            wal_path = self._wal_dir / f"{key.replace(':', '_')}.json"
            if wal_path.exists():
                return wal_path.read_text(encoding="utf-8")
        except (OSError, PermissionError) as e:
            logger.debug("WAL read failed (disk/permissions)", key=key, error=str(e))
        except Exception as e:
            logger.debug("WAL read failed (unexpected)", key=key, error=str(e))
        return None

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
            Task(description=desc, status=TaskStatus.PENDING) for desc in tasks
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
        state_json = state.model_dump_json()
        # Always store in local cache (authoritative fallback)
        self._local_cache[key] = state_json
        # Write to WAL for crash recovery
        self._wal_write(key, state_json)
        if self._redis is not None:
            try:
                await self._redis.set(key, state_json, ex=86400)
            except Exception as e:
                logger.warning(
                    "WorkingMemory.initialize: Redis write failed, using in-memory fallback",
                    error=str(e),
                )
        else:
            logger.warning(
                "WorkingMemory.initialize: Redis unavailable, using in-memory fallback"
            )

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
        result_ref: str | None = None,
        blocked_reason: str | None = None,
        sub_task_info: str | None = None,
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
        # Use Lua script for atomic update if Redis is available
        key = self._get_key(session_id, agent_id)
        if self._redis is not None:
            try:
                # Lua script expects strings for all ARGV
                result_json = await self._redis.client.eval(
                    self._lua_update_task,
                    1,
                    key,
                    str(task_id),
                    status.value,
                    result_ref or "",
                    blocked_reason or "",
                    sub_task_info or "",
                )

                if result_json:
                    self._local_cache[key] = result_json
                    logger.debug(
                        "Updated task atomically via Redis Lua", task_id=str(task_id)
                    )
                else:
                    logger.warning(
                        "Task not found during atomic update", task_id=str(task_id)
                    )
                    # Fallback to legacy behavior if task not found in Redis (might be in local cache only)
                    await self._legacy_update_task(
                        session_id,
                        agent_id,
                        task_id,
                        status,
                        result_ref,
                        blocked_reason,
                    )
            except Exception as e:
                logger.warning("Atomic task update failed, falling back", error=str(e))
                await self._legacy_update_task(
                    session_id, agent_id, task_id, status, result_ref, blocked_reason, sub_task_info
                )
        else:
            await self._legacy_update_task(
                session_id, agent_id, task_id, status, result_ref, blocked_reason, sub_task_info
            )

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
                    "sub_task_info": sub_task_info,
                    "atomic": True,
                },
            )

    async def _legacy_update_task(
        self,
        session_id: UUID,
        agent_id: str,
        task_id: UUID,
        status: TaskStatus,
        result_ref: str | None = None,
        blocked_reason: str | None = None,
        sub_task_info: str | None = None,
    ) -> None:
        """Legacy non-atomic task update (fallback)."""
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
                if sub_task_info is not None:
                    task.sub_task_info = sub_task_info
                break
        else:
            raise ValueError(f"Task {task_id} not found")

        # Store updated state
        key = self._get_key(session_id, agent_id)
        state_json = state.model_dump_json()
        self._local_cache[key] = state_json
        if self._redis is not None:
            await self._redis.set(key, state_json, ex=86400)

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
        data = None

        # Try Redis first
        if self._redis is not None:
            try:
                data = await self._redis.get(key)
            except Exception as e:
                logger.debug(
                    "WorkingMemory.get_state: Redis read failed, trying local cache",
                    error=str(e),
                )

        # Fall back to local cache
        if data is None:
            data = self._local_cache.get(key)

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

        # Atomic update via Lua
        key = self._get_key(session_id, agent_id)
        if self._redis is not None:
            try:
                result_json = await self._redis.client.eval(
                    self._lua_update_state,
                    1,
                    key,
                    json.dumps(updates),
                    "86400",
                    str(session_id),
                    agent_id,
                )
                self._local_cache[key] = result_json
                state = WorkingMemoryState.model_validate_json(result_json)
            except Exception as e:
                logger.warning("Atomic state update failed, falling back", error=str(e))
                state = await self._legacy_update_state(session_id, agent_id, updates)
        else:
            state = await self._legacy_update_state(session_id, agent_id, updates)

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
                    "atomic": True,
                },
            )

        return state

    async def _legacy_update_state(
        self,
        session_id: UUID,
        agent_id: str,
        updates: dict,
    ) -> WorkingMemoryState:
        """Legacy non-atomic state update (fallback)."""
        try:
            state = await self.get_state(session_id, agent_id)
        except ValueError:
            state = WorkingMemoryState(session_id=session_id, agent_id=agent_id)

        for k, v in updates.items():
            if hasattr(state, k):
                setattr(state, k, v)

        key = self._get_key(session_id, agent_id)
        state_json = state.model_dump_json()
        self._local_cache[key] = state_json
        if self._redis is not None:
            await self._redis.set(key, state_json, ex=86400)

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
        state_json = state.model_dump_json()
        self._local_cache[key] = state_json
        if self._redis is not None:
            try:
                await self._redis.set(key, state_json, ex=86400)
            except Exception as e:
                logger.warning(
                    "WorkingMemory.increment_iteration: Redis write failed",
                    error=str(e),
                )

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
        state_json = state.model_dump_json()
        self._local_cache[key] = state_json
        if self._redis is not None:
            try:
                await self._redis.set(key, state_json, ex=86400)
            except Exception as e:
                logger.warning(
                    "WorkingMemory.restore_from_json: Redis write failed", error=str(e)
                )
        else:
            logger.warning(
                "WorkingMemory.restore_from_json: Redis unavailable, using in-memory fallback"
            )

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

        Issue 4.1: Also removes the WAL file so working memory state
        (tasks, reasoning chains) does not persist indefinitely on disk.

        Args:
            session_id: Session UUID
            agent_id: Agent identifier
        """
        key = self._get_key(session_id, agent_id)

        # Clear from local cache first
        if key in self._local_cache:
            del self._local_cache[key]

        if self._redis is not None:
            try:
                await self._redis.delete(key)
            except Exception as e:
                logger.warning("WorkingMemory.clear: Redis delete failed", error=str(e))

        # Issue 4.1: Remove WAL file to prevent PII accumulation on disk
        try:
            wal_path = self._wal_dir / f"{key.replace(':', '_')}.json"
            wal_path.unlink(missing_ok=True)
        except (OSError, PermissionError) as e:
            logger.debug("WAL cleanup failed (disk/permissions)", error=str(e))
        except Exception as e:
            logger.debug("WAL cleanup failed (unexpected)", error=str(e))

        logger.info(
            "Cleared working memory",
            session_id=str(session_id),
            agent_id=agent_id,
        )


# Singleton instance — protected by a lock to prevent concurrent init races
_working_memory: WorkingMemory | None = None
_working_memory_lock: asyncio.Lock | None = None


def _get_working_memory_lock() -> asyncio.Lock:
    """Issue 4.3: Lazily create the lock inside a running event loop."""
    global _working_memory_lock
    if _working_memory_lock is None:
        _working_memory_lock = asyncio.Lock()
    return _working_memory_lock


async def get_working_memory() -> WorkingMemory:
    """
    Get or create the working memory singleton.

    Issue 4.3: Double-checked locking via asyncio.Lock prevents two concurrent
    coroutines from each creating their own WorkingMemory (and leaking a
    RedisClient connection pool).

    Returns:
        WorkingMemory instance
    """
    global _working_memory
    if _working_memory is not None:
        return _working_memory
    async with _get_working_memory_lock():
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
