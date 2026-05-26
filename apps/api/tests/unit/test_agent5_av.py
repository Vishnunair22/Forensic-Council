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

from agents.agent5_metadata import Agent5Metadata
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


def _agent_for_mime(mime_type: str) -> Agent5Metadata:
    wm, em, cl, es = _deps()
    return Agent5Metadata(
        agent_id="Agent5",
        session_id=uuid4(),
        evidence_artifact=_artifact("/tmp/test_file", mime_type),
        config=_settings(),
        working_memory=wm,
        episodic_memory=em,
        custody_logger=cl,
        evidence_store=es,
    )


class TestAgent5AVBranch:
    def test_av_media_includes_file_hash_verify(self):
        agent = _agent_for_mime("video/mp4")
        tasks = agent.task_decomposition
        assert any("file_hash_verify" in t for t in tasks)

    def test_av_media_excludes_compression_risk_audit(self):
        agent = _agent_for_mime("video/mp4")
        tasks = agent.task_decomposition
        assert not any("compression_risk_audit" in t for t in tasks)

    def test_av_media_includes_av_file_identity(self):
        agent = _agent_for_mime("video/mp4")
        tasks = agent.task_decomposition
        assert any("av_file_identity" in t for t in tasks)

    def test_av_media_includes_mediainfo_profile(self):
        agent = _agent_for_mime("video/mp4")
        tasks = agent.task_decomposition
        assert any("mediainfo_profile" in t for t in tasks)

    def test_audio_media_excludes_compression_risk_audit(self):
        agent = _agent_for_mime("audio/wav")
        tasks = agent.task_decomposition
        assert not any("compression_risk_audit" in t for t in tasks)

    def test_image_media_still_includes_compression_risk_audit(self):
        agent = _agent_for_mime("image/jpeg")
        tasks = agent.task_decomposition
        assert any("compression_risk_audit" in t for t in tasks)

    def test_av_task_count_is_reasonable(self):
        agent = _agent_for_mime("video/mp4")
        tasks = agent.task_decomposition
        assert 3 <= len(tasks) <= 10
