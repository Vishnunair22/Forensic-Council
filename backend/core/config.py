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


# Default credentials that must be changed in production
INSECURE_DEFAULTS = {
    "forensic_pass",
    "postgres",
    "password",
    "admin",
    "123456",
    "change-me",
    "changeme",
}


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
    
    @field_validator("app_env")
    @classmethod
    def validate_app_env(cls, v: str) -> str:
        """Validate application environment."""
        allowed = ["development", "staging", "production", "testing"]
        v_lower = v.lower()
        if v_lower not in allowed:
            raise ValueError(f"Environment must be one of {allowed}, got {v}")
        return v_lower
        
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
    postgres_min_pool_size: int = Field(default=5, description="Min DB connection pool size")
    postgres_max_pool_size: int = Field(default=20, description="Max DB connection pool size")
    
    @field_validator("postgres_user")
    @classmethod
    def validate_postgres_user(cls, v: str, info) -> str:
        """Block insecure default usernames in production."""
        data = info.data if hasattr(info, 'data') else {}
        env = data.get("app_env", "development")
        if env == "production" and v.lower() in INSECURE_DEFAULTS:
            raise ValueError(
                f"POSTGRES_USER '{v}' is insecure for production! "
                "Set a strong, unique username via the POSTGRES_USER environment variable."
            )
        return v
    
    @field_validator("postgres_password")
    @classmethod
    def validate_postgres_password(cls, v: str, info) -> str:
        """Block insecure default passwords in production."""
        data = info.data if hasattr(info, 'data') else {}
        env = data.get("app_env", "development")
        if env == "production":
            if v.lower() in INSECURE_DEFAULTS:
                raise ValueError(
                    f"POSTGRES_PASSWORD '{v}' is insecure for production! "
                    "Set a strong, unique password via the POSTGRES_PASSWORD environment variable."
                )
            if len(v) < 16:
                raise ValueError(
                    "POSTGRES_PASSWORD must be at least 16 characters in production!"
                )
        return v
    
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
    jwt_secret_key: Optional[str] = Field(default=None, description="Secret key for JWT token signing. If not set, uses SIGNING_KEY")
    jwt_access_token_expire_minutes: int = Field(default=60, description="JWT access token expiration in minutes (default: 1 hour)")
    jwt_refresh_token_expire_days: int = Field(default=7, description="JWT refresh token expiration in days")
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    cors_allowed_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"],
        description="Allowed CORS origins (comma-separated in env)",
    )
    
    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_cors(cls, v):
        import json
        if isinstance(v, str):
            if v.startswith("["):
                try:
                    return json.loads(v)
                except json.JSONDecodeError:
                    raise ValueError(f"Invalid CORS_ALLOWED_ORIGINS JSON: {v}")
            return [i.strip() for i in v.split(",") if i.strip()]
        return v
    
    @property
    def effective_jwt_secret(self) -> str:
        """Get the effective JWT secret key."""
        return self.jwt_secret_key or self.signing_key
    
    
    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret_key(cls, v: Optional[str], info) -> Optional[str]:
        """Block insecure default JWT secret keys in production."""
        if v is None:
            return v
        data = info.data if hasattr(info, 'data') else {}
        env = data.get("app_env", "development")
        if env == "production":
            if any(word in v.lower() for word in ("change", "default", "dev")):
                raise ValueError(
                    "JWT_SECRET_KEY must be changed from the default for production! "
                    "Set a strong, unique key via the JWT_SECRET_KEY environment variable."
                )
            if len(v) < 32:
                raise ValueError(
                    "JWT_SECRET_KEY must be at least 32 characters in production!"
                )
            
            # Entropy check - must have diversity
            has_upper = any(c.isupper() for c in v)
            has_lower = any(c.islower() for c in v)
            has_digit = any(c.isdigit() for c in v)
            has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in v)
            
            entropy_score = sum([has_upper, has_lower, has_digit, has_special])
            if entropy_score < 3:
                raise ValueError(
                    "JWT_SECRET_KEY must contain at least 3 of: uppercase, lowercase, digits, special chars"
                )
        return v
    
    # Agent Configuration
    default_iteration_ceiling: int = Field(default=20, description="Default iteration ceiling for agent loops")
    hitl_enabled: bool = Field(default=True, description="Enable Human-in-the-Loop checkpoints")
    investigation_timeout: int = Field(default=300, description="Max seconds for a single investigation")
    investigation_max_retries: int = Field(default=3, description="Max retry attempts for failed investigations")
    investigation_retry_delay: float = Field(default=5.0, description="Base delay between investigation retries (seconds)")
    
    # LLM Configuration
    llm_provider: str = Field(default="openai", description="LLM provider: openai, anthropic, or none")
    llm_api_key: Optional[str] = Field(default=None, description="API key for LLM provider")
    llm_model: str = Field(default="gpt-4", description="LLM model to use for reasoning")
    llm_temperature: float = Field(default=0.1, description="Temperature for LLM sampling (0.0-1.0)")
    llm_max_tokens: int = Field(default=2048, description="Maximum tokens for LLM responses")
    llm_timeout: float = Field(default=60.0, description="Timeout for LLM API calls in seconds")
    llm_enable_react_reasoning: bool = Field(default=True, description="Enable LLM reasoning in ReAct loop")

    # HuggingFace Token (for pyannote.audio speaker diarization and other HF models)
    hf_token: Optional[str] = Field(default=None, description="HuggingFace API token for model downloads")
    
    @field_validator("hf_token")
    @classmethod
    def validate_hf_token(cls, v: Optional[str], info) -> Optional[str]:
        """Warn if HuggingFace token is missing when needed."""
        if v is None:
            import warnings
            warnings.warn(
                "HF_TOKEN not set. Agent 2 speaker diarization will fail gracefully. "
                "Get a free token at https://hf.co/settings/tokens",
                UserWarning
            )
        return v
    
    @field_validator("llm_api_key")
    @classmethod
    def validate_llm_api_key(cls, v: Optional[str], info) -> Optional[str]:
        """Validate LLM API key when LLM provider is enabled."""
        data = info.data if hasattr(info, 'data') else {}
        provider = data.get("llm_provider", "none")
        
        if provider != "none" and not v:
            raise ValueError(
                f"LLM_API_KEY is required when LLM_PROVIDER='{provider}'. "
                f"Set LLM_PROVIDER='none' or provide LLM_API_KEY."
            )
        
        if v and provider != "none" and len(v) < 20:
            raise ValueError(f"LLM_API_KEY appears invalid (too short)")
        
        return v
    
    # Retry Configuration
    database_retry_max: int = Field(default=5, description="Max database connection retries")
    database_retry_delay: float = Field(default=1.0, description="Base database retry delay (seconds)")
    external_api_retry_max: int = Field(default=3, description="Max external API retries")
    external_api_retry_delay: float = Field(default=1.0, description="Base external API retry delay (seconds)")
    
    # Session Persistence
    session_ttl_hours: int = Field(default=24, description="Session state TTL in hours")
    enable_session_persistence: bool = Field(default=True, description="Enable PostgreSQL session persistence")
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is one of the allowed values."""
        allowed = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"Log level must be one of {allowed}, got {v}")
        return v_upper
    
    
    @field_validator("signing_key")
    @classmethod
    def validate_signing_key(cls, v: str, info) -> str:
        """Block empty or insecure signing keys in all environments."""
        if not v or not v.strip():
            raise ValueError(
                "SIGNING_KEY cannot be empty. Generate one with: "
                "python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        data = info.data if hasattr(info, "data") else {}
        env = data.get("app_env", "development")
        if env == "production":
            if any(word in v.lower() for word in ("change", "default", "dev", "example")):
                raise ValueError(
                    "SIGNING_KEY must be changed from the default for production! "
                    "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
                )
            if len(v) < 32:
                raise ValueError(
                    "SIGNING_KEY must be at least 32 characters in production!"
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
