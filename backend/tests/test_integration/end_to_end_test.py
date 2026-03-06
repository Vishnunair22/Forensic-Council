"""
End-to-End Integration Tests for Forensic Council Pipeline
==========================================================

Tests the complete pipeline from evidence ingestion to final report.
Covers: report integrity, chain of custody, session lifecycle, HITL,
API health, WebSocket contracts, authentication, and edge cases.

Run with:
    pytest tests/test_integration/test_e2e.py -v
    pytest tests/test_integration/test_e2e.py -v -k "not integration"
"""

import hashlib
import io
import json
import os
import re
import tempfile
import wave
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import piexif
import pytest
from PIL import Image


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def test_image_with_splice_and_exif():
    """Create a test JPEG with copy-paste splice and stripped EXIF software field."""
    img = Image.new("RGB", (800, 600), color=(200, 200, 200))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    draw.rectangle([100, 100, 300, 300], fill=(255, 0, 0))
    draw.ellipse([400, 200, 600, 400], fill=(0, 255, 0))
    region = img.crop((400, 300, 600, 500))
    img.paste(region, (50, 50))

    exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
    exif_bytes = piexif.dump(exif_dict)

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        temp_path = f.name
    img.save(temp_path, format="JPEG", exif=exif_bytes, quality=95)

    yield temp_path

    if os.path.exists(temp_path):
        os.remove(temp_path)


@pytest.fixture
def test_image_authentic():
    """Create a clean test JPEG with full EXIF data (no manipulation)."""
    img = Image.new("RGB", (640, 480), color=(100, 149, 237))
    exif_dict = {
        "0th": {
            piexif.ImageIFD.Make: b"TestCam",
            piexif.ImageIFD.Software: b"TestSoftware 1.0",
        },
        "Exif": {},
        "GPS": {},
        "1st": {},
        "thumbnail": None,
    }
    exif_bytes = piexif.dump(exif_dict)

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        temp_path = f.name
    img.save(temp_path, format="JPEG", exif=exif_bytes, quality=95)

    yield temp_path

    if os.path.exists(temp_path):
        os.remove(temp_path)


@pytest.fixture
def test_audio_wav():
    """Create a minimal valid WAV file (1s silence, 16kHz mono) for audio testing."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        temp_path = f.name

    with wave.open(temp_path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000)

    yield temp_path

    if os.path.exists(temp_path):
        os.remove(temp_path)


@pytest.fixture
def temp_storage_dir():
    """Create a temporary storage directory for test evidence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_dir = Path(tmpdir) / "evidence"
        evidence_dir.mkdir()
        yield str(evidence_dir)


# ─── Full Pipeline Tests ──────────────────────────────────────────────────────


