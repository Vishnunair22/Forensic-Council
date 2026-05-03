"""
Unit tests for core/episodic_memory.py.

Covers:
- EpisodicEntry model (to_dict / from_dict)
- ForensicSignatureType enum
- EpisodicMemory.ensure_collection()
- EpisodicMemory.store()
- EpisodicMemory.query()
- EpisodicMemory.get_by_case()
- EpisodicMemory.get_by_session()
- EpisodicMemory context manager
"""

import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_PASSWORD", "test")
os.environ.setdefault("DEMO_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")

from core.episodic_memory import (
    EpisodicEntry,
    EpisodicMemory,
    ForensicSignatureType,
)


def _make_entry(sid=None, case_id="CASE001") -> EpisodicEntry:
    return EpisodicEntry(
        case_id=case_id,
        agent_id="Agent1",
        session_id=sid or uuid4(),
        signature_type=ForensicSignatureType.MANIPULATION_SIGNATURE,
        finding_type="ela",
        confidence=0.85,
        summary="ELA analysis shows manipulation.",
    )


def _make_qdrant() -> AsyncMock:
    qdrant = AsyncMock()
    qdrant.create_collection = AsyncMock()
    qdrant.upsert = AsyncMock()
    qdrant.query = AsyncMock(return_value=[])
    qdrant.scroll = AsyncMock(return_value=[])
    qdrant.disconnect = AsyncMock()
    return qdrant


# ── ForensicSignatureType ──────────────────────────────────────────────────────


class TestForensicSignatureType:
    def test_all_values(self):
        types = {t.value for t in ForensicSignatureType}
        assert "DEVICE_FINGERPRINT" in types
        assert "MANIPULATION_SIGNATURE" in types
        assert "METADATA_PATTERN" in types
        assert "AUDIO_ARTIFACT" in types
        assert "VIDEO_ARTIFACT" in types
        assert "OBJECT_DETECTION" in types


# ── EpisodicEntry model ────────────────────────────────────────────────────────


class TestEpisodicEntry:
    def test_creation_defaults(self):
        entry = _make_entry()
        assert entry.entry_id is not None
        assert entry.confidence == 0.85
        assert isinstance(entry.timestamp_utc, datetime)

    def test_to_dict(self):
        entry = _make_entry()
        d = entry.to_dict()
        assert d["case_id"] == "CASE001"
        assert d["agent_id"] == "Agent1"
        assert d["signature_type"] == "MANIPULATION_SIGNATURE"
        assert d["confidence"] == 0.85
        assert "entry_id" in d
        assert "timestamp_utc" in d

    def test_from_dict_roundtrip(self):
        entry = _make_entry()
        restored = EpisodicEntry.from_dict(entry.to_dict())
        assert restored.case_id == entry.case_id
        assert restored.agent_id == entry.agent_id
        assert restored.confidence == entry.confidence
        assert restored.signature_type == entry.signature_type

    def test_from_dict_with_datetime_object(self):
        entry = _make_entry()
        d = entry.to_dict()
        d["timestamp_utc"] = datetime.now(UTC)
        restored = EpisodicEntry.from_dict(d)
        assert restored is not None


# ── EpisodicMemory with no Qdrant ──────────────────────────────────────────────


class TestEpisodicMemoryNoQdrant:
    def _make_em(self):
        cl = AsyncMock()
        cl.log_entry = AsyncMock()
        return EpisodicMemory(qdrant_client=None, custody_logger=cl)

    @pytest.mark.asyncio
    async def test_ensure_collection_returns_false_when_no_qdrant(self):
        em = self._make_em()
        result = await em.ensure_collection()
        assert result is False

    @pytest.mark.asyncio
    async def test_store_skips_when_qdrant_unavailable(self):
        em = self._make_em()
        entry = _make_entry()
        embedding = [0.1] * 512
        # Should not raise
        await em.store(entry, embedding)

    @pytest.mark.asyncio
    async def test_query_returns_empty_when_qdrant_unavailable(self):
        em = self._make_em()
        results = await em.query([0.0] * 512)
        assert results == []

    @pytest.mark.asyncio
    async def test_get_by_case_returns_empty_when_qdrant_unavailable(self):
        em = self._make_em()
        results = await em.get_by_case("CASE001")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_by_session_returns_empty_when_qdrant_unavailable(self):
        em = self._make_em()
        results = await em.get_by_session(uuid4())
        assert results == []


# ── EpisodicMemory with mocked Qdrant ─────────────────────────────────────────


