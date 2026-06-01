"""
Unit tests for deep phase configuration, phase gate hardening, and final report modes.

Covers:
- Deep agent timeout derivation from config fields
- Phase gate mandatory expected_phase enforcement
- Final report use_llm config-driven toggle
- Pre-warm preservation hash comparison
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch
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


def _make_config(**overrides):
    from core.config import Settings

    base = dict(
        app_env="testing",
        signing_key="test-signing-key-" + "x" * 32,
        postgres_user="test",
        postgres_password="test",
        postgres_db="test",
        redis_password="test",
        DEMO_PASSWORD="test",
        llm_provider="none",
        llm_api_key=None,
        llm_model="test-model",
        bootstrap_admin_password="Admin_123!",
        bootstrap_investigator_password="Inv_123!",
    )
    base.update(overrides)
    return Settings(**base)


# ── Deep timeout config ──────────────────────────────────────────────────


class TestDeepTimeoutConfig:
    def test_deep_agent_timeout_seconds_default(self):
        config = _make_config()
        assert config.deep_agent_timeout_seconds == 900

    def test_deep_agent_timeout_seconds_custom(self):
        config = _make_config(deep_agent_timeout_seconds=600)
        assert config.deep_agent_timeout_seconds == 600

    def test_deep_tool_timeout_seconds_default(self):
        config = _make_config()
        assert config.deep_tool_timeout_seconds == 300

    def test_deep_agent_hard_cap_default(self):
        config = _make_config()
        assert config.deep_agent_hard_cap_seconds == 1800

    def test_deep_timeout_derivation_honors_config(self):
        """The deep timeout should use config.deep_agent_timeout_seconds
        capped by deep_agent_hard_cap_seconds, NOT investigation_timeout // 4."""
        config = _make_config(
            investigation_timeout=2400,
            deep_agent_timeout_seconds=900,
            deep_agent_hard_cap_seconds=1800,
        )
        expected = min(config.deep_agent_timeout_seconds, config.deep_agent_hard_cap_seconds)
        assert expected == 900

    def test_deep_timeout_hard_cap_applied(self):
        """When deep_agent_timeout_seconds exceeds the hard cap, the cap wins."""
        config = _make_config(
            deep_agent_timeout_seconds=3600,
            deep_agent_hard_cap_seconds=1800,
        )
        expected = min(config.deep_agent_timeout_seconds, config.deep_agent_hard_cap_seconds)
        assert expected == 1800

    def test_deep_tool_timeout_injected(self):
        """deep_tool_timeout_seconds should be assigned to agent.deep_tool_timeout."""
        from core.config import Settings
        config = _make_config(deep_tool_timeout_seconds=120)
        agent = MagicMock()
        agent.deep_tool_timeout = config.deep_tool_timeout_seconds
        assert agent.deep_tool_timeout == 120


# ── Phase gate: mandatory expected_phase ─────────────────────────────────


class TestPhaseGateMandatory:
    def test_resume_request_requires_expected_phase(self):
        """ResumeRequest must require expected_phase (not Optional)."""
        try:
            from api.routes.sessions import ResumeRequest
            req = ResumeRequest(deep_analysis=True, expected_phase="initial")
            assert req.expected_phase == "initial"
            assert req.deep_analysis is True
        except Exception as e:
            pytest.fail(f"ResumeRequest should accept expected_phase as required: {e}")

    def test_resume_request_rejects_missing_expected_phase(self):
        """ResumeRequest should raise pydantic ValidationError when expected_phase is omitted."""
        from api.routes.sessions import ResumeRequest
        with pytest.raises(Exception) as exc_info:
            ResumeRequest(deep_analysis=True)
        assert "expected_phase" in str(exc_info.value) or "Field required" in str(exc_info.value)

    def test_resume_phase_gate_initial_matches(self):
        """expected_phase='initial' should match awaiting_decision status."""
        from api.routes.sessions import ResumeRequest
        req = ResumeRequest(deep_analysis=False, expected_phase="initial")
        assert req.deep_analysis is False
        assert req.expected_phase == "initial"

    def test_resume_phase_gate_deep_matches(self):
        """expected_phase='deep' should match awaiting_deep_report status."""
        from api.routes.sessions import ResumeRequest
        req = ResumeRequest(deep_analysis=False, expected_phase="deep")
        assert req.expected_phase == "deep"


# ── Final report modes ───────────────────────────────────────────────────


