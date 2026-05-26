import io
import tempfile
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from api.routes import investigation as investigation_routes
from orchestration import investigation_runner


@pytest.mark.asyncio
async def test_start_investigation_continues_when_queue_handoff_fails(monkeypatch):
    file_obj = io.BytesIO(
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
    )
    upload = UploadFile(filename="evidence.jpg", file=file_obj)
    upload.size = len(file_obj.getvalue())
    upload.headers = {"content-type": "image/jpeg"}

    created_tasks = []
    active_pipelines = []
    active_task_handles = []
    metadata_updates = []

    class DummyQueue:
        async def submit(self, **kwargs):
            raise RuntimeError("redis queue unavailable")

    class DummyPipeline:
        pass

    def fake_create_task(coro):
        created_tasks.append(coro)
        coro.close()
        return SimpleNamespace(name="fake-task")

    monkeypatch.setattr(investigation_routes, "check_investigation_rate_limit", AsyncMock())
    monkeypatch.setattr(investigation_routes, "check_daily_cost_quota", AsyncMock())
    monkeypatch.setattr(investigation_routes, "ForensicCouncilPipeline", lambda: DummyPipeline())
    monkeypatch.setattr(
        investigation_routes,
        "set_active_pipeline",
        lambda session_id, pipeline: active_pipelines.append((session_id, pipeline)),
    )
    monkeypatch.setattr(
        investigation_routes,
        "set_active_task",
        lambda session_id, task: active_task_handles.append((session_id, task)),
    )

    async def fake_set_active_pipeline_metadata(session_id, metadata):
        metadata_updates.append((session_id, metadata))

    monkeypatch.setattr(
        investigation_routes,
        "set_active_pipeline_metadata",
        fake_set_active_pipeline_metadata,
    )
    monkeypatch.setattr(investigation_routes.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(
        "orchestration.investigation_queue.get_investigation_queue",
        lambda: DummyQueue(),
    )

    class FakeMagic:
        @staticmethod
        def from_buffer(_head, mime=True):
            return "image/jpeg"

    monkeypatch.setitem(__import__("sys").modules, "magic", FakeMagic)

    class FakeImage:
        size = (10, 10)

        def verify(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("PIL.Image.open", lambda *_args, **_kwargs: FakeImage())

    user = SimpleNamespace(user_id="tester", role=SimpleNamespace(value="investigator"))

    response = await investigation_routes.start_investigation(
        file=upload,
        case_id="CASE-1234567890",
        investigator_id="REQ-12345",
        current_user=user,
    )

    assert response.status == "started"
    assert response.message.startswith("Investigation started for")
    assert active_pipelines
    assert active_task_handles
    assert created_tasks, "expected local background tasks to be scheduled"
    assert metadata_updates
    assert metadata_updates[-1][1]["status"] == "running"
    assert metadata_updates[-1][1]["brief"] == "Initializing forensic pipeline..."


@pytest.mark.asyncio
async def test_run_investigation_task_awaits_final_report_cache(monkeypatch):
    report = SimpleNamespace(
        report_id="report-123",
        model_dump=lambda mode="json": {"report_id": "report-123"},
    )
    pipeline = SimpleNamespace(_final_report=None, _error=None)

    monkeypatch.setattr(
        investigation_runner, "_wrap_pipeline_with_broadcasts", AsyncMock(return_value=report)
    )

    monkeypatch.setattr(
        "orchestration.session_finalization.set_final_report", AsyncMock()
    )
    monkeypatch.setattr(
        "orchestration.session_finalization.set_active_pipeline_metadata", AsyncMock()
    )
    monkeypatch.setattr(
        "orchestration.session_finalization.increment_investigations_completed", lambda: None
    )
    monkeypatch.setattr(
        "orchestration.session_finalization.broadcast_update", AsyncMock()
    )

    monkeypatch.setattr(Path, "unlink", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(investigation_runner, "remove_active_pipeline", lambda _sid: None)
    monkeypatch.setattr(investigation_runner, "clear_session_websockets", lambda _sid: None)
    monkeypatch.setattr(investigation_runner, "_active_tasks", {})

    fake_persistence = SimpleNamespace(
        save_report=AsyncMock(return_value=True),
        update_session_status=AsyncMock(return_value=True),
    )

    async def fake_get_session_persistence():
        return fake_persistence

    monkeypatch.setattr(
        "orchestration.session_finalization.get_session_persistence", fake_get_session_persistence
    )

    await investigation_routes.run_investigation_task(
        session_id="11111111-1111-1111-1111-111111111111",
        pipeline=pipeline,
        evidence_file_path="fake-file.jpg",
        case_id="CASE-1234567890",
        investigator_id="REQ-12345",
        original_filename="fake-file.jpg",
    )


@pytest.mark.asyncio
async def test_start_investigation_returns_503_when_redis_dedup_fails(monkeypatch):
    """be-G-1: if Redis is unavailable during dedup check, return 503 and clean up the tmp file."""
    import hashlib

    file_obj = io.BytesIO(
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
    )
    upload = UploadFile(filename="evidence.jpg", file=file_obj)
    upload.size = len(file_obj.getvalue())
    upload.headers = {"content-type": "image/jpeg"}

    unlinked_paths: list[str] = []

    original_unlink = Path.unlink

    def fake_unlink(self, missing_ok=False):
        unlinked_paths.append(str(self))

    monkeypatch.setattr(Path, "unlink", fake_unlink)
    monkeypatch.setattr(investigation_routes, "check_investigation_rate_limit", AsyncMock())
    monkeypatch.setattr(investigation_routes, "check_daily_cost_quota", AsyncMock())

    class FakeMagic:
        @staticmethod
        def from_buffer(_head, mime=True):
            return "image/jpeg"

    monkeypatch.setitem(__import__("sys").modules, "magic", FakeMagic)

    class FakeImage:
        size = (10, 10)

        def verify(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("PIL.Image.open", lambda *_args, **_kwargs: FakeImage())

    async def redis_raises():
        raise ConnectionError("Redis is down")

    monkeypatch.setattr(
        "core.persistence.redis_client.get_redis_client",
        redis_raises,
    )

    user = SimpleNamespace(user_id="tester", role=SimpleNamespace(value="investigator"))

    with pytest.raises(HTTPException) as exc_info:
        await investigation_routes.start_investigation(
            file=upload,
            case_id="CASE-9999999999",
            investigator_id="REQ-99999",
            current_user=user,
        )

    assert exc_info.value.status_code == 503, (
        "Redis dedup failure must return 503, not fall through silently"
    )
    assert unlinked_paths, "Tmp file must be unlinked when Redis dedup raises"
