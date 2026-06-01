from __future__ import annotations

import os
from unittest.mock import AsyncMock
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

from agents.agent1_image import Agent1Image
from agents.agent2_audio import Agent2Audio
from agents.agent3_object import Agent3Object
from agents.agent4_video import Agent4Video
from agents.agent5_metadata import Agent5Metadata
from core.agent_registry import get_agent_registry
from core.config import Settings
from core.evidence import ArtifactType, EvidenceArtifact
from core.react_loop import ReActLoopEngine


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


def _agent(agent_cls, agent_id: str, path: str, mime_type: str):
    wm, em, cl, es = _deps()
    return agent_cls(
        agent_id=agent_id,
        session_id=uuid4(),
        evidence_artifact=_artifact(path, mime_type),
        config=_settings(),
        working_memory=wm,
        episodic_memory=em,
        custody_logger=cl,
        evidence_store=es,
    )


AGENTS = [
    (Agent1Image, "Agent1"),
    (Agent2Audio, "Agent2"),
    (Agent3Object, "Agent3"),
    (Agent4Video, "Agent4"),
    (Agent5Metadata, "Agent5"),
]


@pytest.mark.parametrize(
    ("path", "mime_type", "expected_agents"),
    [
        ("photo.jpg", "image/jpeg", {"Agent1", "Agent3", "Agent5"}),
        ("screenshot.png", "image/png", {"Agent1", "Agent3", "Agent5"}),
        ("audio.wav", "audio/wav", set()),
        ("video.mp4", "video/mp4", set()),
        ("audio.mp3", "audio/mpeg", set()),
        ("video.mov", "video/quicktime", set()),
    ],
)
def test_agent_file_type_support_matrix(path: str, mime_type: str, expected_agents: set[str]):
    active = {
        agent_id
        for agent_cls, agent_id in AGENTS
        if _agent(agent_cls, agent_id, path, mime_type).supports_uploaded_file
    }
    assert active == expected_agents


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "mime_type"),
    [
        ("photo.jpg", "image/jpeg"),
        ("screenshot.png", "image/png"),
        ("audio.wav", "audio/wav"),
        ("video.mp4", "video/mp4"),
        ("document.pdf", "application/pdf"),
        ("archive.zip", "application/zip"),
    ],
)
async def test_every_applicable_agent_task_maps_to_registered_tool(path: str, mime_type: str):
    failures: list[str] = []

    for agent_cls, agent_id in AGENTS:
        agent = _agent(agent_cls, agent_id, path, mime_type)
        if not agent.supports_uploaded_file:
            continue

        registry = await agent.build_tool_registry()
        tools = registry.list_tools()
        registered = {tool.name for tool in tools}
        for phase, tasks in (
            ("initial", agent.task_decomposition),
            ("deep", agent.deep_task_decomposition),
        ):
            for task in tasks:
                match = ReActLoopEngine._match_tool_to_task(task, tools)
                if match is None or match.name not in registered:
                    failures.append(f"{agent_id} {phase}: {task!r}")

    assert failures == []


def test_agent5_routes_non_visual_files_to_document_and_binary_tools_only():
    pdf_agent = _agent(Agent5Metadata, "Agent5", "document.pdf", "application/pdf")
    zip_agent = _agent(Agent5Metadata, "Agent5", "archive.zip", "application/zip")

    pdf_tasks = " ".join(pdf_agent.task_decomposition + pdf_agent.deep_task_decomposition)
    zip_tasks = " ".join(zip_agent.task_decomposition + zip_agent.deep_task_decomposition)

    assert "document text extraction" in pdf_tasks
    assert "document text extraction" not in zip_tasks

    camera_only_phrases = {
        "exif_extract",
        "exif_isolation_forest",
        "astro_grounding",
        "gps_timezone_validate",
        "camera_profile_match",
        "Hardware-Grounded Provenance",
    }
    for phrase in camera_only_phrases:
        assert phrase not in pdf_tasks
        assert phrase not in zip_tasks


def test_registry_contains_exactly_the_five_specialists_plus_arbiter_metadata():
    agent_ids = set(get_agent_registry().get_all_agent_ids())
    assert {"Agent1", "Agent2", "Agent3", "Agent4", "Agent5"} <= agent_ids
