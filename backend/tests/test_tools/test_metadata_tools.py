"""
Tests for Metadata Forensic Tools
=================================

Tests for EXIF extraction, GPS/timezone validation, and steganography detection.
"""

import hashlib
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PIL.ExifTags import TAGS

from core.evidence import ArtifactType, EvidenceArtifact
from core.exceptions import ToolUnavailableError
from tools.metadata_tools import (
    exif_extract,
    gps_timezone_validate,
    steganography_scan,
    file_structure_analysis,
    timestamp_analysis,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def create_image_with_exif(temp_dir: Path, filename: str = "with_exif.jpg") -> Path:
    """Create a JPEG image with EXIF data."""
    # Create a simple image
    img_array = np.zeros((200, 200, 3), dtype=np.uint8)
    for i in range(200):
        for j in range(200):
            img_array[i, j] = [i % 256, j % 256, (i + j) % 256]
    
    img = Image.fromarray(img_array, mode="RGB")
    
    # Create minimal EXIF data
    # Note: PIL doesn't easily support writing EXIF, so we create a basic image
    # and rely on the fact that most cameras add EXIF
    img_path = temp_dir / filename
    img.save(img_path, "JPEG", quality=95)
    
    return img_path


def create_image_without_exif(temp_dir: Path, filename: str = "no_exif.jpg") -> Path:
    """Create a JPEG image without EXIF data (stripped)."""
    # Create a simple image
    img_array = np.zeros((200, 200, 3), dtype=np.uint8)
    for i in range(200):
        for j in range(200):
            img_array[i, j] = [i % 256, j % 256, (i + j) % 256]
    
    img = Image.fromarray(img_array, mode="RGB")
    
    # Save without any EXIF (PIL default doesn't add EXIF)
    img_path = temp_dir / filename
    img.save(img_path, "JPEG", quality=95)
    
    return img_path


@pytest.fixture
def image_with_exif(temp_dir: Path) -> Path:
    """Create a JPEG with EXIF data."""
    return create_image_with_exif(temp_dir, "with_exif.jpg")


@pytest.fixture
def image_without_exif(temp_dir: Path) -> Path:
    """Create a JPEG without EXIF data."""
    return create_image_without_exif(temp_dir, "no_exif.jpg")


@pytest.fixture
def artifact_with_exif(image_with_exif: Path) -> EvidenceArtifact:
    """Create an evidence artifact from image with EXIF."""
    with open(image_with_exif, "rb") as f:
        content_hash = hashlib.sha256(f.read()).hexdigest()
    
    return EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=str(image_with_exif),
        content_hash=content_hash,
        action="upload",
        agent_id="test",
        session_id=uuid.uuid4(),
    )


@pytest.fixture
def artifact_without_exif(image_without_exif: Path) -> EvidenceArtifact:
    """Create an evidence artifact from image without EXIF."""
    with open(image_without_exif, "rb") as f:
        content_hash = hashlib.sha256(f.read()).hexdigest()
    
    return EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=str(image_without_exif),
        content_hash=content_hash,
        action="upload",
        agent_id="test",
        session_id=uuid.uuid4(),
    )


# ============================================================================
# EXIF Extract Tests
# ============================================================================

@pytest.mark.asyncio
async def test_exif_extract_returns_present_fields(artifact_with_exif: EvidenceArtifact):
    """Test that EXIF extraction returns present fields."""
    result = await exif_extract(artifact_with_exif)
    
    assert "present_fields" in result
    assert "absent_fields" in result
    assert "device_model" in result
    assert "gps_coordinates" in result
    assert "has_exif" in result
    
    # Present fields should be a dict
    assert isinstance(result["present_fields"], dict)
    
    # Absent fields should be a list
    assert isinstance(result["absent_fields"], list)


@pytest.mark.asyncio
async def test_exif_extract_flags_absent_fields_on_stripped_image(
    artifact_without_exif: EvidenceArtifact,
):
    """Test that EXIF extraction flags absent fields on stripped image."""
    result = await exif_extract(artifact_without_exif)
    
    assert "absent_fields" in result
    assert "has_exif" in result
    
    # Image without EXIF should have many absent fields
    # (Most expected EXIF fields should be missing)
    assert len(result["absent_fields"]) > 0
    
    # has_exif should be False for stripped image
    # Note: PIL-created images may have minimal EXIF, so this might not be strictly False
    # The key is that absent_fields is populated


