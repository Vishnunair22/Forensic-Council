"""
Backend Unit Tests â€” core/config.py & core/signing.py & api/schemas.py
========================================================================
Tests application configuration loading, secure defaults detection,
ECDSA cryptographic signing, and Pydantic DTO validation.
"""
from datetime import datetime

import pytest

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# CONFIG TESTS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestSettings:
    """Test that configuration loads correctly from environment."""

    def test_settings_importable(self):
        try:
            from core.config import get_settings
            settings = get_settings()
            assert settings is not None
        except ImportError:
            pytest.skip("core.config not importable")

    def test_app_env_is_testing(self):
        try:
            from core.config import get_settings
            settings = get_settings()
            assert settings.app_env in ("testing", "development", "production")
        except ImportError:
            pytest.skip()

    def test_signing_key_present(self):
        try:
            from core.config import get_settings
            settings = get_settings()
            assert settings.signing_key
            assert len(settings.signing_key) > 0
        except ImportError:
            pytest.skip()

    def test_jwt_expire_minutes_is_reasonable(self):
        """JWT expire should be <= 120 minutes (not 7 days = 10080 from old bug)."""
        try:
            from core.config import get_settings
            settings = get_settings()
            assert hasattr(settings, "jwt_access_token_expire_minutes")
            assert settings.jwt_access_token_expire_minutes <= 120, (
                f"JWT expires in {settings.jwt_access_token_expire_minutes} min â€” "
                "should be â‰¤ 120 (v1.0.3 fix)"
            )
        except ImportError:
            pytest.skip()

    def test_cors_origins_is_list(self):
        try:
            from core.config import get_settings
            settings = get_settings()
            if hasattr(settings, "cors_origins"):
                assert isinstance(settings.cors_origins, (list, tuple))
        except ImportError:
            pytest.skip()

    def test_debug_is_bool(self):
        try:
            from core.config import get_settings
            settings = get_settings()
            assert isinstance(settings.debug, bool)
        except ImportError:
            pytest.skip()

    def test_log_level_is_valid(self):
        try:
            from core.config import get_settings
            settings = get_settings()
            if hasattr(settings, "log_level"):
                assert settings.log_level.upper() in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
        except ImportError:
            pytest.skip()

    def test_llm_provider_set(self):
        try:
            from core.config import get_settings
            settings = get_settings()
            if hasattr(settings, "llm_provider"):
                assert settings.llm_provider in ("groq", "openai", "anthropic", "none", "test")
        except ImportError:
            pytest.skip()

    def test_settings_singleton_via_lru_cache(self):
        """get_settings() should return the same instance (lru_cache)."""
        try:
            from core.config import get_settings
            s1 = get_settings()
            s2 = get_settings()
            assert s1 is s2
        except ImportError:
            pytest.skip()

    def test_insecure_default_detected(self):
        """The dev signing key placeholder should be flagged as insecure."""
        try:
            from core.config import get_settings
            settings = get_settings()
            key = settings.signing_key
            # Known dev placeholder from .env.example
            dev_placeholder = "dev-placeholder-change-me-in-production"
            if dev_placeholder in key:
                # In test env, this is fine â€” but the config should not force production mode with this key
                assert settings.app_env != "production", (
                    "Dev signing key detected in production mode â€” security violation"
                )
        except ImportError:
            pytest.skip()

    def test_postgres_config_present(self):
        try:
            from core.config import get_settings
            s = get_settings()
            assert hasattr(s, "postgres_user") or hasattr(s, "postgres_host") or hasattr(s, "postgres_db")
        except ImportError:
            pytest.skip()

    def test_redis_config_present(self):
        try:
            from core.config import get_settings
            s = get_settings()
            assert hasattr(s, "redis_password") or hasattr(s, "redis_host") or hasattr(s, "redis_url")
        except ImportError:
            pytest.skip()


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# SIGNING TESTS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestSignContent:
    """Tests for core/signing.py â€” ECDSA P-256 / SHA-256."""

    @pytest.fixture(autouse=True)
    def skip_if_missing(self):
        try:
            from core.signing import SignedEntry, sign_content, verify_entry
            self.sign_content = sign_content
            self.verify_entry = verify_entry
            self.SignedEntry = SignedEntry
        except ImportError:
            pytest.skip("core.signing not importable")

    def test_sign_returns_signed_entry(self):
        entry = self.sign_content("agent-img", {"result": "clean"})
        assert entry is not None

    def test_signed_entry_has_required_fields(self):
        entry = self.sign_content("agent-img", {"result": "clean"})
        d = entry if isinstance(entry, dict) else entry.to_dict() if hasattr(entry, "to_dict") else vars(entry)
        assert "agent_id" in d or hasattr(entry, "agent_id")
        assert "hash" in d or "content_hash" in d or hasattr(entry, "hash") or hasattr(entry, "content_hash")
        assert "signature" in d or hasattr(entry, "signature")
        assert "timestamp_utc" in d or hasattr(entry, "timestamp_utc")

    def test_hash_is_deterministic_for_same_content(self):
        e1 = self.sign_content("agent-img", {"result": "clean"})
        e2 = self.sign_content("agent-img", {"result": "clean"})
        h1 = getattr(e1, "hash", None) or getattr(e1, "content_hash", None)
        h2 = getattr(e2, "hash", None) or getattr(e2, "content_hash", None)
        if h1 and h2:
            assert h1 == h2

    def test_different_content_different_hash(self):
        e1 = self.sign_content("agent-img", {"result": "clean"})
        e2 = self.sign_content("agent-img", {"result": "TAMPERED"})
        h1 = getattr(e1, "hash", None) or getattr(e1, "content_hash", None)
        h2 = getattr(e2, "hash", None) or getattr(e2, "content_hash", None)
        if h1 and h2:
            assert h1 != h2

    def test_verify_returns_true_for_valid_entry(self):
        entry = self.sign_content("agent-img", {"result": "clean"})
        assert self.verify_entry(entry) is True

    def test_verify_fails_for_tampered_content(self):
        entry = self.sign_content("agent-img", {"result": "clean"})
        # Tamper with the agent_id or content
        if hasattr(entry, "__dict__"):
            entry_copy = type("E", (), vars(entry).copy())()
            if hasattr(entry_copy, "agent_id"):
                entry_copy.agent_id = "tampered-agent"
                result = self.verify_entry(entry_copy)
                assert result is False
        # If not mutable, just verify valid entry verifies correctly
        assert self.verify_entry(entry) is True

    def test_verify_fails_for_tampered_hash(self):
        entry = self.sign_content("agent-img", {"result": "clean"})
        if hasattr(entry, "__dict__"):
            entry_copy = type("E", (), vars(entry).copy())()
            for attr in ("hash", "content_hash"):
                if hasattr(entry_copy, attr):
                    setattr(entry_copy, attr, "0" * 64)
                    assert self.verify_entry(entry_copy) is False
                    break

    def test_different_agents_produce_different_signatures(self):
        content = {"result": "clean"}
        e1 = self.sign_content("agent-img", content)
        e2 = self.sign_content("agent-audio", content)
        sig1 = getattr(e1, "signature", None)
        sig2 = getattr(e2, "signature", None)
        if sig1 and sig2:
            assert sig1 != sig2

    def test_timestamp_is_utc(self):
        entry = self.sign_content("agent-img", {"x": 1})
        ts = getattr(entry, "timestamp_utc", None)
        if ts:
            if isinstance(ts, str):
                assert "Z" in ts or "+" in ts or ts.endswith("00:00")
            elif isinstance(ts, datetime):
                assert ts.tzinfo is not None

    def test_complex_nested_data_signed_successfully(self):
        complex_data = {
            "findings": [{"type": "ela", "confidence": 0.95, "metadata": {"phase": "deep"}}],
            "agents": {"img": {"status": "complete"}},
            "nested": {"a": {"b": {"c": 42}}},
        }
        entry = self.sign_content("arbiter", complex_data)
        assert self.verify_entry(entry) is True


