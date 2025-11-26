"""
Configuration loader for the job intelligence pipeline.

Loads all settings from environment variables (.env file).
Validates required settings and provides type-safe access.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """
    Centralized configuration for all pipeline components.

    All values loaded from environment variables - NO SECRETS IN CODE.
    """

    # ===== MongoDB =====
    MONGODB_URI: str = os.getenv("MONGODB_URI", "")

    # ===== LLM APIs =====
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # LLM Provider Selection for CV Generation
    # Priority: USE_ANTHROPIC > USE_OPENROUTER > OpenAI (default)
    # OpenRouter is limited to CV generation; all other layers use OpenAI directly
    USE_OPENROUTER: bool = os.getenv("USE_OPENROUTER", "false").lower() == "true"
    USE_ANTHROPIC: bool = os.getenv("USE_ANTHROPIC", "true").lower() == "true"  # Default to true to avoid OpenRouter rate limits

    # ===== Web Scraping =====
    FIRECRAWL_API_KEY: str = os.getenv("FIRECRAWL_API_KEY", "")

    # ===== LangSmith (Observability) =====
    LANGSMITH_API_KEY: str = os.getenv("LANGSMITH_API_KEY", "")
    LANGCHAIN_TRACING_V2: str = os.getenv("LANGCHAIN_TRACING_V2", "true")
    LANGCHAIN_PROJECT: str = os.getenv("LANGCHAIN_PROJECT", "job-intelligence-pipeline")

    # ===== Google APIs =====
    GOOGLE_CREDENTIALS_PATH: str = os.getenv(
        "GOOGLE_CREDENTIALS_PATH",
        "./credentials/google-service-account.json"
    )
    GOOGLE_DRIVE_FOLDER_ID: str = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
    GOOGLE_SHEET_ID: str = os.getenv("GOOGLE_SHEET_ID", "")

    # ===== Candidate Profile =====
    CANDIDATE_PROFILE_PATH: str = os.getenv(
        "CANDIDATE_PROFILE_PATH",
        "./master-cv.md"
    )

    # ===== Feature Flags =====
    # Disable STAR selector while keeping code available for future re-enable
    ENABLE_STAR_SELECTOR: bool = os.getenv("ENABLE_STAR_SELECTOR", "false").lower() == "true"
    # Disable remote publishing (Drive/Sheets) and rely on local ./applications output by default
    ENABLE_REMOTE_PUBLISHING: bool = os.getenv("ENABLE_REMOTE_PUBLISHING", "false").lower() == "true"
    # Disable FireCrawl-backed people discovery/outreach by default (use role-based contacts instead)
    DISABLE_FIRECRAWL_OUTREACH: bool = os.getenv("DISABLE_FIRECRAWL_OUTREACH", "true").lower() == "true"

    # ===== STAR Selection Strategy (Phase 2.2) =====
    # LLM_ONLY: Skip embedding filter, use LLM scoring only (simple, slower)
    # HYBRID: Graph + embedding filter + LLM ranker (recommended, requires embeddings)
    # EMBEDDING_ONLY: Pure cosine similarity (fast, less accurate, requires embeddings)
    STAR_SELECTION_STRATEGY: str = os.getenv("STAR_SELECTION_STRATEGY", "LLM_ONLY")

    # Knowledge base path for STAR parsing
    KNOWLEDGE_BASE_PATH: str = os.getenv("KNOWLEDGE_BASE_PATH", "./knowledge-base.md")

    # ===== LLM Model Configuration =====
    # Default models per layer (can be overridden)
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "gpt-4o")  # GPT-4o for quality
    CHEAP_MODEL: str = os.getenv("CHEAP_MODEL", "gpt-4o-mini")  # Mini for simple tasks

    # CV generation model selection
    # For direct Anthropic: "claude-3-5-haiku-20241022"
    # For OpenRouter: "anthropic/claude-3-5-haiku-20241022"
    CV_MODEL: str = os.getenv("CV_MODEL", "claude-3-5-haiku-20241022")

    # Temperature settings
    CREATIVE_TEMPERATURE: float = 0.7  # For outreach generation
    ANALYTICAL_TEMPERATURE: float = 0.3  # For pain point extraction, scoring
    CV_TEMPERATURE: float = float(os.getenv("CV_TEMPERATURE", "0.33"))  # Slightly warmer CV tone

    @classmethod
    def validate(cls) -> None:
        """
        Validate that all required configuration is present.
        Raises ValueError if critical settings are missing.
        """
        required_settings = {
            "MONGODB_URI": cls.MONGODB_URI,
            "OPENAI_API_KEY": cls.OPENAI_API_KEY,
            "FIRECRAWL_API_KEY": cls.FIRECRAWL_API_KEY,
        }

        if cls.ENABLE_REMOTE_PUBLISHING:
            required_settings.update({
                "GOOGLE_CREDENTIALS_PATH": cls.GOOGLE_CREDENTIALS_PATH,
                "GOOGLE_DRIVE_FOLDER_ID": cls.GOOGLE_DRIVE_FOLDER_ID,
                "GOOGLE_SHEET_ID": cls.GOOGLE_SHEET_ID,
            })

        missing = [name for name, value in required_settings.items() if not value]

        if missing:
            raise ValueError(
                f"Missing required configuration: {', '.join(missing)}. "
                f"Please check your .env file."
            )

        if cls.USE_OPENROUTER and not cls.OPENROUTER_API_KEY:
            raise ValueError(
                "USE_OPENROUTER is enabled for CV generation but OPENROUTER_API_KEY is missing."
            )

        # Validate file paths exist
        if cls.ENABLE_REMOTE_PUBLISHING:
            if not Path(cls.GOOGLE_CREDENTIALS_PATH).exists():
                raise FileNotFoundError(
                    f"Google credentials file not found: {cls.GOOGLE_CREDENTIALS_PATH}"
                )

        if not Path(cls.CANDIDATE_PROFILE_PATH).exists():
            raise FileNotFoundError(
                f"Candidate profile file not found: {cls.CANDIDATE_PROFILE_PATH}"
            )

    @classmethod
    def get_llm_api_key(cls) -> str:
        """Get the API key for general pipeline LLM calls (always OpenAI)."""
        return cls.OPENAI_API_KEY

    @classmethod
    def get_llm_base_url(cls) -> Optional[str]:
        """General LLM base URL (None to use OpenAI directly)."""
        return None

    @classmethod
    def get_cv_llm_api_key(cls) -> str:
        """
        Get the API key for CV generation.

        Priority: Anthropic > OpenRouter > OpenAI
        """
        if cls.USE_ANTHROPIC and cls.ANTHROPIC_API_KEY:
            return cls.ANTHROPIC_API_KEY
        if cls.USE_OPENROUTER and cls.OPENROUTER_API_KEY:
            return cls.OPENROUTER_API_KEY
        return cls.OPENAI_API_KEY

    @classmethod
    def get_cv_llm_base_url(cls) -> Optional[str]:
        """
        Get the LLM base URL for CV generation.

        Returns:
            - "https://openrouter.ai/api/v1" when using OpenRouter
            - None when using direct Anthropic or OpenAI APIs
        """
        if cls.USE_ANTHROPIC and cls.ANTHROPIC_API_KEY:
            return None  # Use direct Anthropic SDK
        if cls.USE_OPENROUTER and cls.OPENROUTER_API_KEY:
            return "https://openrouter.ai/api/v1"
        return None

    @classmethod
    def get_cv_llm_provider(cls) -> str:
        """
        Get the LLM provider being used for CV generation.

        Returns:
            "anthropic", "openrouter", or "openai"
        """
        if cls.USE_ANTHROPIC and cls.ANTHROPIC_API_KEY:
            return "anthropic"
        if cls.USE_OPENROUTER and cls.OPENROUTER_API_KEY:
            return "openrouter"
        return "openai"

    @classmethod
    def summary(cls) -> str:
        """Return a summary of the current configuration (safe for logging)."""
        return f"""
