import asyncio
import os
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
    detected_mime: str | None = None
    validated_extension: str | None = None
    content_sha256: str | None = None
    file_size_bytes: int | None = None
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
    WORKER_HEARTBEAT_KEY = "forensic:worker:heartbeat"
    WORKER_HEARTBEAT_TTL = 30

    def __init__(self):
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            self._redis = await get_redis_client()
        return self._redis

    async def _mark_session_failed(self, task: InvestigationTask, error: str) -> None:
        try:
            from api.routes._session_state import (
                broadcast_update,
                update_active_pipeline_metadata,
            )
            from api.schemas import BriefUpdate

            session_id = str(task.session_id)
            # F-15: use atomic CAS instead of non-atomic RMW
            await update_active_pipeline_metadata(
                session_id,
                {
                    "status": "error",
                    "brief": error,
                    "error": error,
                    "completed_at": time.time(),
                },
            )
            await broadcast_update(
                session_id,
                BriefUpdate(
                    type="ERROR",
                    session_id=session_id,
                    message="Investigation failed.",
                    data={"error": error, "status": "error"},
                ),
            )
        except Exception as exc:
            logger.warning(
                "Failed to mark session failed after worker error",
                session_id=str(task.session_id),
                error=str(exc),
            )
        try:
            from core.session_persistence import get_session_persistence

            persistence = await get_session_persistence()
            await persistence.update_session_status(str(task.session_id), "error", error)
        except Exception as exc:
            logger.warning(
                "Failed to persist worker failure",
                session_id=str(task.session_id),
                error=str(exc),
            )

    async def submit(
        self,
        session_id: UUID,
        case_id: str,
        investigator_id: str,
        evidence_file_path: str,
        original_filename: str | None = None,
        detected_mime: str | None = None,
        validated_extension: str | None = None,
        content_sha256: str | None = None,
        file_size_bytes: int | None = None,
    ) -> InvestigationTask:
        """Submit a new investigation to the Redis queue."""
        redis = await self._get_redis()
        task = InvestigationTask(
            session_id=session_id,
            case_id=case_id,
            investigator_id=investigator_id,
            evidence_file_path=evidence_file_path,
            original_filename=original_filename,
            detected_mime=detected_mime,
            validated_extension=validated_extension,
            content_sha256=content_sha256,
            file_size_bytes=file_size_bytes,
        )

        try:
            # D-C-1: cap unbounded growth of the task hash and queue list.
            # Without these EXPIREs, abandoned/crashed sessions accumulate
            # forever and Redis ultimately hits maxmemory. 24 h covers the
            # longest legitimate investigation lifecycle.
            async with redis.client.pipeline(transaction=True) as pipe:
                pipe.hset(self.METADATA_KEY, str(session_id), task.model_dump_json())
                pipe.rpush(self.QUEUE_KEY, str(session_id))
                pipe.expire(self.METADATA_KEY, 86400)
                pipe.expire(self.QUEUE_KEY, 86400)
                await pipe.execute()
        except Exception as e:
            logger.error(
                "Failed to submit investigation to Redis",
                session_id=str(session_id),
                error=str(e),
            )
            await redis.hdel(self.METADATA_KEY, str(session_id))
            raise

        logger.info(
            "Investigation queued in Redis",
            session_id=str(session_id),
            case_id=case_id,
        )
        return task

    async def is_worker_alive(self) -> bool:
        """Return True if a worker has written a heartbeat within the last 30 seconds."""
        redis = await self._get_redis()
        return bool(await redis.exists(self.WORKER_HEARTBEAT_KEY))

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
        await redis.hset(self.METADATA_KEY, str(task.session_id), task.model_dump_json())


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

    def _task_timeout_seconds(self) -> float:
        # Default to investigation_timeout + 120s buffer so workers are not
        # killed before investigations can complete. WORKER_TASK_TIMEOUT_SECONDS
        # env var overrides this for fine-grained control.
        from core.config import get_settings as _gs
        _default = float(getattr(_gs(), "investigation_timeout", 2400)) + 120.0
        raw = os.environ.get("WORKER_TASK_TIMEOUT_SECONDS", str(int(_default)))
        try:
            timeout = float(raw)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid WORKER_TASK_TIMEOUT_SECONDS; using default",
                value=raw,
                default_seconds=_default,
            )
            return _default
        return max(30.0, timeout)

    def _concurrency(self) -> int:
        raw = os.environ.get("WORKER_CONCURRENCY", "2")
        try:
            concurrency = int(raw)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid WORKER_CONCURRENCY; using default",
                value=raw,
                default=2,
            )
            return 2
        return max(1, concurrency)

    async def _write_heartbeat(self) -> None:
        redis = await self.queue._get_redis()
        await redis.set(
            InvestigationQueue.WORKER_HEARTBEAT_KEY,
            str(time.time()),
            ex=InvestigationQueue.WORKER_HEARTBEAT_TTL,
        )

    async def _heartbeat_loop(self) -> None:
        """Keep worker liveness fresh while long investigations are running."""
        interval = max(1, InvestigationQueue.WORKER_HEARTBEAT_TTL // 3)
        try:
            await self._write_heartbeat()  # write immediately on start
        except Exception as e:
            logger.warning(
                f"Worker {self.worker_id} initial heartbeat failed",
                error=str(e),
            )
        while self._running:
            await asyncio.sleep(interval)
            if not self._running:
                break
            try:
                await self._write_heartbeat()
            except Exception as e:
                logger.warning(
                    f"Worker {self.worker_id} heartbeat refresh failed",
                    error=str(e),
                )

    async def start(self) -> None:
        """Start the worker loop."""
        self._running = True
        redis = await self.queue._get_redis()
        concurrency = self._concurrency()
        logger.info(
            f"Worker {self.worker_id} started, waiting for tasks...",
            concurrency=concurrency,
        )
        heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        active_tasks: set[asyncio.Task] = set()

        async def process_task(task: InvestigationTask) -> None:
            try:
                if self._handler is None:
                    logger.error(f"Worker {self.worker_id}: No handler set")
                    task.status = InvestigationStatus.FAILED
                    task.error = "No worker handler configured"
                    await self.queue.update_task(task)
                    return

                task.status = InvestigationStatus.RUNNING
                task.started_at = time.time()
                await self.queue.update_task(task)

                logger.info(
                    f"Worker {self.worker_id} processing task",
                    session_id=str(task.session_id),
                )

                try:
                    timeout_seconds = self._task_timeout_seconds()
                    result = await asyncio.wait_for(
                        self._handler(
                            evidence_file_path=task.evidence_file_path,
                            case_id=task.case_id,
                            investigator_id=task.investigator_id,
                            original_filename=task.original_filename,
                            session_id=task.session_id,
                            detected_mime=task.detected_mime,
                            validated_extension=task.validated_extension,
                            content_sha256=task.content_sha256,
                            file_size_bytes=task.file_size_bytes,
                        ),
                        timeout=timeout_seconds,
                    )

                    task.status = InvestigationStatus.COMPLETED
                    task.result = (
                        result.model_dump(mode="json")
                        if hasattr(result, "model_dump")
                        else result
                    )
                    task.completed_at = time.time()
                except TimeoutError:
                    task.status = InvestigationStatus.FAILED
                    task.error = (
                        f"Investigation worker timed out after "
                        f"{self._task_timeout_seconds():.0f}s"
                    )
                    task.completed_at = time.time()
                    logger.error(
                        f"Worker {self.worker_id} task timed out",
                        session_id=str(task.session_id),
                        timeout_seconds=self._task_timeout_seconds(),
                    )
                    await self.queue._mark_session_failed(task, task.error)
                    try:
                        from api.routes._session_state import broadcast_update
                        from api.schemas import BriefUpdate
                        await broadcast_update(
                            str(task.session_id),
                            BriefUpdate(
                                type="ERROR",
                                session_id=str(task.session_id),
                                message=f"Investigation timed out after {timeout_seconds:.0f}s",
                                data={"status": "error", "error": "timeout"},
                            ),
                        )
                    except Exception as _broadcast_err:
                        logger.debug("Timeout error broadcast failed", error=str(_broadcast_err))
                except Exception as e:
                    task.status = InvestigationStatus.FAILED
                    task.error = str(e)
                    task.completed_at = time.time()
                    logger.error(
                        f"Worker {self.worker_id} task failed",
                        session_id=str(task.session_id),
                        error=str(e),
                        exc_info=True,
                    )
                    await self.queue._mark_session_failed(task, task.error)

                await self.queue.update_task(task)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(
                    f"Worker {self.worker_id} task bookkeeping failed",
                    session_id=str(task.session_id),
                    error=str(e),
                    exc_info=True,
                )

        try:
            while self._running:
                try:
                    active_tasks = {t for t in active_tasks if not t.done()}
                    if len(active_tasks) >= concurrency:
                        done, pending = await asyncio.wait(
                            active_tasks,
                            timeout=1,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        for done_task in done:
                            try:
                                await done_task
                            except Exception as e:
                                logger.error(
                                    f"Worker {self.worker_id} background task crashed",
                                    error=str(e),
                                    exc_info=True,
                                )
                        active_tasks = set(pending)
                        continue

                    # BLPOP blocks until a task is available (timeout 1s)
                    result = await redis.client.blpop(InvestigationQueue.QUEUE_KEY, timeout=1)
                    if not result:
                        continue

                    _, session_id_str = result
                    session_id = UUID(session_id_str)

                    task = await self.queue.get_status(session_id)
                    if not task:
                        logger.error(f"Worker {self.worker_id}: Task {session_id} metadata missing")
                        continue

                    bg_task = asyncio.create_task(process_task(task))
                    active_tasks.add(bg_task)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Worker {self.worker_id} loop error", error=str(e))
                    await asyncio.sleep(1)
        finally:
            self._running = False
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            if active_tasks:
                await asyncio.gather(*active_tasks, return_exceptions=True)

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
