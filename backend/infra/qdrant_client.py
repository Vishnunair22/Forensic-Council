"""
Qdrant Client Module
====================

Async Qdrant client wrapper for episodic memory (vector storage).
Supports async context managers and logs connection events.
"""

from typing import Any, Optional
from uuid import UUID
import asyncio

from qdrant_client import AsyncQdrantClient as QdrantAsyncClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

from core.config import get_settings
from core.logging import get_logger
from core.exceptions import QdrantConnectionError

logger = get_logger(__name__)

# Default collection name for episodic memory
EPISODIC_MEMORY_COLLECTION = "forensic_episodes"
DEFAULT_VECTOR_SIZE = 768


class QdrantClient:
    """
    Async Qdrant client wrapper.
    
    Provides a high-level interface for Qdrant vector operations with:
    - Async context manager support
    - Connection event logging
    - Typed exception handling
    - Collection management
    
    Usage:
        async with QdrantClient() as client:
            await client.create_collection("my_collection", vector_size=768)
            await client.upsert("my_collection", point_id, vector, payload)
            results = await client.query("my_collection", query_vector, top_k=5)
    """
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        grpc_port: Optional[int] = None,
        api_key: Optional[str] = None,
    ) -> None:
        """
        Initialize Qdrant client.
        
        Args:
            host: Qdrant host (defaults to settings)
            port: Qdrant REST API port (defaults to settings)
            grpc_port: Qdrant gRPC port (defaults to settings)
            api_key: Qdrant API key (defaults to settings)
        """
        settings = get_settings()
        self._host = host or settings.qdrant_host
        self._port = port or settings.qdrant_port
        self._grpc_port = grpc_port or settings.qdrant_grpc_port
        self._api_key = api_key or settings.qdrant_api_key
        
        self._client: Optional[QdrantAsyncClient] = None
    
    async def __aenter__(self) -> "QdrantClient":
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()
    
    async def connect(self) -> None:
        """Establish connection to Qdrant."""
        try:
            self._client = QdrantAsyncClient(
                host=self._host,
                port=self._port,
                grpc_port=self._grpc_port,
                api_key=self._api_key,
                https=False,  # Use HTTP for local development
                check_compatibility=False,  # Disable version check for compatibility
            )
            
            # Test connection by getting collections
            await self._client.get_collections()
            
            logger.info(
                "Connected to Qdrant",
                host=self._host,
                port=self._port,
                grpc_port=self._grpc_port,
            )
        except Exception as e:
            logger.error("Failed to connect to Qdrant", error=str(e))
            raise QdrantConnectionError(
                f"Failed to connect to Qdrant at {self._host}:{self._port}",
                details={"host": self._host, "port": self._port, "error": str(e)},
            )
    
    async def disconnect(self) -> None:
        """Close connection to Qdrant."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Disconnected from Qdrant")
    
    @property
    def client(self) -> QdrantAsyncClient:
        """Get the underlying Qdrant client."""
        if self._client is None:
            raise QdrantConnectionError("Qdrant client not connected. Call connect() first.")
        return self._client
    
    async def health_check(self) -> bool:
        """Test Qdrant connection."""
        try:
            result = await self.client.get_collections()
            return True
        except Exception as e:
            logger.error("Qdrant health check failed", error=str(e))
            raise QdrantConnectionError("Qdrant health check failed", details={"error": str(e)})
    
    async def collection_exists(self, collection_name: str) -> bool:
        """
        Check if a collection exists.
        
        Args:
            collection_name: Name of the collection
        
        Returns:
            True if collection exists
        """
        collections = await self.client.get_collections()
        return any(c.name == collection_name for c in collections.collections)
    
    async def create_collection(
        self,
        collection_name: str,
        vector_size: int = DEFAULT_VECTOR_SIZE,
        distance: Distance = Distance.COSINE,
    ) -> bool:
        """
        Create a new collection.
        
        Args:
            collection_name: Name of the collection
            vector_size: Size of vectors to store
            distance: Distance metric (COSINE, EUCLID, DOT)
        
        Returns:
            True if created successfully
        """
        if await self.collection_exists(collection_name):
            logger.info("Collection already exists", collection=collection_name)
            return True
        
        await self.client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=distance,
            ),
        )
        
        logger.info(
            "Created Qdrant collection",
            collection=collection_name,
            vector_size=vector_size,
            distance=distance.value,
        )
        return True
    
    async def delete_collection(self, collection_name: str) -> bool:
        """
        Delete a collection.
        
        Args:
            collection_name: Name of the collection
        
        Returns:
            True if deleted successfully
        """
        await self.client.delete_collection(collection_name)
        logger.info("Deleted Qdrant collection", collection=collection_name)
        return True
    
    async def upsert(
        self,
        collection_name: str,
        point_id: str | UUID,
        vector: list[float],
        payload: Optional[dict[str, Any]] = None,
    ) -> bool:
        """
        Insert or update a point in a collection.
        
        Args:
            collection_name: Name of the collection
            point_id: Unique identifier for the point
            vector: Vector embedding
            payload: Optional metadata payload
        
        Returns:
            True if successful
        """
        point = PointStruct(
            id=str(point_id),
            vector=vector,
            payload=payload or {},
        )
        
        await self.client.upsert(
            collection_name=collection_name,
            points=[point],
        )
        
        logger.debug(
            "Upserted point to Qdrant",
            collection=collection_name,
            point_id=str(point_id),
        )
        return True
    
    async def batch_upsert(
        self,
        collection_name: str,
        points: list[tuple[str | UUID, list[float], Optional[dict[str, Any]]]],
    ) -> bool:
        """
        Insert or update multiple points.
        
        Args:
            collection_name: Name of the collection
            points: List of (id, vector, payload) tuples
        
        Returns:
            True if successful
        """
        point_structs = [
            PointStruct(
                id=str(p[0]),
                vector=p[1],
                payload=p[2] or {},
            )
            for p in points
        ]
        
        await self.client.upsert(
            collection_name=collection_name,
            points=point_structs,
        )
        
        logger.debug(
            "Batch upserted points to Qdrant",
            collection=collection_name,
            count=len(points),
        )
        return True
    
    async def query(
        self,
        collection_name: str,
        query_vector: list[float],
        top_k: int = 5,
        filter_conditions: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """
        Query for similar vectors.
        
        Args:
            collection_name: Name of the collection
            query_vector: Query vector embedding
            top_k: Number of results to return
            filter_conditions: Optional filter conditions
        
        Returns:
            List of results with id, score, and payload
        """
        query_filter = None
        if filter_conditions:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filter_conditions.items()
            ]
            query_filter = Filter(must=conditions)
        
        results = await self.client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=top_k,
            query_filter=query_filter,
        )
        
        return [
            {
                "id": str(result.id),
                "score": result.score,
                "payload": result.payload,
            }
            for result in results.points
        ]
    
    async def get(
        self,
        collection_name: str,
        point_id: str | UUID,
    ) -> Optional[dict[str, Any]]:
        """
        Get a specific point by ID.
        
        Args:
            collection_name: Name of the collection
            point_id: Point identifier
        
        Returns:
            Point data with id, vector, and payload, or None if not found
        """
        result = await self.client.retrieve(
            collection_name=collection_name,
            ids=[str(point_id)],
            with_vectors=True,
        )
        
        if not result:
            return None
        
        point = result[0]
        return {
            "id": str(point.id),
            "vector": point.vector,
            "payload": point.payload,
        }
    
    async def delete(
        self,
        collection_name: str,
        point_id: str | UUID,
    ) -> bool:
        """
        Delete a point by ID.
        
        Args:
            collection_name: Name of the collection
            point_id: Point identifier
        
        Returns:
            True if successful
        """
        await self.client.delete(
            collection_name=collection_name,
            points_selector=[str(point_id)],
        )
        return True
    
    async def get_collection_info(self, collection_name: str) -> dict[str, Any]:
        """
        Get information about a collection.
        
        Args:
            collection_name: Name of the collection
        
        Returns:
            Collection info including vector count
        """
        info = await self.client.get_collection(collection_name)
        # Handle both old and new Qdrant API responses
        vectors_count = getattr(info, 'vectors_count', None)
        if vectors_count is None:
            # Newer Qdrant versions use points_count for total vectors
            vectors_count = info.points_count
        return {
            "name": collection_name,
            "vectors_count": vectors_count,
            "points_count": info.points_count,
            "status": info.status.value,
        }
    
    async def scroll(
        self,
        collection_name: str,
        filter_conditions: Optional[dict[str, Any]] = None,
        limit: int = 100,
        with_vectors: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Scroll through points with optional filters (filter-only query).
        
        This is the proper way to do filter-only queries in Qdrant,
        instead of using query with a zero vector.
        
        Args:
            collection_name: Name of the collection
            filter_conditions: Optional filter conditions
            limit: Maximum number of points to return
            with_vectors: Whether to include vectors in results
        
        Returns:
            List of results with id and payload
        """
        query_filter = None
        if filter_conditions:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filter_conditions.items()
            ]
            query_filter = Filter(must=conditions)
        
        results = await self.client.scroll(
            collection_name=collection_name,
            filter=query_filter,
            limit=limit,
            with_vectors=with_vectors,
        )
        
        return [
            {
                "id": str(point.id),
                "score": 1.0,  # Dummy score for consistency with query()
                "payload": point.payload,
            }
            for point in results[0]
        ]


# Singleton instance — protected by a lock to prevent concurrent init races
_qdrant_client: Optional[QdrantClient] = None
_qdrant_lock: Optional[asyncio.Lock] = None


def _get_qdrant_lock() -> asyncio.Lock:
    """Lazily create the Qdrant init lock on first use (must run inside an event loop)."""
    global _qdrant_lock
    if _qdrant_lock is None:
        _qdrant_lock = asyncio.Lock()
    return _qdrant_lock


async def get_qdrant_client() -> QdrantClient:
    """
    Get or create the Qdrant client singleton.

    Thread-safe via asyncio.Lock — concurrent callers wait rather than each
    creating their own connection to Qdrant.

    Returns:
        QdrantClient instance
    """
    global _qdrant_client
    if _qdrant_client is not None:
        return _qdrant_client
    async with _get_qdrant_lock():
        # Double-checked locking
        if _qdrant_client is None:
            client = QdrantClient()
            await client.connect()
            _qdrant_client = client
    return _qdrant_client


async def close_qdrant_client() -> None:
    """Close the Qdrant client singleton."""
    global _qdrant_client
    async with _get_qdrant_lock():
        if _qdrant_client is not None:
            await _qdrant_client.disconnect()
            _qdrant_client = None
