"""
Unit tests for core/evidence.py
"""

import pytest
from pathlib import Path
from core.evidence import EvidenceArtifact, ArtifactType
from pydantic import ValidationError


class TestEvidenceArtifact:
    """Test cases for EvidenceArtifact."""

    def test_create_valid_artifact(self):
        """Test creating a valid artifact."""
        from uuid import uuid4
        
        artifact = EvidenceArtifact(
            artifact_id=uuid4(),
            parent_id=None,
            root_id=uuid4(),
            artifact_type=ArtifactType.ORIGINAL,
            file_path="/tmp/test.jpg",
            content_hash="abc123",
            action="upload",
            agent_id="system",
            session_id=uuid4(),
        )
        
        assert artifact.file_path == "/tmp/test.jpg"
        assert artifact.artifact_type == ArtifactType.ORIGINAL

    def test_artifact_type_enum(self):
        """Test artifact type enum values."""
        assert ArtifactType.ORIGINAL.value == "ORIGINAL"
        assert ArtifactType.ELA_OUTPUT.value == "ELA_OUTPUT"
        assert ArtifactType.ROI_CROP.value == "ROI_CROP"
        assert ArtifactType.AUDIO_SEGMENT.value == "AUDIO_SEGMENT"
        assert ArtifactType.VIDEO_FRAME_WINDOW.value == "VIDEO_FRAME_WINDOW"
        assert ArtifactType.METADATA_EXPORT.value == "METADATA_EXPORT"
        assert ArtifactType.STEGANOGRAPHY_SCAN.value == "STEGANOGRAPHY_SCAN"
        assert ArtifactType.CODEC_FINGERPRINT.value == "CODEC_FINGERPRINT"
        assert ArtifactType.OPTICAL_FLOW_HEATMAP.value == "OPTICAL_FLOW_HEATMAP"
        assert ArtifactType.CALIBRATION_OUTPUT.value == "CALIBRATION_OUTPUT"

    def test_artifact_to_dict(self):
        """Test artifact serialization."""
        from uuid import uuid4
        
        artifact_id = uuid4()
        root_id = uuid4()
        session_id = uuid4()
        
        artifact = EvidenceArtifact(
            artifact_id=artifact_id,
            parent_id=None,
            root_id=root_id,
            artifact_type=ArtifactType.ORIGINAL,
            file_path="/tmp/test.jpg",
            content_hash="abc123",
            action="upload",
            agent_id="system",
            session_id=session_id,
        )
        
        data = artifact.to_dict()
        
        assert data["artifact_id"] == str(artifact_id)
        assert data["file_path"] == "/tmp/test.jpg"
        assert data["content_hash"] == "abc123"
