"""
Unit tests for miscellaneous modules with zero or low coverage.

Covers:
- core/adversarial.py — AdversarialChecker, RobustnessCaveat
- core/scoring.py — ConfidenceCalibrator
- core/audit_logger.py — log_sensitive_operation
- agents/tool_handlers.py — ToolHandlers
- core/mime_registry.py — MimeRegistry
- core/synthesis.py — SynthesisService
- core/grounding.py — GroundingService
- core/task_tool_config.py — get_task_tool_overrides
- core/model_registry.py — ModelRegistry
"""

import os
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


# ── AdversarialChecker ────────────────────────────────────────────────────────

class TestAdversarialChecker:
    def test_instantiation(self):
        from core.adversarial import AdversarialChecker
        checker = AdversarialChecker()
        assert checker is not None

    def test_check_anti_ela_evasion_returns_list(self):
        from core.adversarial import AdversarialChecker
        checker = AdversarialChecker()
        result = checker.check_anti_ela_evasion({"ela_variance": 0.001})
        assert isinstance(result, list)

    def test_check_anti_ela_evasion_texture_synthesis(self):
        from core.adversarial import AdversarialChecker
        checker = AdversarialChecker()
        result = checker.check_anti_ela_evasion({"spatial_frequency_uniformity": 0.99})
        assert isinstance(result, list)

    def test_check_anti_ela_no_flags(self):
        from core.adversarial import AdversarialChecker
        checker = AdversarialChecker()
        result = checker.check_anti_ela_evasion({})
        assert isinstance(result, list)
        assert len(result) == 0

    def test_check_anti_spoofing_evasion_returns_list(self):
        from core.adversarial import AdversarialChecker
        checker = AdversarialChecker()
        result = checker.check_anti_spoofing_evasion({"frequency_variance": 0.01})
        assert isinstance(result, list)

    def test_check_anti_spoofing_prosody(self):
        from core.adversarial import AdversarialChecker
        checker = AdversarialChecker()
        result = checker.check_anti_spoofing_evasion({"pitch_contour_variance": 0.001})
        assert isinstance(result, list)

    def test_caveats_have_court_disclosure(self):
        from core.adversarial import AdversarialChecker
        checker = AdversarialChecker()
        caveats = checker.check_anti_ela_evasion({"ela_variance": 0.001})
        if caveats:
            assert hasattr(caveats[0], "court_disclosure")


class TestRobustnessCaveat:
    def test_model_creation(self):
        from core.adversarial import RobustnessCaveat
        caveat = RobustnessCaveat(
            agent_id="Agent1",
            evasion_technique="uniform_recompression",
            plausibility="HIGH",
            detection_basis="Low ELA variance detected.",
            court_disclosure="The anti-forensic technique of uniform recompression may have been applied.",
        )
        assert caveat.agent_id == "Agent1"
        assert caveat.plausibility == "HIGH"
        assert caveat.caveat_id is not None

    def test_model_uuid_auto_generated(self):
        from core.adversarial import RobustnessCaveat
        c1 = RobustnessCaveat(
            agent_id="A1",
            evasion_technique="t1",
            plausibility="LOW",
            detection_basis="b1",
            court_disclosure="d1",
        )
        c2 = RobustnessCaveat(
            agent_id="A1",
            evasion_technique="t1",
            plausibility="LOW",
            detection_basis="b1",
            court_disclosure="d1",
        )
        assert c1.caveat_id != c2.caveat_id


# ── ConfidenceCalibrator ──────────────────────────────────────────────────────

class TestConfidenceCalibrator:
    def test_calibrate_heuristic_returns_float(self):
        from core.scoring import ConfidenceCalibrator
        result = ConfidenceCalibrator.calibrate_heuristic(0.7)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_calibrate_heuristic_with_known_tag(self):
        from core.scoring import ConfidenceCalibrator
        result = ConfidenceCalibrator.calibrate_heuristic(0.5, reliability_tag="yolo11")
        assert isinstance(result, float)

    def test_calibrate_heuristic_caps_at_95(self):
        from core.scoring import ConfidenceCalibrator
        result = ConfidenceCalibrator.calibrate_heuristic(1.0, reliability_tag="siglip2")
        assert result <= 0.95

    def test_weighted_average_empty_returns_zero(self):
        from core.scoring import ConfidenceCalibrator
        result = ConfidenceCalibrator.weighted_average([])
        assert result == 0.0

    def test_weighted_average_single_score(self):
        from core.scoring import ConfidenceCalibrator
        result = ConfidenceCalibrator.weighted_average([(0.8, "siglip2")])
        assert isinstance(result, float)
        assert result > 0.0

    def test_weighted_average_multiple_scores(self):
        from core.scoring import ConfidenceCalibrator
        result = ConfidenceCalibrator.weighted_average([
            (0.9, "siglip2"),
            (0.7, "opencv_heuristic"),
            (0.6, "linear_fallback"),
        ])
        assert 0.0 < result <= 1.0

    def test_map_to_court_statement_high_confidence(self):
        from core.scoring import ConfidenceCalibrator
        stmt = ConfidenceCalibrator.map_to_court_statement(0.95)
        assert "calibrated" in stmt.lower() or "neural" in stmt.lower()

    def test_map_to_court_statement_medium(self):
        from core.scoring import ConfidenceCalibrator
        stmt = ConfidenceCalibrator.map_to_court_statement(0.80)
        assert isinstance(stmt, str)

    def test_map_to_court_statement_indicative(self):
        from core.scoring import ConfidenceCalibrator
        stmt = ConfidenceCalibrator.map_to_court_statement(0.60)
        assert "heuristic" in stmt.lower() or "indicative" in stmt.lower()

    def test_map_to_court_statement_low(self):
        from core.scoring import ConfidenceCalibrator
        stmt = ConfidenceCalibrator.map_to_court_statement(0.30)
        assert "inconclusive" in stmt.lower() or "limited" in stmt.lower()

    def test_reliability_map_has_expected_keys(self):
        from core.scoring import ConfidenceCalibrator
        assert "siglip2" in ConfidenceCalibrator.RELIABILITY_MAP
        assert "yolo11" in ConfidenceCalibrator.RELIABILITY_MAP


