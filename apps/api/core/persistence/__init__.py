"""
Infrastructure Module
=====================

This module contains infrastructure clients and utilities:
- Redis client for working memory and caching
- Qdrant client for episodic memory (vector storage)
- PostgreSQL client for chain-of-custody logging
- Storage abstraction for evidence files
"""

from core.persistence.evidence_store import EvidenceStore, get_evidence_store
from core.persistence.postgres_client import (
    PostgresClient,
    close_postgres_client,
    get_postgres_client,
)
from core.persistence.qdrant_client import QdrantClient, close_qdrant_client, get_qdrant_client
from core.persistence.redis_client import RedisClient, close_redis_client, get_redis_client
from core.persistence.storage import LocalStorageBackend, StorageBackend

__all__ = [
    "RedisClient",
    "get_redis_client",
    "close_redis_client",
    "QdrantClient",
    "get_qdrant_client",
    "close_qdrant_client",
    "PostgresClient",
    "get_postgres_client",
    "close_postgres_client",
    "StorageBackend",
    "LocalStorageBackend",
    "EvidenceStore",
    "get_evidence_store",
]
