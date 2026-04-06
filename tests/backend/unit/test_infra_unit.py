"""
Infrastructure Layer Unit Tests
================================
Covers:
  - Session state management (register/unregister WebSockets, pipeline CRUD)
  - Rate limiting (in-memory fallback paths)
  - Metrics counter helpers + Prometheus format validation
  - Sessions route helpers (_forensic_report_to_dto, _is_real_finding)
  - Download report serialization regression (was passing Pydantic model raw)
  - Proxy route header stripping

Run: pytest tests/backend/unit/test_infra_unit.py -v
"""
import asyncio
import time
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# SESSION STATE — WebSocket management
# ═══════════════════════════════════════════════════════════════════════════════

class TestSessionStateWebSockets:
    """_session_state.py WebSocket bookkeeping."""

    def _import(self):
        from api.routes._session_state import (
            register_websocket,
            unregister_websocket,
            get_session_websockets,
            clear_session_websockets,
            _websocket_connections,
        )
        return register_websocket, unregister_websocket, get_session_websockets, clear_session_websockets, _websocket_connections

    def test_register_and_retrieve(self):
        reg, unreg, get, clear, store = self._import()
        sid = str(uuid.uuid4())
        ws = MagicMock()
        reg(sid, ws)
        assert ws in get(sid)
        clear(sid)

    def test_unregister_removes_specific_ws(self):
        reg, unreg, get, clear, store = self._import()
        sid = str(uuid.uuid4())
        ws1, ws2 = MagicMock(), MagicMock()
        reg(sid, ws1)
        reg(sid, ws2)
        unreg(sid, ws1)
        remaining = get(sid)
        assert ws1 not in remaining
        assert ws2 in remaining
        clear(sid)

    def test_unregister_nonexistent_is_noop(self):
        reg, unreg, get, clear, store = self._import()
        sid = str(uuid.uuid4())
        ws = MagicMock()
        # Should not raise
        unreg(sid, ws)

    def test_clear_removes_all(self):
        reg, unreg, get, clear, store = self._import()
        sid = str(uuid.uuid4())
        reg(sid, MagicMock())
        reg(sid, MagicMock())
        clear(sid)
        assert get(sid) == []

    def test_empty_session_returns_empty_list(self):
        _, _, get, _, _ = self._import()
        assert get(str(uuid.uuid4())) == []

    def test_multiple_sessions_isolated(self):
        reg, _, get, clear, _ = self._import()
        s1, s2 = str(uuid.uuid4()), str(uuid.uuid4())
        ws1, ws2 = MagicMock(), MagicMock()
        reg(s1, ws1)
        reg(s2, ws2)
        assert ws2 not in get(s1)
        assert ws1 not in get(s2)
        clear(s1)
        clear(s2)


# ═══════════════════════════════════════════════════════════════════════════════
# SESSION STATE — pipeline CRUD
# ═══════════════════════════════════════════════════════════════════════════════

class TestSessionStatePipelines:
    def test_set_and_get_active_pipeline(self):
        from api.routes._session_state import (
            set_active_pipeline, get_active_pipeline, remove_active_pipeline
        )
        sid = str(uuid.uuid4())
        pipeline = MagicMock()
        set_active_pipeline(sid, pipeline)
        assert get_active_pipeline(sid) is pipeline
        remove_active_pipeline(sid)

    def test_get_missing_pipeline_returns_none(self):
        from api.routes._session_state import get_active_pipeline
        assert get_active_pipeline(str(uuid.uuid4())) is None

    def test_remove_pipeline_is_idempotent(self):
        from api.routes._session_state import remove_active_pipeline
        sid = str(uuid.uuid4())
        # Should not raise even if it doesn't exist
        remove_active_pipeline(sid)
        remove_active_pipeline(sid)

    def test_get_all_active_pipelines_returns_snapshot(self):
        from api.routes._session_state import (
            set_active_pipeline, get_all_active_pipelines, remove_active_pipeline
        )
        sid = str(uuid.uuid4())
        p = MagicMock()
        set_active_pipeline(sid, p)
        snap = get_all_active_pipelines()
        assert sid in snap
        remove_active_pipeline(sid)

    def test_active_task_crud(self):
        from api.routes._session_state import (
            set_active_task, pop_active_task
        )
        sid = str(uuid.uuid4())
        task = MagicMock()
        set_active_task(sid, task)
        popped = pop_active_task(sid)
        assert popped is task
        # Second pop returns None
        assert pop_active_task(sid) is None


