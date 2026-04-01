"""
Investigation Queue — async worker pool for forensic investigations.

Instead of running investigations in the FastAPI event loop (which blocks
the uvicorn worker for 60+ seconds), investigations are submitted to an
async queue and processed by background workers.

This enables:
  - Multiple concurrent investigations without blocking the API
  - Configurable worker count based on available CPU/memory
  - Graceful shutdown with in-flight investigation draining
  - Status tracking for queued/running/completed investigations
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Optional
from uuid import UUID, uuid4

from core.structured_logging import get_logger

logger = get_logger(__name__)


class InvestigationStatus(str, Enum):
    """Status of a queued investigation."""
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class InvestigationTask:
    """A queued investigation task."""
    task_id: UUID
    session_id: UUID
    case_id: str
    investigator_id: str
    status: InvestigationStatus = InvestigationStatus.QUEUED
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    result: Any = None


class InvestigationQueue:
    """
    Async worker pool for processing forensic investigations.

    Workers pull tasks from an asyncio.Queue and execute them.
    The API layer submits tasks and returns immediately with a session_id.
    """

    def __init__(self, max_workers: int = 4, max_queue_size: int = 50):
        """
        Args:
            max_workers: Number of concurrent investigation workers
            max_queue_size: Maximum tasks before rejecting new submissions
        """
        self._max_workers = max_workers
        self._queue: asyncio.Queue[InvestigationTask] = asyncio.Queue(maxsize=max_queue_size)
        self._tasks: dict[UUID, InvestigationTask] = {}
        self._workers: list[asyncio.Task] = []
        self._running = False
        self._handler: Optional[Callable] = None

    def set_handler(self, handler: Callable[[UUID, str, str, str], Coroutine]) -> None:
        """Set the async handler that processes each investigation."""
        self._handler = handler

    async def start(self) -> None:
        """Start the worker pool."""
        if self._running:
            return
        self._running = True
        for i in range(self._max_workers):
            worker = asyncio.create_task(self._worker_loop(i))
            self._workers.append(worker)
        logger.info(f"Investigation queue started with {self._max_workers} workers")

    async def stop(self, drain_timeout: float = 30.0) -> None:
        """Stop the worker pool, waiting for in-flight tasks to complete."""
        self._running = False
        # Cancel idle workers
        for w in self._workers:
            w.cancel()
        # Wait for workers to finish
        if self._workers:
            await asyncio.wait(self._workers, timeout=drain_timeout)
        self._workers.clear()
        logger.info("Investigation queue stopped")

    async def submit(
        self,
        session_id: UUID,
        case_id: str,
        investigator_id: str,
    ) -> InvestigationTask:
        """
        Submit a new investigation to the queue.

        Returns the InvestigationTask immediately.
        Raises asyncio.QueueFull if the queue is at capacity.
        """
        task = InvestigationTask(
            task_id=uuid4(),
            session_id=session_id,
            case_id=case_id,
            investigator_id=investigator_id,
        )
        self._tasks[session_id] = task
        await self._queue.put(task)
        logger.info(
            f"Investigation queued",
            session_id=str(session_id),
            queue_size=self._queue.qsize(),
        )
        return task

    def get_status(self, session_id: UUID) -> Optional[InvestigationTask]:
        """Get the status of a queued/running investigation."""
        return self._tasks.get(session_id)

    def get_queue_stats(self) -> dict[str, Any]:
        """Return queue statistics."""
        statuses = {}
        for task in self._tasks.values():
            s = task.status.value
            statuses[s] = statuses.get(s, 0) + 1
        return {
            "queue_size": self._queue.qsize(),
            "max_workers": self._max_workers,
            "active_workers": sum(1 for w in self._workers if not w.done()),
            "total_tasks": len(self._tasks),
            "by_status": statuses,
        }

    async def _worker_loop(self, worker_id: int) -> None:
        """Worker loop that processes investigations from the queue."""
        logger.debug(f"Worker {worker_id} started")
        while self._running:
            try:
                task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            if self._handler is None:
                logger.error(f"Worker {worker_id}: No handler set, dropping task")
                task.status = InvestigationStatus.FAILED
                task.error = "No handler configured"
                continue

            task.status = InvestigationStatus.RUNNING
            task.started_at = time.time()
            logger.info(
                f"Worker {worker_id} processing investigation",
                session_id=str(task.session_id),
            )

            try:
                result = await self._handler(
                    task.session_id,
                    task.case_id,
                    task.investigator_id,
                )
                task.status = InvestigationStatus.COMPLETED
                task.result = result
                task.completed_at = time.time()
                elapsed = task.completed_at - task.started_at
                logger.info(
                    f"Worker {worker_id} completed investigation",
                    session_id=str(task.session_id),
                    elapsed_s=round(elapsed, 1),
                )
            except Exception as e:
                task.status = InvestigationStatus.FAILED
                task.error = str(e)
                task.completed_at = time.time()
                logger.error(
                    f"Worker {worker_id} investigation failed",
                    session_id=str(task.session_id),
                    error=str(e),
                )

        logger.debug(f"Worker {worker_id} stopped")


# Global singleton
_queue: Optional[InvestigationQueue] = None


def get_investigation_queue() -> InvestigationQueue:
    """Get or create the global investigation queue."""
    global _queue
    if _queue is None:
        import os
        max_workers = int(os.getenv("INVESTIGATION_WORKERS", "4"))
        _queue = InvestigationQueue(max_workers=max_workers)
    return _queue
