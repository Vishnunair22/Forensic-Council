"""
Unit tests for orchestration/investigation_queue.py.

Covers:
- InvestigationStatus enum
- InvestigationTask model
- InvestigationQueue.submit()
- InvestigationQueue.get_status()
- InvestigationQueue.update_task()
- InvestigationWorker.start() / stop()
- get_investigation_queue() singleton
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

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

from orchestration.investigation_queue import (
    InvestigationQueue,
    InvestigationStatus,
    InvestigationTask,
    InvestigationWorker,
    get_investigation_queue,
)


def _make_redis_mock():
    redis = AsyncMock()
    redis.hset = AsyncMock()
    redis.hdel = AsyncMock()
    redis.hget = AsyncMock(return_value=None)
    redis.exists = AsyncMock(return_value=True)
    redis.set = AsyncMock()

    pipe = MagicMock()
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock(return_value=None)
    pipe.hset = MagicMock()
    pipe.rpush = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = AsyncMock(return_value=[])

    pipeline_mock = MagicMock()
    pipeline_mock.return_value = pipe

    redis.client = MagicMock()
    redis.client.pipeline = pipeline_mock
    redis.client.rpush = AsyncMock()
    redis.client.blpop = AsyncMock(return_value=None)
    return redis


# ── InvestigationStatus ────────────────────────────────────────────────────────


class TestInvestigationStatus:
    def test_all_values(self):
        vals = {s.value for s in InvestigationStatus}
        assert "QUEUED" in vals
        assert "RUNNING" in vals
        assert "COMPLETED" in vals
        assert "FAILED" in vals
        assert "CANCELLED" in vals


# ── InvestigationTask model ────────────────────────────────────────────────────


class TestInvestigationTask:
    def test_creation_defaults(self):
        task = InvestigationTask(
            session_id=uuid4(),
            case_id="CASE001",
            investigator_id="inv1",
            evidence_file_path="/tmp/evidence.jpg",
        )
        assert task.status == InvestigationStatus.QUEUED
        assert task.task_id is not None
        assert task.started_at is None
        assert task.error is None

    def test_to_dict(self):
        task = InvestigationTask(
            session_id=uuid4(),
            case_id="CASE001",
            investigator_id="inv1",
            evidence_file_path="/tmp/evidence.jpg",
            original_filename="evidence.jpg",
        )
        d = task.to_dict()
        assert d["case_id"] == "CASE001"
        assert d["status"] == "QUEUED"

    def test_from_dict_roundtrip(self):
        task = InvestigationTask(
            session_id=uuid4(),
            case_id="CASE002",
            investigator_id="inv2",
            evidence_file_path="/tmp/file.mp4",
        )
        restored = InvestigationTask.from_dict(task.to_dict())
        assert restored.case_id == "CASE002"
        assert restored.status == InvestigationStatus.QUEUED


# ── InvestigationQueue ─────────────────────────────────────────────────────────


class TestInvestigationQueue:
    def _make_queue_with_redis(self):
        redis = _make_redis_mock()
        queue = InvestigationQueue()
        queue._redis = redis
        return queue, redis

    @pytest.mark.asyncio
    async def test_submit_creates_task(self):
        queue, redis = self._make_queue_with_redis()
        sid = uuid4()
        task = await queue.submit(
            session_id=sid,
            case_id="CASE001",
            investigator_id="inv1",
            evidence_file_path="/tmp/file.jpg",
        )
        assert isinstance(task, InvestigationTask)
        assert task.case_id == "CASE001"
        pipe = redis.client.pipeline()
        pipe.hset.assert_called_once()
        pipe.rpush.assert_called_once()
        pipe.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_cleans_up_on_push_failure(self):
        queue, redis = self._make_queue_with_redis()
        pipe = redis.client.pipeline()
        pipe.execute = AsyncMock(side_effect=RuntimeError("Redis down"))
        sid = uuid4()
        with pytest.raises(RuntimeError):
            await queue.submit(
                session_id=sid,
                case_id="CASE001",
                investigator_id="inv1",
                evidence_file_path="/tmp/file.jpg",
            )
        redis.hdel.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_with_original_filename(self):
        queue, redis = self._make_queue_with_redis()
        sid = uuid4()
        task = await queue.submit(
            session_id=sid,
            case_id="CASE003",
            investigator_id="inv3",
            evidence_file_path="/tmp/evidence.jpg",
            original_filename="original_photo.jpg",
        )
        assert task.original_filename == "original_photo.jpg"

    @pytest.mark.asyncio
    async def test_get_status_returns_none_when_missing(self):
        queue, redis = self._make_queue_with_redis()
        redis.hget = AsyncMock(return_value=None)
        result = await queue.get_status(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_get_status_returns_task_when_present(self):
        queue, redis = self._make_queue_with_redis()
        sid = uuid4()
        task = InvestigationTask(
            session_id=sid,
            case_id="CASE001",
            investigator_id="inv1",
            evidence_file_path="/tmp/file.jpg",
        )
        redis.hget = AsyncMock(return_value=task.to_dict())
        result = await queue.get_status(sid)
        assert result is not None
        assert result.case_id == "CASE001"

    @pytest.mark.asyncio
    async def test_update_task_stores_metadata(self):
        queue, redis = self._make_queue_with_redis()
        sid = uuid4()
        task = InvestigationTask(
            session_id=sid,
            case_id="CASE001",
            investigator_id="inv1",
            evidence_file_path="/tmp/file.jpg",
            status=InvestigationStatus.RUNNING,
        )
        await queue.update_task(task)
        redis.hset.assert_called()

    @pytest.mark.asyncio
    async def test_get_redis_initializes_lazily(self):
        queue = InvestigationQueue()
        mock_redis = _make_redis_mock()
        with patch(
            "orchestration.investigation_queue.get_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            result = await queue._get_redis()
        assert result is mock_redis


# ── InvestigationWorker ────────────────────────────────────────────────────────


class TestInvestigationWorker:
    def test_set_handler(self):
        queue = InvestigationQueue()
        worker = InvestigationWorker(queue, worker_id=0)
        handler = AsyncMock()
        worker.set_handler(handler)
        assert worker._handler is handler

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self):
        queue = InvestigationQueue()
        worker = InvestigationWorker(queue)
        worker._running = True
        await worker.stop()
        assert worker._running is False

    @pytest.mark.asyncio
    async def test_start_breaks_on_cancelled_error(self):
        redis = _make_redis_mock()
        redis.client.blpop = AsyncMock(side_effect=asyncio.CancelledError())
        queue = InvestigationQueue()
        queue._redis = redis
        worker = InvestigationWorker(queue, worker_id=1)
        handler = AsyncMock(return_value={"status": "done"})
        worker.set_handler(handler)
        # Should exit cleanly on CancelledError
        await worker.start()
        assert worker._running is False

    @pytest.mark.asyncio
    async def test_start_processes_task_successfully(self):
        redis = _make_redis_mock()
        sid = uuid4()
        task = InvestigationTask(
            session_id=sid,
            case_id="CASE001",
            investigator_id="inv1",
            evidence_file_path="/tmp/file.jpg",
        )
        # blpop returns task_id, then CancelledError to stop
        redis.client.blpop = AsyncMock(
            side_effect=[
                (None, str(sid)),
                asyncio.CancelledError(),
            ]
        )
        redis.hget = AsyncMock(return_value=task.to_dict())
        redis.hset = AsyncMock()

        queue = InvestigationQueue()
        queue._redis = redis

        result_mock = MagicMock()
        result_mock.model_dump = MagicMock(return_value={"status": "ok"})
        handler = AsyncMock(return_value=result_mock)

        worker = InvestigationWorker(queue, worker_id=2)
        worker.set_handler(handler)
        await worker.start()
        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_handles_missing_task_metadata(self):
        redis = _make_redis_mock()
        sid = uuid4()
        # blpop returns session_id, but hget returns None (no metadata)
        redis.client.blpop = AsyncMock(
            side_effect=[
                (None, str(sid)),
                asyncio.CancelledError(),
            ]
        )
        redis.hget = AsyncMock(return_value=None)

        queue = InvestigationQueue()
        queue._redis = redis
        worker = InvestigationWorker(queue, worker_id=3)
        worker.set_handler(AsyncMock())
        await worker.start()  # Should handle gracefully

    @pytest.mark.asyncio
    async def test_start_handles_no_handler_set(self):
        redis = _make_redis_mock()
        sid = uuid4()
        task = InvestigationTask(
            session_id=sid,
            case_id="CASE001",
            investigator_id="inv1",
            evidence_file_path="/tmp/file.jpg",
        )
        redis.client.blpop = AsyncMock(
            side_effect=[
                (None, str(sid)),
                asyncio.CancelledError(),
            ]
        )
        redis.hget = AsyncMock(return_value=task.to_dict())
        redis.hset = AsyncMock()

        queue = InvestigationQueue()
        queue._redis = redis
        worker = InvestigationWorker(queue, worker_id=4)
        # No handler set
        await worker.start()
        # Task should be marked FAILED
        redis.hset.assert_called()

    @pytest.mark.asyncio
    async def test_start_handles_handler_exception(self):
        redis = _make_redis_mock()
        sid = uuid4()
        task = InvestigationTask(
            session_id=sid,
            case_id="CASE001",
            investigator_id="inv1",
            evidence_file_path="/tmp/file.jpg",
        )
        redis.client.blpop = AsyncMock(
            side_effect=[
                (None, str(sid)),
                asyncio.CancelledError(),
            ]
        )
        redis.hget = AsyncMock(return_value=task.to_dict())
        redis.hset = AsyncMock()

        queue = InvestigationQueue()
        queue._redis = redis
        worker = InvestigationWorker(queue, worker_id=5)
        worker.set_handler(AsyncMock(side_effect=RuntimeError("handler crashed")))
        await worker.start()
        # Task should be marked FAILED
        redis.hset.assert_called()

    @pytest.mark.asyncio
    async def test_start_times_out_stuck_handler(self):
        redis = _make_redis_mock()
        sid = uuid4()
        task = InvestigationTask(
            session_id=sid,
            case_id="CASE001",
            investigator_id="inv1",
            evidence_file_path="/tmp/file.jpg",
        )
        redis.client.blpop = AsyncMock(
            side_effect=[
                (None, str(sid)),
                asyncio.CancelledError(),
            ]
        )
        redis.hget = AsyncMock(return_value=task.to_dict())
        redis.hset = AsyncMock()

        queue = InvestigationQueue()
        queue._redis = redis

        async def stuck_handler(**kwargs):
            await asyncio.sleep(1)

        worker = InvestigationWorker(queue, worker_id=7)
        worker._task_timeout_seconds = lambda: 0.01
        worker.set_handler(stuck_handler)

        await worker.start()

        import json
        final_task_str = redis.hset.call_args_list[-1].args[2]
        final_task = json.loads(final_task_str)
        assert final_task["status"] == "FAILED"
        assert "timed out" in final_task["error"]

    @pytest.mark.asyncio
    async def test_start_blpop_timeout_continues_loop(self):
        """blpop returning None (timeout) should continue the loop."""
        redis = _make_redis_mock()
        # First call returns None (timeout), second raises CancelledError
        redis.client.blpop = AsyncMock(side_effect=[None, asyncio.CancelledError()])
        queue = InvestigationQueue()
        queue._redis = redis
        worker = InvestigationWorker(queue, worker_id=6)
        worker.set_handler(AsyncMock())
        await worker.start()


# ── Singleton ─────────────────────────────────────────────────────────────────


class TestGetInvestigationQueue:
    def test_returns_same_instance(self):
        import orchestration.investigation_queue as iq_mod

        iq_mod._queue = None  # Reset singleton
        q1 = get_investigation_queue()
        q2 = get_investigation_queue()
        assert q1 is q2

    def test_returns_investigation_queue_instance(self):
        import orchestration.investigation_queue as iq_mod

        iq_mod._queue = None
        q = get_investigation_queue()
        assert isinstance(q, InvestigationQueue)


# ── Phase 2.15: Worker heartbeat ────────────────────────────────────────────────


class TestWorkerHeartbeat:
    @pytest.mark.asyncio
    async def test_worker_start_writes_heartbeat(self):
        """InvestigationWorker.start() writes forensic:worker:heartbeat."""
        redis = _make_redis_mock()

        async def mock_blpop(*args, **kwargs):
            await asyncio.sleep(0.01)
            raise asyncio.CancelledError()
        redis.client.blpop = mock_blpop

        heartbeat_written = False
        original_set = redis.set

        def mock_set(key, value, ex=None):
            nonlocal heartbeat_written
            if "heartbeat" in key:
                heartbeat_written = True
            return original_set(key, value, ex)

        redis.set = mock_set
        queue = InvestigationQueue()
        queue._redis = redis
        worker = InvestigationWorker(queue, worker_id=99)
        worker.set_handler(AsyncMock())

        await worker.start()

        assert heartbeat_written, "Worker.start() should write forensic:worker:heartbeat"

    @pytest.mark.asyncio
    async def test_worker_heartbeat_key_format(self):
        """Heartbeat key follows the expected naming convention."""
        redis = _make_redis_mock()

        async def mock_blpop(*args, **kwargs):
            await asyncio.sleep(0.01)
            raise asyncio.CancelledError()
        redis.client.blpop = mock_blpop

        keys_written: list = []

        def capture_set(key, value, ex=None):
            keys_written.append(key)
            return AsyncMock()(key, value, ex)

        redis.set = capture_set
        queue = InvestigationQueue()
        queue._redis = redis
        worker = InvestigationWorker(queue, worker_id=42)
        worker.set_handler(AsyncMock())

        await worker.start()

        heartbeat_keys = [k for k in keys_written if "heartbeat" in k]
        assert len(heartbeat_keys) > 0, "At least one heartbeat key should be written"
        assert any("forensic:worker:heartbeat" in k for k in heartbeat_keys)
