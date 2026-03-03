"""
Evidence Store Module
=====================

Manages immutable evidence artifact storage with versioning.
"""

import hashlib
import os
import shutil
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from core.config import get_settings
from core.evidence import EvidenceArtifact, ArtifactType, VersionTree
from core.custody_logger import CustodyLogger, EntryType
from core.logging import get_logger
from core.exceptions import ForensicCouncilBaseException
from infra.postgres_client import PostgresClient, get_postgres_client
from infra.storage import StorageBackend

logger = get_logger(__name__)


class EvidenceStoreError(ForensicCouncilBaseException):
    """Exception raised for evidence store errors."""
    pass


class EvidenceStore:
    """
    Manages immutable evidence artifact storage.
    
    Provides:
    - Evidence ingestion with hash verification
    - Derivative artifact creation
    - Version tree tracking
    - Integrity verification
    
    Usage:
        async with EvidenceStore() as store:
            # Ingest original evidence
            artifact = await store.ingest(
                file_path="/path/to/evidence.jpg",
                session_id=session_uuid,
                agent_id="ingestion_agent"
            )
            
            # Create derivative
            derivative = await store.create_derivative(
                parent=artifact,
                data=processed_bytes,
                artifact_type=ArtifactType.ELA_OUTPUT,
                action="error_level_analysis",
                agent_id="image_agent"
            )
    """
    
    def __init__(
        self,
        postgres_client: Optional[PostgresClient] = None,
        storage_backend: Optional[StorageBackend] = None,
        custody_logger: Optional[CustodyLogger] = None,
    ) -> None:
        """
        Initialize the evidence store.
        
        Args:
            postgres_client: Optional PostgreSQL client
            storage_backend: Optional storage backend
            custody_logger: Optional custody logger
        """
        self._postgres = postgres_client
        self._storage = storage_backend
        self._custody_logger = custody_logger
        self._owned_client = postgres_client is None
        self._owned_storage = storage_backend is None
        self._owned_logger = custody_logger is None
    
    async def __aenter__(self) -> "EvidenceStore":
        """Async context manager entry."""
        if self._postgres is None:
            self._postgres = await get_postgres_client()
        if self._storage is None:
            self._storage = StorageBackend()
        if self._custody_logger is None:
            self._custody_logger = CustodyLogger(postgres_client=self._postgres)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        if self._owned_client and self._postgres:
            await self._postgres.disconnect()
            self._postgres = None
    
    def _compute_hash(self, data: bytes) -> str:
        """
        Compute SHA-256 hash of data.
        
        Args:
            data: Bytes to hash
        
        Returns:
            Hex-encoded SHA-256 hash
        """
        return hashlib.sha256(data).hexdigest()
    
    def _read_file(self, file_path: str) -> bytes:
        """
        Read file contents.
        
        Args:
            file_path: Path to file
        
        Returns:
            File contents as bytes
        """
        with open(file_path, "rb") as f:
            return f.read()
    
    async def ingest(
        self,
        file_path: str,
        session_id: UUID,
        agent_id: str,
        artifact_type: ArtifactType = ArtifactType.ORIGINAL,
        action: str = "ingest",
        metadata: Optional[dict[str, Any]] = None,
    ) -> EvidenceArtifact:
        """
        Ingest a file as evidence.
        
        Computes hash, copies to immutable storage, creates artifact record,
        and logs to chain of custody.
        
        Args:
            file_path: Path to the file to ingest
            session_id: Analysis session ID
            agent_id: Agent performing ingestion
            artifact_type: Type of artifact (default: ORIGINAL)
            action: Action description (default: "ingest")
            metadata: Additional metadata
        
        Returns:
            EvidenceArtifact representing the ingested file
        
        Raises:
            EvidenceStoreError: If ingestion fails
        """
        try:
            # Read and hash file
            data = self._read_file(file_path)
            content_hash = self._compute_hash(data)
            
            # Create artifact record (root_id will be set to artifact_id)
            artifact = EvidenceArtifact.create_root(
                artifact_type=artifact_type,
                file_path="",  # Will be updated after storage
                content_hash=content_hash,
                action=action,
                agent_id=agent_id,
                session_id=session_id,
                metadata=metadata,
            )
            
            # Store file in immutable storage
            stored_path = await self._storage.store(
                root_id=artifact.root_id,
                artifact_id=artifact.artifact_id,
                data=data,
            )
            artifact.file_path = stored_path
            
            # Save to database
            await self._save_artifact(artifact)
            
            # Log to chain of custody
            await self._custody_logger.log_entry(
                agent_id=agent_id,
                session_id=session_id,
                entry_type=EntryType.ARTIFACT_VERSION,
                content={
                    "artifact_id": str(artifact.artifact_id),
                    "root_id": str(artifact.root_id),
                    "artifact_type": artifact.artifact_type.value,
                    "content_hash": content_hash,
                    "action": action,
                    "file_path": stored_path,
                },
            )
            
            logger.info(
                "Ingested evidence artifact",
                artifact_id=str(artifact.artifact_id),
                root_id=str(artifact.root_id),
                content_hash=content_hash[:16] + "...",
                session_id=str(session_id),
            )
            
            return artifact
            
        except Exception as e:
            logger.error("Failed to ingest evidence", error=str(e), file_path=file_path)
            raise EvidenceStoreError(
                f"Failed to ingest evidence: {file_path}",
                details={"file_path": file_path, "error": str(e)},
            )
    
    async def create_derivative(
        self,
        parent: EvidenceArtifact,
        data: bytes,
        artifact_type: ArtifactType,
        action: str,
        agent_id: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> EvidenceArtifact:
        """
        Create a derivative artifact from a parent.
        
        Writes data to storage under same root_id, creates child artifact
        with parent_id set, and logs to chain of custody.
        
        Args:
            parent: Parent artifact
            data: Derivative data bytes
            artifact_type: Type of derivative
            action: Action that created the derivative
            agent_id: Agent that created the derivative
            metadata: Additional metadata
        
        Returns:
            EvidenceArtifact representing the derivative
        """
        try:
            # Hash the data
            content_hash = self._compute_hash(data)
            
            # Create derivative artifact
            artifact = EvidenceArtifact.create_derivative(
                parent=parent,
                artifact_type=artifact_type,
                file_path="",  # Will be updated after storage
                content_hash=content_hash,
                action=action,
                agent_id=agent_id,
                metadata=metadata,
            )
            
            # Store in same root directory
            stored_path = await self._storage.store(
                root_id=artifact.root_id,
                artifact_id=artifact.artifact_id,
                data=data,
            )
            artifact.file_path = stored_path
            
            # Save to database
            await self._save_artifact(artifact)
            
            # Log to chain of custody
            await self._custody_logger.log_entry(
                agent_id=agent_id,
                session_id=artifact.session_id,
                entry_type=EntryType.ARTIFACT_VERSION,
                content={
                    "artifact_id": str(artifact.artifact_id),
                    "parent_id": str(artifact.parent_id),
                    "root_id": str(artifact.root_id),
                    "artifact_type": artifact.artifact_type.value,
                    "content_hash": content_hash,
                    "action": action,
                    "file_path": stored_path,
                },
            )
            
            logger.info(
                "Created derivative artifact",
                artifact_id=str(artifact.artifact_id),
                parent_id=str(artifact.parent_id),
                root_id=str(artifact.root_id),
                artifact_type=artifact_type.value,
            )
            
            return artifact
            
        except Exception as e:
            logger.error("Failed to create derivative", error=str(e))
            raise EvidenceStoreError(
                "Failed to create derivative artifact",
                details={"parent_id": str(parent.artifact_id), "error": str(e)},
            )
    
    async def _save_artifact(self, artifact: EvidenceArtifact) -> None:
        """Save artifact to database."""
        query = """
            INSERT INTO evidence_artifacts (
                artifact_id, parent_id, root_id, artifact_type,
                file_path, content_hash, action, agent_id,
                session_id, timestamp_utc, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """
        
        await self._postgres.execute(
            query,
            artifact.artifact_id,
            artifact.parent_id,
            artifact.root_id,
            artifact.artifact_type.value,
            artifact.file_path,
            artifact.content_hash,
            artifact.action,
            artifact.agent_id,
            artifact.session_id,
            artifact.timestamp_utc,
            artifact.metadata,
        )
    
    async def get_artifact(self, artifact_id: UUID) -> Optional[EvidenceArtifact]:
        """
        Get an artifact by ID.
        
        Args:
            artifact_id: Artifact UUID
        
        Returns:
            EvidenceArtifact if found, None otherwise
        """
        query = """
            SELECT artifact_id, parent_id, root_id, artifact_type,
                   file_path, content_hash, action, agent_id,
                   session_id, timestamp_utc, metadata
            FROM evidence_artifacts
            WHERE artifact_id = $1
        """
        
        row = await self._postgres.fetch_one(query, artifact_id)
        
        if row is None:
            return None
        
        return EvidenceArtifact(
            artifact_id=row["artifact_id"],
            parent_id=row["parent_id"],
            root_id=row["root_id"],
            artifact_type=ArtifactType(row["artifact_type"]),
            file_path=row["file_path"],
            content_hash=row["content_hash"],
            action=row["action"],
            agent_id=row["agent_id"],
            session_id=row["session_id"],
            timestamp_utc=row["timestamp_utc"],
            metadata=row["metadata"],
        )
    
    async def get_version_tree(self, root_id: UUID) -> Optional[VersionTree]:
        """
        Get the version tree for a root artifact.
        
        Args:
            root_id: Root artifact UUID
        
        Returns:
            VersionTree if found, None otherwise
        """
        query = """
            SELECT artifact_id, parent_id, root_id, artifact_type,
                   file_path, content_hash, action, agent_id,
                   session_id, timestamp_utc, metadata
            FROM evidence_artifacts
            WHERE root_id = $1
            ORDER BY timestamp_utc ASC
        """
        
        rows = await self._postgres.fetch(query, root_id)
        
        if not rows:
            return None
        
        # Create artifacts from rows
        artifacts = [
            EvidenceArtifact(
                artifact_id=row["artifact_id"],
                parent_id=row["parent_id"],
                root_id=row["root_id"],
                artifact_type=ArtifactType(row["artifact_type"]),
                file_path=row["file_path"],
                content_hash=row["content_hash"],
                action=row["action"],
                agent_id=row["agent_id"],
                session_id=row["session_id"],
                timestamp_utc=row["timestamp_utc"],
                metadata=row["metadata"],
            )
            for row in rows
        ]
        
        # Build tree
        artifact_map = {a.artifact_id: a for a in artifacts}
        tree_map: dict[UUID, VersionTree] = {}
        
        # Find root (parent_id is None)
        root_artifact = None
        for artifact in artifacts:
            if artifact.parent_id is None:
                root_artifact = artifact
                break
        
        if root_artifact is None:
            return None
        
        # Create tree nodes
        for artifact in artifacts:
            tree_map[artifact.artifact_id] = VersionTree(artifact=artifact)
        
        # Link children to parents
        for artifact in artifacts:
            if artifact.parent_id is not None:
                parent_tree = tree_map.get(artifact.parent_id)
                if parent_tree:
                    parent_tree.add_child(tree_map[artifact.artifact_id])
        
        return tree_map[root_artifact.artifact_id]
    
    async def verify_artifact_integrity(self, artifact: EvidenceArtifact) -> bool:
        """
        Verify the integrity of an artifact.
        
        Recomputes hash of stored file and compares to artifact.content_hash.
        
        Args:
            artifact: Artifact to verify
        
        Returns:
            True if integrity is valid, False otherwise
        """
        try:
            # Read stored file
            data = self._storage.read(artifact.file_path)
            
            # Recompute hash
            computed_hash = self._compute_hash(data)
            
            # Compare
            if computed_hash != artifact.content_hash:
                logger.warning(
                    "Artifact integrity check failed",
                    artifact_id=str(artifact.artifact_id),
                    expected=artifact.content_hash[:16] + "...",
                    computed=computed_hash[:16] + "...",
                )
                return False
            
            logger.debug(
                "Artifact integrity verified",
                artifact_id=str(artifact.artifact_id),
            )
            return True
            
        except Exception as e:
            logger.error(
                "Failed to verify artifact integrity",
                artifact_id=str(artifact.artifact_id),
                error=str(e),
            )
            return False


# Singleton instance
_evidence_store: Optional[EvidenceStore] = None


async def get_evidence_store() -> EvidenceStore:
    """
    Get or create the evidence store singleton.
    
    Returns:
        EvidenceStore instance
    """
    global _evidence_store
    if _evidence_store is None:
        postgres = await get_postgres_client()
        _evidence_store = EvidenceStore(postgres_client=postgres)
    return _evidence_store


async def close_evidence_store() -> None:
    """Close the evidence store singleton."""
    global _evidence_store
    if _evidence_store is not None:
        if _evidence_store._postgres:
            await _evidence_store._postgres.disconnect()
        _evidence_store = None