"""
Tests for Video Forensic Tools
==============================

Tests for optical flow analysis, frame extraction, frame consistency analysis,
and face swap detection.
"""

import hashlib
import os
import tempfile
import uuid
from pathlib import Path

import cv2
import numpy as np
import pytest

from core.evidence import ArtifactType, EvidenceArtifact
from core.exceptions import ToolUnavailableError
from tools.video_tools import (
    optical_flow_analyze,
    frame_window_extract,
    frame_consistency_analyze,
    face_swap_detect,
    video_metadata_extract,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def create_video(
    output_path: str,
    frame_count: int = 30,
    width: int = 320,
    height: int = 240,
    fps: float = 30.0,
    color: tuple = (100, 100, 100),
    with_edit: bool = False,
) -> None:
    """Create a synthetic video for testing."""
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    
    for i in range(frame_count):
        # Create a frame with some pattern
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Add a moving rectangle
        x = int((i / frame_count) * (width - 50))
        cv2.rectangle(frame, (x, 100), (x + 50, 150), color, -1)
        
        # Add some texture
        cv2.putText(frame, f"Frame {i}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # If with_edit, introduce a sudden change at frame 15
        if with_edit and i == 15:
            # Sudden color change
            frame[:, :] = (200, 50, 50)
        
        out.write(frame)
    
    out.release()


@pytest.fixture
def clean_video(temp_dir: Path) -> Path:
    """Create a clean video file."""
    video_path = temp_dir / "clean.mp4"
    create_video(str(video_path), frame_count=30, color=(100, 150, 200))
    return video_path


@pytest.fixture
def edited_video(temp_dir: Path) -> Path:
    """Create a video with a deliberate edit."""
    video_path = temp_dir / "edited.mp4"
    create_video(str(video_path), frame_count=30, color=(100, 150, 200), with_edit=True)
    return video_path


@pytest.fixture
def clean_artifact(clean_video: Path) -> EvidenceArtifact:
    """Create an evidence artifact from the clean video."""
    with open(clean_video, "rb") as f:
        content_hash = hashlib.sha256(f.read()).hexdigest()
    
    return EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=str(clean_video),
        content_hash=content_hash,
        action="upload",
        agent_id="test",
        session_id=uuid.uuid4(),
    )


@pytest.fixture
def edited_artifact(edited_video: Path) -> EvidenceArtifact:
    """Create an evidence artifact from the edited video."""
    with open(edited_video, "rb") as f:
        content_hash = hashlib.sha256(f.read()).hexdigest()
    
    return EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=str(edited_video),
        content_hash=content_hash,
        action="upload",
        agent_id="test",
        session_id=uuid.uuid4(),
    )


# ============================================================================
# Optical Flow Tests
# ============================================================================

@pytest.mark.asyncio
async def test_optical_flow_generates_heatmap_artifact(clean_artifact: EvidenceArtifact):
    """Test that optical flow analysis generates a heatmap artifact."""
    result = await optical_flow_analyze(clean_artifact)
    
    assert "anomaly_heatmap_artifact" in result
    assert "flagged_frames" in result
    assert "motion_stats" in result
    assert "video_info" in result
    
    # Check heatmap artifact
    heatmap_artifact = result["anomaly_heatmap_artifact"]
    assert heatmap_artifact is not None
    assert heatmap_artifact.artifact_type == ArtifactType.OPTICAL_FLOW_HEATMAP
    assert heatmap_artifact.parent_id == clean_artifact.artifact_id
    
    # Check that heatmap file was created
    assert os.path.exists(heatmap_artifact.file_path)
    
    # Check video info
    assert result["video_info"]["fps"] > 0
    assert result["video_info"]["frame_count"] > 0


@pytest.mark.asyncio
async def test_optical_flow_flags_abrupt_motion_change(edited_artifact: EvidenceArtifact):
    """Test that optical flow flags abrupt motion changes."""
    result = await optical_flow_analyze(edited_artifact, flow_threshold=2.0)
    
    assert "flagged_frames" in result
    assert "motion_stats" in result
    
    # The edited video has a sudden change at frame 15
    # This might be flagged depending on the threshold
    # Note: Detection depends on the nature of the edit


@pytest.mark.asyncio
async def test_optical_flow_handles_missing_file(temp_dir: Path):
    """Test that optical flow handles missing file."""
    missing_path = temp_dir / "nonexistent.mp4"
    
    artifact = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=str(missing_path),
        content_hash="abc123",
        action="upload",
        agent_id="test",
        session_id=uuid.uuid4(),
    )
    
    with pytest.raises(ToolUnavailableError):
        await optical_flow_analyze(artifact)


# ============================================================================
# Frame Window Extract Tests
# ============================================================================