Configuration Summary:
  MongoDB: {'✓ Configured' if cls.MONGODB_URI else '✗ Missing'}
  LLM (general): OpenAI {'✓' if cls.get_llm_api_key() else '✗ Missing'}
  CV LLM: {'OpenRouter' if cls.get_cv_llm_base_url() else 'OpenAI'} {'✓' if cls.get_cv_llm_api_key() else '✗ Missing'}
  FireCrawl: {'✓ Configured' if cls.FIRECRAWL_API_KEY else '✗ Missing'}
  People Mapper FireCrawl: {'Disabled' if cls.DISABLE_FIRECRAWL_OUTREACH else 'Enabled'}
  LangSmith: {'✓ Enabled' if cls.LANGSMITH_API_KEY else '✗ Disabled'}
  Google Drive: {'✓ Configured' if cls.GOOGLE_DRIVE_FOLDER_ID else '✗ Missing'}
  Google Sheets: {'✓ Configured' if cls.GOOGLE_SHEET_ID else '✗ Missing'}
  Candidate Profile: {cls.CANDIDATE_PROFILE_PATH}
  Default Model: {cls.DEFAULT_MODEL}
        """.strip()


# Validate configuration on import (fail fast if misconfigured)
# Comment this out during development if you want to test without all keys
# Config.validate()