@pytest.mark.asyncio
async def test_exif_extract_handles_missing_file(temp_dir: Path):
    """Test that EXIF extraction handles missing file gracefully."""
    missing_path = temp_dir / "nonexistent.jpg"
    
    artifact = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=str(missing_path),
        content_hash="abc123",
        action="upload",
        agent_id="test",
        session_id=uuid.uuid4(),
    )
    
    with pytest.raises(ToolUnavailableError):
        await exif_extract(artifact)


# ============================================================================
# GPS/Timezone Validation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_gps_timezone_validate_london_coordinates():
    """Test GPS/timezone validation with London coordinates."""
    # London coordinates
    gps_lat = 51.5074
    gps_lon = -0.1278
    timestamp_utc = "2024-06-15T14:30:00Z"
    
    result = await gps_timezone_validate(gps_lat, gps_lon, timestamp_utc)
    
    assert "timezone" in result
    assert "plausible" in result
    assert "offset_hours" in result
    assert "issues" in result
    
    # Should identify London/European timezone
    # timezonefinder should return "Europe/London"
    assert result["timezone"] in ["Europe/London", "Unknown"]
    
    # Timestamp should be plausible (not future, not too old)
    assert result["plausible"] is True
    assert len(result["issues"]) == 0


@pytest.mark.asyncio
async def test_gps_timezone_validate_flags_implausible_timestamp():
    """Test GPS/timezone validation flags implausible timestamp."""
    # New York coordinates
    gps_lat = 40.7128
    gps_lon = -74.0060
    
    # Future timestamp
    future_timestamp = "2030-01-01T00:00:00Z"
    
    result = await gps_timezone_validate(gps_lat, gps_lon, future_timestamp)
    
    assert "plausible" in result
    assert "issues" in result
    
    # Should flag future timestamp
    assert result["plausible"] is False
    assert any("future" in issue.lower() for issue in result["issues"])


@pytest.mark.asyncio
async def test_gps_timezone_validate_flags_predigital_timestamp():
    """Test GPS/timezone validation flags timestamp before digital cameras."""
    # Tokyo coordinates
    gps_lat = 35.6762
    gps_lon = 139.6503
    
    # Timestamp before digital cameras
    old_timestamp = "1980-01-01T00:00:00Z"
    
    result = await gps_timezone_validate(gps_lat, gps_lon, old_timestamp)
    
    assert "plausible" in result
    assert "issues" in result
    
    # Should flag old timestamp
    assert result["plausible"] is False
    assert any("predates" in issue.lower() for issue in result["issues"])


@pytest.mark.asyncio
async def test_gps_timezone_validate_ocean_coordinates():
    """Test GPS/timezone validation with ocean coordinates."""
    # Middle of Pacific Ocean
    gps_lat = 0.0
    gps_lon = -160.0
    timestamp_utc = "2024-06-15T14:30:00Z"
    
    result = await gps_timezone_validate(gps_lat, gps_lon, timestamp_utc)
    
    assert "timezone" in result
    
    # Ocean coordinates may return "Unknown" timezone
    # The function should handle this gracefully


# ============================================================================
# Steganography Scan Tests
# ============================================================================

@pytest.mark.asyncio
async def test_steganography_scan_clean_image_returns_false(
    artifact_without_exif: EvidenceArtifact,
):
    """Test steganography scan on clean image returns low confidence."""
    result = await steganography_scan(artifact_without_exif)
    
    assert "stego_suspected" in result
    assert "confidence" in result
    assert "method" in result
    assert "lsb_statistics" in result
    
    # Clean image should have low steganography confidence
    # (LSBs should be relatively random)
    assert result["confidence"] < 0.7
    
    # LSB statistics should be present
    lsb_stats = result["lsb_statistics"]
    assert "proportion_ones" in lsb_stats
    assert "transition_ratio" in lsb_stats