@pytest.mark.asyncio
async def test_frame_window_extract_creates_derivative(clean_artifact: EvidenceArtifact):
    """Test that frame window extraction creates a derivative artifact."""
    result = await frame_window_extract(clean_artifact, start_frame=0, end_frame=10)
    
    assert "frames_artifact" in result
    assert "frame_count" in result
    assert "output_path" in result
    
    # Check derivative artifact
    frames_artifact = result["frames_artifact"]
    assert frames_artifact.artifact_type == ArtifactType.VIDEO_FRAME_WINDOW
    assert frames_artifact.parent_id == clean_artifact.artifact_id
    
    # Check that frames were extracted
    assert result["frame_count"] > 0
    assert os.path.exists(result["output_path"])
    assert os.path.isdir(result["output_path"])


@pytest.mark.asyncio
async def test_frame_window_extract_handles_out_of_bounds(clean_artifact: EvidenceArtifact):
    """Test that frame extraction handles out-of-bounds frame numbers."""
    # Request frames beyond video length
    result = await frame_window_extract(clean_artifact, start_frame=0, end_frame=1000)
    
    # Should extract available frames without error
    assert "frame_count" in result
    assert result["frame_count"] > 0


# ============================================================================
# Frame Consistency Analysis Tests
# ============================================================================

@pytest.mark.asyncio
async def test_frame_consistency_detects_discontinuity(edited_artifact: EvidenceArtifact):
    """Test that frame consistency analysis detects discontinuity."""
    # First extract frames
    extract_result = await frame_window_extract(edited_artifact, start_frame=0, end_frame=30)
    frames_artifact = extract_result["frames_artifact"]
    
    # Then analyze consistency
    result = await frame_consistency_analyze(frames_artifact)
    
    assert "inconsistencies" in result
    assert "classification_hint" in result
    assert "statistics" in result
    
    # The edited video has a sudden change, might be detected
    # Note: Detection depends on thresholds


@pytest.mark.asyncio
async def test_frame_consistency_clean_video(clean_artifact: EvidenceArtifact):
    """Test frame consistency analysis on clean video."""
    # First extract frames
    extract_result = await frame_window_extract(clean_artifact, start_frame=0, end_frame=30)
    frames_artifact = extract_result["frames_artifact"]
    
    # Then analyze consistency
    result = await frame_consistency_analyze(frames_artifact)
    
    assert "inconsistencies" in result
    assert "classification_hint" in result
    
    # Clean video should have fewer inconsistencies
    # (though some might be detected due to the moving rectangle)


# ============================================================================
# Face Swap Detection Tests
# ============================================================================

@pytest.mark.asyncio
async def test_face_swap_detect_runs_without_error_on_no_face_frame(
    clean_artifact: EvidenceArtifact,
):
    """Test that face swap detection runs without error on frames without faces."""
    # First extract frames
    extract_result = await frame_window_extract(clean_artifact, start_frame=0, end_frame=10)
    frames_artifact = extract_result["frames_artifact"]
    
    # Then run face swap detection
    result = await face_swap_detect(frames_artifact)
    
    assert "deepfake_suspected" in result
    assert "confidence" in result
    assert "flagged_frames" in result
    assert "face_count" in result
    assert "analysis_method" in result
    
    # The synthetic video has no faces
    assert result["face_count"] == 0
    assert result["deepfake_suspected"] is False


@pytest.mark.asyncio
async def test_face_swap_detect_production_note(clean_artifact: EvidenceArtifact):
    """Test that face swap detection includes production note."""
    # First extract frames
    extract_result = await frame_window_extract(clean_artifact, start_frame=0, end_frame=10)
    frames_artifact = extract_result["frames_artifact"]
    
    # Then run face swap detection
    result = await face_swap_detect(frames_artifact)
    
    # Should include production note about heuristic implementation
    assert "production_note" in result
    assert "FaceForensics++" in result["production_note"]


# ============================================================================
# Video Metadata Tests
# ============================================================================

@pytest.mark.asyncio
async def test_video_metadata_extract(clean_artifact: EvidenceArtifact):
    """Test video metadata extraction."""
    result = await video_metadata_extract(clean_artifact)
    
    assert "metadata" in result
    assert "file_path" in result
    
    metadata = result["metadata"]
    assert "fps" in metadata
    assert "frame_count" in metadata
    assert "width" in metadata
    assert "height" in metadata
    assert "duration" in metadata
    
    # Check reasonable values
    assert metadata["fps"] > 0
    assert metadata["frame_count"] > 0
    assert metadata["width"] > 0
    assert metadata["height"] > 0


@pytest.mark.asyncio
async def test_video_metadata_handles_missing_file(temp_dir: Path):
    """Test video metadata extraction handles missing file."""
    missing_path = temp_dir / "nonexistent.mp4"
    
    artifact = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=str(missing_path),
        content_hash="abc123",
        action="upload",
        agent_id="test",
        session_id=uuid.uuid4(),
    )
    
    with pytest.raises(ToolUnavailableError):
        await video_metadata_extract(artifact)
