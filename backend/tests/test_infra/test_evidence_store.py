"""
Evidence Store Tests
====================

Tests for evidence ingestion and versioning system.
"""

import os
import tempfile
import pytest
from pathlib import Path
from uuid import uuid4

from core.evidence import ArtifactType, EvidenceArtifact, VersionTree
from core.custody_logger import CustodyLogger, EntryType
from infra.evidence_store import EvidenceStore
from infra.postgres_client import PostgresClient
from infra.storage import LocalStorageBackend


@pytest.fixture
def temp_storage(tmp_path: Path) -> LocalStorageBackend:
    """Create a temporary storage backend."""
    return LocalStorageBackend(storage_path=str(tmp_path / "evidence"))


@pytest.fixture
async def evidence_store(
    postgres_client: PostgresClient,
    temp_storage: LocalStorageBackend,
) -> EvidenceStore:
    """Create an EvidenceStore with test dependencies."""
    custody_logger = CustodyLogger(postgres_client=postgres_client)
    store = EvidenceStore(
        postgres_client=postgres_client,
        storage_backend=temp_storage,
        custody_logger=custody_logger,
    )
    return store


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    """Create a sample evidence file."""
    file_path = tmp_path / "test_evidence.jpg"
    file_path.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
    return file_path


class TestEvidenceStore:
    """Tests for EvidenceStore class."""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_ingest_creates_root_artifact_with_correct_hash(
        self,
        evidence_store: EvidenceStore,
        sample_file: Path,
    ):
        """Test that ingest creates a root artifact with correct hash."""
        session_id = uuid4()
        
        artifact = await evidence_store.ingest(
            file_path=str(sample_file),
            session_id=session_id,
            agent_id="test_agent",
        )
        
        assert artifact is not None
        assert artifact.artifact_id is not None
        assert artifact.parent_id is None  # Root artifact
        assert artifact.root_id == artifact.artifact_id
        assert artifact.artifact_type == ArtifactType.ORIGINAL
        assert artifact.agent_id == "test_agent"
        assert artifact.session_id == session_id
        assert len(artifact.content_hash) == 64  # SHA-256 hex
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_ingest_copies_file_to_immutable_storage(
        self,
        evidence_store: EvidenceStore,
        sample_file: Path,
    ):
        """Test that ingest copies file to storage."""
        session_id = uuid4()
        
        artifact = await evidence_store.ingest(
            file_path=str(sample_file),
            session_id=session_id,
            agent_id="test_agent",
        )
        
        # Check file exists in storage
        assert os.path.exists(artifact.file_path)
        
        # Check content matches
        stored_content = Path(artifact.file_path).read_bytes()
        original_content = sample_file.read_bytes()
        assert stored_content == original_content
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_derivative_links_to_parent(
        self,
        evidence_store: EvidenceStore,
        sample_file: Path,
    ):
        """Test that derivative artifacts link to parent."""
        session_id = uuid4()
        
        # Create parent
        parent = await evidence_store.ingest(
            file_path=str(sample_file),
            session_id=session_id,
            agent_id="test_agent",
        )
        
        # Create derivative
        derivative_data = b"processed_data_content"
        derivative = await evidence_store.create_derivative(
            parent=parent,
            data=derivative_data,
            artifact_type=ArtifactType.ELA_OUTPUT,
            action="error_level_analysis",
            agent_id="image_agent",
        )
        
        assert derivative.parent_id == parent.artifact_id
        assert derivative.root_id == parent.root_id
        assert derivative.artifact_type == ArtifactType.ELA_OUTPUT
        assert derivative.action == "error_level_analysis"
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_version_tree_shows_parent_child_relationship(
        self,
        evidence_store: EvidenceStore,
        sample_file: Path,
    ):
        """Test that version tree shows parent-child relationship."""
        session_id = uuid4()
        
        # Create parent
        parent = await evidence_store.ingest(
            file_path=str(sample_file),
            session_id=session_id,
            agent_id="test_agent",
        )
        
        # Create derivative
        derivative = await evidence_store.create_derivative(
            parent=parent,
            data=b"derivative_data",
            artifact_type=ArtifactType.ELA_OUTPUT,
            action="ela",
            agent_id="image_agent",
        )
        
        # Get version tree
        tree = await evidence_store.get_version_tree(parent.root_id)
        
        assert tree is not None
        assert tree.artifact.artifact_id == parent.artifact_id
        assert len(tree.children) == 1
        assert tree.children[0].artifact.artifact_id == derivative.artifact_id
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_version_tree_three_levels_deep(
        self,
        evidence_store: EvidenceStore,
        sample_file: Path,
    ):
        """Test version tree with three levels of derivatives."""
        session_id = uuid4()
        
        # Create root
        root = await evidence_store.ingest(
            file_path=str(sample_file),
            session_id=session_id,
            agent_id="test_agent",
        )
        
        # Create level 1 derivative
        level1 = await evidence_store.create_derivative(
            parent=root,
            data=b"level1_data",
            artifact_type=ArtifactType.ELA_OUTPUT,
            action="ela",
            agent_id="agent1",
        )
        
        # Create level 2 derivative
        level2 = await evidence_store.create_derivative(
            parent=level1,
            data=b"level2_data",
            artifact_type=ArtifactType.ROI_CROP,
            action="crop",
            agent_id="agent2",
        )
        
        # Get version tree
        tree = await evidence_store.get_version_tree(root.root_id)
        
        assert tree is not None
        assert tree.count() == 3
        assert tree.max_depth() == 3
        
        # Verify structure
        assert tree.artifact.artifact_id == root.artifact_id
        assert len(tree.children) == 1
        assert tree.children[0].artifact.artifact_id == level1.artifact_id
        assert len(tree.children[0].children) == 1
        assert tree.children[0].children[0].artifact.artifact_id == level2.artifact_id
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_integrity_check_passes_untouched_file(
        self,
        evidence_store: EvidenceStore,
        sample_file: Path,
    ):
        """Test integrity check passes for untouched file."""
        session_id = uuid4()
        
        artifact = await evidence_store.ingest(
            file_path=str(sample_file),
            session_id=session_id,
            agent_id="test_agent",
        )
        
        is_valid = await evidence_store.verify_artifact_integrity(artifact)
        
        assert is_valid is True
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_integrity_check_fails_modified_file(
        self,
        evidence_store: EvidenceStore,
        sample_file: Path,
    ):
        """Test integrity check fails for modified file."""
        session_id = uuid4()
        
        artifact = await evidence_store.ingest(
            file_path=str(sample_file),
            session_id=session_id,
            agent_id="test_agent",
        )
        
        # Modify the stored file
        stored_path = Path(artifact.file_path)
        # Need to make writable first
        stored_path.chmod(0o644)
        stored_path.write_bytes(b"tampered_content")
        stored_path.chmod(0o444)
        
        is_valid = await evidence_store.verify_artifact_integrity(artifact)
        
        assert is_valid is False
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_ingest_logs_artifact_version_to_custody_logger(
        self,
        evidence_store: EvidenceStore,
        sample_file: Path,
    ):
        """Test that ingest logs to chain of custody."""
        session_id = uuid4()
        
        artifact = await evidence_store.ingest(
            file_path=str(sample_file),
            session_id=session_id,
            agent_id="test_agent",
        )
        
        # Get chain
        chain = await evidence_store._custody_logger.get_session_chain(session_id)
        
        assert len(chain) == 1
        assert chain[0].entry_type == EntryType.ARTIFACT_VERSION
        assert chain[0].content["artifact_id"] == str(artifact.artifact_id)
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_derivative_logs_artifact_version_to_custody_logger(
        self,
        evidence_store: EvidenceStore,
        sample_file: Path,
    ):
        """Test that derivative creation logs to chain of custody."""
        session_id = uuid4()
        
        # Create parent
        parent = await evidence_store.ingest(
            file_path=str(sample_file),
            session_id=session_id,
            agent_id="test_agent",
        )
        
        # Create derivative
        derivative = await evidence_store.create_derivative(
            parent=parent,
            data=b"derivative_data",
            artifact_type=ArtifactType.ELA_OUTPUT,
            action="ela",
            agent_id="image_agent",
        )
        
        # Get chain
        chain = await evidence_store._custody_logger.get_session_chain(session_id)
        
        assert len(chain) == 2
        # First entry is for parent
        assert chain[0].entry_type == EntryType.ARTIFACT_VERSION
        # Second entry is for derivative
        assert chain[1].entry_type == EntryType.ARTIFACT_VERSION
        assert chain[1].content["parent_id"] == str(parent.artifact_id)
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_artifact(
        self,
        evidence_store: EvidenceStore,
        sample_file: Path,
    ):
        """Test retrieving an artifact by ID."""
        session_id = uuid4()
        
        artifact = await evidence_store.ingest(
            file_path=str(sample_file),
            session_id=session_id,
            agent_id="test_agent",
        )
        
        retrieved = await evidence_store.get_artifact(artifact.artifact_id)
        
        assert retrieved is not None
        assert retrieved.artifact_id == artifact.artifact_id
        assert retrieved.content_hash == artifact.content_hash
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_nonexistent_artifact(
        self,
        evidence_store: EvidenceStore,
    ):
        """Test retrieving a non-existent artifact returns None."""
        result = await evidence_store.get_artifact(uuid4())
        
        assert result is None


