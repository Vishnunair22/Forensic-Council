from __future__ import annotations

import os
from unittest.mock import AsyncMock
from uuid import uuid4

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

from agents.agent3_object import Agent3Object
from core.config import Settings
from core.evidence import ArtifactType, EvidenceArtifact


def _settings() -> Settings:
    return Settings(
        app_env="testing",
        signing_key="test-signing-key-" + "x" * 32,
        postgres_user="test",
        postgres_password="test",
        postgres_db="test",
        redis_password="test",
        DEMO_PASSWORD="test",
        llm_provider="none",
        llm_api_key=None,
        llm_model="test-model",
        bootstrap_admin_password="Admin_123!",
        bootstrap_investigator_password="Inv_123!",
    )


def _artifact(path: str, mime_type: str) -> EvidenceArtifact:
    return EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=path,
        content_hash="hash123",
        action="upload",
        agent_id="system",
        session_id=uuid4(),
        metadata={"mime_type": mime_type},
    )


def _deps():
    wm = AsyncMock()
    em = AsyncMock()
    cl = AsyncMock()
    es = AsyncMock()
    return wm, em, cl, es


def _agent_for_mime(mime_type: str) -> Agent3Object:
    wm, em, cl, es = _deps()
    return Agent3Object(
        agent_id="Agent3",
        session_id=uuid4(),
        evidence_artifact=_artifact("/tmp/test_vid.mp4", mime_type),
        config=_settings(),
        working_memory=wm,
        episodic_memory=em,
        custody_logger=cl,
        evidence_store=es,
    )


class TestAgent3ObjectTaskDecomposition:
    def test_video_task_includes_frame_extraction(self):
        agent = _agent_for_mime("video/mp4")
        tasks = agent.task_decomposition
        assert "Run frame_extraction for video frame sampling and scene segmentation" in tasks

    def test_video_task_first_is_frame_extraction(self):
        agent = _agent_for_mime("video/mp4")
        tasks = agent.task_decomposition
        assert tasks[0].startswith("Run frame_extraction")

    def test_video_task_has_scene_tools_after_frame_extraction(self):
        agent = _agent_for_mime("video/mp4")
        tasks = agent.task_decomposition
        assert any("object_detection" in t for t in tasks)
        assert any("scene_incongruence" in t for t in tasks)

    def test_image_task_does_not_include_frame_extraction(self):
        agent = _agent_for_mime("image/jpeg")
        tasks = agent.task_decomposition
        assert not any("frame_extraction" in t for t in tasks)

    def test_screen_capture_task_unchanged(self):
        agent = _agent_for_mime("image/png")
        agent._is_screen_capture = True
        tasks = agent.task_decomposition
        assert any("screenshot_scene_applicability" in t for t in tasks)
        assert not any("frame_extraction" in t for t in tasks)

    def test_video_task_count_is_reasonable(self):
        agent = _agent_for_mime("video/mp4")
        tasks = agent.task_decomposition
        assert 3 <= len(tasks) <= 10