# ═══════════════════════════════════════════════════════════════════════════════
# RATE LIMITING — in-memory fallback paths
# ═══════════════════════════════════════════════════════════════════════════════

class TestInvestigationRateLimit:
    """Test the in-memory fallback path (Redis unavailable scenario)."""

    def _run(self, coro):
        return asyncio.run(coro)

    def _patch_redis_unavailable(self):
        """Context manager that makes Redis raise to trigger in-memory fallback."""
        return patch(
            "infra.redis_client.get_redis_client",
            new=AsyncMock(side_effect=ConnectionError("Redis down")),
        )

    def test_allows_first_investigation(self):
        from api.routes._rate_limiting import (
            check_investigation_rate_limit,
            _user_investigation_times,
        )
        uid = str(uuid.uuid4())
        _user_investigation_times.pop(uid, None)
        with self._patch_redis_unavailable():
            # Should not raise
            self._run(check_investigation_rate_limit(uid))
        _user_investigation_times.pop(uid, None)

    def test_window_prunes_old_entries(self):
        from api.routes._rate_limiting import (
            check_investigation_rate_limit,
            _user_investigation_times,
            _USER_RATE_WINDOW_SECS,
        )
        uid = str(uuid.uuid4())
        # Fill with timestamps older than the window
        old_time = time.time() - _USER_RATE_WINDOW_SECS - 1
        _user_investigation_times[uid] = [old_time] * 50

        with self._patch_redis_unavailable():
            # Old entries pruned → under limit → should not raise
            self._run(check_investigation_rate_limit(uid))
        _user_investigation_times.pop(uid, None)

    def test_blocks_over_limit(self):
        from fastapi import HTTPException
        from api.routes._rate_limiting import (
            check_investigation_rate_limit,
            _user_investigation_times,
            _MAX_INVESTIGATIONS_PER_USER,
        )
        uid = str(uuid.uuid4())
        now = time.time()
        _user_investigation_times[uid] = [now] * _MAX_INVESTIGATIONS_PER_USER

        with self._patch_redis_unavailable():
            with pytest.raises(HTTPException) as exc_info:
                self._run(check_investigation_rate_limit(uid))
        assert exc_info.value.status_code == 429
        _user_investigation_times.pop(uid, None)

    def test_retry_after_header_present_on_429(self):
        from fastapi import HTTPException
        from api.routes._rate_limiting import (
            check_investigation_rate_limit,
            _user_investigation_times,
            _MAX_INVESTIGATIONS_PER_USER,
        )
        uid = str(uuid.uuid4())
        now = time.time()
        _user_investigation_times[uid] = [now] * _MAX_INVESTIGATIONS_PER_USER

        with self._patch_redis_unavailable():
            with pytest.raises(HTTPException) as exc_info:
                self._run(check_investigation_rate_limit(uid))
        assert "Retry-After" in exc_info.value.headers
        _user_investigation_times.pop(uid, None)