class TestEpisodicMemoryWithQdrant:
    def _make_em(self):
        qdrant = _make_qdrant()
        cl = AsyncMock()
        cl.log_entry = AsyncMock()
        em = EpisodicMemory(qdrant_client=qdrant, custody_logger=cl)
        return em, qdrant

    @pytest.mark.asyncio
    async def test_ensure_collection_calls_create(self):
        em, qdrant = self._make_em()
        result = await em.ensure_collection()
        assert result is True
        qdrant.create_collection.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_collection_returns_false_on_error(self):
        em, qdrant = self._make_em()
        qdrant.create_collection = AsyncMock(side_effect=RuntimeError("connection failed"))
        result = await em.ensure_collection()
        assert result is False

    @pytest.mark.asyncio
    async def test_store_calls_upsert(self):
        em, qdrant = self._make_em()
        entry = _make_entry()
        embedding = [0.1] * 512
        await em.store(entry, embedding)
        qdrant.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_handles_upsert_failure(self):
        em, qdrant = self._make_em()
        qdrant.upsert = AsyncMock(side_effect=RuntimeError("upsert failed"))
        entry = _make_entry()
        embedding = [0.0] * 512
        # Should not raise
        await em.store(entry, embedding)

    @pytest.mark.asyncio
    async def test_query_returns_entries(self):
        em, qdrant = self._make_em()
        entry = _make_entry()
        qdrant.query = AsyncMock(return_value=[{"payload": entry.to_dict()}])
        results = await em.query([0.1] * 512)
        assert len(results) == 1
        assert results[0].case_id == "CASE001"

    @pytest.mark.asyncio
    async def test_query_with_signature_type_filter(self):
        em, qdrant = self._make_em()
        entry = _make_entry()
        qdrant.query = AsyncMock(return_value=[{"payload": entry.to_dict()}])
        results = await em.query(
            [0.1] * 512,
            signature_type=ForensicSignatureType.MANIPULATION_SIGNATURE,
        )
        assert isinstance(results, list)
        # Filter conditions should be passed to Qdrant
        call_kwargs = qdrant.query.call_args
        assert call_kwargs is not None

    @pytest.mark.asyncio
    async def test_query_handles_error(self):
        em, qdrant = self._make_em()
        qdrant.query = AsyncMock(side_effect=RuntimeError("query failed"))
        results = await em.query([0.0] * 512)
        assert results == []

    @pytest.mark.asyncio
    async def test_get_by_case_returns_entries(self):
        em, qdrant = self._make_em()
        entry = _make_entry()
        qdrant.scroll = AsyncMock(return_value=[{"payload": entry.to_dict()}])
        results = await em.get_by_case("CASE001")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_get_by_case_handles_scroll_error(self):
        em, qdrant = self._make_em()
        qdrant.scroll = AsyncMock(side_effect=RuntimeError("scroll failed"))
        results = await em.get_by_case("CASE001")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_by_session_returns_entries(self):
        em, qdrant = self._make_em()
        sid = uuid4()
        entry = _make_entry(sid=sid)
        qdrant.scroll = AsyncMock(return_value=[{"payload": entry.to_dict()}])
        results = await em.get_by_session(sid)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_store_without_custody_logger(self):
        qdrant = _make_qdrant()
        em = EpisodicMemory(qdrant_client=qdrant, custody_logger=None)
        entry = _make_entry()
        embedding = [0.0] * 512
        await em.store(entry, embedding)
        qdrant.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_with_entries_and_custody_logger(self):
        em, qdrant = self._make_em()
        entry = _make_entry()
        qdrant.query = AsyncMock(return_value=[{"payload": entry.to_dict()}])
        results = await em.query([0.0] * 512, top_k=3)
        assert len(results) == 1
        em._custody_logger.log_entry.assert_called()


# ── Async context manager ──────────────────────────────────────────────────────


class TestEpisodicMemoryContextManager:
    @pytest.mark.asyncio
    async def test_context_manager_connects_and_disconnects(self):
        with patch("core.episodic_memory.get_qdrant_client") as mock_get:
            mock_qdrant = _make_qdrant()
            mock_get.return_value = mock_qdrant
            em = EpisodicMemory(qdrant_client=None)
            async with em:
                assert em._qdrant is not None
            mock_qdrant.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_does_not_disconnect_provided_client(self):
        qdrant = _make_qdrant()
        em = EpisodicMemory(qdrant_client=qdrant)
        async with em:
            pass
        qdrant.disconnect.assert_not_called()
