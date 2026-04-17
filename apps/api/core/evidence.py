"""
Evidence Module
===============

Defines evidence artifact models and types for forensic analysis.
Supports immutable versioning and chain-of-custody tracking.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Optional
from uuid import UUID, uuid4


class EvidenceVerdict(StrEnum):
    """
    Strict semantic verdict for every tool output and finding.

    Every piece of forensic evidence MUST resolve to exactly one of these
    five values.  This eliminates the semantic conflation where a SKIPPED
    tool was represented as CONFIRMED with confidence=1.0.

    POSITIVE        — Evidence of manipulation / anomaly detected.
    NEGATIVE        — No manipulation / anomaly detected.
    INCONCLUSIVE    — Insufficient signal to decide either way.
    NOT_APPLICABLE  — Tool does not apply to this media type (confidence
                      MUST be None).
    ERROR           — Tool failed or produced unusable output (confidence
                      SHOULD be None or 0.0).
    """

    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    ERROR = "ERROR"


class ArtifactType(StrEnum):
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
    parent_id: UUID | None
    root_id: UUID
    artifact_type: ArtifactType
    file_path: str
    content_hash: str
    action: str
    agent_id: str
    session_id: UUID
    timestamp_utc: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def mime_type(self) -> str:
        """Convenience accessor for the MIME type stored in metadata."""
        return (self.metadata or {}).get("mime_type", "") or ""

    @classmethod
    def create_root(
        cls,
        artifact_type: ArtifactType,
        file_path: str,
        content_hash: str,
        action: str,
        agent_id: str,
        session_id: UUID,
        metadata: dict[str, Any] | None = None,
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
        metadata: dict[str, Any] | None = None,
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
