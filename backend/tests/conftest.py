"""
Shared pytest fixtures for Forensic Council backend tests.
"""
import os
import pytest

# Set required environment variables before importing any modules
# Note: These must be set before any core imports
os.environ.setdefault("LLM_API_KEY", "gsk_test_key_12345678901234567890123456789012")
os.environ.setdefault("GROQ_API_KEY", "gsk_test_key_12345678901234567890123456789012")
os.environ.setdefault("LLM_PROVIDER", "groq")
os.environ.setdefault("SIGNING_KEY", "a" * 64)
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")


@pytest.fixture
def sample_session_id() -> str:
    return "test-session-12345"


@pytest.fixture
def sample_case_id() -> str:
    return "CASE-1697000000"


@pytest.fixture
def sample_investigator_id() -> str:
    return "REQ-12345"
