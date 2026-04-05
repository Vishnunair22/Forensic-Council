"""
E2E Test Shared Fixtures
========================

Provides common fixtures for end-to-end tests including:
- Authenticated client sessions
- Test user creation and cleanup
- WebSocket connections
- File upload helpers
"""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Dict, Any
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.infra.postgres_client import get_postgres_client, close_postgres_client
from backend.infra.redis_client import get_redis_client, close_redis_client


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_db():
    """Create test database schema."""
    client = await get_postgres_client()
    
    # Create test tables
    await client.execute("""
        CREATE TABLE IF NOT EXISTS test_users (
            user_id VARCHAR(64) PRIMARY KEY,
            username VARCHAR(255) NOT NULL UNIQUE,
            email VARCHAR(255) UNIQUE,
            hashed_password VARCHAR(255) NOT NULL,
            role VARCHAR(64) NOT NULL DEFAULT 'investigator',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    
    yield client
    
    # Cleanup
    await client.execute("DROP TABLE IF EXISTS test_users CASCADE")
    await close_postgres_client()


@pytest_asyncio.fixture(scope="function")
async def authenticated_client(test_db) -> AsyncGenerator[AsyncClient, None]:
    """Create an authenticated HTTP client for testing."""
    from backend.core.auth import create_access_token
    
    # Create test user
    user_id = f"test_user_{uuid4().hex[:8]}"
    username = f"testuser_{uuid4().hex[:8]}"
    
    await test_db.execute(
        """
        INSERT INTO users (user_id, username, email, hashed_password, role)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id) DO NOTHING
        """,
        user_id,
        username,
        f"{username}@test.com",
        "$2b$12$dummy_hash_for_testing",  # Dummy hash
        "investigator"
    )
    
    # Create JWT token
    access_token = create_access_token(
        data={"sub": user_id, "username": username, "role": "investigator"}
    )
    
    # Create test client
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        })
        yield client
    
    # Cleanup test user
    await test_db.execute("DELETE FROM users WHERE user_id = $1", user_id)


@pytest_asyncio.fixture(scope="function")
async def admin_client(test_db) -> AsyncGenerator[AsyncClient, None]:
    """Create an authenticated admin HTTP client."""
    from backend.core.auth import create_access_token
    
    user_id = f"admin_{uuid4().hex[:8]}"
    username = f"admin_{uuid4().hex[:8]}"
    
    await test_db.execute(
        """
        INSERT INTO users (user_id, username, email, hashed_password, role)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id) DO NOTHING
        """,
        user_id,
        username,
        f"{username}@admin.com",
        "$2b$12$dummy_hash_for_testing",
        "admin"
    )
    
    access_token = create_access_token(
        data={"sub": user_id, "username": username, "role": "admin"}
    )
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        })
        yield client
    
    await test_db.execute("DELETE FROM users WHERE user_id = $1", user_id)


@pytest.fixture
def sample_evidence_file() -> Path:
    """Create a temporary sample evidence file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("Sample evidence content for testing")
        path = Path(f.name)
    
    yield path
    
    # Cleanup
    if path.exists():
        path.unlink()


@pytest.fixture
def sample_image_file() -> Path:
    """Create a temporary sample image file (minimal JPEG)."""
    # Minimal valid JPEG header
    jpeg_data = bytes([
        0xFF, 0xD8, 0xFF, 0xE0,  # SOI + APP0 marker
        0x00, 0x10, 0x4A, 0x46,  # Length + "JFIF"
        0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01,
        0x00, 0x01, 0x00, 0x00,
        0xFF, 0xD9  # EOI
    ])
    
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.jpg', delete=False) as f:
        f.write(jpeg_data)
        path = Path(f.name)
    
    yield path
    
    if path.exists():
        path.unlink()


@pytest_asyncio.fixture
async def redis_client():
    """Provide Redis client for testing."""
    client = await get_redis_client()
    yield client
    # Flush test keys
    await client.flushdb()
    await close_redis_client()


@pytest.fixture
def websocket_headers(authenticated_client) -> Dict[str, str]:
    """Get WebSocket authentication headers."""
    auth_header = authenticated_client.headers.get("Authorization", "")
    return {
        "Authorization": auth_header,
        "Sec-WebSocket-Protocol": "websocket"
    }
