"""
Unit tests for core/config.py
"""

import pytest
from pydantic import ValidationError


class TestSettings:
    """Test cases for Settings configuration."""

    def test_default_values(self):
        """Test that default values are set correctly."""
        from core.config import Settings, get_settings
        
        settings = Settings(
            app_env="development",
            debug=True,
            signing_key="test-key-12345678901234567890",
            groq_api_key="test-groq-key",
        )
        
        assert settings.app_env == "development"
        assert settings.debug is True
        assert settings.signing_key == "test-key-12345678901234567890"

    def test_signing_key_validation(self):
        """Test that signing key is validated."""
        from core.config import Settings
        
        # Valid signing key (64 hex chars = 32 bytes)
        settings = Settings(
            app_env="development",
            debug=True,
            signing_key="a" * 64,
            groq_api_key="test-key",
        )
        assert len(settings.signing_key) == 64
        
        # Test dev key works
        dev_settings = Settings(
            app_env="development",
            debug=True,
            signing_key="dev-" + "b" * 60,
            groq_api_key="test-key",
        )
        assert dev_settings.signing_key.startswith("dev-")

    def test_redis_url_default(self):
        """Test Redis URL default value."""
        from core.config import Settings
        
        settings = Settings(
            app_env="development",
            debug=True,
            signing_key="test-key" + "0" * 56,
            groq_api_key="test-key",
        )
        
        assert settings.redis_url == "redis://localhost:6379/0"

    def test_postgres_url_default(self):
        """Test Postgres URL default value."""
        from core.config import Settings
        
        settings = Settings(
            app_env="development",
            debug=True,
            signing_key="test-key" + "0" * 56,
            groq_api_key="test-key",
        )
        
        assert "localhost" in settings.database_url
        assert "5432" in settings.database_url

    def test_cors_origins_parsing(self):
        """Test CORS origins are parsed correctly."""
        import json
        from core.config import Settings
        
        origins = ["http://localhost:3000", "http://localhost:8000"]
        settings = Settings(
            app_env="development",
            debug=True,
            signing_key="test-key" + "0" * 56,
            groq_api_key="test-key",
            cors_allowed_origins=json.dumps(origins),
        )
        
        assert settings.cors_allowed_origins == origins

    def test_production_settings(self):
        """Test production-specific settings."""
        from core.config import Settings
        
        settings = Settings(
            app_env="production",
            debug=False,
            signing_key="test-key" + "0" * 56,
            groq_api_key="test-key",
        )
        
        assert settings.app_env == "production"
        assert settings.debug is False
        assert settings.docs_url is None
