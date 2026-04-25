"""
Evidence Store Module
=====================

Manages immutable evidence artifact storage with versioning.
"""

import hashlib
from typing import Any
from uuid import UUID

from core.custody_logger import CustodyLogger, EntryType
from core.evidence import ArtifactType, EvidenceArtifact, VersionTree
from core.exceptions import ForensicCouncilBaseException
from core.persistence.postgres_client import PostgresClient, get_postgres_client
from core.persistence.storage import LocalStorageBackend, StorageBackend
from core.structured_logging import get_logger

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
        postgres_client: PostgresClient | None = None,
        storage_backend: StorageBackend | None = None,
        custody_logger: CustodyLogger | None = None,
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
            self._storage = LocalStorageBackend()
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

    async def _read_file(self, file_path: str) -> bytes:
        """
        Read file contents asynchronously.

        Args:
            file_path: Path to file

        Returns:
            File contents as bytes
        """
        import asyncio

        def _read():
            with open(file_path, "rb") as f:
                return f.read()

        return await asyncio.to_thread(_read)

    async def _compute_file_hash(self, file_path: str) -> str:
        """Compute SHA-256 hash of a file using chunked streaming to avoid OOM."""
        import asyncio
        import hashlib

        def _hash_sync():
            sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):  # 1MB chunks
                    sha256.update(chunk)
            return sha256.hexdigest()

        return await asyncio.to_thread(_hash_sync)

    async def ingest(
        self,
        file_path: str,
        session_id: UUID,
        agent_id: str,
        artifact_type: ArtifactType = ArtifactType.ORIGINAL,
        action: str = "ingest",
        metadata: dict[str, Any] | None = None,
    ) -> EvidenceArtifact:
        """
        Ingest a file as evidence.

        Computes hash using streaming, copies to immutable storage,
        creates artifact record, and logs to chain of custody.
        """
        try:
            # Compute hash using chunked streaming (memory-safe)
            content_hash = await self._compute_file_hash(file_path)

            # Create artifact record placeholder (path updated after storage)
            artifact = EvidenceArtifact.create_root(
                artifact_type=artifact_type,
                file_path="",
                content_hash=content_hash,
                action=action,
                agent_id=agent_id,
                session_id=session_id,
                metadata=metadata,
            )

            # Store file in immutable storage using direct file copy (memory-safe)
            stored_path = await self._storage.store(
                root_id=artifact.root_id,
                artifact_id=artifact.artifact_id,
                file_path=file_path,
            )
            artifact.file_path = stored_path

            # Save to database
            await self._save_artifact(artifact)

            # Log to chain of custody
            if self._custody_logger:
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
                "Ingested evidence artifact (memory-safe)",
                artifact_id=str(artifact.artifact_id),
                root_id=str(artifact.root_id),
                session_id=str(session_id),
            )

            return artifact

        except OSError as e:
            # Disk I/O errors - potentially recoverable
            logger.error(
                "Disk I/O error during evidence ingest",
                file_path=file_path,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            raise EvidenceStoreError(
                f"Storage I/O failed for {file_path}",
                details={
                    "file_path": file_path,
                    "error_type": type(e).__name__,
                    "recoverable": True,
                    "error": str(e),
                },
            )
        except PermissionError as e:
            # Permission denied - critical security issue
            logger.critical(
                "Permission denied during evidence ingest", file_path=file_path, error=str(e)
            )
            raise EvidenceStoreError(
                f"Permission denied: {file_path}",
                details={
                    "file_path": file_path,
                    "error_type": "PermissionError",
                    "recoverable": False,
                    "error": str(e),
                },
            )
        except EvidenceStoreError:
            # Re-raise as-is
            raise
        except Exception as e:
            # Unexpected errors
            logger.error(
                "Unexpected error during evidence ingest",
                file_path=file_path,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            raise EvidenceStoreError(
                f"Failed to ingest evidence: {file_path}. Cause: {repr(e)}",
                details={
                    "file_path": file_path,
                    "error_type": type(e).__name__,
                    "recoverable": False,
                    "error": str(e),
                },
            )

    async def create_derivative(
        self,
        parent: EvidenceArtifact,
        data: bytes,
        artifact_type: ArtifactType,
        action: str,
        agent_id: str,
        metadata: dict[str, Any] | None = None,
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
            if self._custody_logger:
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
        """Save artifact to database (auto-creates table if missing)."""
        if self._postgres is None:
            logger.warning("EvidenceStore: no postgres client, skipping DB save")
            return

        query = """
            INSERT INTO evidence_artifacts (
                artifact_id, parent_id, root_id, artifact_type,
                file_path, content_hash, action, agent_id,
                session_id, timestamp_utc, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """

        args = (
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

        try:
            await self._postgres.execute(query, *args)
        except Exception as e:
            if "evidence_artifacts" in str(e).lower() and (
                "does not exist" in str(e).lower() or "undefined" in str(e).lower()
            ):
                # Auto-create the table and retry
                logger.warning("evidence_artifacts table missing — creating inline")
                create_sql = """
                    CREATE TABLE IF NOT EXISTS evidence_artifacts (
                        artifact_id   UUID PRIMARY KEY,
                        parent_id     UUID REFERENCES evidence_artifacts(artifact_id),
                        root_id       UUID NOT NULL,
                        artifact_type VARCHAR(64) NOT NULL,
                        file_path     TEXT NOT NULL,
                        content_hash  VARCHAR(64) NOT NULL,
                        action        TEXT NOT NULL,
                        agent_id      VARCHAR(64) NOT NULL,
                        session_id    UUID NOT NULL,
                        timestamp_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        metadata      JSONB NOT NULL DEFAULT '{}'
                    );
                    CREATE INDEX IF NOT EXISTS idx_ev_root ON evidence_artifacts(root_id);
                    CREATE INDEX IF NOT EXISTS idx_ev_session ON evidence_artifacts(session_id);
                    CREATE INDEX IF NOT EXISTS idx_ev_parent ON evidence_artifacts(parent_id);
                    CREATE INDEX IF NOT EXISTS idx_ev_type ON evidence_artifacts(artifact_type);
                """
                await self._postgres.execute(create_sql)
                await self._postgres.execute(query, *args)
            else:
                raise

    async def get_artifact(self, artifact_id: UUID) -> EvidenceArtifact | None:
        """
        Get an artifact by ID.

        Args:
            artifact_id: Artifact UUID

        Returns:
            EvidenceArtifact if found, None otherwise
        """
        if self._postgres is None:
            return None

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

    async def get_version_tree(self, root_id: UUID) -> VersionTree | None:
        """
        Get the version tree for a root artifact.

        Args:
            root_id: Root artifact UUID

        Returns:
            VersionTree if found, None otherwise
        """
        if self._postgres is None:
            return None

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
        {a.artifact_id: a for a in artifacts}
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
            # Use async retrieve so we don't block the event loop on disk I/O.
            data = await self._storage.retrieve(artifact.file_path)

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

    async def get_all_for_session(self, session_id: UUID) -> list[EvidenceArtifact]:
        """
        Get all artifacts for a session in a single batch query.
        Prevents N+1 patterns when rendering summaries of large investigations.

        Args:
            session_id: Investigation session UUID

        Returns:
            List of EvidenceArtifact objects
        """
        if self._postgres is None:
            return []

        query = """
            SELECT artifact_id, parent_id, root_id, artifact_type,
                   file_path, content_hash, action, agent_id,
                   session_id, timestamp_utc, metadata
            FROM evidence_artifacts
            WHERE session_id = $1
            ORDER BY timestamp_utc ASC
        """

        rows = await self._postgres.fetch(query, session_id)

        return [
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


# Singleton instance
_evidence_store: EvidenceStore | None = None


async def get_evidence_store() -> EvidenceStore:
    """
    Get or create the evidence store singleton.

    Returns:
        EvidenceStore instance
    """
    global _evidence_store
    if _evidence_store is None:
        postgres = await get_postgres_client()
        storage = LocalStorageBackend()
        custody_logger = CustodyLogger(postgres_client=postgres)
        _evidence_store = EvidenceStore(
            postgres_client=postgres,
            storage_backend=storage,
            custody_logger=custody_logger,
        )
        # Initialize the store (equivalent to __aenter__ but explicit)
        if _evidence_store._postgres is None:
            _evidence_store._postgres = postgres
        if _evidence_store._storage is None:
            _evidence_store._storage = storage
        if _evidence_store._custody_logger is None:
            _evidence_store._custody_logger = custody_logger
    return _evidence_store


async def close_evidence_store() -> None:
    """Close the evidence store singleton."""
    global _evidence_store
    if _evidence_store is not None:
        if _evidence_store._postgres:
            await _evidence_store._postgres.disconnect()
        _evidence_store = None
