"""
Evidence Module
===============

Defines evidence artifact models and types for forensic analysis.
Supports immutable versioning and chain-of-custody tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4


class ArtifactType(str, Enum):
    """Types of evidence artifacts."""
    ORIGINAL = "ORIGINAL"
    ELA_OUTPUT = "ELA_OUTPUT"
    ROI_CROP = "ROI_CROP"
    AUDIO_SEGMENT = "AUDIO_SEGMENT"
    VIDEO_FRAME_WINDOW = "VIDEO_FRAME_WINDOW"
    METADATA_EXPORT = "METADATA_EXPORT"
    STEGANOGRAPHY_SCAN = "STEGANOGRAPHY_SCAN"
    CODEC_FINGERPRINT = "CODEC_FINGERPRINT"
    OPTICAL_FLOW_HEATMAP = "OPTICAL_FLOW_HEATMAP"
    CALIBRATION_OUTPUT = "CALIBRATION_OUTPUT"


@dataclass
class EvidenceArtifact:
    """
    An evidence artifact with immutable versioning.
    
    Attributes:
        artifact_id: Unique identifier for this artifact
        parent_id: Parent artifact ID (None for root/original)
        root_id: Root artifact ID (same as artifact_id for originals)
        artifact_type: Type of artifact
        file_path: Path to the artifact file in storage
        content_hash: SHA-256 hash of file content
        action: Action that created this artifact
        agent_id: Agent that created this artifact
        session_id: Analysis session ID
        timestamp_utc: When this artifact was created
        metadata: Additional metadata
    """
    artifact_id: UUID
    parent_id: Optional[UUID]
    root_id: UUID
    artifact_type: ArtifactType
    file_path: str
    content_hash: str
    action: str
    agent_id: str
    session_id: UUID
    timestamp_utc: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def create_root(
        cls,
        artifact_type: ArtifactType,
        file_path: str,
        content_hash: str,
        action: str,
        agent_id: str,
        session_id: UUID,
        metadata: Optional[dict[str, Any]] = None,
    ) -> "EvidenceArtifact":
        """
        Create a root artifact (original evidence).
        
        Args:
            artifact_type: Type of artifact
            file_path: Path to the artifact file
            content_hash: SHA-256 hash of file content
            action: Action that created this artifact
            agent_id: Agent that created this artifact
            session_id: Analysis session ID
            metadata: Additional metadata
        
        Returns:
            New EvidenceArtifact with parent_id=None
        """
        artifact_id = uuid4()
        return cls(
            artifact_id=artifact_id,
            parent_id=None,
            root_id=artifact_id,  # Root ID is same as artifact ID for originals
            artifact_type=artifact_type,
            file_path=file_path,
            content_hash=content_hash,
            action=action,
            agent_id=agent_id,
            session_id=session_id,
            metadata=metadata or {},
        )
    
    @classmethod
    def create_derivative(
        cls,
        parent: "EvidenceArtifact",
        artifact_type: ArtifactType,
        file_path: str,
        content_hash: str,
        action: str,
        agent_id: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> "EvidenceArtifact":
        """
        Create a derivative artifact from a parent.
        
        Args:
            parent: Parent artifact
            artifact_type: Type of derivative artifact
            file_path: Path to the derivative file
            content_hash: SHA-256 hash of file content
            action: Action that created this derivative
            agent_id: Agent that created this derivative
            metadata: Additional metadata
        
        Returns:
            New EvidenceArtifact linked to parent
        """
        return cls(
            artifact_id=uuid4(),
            parent_id=parent.artifact_id,
            root_id=parent.root_id,
            artifact_type=artifact_type,
            file_path=file_path,
            content_hash=content_hash,
            action=action,
            agent_id=agent_id,
            session_id=parent.session_id,
            metadata=metadata or {},
        )
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "artifact_id": str(self.artifact_id),
            "parent_id": str(self.parent_id) if self.parent_id else None,
            "root_id": str(self.root_id),
            "artifact_type": self.artifact_type.value,
            "file_path": self.file_path,
            "content_hash": self.content_hash,
            "action": self.action,
            "agent_id": self.agent_id,
            "session_id": str(self.session_id),
            "timestamp_utc": self.timestamp_utc.isoformat(),
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceArtifact":
        """Create from dictionary."""
        return cls(
            artifact_id=UUID(data["artifact_id"]),
            parent_id=UUID(data["parent_id"]) if data.get("parent_id") else None,
            root_id=UUID(data["root_id"]),
            artifact_type=ArtifactType(data["artifact_type"]),
            file_path=data["file_path"],
            content_hash=data["content_hash"],
            action=data["action"],
            agent_id=data["agent_id"],
            session_id=UUID(data["session_id"]),
            timestamp_utc=datetime.fromisoformat(data["timestamp_utc"])
            if isinstance(data["timestamp_utc"], str)
            else data["timestamp_utc"],
            metadata=data.get("metadata", {}),
        )
    
    def is_root(self) -> bool:
        """Check if this is a root/original artifact."""
        return self.parent_id is None


@dataclass
class VersionTree:
    """
    A tree structure representing the version history of an evidence artifact.
    
    Attributes:
        root: The root artifact
        children: List of child VersionTree nodes
    """
    artifact: EvidenceArtifact
    children: list["VersionTree"] = field(default_factory=list)
    
    def add_child(self, child: "VersionTree") -> None:
        """Add a child node to this tree."""
        self.children.append(child)
    
    def find_by_id(self, artifact_id: UUID) -> Optional["VersionTree"]:
        """
        Find a node in the tree by artifact ID.
        
        Args:
            artifact_id: ID to search for
        
        Returns:
            VersionTree node if found, None otherwise
        """
        if self.artifact.artifact_id == artifact_id:
            return self
        
        for child in self.children:
            result = child.find_by_id(artifact_id)
            if result:
                return result
        
        return None
    
    def get_all_artifacts(self) -> list[EvidenceArtifact]:
        """
        Get all artifacts in this tree.
        
        Returns:
            Flat list of all artifacts
        """
        artifacts = [self.artifact]
        for child in self.children:
            artifacts.extend(child.get_all_artifacts())
        return artifacts
    
    def count(self) -> int:
        """Count total artifacts in tree."""
        return 1 + sum(child.count() for child in self.children)
    
    def max_depth(self) -> int:
        """Get maximum depth of the tree."""
        if not self.children:
            return 1
        return 1 + max(child.max_depth() for child in self.children)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "artifact": self.artifact.to_dict(),
            "children": [child.to_dict() for child in self.children],
        }
