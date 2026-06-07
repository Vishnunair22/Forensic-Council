"""Tests for weapon detection priority in CLIP and object detection pipeline."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import numpy as np
import pytest
from PIL import Image

from core.evidence import ArtifactType, EvidenceArtifact
from tools.clip_utils import CLIPImageAnalyzer


@pytest.fixture
def mock_artifact():
    sid = uuid4()
    return EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path="test_weapon.jpg",
        content_hash="abc",
        action="upload",
        agent_id="test",
        session_id=sid,
        metadata={"mime_type": "image/jpeg"},
    )


def test_clip_weapon_categories_prioritized():
    """Weapon categories must appear first in DEFAULT_IMAGE_CATEGORIES."""
    categories = CLIPImageAnalyzer.DEFAULT_IMAGE_CATEGORIES
    first_category = categories[0].lower()

    assert any(kw in first_category for kw in ("weapon", "knife", "gun", "firearm")), (
        f"Weapon category not first. First: {first_category}"
    )


def test_clip_concern_categories_include_weapons():
    """CONCERN_CATEGORIES must include weapon-related terms."""
    concern = " ".join(CLIPImageAnalyzer.CONCERN_CATEGORIES).lower()
    for term in ("firearm", "knife", "blade", "weapon"):
        assert term in concern, f"CONCERN_CATEGORIES missing '{term}'"


@pytest.mark.asyncio
async def test_agent3_weapon_detection_triggers_scale_validation(tmp_path):
    """When YOLO detects a weapon, scale validation should be triggered."""
    from agents.agent3_object import Agent3Object
    from core.config import Settings

    settings = Settings(
        app_env="testing",
        signing_key="test-signing-key-" + "x" * 32,
    )

    arr = np.full((480, 640, 3), 120, dtype=np.uint8)
    path = str(tmp_path / "knife_test.jpg")
    Image.fromarray(arr, mode="RGB").save(path, "JPEG")

    artifact = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=path,
        content_hash="abc",
        action="upload",
        agent_id="test",
        session_id=uuid4(),
        metadata={"mime_type": "image/jpeg"},
    )

    agent = Agent3Object(
        agent_id="Agent3",
        session_id=artifact.session_id,
        evidence_artifact=artifact,
        config=settings,
        working_memory=AsyncMock(),
        episodic_memory=AsyncMock(),
        custody_logger=AsyncMock(),
        evidence_store=AsyncMock(),
    )

    tasks = agent.task_decomposition
    task_names = " ".join(t.lower() for t in tasks)
    assert "scale_validation" in task_names or "vector_contraband" in task_names


@pytest.mark.asyncio
async def test_agent1_weapon_content_triggers_crime_scene_signal(tmp_path):
    """When CLIP detects weapon content, agent1 should signal crime_scene_detected."""
    from agents.agent1_image import Agent1Image
    from core.config import Settings

    settings = Settings(
        app_env="testing",
        signing_key="test-signing-key-" + "x" * 32,
    )

    arr = np.full((480, 640, 3), 120, dtype=np.uint8)
    path = str(tmp_path / "weapon_scene.jpg")
    Image.fromarray(arr, mode="RGB").save(path, "JPEG")

    artifact = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=path,
        content_hash="abc",
        action="upload",
        agent_id="test",
        session_id=uuid4(),
        metadata={"mime_type": "image/jpeg"},
    )

    inter_agent_bus = MagicMock()
    agent = Agent1Image(
        agent_id="Agent1",
        session_id=artifact.session_id,
        evidence_artifact=artifact,
        config=settings,
        working_memory=AsyncMock(),
        episodic_memory=AsyncMock(),
        custody_logger=AsyncMock(),
        evidence_store=AsyncMock(),
        inter_agent_bus=inter_agent_bus,
    )

    # Agent1 now sources content from the shared visual profile (CLIP/content
    # classification belongs to Agent3); crime-scene content is routed via
    # _escalate_from_visual_profile, which emits a crime_scene_detected bus signal.
    result = agent._on_tool_result_impl(
        type("Finding", (), {
            "metadata": {
                "tool_name": "visual_evidence_profile",
                "content_description": "a photograph of a weapon or knife at a crime scene",
            },
            "evidence_verdict": "POSITIVE",
            "confidence_raw": 0.85,
        })()
    )
    await result
    assert inter_agent_bus.signal_event.called
    assert any(
        "crime_scene_detected" in str(c) for c in inter_agent_bus.signal_event.call_args_list
    )
