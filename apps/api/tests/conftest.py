"""
Shared pytest fixtures for the Forensic Council backend test suite.
Provides mocked infrastructure (Redis, Postgres, Qdrant), auth helpers,
sample data, and a preconfigured TestClient.
"""
import io
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

# Suppress noisy passlib deprecation warnings in test output.
logging.getLogger("passlib").setLevel(logging.ERROR)

# -- Minimal environment before any backend import --

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test_user")
os.environ.setdefault("POSTGRES_PASSWORD", "test_pass")
os.environ.setdefault("POSTGRES_DB", "forensic_test")
os.environ.setdefault("REDIS_PASSWORD", "test_redis_pass")
os.environ.setdefault("NEXT_PUBLIC_DEMO_PASSWORD", "test_demo_pass")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")
os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60")
os.environ.setdefault("BOOTSTRAP_ADMIN_PASSWORD", "admin_test_123!")
os.environ.setdefault("BOOTSTRAP_INVESTIGATOR_PASSWORD", "inv_test_123!")
os.environ.setdefault("NEXT_PUBLIC_API_URL", "http://localhost:8000")

# -- Pytest configuration --

def pytest_configure(config):
    """Register custom marks to avoid warnings."""
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "requires_docker: needs running Docker stack")
    config.addinivalue_line("markers", "requires_network: needs internet access")


# -- Simple ID fixtures --

@pytest.fixture
def sample_session_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def sample_case_id() -> str:
    return "CASE-1234567890"


@pytest.fixture
def sample_investigator_id() -> str:
    return "REQ-12345"


@pytest.fixture
def sample_user_id() -> str:
    return str(uuid.uuid4())


# -- Sample files --

@pytest.fixture
def sample_jpeg_bytes() -> bytes:
    """Minimal valid JPEG bytes (SOI + EOI markers)."""
    return (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xd9"
    )


@pytest.fixture
def sample_image_file(sample_jpeg_bytes) -> io.BytesIO:
    buf = io.BytesIO(sample_jpeg_bytes)
    buf.name = "evidence.jpg"
    return buf


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"


@pytest.fixture
def sample_pdf_file(sample_pdf_bytes) -> io.BytesIO:
    buf = io.BytesIO(sample_pdf_bytes)
    buf.name = "document.pdf"
    return buf


# -- JWT / auth fixtures --

@pytest.fixture
def valid_investigator_payload(sample_user_id) -> dict:
    return {
        "sub": sample_user_id,
        "role": "investigator",
        "exp": (datetime.now(UTC) + timedelta(hours=1)).timestamp(),
    }


@pytest.fixture
def valid_admin_payload(sample_user_id) -> dict:
    return {
        "sub": sample_user_id,
        "role": "admin",
        "exp": (datetime.now(UTC) + timedelta(hours=1)).timestamp(),
    }


@pytest.fixture
def expired_payload(sample_user_id) -> dict:
    return {
        "sub": sample_user_id,
        "role": "investigator",
        "exp": (datetime.now(UTC) - timedelta(seconds=1)).timestamp(),
    }


@pytest.fixture
def auth_headers() -> dict:
    """Returns headers with a dummy Bearer token for HTTP test client calls."""
    return {"Authorization": "Bearer test-token-placeholder"}


@pytest.fixture
def admin_auth_headers() -> dict:
    return {"Authorization": "Bearer admin-token-placeholder"}


# -- Infrastructure mocks --

@pytest.fixture
def mock_redis():
    """AsyncMock Redis client with all common methods stubbed."""
    m = AsyncMock()
    m.get = AsyncMock(return_value=None)
    m.set = AsyncMock(return_value=True)
    m.delete = AsyncMock(return_value=1)
    m.exists = AsyncMock(return_value=0)
    m.expire = AsyncMock(return_value=True)
    m.incr = AsyncMock(return_value=1)
    m.incrby = AsyncMock(return_value=1)
    m.ttl = AsyncMock(return_value=3600)
    m.publish = AsyncMock(return_value=1)
    m.subscribe = AsyncMock()
    m.ping = AsyncMock(return_value=True)
    m.flushdb = AsyncMock()
    return m


@pytest.fixture
def mock_postgres():
    """AsyncMock Postgres client."""
    m = AsyncMock()
    m.fetch_one = AsyncMock(return_value=None)
    m.fetch_all = AsyncMock(return_value=[])
    m.execute = AsyncMock(return_value="OK")
    m.executemany = AsyncMock()
    m.transaction = MagicMock()
    m.transaction.return_value.__aenter__ = AsyncMock(return_value=None)
    m.transaction.return_value.__aexit__ = AsyncMock(return_value=False)
    m.ping = AsyncMock(return_value=True)
    return m


@pytest.fixture
def mock_qdrant():
    """AsyncMock Qdrant client."""
    m = AsyncMock()
    m.upsert = AsyncMock()
    m.search = AsyncMock(return_value=[])
    m.delete = AsyncMock()
    m.get_collection = AsyncMock(return_value=MagicMock(vectors_count=0))
    m.ping = AsyncMock(return_value=True)
    return m


# -- Domain fixtures --

@pytest.fixture
def sample_agent_finding() -> dict:
    return {
        "finding_id": str(uuid.uuid4()),
        "agent_id": "agent-img",
        "agent_name": "Image Integrity Expert",
        "finding_type": "ela_analysis",
        "status": "complete",
        "confidence_raw": 0.88,
        "calibrated": True,
        "calibrated_probability": 0.85,
        "court_statement": "No manipulation detected at the pixel level.",
        "robustness_caveat": False,
        "robustness_caveat_detail": None,
        "reasoning_summary": "ELA map uniform; quantization tables intact.",
        "metadata": None,
    }


@pytest.fixture
def sample_report_dto(sample_session_id, sample_case_id, sample_agent_finding) -> dict:
    return {
        "report_id": str(uuid.uuid4()),
        "session_id": sample_session_id,
        "case_id": sample_case_id,
        "executive_summary": "Evidence appears authentic.",
        "per_agent_findings": {"agent-img": [sample_agent_finding]},
        "cross_modal_confirmed": [],
        "contested_findings": [],
        "tribunal_resolved": [],
        "incomplete_findings": [],
        "uncertainty_statement": "Low uncertainty.",
        "cryptographic_signature": "test-sig-abc123",
        "report_hash": "abc123hash",
        "signed_utc": datetime.now(UTC).isoformat(),
    }
