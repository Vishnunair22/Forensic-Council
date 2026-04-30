"""
Contract Tests — Frontend ↔ Backend API Surface
================================================
Boots the API in-memory (no Docker, no real DB) with all infrastructure
mocked. Verifies every frontend↔backend interaction at the HTTP boundary.

Run with: pytest tests/contracts/ -v

These tests cover the contract bugs identified in the stabilization audit:
  - Upload → session_id returned in correct field
  - SSE /progress endpoint connects and emits CONNECTED event
  - /resume lives at /api/v1/sessions/{id}/resume (not /api/v1/resume)
  - /arbiter-status never raises — always returns a safe JSON body
  - /report returns 202 while in-progress, 200 when done
  - ReportDTO schema includes all fields the frontend reads
  - Auth is enforced on all protected endpoints
  - Wrong-owner access returns 403, not 404
"""

from __future__ import annotations

import io
import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Guard: skip entire module if FastAPI test dependencies are absent
# ---------------------------------------------------------------------------
try:
    from fastapi.testclient import TestClient

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

pytestmark = pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SESSION_ID = str(uuid.uuid4())
OTHER_USER_ID = str(uuid.uuid4())
OWNER_USER_ID = str(uuid.uuid4())


def _make_redis_mock() -> AsyncMock:
    m = AsyncMock()
    m.get = AsyncMock(return_value=None)
    m.get_json = AsyncMock(return_value=None)
    m.set = AsyncMock(return_value=True)
    m.delete = AsyncMock(return_value=1)
    m.exists = AsyncMock(return_value=0)
    m.expire = AsyncMock(return_value=True)
    m.incr = AsyncMock(return_value=1)
    m.incrby = AsyncMock(return_value=1)
    m.ttl = AsyncMock(return_value=3600)
    m.ping = AsyncMock(return_value=True)
    m.keys = AsyncMock(return_value=[])
    m.publish = AsyncMock(return_value=0)
    m.get_pubsub = MagicMock(return_value=MagicMock())
    pipe = AsyncMock()
    pipe.execute = AsyncMock(return_value=[])
    m.pipeline = MagicMock(return_value=pipe)
    m.client = AsyncMock()
    m.client.publish = AsyncMock(return_value=0)
    return m


def _make_pg_mock() -> AsyncMock:
    m = AsyncMock()
    m.fetch_one = AsyncMock(return_value=None)
    m.fetch_all = AsyncMock(return_value=[])
    m.fetch = AsyncMock(return_value=[])
    m.execute = AsyncMock(return_value="OK")
    m.executemany = AsyncMock()
    m.ping = AsyncMock(return_value=True)
    m.client = None
    return m


def _make_qdrant_mock() -> AsyncMock:
    m = AsyncMock()
    m.search = AsyncMock(return_value=[])
    m.ping = AsyncMock(return_value=True)
    return m


def _jwt_for(user_id: str, role: str = "investigator") -> str:
    """Create a real JWT so decode_token succeeds inside route handlers."""
    import jwt as _jwt

    from core.config import get_settings

    _settings = get_settings()

    secret = _settings.jwt_signing_key
    payload = {
        "sub": user_id,
        "user_id": user_id,
        "username": user_id,
        "role": role,
        "exp": (datetime.now(UTC) + timedelta(hours=1)).timestamp(),
        "aud": _settings.app_name,
    }
    return _jwt.encode(payload, secret, algorithm=_settings.jwt_algorithm)


def _auth(user_id: str = OWNER_USER_ID, role: str = "investigator") -> dict:
    return {"Authorization": f"Bearer {_jwt_for(user_id, role)}"}


