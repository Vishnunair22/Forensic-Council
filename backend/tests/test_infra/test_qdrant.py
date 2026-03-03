"""
Qdrant Client Tests
===================

Tests for the Qdrant client wrapper.
"""

import pytest
from uuid import uuid4, UUID
import time

from core.exceptions import QdrantConnectionError
from infra.qdrant_client import QdrantClient
from qdrant_client.models import Distance


def unique_collection_name(prefix: str) -> str:
    """Generate a unique collection name for test isolation."""
    return f"{prefix}_{uuid4().hex[:8]}"


class TestQdrantClient:
    """Tests for QdrantClient class."""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_health_check(self, qdrant_client: QdrantClient):
        """Test Qdrant health check."""
        result = await qdrant_client.health_check()
        assert result is True
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_collection(self, qdrant_client: QdrantClient):
        """Test creating a collection."""
        collection_name = unique_collection_name("test_collection")
        
        # Create collection
        result = await qdrant_client.create_collection(
            collection_name=collection_name,
            vector_size=384,
            distance=Distance.COSINE,
        )
        assert result is True
        
        # Verify collection exists
        exists = await qdrant_client.collection_exists(collection_name)
        assert exists is True
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_collection_exists_false(self, qdrant_client: QdrantClient):
        """Test checking if non-existent collection exists."""
        exists = await qdrant_client.collection_exists("nonexistent_collection_xyz")
        assert exists is False
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_upsert_and_query(self, qdrant_client: QdrantClient):
        """Test upserting and querying vectors."""
        collection_name = unique_collection_name("test_query")
        
        # Create collection
        await qdrant_client.create_collection(
            collection_name=collection_name,
            vector_size=4,
        )
        
        # Upsert vectors
        point_id = uuid4()
        vector = [0.1, 0.2, 0.3, 0.4]
        payload = {"name": "test", "category": "example"}
        
        result = await qdrant_client.upsert(
            collection_name=collection_name,
            point_id=point_id,
            vector=vector,
            payload=payload,
        )
        assert result is True
        
        # Query for similar vectors
        query_vector = [0.1, 0.2, 0.3, 0.4]
        results = await qdrant_client.query(
            collection_name=collection_name,
            query_vector=query_vector,
            top_k=1,
        )
        
        assert len(results) == 1
        assert results[0]["id"] == str(point_id)
        assert results[0]["score"] >= 0.99  # Should be very similar
        assert results[0]["payload"]["name"] == "test"
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_batch_upsert(self, qdrant_client: QdrantClient):
        """Test batch upserting vectors."""
        collection_name = unique_collection_name("test_batch")
        
        # Create collection
        await qdrant_client.create_collection(
            collection_name=collection_name,
            vector_size=4,
        )
        
        # Batch upsert
        points = [
            (uuid4(), [0.1, 0.2, 0.3, 0.4], {"id": 1}),
            (uuid4(), [0.5, 0.6, 0.7, 0.8], {"id": 2}),
            (uuid4(), [0.9, 1.0, 0.1, 0.2], {"id": 3}),
        ]
        
        result = await qdrant_client.batch_upsert(
            collection_name=collection_name,
            points=points,
        )
        assert result is True
        
        # Query to verify
        results = await qdrant_client.query(
            collection_name=collection_name,
            query_vector=[0.1, 0.2, 0.3, 0.4],
            top_k=3,
        )
        assert len(results) == 3
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_query_with_filter(self, qdrant_client: QdrantClient):
        """Test querying with filter conditions."""
        collection_name = unique_collection_name("test_filter")
        
        # Create collection
        await qdrant_client.create_collection(
            collection_name=collection_name,
            vector_size=4,
        )
        
        # Upsert vectors with different categories
        await qdrant_client.upsert(
            collection_name=collection_name,
            point_id=uuid4(),
            vector=[0.1, 0.2, 0.3, 0.4],
            payload={"category": "A", "name": "first"},
        )
        await qdrant_client.upsert(
            collection_name=collection_name,
            point_id=uuid4(),
            vector=[0.2, 0.3, 0.4, 0.5],
            payload={"category": "B", "name": "second"},
        )
        
        # Query with filter
        results = await qdrant_client.query(
            collection_name=collection_name,
            query_vector=[0.1, 0.2, 0.3, 0.4],
            top_k=10,
            filter_conditions={"category": "A"},
        )
        
        assert len(results) == 1
        assert results[0]["payload"]["category"] == "A"
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_point(self, qdrant_client: QdrantClient):
        """Test getting a specific point by ID."""
        collection_name = unique_collection_name("test_get")
        
        # Create collection
        await qdrant_client.create_collection(
            collection_name=collection_name,
            vector_size=4,
        )
        
        # Upsert vector
        point_id = uuid4()
        vector = [0.1, 0.2, 0.3, 0.4]
        payload = {"name": "test_point"}
        
        await qdrant_client.upsert(
            collection_name=collection_name,
            point_id=point_id,
            vector=vector,
            payload=payload,
        )
        
        # Get point
        result = await qdrant_client.get(
            collection_name=collection_name,
            point_id=point_id,
        )
        
        assert result is not None
        assert result["id"] == str(point_id)
        # Note: Qdrant normalizes vectors with COSINE distance, so we check dimensions
        assert len(result["vector"]) == 4
        assert result["payload"]["name"] == "test_point"
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_nonexistent_point(self, qdrant_client: QdrantClient):
        """Test getting a point that doesn't exist."""
        collection_name = unique_collection_name("test_get_nonexistent")
        
        # Create collection
        await qdrant_client.create_collection(
            collection_name=collection_name,
            vector_size=4,
        )
        
        # Try to get non-existent point
        result = await qdrant_client.get(
            collection_name=collection_name,
            point_id=uuid4(),
        )
        
        assert result is None
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_delete_point(self, qdrant_client: QdrantClient):
        """Test deleting a point."""
        collection_name = unique_collection_name("test_delete")
        
        # Create collection
        await qdrant_client.create_collection(
            collection_name=collection_name,
            vector_size=4,
        )
        
        # Upsert vector
        point_id = uuid4()
        await qdrant_client.upsert(
            collection_name=collection_name,
            point_id=point_id,
            vector=[0.1, 0.2, 0.3, 0.4],
        )
        
        # Delete point
        result = await qdrant_client.delete(
            collection_name=collection_name,
            point_id=point_id,
        )
        assert result is True
        
        # Verify deleted
        result = await qdrant_client.get(
            collection_name=collection_name,
            point_id=point_id,
        )
        assert result is None
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_collection_info(self, qdrant_client: QdrantClient):
        """Test getting collection info."""
        collection_name = unique_collection_name("test_info")
        
        # Create collection
        await qdrant_client.create_collection(
            collection_name=collection_name,
            vector_size=4,
        )
        
        # Upsert some vectors
        await qdrant_client.upsert(
            collection_name=collection_name,
            point_id=uuid4(),
            vector=[0.1, 0.2, 0.3, 0.4],
        )
        
        # Get info
        info = await qdrant_client.get_collection_info(collection_name)
        
        assert info["name"] == collection_name
        assert info["vectors_count"] == 1
        assert info["points_count"] == 1
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_delete_collection(self, qdrant_client: QdrantClient):
        """Test deleting a collection."""
        collection_name = unique_collection_name("test_delete_final")
        
        # Create collection
        await qdrant_client.create_collection(
            collection_name=collection_name,
            vector_size=4,
        )
        
        # Verify exists
        assert await qdrant_client.collection_exists(collection_name)
        
        # Delete collection
        result = await qdrant_client.delete_collection(collection_name)
        assert result is True
        
        # Verify deleted
        assert not await qdrant_client.collection_exists(collection_name)
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_context_manager(self):
        """Test using QdrantClient as async context manager."""
        async with QdrantClient() as client:
            result = await client.health_check()
            assert result is True
