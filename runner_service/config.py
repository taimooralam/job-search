"""
Runner Service Configuration Module

Centralized configuration management with Pydantic validation.
All environment variables are validated at startup to catch misconfigurations early.
"""

from functools import lru_cache
from typing import List, Optional
from pydantic import Field, field_validator, AnyHttpUrl
from pydantic_settings import BaseSettings


class RunnerSettings(BaseSettings):
    """
    Runner service configuration with validation.

    All settings can be overridden via environment variables.
    Validation happens at startup to fail fast on misconfiguration.
    """

    # === Concurrency & Limits ===
    max_concurrency: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Maximum concurrent pipeline runs (1-20)"
    )
    log_buffer_limit: int = Field(
        default=500,
        ge=100,
        le=10000,
        description="Maximum log lines per run (100-10000)"
    )
    pipeline_timeout_seconds: int = Field(
        default=600,
        ge=60,
        le=3600,
        description="Pipeline execution timeout in seconds (60-3600)"
    )

    # === Security ===
    runner_api_secret: Optional[str] = Field(
        default=None,
        min_length=16,
        description="API authentication secret (min 16 chars for security)"
    )
    environment: str = Field(
        default="development",
        description="Environment: development, staging, production"
    )

    # === Service URLs ===
    pdf_service_url: str = Field(
        default="http://pdf-service:8001",
        description="PDF service endpoint URL"
    )

    # === CORS ===
    cors_origins: str = Field(
        default="",
        description="Comma-separated list of allowed CORS origins"
    )

    # === MongoDB ===
    mongodb_uri: str = Field(
        default="mongodb://localhost:27017",
        description="MongoDB connection URI"
    )
    mongo_db_name: str = Field(
        default="jobs",
        description="MongoDB database name"
    )

    # === Redis (Optional) ===
    redis_url: Optional[str] = Field(
        default=None,
        description="Redis connection URL (optional)"
    )

    # === API Keys for Usage Tracking ===
    firecrawl_api_key: Optional[str] = Field(
        default=None,
        description="FireCrawl API key for usage tracking"
    )
    openrouter_api_key: Optional[str] = Field(
        default=None,
        description="OpenRouter API key for credits tracking"
    )

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment is a known value."""
        allowed = {"development", "staging", "production"}
        v_lower = v.lower()
        if v_lower not in allowed:
            raise ValueError(f"environment must be one of: {', '.join(allowed)}")
        return v_lower

    @field_validator("runner_api_secret")
    @classmethod
    def validate_secret_strength(cls, v: Optional[str]) -> Optional[str]:
        """Validate API secret has minimum entropy for production."""
        if v is None:
            return None
        # Check for common weak secrets
        weak_secrets = {"secret", "password", "12345678901234567", "changeme"}
        if v.lower() in weak_secrets or len(set(v)) < 4:
            raise ValueError("API secret is too weak - use a secure random string")
        return v

    @field_validator("pdf_service_url", "mongodb_uri")
    @classmethod
    def validate_url_format(cls, v: str) -> str:
        """Basic URL format validation."""
        if not v.startswith(("http://", "https://", "mongodb://", "mongodb+srv://")):
            raise ValueError(f"Invalid URL format: {v}")
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins into a list."""
        if not self.cors_origins:
            return []
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == "production"

    @property
    def auth_required(self) -> bool:
        """Check if authentication is required."""
        # Auth required in production OR if secret is configured
        return self.is_production or self.runner_api_secret is not None

    def validate_production_config(self) -> List[str]:
        """
        Validate configuration is suitable for production.

        Returns list of warning/error messages.
        """
        issues = []

        if self.is_production:
            if not self.runner_api_secret:
                issues.append("CRITICAL: RUNNER_API_SECRET required in production")
            if not self.cors_origins:
                issues.append("WARNING: CORS_ORIGINS not configured")
            if "localhost" in self.mongodb_uri:
                issues.append("WARNING: Using localhost MongoDB in production")

        return issues

    class Config:
        env_prefix = ""  # No prefix, use exact env var names
        case_sensitive = False  # RUNNER_API_SECRET = runner_api_secret

        # Map env vars to field names (handles different naming conventions)
        env_mapping = {
            "MAX_CONCURRENCY": "max_concurrency",
            "LOG_BUFFER_LIMIT": "log_buffer_limit",
            "PIPELINE_TIMEOUT_SECONDS": "pipeline_timeout_seconds",
            "RUNNER_API_SECRET": "runner_api_secret",
            "ENVIRONMENT": "environment",
            "PDF_SERVICE_URL": "pdf_service_url",
            "CORS_ORIGINS": "cors_origins",
            "MONGODB_URI": "mongodb_uri",
            "MONGO_DB_NAME": "mongo_db_name",
            "REDIS_URL": "redis_url",
        }


@lru_cache()
def get_settings() -> RunnerSettings:
    """
    Get cached settings instance.

    Settings are loaded once and cached for performance.
    Use this function to access configuration throughout the app.
    """
    return RunnerSettings()


def validate_config_on_startup() -> None:
    """
    Validate configuration at application startup.

    Raises ValueError with details if config is invalid.
    Logs warnings for non-critical issues.
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        settings = get_settings()
    except Exception as e:
        raise ValueError(f"Configuration validation failed: {e}")

    # Check production-specific requirements
    issues = settings.validate_production_config()

    for issue in issues:
        if issue.startswith("CRITICAL"):
            raise ValueError(issue)
        else:
            logger.warning(issue)

    # Log loaded configuration (redact secrets)
    logger.info(f"Configuration loaded: environment={settings.environment}")
    logger.info(f"  max_concurrency={settings.max_concurrency}")
    logger.info(f"  pipeline_timeout={settings.pipeline_timeout_seconds}s")
    logger.info(f"  pdf_service_url={settings.pdf_service_url}")
    logger.info(f"  mongodb_uri={'*****' if 'localhost' not in settings.mongodb_uri else settings.mongodb_uri}")
    logger.info(f"  auth_required={settings.auth_required}")


# Convenience exports
settings = get_settings()
