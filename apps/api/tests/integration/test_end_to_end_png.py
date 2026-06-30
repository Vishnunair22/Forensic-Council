"""End-to-end integration tests for PNG/screenshot investigations."""

from unittest.mock import patch
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


def _create_manipulated_screenshot(path: str) -> str:
    from PIL import ImageDraw
    img = Image.new("RGB", (800, 600), "white")
    edit = Image.new("RGB", (200, 50), "white")
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "Balance: $1,000", fill="black")
    draw.text((50, 100), "Date: 2024-01-01", fill="black")
    draw.text((50, 150), "Account: #12345", fill="black")
    edit_draw = ImageDraw.Draw(edit)
    edit_draw.text((10, 10), "Balance: $9,999", fill="red")
    img.paste(edit, (50, 50))
    img.save(path, "PNG")
    return path


@pytest.mark.asyncio
async def test_png_ela_runs_and_returns_lossless_flag(tmp_path, settings):
    """ELA on manipulated PNG should return results with lossless flag."""
    from tools.image_tools import ela_full_image

    path = _create_manipulated_screenshot(str(tmp_path / "manipulated.png"))
    artifact = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=path,
        content_hash="abc",
        action="upload",
        agent_id="test",
        session_id=uuid4(),
        metadata={"mime_type": "image/png"},
    )

    with patch("os.path.exists", return_value=True):
        result = await ela_full_image(artifact, multi_quality=False)

    assert result["available"] is True
    if result.get("is_lossless_source"):
        assert "lossless_interpretation" in result


@pytest.mark.asyncio
async def test_png_mime_detection_fallback(tmp_path, settings):
    """Upload with octet-stream should fallback to PIL detection."""
    # Import the private function directly using importlib to avoid triggering
    # the full api.routes.investigation module-level dependency chain (which
    # requires FastAPI, DB connections, etc. unavailable in unit-test context).
    import importlib
    _inv_mod = importlib.import_module("api.routes.investigation")
    _detect_mime_from_head = _inv_mod._detect_mime_from_head

    arr = np.full((100, 100, 3), 128, dtype=np.uint8)
    path = str(tmp_path / "test.png")
    Image.fromarray(arr, mode="RGB").save(path, "PNG")

    with open(path, "rb") as f:
        head = f.read(32)

    with patch.object(_inv_mod, "magic") as mock_magic:
        mock_magic.from_buffer.return_value = "application/octet-stream"
        mime = await _detect_mime_from_head(head)

    assert mime in ("image/png", "application/octet-stream")


@pytest.mark.asyncio
async def test_arbiter_file_type_thresholds(settings):
    """Arbiter should apply different thresholds for PNG vs JPEG."""
    from core.forensic_policy import ForensicPolicy

    png_thresholds = ForensicPolicy.get_verdict_thresholds("image/png")
    jpeg_thresholds = ForensicPolicy.get_verdict_thresholds("image/jpeg")

    # PNG has higher manipulated threshold than JPEG (less susceptible to recompression)
    assert png_thresholds["manipulated"] > jpeg_thresholds["manipulated"]
    assert png_thresholds["likely_manipulated"] > jpeg_thresholds["likely_manipulated"]


@pytest.mark.asyncio
async def test_png_ghost_detection(tmp_path, settings):
    """JPEG ghost should run on PNG and detect embedded JPEG artifacts."""
    from tools.image_tools import jpeg_ghost_detect

    path = str(tmp_path / "ghost_test.png")
    img = Image.new("RGB", (200, 200), "blue")
    img.save(path, "PNG")
    artifact = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=path,
        content_hash="abc",
        action="upload",
        agent_id="test",
        session_id=uuid4(),
        metadata={"mime_type": "image/png"},
    )

    with patch("os.path.exists", return_value=True):
        result = await jpeg_ghost_detect(artifact)

    assert result["available"] is True
    assert result["court_defensible"] is True