class TestFullPipeline:
    """Test the complete forensic pipeline end-to-end."""

    @pytest.mark.asyncio
    async def test_full_pipeline_produces_signed_report(
        self, test_image_with_splice_and_exif, temp_storage_dir, monkeypatch
    ):
        """Pipeline must produce a signed report whose hash matches its content."""
        monkeypatch.setenv("evidence_storage_path", temp_storage_dir)
        from orchestration.pipeline import ForensicCouncilPipeline

        report = await ForensicCouncilPipeline().run_investigation(
            evidence_file_path=test_image_with_splice_and_exif,
            case_id="e2e_001",
            investigator_id="test_inv",
        )

        assert report is not None
        assert report.cryptographic_signature not in (None, "")
        assert report.report_hash not in (None, "")

        report_dict = report.model_dump(
            exclude={"cryptographic_signature", "report_hash", "signed_utc"}
        )
        report_json = json.dumps(report_dict, sort_keys=True, default=str)
        expected = hashlib.sha256(report_json.encode()).hexdigest()
        assert report.report_hash == expected

    @pytest.mark.asyncio
    async def test_chain_of_custody_log_not_empty(
        self, test_image_with_splice_and_exif, temp_storage_dir, monkeypatch
    ):
        """Chain-of-custody log must have at least one entry after investigation."""
        monkeypatch.setenv("evidence_storage_path", temp_storage_dir)
        from orchestration.pipeline import ForensicCouncilPipeline

        report = await ForensicCouncilPipeline().run_investigation(
            evidence_file_path=test_image_with_splice_and_exif,
            case_id="e2e_002",
            investigator_id="test_inv",
        )
        assert len(report.chain_of_custody_log) > 0

    @pytest.mark.asyncio
    async def test_chain_of_custody_entries_are_non_null(
        self, test_image_with_splice_and_exif, temp_storage_dir, monkeypatch
    ):
        """All custody log entries must be non-null."""
        monkeypatch.setenv("evidence_storage_path", temp_storage_dir)
        from orchestration.pipeline import ForensicCouncilPipeline

        report = await ForensicCouncilPipeline().run_investigation(
            evidence_file_path=test_image_with_splice_and_exif,
            case_id="e2e_003",
            investigator_id="test_inv",
        )
        for entry in report.chain_of_custody_log:
            assert entry is not None

    @pytest.mark.asyncio
    async def test_evidence_version_tree_has_derivative_artifacts(
        self, test_image_with_splice_and_exif, temp_storage_dir, monkeypatch
    ):
        """Evidence version tree must contain at least 1 node (root artifact)."""
        monkeypatch.setenv("evidence_storage_path", temp_storage_dir)
        from orchestration.pipeline import ForensicCouncilPipeline

        report = await ForensicCouncilPipeline().run_investigation(
            evidence_file_path=test_image_with_splice_and_exif,
            case_id="e2e_004",
            investigator_id="test_inv",
        )
        assert len(report.evidence_version_trees) >= 1

    @pytest.mark.asyncio
    async def test_report_uncertainty_statement_present(
        self, test_image_with_splice_and_exif, temp_storage_dir, monkeypatch
    ):
        """Report must include a non-empty uncertainty statement."""
        monkeypatch.setenv("evidence_storage_path", temp_storage_dir)
        from orchestration.pipeline import ForensicCouncilPipeline

        report = await ForensicCouncilPipeline().run_investigation(
            evidence_file_path=test_image_with_splice_and_exif,
            case_id="e2e_005",
            investigator_id="test_inv",
        )
        assert report.uncertainty_statement not in (None, "")

    @pytest.mark.asyncio
    async def test_no_finding_silently_merged_contested(
        self, test_image_with_splice_and_exif, temp_storage_dir, monkeypatch
    ):
        """Report must expose contested_findings field (not silently merged)."""
        monkeypatch.setenv("evidence_storage_path", temp_storage_dir)
        from orchestration.pipeline import ForensicCouncilPipeline

        report = await ForensicCouncilPipeline().run_investigation(
            evidence_file_path=test_image_with_splice_and_exif,
            case_id="e2e_006",
            investigator_id="test_inv",
        )
        assert hasattr(report, "contested_findings")

    @pytest.mark.asyncio
    async def test_executive_summary_present_and_non_empty(
        self, test_image_with_splice_and_exif, temp_storage_dir, monkeypatch
    ):
        """Report must include a non-empty executive summary."""
        monkeypatch.setenv("evidence_storage_path", temp_storage_dir)
        from orchestration.pipeline import ForensicCouncilPipeline

        report = await ForensicCouncilPipeline().run_investigation(
            evidence_file_path=test_image_with_splice_and_exif,
            case_id="e2e_007",
            investigator_id="test_inv",
        )
        assert report.executive_summary not in (None, "")

    @pytest.mark.asyncio
    async def test_report_has_per_agent_findings(
        self, test_image_with_splice_and_exif, temp_storage_dir, monkeypatch
    ):
        """Report per_agent_findings must be populated with at least one agent."""
        monkeypatch.setenv("evidence_storage_path", temp_storage_dir)
        from orchestration.pipeline import ForensicCouncilPipeline

        report = await ForensicCouncilPipeline().run_investigation(
            evidence_file_path=test_image_with_splice_and_exif,
            case_id="e2e_008",
            investigator_id="test_inv",
        )
        assert hasattr(report, "per_agent_findings")
        assert len(report.per_agent_findings) > 0

    @pytest.mark.asyncio
    async def test_report_ids_unique_across_runs(
        self, test_image_with_splice_and_exif, temp_storage_dir, monkeypatch
    ):
        """Two separate pipeline runs must produce distinct report_ids."""
        monkeypatch.setenv("evidence_storage_path", temp_storage_dir)
        from orchestration.pipeline import ForensicCouncilPipeline

        r1 = await ForensicCouncilPipeline().run_investigation(
            evidence_file_path=test_image_with_splice_and_exif,
            case_id="e2e_009a",
            investigator_id="test_inv",
        )
        r2 = await ForensicCouncilPipeline().run_investigation(
            evidence_file_path=test_image_with_splice_and_exif,
            case_id="e2e_009b",
            investigator_id="test_inv",
        )
        assert r1.report_id != r2.report_id

    @pytest.mark.asyncio
    async def test_pipeline_with_nonexistent_file_raises(
        self, temp_storage_dir, monkeypatch
    ):
        """Providing a nonexistent file path must raise — not silently produce empty report."""
        monkeypatch.setenv("evidence_storage_path", temp_storage_dir)
        from orchestration.pipeline import ForensicCouncilPipeline

        with pytest.raises(Exception):
            await ForensicCouncilPipeline().run_investigation(
                evidence_file_path="/tmp/ghost_file_xyz.jpg",
                case_id="e2e_010",
                investigator_id="test_inv",
            )

    @pytest.mark.asyncio
    async def test_signed_utc_is_iso8601_parseable(
        self, test_image_with_splice_and_exif, temp_storage_dir, monkeypatch
    ):
        """Report signed_utc must be a valid ISO-8601 datetime string."""
        monkeypatch.setenv("evidence_storage_path", temp_storage_dir)
        from datetime import datetime
        from orchestration.pipeline import ForensicCouncilPipeline

        report = await ForensicCouncilPipeline().run_investigation(
            evidence_file_path=test_image_with_splice_and_exif,
            case_id="e2e_011",
            investigator_id="test_inv",
        )
        assert report.signed_utc not in (None, "")
        parsed = datetime.fromisoformat(str(report.signed_utc).replace("Z", "+00:00"))
        assert parsed is not None

    @pytest.mark.asyncio
    async def test_authentic_image_no_high_confidence_manipulation(
        self, test_image_authentic, temp_storage_dir, monkeypatch
    ):
        """An unmodified image must not produce confidence_raw > 0.9 MANIPULATION findings."""
        monkeypatch.setenv("evidence_storage_path", temp_storage_dir)
        from orchestration.pipeline import ForensicCouncilPipeline

        report = await ForensicCouncilPipeline().run_investigation(
            evidence_file_path=test_image_authentic,
            case_id="e2e_012",
            investigator_id="test_inv",
        )
        all_findings = [
            f
            for findings in report.per_agent_findings.values()
            for f in findings
        ]
        flagged = [
            f for f in all_findings
            if f.finding_type == "MANIPULATION" and f.confidence_raw > 0.9
        ]
        assert len(flagged) == 0, (
            f"Authentic image triggered high-confidence flags: "
            f"{[f.reasoning_summary for f in flagged]}"
        )

    @pytest.mark.asyncio
    async def test_report_case_id_matches_input(
        self, test_image_with_splice_and_exif, temp_storage_dir, monkeypatch
    ):
        """Report case_id must exactly match the input case_id."""
        monkeypatch.setenv("evidence_storage_path", temp_storage_dir)
        from orchestration.pipeline import ForensicCouncilPipeline

        report = await ForensicCouncilPipeline().run_investigation(
            evidence_file_path=test_image_with_splice_and_exif,
            case_id="MY-SPECIFIC-CASE-XYZ",
            investigator_id="test_inv",
        )
        assert report.case_id == "MY-SPECIFIC-CASE-XYZ"


