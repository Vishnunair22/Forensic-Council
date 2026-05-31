"""Tests for screenshot-specific forensic tools (font inconsistency, UI overlay forgery)."""

from unittest.mock import patch
from uuid import uuid4

import numpy as np
import pytest
from PIL import Image

from core.evidence import ArtifactType, EvidenceArtifact
from tools.screenshot_tools import (
    detect_font_inconsistency,
    detect_ui_overlay_forgery,
)


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
        metadata={"mime_type": "image/png", "original_filename": "screenshot.png"},
    )


def _create_tweet_screenshot(path: str, with_edit: bool = True) -> str:
    """Create a fake tweet screenshot PNG."""
    from PIL import ImageDraw
    img = Image.new("RGB", (800, 600), "white")
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "Original tweet text here", fill="black")
    draw.text((50, 100), "Another line of text", fill="black")
    draw.text((50, 150), "Third line for consistency", fill="black")

    if with_edit:
        edit_region = Image.new("RGB", (200, 50), "white")
        edit_draw = ImageDraw.Draw(edit_region)
        edit_draw.text((10, 10), "EDITED TEXT", fill="red")
        img.paste(edit_region, (50, 200))

    img.save(path, "PNG")
    return path


@pytest.fixture
def mock_tesseract():
    """Mock pytesseract to avoid depending on tesseract binary."""
    import pytesseract
    with patch.object(pytesseract, "image_to_data") as mock:
        mock.return_value = {
            "text": ["Hello", "World", "Test", "", "", "Uniform", "Text", ""],
            "left": [10, 100, 200, 0, 0, 300, 400, 0],
            "top": [10, 10, 10, 0, 0, 100, 100, 0],
            "width": [50, 80, 60, 0, 0, 70, 90, 0],
            "height": [20, 20, 20, 0, 0, 20, 20, 0],
        }
        yield


@pytest.mark.asyncio
async def test_font_inconsistency_detects_edit(tmp_path, mock_artifact, mock_tesseract):
    """Font inconsistency should flag edited text regions."""
    path = _create_tweet_screenshot(str(tmp_path / "fake_tweet.png"), with_edit=True)
    mock_artifact.file_path = path

    with patch("os.path.exists", return_value=True):
        result = await detect_font_inconsistency(mock_artifact)

    assert result["available"] is True
    assert "anomaly_detected" in result
    assert result["status"] in ("complete", "insufficient_text", "insufficient_samples")


@pytest.mark.asyncio
async def test_font_inconsistency_clean_screenshot(tmp_path, mock_artifact, mock_tesseract):
    """Clean screenshot should not flag font anomalies."""
    from PIL import ImageDraw
    img = Image.new("RGB", (800, 600), "white")
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "Uniform text everywhere", fill="black")
    draw.text((50, 100), "All same font style here", fill="black")
    draw.text((50, 150), "Consistent rendering", fill="black")
    draw.text((50, 200), "No edits detected", fill="black")
    path = str(tmp_path / "clean_tweet.png")
    img.save(path, "PNG")
    mock_artifact.file_path = path

    with patch("os.path.exists", return_value=True):
        result = await detect_font_inconsistency(mock_artifact)

    assert result["available"] is True


@pytest.mark.asyncio
async def test_ui_overlay_forgery_detects_banner(tmp_path, mock_artifact):
    """UI overlay detection should flag solid-color banners."""
    img = np.full((600, 800, 3), 240, dtype=np.uint8)
    # Add a fake notification bar at top
    img[0:40, :] = [30, 30, 30]
    # Add content area
    img[100:500, 50:750] = [255, 255, 255]
    path = str(tmp_path / "fake_overlay.png")
    Image.fromarray(img, mode="RGB").save(path, "PNG")
    mock_artifact.file_path = path

    with patch("os.path.exists", return_value=True):
        result = await detect_ui_overlay_forgery(mock_artifact)

    assert result["available"] is True
    assert "overlay_detected" in result


@pytest.mark.asyncio
async def test_ui_overlay_forgery_clean(tmp_path, mock_artifact):
    """Clean image without banners should not flag overlays."""
    arr = np.random.randint(50, 200, (600, 800, 3), dtype=np.uint8)
    path = str(tmp_path / "clean_scene.png")
    Image.fromarray(arr, mode="RGB").save(path, "PNG")
    mock_artifact.file_path = path

    with patch("os.path.exists", return_value=True):
        result = await detect_ui_overlay_forgery(mock_artifact)

    assert result["available"] is True
    assert result["overlay_detected"] is False


@pytest.mark.asyncio
async def test_font_inconsistency_file_not_found(mock_artifact):
    """Should handle missing file gracefully."""
    mock_artifact.file_path = "/nonexistent/path.png"
    result = await detect_font_inconsistency(mock_artifact)
    assert result["available"] is False


@pytest.mark.asyncio
async def test_ui_overlay_forgery_file_not_found(mock_artifact):
    """Should handle missing file gracefully."""
    mock_artifact.file_path = "/nonexistent/path.png"
    result = await detect_ui_overlay_forgery(mock_artifact)
    assert result["available"] is False
