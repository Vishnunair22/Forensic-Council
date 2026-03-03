"""
Storage Backend Module
======================

Immutable file storage abstraction for evidence artifacts.
Provides a local filesystem implementation as a stub for production cloud storage.
"""

import hashlib
import shutil
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from core.config import get_settings
from core.logging import get_logger
from core.exceptions import EvidenceIntegrityError, EvidenceNotFoundError

logger = get_logger(__name__)


class StorageBackend(ABC):
    """
    Abstract base class for storage backends.
    
    Defines the interface for immutable evidence storage.
    Implementations can use local filesystem, S3, GCS, etc.
    """
    
    @abstractmethod
    async def store(
        self,
        file_path: str,
        root_id: UUID,
        artifact_id: UUID,
    ) -> str:
        """
        Store a file in immutable storage.
        
        Args:
            file_path: Path to the source file
            root_id: Root artifact ID for directory organization
            artifact_id: Artifact ID for the stored file
        
        Returns:
            Path to the stored file
        
        Raises:
            EvidenceIntegrityError: If file cannot be stored
        """
        pass
    
    @abstractmethod
    async def store_data(
        self,
        data: bytes,
        root_id: UUID,
        artifact_id: UUID,
        extension: str = ".bin",
    ) -> str:
        """
        Store raw data in immutable storage.
        
        Args:
            data: Raw bytes to store
            root_id: Root artifact ID for directory organization
            artifact_id: Artifact ID for the stored file
            extension: File extension to use
        
        Returns:
            Path to the stored file
        """
        pass
    
    @abstractmethod
    async def retrieve(self, storage_path: str) -> bytes:
        """
        Retrieve file contents from storage.
        
        Args:
            storage_path: Path to the stored file
        
        Returns:
            File contents as bytes
        
        Raises:
            EvidenceNotFoundError: If file not found
        """
        pass
    
    @abstractmethod
    async def compute_hash(self, storage_path: str) -> str:
        """
        Compute SHA-256 hash of a stored file.
        
        Args:
            storage_path: Path to the stored file
        
        Returns:
            Hex-encoded SHA-256 hash
        """
        pass
    
    @abstractmethod
    async def exists(self, storage_path: str) -> bool:
        """
        Check if a file exists in storage.
        
        Args:
            storage_path: Path to check
        
        Returns:
            True if file exists
        """
        pass
    
    @abstractmethod
    async def get_size(self, storage_path: str) -> int:
        """
        Get the size of a stored file.
        
        Args:
            storage_path: Path to the stored file
        
        Returns:
            File size in bytes
        """
        pass


