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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Suppress noisy passlib deprecation warnings in test output.
logging.getLogger("passlib").setLevel(logging.ERROR)


class _AwaitableResponse:
    def __init__(self, response):
        self._response = response

    def __await__(self):
        async def _resolve():
            return self._response

        return _resolve().__await__()

    def __getattr__(self, name):
        return getattr(self._response, name)


class _DualModeTestClient:
    """Expose TestClient responses to both sync tests and async ``await client.get`` tests."""

    def __init__(self, client: TestClient) -> None:
        self._client = client
        self.app = client.app
        self.cookies = client.cookies

    def get(self, *args, **kwargs):
        return _AwaitableResponse(self._client.get(*args, **kwargs))

    def post(self, *args, **kwargs):
        return _AwaitableResponse(self._client.post(*args, **kwargs))

    def put(self, *args, **kwargs):
        return _AwaitableResponse(self._client.put(*args, **kwargs))

    def patch(self, *args, **kwargs):
        return _AwaitableResponse(self._client.patch(*args, **kwargs))

    def delete(self, *args, **kwargs):
        return _AwaitableResponse(self._client.delete(*args, **kwargs))

# -- Minimal environment before any backend import --

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test_user")
os.environ.setdefault("POSTGRES_PASSWORD", "test_pass")
os.environ.setdefault("POSTGRES_DB", "forensic_test")
os.environ.setdefault("REDIS_PASSWORD", "test_redis_pass")
os.environ.setdefault("DEMO_PASSWORD", "test_demo_pass")
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
    return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


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
    """Returns headers with a valid investigator Bearer token for HTTP test client calls."""
    from core.auth import UserRole, create_access_token

    token = create_access_token("user-1", UserRole.INVESTIGATOR, username="test")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_auth_headers() -> dict:
    from core.auth import UserRole, create_access_token

    token = create_access_token("admin-1", UserRole.ADMIN, username="admin")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(mock_redis, mock_postgres, mock_qdrant):
    """FastAPI TestClient with infrastructure calls mocked for route tests."""
    from api.main import app

    patches = [
        patch("core.persistence.redis_client.get_redis_client", return_value=mock_redis),
        patch("core.persistence.postgres_client.get_postgres_client", return_value=mock_postgres),
        patch("core.persistence.qdrant_client.get_qdrant_client", return_value=mock_qdrant),
        patch("core.migrations.run_migrations", new_callable=AsyncMock),
        patch("scripts.init_db.bootstrap_users", new_callable=AsyncMock),
    ]
    for patcher in patches:
        patcher.start()
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield _DualModeTestClient(test_client)
    finally:
        app.dependency_overrides.clear()
        for patcher in reversed(patches):
            patcher.stop()


@pytest.fixture
def jpeg_file(sample_jpeg_bytes) -> io.BytesIO:
    buf = io.BytesIO(sample_jpeg_bytes)
    buf.name = "test.jpg"
    return buf


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
