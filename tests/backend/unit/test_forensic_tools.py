import pytest
from unittest.mock import MagicMock, patch
import numpy as np
from PIL import Image
from backend.tools.image_tools import (
    ela_full_image,
    roi_extract,
    jpeg_ghost_detect,
    compute_perceptual_hash,
    BoundingBox
)
from backend.core.evidence import EvidenceArtifact
from uuid import uuid4

@pytest.fixture
def mock_artifact():
    return EvidenceArtifact(
        artifact_id=uuid4(),
        file_path="mock_image.jpg",
        original_filename="mock_image.jpg",
        mime_type="image/jpeg",
        file_size=1024,
        sha256_hash="abc",
        content_hash="abc",
        metadata={}
    )

def test_bounding_box_to_dict():
    bbox = BoundingBox(x=10, y=20, w=30, h=40)
    expected = {"x": 10, "y": 20, "w": 30, "h": 40}
    assert bbox.to_dict() == expected

@pytest.mark.asyncio
@patch("os.path.exists", return_value=True)
@patch("PIL.Image.open")
async def test_ela_full_image_lossy(mock_open, mock_exists, mock_artifact):
    # Mock PIL Image
    img_mock = MagicMock()
    img_mock.format = "JPEG"
    img_mock.mode = "RGB"
    img_mock.size = (100, 100)
    img_mock.copy.return_value = img_mock
    img_mock.convert.return_value = img_mock
    mock_open.return_value.__enter__.return_value = img_mock

    # Mock numpy array
    with patch("numpy.array", return_value=np.zeros((100, 100, 3))):
        result = await ela_full_image(mock_artifact, multi_quality=False)
        
    assert result["available"] is True
    assert "mean_ela" in result
    assert result["court_defensible"] is True

@pytest.mark.asyncio
@patch("os.path.exists", return_value=True)
@patch("PIL.Image.open")
async def test_ela_full_image_lossless(mock_open, mock_exists, mock_artifact):
    # Change artifact to PNG
    mock_artifact.mime_type = "image/png"
    
    img_mock = MagicMock()
    img_mock.format = "PNG"
    mock_open.return_value.__enter__.return_value = img_mock

    result = await ela_full_image(mock_artifact)
    
    assert result["ela_not_applicable"] is True
    assert "limitation_note" in result

@pytest.mark.asyncio
@patch("os.path.exists", return_value=True)
@patch("PIL.Image.open")
async def test_roi_extract_logic(mock_open, mock_exists, mock_artifact):
    img_mock = MagicMock()
    img_mock.mode = "RGB"
    img_mock.size = (1000, 1000)
    mock_open.return_value.__enter__.return_value = img_mock
    
    bbox = {"x": 100, "y": 100, "w": 200, "h": 200}
    
    with patch("backend.core.evidence.EvidenceArtifact.create_derivative", return_value=MagicMock()):
        result = await roi_extract(mock_artifact, bbox)
    
    assert result["dimensions"] == {"width": 200, "height": 200}
    img_mock.crop.assert_called_once()

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
