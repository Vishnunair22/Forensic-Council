"""
Unit tests for the EvidenceArtifact model.

Covers:
- Root artifact creation (parent_id=None, root_id == artifact_id)
- Derivative artifact creation (parent linkage, root lineage)
- mime_type property fallback
- ArtifactType enum completeness
- Immutable chain lineage assertions
"""

import os
from uuid import UUID, uuid4

import pytest

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_PASSWORD", "test")
os.environ.setdefault("DEMO_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")

from core.evidence import ArtifactType, EvidenceArtifact

# â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _root(session_id: UUID | None = None) -> EvidenceArtifact:
    return EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path="/evidence/img.jpg",
        content_hash="abc123hash",
        action="upload",
        agent_id="system",
        session_id=session_id or uuid4(),
        metadata={"mime_type": "image/jpeg"},
    )


def _derivative(parent: EvidenceArtifact) -> EvidenceArtifact:
    return EvidenceArtifact.create_derivative(
        parent=parent,
        artifact_type=ArtifactType.ELA_OUTPUT,
        file_path="/evidence/ela_output.png",
        content_hash="ela_hash_456",
        action="ela_analysis",
        agent_id="Agent1",
        metadata={"quality_level": 95},
    )


# â”€â”€ Root artifact â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestRootArtifact:
    def test_root_parent_id_is_none(self):
        a = _root()
        assert a.parent_id is None

    def test_root_id_equals_artifact_id(self):
        a = _root()
        assert a.root_id == a.artifact_id

    def test_root_artifact_id_is_uuid(self):
        a = _root()
        assert isinstance(a.artifact_id, UUID)

    def test_root_artifact_type_correct(self):
        a = _root()
        assert a.artifact_type == ArtifactType.ORIGINAL

    def test_root_file_path_stored(self):
        a = _root()
        assert a.file_path == "/evidence/img.jpg"

    def test_root_content_hash_stored(self):
        a = _root()
        assert a.content_hash == "abc123hash"

    def test_root_agent_id_stored(self):
        a = _root()
        assert a.agent_id == "system"

    def test_root_session_id_matches(self):
        sid = uuid4()
        a = _root(session_id=sid)
        assert a.session_id == sid

    def test_root_timestamp_is_set(self):
        from datetime import datetime

        a = _root()
        assert isinstance(a.timestamp_utc, datetime)

    def test_root_metadata_stored(self):
        a = _root()
        assert a.metadata.get("mime_type") == "image/jpeg"

    def test_mime_type_from_metadata(self):
        a = _root()
        assert a.mime_type == "image/jpeg"

    def test_mime_type_empty_when_no_metadata(self):
        a = EvidenceArtifact.create_root(
            artifact_type=ArtifactType.ORIGINAL,
            file_path="/x.jpg",
            content_hash="h",
            action="upload",
            agent_id="system",
            session_id=uuid4(),
        )
        assert a.mime_type == ""

    def test_two_roots_have_different_artifact_ids(self):
        a, b = _root(), _root()
        assert a.artifact_id != b.artifact_id


# â”€â”€ Derivative artifact â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestDerivativeArtifact:
    def test_derivative_parent_id_equals_parent_artifact_id(self):
        root = _root()
        deriv = _derivative(root)
        assert deriv.parent_id == root.artifact_id

    def test_derivative_root_id_equals_original_root_id(self):
        root = _root()
        deriv = _derivative(root)
        assert deriv.root_id == root.root_id

    def test_derivative_artifact_id_is_new(self):
        root = _root()
        deriv = _derivative(root)
        assert deriv.artifact_id != root.artifact_id

    def test_derivative_type_correct(self):
        root = _root()
        deriv = _derivative(root)
        assert deriv.artifact_type == ArtifactType.ELA_OUTPUT

    def test_derivative_agent_id_correct(self):
        root = _root()
        deriv = _derivative(root)
        assert deriv.agent_id == "Agent1"

    def test_second_generation_preserves_root(self):
        """Grandchild must trace root_id back to original."""
        root = _root()
        child = _derivative(root)
        grandchild = EvidenceArtifact.create_derivative(
            parent=child,
            artifact_type=ArtifactType.ROI_CROP,
            file_path="/roi.png",
            content_hash="roi_hash",
            action="roi_extract",
            agent_id="Agent1",
        )
        assert grandchild.root_id == root.artifact_id
        assert grandchild.parent_id == child.artifact_id

    def test_derivative_metadata_stored(self):
        root = _root()
        deriv = _derivative(root)
        assert deriv.metadata.get("quality_level") == 95


# â”€â”€ ArtifactType enum â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestArtifactTypeEnum:
    EXPECTED_TYPES = [
        "ORIGINAL",
        "ELA_OUTPUT",
        "ROI_CROP",
        "AUDIO_SEGMENT",
        "VIDEO_FRAME_WINDOW",
        "METADATA_EXPORT",
        "OPTICAL_FLOW_HEATMAP",
        "CODEC_FINGERPRINT",
        "CALIBRATION_OUTPUT",
    ]

    @pytest.mark.parametrize("name", EXPECTED_TYPES)
    def test_artifact_type_exists(self, name):
        assert hasattr(ArtifactType, name), f"ArtifactType.{name} missing"

    def test_all_types_are_strings(self):
        for t in ArtifactType:
            assert isinstance(t.value, str)