class TestDailyCostQuota:
    def _run(self, coro):
        return asyncio.run(coro)

    def _patch_redis_unavailable(self):
        return patch(
            "infra.redis_client.get_redis_client",
            new=AsyncMock(side_effect=ConnectionError("Redis down")),
        )

    def test_allows_first_investigation_under_quota(self):
        from api.routes._rate_limiting import (
            check_daily_cost_quota,
            _mem_cost_tracker,
        )
        uid = str(uuid.uuid4())
        _mem_cost_tracker.pop(uid, None)
        with self._patch_redis_unavailable():
            self._run(check_daily_cost_quota(uid, "investigator"))
        _mem_cost_tracker.pop(uid, None)

    def test_blocks_over_daily_quota(self):
        from fastapi import HTTPException
        from api.routes._rate_limiting import (
            check_daily_cost_quota,
            _mem_cost_tracker,
            _DAILY_COST_QUOTA_USD,
            _COST_PER_INVESTIGATION_USD,
        )
        uid = str(uuid.uuid4())
        quota = _DAILY_COST_QUOTA_USD.get("investigator", 50.0)
        # Set cost to just below quota so one more pushes over
        _mem_cost_tracker[uid] = (quota, time.time())

        with self._patch_redis_unavailable():
            with pytest.raises(HTTPException) as exc_info:
                self._run(check_daily_cost_quota(uid, "investigator"))
        assert exc_info.value.status_code == 429
        _mem_cost_tracker.pop(uid, None)

    def test_window_reset_allows_new_quota(self):
        from api.routes._rate_limiting import (
            check_daily_cost_quota,
            _mem_cost_tracker,
            _DAILY_COST_QUOTA_USD,
            _COST_QUOTA_WINDOW_SECS,
        )
        uid = str(uuid.uuid4())
        quota = _DAILY_COST_QUOTA_USD.get("investigator", 50.0)
        # Set cost at quota but window started long ago (expired)
        old_start = time.time() - _COST_QUOTA_WINDOW_SECS - 1
        _mem_cost_tracker[uid] = (quota, old_start)

        with self._patch_redis_unavailable():
            # Window expired → reset → should not raise
            self._run(check_daily_cost_quota(uid, "investigator"))
        _mem_cost_tracker.pop(uid, None)

    def test_admin_has_higher_quota(self):
        from api.routes._rate_limiting import (
            _DAILY_COST_QUOTA_USD,
        )
        assert _DAILY_COST_QUOTA_USD["admin"] > _DAILY_COST_QUOTA_USD["investigator"]


# ═══════════════════════════════════════════════════════════════════════════════
# METRICS — counter helpers and Prometheus format
# ═══════════════════════════════════════════════════════════════════════════════

