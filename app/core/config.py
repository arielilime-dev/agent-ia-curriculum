"""Configuration loading for the Resume Analyzer API.

All runtime configuration is exposed through :class:`Settings`, which reads from
environment variables (and an optional ``.env`` file).  Instantiating the class
validates cross-field constraints so that misconfiguration fails at startup
instead of at the first request.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]
AIProviderName = Literal["heuristic", "openai", "deepseek", "ollama", "openai_compatible"]

DEFAULT_JWT_SECRET = "insecure-development-secret-change-me-please"
MIN_PRODUCTION_SECRET_LENGTH = 32

# Base URLs for the built-in OpenAI-compatible providers.
PROVIDER_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "ollama": "http://localhost:11434/v1",
}


class Settings(BaseSettings):
    """Typed application settings.

    Values can be overridden with environment variables of the same name
    (case-insensitive), e.g. ``DATABASE_URL`` or ``JWT_SECRET_KEY``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -- Application ---------------------------------------------------------
    app_name: str = "Resume Analyzer API"
    app_version: str = "1.0.0"
    environment: Environment = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    # -- Database ------------------------------------------------------------
    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    database_echo: bool = False
    auto_create_tables: bool = True

    # -- Authentication ------------------------------------------------------
    jwt_secret_key: str = DEFAULT_JWT_SECRET
    jwt_issuer: str = "resume-analyzer"
    access_token_ttl_minutes: int = Field(default=15, ge=1, le=1440)
    refresh_token_ttl_days: int = Field(default=7, ge=1, le=90)
    password_min_length: int = Field(default=8, ge=8, le=128)
    # 600k PBKDF2-HMAC-SHA256 iterations is the OWASP 2023 recommendation.
    # The lower bound exists so that tests can use a fast, deterministic value.
    password_hash_iterations: int = Field(default=600_000, ge=1_000, le=5_000_000)

    # -- Uploads -------------------------------------------------------------
    max_upload_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)
    max_resume_chars: int = Field(default=100_000, ge=1_000, le=1_000_000)
    allowed_extensions: set[str] = Field(default_factory=lambda: {".pdf", ".docx", ".txt", ".md"})
    storage_dir: Path = Path("./data/uploads")

    # -- AI ------------------------------------------------------------------
    ai_provider: AIProviderName = "heuristic"
    ai_api_key: str | None = None
    ai_base_url: str | None = None
    ai_model: str = "gpt-4o-mini"
    ai_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    ai_max_retries: int = Field(default=2, ge=0, le=5)
    ai_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    ai_fallback_enabled: bool = True

    # -- HTTP / security -----------------------------------------------------
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    rate_limit_enabled: bool = True
    rate_limit_auth_per_minute: int = Field(default=30, ge=1, le=10_000)

    # -- Validators ----------------------------------------------------------
    @field_validator("allowed_extensions")
    @classmethod
    def _normalize_extensions(cls, value: set[str]) -> set[str]:
        normalized: set[str] = set()
        for raw in value:
            ext = raw.strip().lower()
            if not ext:
                continue
            if not ext.startswith("."):
                ext = f".{ext}"
            normalized.add(ext)
        if not normalized:
            raise ValueError("allowed_extensions must contain at least one extension")
        return normalized

    @field_validator("ai_base_url")
    @classmethod
    def _strip_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().rstrip("/")
        return cleaned or None

    @field_validator("ai_api_key")
    @classmethod
    def _strip_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def _validate_production_hardening(self) -> Settings:
        if self.environment == "production":
            if self.jwt_secret_key == DEFAULT_JWT_SECRET:
                raise ValueError("JWT_SECRET_KEY must be changed in production")
            if len(self.jwt_secret_key) < MIN_PRODUCTION_SECRET_LENGTH:
                raise ValueError(
                    f"JWT_SECRET_KEY must be at least {MIN_PRODUCTION_SECRET_LENGTH} characters"
                )
            if self.password_hash_iterations < 100_000:
                raise ValueError("PASSWORD_HASH_ITERATIONS must be >= 100000 in production")
            if self.debug:
                raise ValueError("DEBUG must be false in production")
            if "*" in self.cors_origins:
                raise ValueError("wildcard CORS origin is not allowed in production")
        return self

    # -- Helpers -------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_testing(self) -> bool:
        return self.environment == "test"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def resolved_ai_base_url(self) -> str | None:
        """Return the effective base URL for the configured AI provider."""
        if self.ai_base_url:
            return self.ai_base_url
        return PROVIDER_BASE_URLS.get(self.ai_provider)

    def ensure_storage_dir(self) -> Path:
        """Create the upload directory (if needed) and return its absolute path."""
        path = self.storage_dir.expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()