class LocalStorageBackend(StorageBackend):
    """
    Local filesystem storage backend.
    
    Stores files in an immutable directory structure organized by root_id.
    This is a stub implementation - production should use cloud storage (S3, GCS).
    
    Directory structure:
        {storage_path}/
            {root_id}/
                {artifact_id}.ext
                {artifact_id}_derivative.ext
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize local storage backend.
        
        Args:
            storage_path: Base path for storage (defaults to settings)
        """
        settings = get_settings()
        self._storage_path = Path(storage_path or settings.evidence_storage_path)
        self._ensure_storage_directory()
    
    def _ensure_storage_directory(self) -> None:
        """Ensure the storage directory exists."""
        self._storage_path.mkdir(parents=True, exist_ok=True)
        logger.info("Storage directory initialized", path=str(self._storage_path))
    
    def _get_artifact_dir(self, root_id: UUID) -> Path:
        """Get the directory for a root artifact."""
        return self._storage_path / str(root_id)
    
    def _get_extension(self, file_path: str) -> str:
        """Get file extension from path."""
        return Path(file_path).suffix or ".bin"
    
    async def store(
        self,
        root_id: UUID,
        artifact_id: UUID,
        data: Optional[bytes] = None,
        file_path: Optional[str] = None,
        extension: str = ".bin",
    ) -> str:
        """
        Store a file or data in local storage.
        
        Args:
            root_id: Root artifact ID
            artifact_id: Artifact ID
            data: Raw bytes to store (mutually exclusive with file_path)
            file_path: Path to the source file (mutually exclusive with data)
            extension: File extension (used when data is provided)
        
        Returns:
            Path to the stored file
        """
        # Create artifact directory
        artifact_dir = self._get_artifact_dir(root_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        
        if data is not None:
            # Store raw data
            dest_path = artifact_dir / f"{artifact_id}{extension}"
            dest_path.write_bytes(data)
        elif file_path is not None:
            # Copy from source file
            source = Path(file_path)
            if not source.exists():
                raise EvidenceNotFoundError(
                    f"Source file not found: {file_path}",
                    details={"file_path": file_path},
                )
            extension = self._get_extension(file_path)
            dest_path = artifact_dir / f"{artifact_id}{extension}"
            shutil.copy2(source, dest_path)
        else:
            raise ValueError("Either data or file_path must be provided")
        
        # Make file read-only for immutability
        dest_path.chmod(0o444)
        
        logger.info(
            "Stored evidence",
            dest=str(dest_path),
            root_id=str(root_id),
            artifact_id=str(artifact_id),
        )
        
        return str(dest_path)
    
    async def store_data(
        self,
        data: bytes,
        root_id: UUID,
        artifact_id: UUID,
        extension: str = ".bin",
    ) -> str:
        """
        Store raw data in local storage.
        
        Args:
            data: Raw bytes to store
            root_id: Root artifact ID
            artifact_id: Artifact ID
            extension: File extension
        
        Returns:
            Path to the stored file
        """
        return await self.store(
            root_id=root_id,
            artifact_id=artifact_id,
            data=data,
            extension=extension,
        )
    
    def read(self, storage_path: str) -> bytes:
        """
        Read file contents synchronously.
        
        Args:
            storage_path: Path to the stored file
        
        Returns:
            File contents as bytes
        """
        path = Path(storage_path)
        if not path.exists():
            raise EvidenceNotFoundError(
                f"Evidence file not found: {storage_path}",
                details={"storage_path": storage_path},
            )
        
        return path.read_bytes()
    
    async def retrieve(self, storage_path: str) -> bytes:
        """
        Retrieve file contents.
        
        Args:
            storage_path: Path to the stored file
        
        Returns:
            File contents as bytes
        """
        return self.read(storage_path)
    
    async def compute_hash(self, storage_path: str) -> str:
        """
        Compute SHA-256 hash of a stored file.
        
        Args:
            storage_path: Path to the stored file
        
        Returns:
            Hex-encoded SHA-256 hash
        """
        path = Path(storage_path)
        if not path.exists():
            raise EvidenceNotFoundError(
                f"Evidence file not found: {storage_path}",
                details={"storage_path": storage_path},
            )
        
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        
        return sha256.hexdigest()
    
    async def exists(self, storage_path: str) -> bool:
        """Check if a file exists."""
        return Path(storage_path).exists()
    
    async def get_size(self, storage_path: str) -> int:
        """Get the size of a stored file."""
        path = Path(storage_path)
        if not path.exists():
            raise EvidenceNotFoundError(
                f"Evidence file not found: {storage_path}",
                details={"storage_path": storage_path},
            )
        return path.stat().st_size
    
    async def list_artifacts(self, root_id: UUID) -> list[str]:
        """
        List all artifacts under a root ID.
        
        Args:
            root_id: Root artifact ID
        
        Returns:
            List of artifact file paths
        """
        artifact_dir = self._get_artifact_dir(root_id)
        if not artifact_dir.exists():
            return []
        
        return [str(f) for f in artifact_dir.iterdir() if f.is_file()]


# Singleton instance
_storage_backend: Optional[LocalStorageBackend] = None


def get_storage_backend() -> LocalStorageBackend:
    """
    Get or create the storage backend singleton.
    
    Returns:
        LocalStorageBackend instance
    """
    global _storage_backend
    if _storage_backend is None:
        _storage_backend = LocalStorageBackend()
    return _storage_backend
