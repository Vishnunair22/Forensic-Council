"""
Pytest Configuration and Fixtures
==================================

Shared fixtures for testing the Forensic Council system.
Provides test clients, mock data, and test infrastructure.
"""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator
from uuid import uuid4, UUID

import pytest
import pytest_asyncio

# Set test environment before importing modules
os.environ["APP_ENV"] = "testing"
os.environ["REDIS_HOST"] = "localhost"
os.environ["REDIS_PORT"] = "6380"
os.environ["QDRANT_HOST"] = "localhost"
os.environ["QDRANT_PORT"] = "6333"
os.environ["POSTGRES_HOST"] = "localhost"
os.environ["POSTGRES_PORT"] = "5432"
os.environ["POSTGRES_USER"] = "forensic_user"
os.environ["POSTGRES_PASSWORD"] = "forensic_pass"
os.environ["POSTGRES_DB"] = "forensic_council"

from core.config import Settings, get_settings
from core.logging import get_logger
from infra.redis_client import RedisClient, close_redis_client
from infra.qdrant_client import QdrantClient, close_qdrant_client
from infra.postgres_client import PostgresClient, close_postgres_client
from infra.storage import LocalStorageBackend

logger = get_logger(__name__)


# Event loop fixture for async tests
@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Test settings fixture
@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Get test settings."""
    # Clear the cache to ensure fresh settings
    get_settings.cache_clear()
    settings = get_settings()
    return settings


# Autouse cleanup fixture
@pytest_asyncio.fixture(scope="function", autouse=True)
async def cleanup_singletons():
    """Clear singleton clients after each test to prevent event loop closed errors."""
    yield
    await close_postgres_client()
    await close_qdrant_client()
    # close_redis_client is synchronous or async? Let's assume async if others are. No, redis_client doesn't have a singleton usually, but let's check if close_redis_client exists
    # If it is async:
    try:
        await close_redis_client()
    except TypeError: # If it turns out synchronous
        close_redis_client()
    
    import infra.storage
    infra.storage._storage_backend = None


# Redis fixtures
@pytest_asyncio.fixture(scope="function")
async def redis_client() -> AsyncGenerator[RedisClient, None]:
    """Provide a Redis client for testing."""
    client = RedisClient()
    await client.connect()
    yield client
    # Cleanup
    await client.flushdb()
    await client.disconnect()


# Qdrant fixtures
@pytest_asyncio.fixture(scope="function")
async def qdrant_client() -> AsyncGenerator[QdrantClient, None]:
    """Provide a Qdrant client for testing."""
    client = QdrantClient()
    await client.connect()
    yield client
    # Cleanup - delete test collections
    try:
        await client.delete_collection("test_collection")
        await client.delete_collection("forensic_episodes")
    except Exception:
        pass
    await client.disconnect()


# PostgreSQL fixtures
@pytest_asyncio.fixture(scope="function")
async def postgres_client() -> AsyncGenerator[PostgresClient, None]:
    """Provide a PostgreSQL client for testing."""
    client = PostgresClient()
    await client.connect()
    yield client
    # Cleanup - truncate test tables
    try:
        await client.execute("TRUNCATE TABLE chain_of_custody CASCADE")
        await client.execute("TRUNCATE TABLE evidence_artifacts CASCADE")
    except Exception:
        pass
    await client.disconnect()


# Storage fixture
@pytest.fixture(scope="function")
def storage_backend() -> Generator[LocalStorageBackend, None, None]:
    """Provide a local storage backend with a temp directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        backend = LocalStorageBackend(storage_path=temp_dir)
        yield backend


# Test data fixtures
@pytest.fixture
def sample_session_id() -> UUID:
    """Provide a sample session UUID."""
    return uuid4()


@pytest.fixture
def sample_artifact_id() -> UUID:
    """Provide a sample artifact UUID."""
    return uuid4()


@pytest.fixture
def sample_agent_id() -> str:
    """Provide a sample agent ID."""
    return "Agent1_ImageIntegrity"


@pytest.fixture
def sample_case_id() -> str:
    """Provide a sample case ID."""
    return "TEST-CASE-001"


@pytest.fixture
def temp_evidence_file() -> Generator[Path, None, None]:
    """Create a temporary evidence file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        # Write minimal JPEG header
        f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
        f.write(b"\xff\xd9")  # JPEG end marker
        temp_path = Path(f.name)
    
    yield temp_path
    
    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def temp_image_file() -> Generator[Path, None, None]:
    """Create a temporary image file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        # Write minimal PNG header
        f.write(b"\x89PNG\r\n\x1a\n")  # PNG signature
        temp_path = Path(f.name)
    
    yield temp_path
    
    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def temp_audio_file() -> Generator[Path, None, None]:
    """Create a temporary audio file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        # Write minimal WAV header
        f.write(b"RIFF")
        f.write((36).to_bytes(4, "little"))  # File size - 8
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write((16).to_bytes(4, "little"))  # Subchunk size
        f.write((1).to_bytes(2, "little"))   # Audio format (PCM)
        f.write((1).to_bytes(2, "little"))   # Channels
        f.write((44100).to_bytes(4, "little"))  # Sample rate
        f.write((88200).to_bytes(4, "little"))  # Byte rate
        f.write((2).to_bytes(2, "little"))   # Block align
        f.write((16).to_bytes(2, "little"))  # Bits per sample
        f.write(b"data")
        f.write((0).to_bytes(4, "little"))   # Data size
        temp_path = Path(f.name)
    
    yield temp_path
    
    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def temp_video_file() -> Generator[Path, None, None]:
    """Create a temporary video file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        # Write minimal MP4 header (just enough to be recognized)
        f.write(b"\x00\x00\x00\x18ftypmp42")
        f.write(b"\x00\x00\x00\x00mp42isom")
        temp_path = Path(f.name)
    
    yield temp_path
    
    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


# Helper fixtures for creating test data
@pytest.fixture
def sample_custody_entry() -> dict:
    """Provide sample custody entry data."""
    return {
        "entry_type": "THOUGHT",
        "agent_id": "Agent1_ImageIntegrity",
        "session_id": str(uuid4()),
        "content": {"thought": "Analyzing image for manipulation indicators"},
        "content_hash": "abc123def456",
        "signature": "test_signature",
    }


@pytest.fixture
def sample_evidence_artifact() -> dict:
    """Provide sample evidence artifact data."""
    return {
        "artifact_type": "ORIGINAL",
        "file_path": "/test/evidence/image.jpg",
        "content_hash": "sha256:abc123def456",
        "action": "ingest",
        "agent_id": "Agent1_ImageIntegrity",
        "session_id": str(uuid4()),
        "metadata": {"original_filename": "image.jpg", "file_size": 1024},
    }


# Markers for different test types
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")
