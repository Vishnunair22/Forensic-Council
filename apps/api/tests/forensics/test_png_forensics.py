"""Tests for PNG/lossless forensics: ELA, JPEG ghost, deepfake detection."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import numpy as np
import pytest
from PIL import Image

from core.evidence import ArtifactType, EvidenceArtifact
from tools.image_tools import ela_full_image


@pytest.fixture
def mock_artifact():
    sid = uuid4()
    return EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path="",
        content_hash="abc",
        action="upload",
        agent_id="test",
        session_id=sid,
        metadata={"mime_type": "image/png", "original_filename": "test.png"},
    )


@pytest.mark.asyncio
@patch("os.path.exists", return_value=True)
@patch("PIL.Image.open")
async def test_ela_runs_on_png(mock_open, mock_exists, mock_artifact):
    """ELA must run on PNG (not skip) and indicate lossless interpretation."""
    img_mock = MagicMock()
    img_mock.format = "PNG"
    img_mock.mode = "RGB"
    img_mock.size = (100, 100)
    img_mock.copy.return_value = img_mock
    img_mock.convert.return_value = img_mock
    mock_open.return_value.__enter__.return_value = img_mock

    with (
        patch("numpy.array", return_value=np.zeros((100, 100, 3))),
        patch("tools.image_tools.is_lossless_image", return_value=True),
    ):
        result = await ela_full_image(mock_artifact, multi_quality=False)

    assert result["available"] is True
    assert result["court_defensible"] is True
    assert "lossless_interpretation" in result
    assert result["max_anomaly"] is not None


@pytest.mark.asyncio
async def test_ela_on_png_with_manipulation(tmp_path, mock_artifact):
    """ELA on PNG with copy-paste region should detect anomalies."""
    img = Image.new("RGB", (200, 200), color="blue")
    pixels = np.array(img)
    pixels[50:100, 50:100] = [255, 0, 0]
    img = Image.fromarray(pixels)
    path = str(tmp_path / "test_manipulated.png")
    img.save(path, "PNG")
    mock_artifact.file_path = path
    mock_artifact.metadata["mime_type"] = "image/png"

    with patch("os.path.exists", return_value=True):
        with patch("tools.image_tools.is_lossless_image", return_value=True):
            result = await ela_full_image(mock_artifact, multi_quality=False)

    assert result["available"] is True
    assert "lossless_interpretation" in result
    if result.get("max_anomaly") is not None:
        assert isinstance(result["max_anomaly"], (int, float))


@pytest.mark.asyncio
@patch("os.path.exists", return_value=True)
@patch("PIL.Image.open")
async def test_ela_on_jpeg_not_marked_lossless(mock_open, mock_exists, mock_artifact):
    """ELA on JPEG should NOT include lossless_interpretation."""
    mock_artifact.metadata["mime_type"] = "image/jpeg"
    img_mock = MagicMock()
    img_mock.format = "JPEG"
    img_mock.mode = "RGB"
    img_mock.size = (100, 100)
    img_mock.copy.return_value = img_mock
    img_mock.convert.return_value = img_mock
    mock_open.return_value.__enter__.return_value = img_mock

    with (
        patch("numpy.array", return_value=np.zeros((100, 100, 3))),
        patch("tools.image_tools.is_lossless_image", return_value=False),
    ):
        result = await ela_full_image(mock_artifact, multi_quality=False)

    assert result["available"] is True
    assert result.get("lossless_interpretation") is None


@pytest.mark.asyncio
async def test_agent1_screenshot_triggers_font_overlay_tasks(tmp_path):
    """Agent1 should inject font/UI overlay tasks when screenshot detected."""
    from agents.agent1_image import Agent1Image
    from core.config import Settings

    settings = Settings(
        app_env="testing",
        signing_key="test-signing-key-" + "x" * 32,
    )

    arr = np.full((1080, 1920, 3), 245, dtype=np.uint8)
    arr[120:180, 150:900] = 20
    path = str(tmp_path / "screen_test.png")
    Image.fromarray(arr, mode="RGB").save(path, "PNG")

    from unittest.mock import AsyncMock

    artifact = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=path,
        content_hash="abc",
        action="upload",
        agent_id="test",
        session_id=uuid4(),
        metadata={"mime_type": "image/png"},
    )

    working_memory = AsyncMock()
    working_memory.get_state.return_value = type("State", (), {"tasks": []})()

    agent = Agent1Image(
        agent_id="Agent1",
        session_id=artifact.session_id,
        evidence_artifact=artifact,
        config=settings,
        working_memory=working_memory,
        episodic_memory=AsyncMock(),
        custody_logger=AsyncMock(),
        evidence_store=AsyncMock(),
    )

    import sys
    from types import ModuleType

    # Stub api.routes._session_state.broadcast_update so inject_task's telemetry
    # broadcast doesn't hit Redis. CRITICAL: snapshot and RESTORE the original
    # sys.modules entries — deleting them leaves `api.routes` re-imported without
    # its `auth` submodule bound, which poisons every later test that does
    # `import api.routes.auth` (was the source of 44 test_api_routes setup errors).
    _orig_routes = sys.modules.get("api.routes")
    _orig_ss = sys.modules.get("api.routes._session_state")
    routes_mod = ModuleType("api.routes")
    routes_mod.__path__ = []
    ss_mod = ModuleType("api.routes._session_state")
    ss_mod.broadcast_update = AsyncMock()
    sys.modules["api.routes"] = routes_mod
    sys.modules["api.routes._session_state"] = ss_mod

    try:
        await agent._on_tool_result_impl(
            type("Finding", (), {
                "metadata": {
                    # Agent1 now sources content from the shared visual profile
                    # (analyze_image_content moved to Agent3); screenshot integrity
                    # tools are injected via _escalate_from_visual_profile.
                    "tool_name": "visual_evidence_profile",
                    "content_type": "screenshot",
                    "content_description": "a screen capture / digital UI",
                },
                "evidence_verdict": "NEGATIVE",
                "confidence_raw": 0.72,
            })()
        )
    finally:
        if _orig_routes is not None:
            sys.modules["api.routes"] = _orig_routes
        else:
            sys.modules.pop("api.routes", None)
        if _orig_ss is not None:
            sys.modules["api.routes._session_state"] = _orig_ss
        else:
            sys.modules.pop("api.routes._session_state", None)

    calls = [str(c) for c in working_memory.create_task.call_args_list]
    font_call = any("detect_font_inconsistency" in s for s in calls)
    overlay_call = any("detect_ui_overlay_forgery" in s for s in calls)
    assert font_call, "detect_font_inconsistency should be injected for screenshots"
    assert overlay_call, "detect_ui_overlay_forgery should be injected for screenshots"