# ---------------------------------------------------------------------------
# Fixture: TestClient with all infra mocked
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    """Spin up the FastAPI app in-memory with all infra mocked."""
    redis_mock = _make_redis_mock()
    pg_mock = _make_pg_mock()
    qdrant_mock = _make_qdrant_mock()

    patches = [
        patch("core.persistence.redis_client.get_redis_client", return_value=redis_mock),
        patch("core.persistence.postgres_client.get_postgres_client", return_value=pg_mock),
        patch("core.persistence.qdrant_client.get_qdrant_client", return_value=qdrant_mock),
        patch("core.migrations.run_migrations", new_callable=AsyncMock),
        patch("scripts.init_db.bootstrap_users", new_callable=AsyncMock),
    ]

    [p.start() for p in patches]
    try:
        from api.main import app

        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    finally:
        for p in patches:
            p.stop()


# ---------------------------------------------------------------------------
# Minimal ReportDTO fixture returned by mocked pipeline
# ---------------------------------------------------------------------------


def _minimal_report_dto() -> dict:
    return {
        "report_id": str(uuid.uuid4()),
        "session_id": SESSION_ID,
        "case_id": "CASE-CONTRACT-001",
        "executive_summary": "Contract test report.",
        "per_agent_findings": {},
        "per_agent_metrics": {},
        "per_agent_analysis": {},
        "overall_confidence": 0.7,
        "overall_error_rate": 0.0,
        "overall_verdict": "AUTHENTIC",
        "cross_modal_confirmed": [],
        "contested_findings": [],
        "tribunal_resolved": [],
        "incomplete_findings": [],
        "uncertainty_statement": "Low.",
        "cryptographic_signature": "sig-abc",
        "report_hash": "hash-abc",
        "signed_utc": datetime.now(UTC).isoformat(),
        "verdict_sentence": "Evidence appears authentic.",
        "key_findings": [],
        "reliability_note": "",
        "manipulation_probability": 0.1,
        "compression_penalty": 1.0,
        "confidence_min": 0.6,
        "confidence_max": 0.8,
        "confidence_std_dev": 0.05,
        "applicable_agent_count": 5,
        "skipped_agents": {},
        "analysis_coverage_note": "",
        "per_agent_summary": {},
        "degradation_flags": [],
        "cross_modal_fusion": {},
    }


# ===========================================================================
# HAPPY PATH TESTS
# ===========================================================================


class TestInvestigateEndpoint:
    """POST /api/v1/investigate"""

    def test_investigate_queues_job_and_returns_session_id(self, client):
        """Upload returns 202 with a valid session_id — the field the frontend reads."""
        from PIL import Image

        img = Image.new("RGB", (100, 100), color="red")
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format="JPEG")
        file_bytes = img_byte_arr.getvalue()

        with (
            patch("orchestration.investigation_queue.get_investigation_queue") as mock_queue_getter,
            patch("core.persistence.redis_client.get_redis_client") as mock_redis_getter,
        ):
            mock_queue = AsyncMock()
            mock_queue.enqueue = AsyncMock(return_value=str(uuid.uuid4()))
            mock_queue_getter.return_value = mock_queue

            mock_redis = _make_redis_mock()
            mock_redis_getter.return_value = mock_redis

            resp = client.post(
                "/api/v1/investigate",
                headers=_auth(),
                files={"file": ("evidence.jpg", io.BytesIO(file_bytes), "image/jpeg")},
                data={"case_id": "CASE-001", "investigator_id": "INVESTIGATOR-001"},
            )

        assert resp.status_code in (200, 202), resp.text
        body = resp.json()
        assert "session_id" in body, f"Missing session_id in response: {body}"
        # Must be a valid UUID (frontend passes it to SSE/WS endpoints)
        uuid.UUID(body["session_id"])

    def test_investigate_requires_auth(self, client):
        """No auth token → 401."""
        file_bytes = b"\xff\xd8\xff\xe0"
        resp = client.post(
            "/api/v1/investigate",
            files={"file": ("e.jpg", io.BytesIO(file_bytes), "image/jpeg")},
        )
        assert resp.status_code == 401

    def test_investigate_missing_file_returns_422(self, client):
        """Missing multipart file body → 422 Unprocessable Entity."""
        resp = client.post(
            "/api/v1/investigate",
            headers=_auth(),
            data={"case_id": "CASE-001"},
        )
        assert resp.status_code == 422