class TestEvidenceArtifact:
    """Tests for EvidenceArtifact dataclass."""
    
    def test_create_root(self):
        """Test creating a root artifact."""
        session_id = uuid4()
        
        artifact = EvidenceArtifact.create_root(
            artifact_type=ArtifactType.ORIGINAL,
            file_path="/path/to/file.jpg",
            content_hash="abc123",
            action="ingest",
            agent_id="agent",
            session_id=session_id,
        )
        
        assert artifact.parent_id is None
        assert artifact.root_id == artifact.artifact_id
        assert artifact.is_root() is True
    
    def test_create_derivative(self):
        """Test creating a derivative artifact."""
        session_id = uuid4()
        
        parent = EvidenceArtifact.create_root(
            artifact_type=ArtifactType.ORIGINAL,
            file_path="/path/to/file.jpg",
            content_hash="abc123",
            action="ingest",
            agent_id="agent",
            session_id=session_id,
        )
        
        derivative = EvidenceArtifact.create_derivative(
            parent=parent,
            artifact_type=ArtifactType.ELA_OUTPUT,
            file_path="/path/to/ela.png",
            content_hash="def456",
            action="ela",
            agent_id="image_agent",
        )
        
        assert derivative.parent_id == parent.artifact_id
        assert derivative.root_id == parent.root_id
        assert derivative.session_id == parent.session_id
        assert derivative.is_root() is False
    
    def test_to_dict_and_from_dict(self):
        """Test serialization and deserialization."""
        session_id = uuid4()
        
        original = EvidenceArtifact.create_root(
            artifact_type=ArtifactType.ORIGINAL,
            file_path="/path/to/file.jpg",
            content_hash="abc123",
            action="ingest",
            agent_id="agent",
            session_id=session_id,
            metadata={"key": "value"},
        )
        
        data = original.to_dict()
        restored = EvidenceArtifact.from_dict(data)
        
        assert restored.artifact_id == original.artifact_id
        assert restored.parent_id == original.parent_id
        assert restored.root_id == original.root_id
        assert restored.artifact_type == original.artifact_type
        assert restored.file_path == original.file_path
        assert restored.content_hash == original.content_hash
        assert restored.metadata == original.metadata