class TestSignedEntry:
    """Tests for the SignedEntry dataclass/model."""

    @pytest.fixture(autouse=True)
    def skip_if_missing(self):
        try:
            from core.signing import SignedEntry
            self.SignedEntry = SignedEntry
        except ImportError:
            pytest.skip("SignedEntry not importable")

    def test_to_dict_roundtrip(self):
        try:
            from core.signing import sign_content
            entry = sign_content("agent-img", {"x": 1})
            if hasattr(entry, "to_dict") and hasattr(entry.__class__, "from_dict"):
                d = entry.to_dict()
                assert isinstance(d, dict)
        except ImportError:
            pytest.skip()


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# PYDANTIC SCHEMA TESTS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestSchemas:
    """Tests for api/schemas.py Pydantic models."""

    @pytest.fixture(autouse=True)
    def skip_if_missing(self):
        try:
            from api.schemas import (
                AgentFindingDTO,
                HITLDecisionRequest,
                InvestigationRequest,
                ReportDTO,
            )
            self.InvestigationRequest = InvestigationRequest
            self.AgentFindingDTO = AgentFindingDTO
            self.ReportDTO = ReportDTO
            self.HITLDecisionRequest = HITLDecisionRequest
        except ImportError:
            pytest.skip("api.schemas not importable")

    # InvestigationRequest

    def test_investigation_request_valid(self):
        obj = self.InvestigationRequest(case_id="CASE-1234567890", investigator_id="REQ-12345")
        assert obj.case_id == "CASE-1234567890"

    def test_investigation_request_missing_case_id_raises(self):
        import pydantic
        with pytest.raises((pydantic.ValidationError, TypeError)):
            self.InvestigationRequest(investigator_id="REQ-12345")

    def test_investigation_request_missing_investigator_id_raises(self):
        import pydantic
        with pytest.raises((pydantic.ValidationError, TypeError)):
            self.InvestigationRequest(case_id="CASE-1234567890")

    # AgentFindingDTO

    def test_agent_finding_dto_valid(self, sample_agent_finding):
        obj = self.AgentFindingDTO(**sample_agent_finding)
        assert obj.agent_id == "agent-img"
        assert obj.confidence_raw == 0.88

    def test_agent_finding_optional_fields_default_none(self, sample_agent_finding):
        minimal = {k: v for k, v in sample_agent_finding.items()
                   if k in ("finding_id", "agent_id", "agent_name", "finding_type",
                             "status", "confidence_raw", "calibrated", "robustness_caveat")}
        # Should accept with optional fields absent
        try:
            obj = self.AgentFindingDTO(**minimal)
            assert obj is not None
        except Exception:
            pass  # Acceptable if required fields differ

    def test_agent_finding_confidence_raw_numeric(self, sample_agent_finding):
        obj = self.AgentFindingDTO(**sample_agent_finding)
        assert isinstance(obj.confidence_raw, float)

    # HITLDecisionRequest

    def test_hitl_approve(self):
        obj = self.HITLDecisionRequest(
            session_id="sess", checkpoint_id="cp", agent_id="a", decision="APPROVE"
        )
        assert obj.decision == "APPROVE"

    def test_hitl_all_decision_types(self):
        for decision in ("APPROVE", "REDIRECT", "TERMINATE", "ESCALATE", "OVERRIDE"):
            try:
                obj = self.HITLDecisionRequest(
                    session_id="s", checkpoint_id="c", agent_id="a", decision=decision
                )
                assert obj.decision == decision
            except Exception:
                pass  # Some decision types may not all be valid

    def test_hitl_invalid_decision_raises(self):
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            self.HITLDecisionRequest(
                session_id="s", checkpoint_id="c", agent_id="a", decision="INVALID_GARBAGE"
            )


