import asyncio
import time
from collections.abc import Callable
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from core.persistence.redis_client import get_redis_client
from core.structured_logging import get_logger

logger = get_logger(__name__)


class InvestigationStatus(StrEnum):
    """Status of a queued investigation."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


from pydantic import BaseModel, Field


class InvestigationTask(BaseModel):
    """A queued investigation task."""

    task_id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    case_id: str
    investigator_id: str
    evidence_file_path: str
    original_filename: str | None = None
    status: InvestigationStatus = InvestigationStatus.QUEUED
    created_at: float = Field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    error: str | None = None
    result: Any = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InvestigationTask":
        """Create from dictionary (JSON deserialization)."""
        return cls.model_validate(data)


class InvestigationQueue:
    """
    Redis-backed worker pool for processing forensic investigations.

    Tasks are stored in a Redis list ('forensic:investigation:queue') and
    task metadata is stored in a Redis hash ('forensic:investigation:tasks').
    """

    QUEUE_KEY = "forensic:investigation:queue"
    METADATA_KEY = "forensic:investigation:tasks"

    def __init__(self):
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            self._redis = await get_redis_client()
        return self._redis

    async def submit(
        self,
        session_id: UUID,
        case_id: str,
        investigator_id: str,
        evidence_file_path: str,
        original_filename: str | None = None,
    ) -> InvestigationTask:
        """
        Submit a new investigation to the Redis queue.
        """
        redis = await self._get_redis()
        task = InvestigationTask(
            session_id=session_id,
            case_id=case_id,
            investigator_id=investigator_id,
            evidence_file_path=evidence_file_path,
            original_filename=original_filename,
        )

        try:
            # Store metadata
            await redis.hset(self.METADATA_KEY, str(session_id), task.model_dump_json())
            # Push to queue
            await redis.client.rpush(self.QUEUE_KEY, str(session_id))
        except Exception as e:
            logger.error("Failed to submit investigation to Redis", session_id=str(session_id), error=str(e))
            # Attempt to clean up metadata if queue push failed
            await redis.hdel(self.METADATA_KEY, str(session_id))
            raise

        logger.info(
            "Investigation queued in Redis",
            session_id=str(session_id),
            case_id=case_id,
        )
        return task

    async def get_status(self, session_id: UUID) -> InvestigationTask | None:
        """Get the status of an investigation from Redis."""
        redis = await self._get_redis()
        data = await redis.hget(self.METADATA_KEY, str(session_id))
        if data:
            return InvestigationTask.from_dict(data)
        return None

    async def update_task(self, task: InvestigationTask) -> None:
        """Update task metadata in Redis."""
        redis = await self._get_redis()
        await redis.hset(self.METADATA_KEY, str(task.session_id), task.to_dict())


class InvestigationWorker:
    """
    Background worker that consumes tasks from Redis and runs the pipeline.
    """

    def __init__(self, queue: InvestigationQueue, worker_id: int = 0):
        self.queue = queue
        self.worker_id = worker_id
        self._running = False
        self._handler: Callable | None = None

    def set_handler(self, handler: Callable) -> None:
        """Set the async handler that processes each task."""
        self._handler = handler

    async def start(self) -> None:
        """Start the worker loop."""
        self._running = True
        redis = await self.queue._get_redis()
        logger.info(f"Worker {self.worker_id} started, waiting for tasks...")

        while self._running:
            try:
                # BLPOP blocks until a task is available (timeout 5s)
                result = await redis.client.blpop(InvestigationQueue.QUEUE_KEY, timeout=5)
                if not result:
                    continue

                _, session_id_str = result
                session_id = UUID(session_id_str)

                task = await self.queue.get_status(session_id)
                if not task:
                    logger.error(f"Worker {self.worker_id}: Task {session_id} metadata missing")
                    continue

                if self._handler is None:
                    logger.error(f"Worker {self.worker_id}: No handler set")
                    task.status = InvestigationStatus.FAILED
                    task.error = "No worker handler configured"
                    await self.queue.update_task(task)
                    continue

                task.status = InvestigationStatus.RUNNING
                task.started_at = time.time()
                await self.queue.update_task(task)

                logger.info(
                    f"Worker {self.worker_id} processing task",
                    session_id=str(session_id),
                )

                try:
                    # Execute the investigation
                    # The handler is expected to be ForensicCouncilPipeline.run_investigation or a wrapper
                    result = await self._handler(
                        evidence_file_path=task.evidence_file_path,
                        case_id=task.case_id,
                        investigator_id=task.investigator_id,
                        original_filename=task.original_filename,
                        session_id=task.session_id,
                    )

                    task.status = InvestigationStatus.COMPLETED
                    task.result = result.model_dump() if hasattr(result, "model_dump") else result
                    task.completed_at = time.time()
                except Exception as e:
                    task.status = InvestigationStatus.FAILED
                    task.error = str(e)
                    task.completed_at = time.time()
                    logger.error(
                        f"Worker {self.worker_id} task failed",
                        session_id=str(session_id),
                        error=str(e),
                        exc_info=True,
                    )

                await self.queue.update_task(task)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {self.worker_id} loop error", error=str(e))
                await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop the worker loop."""
        self._running = False
        logger.info(f"Worker {self.worker_id} stopping...")


# Global singleton
_queue: InvestigationQueue | None = None


def get_investigation_queue() -> InvestigationQueue:
    """Get the global investigation queue singleton."""
    global _queue
    if _queue is None:
        _queue = InvestigationQueue()
    return _queue
