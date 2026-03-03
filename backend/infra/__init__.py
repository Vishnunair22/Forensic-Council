"""
Infrastructure Module
=====================

This module contains infrastructure clients and utilities:
- Redis client for working memory and caching
- Qdrant client for episodic memory (vector storage)
- PostgreSQL client for chain-of-custody logging
- Storage abstraction for evidence files
"""

from infra.redis_client import RedisClient, get_redis_client
from infra.qdrant_client import QdrantClient, get_qdrant_client
from infra.postgres_client import PostgresClient, get_postgres_client
from infra.storage import StorageBackend, LocalStorageBackend

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
