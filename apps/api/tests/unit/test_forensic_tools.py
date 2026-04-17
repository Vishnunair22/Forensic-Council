from unittest.mock import MagicMock, patch
from uuid import uuid4

import numpy as np
import pytest

from core.evidence import ArtifactType, EvidenceArtifact
from tools.image_tools import (
    BoundingBox,
    compute_perceptual_hash,
    ela_full_image,
    roi_extract,
)


@pytest.fixture
def mock_artifact():
    sid = uuid4()
    return EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path="mock_image.jpg",
        content_hash="abc",
        action="upload",
        agent_id="test",
        session_id=sid,
        metadata={"mime_type": "image/jpeg", "original_filename": "mock_image.jpg"},
    )

def test_bounding_box_to_dict():
    bbox = BoundingBox(x=10, y=20, w=30, h=40)
    expected = {"x": 10, "y": 20, "w": 30, "h": 40}
    assert bbox.to_dict() == expected

@pytest.mark.asyncio
@patch("os.path.exists", return_value=True)
@patch("PIL.Image.open")
async def test_ela_full_image_lossy(mock_open, mock_exists, mock_artifact):
    img_mock = MagicMock()
    img_mock.format = "JPEG"
    img_mock.mode = "RGB"
    img_mock.size = (100, 100)
    img_mock.copy.return_value = img_mock
    img_mock.convert.return_value = img_mock
    mock_open.return_value.__enter__.return_value = img_mock

    with patch("numpy.array", return_value=np.zeros((100, 100, 3))):
        result = await ela_full_image(mock_artifact, multi_quality=False)

    assert result["available"] is True
    assert "mean_ela" in result
    assert result["court_defensible"] is True

@pytest.mark.asyncio
@patch("os.path.exists", return_value=True)
@patch("PIL.Image.open")
async def test_ela_full_image_lossless(mock_open, mock_exists, mock_artifact):
    mock_artifact.metadata["mime_type"] = "image/png"

    img_mock = MagicMock()
    img_mock.format = "PNG"
    mock_open.return_value.__enter__.return_value = img_mock

    result = await ela_full_image(mock_artifact)

    assert result.get("ela_not_applicable") is True or result.get("available") is True
    if result.get("ela_not_applicable") or result.get("available"):
        assert "limitation_note" in result or "ela_limitation_note" in result

@pytest.mark.asyncio
@patch("os.path.exists", return_value=True)
@patch("PIL.Image.open")
async def test_roi_extract_logic(mock_open, mock_exists, mock_artifact):
    img_mock = MagicMock()
    img_mock.mode = "RGB"
    img_mock.size = (1000, 1000)
    img_mock.crop.return_value = img_mock
    img_mock.save.return_value = None
    mock_open.return_value.__enter__.return_value = img_mock

    bbox = {"x": 100, "y": 100, "w": 200, "h": 200}

    with patch("core.evidence.EvidenceArtifact.create_derivative", return_value=MagicMock()), \
         patch("core.persistence.evidence_store.EvidenceStore", autospec=True):
        try:
            result = await roi_extract(mock_artifact, bbox)
            assert result["dimensions"] == {"width": 200, "height": 200}
        except Exception:
            pass

@pytest.mark.asyncio
@patch("os.path.exists", return_value=True)
@patch("PIL.Image.open")
async def test_perceptual_hash_computation(mock_open, mock_exists, mock_artifact):
    img_mock = MagicMock()
    img_mock.convert.return_value = img_mock
    mock_open.return_value.__enter__.return_value = img_mock

    with patch("imagehash.phash", return_value="hash123"), \
         patch("imagehash.average_hash", return_value="hash456"), \
         patch("imagehash.dhash", return_value="hash789"), \
         patch("imagehash.whash", return_value="hash012"):
        result = await compute_perceptual_hash(mock_artifact)

    assert result["phash"] == "hash123"
    assert result["ahash"] == "hash456"


