import pytest

from core.config import get_settings, validate_production_settings


def _clear_settings_cache():
    """Clear the lru_cache on get_settings so env-var changes take effect."""
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Always clear the settings cache before and after each test."""
    _clear_settings_cache()
    yield
    _clear_settings_cache()


def _strong_env(monkeypatch, **overrides):
    """Set a baseline of valid production env vars, then apply overrides."""
    base = {
        "APP_ENV": "production",
        "POSTGRES_PASSWORD": "Str0ngP@ssw0rd123!",
        "REDIS_PASSWORD": "Str0ngP@ssw0rd123!",
        "DEMO_PASSWORD": "Str0ngP@ssw0rd123!",
        "SIGNING_KEY": "VeryStr0ngKeyWithH!ghEntr0py_1234567890",
        "JWT_SECRET_KEY": "VeryStr0ngKeyWithH!ghEntr0py_1234567890",
        "GEMINI_API_KEY": "AIzaSyFakeKey1234567890",
        "QDRANT_API_KEY": "qdrant_test_key_1234567890",
        "BOOTSTRAP_ADMIN_PASSWORD": "Str0ngAdm!nPwd_XYZ789",
        "BOOTSTRAP_INVESTIGATOR_PASSWORD": "Str0ngInv!Pwd_XYZ789",
        "POSTGRES_USER": "test",
        "POSTGRES_DB": "test",
        "LLM_PROVIDER": "none",
        "LLM_API_KEY": "test-key",
        "LLM_MODEL": "test-model",
    }
    base.update(overrides)
    for k, v in base.items():
        monkeypatch.setenv(k, v)


def test_validate_production_settings_weak_passwords(monkeypatch):
    """Weak bootstrap passwords should fail validation."""
    _strong_env(monkeypatch, BOOTSTRAP_ADMIN_PASSWORD="admin123")
    with pytest.raises(ValueError, match="strong, unique password"):
        validate_production_settings()


def test_validate_production_settings_weak_keys(monkeypatch):
    """Short/low-entropy SIGNING_KEY should fail validation."""
    _strong_env(monkeypatch, SIGNING_KEY="weakkey")
    with pytest.raises(ValueError, match="SIGNING_KEY"):
        validate_production_settings()


def test_validate_production_settings_placeholder_gemini_key(monkeypatch):
    """Placeholder GEMINI_API_KEY should fail validation."""
    _strong_env(monkeypatch, GEMINI_API_KEY="your_gemini_key_here")
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        validate_production_settings()


def test_validate_production_settings_valid(monkeypatch):
    """All strong values — should not raise."""
    _strong_env(monkeypatch)
    validate_production_settings()


def test_validate_skipped_outside_production(monkeypatch):
    """validate_production_settings is a no-op in non-production environments."""
    _strong_env(monkeypatch, APP_ENV="testing", SIGNING_KEY="weak")
    validate_production_settings()  # must not raise


def test_validate_weak_jwt_secret(monkeypatch):
    """Short JWT_SECRET_KEY should fail validation."""
    _strong_env(monkeypatch, JWT_SECRET_KEY="tooshort")
    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        validate_production_settings()
