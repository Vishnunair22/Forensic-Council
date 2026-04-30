import os
from unittest.mock import AsyncMock
from uuid import uuid4

import numpy as np
from PIL import Image

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_PASSWORD", "test")
os.environ.setdefault("NEXT_PUBLIC_DEMO_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")

from agents.agent1_image import Agent1Image
from agents.agent3_object import Agent3Object
from agents.agent5_metadata import Agent5Metadata
from core.config import Settings
from core.evidence import ArtifactType, EvidenceArtifact
from core.media_kind import is_screen_capture_like


def _settings() -> Settings:
    return Settings(
        app_env="testing",
        signing_key="test-signing-key-" + "x" * 32,
        postgres_user="test",
        postgres_password="test",
        postgres_db="test",
        redis_password="test",
        next_public_demo_password="test",
        llm_provider="none",
        llm_api_key=None,
        llm_model="test-model",
        bootstrap_admin_password="Admin_123!",
        bootstrap_investigator_password="Inv_123!",
    )


def _artifact(path: str, mime_type: str = "image/png") -> EvidenceArtifact:
    return EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=path,
        content_hash="abc123",
        action="upload",
        agent_id="system",
        session_id=uuid4(),
        metadata={"mime_type": mime_type},
    )


def _agent(cls, agent_id: str, artifact: EvidenceArtifact):
    return cls(
        agent_id=agent_id,
        session_id=artifact.session_id,
        evidence_artifact=artifact,
        config=_settings(),
        working_memory=AsyncMock(),
        episodic_memory=AsyncMock(),
        custody_logger=AsyncMock(),
        evidence_store=AsyncMock(),
    )


def _save_screen_png(path) -> None:
    arr = np.full((1080, 1920, 3), 245, dtype=np.uint8)
    arr[120:180, 150:900] = 20
    Image.fromarray(arr, mode="RGB").save(path, format="PNG")


def test_screen_capture_like_png_is_detected(tmp_path):
    path = tmp_path / "screen.png"
    _save_screen_png(path)
    assert is_screen_capture_like(_artifact(str(path))) is True


def test_agent1_uses_short_screen_capture_initial_plan(tmp_path):
    path = tmp_path / "screen.png"
    _save_screen_png(path)
    agent = _agent(Agent1Image, "Agent1", _artifact(str(path)))

    tasks = agent.task_decomposition

    assert "Run extract_text_from_image for visible text extraction" in tasks
    assert all("noiseprint" not in t.lower() for t in tasks)
    assert all("neural_fingerprint" not in t.lower() for t in tasks)


def test_agent3_skips_physical_scene_tools_for_screen_capture(tmp_path):
    path = tmp_path / "screen.png"
    _save_screen_png(path)
    agent = _agent(Agent3Object, "Agent3", _artifact(str(path)))

    assert agent.task_decomposition == [
        "Run screenshot_scene_applicability for screen-capture object/scene scope",
    ]
    # Now has deep tasks for screen captures instead of empty
    assert len(agent.deep_task_decomposition) == 2


def test_agent5_omits_camera_provenance_tools_for_screen_capture(tmp_path):
    path = tmp_path / "screen.png"
    _save_screen_png(path)
    agent = _agent(Agent5Metadata, "Agent5", _artifact(str(path)))

    tasks = " ".join(agent.task_decomposition).lower()

    assert "gps_timezone" not in tasks
    assert "astro_grounding" not in tasks
    assert "exif_isolation_forest" not in tasks
    assert agent.deep_task_decomposition == []