class TestVersionTree:
    """Tests for VersionTree dataclass."""
    
    def test_count_and_depth(self):
        """Test tree counting and depth."""
        root_artifact = EvidenceArtifact.create_root(
            artifact_type=ArtifactType.ORIGINAL,
            file_path="/root.jpg",
            content_hash="abc",
            action="ingest",
            agent_id="agent",
            session_id=uuid4(),
        )
        
        tree = VersionTree(artifact=root_artifact)
        
        assert tree.count() == 1
        assert tree.max_depth() == 1
        
        # Add child
        child = EvidenceArtifact.create_derivative(
            parent=root_artifact,
            artifact_type=ArtifactType.ELA_OUTPUT,
            file_path="/ela.png",
            content_hash="def",
            action="ela",
            agent_id="agent",
        )
        
        tree.add_child(VersionTree(artifact=child))
        
        assert tree.count() == 2
        assert tree.max_depth() == 2
    
    def test_find_by_id(self):
        """Test finding artifact by ID in tree."""
        root_artifact = EvidenceArtifact.create_root(
            artifact_type=ArtifactType.ORIGINAL,
            file_path="/root.jpg",
            content_hash="abc",
            action="ingest",
            agent_id="agent",
            session_id=uuid4(),
        )
        
        child_artifact = EvidenceArtifact.create_derivative(
            parent=root_artifact,
            artifact_type=ArtifactType.ELA_OUTPUT,
            file_path="/ela.png",
            content_hash="def",
            action="ela",
            agent_id="agent",
        )
        
        tree = VersionTree(artifact=root_artifact)
        tree.add_child(VersionTree(artifact=child_artifact))
        
        # Find root
        found = tree.find_by_id(root_artifact.artifact_id)
        assert found is not None
        assert found.artifact.artifact_id == root_artifact.artifact_id
        
        # Find child
        found = tree.find_by_id(child_artifact.artifact_id)
        assert found is not None
        assert found.artifact.artifact_id == child_artifact.artifact_id
        
        # Not found
        found = tree.find_by_id(uuid4())
        assert found is None
    
    def test_get_all_artifacts(self):
        """Test getting all artifacts from tree."""
        root_artifact = EvidenceArtifact.create_root(
            artifact_type=ArtifactType.ORIGINAL,
            file_path="/root.jpg",
            content_hash="abc",
            action="ingest",
            agent_id="agent",
            session_id=uuid4(),
        )
        
        child_artifact = EvidenceArtifact.create_derivative(
            parent=root_artifact,
            artifact_type=ArtifactType.ELA_OUTPUT,
            file_path="/ela.png",
            content_hash="def",
            action="ela",
            agent_id="agent",
        )
        
        tree = VersionTree(artifact=root_artifact)
        tree.add_child(VersionTree(artifact=child_artifact))
        
        all_artifacts = tree.get_all_artifacts()
        
        assert len(all_artifacts) == 2
        assert root_artifact in all_artifacts
        assert child_artifact in all_artifacts


class TestArtifactType:
    """Tests for ArtifactType enum."""
    
    def test_all_types_exist(self):
        """Test that all required artifact types are defined."""
        expected_types = [
            "ORIGINAL", "ELA_OUTPUT", "ROI_CROP", "AUDIO_SEGMENT",
            "VIDEO_FRAME_WINDOW", "METADATA_EXPORT", "STEGANOGRAPHY_SCAN",
            "CODEC_FINGERPRINT", "OPTICAL_FLOW_HEATMAP", "CALIBRATION_OUTPUT"
        ]
        
        for type_name in expected_types:
            assert hasattr(ArtifactType, type_name)
    
    def test_type_values(self):
        """Test that type values match names."""
        assert ArtifactType.ORIGINAL.value == "ORIGINAL"
        assert ArtifactType.ELA_OUTPUT.value == "ELA_OUTPUT"
        assert ArtifactType.ROI_CROP.value == "ROI_CROP"
