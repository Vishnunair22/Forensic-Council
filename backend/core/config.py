"""
Configuration Management Module
===============================

Pydantic Settings-based configuration loading from environment variables.
All configuration is centralized and validated at startup.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    All settings can be overridden via .env file or environment variables.
    Environment variables take precedence over .env file values.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # Application Settings
    app_name: str = Field(default="forensic_council", description="Application name")
    app_env: str = Field(default="development", description="Environment: development, staging, production")
    debug: bool = Field(default=False, description="Debug mode flag")
    log_level: str = Field(default="INFO", description="Logging level")
    
    @field_validator('debug', mode='before')
    @classmethod
    def parse_debug(cls, v):
        """Handle debug field from string or boolean."""
        if isinstance(v, str):
            # Handle common string representations
            lower = v.lower().strip()
            if lower in ('true', '1', 'yes', 'on'):
                return True
            elif lower in ('false', '0', 'no', 'off', 'release'):
                return False
        return v
    
    # Redis Configuration
    redis_host: str = Field(default="localhost", description="Redis server host")
    redis_port: int = Field(default=6379, description="Redis server port")
    redis_db: int = Field(default=0, description="Redis database number")
    redis_password: Optional[str] = Field(default=None, description="Redis password")
    
    @property
    def redis_url(self) -> str:
        """Construct Redis URL from components."""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    # Qdrant Configuration
    qdrant_host: str = Field(default="localhost", description="Qdrant server host")
    qdrant_port: int = Field(default=6333, description="Qdrant REST API port")
    qdrant_grpc_port: int = Field(default=6334, description="Qdrant gRPC port")
    qdrant_api_key: Optional[str] = Field(default=None, description="Qdrant API key")
    
    # PostgreSQL Configuration
    postgres_host: str = Field(default="localhost", description="PostgreSQL server host")
    postgres_port: int = Field(default=5432, description="PostgreSQL server port")
    postgres_user: str = Field(default="forensic_user", description="PostgreSQL username")
    postgres_password: str = Field(default="forensic_pass", description="PostgreSQL password")
    postgres_db: str = Field(default="forensic_council", description="PostgreSQL database name")
    
    @property
    def database_url(self) -> str:
        """Construct PostgreSQL connection URL from components."""
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    @property
    def sqlalchemy_async_database_url(self) -> str:
        """
        Construct async PostgreSQL connection URL for SQLAlchemy.
        Note: Requires postgresql+asyncpg:// prefix.
        """
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    # Storage Configuration
    evidence_storage_path: str = Field(default="./storage/evidence", description="Path for evidence storage")
    calibration_models_path: str = Field(default="./storage/calibration_models", description="Path for calibration models")
    
    # Security Configuration
    signing_key: str = Field(default="change-me-in-production", description="Key for signing audit entries")
    cors_allowed_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"],
        description="Allowed CORS origins (comma-separated in env)",
    )
    
    # Agent Configuration
    default_iteration_ceiling: int = Field(default=20, description="Default iteration ceiling for agent loops")
    hitl_enabled: bool = Field(default=True, description="Enable Human-in-the-Loop checkpoints")
    investigation_timeout: int = Field(default=300, description="Max seconds for a single investigation")
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is one of the allowed values."""
        allowed = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"Log level must be one of {allowed}, got {v}")
        return v_upper
    
    @field_validator("app_env")
    @classmethod
    def validate_app_env(cls, v: str) -> str:
        """Validate application environment."""
        allowed = ["development", "staging", "production", "testing"]
        v_lower = v.lower()
        if v_lower not in allowed:
            raise ValueError(f"Environment must be one of {allowed}, got {v}")
        return v_lower
    
    @field_validator("signing_key")
    @classmethod
    def validate_signing_key(cls, v: str, info) -> str:
        """Block insecure default signing keys in production."""
        data = info.data if hasattr(info, 'data') else {}
        env = data.get("app_env", "development")
        if env == "production" and ("change" in v.lower() or "default" in v.lower() or "dev" in v.lower()):
            raise ValueError(
                "SIGNING_KEY must be changed from the default for production! "
                "Set a strong, unique key via the SIGNING_KEY environment variable."
            )
        return v


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached application settings.
    
    Uses lru_cache to ensure settings are only loaded once.
    Call settings.cache_clear() to reload settings (useful for testing).
    """
    return Settings()


# Convenience alias
settings = get_settings()