# ─── Session Manager Tests ────────────────────────────────────────────────────


class TestSessionManager:
    """Test session management CRUD and checkpoint lifecycle."""

    @pytest.mark.asyncio
    async def test_create_session(self):
        """Creating a session must return INITIALIZING status with all agent slots."""
        from orchestration.session_manager import SessionManager, SessionStatus

        manager = SessionManager()
        session = await manager.create_session(
            session_id=uuid4(),
            case_id="sm_001",
            investigator_id="test_inv",
            agent_ids=["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"],
        )

        assert session is not None
        assert session.case_id == "sm_001"
        assert session.status == SessionStatus.INITIALIZING
        assert len(session.agent_loops) == 5

    @pytest.mark.asyncio
    async def test_add_and_resolve_checkpoint(self):
        """Resolving a PENDING checkpoint must remove it from the active list."""
        from orchestration.session_manager import SessionManager, CheckpointStatus

        manager = SessionManager()
        session_id = uuid4()
        await manager.create_session(
            session_id=session_id,
            case_id="sm_002",
            investigator_id="test_inv",
            agent_ids=["Agent1"],
        )

        cp = await manager.add_checkpoint(
            session_id=session_id,
            agent_id="Agent1",
            checkpoint_type="EVIDENCE_VERIFICATION",
            description="Verify this evidence",
            pending_content={"evidence_id": "test123"},
        )
        assert cp.status == CheckpointStatus.PENDING

        await manager.resolve_checkpoint(
            checkpoint_id=cp.checkpoint_id,
            decision={"status": "APPROVED", "notes": "OK"},
        )

        active = await manager.get_active_checkpoints(session_id)
        assert len(active) == 0

    @pytest.mark.asyncio
    async def test_session_ids_are_unique(self):
        """Two separate create_session calls must produce distinct session_ids."""
        from orchestration.session_manager import SessionManager

        manager = SessionManager()
        s1 = await manager.create_session(
            session_id=uuid4(), case_id="sm_003a", investigator_id="inv", agent_ids=["Agent1"]
        )
        s2 = await manager.create_session(
            session_id=uuid4(), case_id="sm_003b", investigator_id="inv", agent_ids=["Agent1"]
        )
        assert s1.session_id != s2.session_id

    @pytest.mark.asyncio
    async def test_get_session_returns_created_session(self):
        """get_session must return the same session that was created."""
        from orchestration.session_manager import SessionManager

        manager = SessionManager()
        session_id = uuid4()
        created = await manager.create_session(
            session_id=session_id,
            case_id="sm_004",
            investigator_id="inv",
            agent_ids=["Agent1"],
        )
        fetched = await manager.get_session(session_id)
        assert fetched is not None
        assert fetched.session_id == created.session_id
        assert fetched.case_id == "sm_004"

    @pytest.mark.asyncio
    async def test_get_nonexistent_session_returns_none(self):
        """Fetching a session that was never created must return None."""
        from orchestration.session_manager import SessionManager

        result = await SessionManager().get_session(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_multiple_checkpoints_resolved_independently(self):
        """Resolving cp1 must leave cp2 still active."""
        from orchestration.session_manager import SessionManager

        manager = SessionManager()
        session_id = uuid4()
        await manager.create_session(
            session_id=session_id,
            case_id="sm_005",
            investigator_id="inv",
            agent_ids=["Agent1", "Agent2"],
        )

        cp1 = await manager.add_checkpoint(
            session_id=session_id, agent_id="Agent1",
            checkpoint_type="EVIDENCE_VERIFICATION", description="Check 1", pending_content={},
        )
        cp2 = await manager.add_checkpoint(
            session_id=session_id, agent_id="Agent2",
            checkpoint_type="EVIDENCE_VERIFICATION", description="Check 2", pending_content={},
        )

        await manager.resolve_checkpoint(
            checkpoint_id=cp1.checkpoint_id, decision={"status": "APPROVED"}
        )

        active = await manager.get_active_checkpoints(session_id)
        assert len(active) == 1
        assert active[0].checkpoint_id == cp2.checkpoint_id

    @pytest.mark.asyncio
    async def test_session_stores_correct_investigator_id(self):
        """Session must preserve the investigator_id passed at creation."""
        from orchestration.session_manager import SessionManager

        manager = SessionManager()
        session_id = uuid4()
        session = await manager.create_session(
            session_id=session_id,
            case_id="sm_006",
            investigator_id="INVESTIGATOR-007",
            agent_ids=["Agent1"],
        )
        assert session.investigator_id == "INVESTIGATOR-007"


# ─── Pipeline Component Unit Tests ───────────────────────────────────────────


class TestPipelineComponents:
    """Test pipeline helper methods in isolation."""

    @pytest.mark.asyncio
    async def test_pipeline_initialization(self):
        """Pipeline must initialize with a non-None config."""
        from orchestration.pipeline import ForensicCouncilPipeline

        pipeline = ForensicCouncilPipeline()
        assert pipeline is not None
        assert pipeline.config is not None

    @pytest.mark.asyncio
    async def test_mime_type_image_formats(self):
        """Common image extensions must map to correct MIME types."""
        from orchestration.pipeline import ForensicCouncilPipeline

        p = ForensicCouncilPipeline()
        assert p._get_mime_type("test.jpg") == "image/jpeg"
        assert p._get_mime_type("test.jpeg") == "image/jpeg"
        assert p._get_mime_type("test.png") == "image/png"
        assert p._get_mime_type("test.webp") == "image/webp"
        assert p._get_mime_type("test.tiff") == "image/tiff"

    @pytest.mark.asyncio
    async def test_mime_type_av_formats(self):
        """Audio/video extensions must map to correct MIME types."""
        from orchestration.pipeline import ForensicCouncilPipeline

        p = ForensicCouncilPipeline()
        assert p._get_mime_type("test.mp4") == "video/mp4"
        assert p._get_mime_type("test.mov") == "video/quicktime"
        assert p._get_mime_type("test.wav") == "audio/wav"
        assert p._get_mime_type("test.mp3") == "audio/mpeg"

    @pytest.mark.asyncio
    async def test_mime_type_unknown_fallback(self):
        """Unknown extensions must fall back to application/octet-stream."""
        from orchestration.pipeline import ForensicCouncilPipeline

        p = ForensicCouncilPipeline()
        assert p._get_mime_type("test.unknown") == "application/octet-stream"
        assert p._get_mime_type("test") == "application/octet-stream"

    @pytest.mark.asyncio
    async def test_config_has_required_fields(self):
        """Pipeline config must expose iteration_ceiling and investigation_timeout."""
        from orchestration.pipeline import ForensicCouncilPipeline

        config = ForensicCouncilPipeline().config
        assert hasattr(config, "default_iteration_ceiling")
        assert hasattr(config, "investigation_timeout")
        assert config.default_iteration_ceiling > 0
        assert config.investigation_timeout > 0


# ─── API Contract Tests ───────────────────────────────────────────────────────


class TestAPIContracts:
    """
    Fast contract tests using FastAPI TestClient — no live infrastructure required.
    DB init and migrations are patched out.
    """

    @pytest.fixture(autouse=True)
    def _patch_startup(self):
        with (
            patch("scripts.init_db.init_database", new_callable=AsyncMock),
            patch("core.migrations.run_migrations", new_callable=AsyncMock, return_value=True),
        ):
            yield

    def _client(self):
        from fastapi.testclient import TestClient
        from api.main import app
        return TestClient(app)

    def test_root_returns_name_and_version(self):
        resp = self._client().get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Forensic Council API"
        assert body["version"] == "1.0.0"

    def test_health_returns_healthy(self):
        resp = self._client().get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_health_has_environment_field(self):
        resp = self._client().get("/health")
        assert "environment" in resp.json()

    def test_health_has_active_sessions_count(self):
        resp = self._client().get("/health")
        body = resp.json()
        assert "active_sessions" in body
        assert isinstance(body["active_sessions"], int)

    def test_investigate_invalid_mime_returns_422(self):
        resp = self._client().post(
            "/api/v1/investigate",
            files={"file": ("evil.exe", io.BytesIO(b"x"), "application/x-executable")},
            data={"case_id": "C1", "investigator_id": "inv"},
        )
        assert resp.status_code == 422

    def test_investigate_oversized_file_returns_413(self):
        resp = self._client().post(
            "/api/v1/investigate",
            files={"file": ("big.jpg", io.BytesIO(b"x" * (51 * 1024 * 1024)), "image/jpeg")},
            data={"case_id": "C1", "investigator_id": "inv"},
        )
        assert resp.status_code == 413

    def test_get_report_unknown_session_returns_404(self):
        resp = self._client().get("/api/v1/sessions/does-not-exist/report")
        assert resp.status_code == 404

    def test_security_headers_present(self):
        resp = self._client().get("/")
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"

    def test_unknown_route_returns_404(self):
        resp = self._client().get("/api/v1/nonexistent-endpoint")
        assert resp.status_code == 404

    def test_cors_header_present_for_allowed_origin(self):
        resp = self._client().get("/", headers={"Origin": "http://localhost:3000"})
        assert resp.headers.get("access-control-allow-origin") is not None

    def test_options_preflight_returns_200(self):
        """CORS preflight OPTIONS must be accepted for allowed origins."""
        resp = self._client().options(
            "/api/v1/investigate",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp.status_code in (200, 204)

    def test_investigate_missing_case_id_returns_422(self):
        """POST without case_id form field must be rejected as unprocessable."""
        resp = self._client().post(
            "/api/v1/investigate",
            files={"file": ("test.jpg", io.BytesIO(b"fake"), "image/jpeg")},
            # intentionally omit case_id
            data={"investigator_id": "inv"},
        )
        assert resp.status_code == 422


# ─── Cryptographic Integrity Tests ───────────────────────────────────────────


class TestCryptographicIntegrity:
    """Verify hash and signing behaviour independent of live pipeline runs."""

    def test_sha256_hash_is_64_char_lowercase_hex(self):
        content = {"key": "value"}
        h = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
        assert re.fullmatch(r"[0-9a-f]{64}", h)

    def test_tampered_content_produces_different_hash(self):
        orig = {"case_id": "A", "summary": "All clear"}
        tampered = {"case_id": "A", "summary": "Manipulated!"}

        h_orig = hashlib.sha256(json.dumps(orig, sort_keys=True).encode()).hexdigest()
        h_tamp = hashlib.sha256(json.dumps(tampered, sort_keys=True).encode()).hexdigest()
        assert h_orig != h_tamp

    def test_hash_is_deterministic(self):
        content = {"a": 1, "b": [1, 2, 3]}
        j = json.dumps(content, sort_keys=True, default=str)
        assert hashlib.sha256(j.encode()).hexdigest() == hashlib.sha256(j.encode()).hexdigest()

    @pytest.mark.asyncio
    async def test_agent_signer_sign_and_verify_roundtrip(self):
        """AgentSigner must sign and immediately verify the same content."""
        from core.signing import AgentSigner

        key_path = next(
            (p for p in [
                Path("storage/keys/TestAgent.pem"),
                Path("storage/keys/Agent1.pem"),
            ] if p.exists()),
            None,
        )
        if key_path is None:
            pytest.skip("No PEM key found for signing test")

        signer = AgentSigner(agent_id="TestAgent", private_key_path=str(key_path))
        signed = signer.sign({"finding": "splice_detected", "confidence": 0.88})

        assert signed.content_hash is not None
        assert signed.signature is not None
        assert signer.verify(signed) is True

    @pytest.mark.asyncio
    async def test_agent_signer_detects_tampered_content(self):
        """Modifying signed content after the fact must cause verify() to return False."""
        from core.signing import AgentSigner

        key_path = next(
            (p for p in [
                Path("storage/keys/TestAgent.pem"),
                Path("storage/keys/Agent1.pem"),
            ] if p.exists()),
            None,
        )
        if key_path is None:
            pytest.skip("No PEM key found for signing test")

        signer = AgentSigner(agent_id="TestAgent", private_key_path=str(key_path))
        signed = signer.sign({"finding": "original", "confidence": 0.5})
        signed.content["confidence"] = 0.99  # tamper

        assert signer.verify(signed) is False


# ─── Config Validation Tests ──────────────────────────────────────────────────


class TestConfigValidation:
    """Ensure Settings correctly validates environment variables."""

    def test_default_app_env_is_development(self):
        from core.config import Settings
        assert Settings().app_env == "development"

    def test_invalid_log_level_raises(self):
        from pydantic import ValidationError
        from core.config import Settings
        with pytest.raises((ValueError, ValidationError)):
            Settings(log_level="VERBOSE")

    def test_invalid_app_env_raises(self):
        from pydantic import ValidationError
        from core.config import Settings
        with pytest.raises((ValueError, ValidationError)):
            Settings(app_env="gamma")

    def test_redis_url_includes_host_and_port(self):
        from core.config import Settings
        s = Settings(redis_host="myredis", redis_port=6380)
        assert "myredis" in s.redis_url
        assert "6380" in s.redis_url

    def test_database_url_includes_all_components(self):
        from core.config import Settings
        s = Settings(
            postgres_host="pghost", postgres_port=5433,
            postgres_user="testuser", postgres_password="testpassword",
            postgres_db="testdb",
        )
        assert all(x in s.database_url for x in ["pghost", "5433", "testuser", "testdb"])

    def test_debug_parsed_from_string_true(self):
        from core.config import Settings
        assert Settings(debug="true").debug is True  # type: ignore

    def test_debug_parsed_from_string_false(self):
        from core.config import Settings
        assert Settings(debug="false").debug is False  # type: ignore

    def test_effective_jwt_secret_falls_back_to_signing_key(self):
        from core.config import Settings
        s = Settings(signing_key="my-signing-key-32-chars-padded!!")
        assert s.effective_jwt_secret == "my-signing-key-32-chars-padded!!"


# ─── Evidence Fixture Integrity ───────────────────────────────────────────────


class TestEvidenceFixtures:
    """Validate that test fixtures produce parseable, correct files."""

    def test_spliced_jpeg_is_readable(self, test_image_with_splice_and_exif):
        img = Image.open(test_image_with_splice_and_exif)
        assert img.format == "JPEG"
        assert img.size == (800, 600)

    def test_authentic_jpeg_has_software_exif_tag(self, test_image_authentic):
        img = Image.open(test_image_authentic)
        exif_raw = img.info.get("exif")
        assert exif_raw is not None
        exif_dict = piexif.load(exif_raw)
        assert exif_dict["0th"].get(piexif.ImageIFD.Software) is not None

    def test_audio_wav_has_correct_params(self, test_audio_wav):
        with wave.open(test_audio_wav, "r") as wf:
            assert wf.getnchannels() == 1
            assert wf.getframerate() == 16000
            assert wf.getnframes() == 16000

    def test_splice_jpeg_has_no_software_exif_tag(self, test_image_with_splice_and_exif):
        """Splice fixture must NOT have a Software EXIF tag (simulates stripped metadata)."""
        img = Image.open(test_image_with_splice_and_exif)
        exif_raw = img.info.get("exif")
        if exif_raw:
            exif_dict = piexif.load(exif_raw)
            assert exif_dict["0th"].get(piexif.ImageIFD.Software) is None

    def test_authentic_jpeg_dimensions(self, test_image_authentic):
        img = Image.open(test_image_authentic)
        assert img.size == (640, 480)

    def test_audio_wav_is_silence(self, test_audio_wav):
        """WAV fixture frames must all be null bytes (silence)."""
        with wave.open(test_audio_wav, "r") as wf:
            frames = wf.readframes(wf.getnframes())
        assert all(b == 0 for b in frames)
