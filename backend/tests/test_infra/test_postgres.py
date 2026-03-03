"""
PostgreSQL Client Tests
=======================

Tests for the PostgreSQL client wrapper.
"""

import pytest
from uuid import uuid4, UUID
from datetime import datetime, timezone

from core.exceptions import DatabaseConnectionError
from infra.postgres_client import PostgresClient


class TestPostgresClient:
    """Tests for PostgresClient class."""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_health_check(self, postgres_client: PostgresClient):
        """Test PostgreSQL health check."""
        result = await postgres_client.health_check()
        assert result is True
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_execute(self, postgres_client: PostgresClient):
        """Test executing a simple query."""
        result = await postgres_client.execute("SELECT 1")
        assert "SELECT" in result
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_fetch(self, postgres_client: PostgresClient):
        """Test fetching rows."""
        rows = await postgres_client.fetch("SELECT $1::int as value", 42)
        
        assert len(rows) == 1
        assert rows[0]["value"] == 42
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_fetch_one(self, postgres_client: PostgresClient):
        """Test fetching a single row."""
        row = await postgres_client.fetch_one("SELECT $1::text as message", "hello")
        
        assert row is not None
        assert row["message"] == "hello"
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_fetch_one_no_result(self, postgres_client: PostgresClient):
        """Test fetching a single row when no result."""
        row = await postgres_client.fetch_one("SELECT 1 WHERE FALSE")
        
        assert row is None
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_fetch_val(self, postgres_client: PostgresClient):
        """Test fetching a single value."""
        value = await postgres_client.fetch_val("SELECT $1::int + $2::int", 10, 20)
        
        assert value == 30
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_execute_many(self, postgres_client: PostgresClient):
        """Test executing multiple queries."""
        # Create temp table
        await postgres_client.execute("""
            CREATE TEMP TABLE test_many (
                id int,
                value text
            )
        """)
        
        # Insert multiple rows
        args_list = [
            (1, "one"),
            (2, "two"),
            (3, "three"),
        ]
        await postgres_client.execute_many(
            "INSERT INTO test_many (id, value) VALUES ($1, $2)",
            args_list,
        )
        
        # Verify
        rows = await postgres_client.fetch("SELECT * FROM test_many ORDER BY id")
        assert len(rows) == 3
        assert rows[0]["value"] == "one"
        assert rows[1]["value"] == "two"
        assert rows[2]["value"] == "three"
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_insert_and_select_chain_of_custody(self, postgres_client: PostgresClient):
        """Test inserting and selecting from chain_of_custody table."""
        session_id = uuid4()
        entry_id = uuid4()
        
        # Insert entry
        await postgres_client.execute("""
            INSERT INTO chain_of_custody 
            (entry_id, entry_type, agent_id, session_id, timestamp_utc, content, content_hash, signature)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
            entry_id,
            "THOUGHT",
            "Agent1_ImageIntegrity",
            session_id,
            datetime.now(timezone.utc),
            {"thought": "Test thought"},
            "hash123",
            "signature123",
        )
        
        # Select entry
        row = await postgres_client.fetch_one(
            "SELECT * FROM chain_of_custody WHERE entry_id = $1",
            entry_id,
        )
        
        assert row is not None
        assert row["entry_type"] == "THOUGHT"
        assert row["agent_id"] == "Agent1_ImageIntegrity"
        assert row["session_id"] == session_id
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_transaction_commit(self, postgres_client: PostgresClient):
        """Test transaction commit."""
        session_id = uuid4()
        
        async with postgres_client.transaction() as tx:
            await tx.execute("""
                INSERT INTO chain_of_custody 
                (entry_type, agent_id, session_id, timestamp_utc, content, content_hash, signature)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
                "THOUGHT",
                "Agent1_ImageIntegrity",
                session_id,
                datetime.now(timezone.utc),
                {"thought": "Transaction test"},
                "hash_tx",
                "sig_tx",
            )
        
        # Verify committed
        rows = await postgres_client.fetch(
            "SELECT * FROM chain_of_custody WHERE session_id = $1",
            session_id,
        )
        assert len(rows) == 1
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_transaction_rollback(self, postgres_client: PostgresClient):
        """Test transaction rollback on error."""
        session_id = uuid4()
        
        try:
            async with postgres_client.transaction() as tx:
                await tx.execute("""
                    INSERT INTO chain_of_custody 
                    (entry_type, agent_id, session_id, timestamp_utc, content, content_hash, signature)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                    "THOUGHT",
                    "Agent1_ImageIntegrity",
                    session_id,
                    datetime.now(timezone.utc),
                    {"thought": "Rollback test"},
                    "hash_rb",
                    "sig_rb",
                )
                # Force an error
                raise Exception("Test error")
        except Exception:
            pass
        
        # Verify rolled back
        rows = await postgres_client.fetch(
            "SELECT * FROM chain_of_custody WHERE session_id = $1",
            session_id,
        )
        assert len(rows) == 0
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_context_manager(self):
        """Test using PostgresClient as async context manager."""
        async with PostgresClient() as client:
            result = await client.health_check()
            assert result is True
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_jsonb_operations(self, postgres_client: PostgresClient):
        """Test JSONB operations."""
        session_id = uuid4()
        entry_id = uuid4()
        
        # Insert with complex JSONB
        content = {
            "thought": "Analyzing image",
            "metadata": {
                "confidence": 0.95,
                "regions": [{"x": 0, "y": 0}, {"x": 100, "y": 100}],
            },
        }
        
        await postgres_client.execute("""
            INSERT INTO chain_of_custody 
            (entry_id, entry_type, agent_id, session_id, timestamp_utc, content, content_hash, signature)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
            entry_id,
            "THOUGHT",
            "Agent1_ImageIntegrity",
            session_id,
            datetime.now(timezone.utc),
            content,
            "hash_json",
            "sig_json",
        )
        
        # Query JSONB
        row = await postgres_client.fetch_one(
            "SELECT content->>'thought' as thought, content->'metadata'->>'confidence' as confidence FROM chain_of_custody WHERE entry_id = $1",
            entry_id,
        )
        
        assert row is not None
        assert row["thought"] == "Analyzing image"
        assert row["confidence"] == "0.95"
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_uuid_handling(self, postgres_client: PostgresClient):
        """Test UUID handling."""
        session_id = uuid4()
        entry_id = uuid4()
        
        # Insert with UUID
        await postgres_client.execute("""
            INSERT INTO chain_of_custody 
            (entry_id, entry_type, agent_id, session_id, timestamp_utc, content, content_hash, signature)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
            entry_id,
            "THOUGHT",
            "Agent1_ImageIntegrity",
            session_id,
            datetime.now(timezone.utc),
            {"test": "uuid"},
            "hash_uuid",
            "sig_uuid",
        )
        
        # Query by UUID
        row = await postgres_client.fetch_one(
            "SELECT entry_id, session_id FROM chain_of_custody WHERE entry_id = $1",
            entry_id,
        )
        
        assert row is not None
        assert row["entry_id"] == entry_id
        assert row["session_id"] == session_id
