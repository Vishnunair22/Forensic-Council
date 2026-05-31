"""End-to-end integration tests for weapon detection pipeline."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import numpy as np
import pytest
from PIL import Image

from core.config import Settings
from core.evidence import ArtifactType, EvidenceArtifact


@pytest.fixture
def settings():
    return Settings(
        app_env="testing",
        signing_key="test-signing-key-" + "x" * 32,
    )


def _create_weapon_image(path: str) -> str:
    arr = np.full((480, 640, 3), 100, dtype=np.uint8)
    blade = np.full((20, 100, 3), [200, 200, 200], dtype=np.uint8)
    arr[200:220, 270:370] = blade
    Image.fromarray(arr, mode="RGB").save(path, "JPEG")
    return path


@pytest.mark.asyncio
async def test_clip_weapon_category_first(settings):
    """Weapon categories must be first in the CLIP priority list."""
    from tools.clip_utils import CLIPImageAnalyzer

    cats = CLIPImageAnalyzer.DEFAULT_IMAGE_CATEGORIES
    first_three = " ".join(cats[:3]).lower()
    for kw in ("weapon", "knife", "gun", "firearm"):
        if kw in first_three:
            return
    pytest.fail(f"No weapon keyword found in first 3 CLIP categories: {first_three}")


@pytest.mark.asyncio
async def test_agent3_weapon_in_deep_tasks(tmp_path, settings):
    """Agent3 deep tasks should include weapon-related analysis."""
    from agents.agent3_object import Agent3Object

    path = _create_weapon_image(str(tmp_path / "weapon.jpg"))
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

    deep_tasks = " ".join(agent.deep_task_decomposition).lower()
    assert any(kw in deep_tasks for kw in ("scale_validation", "lighting_consistency", "vector_contraband"))


@pytest.mark.asyncio
async def test_evidence_store_preserves_extension(tmp_path, settings):
    """Evidence store should preserve file extension on ingest."""
    from core.persistence.evidence_store import EvidenceStore
    from core.persistence.storage import LocalStorageBackend

    path = _create_weapon_image(str(tmp_path / "knife_evidence.jpg"))
    storage = LocalStorageBackend(str(tmp_path / "evidence_root"))

    with patch("core.persistence.evidence_store.get_postgres_client") as mock_pg:
        mock_client = AsyncMock()
        mock_pg.return_value = mock_client

        async with EvidenceStore(storage_backend=storage) as store:
            artifact = await store.ingest(
                file_path=path,
                session_id=uuid4(),
                agent_id="test",
                metadata={"mime_type": "image/jpeg", "original_filename": "knife_evidence.jpg"},
            )

    stored_path = artifact.file_path
    assert stored_path.endswith(".jpg") or stored_path.endswith(".jpeg"), (
        f"Stored path should preserve .jpg extension: {stored_path}"
    )


@pytest.mark.asyncio
async def test_copy_move_detector_handles_large_image(tmp_path):
    """Copy-move detector should handle (or gracefully refuse) large images."""
    from tools.ml_tools.copy_move_detector import detect_copy_move

    huge = Image.new("RGB", (8000, 6000), "blue")
    path = str(tmp_path / "huge_test.jpg")
    huge.save(path, "JPEG", quality=85)

    with patch("cv2.imread") as mock_imread:
        mock_imread.return_value = np.full((6000, 8000, 3), 255, dtype=np.uint8)
        result = detect_copy_move(path)

    assert isinstance(result, dict)