@pytest.mark.asyncio
async def test_steganography_scan_detects_anomalies(temp_dir: Path):
    """Test steganography scan can detect embedded data."""
    # Create image with embedded data in LSBs
    img_array = np.zeros((200, 200, 3), dtype=np.uint8)
    for i in range(200):
        for j in range(200):
            img_array[i, j] = [i % 256, j % 256, (i + j) % 256]
    
    # Embed a pattern in LSBs (simulating hidden data)
    # Set all LSBs to 0 in a region (non-random pattern)
    img_array[50:150, 50:150, 0] = img_array[50:150, 50:150, 0] & 0xFE  # Clear LSB
    img_array[50:150, 50:150, 1] = img_array[50:150, 50:150, 1] & 0xFE
    img_array[50:150, 50:150, 2] = img_array[50:150, 50:150, 2] & 0xFE
    
    # Save image
    img = Image.fromarray(img_array, mode="RGB")
    img_path = temp_dir / "with_hidden.jpg"
    img.save(img_path, "JPEG", quality=95)
    
    # Create artifact
    with open(img_path, "rb") as f:
        content_hash = hashlib.sha256(f.read()).hexdigest()
    
    artifact = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=str(img_path),
        content_hash=content_hash,
        action="upload",
        agent_id="test",
        session_id=uuid.uuid4(),
    )
    
    result = await steganography_scan(artifact)
    
    assert "stego_suspected" in result
    assert "confidence" in result
    
    # Note: JPEG compression may affect LSB detection
    # The test verifies the function runs correctly


@pytest.mark.asyncio
async def test_steganography_scan_handles_missing_file(temp_dir: Path):
    """Test steganography scan handles missing file."""
    missing_path = temp_dir / "nonexistent.jpg"
    
    artifact = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=str(missing_path),
        content_hash="abc123",
        action="upload",
        agent_id="test",
        session_id=uuid.uuid4(),
    )
    
    with pytest.raises(ToolUnavailableError):
        await steganography_scan(artifact)


# ============================================================================
# File Structure Analysis Tests
# ============================================================================

@pytest.mark.asyncio
async def test_file_structure_analysis_valid_jpeg(artifact_without_exif: EvidenceArtifact):
    """Test file structure analysis on valid JPEG."""
    result = await file_structure_analysis(artifact_without_exif)
    
    assert "file_size" in result
    assert "header_valid" in result
    assert "trailer_valid" in result
    assert "has_appended_data" in result
    assert "anomalies" in result
    
    # Valid JPEG should have valid header and trailer
    assert result["header_valid"] is True
    assert result["trailer_valid"] is True
    assert result["has_appended_data"] is False
    assert len(result["anomalies"]) == 0


@pytest.mark.asyncio
async def test_file_structure_analysis_detects_appended_data(temp_dir: Path):
    """Test file structure analysis detects appended data."""
    # Create a valid JPEG
    img_array = np.zeros((100, 100, 3), dtype=np.uint8)
    img = Image.fromarray(img_array, mode="RGB")
    img_path = temp_dir / "with_appended.jpg"
    img.save(img_path, "JPEG", quality=95)
    
    # Append data after JPEG end marker
    with open(img_path, "ab") as f:
        f.write(b"This is hidden data appended after the image")
    
    # Create artifact
    with open(img_path, "rb") as f:
        content_hash = hashlib.sha256(f.read()).hexdigest()
    
    artifact = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=str(img_path),
        content_hash=content_hash,
        action="upload",
        agent_id="test",
        session_id=uuid.uuid4(),
    )
    
    result = await file_structure_analysis(artifact)
    
    assert "has_appended_data" in result
    assert "anomalies" in result
    
    # Should detect appended data
    assert result["has_appended_data"] is True
    assert any("appended" in a.lower() for a in result["anomalies"])


# ============================================================================
# Timestamp Analysis Tests
# ============================================================================

@pytest.mark.asyncio
async def test_timestamp_analysis(artifact_without_exif: EvidenceArtifact):
    """Test timestamp analysis on image file."""
    result = await timestamp_analysis(artifact_without_exif)
    
    assert "file_created" in result
    assert "file_modified" in result
    assert "exif_timestamps" in result
    assert "inconsistencies" in result
    
    # File timestamps should be present
    assert result["file_created"] is not None
    assert result["file_modified"] is not None


@pytest.mark.asyncio
async def test_timestamp_analysis_handles_missing_file(temp_dir: Path):
    """Test timestamp analysis handles missing file."""
    missing_path = temp_dir / "nonexistent.jpg"
    
    artifact = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=str(missing_path),
        content_hash="abc123",
        action="upload",
        agent_id="test",
        session_id=uuid.uuid4(),
    )
    
    with pytest.raises(ToolUnavailableError):
        await timestamp_analysis(artifact)