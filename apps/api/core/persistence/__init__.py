"""
Infrastructure Module
=====================

This module contains infrastructure clients and utilities:
- Redis client for working memory and caching
- Qdrant client for episodic memory (vector storage)
- PostgreSQL client for chain-of-custody logging
- Storage abstraction for evidence files
"""

from core.persistence.postgres_client import PostgresClient, get_postgres_client
from core.persistence.qdrant_client import QdrantClient, get_qdrant_client
from core.persistence.redis_client import RedisClient, get_redis_client
from core.persistence.storage import LocalStorageBackend, StorageBackend

__all__ = [
    "RedisClient",
    "get_redis_client",
    "QdrantClient",
    "get_qdrant_client",
    "PostgresClient",
    "get_postgres_client",
    "StorageBackend",
    "LocalStorageBackend",
]