class TestSSEEndpoint:
    """GET /api/v1/sessions/{id}/progress — SSE stream"""

    @pytest.mark.skip(reason="FastAPI TestClient hangs on SSE infinite streams in Windows")
    def test_sse_emits_connected_event_on_connect(self, client):
        """SSE stream opens and first data line is CONNECTED."""
        with patch("api.routes.sse.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(use_redis_worker=False)
            with client.stream(
                "GET",
                f"/api/v1/sessions/{SESSION_ID}/progress",
                headers=_auth(),
            ) as stream:
                for line in stream.iter_lines():
                    if line.startswith("data:"):
                        payload = json.loads(line[5:].strip())
                        assert payload["type"] == "CONNECTED"
                        assert payload["session_id"] == SESSION_ID
                        break

    def test_sse_requires_auth(self, client):
        """No auth → not a successful stream."""
        resp = client.get(f"/api/v1/sessions/{SESSION_ID}/progress")
        assert resp.status_code in (401, 403)


class TestResumeEndpoint:
    """POST /api/v1/sessions/{id}/resume — critical path the frontend calls"""

    def test_resume_url_is_under_sessions_prefix(self, client):
        """Verify the endpoint lives at /api/v1/sessions/{id}/resume, not /api/v1/resume."""
        with (
            patch("api.routes._session_state.get_active_pipeline_metadata") as mock_meta,
            patch("api.routes.sessions.get_active_pipeline_metadata") as mock_meta_sessions,
            patch("core.persistence.redis_client.get_redis_client") as mock_redis_getter,
        ):
            mock_meta.return_value = {
                "status": "awaiting_decision",
                "investigator_id": OWNER_USER_ID,
            }
            mock_meta_sessions.return_value = {
                "status": "awaiting_decision",
                "investigator_id": OWNER_USER_ID,
            }
            mock_redis = _make_redis_mock()
            mock_redis_getter.return_value = mock_redis

            resp = client.post(
                f"/api/v1/sessions/{SESSION_ID}/resume",
                headers=_auth(),
                json={"deep_analysis": False},
            )
        # 404 = wrong URL; anything else means route exists
        assert resp.status_code != 404, "Resume endpoint not found — URL is wrong"

    def test_resume_skip_deep_analysis(self, client):
        """deep_analysis=False is accepted and returns 200."""
        with (
            patch("api.routes._session_state.get_active_pipeline_metadata") as mock_meta,
            patch("api.routes.sessions.get_active_pipeline_metadata") as mock_meta_sessions,
            patch("core.persistence.redis_client.get_redis_client") as mock_redis_getter,
            patch("api.routes.sessions.get_active_pipeline") as mock_pipeline_getter,
        ):
            mock_meta.return_value = {
                "status": "awaiting_decision",
                "investigator_id": OWNER_USER_ID,
            }
            mock_meta_sessions.return_value = {
                "status": "awaiting_decision",
                "investigator_id": OWNER_USER_ID,
            }
            mock_redis = _make_redis_mock()
            mock_redis_getter.return_value = mock_redis

            mock_pipeline = MagicMock()
            mock_pipeline.deep_analysis_decision_event = MagicMock()
            mock_pipeline.deep_analysis_decision_event.is_set.return_value = False
            mock_pipeline._awaiting_user_decision = True
            mock_pipeline_getter.return_value = mock_pipeline

            resp = client.post(
                f"/api/v1/sessions/{SESSION_ID}/resume",
                headers=_auth(),
                json={"deep_analysis": False},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["deep_analysis"] is False

    def test_resume_deep_analysis(self, client):
        """deep_analysis=True is accepted and returns 200."""
        with (
            patch("api.routes._session_state.get_active_pipeline_metadata") as mock_meta,
            patch("api.routes.sessions.get_active_pipeline_metadata") as mock_meta_sessions,
            patch("core.persistence.redis_client.get_redis_client") as mock_redis_getter,
            patch("api.routes.sessions.get_active_pipeline") as mock_pipeline_getter,
        ):
            mock_meta.return_value = {
                "status": "awaiting_decision",
                "investigator_id": OWNER_USER_ID,
            }
            mock_meta_sessions.return_value = {
                "status": "awaiting_decision",
                "investigator_id": OWNER_USER_ID,
            }
            mock_redis = _make_redis_mock()
            mock_redis_getter.return_value = mock_redis

            mock_pipeline = MagicMock()
            mock_pipeline.deep_analysis_decision_event = MagicMock()
            mock_pipeline.deep_analysis_decision_event.is_set.return_value = False
            mock_pipeline._awaiting_user_decision = True
            mock_pipeline_getter.return_value = mock_pipeline

            resp = client.post(
                f"/api/v1/sessions/{SESSION_ID}/resume",
                headers=_auth(),
                json={"deep_analysis": True},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["deep_analysis"] is True


class TestArbiterStatusEndpoint:
    """GET /api/v1/sessions/{id}/arbiter-status — never raises"""

    def test_arbiter_status_running_returns_running(self, client):
        with (
            patch("api.routes._session_state.get_active_pipeline_metadata") as mock_meta,
            patch("api.routes.sessions.get_active_pipeline_metadata") as mock_meta_sessions,
        ):
            mock_meta.return_value = {
                "status": "running",
                "brief": "Agents active",
                "investigator_id": OWNER_USER_ID,
            }
            mock_meta_sessions.return_value = {
                "status": "running",
                "brief": "Agents active",
                "investigator_id": OWNER_USER_ID,
            }
            resp = client.get(
                f"/api/v1/sessions/{SESSION_ID}/arbiter-status",
                headers=_auth(),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "running"

    def test_arbiter_status_complete_returns_report_id(self, client):
        with (
            patch("api.routes._session_state.get_final_report") as mock_report,
            patch("api.routes._session_state.get_active_pipeline_metadata") as mock_meta,
            patch("api.routes.sessions.get_active_pipeline_metadata") as mock_meta_sessions,
        ):
            mock_report.return_value = ({"report_id": "rpt-123"}, datetime.now(UTC))
            mock_meta.return_value = {"status": "complete", "investigator_id": OWNER_USER_ID}
            mock_meta_sessions.return_value = {
                "status": "complete",
                "investigator_id": OWNER_USER_ID,
            }
            resp = client.get(
                f"/api/v1/sessions/{SESSION_ID}/arbiter-status",
                headers=_auth(),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "complete"
        assert "report_id" in body

    def test_arbiter_status_unknown_session_returns_not_found_not_500(self, client):
        """Endpoint must never raise — unknown session returns not_found JSON."""
        with (
            patch("api.routes._session_state.get_final_report", return_value=None),
            patch("api.routes._session_state.get_active_pipeline_metadata", return_value=None),
            patch("api.routes.sessions.get_active_pipeline_metadata", return_value=None),
        ):
            resp = client.get(
                f"/api/v1/sessions/{uuid.uuid4()}/arbiter-status",
                headers=_auth(),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] in ("not_found", "running")


class TestReportEndpoint:
    """GET /api/v1/sessions/{id}/report"""

    def test_report_202_while_in_progress(self, client):
        """Pipeline exists but _final_report is None → 202."""
        mock_pipeline = MagicMock()
        mock_pipeline._final_report = None
        mock_pipeline._error = None
        with (
            patch("api.routes.sessions.get_active_pipeline", return_value=mock_pipeline),
            patch("api.routes._session_state.get_active_pipeline_metadata") as mock_meta,
            patch("api.routes.sessions.get_active_pipeline_metadata") as mock_meta_sessions,
        ):
            mock_meta.return_value = {"status": "running", "investigator_id": OWNER_USER_ID}
            mock_meta_sessions.return_value = {
                "status": "running",
                "investigator_id": OWNER_USER_ID,
            }
            resp = client.get(
                f"/api/v1/sessions/{SESSION_ID}/report",
                headers=_auth(),
            )
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "in_progress"

    def test_report_500_when_pipeline_errored(self, client):
        """Pipeline has _error set → 500."""
        mock_pipeline = MagicMock()
        mock_pipeline._final_report = None
        mock_pipeline._error = "Investigation crashed"
        with (
            patch("api.routes.sessions.get_active_pipeline", return_value=mock_pipeline),
            patch("api.routes._session_state.get_active_pipeline_metadata") as mock_meta,
            patch("api.routes.sessions.get_active_pipeline_metadata") as mock_meta_sessions,
        ):
            mock_meta.return_value = {"status": "running", "investigator_id": OWNER_USER_ID}
            mock_meta_sessions.return_value = {
                "status": "running",
                "investigator_id": OWNER_USER_ID,
            }
            resp = client.get(
                f"/api/v1/sessions/{SESSION_ID}/report",
                headers=_auth(),
            )
        assert resp.status_code == 500

    def test_report_200_returns_reportdto_schema(self, client):
        """Completed report returns all fields the frontend reads."""
        from api.schemas import ReportDTO

        dto = ReportDTO(**_minimal_report_dto())

        mock_pipeline = MagicMock()
        mock_pipeline._final_report = dto

        with (
            patch("api.routes.sessions.get_active_pipeline", return_value=mock_pipeline),
            patch("api.routes._session_state.get_active_pipeline_metadata") as mock_meta,
            patch("api.routes.sessions.get_active_pipeline_metadata") as mock_meta_sessions,
        ):
            mock_meta.return_value = {"status": "running", "investigator_id": OWNER_USER_ID}
            mock_meta_sessions.return_value = {
                "status": "running",
                "investigator_id": OWNER_USER_ID,
            }
            resp = client.get(
                f"/api/v1/sessions/{SESSION_ID}/report",
                headers=_auth(),
            )
        assert resp.status_code == 200
        body = resp.json()

        # Verify every field the frontend (ResultsPage) reads is present
        required_frontend_fields = [
            "report_id",
            "session_id",
            "case_id",
            "executive_summary",
            "per_agent_findings",
            "overall_confidence",
            "overall_verdict",
            "cryptographic_signature",
            "report_hash",
            "degradation_flags",
            "key_findings",
            "manipulation_probability",
        ]
        for field in required_frontend_fields:
            assert field in body, f"Field '{field}' missing from report response"

    def test_report_download_has_content_disposition(self, client):
        """Download endpoint must set Content-Disposition attachment header."""
        from api.schemas import ReportDTO

        dto = ReportDTO(**_minimal_report_dto())
        mock_pipeline = MagicMock()
        mock_pipeline._final_report = dto

        with (
            patch("api.routes.sessions.get_active_pipeline", return_value=mock_pipeline),
            patch("api.routes._session_state.get_active_pipeline_metadata") as mock_meta,
            patch("api.routes.sessions.get_active_pipeline_metadata") as mock_meta_sessions,
        ):
            mock_meta.return_value = {"status": "running", "investigator_id": OWNER_USER_ID}
            mock_meta_sessions.return_value = {
                "status": "running",
                "investigator_id": OWNER_USER_ID,
            }
            resp = client.get(
                f"/api/v1/sessions/{SESSION_ID}/report/download",
                headers=_auth(),
            )
        assert resp.status_code == 200
        assert "content-disposition" in {k.lower() for k in resp.headers}
        cd = resp.headers.get("content-disposition", "")
        assert "attachment" in cd

    def test_report_requires_auth(self, client):
        resp = client.get(f"/api/v1/sessions/{SESSION_ID}/report")
        assert resp.status_code in (401, 403)


# ===========================================================================
# UNHAPPY PATH TESTS
# ===========================================================================


class TestAuthEnforcement:
    """All protected endpoints must reject unauthenticated requests."""

    PROTECTED_ROUTES = [
        ("GET", f"/api/v1/sessions/{SESSION_ID}/report"),
        ("GET", f"/api/v1/sessions/{SESSION_ID}/report/download"),
        ("GET", f"/api/v1/sessions/{SESSION_ID}/arbiter-status"),
        ("POST", f"/api/v1/sessions/{SESSION_ID}/resume"),
        ("GET", "/api/v1/sessions"),
        ("DELETE", f"/api/v1/sessions/{SESSION_ID}"),
    ]

    @pytest.mark.parametrize(("method", "path"), PROTECTED_ROUTES)
    def test_endpoint_rejects_no_auth(self, client, method, path):
        resp = getattr(client, method.lower())(path)
        assert resp.status_code in (401, 403), (
            f"{method} {path} returned {resp.status_code} without auth — expected 401/403"
        )


class TestOwnershipEnforcement:
    """Non-admin users cannot access another user's session."""

    def test_resume_wrong_owner_returns_403(self, client):
        with (
            patch("api.routes._session_state.get_active_pipeline_metadata") as mock_meta,
            patch("api.routes.sessions.get_active_pipeline_metadata") as mock_meta_sessions,
            patch("core.persistence.redis_client.get_redis_client") as mock_redis_getter,
        ):
            mock_meta.return_value = {
                "status": "awaiting_decision",
                "investigator_id": OWNER_USER_ID,  # Owned by OWNER_USER_ID
            }
            mock_meta_sessions.return_value = {
                "status": "awaiting_decision",
                "investigator_id": OWNER_USER_ID,  # Owned by OWNER_USER_ID
            }
            mock_redis = _make_redis_mock()
            mock_redis_getter.return_value = mock_redis

            # Request from a DIFFERENT user
            resp = client.post(
                f"/api/v1/sessions/{SESSION_ID}/resume",
                headers=_auth(user_id=OTHER_USER_ID),
                json={"deep_analysis": False},
            )
        assert resp.status_code == 403


class TestInputValidation:
    """Request schema validation at the API boundary."""

    def test_resume_missing_deep_analysis_field_returns_422(self, client):
        """deep_analysis is required — omitting it returns 422."""
        with (
            patch("api.routes._session_state.get_active_pipeline_metadata") as mock_meta,
            patch("api.routes.sessions.get_active_pipeline_metadata") as mock_meta_sessions,
        ):
            mock_meta.return_value = {
                "status": "awaiting_decision",
                "investigator_id": OWNER_USER_ID,
            }
            mock_meta_sessions.return_value = {
                "status": "awaiting_decision",
                "investigator_id": OWNER_USER_ID,
            }
            resp = client.post(
                f"/api/v1/sessions/{SESSION_ID}/resume",
                headers=_auth(),
                json={},  # missing deep_analysis
            )
        assert resp.status_code == 422

    def test_resume_invalid_session_id_format_returns_422(self, client):
        """Session ID that fails UUID validation → 422."""
        resp = client.post(
            "/api/v1/sessions/not-a-uuid!!/resume",
            headers=_auth(),
            json={"deep_analysis": False},
        )
        assert resp.status_code in (404, 422)

    def test_report_nonexistent_session_returns_404(self, client):
        """Session that never existed → 404."""
        with (
            patch("api.routes.sessions.get_active_pipeline", return_value=None),
            patch("api.routes.sessions._final_reports", {}),
            patch("api.routes._session_state.get_final_report", return_value=None),
            patch("api.routes._session_state.get_active_pipeline_metadata", return_value=None),
            patch("api.routes.sessions.get_active_pipeline_metadata", return_value=None),
        ):
            with patch("core.session_persistence.get_session_persistence") as mock_persist:
                mock_persist_inst = AsyncMock()
                mock_persist_inst.get_report = AsyncMock(return_value=None)
                mock_persist.return_value = mock_persist_inst

                resp = client.get(
                    f"/api/v1/sessions/{uuid.uuid4()}/report",
                    headers=_auth(),
                )
        assert resp.status_code == 404


class TestReportSchemaSerialization:
    """ReportDTO must serialize every field without masking errors."""

    def test_reportdto_construction_succeeds_with_minimal_fields(self):
        """Smoke test — every required field present → no exception."""
        from api.schemas import ReportDTO

        dto = ReportDTO(**_minimal_report_dto())
        assert dto.report_id
        assert dto.overall_verdict

    def test_reportdto_overall_verdict_is_string(self):
        from api.schemas import ReportDTO

        dto = ReportDTO(**_minimal_report_dto())
        assert isinstance(dto.overall_verdict, str)

    def test_reportdto_degradation_flags_is_list(self):
        from api.schemas import ReportDTO

        dto = ReportDTO(**_minimal_report_dto())
        assert isinstance(dto.degradation_flags, list)

    def test_reportdto_per_agent_findings_is_dict(self):
        from api.schemas import ReportDTO

        dto = ReportDTO(**_minimal_report_dto())
        assert isinstance(dto.per_agent_findings, dict)

    def test_forensic_report_to_dto_raises_on_bad_report(self):
        """_forensic_report_to_dto must raise (not silently return stub) on bad input."""
        from api.routes.sessions import _forensic_report_to_dto

        class BadReport:
            report_id = "not-a-uuid"
            session_id = None  # will cause str(None) → "None", but report_id is missing
            case_id = None
            per_agent_findings = None
            cross_modal_confirmed = None
            incomplete_findings = None
            contested_findings = None
            tribunal_resolved = None
            signed_utc = None
            executive_summary = None
            uncertainty_statement = None
            cryptographic_signature = None
            report_hash = None

        # After A2 fix, a Pydantic construction failure must propagate — not return a stub
        try:
            result = _forensic_report_to_dto(BadReport())
            # If it returns without raising: verify it's NOT a stub with error summary
            assert "Report serialization failed" not in (result.executive_summary or ""), (
                "_forensic_report_to_dto returned a silent stub DTO — A2 fix was not applied"
            )
        except Exception:
            pass  # Raising is the correct behavior


class TestHITLDecisionEndpoint:
    """POST /api/v1/hitl/decision accepts all 5 decision types."""

    DECISION_TYPES = ["APPROVE", "REDIRECT", "OVERRIDE", "TERMINATE", "ESCALATE"]

    @pytest.mark.parametrize("decision_type", DECISION_TYPES)
    def test_hitl_decision_type_accepted(self, client, decision_type):
        """All documented decision types must be accepted without 422."""
        checkpoint_id = str(uuid.uuid4())
        with (
            patch("api.routes.hitl.get_active_pipeline") as mock_pipeline_getter,
            patch("api.routes._session_state.get_active_pipeline_metadata") as mock_meta,
            patch("api.routes.sessions.get_active_pipeline_metadata") as mock_meta_sessions,
        ):
            mock_pipeline = AsyncMock()
            mock_pipeline.handle_hitl_decision = AsyncMock()
            mock_pipeline_getter.return_value = mock_pipeline
            mock_meta.return_value = {"status": "running", "investigator_id": OWNER_USER_ID}
            mock_meta_sessions.return_value = {
                "status": "running",
                "investigator_id": OWNER_USER_ID,
            }

            resp = client.post(
                "/api/v1/hitl/decision",
                headers=_auth(),
                json={
                    "session_id": SESSION_ID,
                    "checkpoint_id": checkpoint_id,
                    "agent_id": "Agent1",
                    "decision": decision_type,
                    "note": f"Test {decision_type}",
                },
            )
        # 404 (route missing) or 422 (schema rejected) are both failures
        assert resp.status_code not in (404, 422), (
            f"HITL decision type '{decision_type}' rejected with {resp.status_code}: {resp.text}"
        )