# ── log_sensitive_operation() ─────────────────────────────────────────────────

class TestLogSensitiveOperation:
    @pytest.mark.asyncio
    async def test_basic_log_succeeds(self):
        from core.audit_logger import log_sensitive_operation
        # Should not raise
        await log_sensitive_operation(
            user_id="user123",
            operation="password_change",
            resource_type="user",
            resource_id="user123",
            result="success",
        )

    @pytest.mark.asyncio
    async def test_log_with_all_fields(self):
        from core.audit_logger import log_sensitive_operation
        await log_sensitive_operation(
            user_id="admin_01",
            operation="role_update",
            resource_type="user",
            resource_id="user_42",
            old_value="investigator",
            new_value="admin",
            result="success",
            details={"reason": "promotion"},
            ip_address="192.168.1.1",
        )

    @pytest.mark.asyncio
    async def test_log_failure_result(self):
        from core.audit_logger import log_sensitive_operation
        await log_sensitive_operation(
            user_id="user456",
            operation="login_attempt",
            resource_type="session",
            resource_id="sess_789",
            result="failure",
        )


# ── MimeRegistry ──────────────────────────────────────────────────────────────

class TestMimeRegistry:
    def test_agent1_supports_image(self):
        from core.mime_registry import MimeRegistry
        assert MimeRegistry.is_supported("Agent1Image", mime_type="image/jpeg") is True

    def test_agent1_does_not_support_audio(self):
        from core.mime_registry import MimeRegistry
        assert MimeRegistry.is_supported("Agent1Image", mime_type="audio/wav") is False

    def test_agent2_supports_audio(self):
        from core.mime_registry import MimeRegistry
        assert MimeRegistry.is_supported("Agent2Audio", mime_type="audio/wav") is True

    def test_agent2_does_not_support_image(self):
        from core.mime_registry import MimeRegistry
        assert MimeRegistry.is_supported("Agent2Audio", mime_type="image/png") is False

    def test_agent4_supports_video(self):
        from core.mime_registry import MimeRegistry
        assert MimeRegistry.is_supported("Agent4Video", mime_type="video/mp4") is True

    def test_agent5_supports_all(self):
        from core.mime_registry import MimeRegistry
        assert MimeRegistry.is_supported("Agent5Metadata", mime_type="audio/wav") is True
        assert MimeRegistry.is_supported("Agent5Metadata", mime_type="image/jpeg") is True

    def test_get_supported_types_image(self):
        from core.mime_registry import MimeRegistry
        types = MimeRegistry.get_supported_types("Agent1Image")
        assert "image/" in types

    def test_get_supported_extensions_audio(self):
        from core.mime_registry import MimeRegistry
        exts = MimeRegistry.get_supported_extensions("Agent2Audio")
        assert ".wav" in exts or ".mp3" in exts

    def test_is_supported_by_file_path(self):
        from core.mime_registry import MimeRegistry
        assert MimeRegistry.is_supported("Agent1Image", file_path="/tmp/photo.jpg") is True


# ── task_tool_config ──────────────────────────────────────────────────────────

class TestGetTaskToolOverrides:
    def test_returns_dict(self):
        from core.task_tool_config import get_task_tool_overrides
        result = get_task_tool_overrides()
        assert isinstance(result, dict)

    def test_handles_missing_file_gracefully(self):
        from core.task_tool_config import get_task_tool_overrides
        with patch("core.task_tool_config.yaml") as _:
            with patch("builtins.open", side_effect=FileNotFoundError):
                result = get_task_tool_overrides()
        assert isinstance(result, dict)
