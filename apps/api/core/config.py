"""
Configuration Management Module
===============================

Pydantic Settings-based configuration loading from environment variables.
All configuration is centralized and validated at startup.
"""

import logging
import os
import warnings
from functools import lru_cache
from urllib.parse import quote_plus

_config_logger = logging.getLogger(__name__)

from pydantic import Field, field_validator, model_validator
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
        env_file=[".env", "../.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_ignore_empty=True,  # Treat empty strings as "not set" to allow defaults
        extra="ignore",  # Ignore unknown environment variables (allow extra vars)
    )

    # Application Settings
    app_name: str = Field(default="forensic_council", description="Application name")
    app_env: str = Field(
        default="development",
        description="Environment: development, staging, production",
    )
    offline_mode: bool = Field(
        default=False,
        description=(
            "Enable strict offline mode for ML models. "
            "When True, all ML libraries (HuggingFace, YOLO, CLIP) "
            "are forced to use local cache and will fail if models are missing, "
            "rather than attempting an internet download."
        ),
    )

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

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, v):
        """Handle debug field from string or boolean."""
        if isinstance(v, str):
            # Handle common string representations
            lower = v.lower().strip()
            if lower in ("true", "1", "yes", "on"):
                return True
            elif lower in ("false", "0", "no", "off", "release"):
                return False
        return v

    # Redis Configuration
    redis_host: str = Field(default="localhost", description="Redis server host")
    redis_port: int = Field(default=6379, description="Redis server port")
    redis_db: int = Field(default=0, description="Redis database number")
    redis_password: str | None = Field(default=None, description="Redis password")

    @property
    def redis_url(self) -> str:
        """Construct Redis URL from components."""
        if self.redis_password:
            return f"redis://:{quote_plus(self.redis_password)}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # Qdrant Configuration
    qdrant_host: str = Field(default="localhost", description="Qdrant server host")
    qdrant_port: int = Field(default=6333, description="Qdrant REST API port")
    qdrant_grpc_port: int = Field(default=6334, description="Qdrant gRPC port")
    qdrant_api_key: str | None = Field(default=None, description="Qdrant API key")

    # PostgreSQL Configuration
    postgres_host: str = Field(default="localhost", description="PostgreSQL server host")
    postgres_port: int = Field(default=5432, description="PostgreSQL server port")
    postgres_user: str = Field(default="forensic_user", description="PostgreSQL username")
    postgres_password: str = Field(
        default="dev-" + "x" * 15, description="PostgreSQL database password"
    )
    postgres_db: str = Field(default="forensic_council", description="PostgreSQL database name")
    postgres_min_pool_size: int = Field(default=2, description="Min DB connection pool size")
    postgres_max_pool_size: int = Field(default=10, description="Max DB connection pool size")

    @field_validator("postgres_user")
    @classmethod
    def validate_postgres_user(cls, v: str, info) -> str:
        """Block insecure default usernames in production."""
        data = info.data if hasattr(info, "data") else {}
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
        data = info.data if hasattr(info, "data") else {}
        env = data.get("app_env", "development")
        if env == "production":
            v_lower = v.lower()
            if v_lower in INSECURE_DEFAULTS or "replace_me" in v_lower or "replace" in v_lower:
                raise ValueError(
                    f"POSTGRES_PASSWORD '{v}' is insecure for production! "
                    "Set a strong, unique password via the POSTGRES_PASSWORD environment variable."
                )
            if len(v) < 16:
                raise ValueError("POSTGRES_PASSWORD must be at least 16 characters in production!")
        return v

    @property
    def database_url(self) -> str:
        """Construct PostgreSQL connection URL from components."""
        return f"postgresql://{quote_plus(self.postgres_user)}:{quote_plus(self.postgres_password)}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def sqlalchemy_async_database_url(self) -> str:
        """
        Construct async PostgreSQL connection URL for SQLAlchemy.
        Note: Requires postgresql+asyncpg:// prefix.
        """
        return f"postgresql+asyncpg://{quote_plus(self.postgres_user)}:{quote_plus(self.postgres_password)}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    # Storage Configuration
    evidence_storage_path: str = Field(
        default="./storage/evidence", description="Path for evidence storage"
    )
    calibration_models_path: str = Field(
        default="./storage/calibration_models",
        description="Path for calibration models",
    )
    evidence_retention_days: int = Field(
        default=30,
        description="Number of days to retain forensic evidence files before automated purging. Legal forensics typically requires 30-90 days minimum.",
    )

    # ML Cache Configuration (must match Docker volumes)
    hf_home: str = Field(
        default=os.getenv("HF_HOME", "/app/cache/huggingface"),
        description="HuggingFace model cache home",
    )
    torch_home: str = Field(
        default=os.getenv("TORCH_HOME", "/app/cache/torch"),
        description="PyTorch hub cache home",
    )
    yolo_model_dir: str = Field(
        default=os.getenv("YOLO_MODEL_DIR", "/app/cache/ultralytics"),
        description="Ultralytics/YOLO model cache",
    )
    yolo_model_name: str = Field(
        default="yolo11n.pt",
        description="YOLO model weight filename (default yolo11n.pt for speed; use yolo11m.pt for high precision)",
    )
    siglip_model_name: str = Field(
        default="ViT-B-32",
        description=(
            "OpenCLIP model name for vision-language analysis. "
            "Default ViT-B-32 (~150MB) keeps the Docker image small. "
            "Set ViT-L-14 (~1.5GB) for high-precision deployments."
        ),
    )
    aasist_model_name: str = Field(
        default="Vansh180/deepfake-audio-wav2vec2",
        description=(
            "Primary model for audio deepfake anti-spoofing detection. "
            "Vansh180/deepfake-audio-wav2vec2 (wav2vec2-based) is the default. "
            "Set clovaai/AASIST for the original research model (research-only license)."
        ),
    )
    voice_clone_model_name: str = Field(
        default="Vansh180/deepfake-audio-wav2vec2",
        description=(
            "Primary model for voice clone and AI speech synthesis detection. "
            "Default Vansh180/deepfake-audio-wav2vec2. "
            "Set clovaai/AASIST for research-grade accuracy (research-only license)."
        ),
    )
    easyocr_model_dir: str = Field(
        default=os.getenv("EASYOCR_MODEL_DIR", "/app/cache/easyocr"),
        description="EasyOCR model storage",
    )
    numba_cache_dir: str = Field(
        default=os.getenv("NUMBA_CACHE_DIR", "/app/cache/numba_cache"),
        description="Numba JIT cache directory",
    )

    # Security Configuration
    signing_key: str = Field(
        default="dev-" + "x" * 31,
        description='Key for signing audit entries. Generate with: python -c "import secrets; print(secrets.token_hex(32))"',
    )
    jwt_secret_key: str = Field(
        default="dev-" + "x" * 31,
        description='Secret key for JWT generation. Generate with: python -c "import secrets; print(secrets.token_hex(32))"',
    )
    jwt_access_token_expire_minutes: int = Field(
        default=60, description="JWT access token expiry in minutes"
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_private_key: str | None = Field(
        default=None, description="RSA Private Key (PEM) for JWT signing"
    )
    jwt_public_key: str | None = Field(
        default=None, description="RSA Public Key (PEM) for JWT verification"
    )

    cors_allowed_origins: list[str] = Field(
        default=[
            "http://localhost:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3001",
        ],
        description="Allowed CORS origins (comma-separated in env)",
    )

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_cors(cls, v):
        import json

        if isinstance(v, str):
            if v.startswith("["):
                try:
                    parsed = json.loads(v)
                    if not isinstance(parsed, list):
                        raise ValueError("CORS_ORIGINS must be a JSON array")
                    return parsed
                except (json.JSONDecodeError, ValueError) as e:
                    raise ValueError(
                        f"Invalid CORS_ALLOWED_ORIGINS JSON array: '{v}'. "
                        "Expected format: ['http://localhost:3000', 'https://example.com']. "
                        f"Error: {e}"
                    ) from e
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    @field_validator("cors_allowed_origins")
    @classmethod
    def validate_cors_no_wildcard_in_production(cls, v: list, info) -> list:
        """Block wildcard CORS in production — it nullifies same-origin protection."""
        data = info.data if hasattr(info, "data") else {}
        env = data.get("app_env", "development")
        if env == "production" and ("*" in v or "" in v):
            raise ValueError(
                "CORS_ALLOWED_ORIGINS must not contain '*' or empty strings in production. "
                "Specify explicit allowed origins (e.g. https://forensic.yourdomain.com)."
            )
        return v

    @property
    def jwt_signing_key(self) -> str:
        """Get the key to use for signing tokens.

        Raises:
            ValueError: In production, if RS256 is selected but JWT_PRIVATE_KEY is absent.
                        Silently falling back to the HMAC secret would downgrade the
                        cryptographic guarantee without any operator awareness.
        """
        if self.jwt_algorithm.startswith("RS"):
            if not self.jwt_private_key:
                if self.app_env == "production":
                    raise ValueError(
                        "JWT_ALGORITHM is set to RS256 but JWT_PRIVATE_KEY is not configured. "
                        "Refusing to fall back to HMAC in production — this would silently "
                        "downgrade the signing guarantee. Set JWT_PRIVATE_KEY or switch "
                        "JWT_ALGORITHM to HS256."
                    )
                # In development, fall back to symmetric key for convenience
                return self.jwt_secret_key
            return self.jwt_private_key
        return self.jwt_secret_key

    @property
    def jwt_verification_key(self) -> str:
        """Get the key to use for verifying tokens.

        Raises:
            ValueError: In production, if RS256 is selected but JWT_PUBLIC_KEY is absent.
        """
        if self.jwt_algorithm.startswith("RS"):
            if not self.jwt_public_key:
                if self.app_env == "production":
                    raise ValueError(
                        "JWT_ALGORITHM is set to RS256 but JWT_PUBLIC_KEY is not configured. "
                        "Refusing to fall back to HMAC in production. "
                        "Set JWT_PUBLIC_KEY or switch JWT_ALGORITHM to HS256."
                    )
                # In development, fall back to symmetric key for convenience
                return self.jwt_secret_key
            return self.jwt_public_key
        return self.jwt_secret_key

    @property
    def effective_jwt_secret(self) -> str:
        """Get the effective JWT secret key.

        SECURITY: Never fall back to signing_key — key separation principle.
        JWT_SECRET_KEY must be explicitly set in all environments.
        """
        if not self.jwt_secret_key:
            raise ValueError(
                "JWT_SECRET_KEY must be explicitly configured. "
                "Do not rely on SIGNING_KEY for JWT — key separation is required. "
                'Generate with: python -c "import secrets; print(secrets.token_hex(32))"'
            )
        return self.jwt_secret_key

    @field_validator("jwt_secret_key", check_fields=False)
    @classmethod
    def validate_jwt_secret_key(cls, v: str | None, info) -> str | None:
        """Block insecure default JWT secret keys in production."""
        if v is None:
            return v
        data = info.data if hasattr(info, "data") else {}
        env = data.get("app_env", "development")
        if env == "production":
            _forbidden = (
                "change",
                "default",
                "dev",
                "generate",
                "placeholder",
                "replace_me",
                "replace",
                "secret-key",
                "strong",
                "example",
                "production",
            )
            if any(word in v.lower() for word in _forbidden):
                raise ValueError(
                    "JWT_SECRET_KEY must be changed from the placeholder for production! "
                    "Set a strong, unique key via the JWT_SECRET_KEY environment variable."
                )
            if len(v) < 32:
                raise ValueError("JWT_SECRET_KEY must be at least 32 characters in production!")

            # Entropy check: reject weak human-chosen keys.
            # Exception: pure hex strings from secrets.token_hex() are cryptographically
            # secure (256 bits for a 64-char key) despite using only 16 symbols — do not
            # penalise them for lacking uppercase/special chars.
            _is_hex = all(c in "0123456789abcdefABCDEF" for c in v)
            if not _is_hex:
                has_upper = any(c.isupper() for c in v)
                has_lower = any(c.islower() for c in v)
                has_digit = any(c.isdigit() for c in v)
                has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in v)
                if sum([has_upper, has_lower, has_digit, has_special]) < 3:
                    raise ValueError(
                        "JWT_SECRET_KEY must contain at least 3 of: uppercase, lowercase, digits, special chars"
                    )
        return v

    # Agent Configuration
    default_iteration_ceiling: int = Field(
        default=20, description="Default iteration ceiling for agent loops"
    )
    hitl_enabled: bool = Field(default=True, description="Enable Human-in-the-Loop checkpoints")
    investigation_timeout: int = Field(
        default=600, description="Max seconds for a single investigation"
    )
    hitl_decision_timeout: int = Field(
        default=3600,
        description="Max seconds to wait for HITL decision before auto-skipping deep analysis",
    )
    investigation_max_retries: int = Field(
        default=3, description="Max retry attempts for failed investigations"
    )
    investigation_retry_delay: float = Field(
        default=5.0, description="Base delay between investigation retries (seconds)"
    )
    session_ttl_hours: int = Field(
        default=24,
        description="Hours to retain completed investigation sessions in memory before eviction",
    )
    max_parallel_heavy_tools: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Maximum number of simultaneous heavy neural/math tools allowed (prevents CPU starvation).",
    )
    daily_cost_quota_usd: float = Field(
        default=50.0,
        ge=0.0,
        description="Daily API cost quota in USD for investigator/auditor roles. Set to 0 for unlimited.",
    )
    daily_cost_quota_admin_usd: float = Field(
        default=500.0,
        ge=0.0,
        description="Daily API cost quota in USD for admin role. Set to 0 for unlimited.",
    )

    # LLM Configuration (Global / Agents)
    llm_provider: str = Field(
        default="none",
        description="LLM provider for agents: groq (recommended), openai, anthropic, or none",
    )
    llm_api_key: str | None = Field(default=None, description="API key for LLM provider")
    llm_model: str = Field(
        default="llama-3.3-70b-versatile",
        description="LLM model. Groq: llama-3.3-70b-versatile. OpenAI: gpt-4o. Anthropic: claude-3-5-sonnet-20241022",
    )
    llm_fallback_models: str = Field(
        default="openai/gpt-oss-20b,llama-3.1-8b-instant",
        description=(
            "Comma-separated fallback models for the configured LLM provider. "
            "For Groq, these are tried after LLM_MODEL when the primary model "
            "fails or is unavailable."
        ),
    )
    llm_temperature: float = Field(
        default=0.1, description="Temperature for LLM sampling (0.0-1.0)"
    )
    llm_max_tokens: int = Field(
        default=4096, description="Maximum tokens for LLM responses (Groq: up to 32768)"
    )
    llm_timeout: float = Field(
        default=15.0,
        description="Timeout for LLM API calls in seconds (reduced from 30s to fit within per-agent timeout budget)",
    )
    llm_enable_react_reasoning: bool = Field(
        default=False,
        description="Enable LLM reasoning in ReAct loop (disabled: agents use fast task-decomposition driver)",
    )
    llm_enable_post_synthesis: bool = Field(
        default=True,
        description="After tools complete, call LLM once to synthesize findings into rich forensic narratives",
    )

    # Arbiter LLM Configuration (Dedicated high-reasoning tier)
    arbiter_llm_provider: str = Field(
        default="groq",
        description="High-reasoning provider for Arbiter deliberation. Groq Llama 3 70B is used for high-speed evidentiary synthesis.",
    )
    arbiter_llm_api_key: str | None = Field(
        default=None,
        description="Dedicated API key for Arbiter LLM (e.g. Anthropic key). If unset, falls back to LLM_API_KEY.",
    )
    arbiter_primary_model: str = Field(
        default="llama-3.3-70b-versatile",
        description="Primary reasoning engine for the Council Arbiter (Groq Llama 3 70B).",
    )
    arbiter_fallback_chain: str = Field(
        default="gemini/gemini-2.5-flash,gemini/gemini-2.5-flash-lite",
        description=(
            "Cross-provider fallback chain for the Arbiter. Supports provider prefixes "
            "(e.g. 'gemini/gemini-2.5-flash')."
        ),
    )

    # Gemini Vision Configuration (for deep analysis in Agents 1, 3, 5)
    gemini_api_key: str | None = Field(
        default=None,
        description=(
            "Google Gemini API key for vision-powered deep analysis. "
            "Used by Agent 1 (Image Integrity), Agent 3 (Object/Weapon), and "
            "Agent 5 (Metadata/Context) to perform multimodal file understanding. "
            "Get a free key at https://aistudio.google.com/apikey"
        ),
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        description=(
            "Primary Gemini model for vision analysis. "
            "gemini-2.5-flash: high-fidelity multimodal reasoning, 1M context. "
            "gemini-2.5-flash-lite: fastest stable 2.5 fallback."
        ),
    )
    gemini_fallback_models: str = Field(
        default="gemini-2.5-flash-lite,gemini-2.0-flash,gemini-2.0-flash-lite",
        description=(
            "Comma-separated ordered fallback chain tried when the primary model "
            "is unavailable or fails. Each model is attempted in order; the first "
            "successful response is used. 404/429/model-not-found triggers an "
            "immediate skip to the next model (no backoff). "
            "Default: gemini-2.5-flash -> gemini-2.5-flash-lite -> "
            "gemini-2.0-flash -> gemini-2.0-flash-lite."
        ),
    )
    gemini_timeout: float = Field(
        default=55.0,
        description="Timeout for Gemini API calls in seconds (raised to 55s for deep forensic analysis).",
    )
    gemini_max_concurrent: int = Field(
        default=2,
        ge=1,
        le=10,
        description=(
            "Maximum number of Gemini API calls that may be in-flight simultaneously "
            "across all agents. Prevents 5 concurrent agents from saturating the "
            "free-tier quota (10 RPM). Increase if you have a paid-tier key."
        ),
    )

    # Per-provider free-tier quota limits — used by the quota guard before each call
    # to decide whether to proceed or degrade gracefully.
    gemini_rpm_limit: int = Field(
        default=10,
        description="Gemini free-tier requests-per-minute limit. Paid tier: set higher.",
    )
    gemini_rpd_limit: int = Field(
        default=1500,
        description="Gemini free-tier requests-per-day limit.",
    )
    groq_rpm_limit: int = Field(
        default=30,
        description="Groq free-tier RPM limit (varies by model; 30 is conservative).",
    )
    groq_tpm_limit: int = Field(
        default=6000,
        description="Groq free-tier tokens-per-minute limit.",
    )

    # Separate Arbiter Gemini key — isolates Arbiter quota from the 5 analysis agents.
    arbiter_gemini_api_key: str | None = Field(
        default=None,
        description=(
            "Dedicated Gemini API key for the Council Arbiter. "
            "When set, Arbiter calls use this key and quota independently of agents. "
            "Recommended for free-tier deployments so Arbiter is never starved."
        ),
    )

    # Forensic Tool Timeouts
    agent_context_wait_timeout: float = Field(
        default=60.0,
        ge=10,
        le=300,
        description="Max seconds an agent waits for Agent 1 Gemini context before proceeding.",
    )
    ocr_tool_timeout: float = Field(
        default=60.0,
        ge=30,
        le=180,
        description="Timeout for OCR text extraction tools.",
    )
    clip_analysis_timeout: float = Field(
        default=90.0,
        ge=60,
        le=300,
        description="Timeout for CLIP semantic content analysis.",
    )

    @field_validator("gemini_api_key")
    @classmethod
    def validate_gemini_api_key(cls, v: str | None) -> str | None:
        """Warn if Gemini key is missing (optional — agents degrade gracefully).

        Normalises empty or whitespace-only strings to None so that
        GeminiVisionClient correctly detects "not configured" via
        ``bool(self.api_key)``.
        """
        # Normalise empty / whitespace-only value → None
        if v is not None and v.strip() == "":
            v = None

        if v is None:
            msg = (
                "GEMINI_API_KEY not set. Agents 1, 3, and 5 will use local fallback analysis "
                "instead of Gemini vision. Get a free key at https://aistudio.google.com/apikey"
            )
            warnings.warn(msg, UserWarning, stacklevel=2)
            _config_logger.warning(msg)
        elif len(v) < 20:
            msg = (
                "GEMINI_API_KEY appears too short (< 20 chars). Agents 1, 3, and 5 may skip "
                "Gemini vision deep analysis — verify the key at https://aistudio.google.com/apikey"
            )
            warnings.warn(msg, UserWarning, stacklevel=2)
            _config_logger.warning(msg)
        return v

    @field_validator("llm_api_key")
    @classmethod
    def validate_llm_api_key(cls, v: str | None, info) -> str | None:
        """Validate LLM API key when LLM provider is enabled."""
        data = info.data if hasattr(info, "data") else {}
        provider = data.get("llm_provider", "none")

        valid_providers = {"groq", "openai", "anthropic", "none"}
        if provider not in valid_providers:
            raise ValueError(
                f"LLM_PROVIDER must be one of {sorted(valid_providers)}, got '{provider}'. "
                "Recommended: groq (fastest, free tier available at console.groq.com)"
            )
        if provider != "none" and not v:
            raise ValueError(
                f"LLM_API_KEY is required when LLM_PROVIDER='{provider}'. "
                "Get a free Groq API key at https://console.groq.com/keys"
            )

        if v and provider != "none" and len(v) < 20:
            raise ValueError("LLM_API_KEY appears invalid (too short)")

        return v

    # Retry Configuration
    database_retry_max: int = Field(default=5, description="Max database connection retries")
    database_retry_delay: float = Field(
        default=1.0, description="Base database retry delay (seconds)"
    )
    external_api_retry_max: int = Field(default=3, description="Max external API retries")
    external_api_retry_delay: float = Field(
        default=1.0, description="Base external API retry delay (seconds)"
    )

    # Metrics scraping
    metrics_scrape_token: str | None = Field(
        default=None,
        description="Bearer token required to access /api/v1/metrics/raw (Prometheus scrape endpoint). "
        "If not set, the endpoint returns 503.",
    )

    # Session Persistence
    enable_session_persistence: bool = Field(
        default=True, description="Enable PostgreSQL session persistence"
    )

    # Worker mode — when True, the API server submits investigations to the
    # Redis queue for an external worker process to pick up.  When False
    # (default), investigations run in-process via an asyncio task.
    # IMPORTANT: never set both use_redis_worker=True and run the in-process
    # worker simultaneously — the same investigation would execute twice.
    use_redis_worker: bool = Field(
        default=True,
        description="Submit investigations to Redis queue for external worker (worker.py). "
        "Set False when running investigations in-process.",
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is one of the allowed values."""
        allowed = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"Log level must be one of {allowed}, got {v}")
        return v_upper

    @field_validator("signing_key", check_fields=False)
    @classmethod
    def validate_signing_key(cls, v: str, info) -> str:
        """Block empty or insecure signing keys in all environments."""
        if not v or not v.strip():
            raise ValueError(
                "SIGNING_KEY cannot be empty. Generate one with: "
                'python -c "import secrets; print(secrets.token_hex(32))"'
            )
        data = info.data if hasattr(info, "data") else {}
        env = data.get("app_env", "development")
        if env == "production":
            _forbidden = (
                "change",
                "default",
                "dev",
                "example",
                "generate",
                "placeholder",
                "replace_me",
                "replace",
                "secret-key",
                "strong",
                "production",
            )
            if any(word in v.lower() for word in _forbidden):
                raise ValueError(
                    "SIGNING_KEY must be changed from the placeholder for production! "
                    'Generate with: python -c "import secrets; print(secrets.token_hex(32))"'
                )
            if len(v) < 32:
                raise ValueError("SIGNING_KEY must be at least 32 characters in production!")
        return v

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.app_env == "production":
            if not self.signing_key or len(self.signing_key) < 32:
                raise ValueError("SIGNING_KEY must be >= 32 chars in production")
            if not self.jwt_secret_key or len(self.jwt_secret_key) < 32:
                raise ValueError("JWT_SECRET_KEY must be >= 32 chars in production")
            if not self.redis_password:
                raise ValueError("REDIS_PASSWORD must be set in production")
            for _name, _val in (
                ("SIGNING_KEY", self.signing_key),
                ("JWT_SECRET_KEY", self.jwt_secret_key),
                ("REDIS_PASSWORD", self.redis_password or ""),
            ):
                if "replace_me" in _val.lower() or "replace" in _val.lower():
                    raise ValueError(
                        f"{_name} still contains a placeholder value. "
                        "Run infra/generate_production_keys.sh --write to populate real secrets."
                    )
            if not self.qdrant_api_key or "replace_me" in (self.qdrant_api_key or "").lower():
                raise ValueError(
                    "QDRANT_API_KEY must be set in production. "
                    "Without it, Qdrant exposes all vectors to anyone who can reach port 6333."
                )
        return self


    @property
    def gemini_available(self) -> bool:
        """True when a plausible Gemini API key is configured."""
        return bool(self.gemini_api_key and len(self.gemini_api_key) >= 20)


@lru_cache
def get_settings() -> Settings:
    """
    Get cached application settings.

    Uses lru_cache to ensure settings are only loaded once.
    Call settings.cache_clear() to reload settings (useful for testing).
    """
    return Settings()


def validate_production_settings() -> None:
    """Validate that production deployments are hardened. Call at startup."""
    import os

    s = get_settings()
    if s.app_env != "production":
        return
    errors: list[str] = []
    _insecure_patterns = (
        "change",
        "set_a_strong",
        "default",
        "123",
        "admin",
        "investigator",
        "password",
        "replace_me",
        "replace",
    )
    for var in ("BOOTSTRAP_ADMIN_PASSWORD", "BOOTSTRAP_INVESTIGATOR_PASSWORD"):
        val = os.environ.get(var, "").strip()
        if not val or any(p in val.lower() for p in _insecure_patterns):
            errors.append(f"{var} must be set to a strong, unique password for production")
    _key_forbidden = (
        "dev-",
        "change",
        "default",
        "generate",
        "placeholder",
        "replace_me",
        "replace",
        "secret-key",
        "strong",
        "example",
        "production",
        "your_gemini_key",
    )
    _sk = s.signing_key.lower()
    _jk = s.jwt_secret_key.lower()
    _gk = (s.gemini_api_key or "").lower()

    if any(w in _sk for w in _key_forbidden) or len(s.signing_key) < 32:
        errors.append(
            'SIGNING_KEY must be a unique, high-entropy string of at least 32 characters; generate with: python -c "import secrets; print(secrets.token_hex(32))"'
        )
    if any(w in _jk for w in _key_forbidden) or len(s.jwt_secret_key) < 32:
        errors.append(
            "JWT_SECRET_KEY must be changed from placeholder and at least 32 characters for production"
        )
    if "your_gemini_key" in _gk:
        errors.append(
            "GEMINI_API_KEY placeholder detected in production! Please set a valid key or leave empty for local fallback."
        )

    # Entropy check for both main secrets.
    # Pure hex strings (secrets.token_hex output) are exempt — they are cryptographically
    # secure by construction and must not be rejected for lacking uppercase/special chars.
    for key_name, val in [("SIGNING_KEY", s.signing_key), ("JWT_SECRET_KEY", s.jwt_secret_key)]:
        if all(c in "0123456789abcdefABCDEF" for c in val):
            continue  # hex key — entropy is fine
        has_upper = any(c.isupper() for c in val)
        has_lower = any(c.islower() for c in val)
        has_digit = any(c.isdigit() for c in val)
        has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in val)
        if sum([has_upper, has_lower, has_digit, has_special]) < 3:
            errors.append(
                f"{key_name} must contain at least 3 of: uppercase, lowercase, digits, special chars"
            )
    if errors:
        raise ValueError(
            "Production deployment validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        )