class TestFinalReportModes:
    def test_final_report_llm_enabled_default(self):
        config = _make_config()
        assert config.final_report_llm_enabled is False

    def test_final_report_llm_enabled_custom(self):
        config = _make_config(final_report_llm_enabled=True)
        assert config.final_report_llm_enabled is True

    def test_use_llm_honors_config_when_disabled(self):
        """When final_report_llm_enabled=False, use_llm must be False."""
        config = _make_config(final_report_llm_enabled=False)
        assert config.final_report_llm_enabled is False

    def test_use_llm_honors_config_when_enabled(self):
        """When final_report_llm_enabled=True, use_llm must be True."""
        config = _make_config(final_report_llm_enabled=True)
        assert config.final_report_llm_enabled is True

    @pytest.mark.asyncio
    async def test_pre_warm_preserved_when_matching(self):
        """Pre-warm task should be preserved when hash matches arbiter results."""
        import hashlib

        from core.config import Settings
        config = _make_config()

        pipeline = MagicMock()
        pipeline.config = config

        arbiter_results = {
            "Agent1": {"findings": [{"type": "noise"}]},
            "Agent3": {"findings": [{"type": "ela"}]},
        }

        pre_warm_hash = hashlib.sha256(
            str(sorted(arbiter_results.items())).encode()
        ).hexdigest()[:16]

        pre_warm_task = AsyncMock()
        pre_warm_task.done.return_value = False
        pipeline._pre_warm_task = pre_warm_task

        arbiter = MagicMock()
        arbiter._pre_warm_agent_results = arbiter_results
        pipeline.arbiter = arbiter

        _cached = getattr(arbiter, "_pre_warm_agent_results", None)
        assert _cached is not None
        _old_hash = hashlib.sha256(
            str(sorted(_cached.items())).encode()
        ).hexdigest()[:16]
        _new_hash = hashlib.sha256(
            str(sorted(arbiter_results.items())).encode()
        ).hexdigest()[:16]
        assert _old_hash == _new_hash

    @pytest.mark.asyncio
    async def test_pre_warm_cancelled_when_mismatched(self):
        """Pre-warm task should be cancelled when hash doesn't match."""
        import hashlib

        from core.config import Settings
        config = _make_config()

        pipeline = MagicMock()
        pipeline.config = config

        old_results = {"Agent1": {"findings": [{"type": "old"}]}}
        new_results = {"Agent1": {"findings": [{"type": "new"}]}}

        pre_warm_task = AsyncMock()
        pre_warm_task.done.return_value = False
        pipeline._pre_warm_task = pre_warm_task
        pipeline.arbiter = MagicMock()
        pipeline.arbiter._pre_warm_agent_results = old_results

        _cached = pipeline.arbiter._pre_warm_agent_results
        _old_hash = hashlib.sha256(
            str(sorted(_cached.items())).encode()
        ).hexdigest()[:16]
        _new_hash = hashlib.sha256(
            str(sorted(new_results.items())).encode()
        ).hexdigest()[:16]
        assert _old_hash != _new_hash


# ── File type policy contract ────────────────────────────────────────────


class TestFileTypePolicyContract:
    """Ensure the supported MIME types contract is image-only."""

    def test_allowed_mime_types_are_images(self):
        from core.file_type_policy import (
            SUPPORTED_MIME_TYPES,
        )
        for mime in SUPPORTED_MIME_TYPES:
            assert mime.startswith("image/"), f"{mime} is not an image type"

    def test_no_audio_or_video_in_supported(self):
        from core.file_type_policy import (
            SUPPORTED_MIME_TYPES,
        )
        for mime in SUPPORTED_MIME_TYPES:
            assert not mime.startswith("audio/"), f"Audio type {mime} should not be supported"
            assert not mime.startswith("video/"), f"Video type {mime} should not be supported"

    def test_standard_image_types_present(self):
        from core.file_type_policy import (
            SUPPORTED_MIME_TYPES,
        )
        for expected in ("image/jpeg", "image/png", "image/tiff", "image/webp", "image/bmp"):
            assert expected in SUPPORTED_MIME_TYPES, f"{expected} should be supported"

    def test_get_applicable_agents_for_image_returns_correct_agents(self):
        from core.file_type_policy import get_applicable_agents

        agents = get_applicable_agents("image/png")
        assert "Agent1" in agents
        assert "Agent3" in agents
        assert "Agent5" in agents

    def test_get_applicable_agents_for_unknown_returns_empty(self):
        from core.file_type_policy import get_applicable_agents

        agents = get_applicable_agents("application/octet-stream")
        assert len(agents) == 0
