"""
Unit tests for core/session_persistence.py.

Covers:
- SessionPersistence._ensure_client()
- SessionPersistence.close()
- SessionPersistence.save_session_state()
- SessionPersistence.get_session_state()
- SessionPersistence.save_report()
- SessionPersistence.get_report()
- SessionPersistence.update_session_status()
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
os.environ.setdefault("NEXT_PUBLIC_DEMO_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")

from core.session_persistence import SessionPersistence


def _make_postgres_mock():
    pg = AsyncMock()
    pg.execute = AsyncMock()
    pg.fetch_one = AsyncMock(return_value=None)
    return pg


def _make_sp(with_client=True):
    if with_client:
        pg = _make_postgres_mock()
        sp = SessionPersistence(client=pg)
        return sp, pg
    else:
        sp = SessionPersistence(client=None)
        return sp, None


# ── close ──────────────────────────────────────────────────────────────────────


class TestSessionPersistenceClose:
    @pytest.mark.asyncio
    async def test_close_is_noop(self):
        sp, _ = _make_sp()
        # Should not raise
        await sp.close()


# ── save_session_state ─────────────────────────────────────────────────────────


class TestSaveSessionState:
    @pytest.mark.asyncio
    async def test_save_returns_true_on_success(self):
        sp, pg = _make_sp()
        result = await sp.save_session_state(
            session_id=str(uuid4()),
            case_id="CASE001",
            investigator_id="inv1",
            pipeline_state={"step": 1},
        )
        assert result is True
        pg.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_returns_false_when_no_client(self):
        sp, _ = _make_sp(with_client=False)
        # Manually test the None-client path
        sp.client = None

        # Patch _ensure_client to not initialize
        async def noop_ensure():
            pass

        sp._ensure_client = noop_ensure
        result = await sp.save_session_state(
            session_id=str(uuid4()),
            case_id="CASE001",
            investigator_id="inv1",
            pipeline_state={},
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_save_returns_false_on_db_error(self):
        sp, pg = _make_sp()
        pg.execute = AsyncMock(side_effect=Exception("DB error"))
        result = await sp.save_session_state(
            session_id=str(uuid4()),
            case_id="CASE001",
            investigator_id="inv1",
            pipeline_state={"step": 1},
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_save_with_status_param(self):
        sp, pg = _make_sp()
        result = await sp.save_session_state(
            session_id=str(uuid4()),
            case_id="CASE001",
            investigator_id="inv1",
            pipeline_state={},
            status="completed",
        )
        assert result is True


# ── get_session_state ──────────────────────────────────────────────────────────


class TestGetSessionState:
    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        sp, pg = _make_sp()
        pg.fetch_one = AsyncMock(return_value=None)
        result = await sp.get_session_state(str(uuid4()))
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_dict_when_found(self):
        sp, pg = _make_sp()
        now = datetime.now(UTC)
        mock_row = {
            "session_id": uuid4(),
            "case_id": "CASE001",
            "investigator_id": "inv1",
            "pipeline_state": '{"step": 1}',
            "agent_results": None,
            "checkpoints": None,
            "status": "running",
            "created_at": now,
            "updated_at": now,
        }
        pg.fetch_one = AsyncMock(return_value=mock_row)
        result = await sp.get_session_state(str(uuid4()))
        assert result is not None
        assert result["case_id"] == "CASE001"

    @pytest.mark.asyncio
    async def test_returns_none_on_db_error(self):
        sp, pg = _make_sp()
        pg.fetch_one = AsyncMock(side_effect=Exception("DB error"))
        result = await sp.get_session_state(str(uuid4()))
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_client(self):
        sp, _ = _make_sp(with_client=False)
        sp.client = None

        async def noop():
            pass

        sp._ensure_client = noop
        result = await sp.get_session_state(str(uuid4()))
        assert result is None


# ── save_report ────────────────────────────────────────────────────────────────


class TestSaveReport:
    @pytest.mark.asyncio
    async def test_save_report_returns_true_on_success(self):
        sp, pg = _make_sp()
        result = await sp.save_report(
            session_id=str(uuid4()),
            case_id="CASE001",
            investigator_id="inv1",
            report_data={"verdict": "MANIPULATED"},
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_save_report_returns_false_on_error(self):
        sp, pg = _make_sp()
        pg.execute = AsyncMock(side_effect=Exception("DB error"))
        result = await sp.save_report(
            session_id=str(uuid4()),
            case_id="CASE001",
            investigator_id="inv1",
            report_data={},
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_save_report_returns_false_when_no_client(self):
        sp, _ = _make_sp(with_client=False)
        sp.client = None

        async def noop():
            pass

        sp._ensure_client = noop
        result = await sp.save_report(
            session_id=str(uuid4()),
            case_id="CASE001",
            investigator_id="inv1",
            report_data={},
        )
        assert result is False


# ── get_report ─────────────────────────────────────────────────────────────────


class TestGetReport:
    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        sp, pg = _make_sp()
        pg.fetch_one = AsyncMock(return_value=None)
        result = await sp.get_report(str(uuid4()))
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_dict_when_found(self):
        sp, pg = _make_sp()
        now = datetime.now(UTC)
        mock_row = {
            "session_id": uuid4(),
            "case_id": "CASE001",
            "investigator_id": "inv1",
            "status": "completed",
            "completed_at": now,
            "report_data": '{"verdict": "AUTHENTIC"}',
            "error_message": None,
        }
        pg.fetch_one = AsyncMock(return_value=mock_row)
        result = await sp.get_report(str(uuid4()))
        assert result is not None
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self):
        sp, pg = _make_sp()
        pg.fetch_one = AsyncMock(side_effect=Exception("DB error"))
        result = await sp.get_report(str(uuid4()))
        assert result is None


# ── update_session_status ──────────────────────────────────────────────────────


class TestUpdateSessionStatus:
    @pytest.mark.asyncio
    async def test_update_status_returns_true(self):
        sp, pg = _make_sp()
        result = await sp.update_session_status(str(uuid4()), "completed")
        assert result is True

    @pytest.mark.asyncio
    async def test_update_status_with_error_message(self):
        sp, pg = _make_sp()
        result = await sp.update_session_status(
            str(uuid4()), "failed", error_message="Pipeline crashed"
        )
        assert result is True
        # execute called twice (once for investigation_state, once for session_reports)
        assert pg.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_update_status_returns_false_on_error(self):
        sp, pg = _make_sp()
        pg.execute = AsyncMock(side_effect=Exception("DB error"))
        result = await sp.update_session_status(str(uuid4()), "failed")
        assert result is False

    @pytest.mark.asyncio
    async def test_update_status_returns_false_when_no_client(self):
        sp, _ = _make_sp(with_client=False)
        sp.client = None

        async def noop():
            pass

        sp._ensure_client = noop
        result = await sp.update_session_status(str(uuid4()), "failed")
        assert result is False


# ── _ensure_client ─────────────────────────────────────────────────────────────


class TestEnsureClient:
    @pytest.mark.asyncio
    async def test_ensure_client_initializes_when_none(self):
        sp = SessionPersistence(client=None)
        mock_pg = _make_postgres_mock()
        with patch(
            "core.session_persistence.get_postgres_client", new=AsyncMock(return_value=mock_pg)
        ):
            await sp._ensure_client()
        assert sp.client is mock_pg

    @pytest.mark.asyncio
    async def test_ensure_client_raises_on_timeout(self):
        sp = SessionPersistence(client=None)
        with patch(
            "core.session_persistence.get_postgres_client",
            new=AsyncMock(side_effect=TimeoutError()),
        ):
            with pytest.raises(RuntimeError, match="timed out"):
                await sp._ensure_client()