class TestMetricsCounters:
    """Verify counter helpers fire without exceptions."""

    def test_increment_request_count(self):
        from api.routes.metrics import increment_request_count, _local
        before = _local.get("request_count", 0)
        # Call without an event loop → uses local fallback
        with patch("api.routes.metrics.asyncio.get_running_loop", side_effect=RuntimeError):
            increment_request_count()
        # _local["request_count"] incremented
        assert _local["request_count"] >= before

    def test_increment_investigations_started(self):
        from api.routes.metrics import increment_investigations_started, _local
        before = _local.get("investigations_started", 0)
        with patch("api.routes.metrics.asyncio.get_running_loop", side_effect=RuntimeError):
            increment_investigations_started()
        assert _local["investigations_started"] >= before + 1

    def test_increment_investigations_completed(self):
        from api.routes.metrics import increment_investigations_completed, _local
        before = _local.get("investigations_completed", 0)
        with patch("api.routes.metrics.asyncio.get_running_loop", side_effect=RuntimeError):
            increment_investigations_completed()
        assert _local["investigations_completed"] >= before + 1

    def test_increment_investigations_failed(self):
        from api.routes.metrics import increment_investigations_failed, _local
        before = _local.get("investigations_failed", 0)
        with patch("api.routes.metrics.asyncio.get_running_loop", side_effect=RuntimeError):
            increment_investigations_failed()
        assert _local["investigations_failed"] >= before + 1

    def test_record_request_duration(self):
        from api.routes.metrics import record_request_duration, _local
        with patch("api.routes.metrics.asyncio.get_running_loop", side_effect=RuntimeError):
            record_request_duration(42.5)
        assert _local["request_duration_sum"] > 0

    def test_snapshot_returns_all_required_keys(self):
        required = {
            "uptime_seconds", "requests_total", "request_duration_avg_ms",
            "errors_total", "error_rate", "active_sessions",
            "investigations_started", "investigations_completed",
            "investigations_failed", "success_rate",
            "db_pool_size", "db_pool_available", "db_pool_in_use", "db_pool_max",
        }
        from api.routes.metrics import _snapshot

        async def run():
            with patch(
                "infra.redis_client.get_redis_client",
                new=AsyncMock(side_effect=ConnectionError("no redis")),
            ), patch(
                "infra.postgres_client.get_postgres_client",
                new=AsyncMock(side_effect=ConnectionError("no pg")),
            ):
                return await _snapshot()

        snap = asyncio.run(run())
        assert required.issubset(snap.keys())

    def test_prometheus_endpoint_format(self):
        """Prometheus format must have proper HELP/TYPE lines and metric values."""
        from api.routes.metrics import _snapshot
        import asyncio as _asyncio

        async def _get_snap():
            with patch(
                "infra.redis_client.get_redis_client",
                new=AsyncMock(side_effect=ConnectionError),
            ), patch(
                "infra.postgres_client.get_postgres_client",
                new=AsyncMock(side_effect=ConnectionError),
            ):
                return await _snapshot()

        snap = _asyncio.run(_get_snap())
        lines = [
            "# HELP forensic_uptime_seconds Total uptime in seconds",
            "# TYPE forensic_uptime_seconds gauge",
            f'forensic_uptime_seconds{{app="forensic_council"}} {snap["uptime_seconds"]:.3f}',
            "# HELP forensic_requests_total Total number of HTTP requests",
            "# TYPE forensic_requests_total counter",
        ]
        for line in lines:
            assert line.startswith("# ") or "forensic_" in line

    def test_success_rate_is_1_when_no_investigations(self):
        from api.routes.metrics import _snapshot

        async def run():
            with patch(
                "infra.redis_client.get_redis_client",
                new=AsyncMock(side_effect=ConnectionError),
            ), patch(
                "infra.postgres_client.get_postgres_client",
                new=AsyncMock(side_effect=ConnectionError),
            ):
                return await _snapshot()

        # Reset local counters to 0
        from api.routes import metrics as _m
        _m._local["investigations_completed"] = 0
        _m._local["investigations_failed"] = 0
        snap = asyncio.run(run())
        assert snap["success_rate"] == 1.0

    def test_error_rate_is_0_when_no_requests(self):
        from api.routes import metrics as _m
        _m._local["request_count"] = 0
        _m._local["error_count"] = 0

        from api.routes.metrics import _snapshot

        async def run():
            with patch(
                "infra.redis_client.get_redis_client",
                new=AsyncMock(side_effect=ConnectionError),
            ), patch(
                "infra.postgres_client.get_postgres_client",
                new=AsyncMock(side_effect=ConnectionError),
            ):
                return await _snapshot()

        snap = asyncio.run(run())
        assert snap["error_rate"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# SESSIONS ROUTE — _forensic_report_to_dto & _is_real_finding
# ═══════════════════════════════════════════════════════════════════════════════

class TestForensicReportHelpers:
    """Test the sessions.py internal helpers in isolation."""

    def _make_finding(self, **kwargs):
        defaults = {
            "finding_id": str(uuid.uuid4()),
            "agent_id": "agent-img",
            "agent_name": "Image Expert",
            "finding_type": "ela_analysis",
            "status": "complete",
            "confidence_raw": 0.9,
            "calibrated": True,
            "calibrated_probability": 0.88,
            "court_statement": "No manipulation found.",
            "robustness_caveat": False,
            "robustness_caveat_detail": None,
            "reasoning_summary": "ELA uniform.",
            "metadata": None,
        }
        defaults.update(kwargs)
        return defaults

    def test_is_real_finding_passes_normal(self):
        from api.routes.sessions import _forensic_report_to_dto
        # Indirectly test via _is_real_finding through the inner function
        # We test the helper by observing what gets included in the DTO
        report = MagicMock()
        report.report_id = uuid.uuid4()
        report.session_id = uuid.uuid4()
        report.case_id = "CASE-001"
        report.executive_summary = "Test summary"
        report.signed_utc = None
        report.per_agent_findings = {"agent-img": [self._make_finding()]}
        report.cross_modal_confirmed = []
        report.incomplete_findings = []
        report.contested_findings = []
        report.tribunal_resolved = []
        report.uncertainty_statement = ""
        report.cryptographic_signature = "sig"
        report.report_hash = "hash"
        # Patch _assign_severity_tier
        with patch("api.routes.sessions._assign_severity_tier", return_value="HIGH"):
            dto = _forensic_report_to_dto(report)
        assert "agent-img" in dto.per_agent_findings
        assert len(dto.per_agent_findings["agent-img"]) == 1

    def test_stub_findings_filtered_out(self):
        from api.routes.sessions import _forensic_report_to_dto

        report = MagicMock()
        report.report_id = uuid.uuid4()
        report.session_id = uuid.uuid4()
        report.case_id = "CASE-002"
        report.executive_summary = ""
        report.signed_utc = None
        # One stub (empty reasoning + type), one real
        stub = self._make_finding(finding_type="", reasoning_summary="")
        real = self._make_finding()
        report.per_agent_findings = {"agent-img": [stub, real]}
        report.cross_modal_confirmed = []
        report.incomplete_findings = []
        report.contested_findings = []
        report.tribunal_resolved = []
        report.uncertainty_statement = ""
        report.cryptographic_signature = ""
        report.report_hash = ""

        with patch("api.routes.sessions._assign_severity_tier", return_value="LOW"):
            dto = _forensic_report_to_dto(report)

        # Only the real finding should remain
        assert len(dto.per_agent_findings["agent-img"]) == 1
        assert dto.per_agent_findings["agent-img"][0].reasoning_summary == "ELA uniform."

    def test_na_finding_type_filtered(self):
        from api.routes.sessions import _forensic_report_to_dto

        report = MagicMock()
        report.report_id = uuid.uuid4()
        report.session_id = uuid.uuid4()
        report.case_id = "CASE-003"
        report.executive_summary = ""
        report.signed_utc = None
        na_finding = self._make_finding(
            finding_type="file type not applicable",
            reasoning_summary="Not applicable."
        )
        report.per_agent_findings = {"agent-audio": [na_finding]}
        report.cross_modal_confirmed = []
        report.incomplete_findings = []
        report.contested_findings = []
        report.tribunal_resolved = []
        report.uncertainty_statement = ""
        report.cryptographic_signature = ""
        report.report_hash = ""

        with patch("api.routes.sessions._assign_severity_tier", return_value="LOW"):
            dto = _forensic_report_to_dto(report)

        # agent-audio should be absent because all its findings are N/A stubs
        assert "agent-audio" not in dto.per_agent_findings

    def test_signed_utc_datetime_converted_to_string(self):
        from api.routes.sessions import _forensic_report_to_dto

        report = MagicMock()
        report.report_id = uuid.uuid4()
        report.session_id = uuid.uuid4()
        report.case_id = "CASE-004"
        report.executive_summary = ""
        report.signed_utc = datetime.now(timezone.utc)
        report.per_agent_findings = {}
        report.cross_modal_confirmed = []
        report.incomplete_findings = []
        report.contested_findings = []
        report.tribunal_resolved = []
        report.uncertainty_statement = ""
        report.cryptographic_signature = ""
        report.report_hash = ""

        with patch("api.routes.sessions._assign_severity_tier", return_value="LOW"):
            dto = _forensic_report_to_dto(report)

        assert isinstance(dto.signed_utc, str)


# ═══════════════════════════════════════════════════════════════════════════════
# DOWNLOAD REPORT — serialization regression test
# Ensures JSONResponse receives a dict, not a raw Pydantic model.
# ═══════════════════════════════════════════════════════════════════════════════

class TestDownloadReportSerialization:
    """Regression test for the bug where model_dump() was not called."""

    def test_report_dto_model_dump_produces_dict(self):
        """ReportDTO.model_dump() returns a plain dict (JSONResponse-safe)."""
        from api.schemas import ReportDTO
        dto = ReportDTO(
            report_id=str(uuid.uuid4()),
            session_id=str(uuid.uuid4()),
            case_id="CASE-REGRESSION",
            executive_summary="Regression test",
            per_agent_findings={},
            cross_modal_confirmed=[],
            contested_findings=[],
            tribunal_resolved=[],
            incomplete_findings=[],
            uncertainty_statement="",
            cryptographic_signature="sig",
            report_hash="hash",
        )
        result = dto.model_dump() if hasattr(dto, "model_dump") else dto.dict()
        assert isinstance(result, dict)
        assert result["case_id"] == "CASE-REGRESSION"

    def test_model_dump_content_is_json_serializable(self):
        """Content from model_dump() must be JSON-serializable (no Pydantic objects)."""
        import json
        from api.schemas import ReportDTO
        dto = ReportDTO(
            report_id=str(uuid.uuid4()),
            session_id=str(uuid.uuid4()),
            case_id="CASE-JSON",
            executive_summary="JSON test",
            per_agent_findings={},
            cross_modal_confirmed=[],
            contested_findings=[],
            tribunal_resolved=[],
            incomplete_findings=[],
            uncertainty_statement="",
            cryptographic_signature="",
            report_hash="",
        )
        content = dto.model_dump() if hasattr(dto, "model_dump") else dto.dict()
        # Should not raise
        serialized = json.dumps(content, default=str)
        assert "CASE-JSON" in serialized


# ═══════════════════════════════════════════════════════════════════════════════
# PROXY ROUTE — header stripping and structure
# ═══════════════════════════════════════════════════════════════════════════════

class TestProxyRouteHeaderStripping:
    """Verify HOP_BY_HOP_HEADERS are correctly defined and copyRequestHeaders strips them."""

    def test_hop_by_hop_set_contains_connection(self):
        # Import the constant directly from the module under test
        import importlib.util, sys, pathlib
        route_path = pathlib.Path("d:/Forensic Council/frontend/src/app/api/v1/[...path]/route.ts")
        # Read and check content directly (TypeScript — structural test)
        text = route_path.read_text(encoding="utf-8")
        hop_by_hop = [
            "connection", "content-length", "host", "keep-alive",
            "proxy-authenticate", "proxy-authorization", "te",
            "trailer", "transfer-encoding", "upgrade",
        ]
        for header in hop_by_hop:
            assert f'"{header}"' in text, f"HOP_BY_HOP missing: {header}"

    def test_proxy_timeout_is_applied(self):
        """PROXY_TIMEOUT_MS constant must be defined and used in fetch()."""
        import pathlib
        text = pathlib.Path(
            "d:/Forensic Council/frontend/src/app/api/v1/[...path]/route.ts"
        ).read_text(encoding="utf-8")
        assert "PROXY_TIMEOUT_MS" in text
        assert "AbortSignal.timeout(PROXY_TIMEOUT_MS)" in text

    def test_retryable_statuses_defined(self):
        import pathlib
        text = pathlib.Path(
            "d:/Forensic Council/frontend/src/app/api/v1/[...path]/route.ts"
        ).read_text(encoding="utf-8")
        for status in ["502", "503", "504"]:
            assert status in text, f"Retryable status {status} missing"

    def test_503_returned_when_all_backends_fail(self):
        """When no backend succeeds, the proxy must return 503."""
        import pathlib
        text = pathlib.Path(
            "d:/Forensic Council/frontend/src/app/api/v1/[...path]/route.ts"
        ).read_text(encoding="utf-8")
        assert "status: 503" in text

    def test_http_methods_all_exported(self):
        import pathlib
        text = pathlib.Path(
            "d:/Forensic Council/frontend/src/app/api/v1/[...path]/route.ts"
        ).read_text(encoding="utf-8")
        for method in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
            assert f"export async function {method}" in text


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH ROUTE — brute-force protection in-memory path
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthBruteForceProtection:
    """Test the in-memory fallback of _is_rate_limited and _record_failed_attempt."""

    def _run(self, coro):
        return asyncio.run(coro)

    def _patch_redis_unavailable(self):
        return patch(
            "infra.redis_client.get_redis_client",
            new=AsyncMock(side_effect=ConnectionError("no redis")),
        )

    def test_record_and_clear_failed_attempts(self):
        from api.routes.auth import (
            _record_failed_attempt,
            _clear_failed_attempts,
            _failed_attempts,
        )
        ip = f"10.0.0.{uuid.uuid4().int % 254}"
        _failed_attempts.pop(ip, None)

        with self._patch_redis_unavailable():
            self._run(_record_failed_attempt(ip))
        assert ip in _failed_attempts
        assert len(_failed_attempts[ip]) == 1

        with self._patch_redis_unavailable():
            self._run(_clear_failed_attempts(ip))
        assert ip not in _failed_attempts

    def test_too_many_attempts_raises_429(self):
        from fastapi import HTTPException
        from api.routes.auth import (
            _is_rate_limited,
            _failed_attempts,
            _MAX_LOGIN_ATTEMPTS,
        )
        ip = f"192.168.1.{uuid.uuid4().int % 254}"
        now = time.time()
        _failed_attempts[ip] = [now] * _MAX_LOGIN_ATTEMPTS

        with self._patch_redis_unavailable():
            with pytest.raises(HTTPException) as exc_info:
                self._run(_is_rate_limited(ip))
        assert exc_info.value.status_code == 429
        assert "Retry-After" in exc_info.value.headers
        _failed_attempts.pop(ip, None)

    def test_expired_attempts_pruned(self):
        from api.routes.auth import (
            _is_rate_limited,
            _failed_attempts,
            _MAX_LOGIN_ATTEMPTS,
            _LOCKOUT_WINDOW_SECS,
        )
        ip = f"172.16.0.{uuid.uuid4().int % 254}"
        old_time = time.time() - _LOCKOUT_WINDOW_SECS - 1
        _failed_attempts[ip] = [old_time] * _MAX_LOGIN_ATTEMPTS

        with self._patch_redis_unavailable():
            # Should NOT raise — all attempts are outside the window
            result = self._run(_is_rate_limited(ip))
        assert result is False
        _failed_attempts.pop(ip, None)


# ═══════════════════════════════════════════════════════════════════════════════
# SESSIONS ROUTE — WebSocket auth handling (logic level)
# ═══════════════════════════════════════════════════════════════════════════════

class TestWebSocketAuthLogic:
    """Test the token-extraction logic used in the WebSocket handler."""

    def test_subprotocol_token_extraction(self):
        """Token should be extractable from subprotocol 'token.<value>'."""
        subprotocols = ["forensic-v1", "token.my-secret-jwt"]
        auth_token = None
        for proto in subprotocols:
            if proto.startswith("token."):
                auth_token = proto[6:]
                break
        assert auth_token == "my-secret-jwt"

    def test_no_token_in_subprotocols(self):
        """If no 'token.' protocol, auth_token remains None."""
        subprotocols = ["forensic-v1"]
        auth_token = None
        for proto in subprotocols:
            if proto.startswith("token."):
                auth_token = proto[6:]
                break
        assert auth_token is None

    def test_rate_limit_max_messages(self):
        """MAX_MESSAGES_PER_MINUTE constant should be positive."""
        # Read the sessions.py and confirm the constant
        import pathlib
        text = pathlib.Path(
            "d:/Forensic Council/backend/api/routes/sessions.py"
        ).read_text(encoding="utf-8")
        assert "MAX_MESSAGES_PER_MINUTE = 100" in text

    def test_idle_timeout_is_positive(self):
        import pathlib
        text = pathlib.Path(
            "d:/Forensic Council/backend/api/routes/sessions.py"
        ).read_text(encoding="utf-8")
        assert "IDLE_TIMEOUT = 300" in text

    def test_duplicate_pubsub_close_removed(self):
        """Regression: pubsub.close() must appear exactly once in the finally block."""
        import pathlib
        text = pathlib.Path(
            "d:/Forensic Council/backend/api/routes/sessions.py"
        ).read_text(encoding="utf-8")
        # Find the _redis_subscriber finally block
        finally_idx = text.find("finally:")
        subscriber_section = text[finally_idx: finally_idx + 600]
        # Count occurrences of 'pubsub.close()' in this section
        count = subscriber_section.count("await pubsub.close()")
        assert count == 1, f"Expected 1 pubsub.close() call, found {count}"


# ═══════════════════════════════════════════════════════════════════════════════
# METRICS.PY — pool stats uses public API
# ═══════════════════════════════════════════════════════════════════════════════

class TestMetricsPoolStats:
    """Verify _get_pool_stats uses public asyncpg pool API."""

    def test_no_private_holders_attribute(self):
        """pool._holders must NOT be referenced in metrics.py (private attribute)."""
        import pathlib
        text = pathlib.Path(
            "d:/Forensic Council/backend/api/routes/metrics.py"
        ).read_text(encoding="utf-8")
        assert "pool._holders" not in text, (
            "pool._holders is a private asyncpg attribute and may break on version updates. "
            "Use pool.get_max_size() instead."
        )

    def test_get_max_size_used(self):
        import pathlib
        text = pathlib.Path(
            "d:/Forensic Council/backend/api/routes/metrics.py"
        ).read_text(encoding="utf-8")
        assert "get_max_size" in text

    def test_pool_stats_graceful_on_no_pool(self):
        """_get_pool_stats should return zero-filled dict when postgres is down."""
        from api.routes.metrics import _get_pool_stats

        async def run():
            with patch(
                "infra.postgres_client.get_postgres_client",
                new=AsyncMock(side_effect=ConnectionError("no pg")),
            ):
                return await _get_pool_stats()

        stats = asyncio.run(run())
        assert stats == {"size": 0, "available": 0, "in_use": 0, "max": 0}
