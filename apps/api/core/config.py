"""
Configuration Management Module
===============================

Pydantic Settings-based configuration loading from environment variables.
All configuration is centralized and validated at startup.
"""

import logging
import os
from functools import lru_cache  # noqa: F401 — kept for any external callers
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_config_logger = logging.getLogger(__name__)
_APP_ROOT = Path(__file__).resolve().parent.parent

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
        env_file=[
            ".env.local",
            ".env",
            "../.env.local",
            "../.env",
            "../../.env.local",
            "../../.env",
        ],
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
        default=True,
        description=(
            "Enable strict offline mode for ML models. "
            "When True, all ML libraries (HuggingFace, YOLO, CLIP) "
            "are forced to use local cache and will fail if models are missing, "
            "rather than attempting an internet download."
        ),
    )

    analysis_execution_mode: str = Field(
        default="hybrid",
        description=(
            "Analysis execution mode. "
            "'hybrid' allows configured remote providers with local fallback. "
            "'local_only' prohibits all external AI provider calls and runs only "
            "deterministic/local ML tools."
        ),
    )

    @field_validator("analysis_execution_mode")
    @classmethod
    def validate_analysis_execution_mode(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        allowed = {"hybrid", "local_only"}
        if normalized not in allowed:
            raise ValueError(
                f"ANALYSIS_EXECUTION_MODE must be one of {sorted(allowed)}, got {value!r}"
            )
        return normalized

    @property
    def local_only_analysis(self) -> bool:
        return self.analysis_execution_mode == "local_only"

    @property
    def external_ai_allowed(self) -> bool:
        return not self.local_only_analysis

    @property
    def hybrid_analysis(self) -> bool:
        return self.analysis_execution_mode == "hybrid"

    @property
    def remote_visual_profile_allowed(self) -> bool:
        return bool(self.gemini_api_key) and self.analysis_execution_mode != "local_only"

    @property
    def remote_text_synthesis_allowed(self) -> bool:
        return self.hybrid_analysis and self.llm_provider not in ("none",)

    @field_validator("app_env")
    @classmethod
    def validate_app_env(cls, v: str) -> str:
        """Validate application environment."""
        allowed = ["development", "staging", "production", "testing"]
        v_lower = v.lower()
        if v_lower not in allowed:
            raise ValueError(f"Environment must be one of {allowed}, got {v}")
        return v_lower

    @field_validator("offline_mode")
    @classmethod
    def enforce_offline_in_production(cls, v: bool, info: object) -> bool:
        """Warn when OFFLINE_MODE=false in production — models may download at runtime."""
        try:
            app_env = getattr(info, "data", {}).get("app_env", "development") if info else "development"
        except Exception:
            app_env = "development"
        if app_env == "production" and not v:
            _config_logger.warning(
                "OFFLINE_MODE=false in production — models may download at runtime. "
                "Set OFFLINE_MODE=true and pre-download models in Dockerfile."
            )
        return v

    debug: bool = Field(default=False, description="Debug mode flag")
    log_level: str = Field(default="INFO", description="Logging level")
    bootstrap_admin_password: str = Field(
        default="dev-admin-password",
        description="Initial admin password for development/test bootstrap.",
    )
    bootstrap_investigator_password: str = Field(
        default="dev-investigator-password",
        description="Initial investigator password for development/test bootstrap.",
    )

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
    qdrant_https: bool = Field(default=False, description="Use HTTPS for Qdrant REST API")

    # PostgreSQL Configuration
    postgres_host: str = Field(default="localhost", description="PostgreSQL server host")
    postgres_port: int = Field(default=5432, description="PostgreSQL server port")
    postgres_user: str = Field(default="forensic_user", description="PostgreSQL username")
    postgres_password: str = Field(
        default="dev-" + "x" * 15, description="PostgreSQL database password"
    )
    postgres_db: str = Field(default="forensic_council", description="PostgreSQL database name")
    # I-H-2 / D-H-2: bumped from 2/10 to 5/25. The API and worker each get
    # their own pool; under concurrent investigations + rate-limiter +
    # custody-logger + arbiter narrative, 10 connections per process
    # saturated quickly even though Postgres allows 200.
    postgres_min_pool_size: int = Field(default=5, description="Min DB connection pool size")
    postgres_max_pool_size: int = Field(default=25, description="Max DB connection pool size")
    # I-H-2 / D-H-2: separate connect vs command timeouts so a stuck
    # query no longer hangs the pool. 30s command_timeout matches the
    # synthesis call budget; raise via env if a deeper analysis pass
    # needs longer (e.g. for ALTER TABLE during migrations).
    postgres_connect_timeout: float = Field(
        default=10.0, description="Seconds to wait for a fresh PG connect"
    )
    postgres_command_timeout: float = Field(
        default=30.0, description="Per-statement Postgres command timeout in seconds"
    )

    # Q-C-2: previously env-only — _websocket.py reads via `getattr(settings,
    # "max_ws_connections", 1000)`, but without a Pydantic field declaration
    # the `MAX_WS_CONNECTIONS` env var was silently ignored. Now wired.
    max_ws_connections: int = Field(
        default=1000,
        description="Max concurrent WebSocket connections per API process",
    )

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
        default="detr-resnet-50",
        description=(
            "Object detection model. Use detr-resnet-50 for commercial use (Apache-2.0). "
            "Ultralytics YOLO models (yolo11n.pt, yolo11m.pt) are AGPL-licensed and require "
            "enable_agpl_models=True for non-compliant use."
        ),
    )
    enable_agpl_models: bool = Field(
        default=False,
        description=(
            "Set True only if AGPL compliance is confirmed. "
            "Enables Ultralytics YOLO models which are AGPL-licensed. "
            "For commercial use, keep False and use detr-resnet-50."
        ),
    )
    enable_research_models: bool = Field(
        default=False,
        description=(
            "Enables BusterNet, F3-Net, ManTra-Net, TruFor, and clovaai/AASIST. "
            "These models are non-commercial only. Set True only for research deployments."
        ),
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

    @field_validator(
        "hf_home",
        "torch_home",
        "yolo_model_dir",
        "easyocr_model_dir",
        "numba_cache_dir",
        "calibration_models_path",
        mode="after",
    )
    @classmethod
    def normalize_container_cache_paths_for_host(cls, v: str) -> str:
        """Map Docker-only /app paths to writable local paths on Windows host runs."""
        if os.name != "nt" or os.environ.get("RUNNING_IN_DOCKER") == "1":
            return v
        normalized = v.replace("\\", "/")
        if normalized.startswith("/app/cache/"):
            return str(_APP_ROOT / ".cache" / normalized.removeprefix("/app/cache/"))
        if normalized.startswith("/app/storage/"):
            return str(_APP_ROOT / "storage" / normalized.removeprefix("/app/storage/"))
        return v

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

    # ─── Frontend & API Networking ───────────────────────────────────────────
    next_public_api_url: str | None = Field(default=None, alias="NEXT_PUBLIC_API_URL")
    internal_api_url: str | None = Field(default=None, alias="INTERNAL_API_URL")

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
        """
        Parse CORS origins from environment variable.
        Supports both CSV (preferred) and JSON array formats.
        Strips brackets and quotes for robustness against manual .env edits.
        """
        import json

        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            # Robust handling: if it looks like a JSON list, try to parse it
            if v.startswith("["):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [str(i).strip().strip("\"'").strip() for i in parsed]
                except (json.JSONDecodeError, ValueError):
                    # Fall back to CSV parsing if JSON fails
                    v = v.strip("[]")

            # Split on comma and strip whitespace/quotes from each origin
            return [i.strip().strip("\"'").strip() for i in v.split(",") if i.strip()]
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
                "placeholder",
                "replace_me",
                "replace",
                "secret-key",
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
        default=2400, description="Max seconds for a single investigation (40 min — accounts for up to 5 concurrent deep agents, each 480s)"
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
        description="Maximum number of simultaneous heavy neural/math tools allowed (prevents CPU starvation). Reduced to 2 to avoid burst contention during deep passes.",
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

    # Free-tier mode — restricts providers to open-source or free-tier options.
    free_tier_mode: bool = Field(
        default=False,
        description=(
            "When True, restricts LLM_PROVIDER to: none, groq, or gemini. "
            "Prevents accidental paid-tier costs in dev."
        ),
    )

    @field_validator("free_tier_mode", mode="before")
    @classmethod
    def parse_free_tier_mode(cls, v):
        """Parse free_tier_mode from string or boolean."""
        if isinstance(v, str):
            v = v.strip().lower()
            return v in ("true", "1", "yes", "on")
        return bool(v)

    # ─── Free-tier restricted providers (updated by validator below) ─────────
    # LLM Configuration (Global / Agents)
    llm_provider: str = Field(
        default="none",
        description="LLM provider for agents: groq (recommended), gemini, or none",
    )
    llm_api_key: str | None = Field(default=None, description="API key for LLM provider")
    llm_model: str = Field(
        default="llama-3.3-70b-versatile",
        description="LLM model identifier for the selected provider.",
    )
    llm_fallback_models: str = Field(
        default="llama-3.1-8b-instant",
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
        default=25.0,
        description="Timeout for LLM API calls in seconds (inner call timeout — outer asyncio wait_for is 35s to allow clean logging)"
    )
    llm_enable_react_reasoning: bool = Field(
        default=False,
        description="Enable LLM reasoning in ReAct loop (disabled: agents use fast task-decomposition driver)",
    )
    llm_enable_post_synthesis: bool = Field(
        default=True,
        description="After tools complete, call LLM once to synthesize findings into rich forensic narratives",
    )
    gemini_text_calls_enabled: bool = Field(
        default=False,
        description=(
            "Allow Gemini for text-only LLM/OCR synthesis. Default false keeps Gemini "
            "reserved for the single Agent 1 visual evidence probe."
        ),
    )

    # Arbiter LLM Configuration (Dedicated high-reasoning tier)
    arbiter_llm_provider: str = Field(
        default="groq",
        description="High-reasoning provider for Arbiter deliberation. Groq Llama 3 70B is used for high-speed evidentiary synthesis.",
    )
    arbiter_llm_api_key: str | None = Field(
        default=None,
        description="Dedicated API key for Arbiter LLM. If unset, falls back to LLM_API_KEY.",
    )
    arbiter_primary_model: str = Field(
        default="llama-3.3-70b-versatile",
        description="Primary reasoning engine for the Council Arbiter (Groq Llama 3 70B).",
    )
    arbiter_fallback_chain: str = Field(
        default="llama-3.1-8b-instant",
        description=(
            "Fallback model chain for the Arbiter. Gemini is intentionally not used "
            "by default so the Gemini key remains reserved for the Agent 1 visual probe."
        ),
    )

    # Gemini Vision Configuration (for deep analysis in Agents 1, 3, 5)
    gemini_api_key: str | None = Field(
        default=None,
        description=(
            "Google Gemini API key for vision-powered deep analysis. "
            "Used only by Agent 1 (Image Integrity) to perform the session visual probe. "
            "Other agents consume Agent 1's shared visual profile instead of calling Gemini. "
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
        default=90.0,
        description="Timeout for Gemini API calls in seconds.",
    )
    gemini_max_concurrent: int = Field(
        default=2,
        ge=1,
        le=10,
        description=(
            "Maximum number of Gemini API calls that may be in-flight simultaneously "
            "across all agents. Default 2 balances free-tier 429 avoidance with throughput. "
            "Raise to 4 with a paid-tier key or set via GEMINI_MAX_CONCURRENT env var."
        ),
    )

    # Per-provider free-tier quota limits — used by the quota guard before each call
    # to decide whether to proceed or degrade gracefully.
    gemini_rpm_limit: int = Field(
        default=5,
        description="Gemini requests-per-minute per process. Halved from 10 because API + "
        "Worker have independent in-memory guards for the same key. Paid tier: raise as needed.",
    )
    gemini_rpd_limit: int = Field(
        default=1500,
        description="Gemini free-tier requests-per-day limit.",
    )
    groq_rpm_limit: int = Field(
        default=15,
        description="Groq RPM per process (halved for cross-process key sharing; combined "
        "API+Worker = 30, matching the free-tier limit for llama-3.3-70b).",
    )
    groq_tpm_limit: int = Field(
        default=12000,
        description=(
            "Default Groq TPM fallback. Runtime uses per-model overrides where known "
            "(for example llama-3.3-70b-versatile=12K, llama-3.1-8b-instant=6K)."
        ),
    )
    # Gemini API key policy acknowledgment — required before using Gemini in production.
    # See: https://ai.google.dev/terms
    gemini_api_key_policy_ok: bool = Field(
        default=True,
        description=(
            "Acknowledge Gemini API terms of service before enabling Gemini calls. "
            "Set to true after reading and accepting the terms at https://ai.google.dev/terms"
        ),
    )

    @field_validator("gemini_api_key_policy_ok", mode="before")
    @classmethod
    def parse_gemini_policy(cls, v):
        """Parse policy flag from string or boolean."""
        if isinstance(v, str):
            v = v.strip().lower()
            return v in ("true", "1", "yes", "on")
        return bool(v)

    # Separate Arbiter Gemini key — isolates Arbiter quota from the 5 analysis agents.
    arbiter_gemini_api_key: str | None = Field(
        default=None,
        description=(
            "Dedicated Gemini API key for the Council Arbiter. "
            "When set, Arbiter calls use this key and quota independently of agents. "
            "Recommended for free-tier deployments so Arbiter is never starved."
        ),
    )

    @field_validator("arbiter_gemini_api_key")
    @classmethod
    def normalize_arbiter_gemini_key(cls, v: str | None) -> str | None:
        """Normalise empty / whitespace-only string → None (matches gemini_api_key behaviour).

        ARBITER_GEMINI_API_KEY= (empty) is documented as 'share main key'. Without this
        normaliser Pydantic loads the empty string as '' which is falsy but not None,
        creating an inconsistency with all other nullable key fields.
        """
        if v is not None and v.strip() == "":
            return None
        return v

    # ─── Vision provider chain (cascade order) ──────────────────────────────
    vision_provider_chain: str = Field(
        default="gemini,local_ensemble",
        description=(
            "Comma-separated cascade for the session visual profile. "
            "Recommended hybrid production route: gemini,local_ensemble. "
            "Gemini is attempted only by Agent1; local_ensemble is the forensic fallback. "
            "Groq Vision and OpenRouter remain available as opt-in experimental configurations."
        ),
    )
    text_provider_chain: str = Field(
        default="groq,gemini,cerebras,template",
        description="Comma-separated text-LLM cascade for synthesis.",
    )

    # ─── Groq Vision (Llama-3.2/4 vision via OpenAI-compatible endpoint) ────
    groq_vision_api_key: str | None = Field(
        default=None,
        description="Groq API key for vision models. Defaults to LLM_API_KEY if unset.",
    )
    groq_vision_model: str = Field(
        default="meta-llama/llama-4-scout-17b-16e-instruct",
        description="Groq vision model id. Free-tier alternative: llama-3.2-90b-vision-preview.",
    )
    groq_vision_timeout: float = Field(default=30.0)
    groq_vision_rpm_limit: int = Field(default=15)
    groq_vision_rpd_limit: int = Field(default=14400)

    # ─── OpenRouter (free vision models, opt-in) ────────────────────────────
    openrouter_enabled: bool = Field(default=False)
    openrouter_api_key: str | None = Field(default=None)
    openrouter_referer: str | None = Field(default=None)
    openrouter_vision_models: str = Field(
        default="meta-llama/llama-3.2-11b-vision-instruct:free,qwen/qwen2.5-vl-7b-instruct:free,google/gemma-3-12b-it:free",
    )
    openrouter_timeout: float = Field(default=45.0)
    openrouter_rpm_limit: int = Field(default=20)
    openrouter_rpd_limit: int = Field(default=200)

    # ─── Cerebras (text only, free tier) ────────────────────────────────────
    cerebras_api_key: str | None = Field(default=None)
    cerebras_model: str = Field(default="llama-3.3-70b")
    cerebras_rpm_limit: int = Field(default=30)
    cerebras_rpd_limit: int = Field(default=14400)

    # Forensic Tool Timeouts
    agent_context_wait_timeout: float = Field(
        default=60.0,
        ge=10,
        le=300,
        description="Max seconds an agent waits for Agent 1 visual profile before proceeding.",
    )
    ocr_tool_timeout: float = Field(
        default=120.0,
        ge=30,
        le=300,
        description="Timeout for OCR text extraction tools.",
    )
    clip_analysis_timeout: float = Field(
        default=90.0,
        ge=60,
        le=300,
        description="Timeout for CLIP semantic content analysis.",
    )
    ml_subprocess_timeout_s: float = Field(
        default=120.0,
        ge=30,
        le=600,
        description=(
            "Maximum seconds a single ML subprocess (torch model inference) is allowed to run "
            "before being forcibly killed. A subprocess that OOMs or deadlocks would otherwise "
            "block the agent thread indefinitely. The circuit breaker opens after "
            "CIRCUIT_BREAKER_FAILURE_THRESHOLD consecutive timeouts."
        ),
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
                "GEMINI_API_KEY not set. Agent 1 will use local ensemble for the visual "
                "evidence profile instead of Gemini vision. "
                "Get a free key at https://aistudio.google.com/apikey"
            )
            _config_logger.warning(msg)
        elif len(v) < 20:
            msg = (
                "GEMINI_API_KEY appears too short (< 20 chars). Agent 1 may skip "
                "Gemini vision for the visual evidence profile — verify the key "
                "at https://aistudio.google.com/apikey"
            )
            _config_logger.warning(msg)
        return v

    @field_validator("llm_api_key")
    @classmethod
    def validate_llm_api_key(cls, v: str | None, info) -> str | None:
        """Validate LLM API key when LLM provider is enabled."""
        data = info.data if hasattr(info, "data") else {}
        provider = data.get("llm_provider", "none")
        free_tier = data.get("free_tier_mode", False)

        valid_providers = {"groq", "gemini", "none"}
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

        # In free_tier_mode, forbid paid-tier default model strings
        if free_tier and provider == "groq":
            model = data.get("llm_model", "")
            _paid_prefixes = ("gpt-4", "gpt-3.5", "claude")
            if any(p.lower() in model.lower() for p in _paid_prefixes):
                raise ValueError(
                    f"free_tier_mode=True — model '{model}' is a paid-tier model. "
                    "Use Groq's free-tier models (llama-3.3-70b-versatile, llama-3.1-8b-instant). "
                    "Set FREE_TIER_MODE=false to use paid models."
                )

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
        default=False,
        description=(
            "Submit investigations to Redis queue for external worker (worker.py). "
            "Docker stacks override this to True via .env / docker-compose. "
            "Local dev defaults to in-process so `npm run dev` works without a worker."
        ),
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
                        "Run infra/generate_production_keys.sh --update to populate real secrets."
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


_settings_cache: "Settings | None" = None


def get_settings() -> Settings:
    """
    Return the application settings singleton.

    Uses a module-level cache (not lru_cache) so the cache can be explicitly
    cleared between tests via clear_settings_cache() to prevent env leakage.
    """
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = Settings()
    return _settings_cache


def clear_settings_cache() -> None:
    """Clear the settings cache. Call in test teardown to reset settings between tests."""
    global _settings_cache
    _settings_cache = None


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
        "example",
        "production",
        "your_gemini_key",
        "paste_gemini_key_here",
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
    if "your_gemini_key" in _gk or "paste_gemini_key_here" in _gk:
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
