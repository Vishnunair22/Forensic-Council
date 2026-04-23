import io
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import UploadFile

from api.routes import investigation as investigation_routes
from orchestration import investigation_runner


@pytest.mark.asyncio
async def test_start_investigation_continues_when_queue_handoff_fails(monkeypatch):
    file_obj = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9")
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

    monkeypatch.setattr(
        investigation_routes, "check_investigation_rate_limit", AsyncMock()
    )
    monkeypatch.setattr(
        investigation_routes, "check_daily_cost_quota", AsyncMock()
    )
    monkeypatch.setattr(
        investigation_routes, "ForensicCouncilPipeline", lambda: DummyPipeline()
    )
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
    monkeypatch.setattr(investigation_runner, "get_session_websockets", lambda _sid: [])
    monkeypatch.setattr(investigation_runner, "broadcast_update", AsyncMock())
    monkeypatch.setattr(investigation_runner, "set_final_report", AsyncMock())
    monkeypatch.setattr(investigation_runner, "set_active_pipeline_metadata", AsyncMock())
    monkeypatch.setattr(investigation_runner, "increment_investigations_completed", lambda: None)
    monkeypatch.setattr(investigation_runner, "increment_investigations_failed", lambda: None)
    monkeypatch.setattr(investigation_runner.os.path, "exists", lambda _path: False)

    fake_persistence = SimpleNamespace(
        save_report=AsyncMock(return_value=True),
        update_session_status=AsyncMock(return_value=True),
    )

    async def fake_get_session_persistence():
        return fake_persistence

    monkeypatch.setattr(
        "core.session_persistence.get_session_persistence",
        fake_get_session_persistence,
    )

    await investigation_routes.run_investigation_task(
        session_id="11111111-1111-1111-1111-111111111111",
        pipeline=pipeline,
        evidence_file_path="fake-file.jpg",
        case_id="CASE-1234567890",
        investigator_id="REQ-12345",
        original_filename="fake-file.jpg",
    )

    investigation_runner.set_final_report.assert_awaited_once()


