"""
Per-Step LLM Configuration System.

Provides configurable tier settings for each pipeline step with environment variable overrides.
This system allows fine-grained control over which Claude model tier is used for each operation,
with the ability to override settings via environment variables for experimentation.

Tier Definitions:
    - low: Claude Haiku 4.5 - Fastest, lowest cost, good for bulk operations
    - middle: Claude Sonnet 4.5 - Best quality/cost ratio, default for most tasks
    - high: Claude Opus 4.5 - Highest quality, for critical operations

Usage:
    from src.common.llm_config import get_step_config, StepConfig

    # Get config for a specific step
    config = get_step_config("grader")
    print(config.tier)  # "low"
    print(config.get_claude_model())  # "claude-haiku-4-5-20251001"

    # Environment variable overrides:
    # LLM_TIER_grader=high  -> Override grader to use Opus
    # LLM_MODEL_grader=claude-opus-4-5-20251101  -> Explicit model override
    # LLM_TIMEOUT_grader=300  -> Override timeout for grader step
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Optional, Literal, Dict

logger = logging.getLogger(__name__)

# Type alias for tier levels
TierType = Literal["low", "middle", "high"]


# ===== TIER TO MODEL MAPPINGS =====

TIER_TO_CLAUDE_MODEL: Dict[TierType, str] = {
    "low": "claude-haiku-4-5-20251001",
    "middle": "claude-sonnet-4-5-20250929",
    "high": "claude-opus-4-5-20251101",
}

TIER_TO_FALLBACK_MODEL: Dict[TierType, str] = {
    "low": "gpt-4o-mini",
    "middle": "gpt-4o",
    "high": "claude-opus-4-5-20251101",  # Via Anthropic API for fallback
}

# Approximate costs per 1K tokens (USD) for reference
TIER_COSTS = {
    "low": {"input": 0.00025, "output": 0.00125},      # Haiku
    "middle": {"input": 0.003, "output": 0.015},       # Sonnet
    "high": {"input": 0.015, "output": 0.075},         # Opus
}


@dataclass
class StepConfig:
    """
    Configuration for a single LLM invocation step.

    Each pipeline step can have its own tier, model overrides, timeout,
    retry settings, and fallback behavior.

    Attributes:
        tier: Model tier level ("low", "middle", "high")
        claude_model: Override the Claude model for this step (None uses tier default)
        fallback_model: Override the LangChain fallback model (None uses tier default)
        timeout_seconds: Maximum time to wait for LLM response
        max_retries: Number of retry attempts before failing
        use_fallback: Whether to use LangChain fallback if Claude CLI fails
    """

    tier: TierType = "middle"
    claude_model: Optional[str] = None
    fallback_model: Optional[str] = None
    timeout_seconds: int = 120
    max_retries: int = 2
    use_fallback: bool = True

    def get_claude_model(self) -> str:
        """
        Get the Claude model to use for this step.

        Returns the explicit claude_model if set, otherwise returns
        the default model for the configured tier.

        Returns:
            Claude model identifier string
        """
        if self.claude_model:
            return self.claude_model
        return TIER_TO_CLAUDE_MODEL.get(self.tier, TIER_TO_CLAUDE_MODEL["middle"])

    def get_fallback_model(self) -> str:
        """
        Get the LangChain fallback model to use for this step.

        Returns the explicit fallback_model if set, otherwise returns
        the default fallback model for the configured tier.

        Returns:
            Fallback model identifier string
        """
        if self.fallback_model:
            return self.fallback_model
        return TIER_TO_FALLBACK_MODEL.get(self.tier, TIER_TO_FALLBACK_MODEL["middle"])

    def get_estimated_cost_per_1k_tokens(self) -> Dict[str, float]:
        """
        Get estimated cost per 1K tokens for this tier.

        Returns:
            Dict with 'input' and 'output' cost estimates in USD
        """
        return TIER_COSTS.get(self.tier, TIER_COSTS["middle"])


# ===== DEFAULT STEP CONFIGURATIONS =====

STEP_CONFIGS: Dict[str, StepConfig] = {
    # Layer 3: Company Researcher
    "classify_company_type": StepConfig(tier="low"),
    "analyze_company_signals": StepConfig(tier="middle"),
    "summarize_with_llm": StepConfig(tier="low"),
    "fallback_signal_extraction": StepConfig(tier="middle"),

    # Layer 6 V2: CV Generation
    "header_generator": StepConfig(tier="middle"),
    "role_generator": StepConfig(tier="middle"),
    "grader": StepConfig(tier="low"),
    "ensemble_header": StepConfig(tier="middle"),
    "improver": StepConfig(tier="high"),

    # Layer 2: Pain Point Miner
    "pain_point_extraction": StepConfig(tier="middle"),

    # Layer 4: Opportunity Mapper
    "fit_analysis": StepConfig(tier="middle"),

    # Layer 3.5: Role Researcher
    "role_research": StepConfig(tier="middle"),

    # Layer 5: People Mapper
    "people_research": StepConfig(tier="middle"),

    # Persona Builder
    "persona_synthesis": StepConfig(tier="high"),

    # ATS Validation
    "ats_validation": StepConfig(tier="low"),

    # JD Processing
    "jd_structure_parsing": StepConfig(tier="low"),
    "jd_extraction": StepConfig(tier="middle"),

    # Cover Letter
    "cover_letter_generation": StepConfig(tier="middle"),

    # LinkedIn
    "linkedin_optimization": StepConfig(tier="middle"),

    # Outreach Generation
    "outreach_generation": StepConfig(tier="high", timeout_seconds=180),
}


def _get_env_override(step_name: str, setting: str) -> Optional[str]:
    """
    Get environment variable override for a step setting.

    Checks for environment variable in format: LLM_{SETTING}_{step_name}
    Example: LLM_TIER_grader, LLM_MODEL_header_generator

    Args:
        step_name: The pipeline step name
        setting: The setting name (TIER, MODEL, FALLBACK_MODEL, TIMEOUT, RETRIES, USE_FALLBACK)

    Returns:
        Environment variable value if set, None otherwise
    """
    env_var = f"LLM_{setting}_{step_name}"
    value = os.getenv(env_var)
    if value:
        logger.debug(f"Using env override {env_var}={value}")
    return value


def get_step_config(step_name: str) -> StepConfig:
    """
    Get configuration for a step, with environment variable overrides.

    First checks for step-specific configuration in STEP_CONFIGS.
    Then applies any environment variable overrides.
    Falls back to default middle-tier config for unknown steps.

    Environment Variable Overrides:
        - LLM_TIER_{step_name}: Override tier (low/middle/high)
        - LLM_MODEL_{step_name}: Override Claude model
        - LLM_FALLBACK_MODEL_{step_name}: Override fallback model
        - LLM_TIMEOUT_{step_name}: Override timeout in seconds
        - LLM_RETRIES_{step_name}: Override max retries
        - LLM_USE_FALLBACK_{step_name}: Override fallback behavior (true/false)

    Args:
        step_name: The pipeline step identifier (e.g., "grader", "header_generator")

    Returns:
        StepConfig with all settings resolved

    Example:
        >>> config = get_step_config("grader")
        >>> config.tier
        'low'
        >>> config.get_claude_model()
        'claude-haiku-4-5-20251001'
    """
    # Start with default config or step-specific config
    base_config = STEP_CONFIGS.get(step_name, StepConfig())

    # Apply environment variable overrides
    tier_override = _get_env_override(step_name, "TIER")
    if tier_override and tier_override in ("low", "middle", "high"):
        base_config.tier = tier_override  # type: ignore

    model_override = _get_env_override(step_name, "MODEL")
    if model_override:
        base_config.claude_model = model_override

    fallback_override = _get_env_override(step_name, "FALLBACK_MODEL")
    if fallback_override:
        base_config.fallback_model = fallback_override

    timeout_override = _get_env_override(step_name, "TIMEOUT")
    if timeout_override:
        try:
            base_config.timeout_seconds = int(timeout_override)
        except ValueError:
            logger.warning(f"Invalid timeout override for {step_name}: {timeout_override}")

    retries_override = _get_env_override(step_name, "RETRIES")
    if retries_override:
        try:
            base_config.max_retries = int(retries_override)
        except ValueError:
            logger.warning(f"Invalid retries override for {step_name}: {retries_override}")

    fallback_enabled = _get_env_override(step_name, "USE_FALLBACK")
    if fallback_enabled is not None:
        base_config.use_fallback = fallback_enabled.lower() == "true"

    return base_config


def get_all_step_configs() -> Dict[str, StepConfig]:
    """
    Get all step configurations with environment overrides applied.

    Useful for debugging or displaying current configuration state.

    Returns:
        Dictionary mapping step names to their resolved StepConfig
    """
    return {name: get_step_config(name) for name in STEP_CONFIGS.keys()}


def get_tier_display_info() -> list:
    """
    Get tier information for UI display.

    Returns:
        List of tier display dictionaries for dropdown rendering
    """
    return [
        {
            "value": "low",
            "label": "Low (Haiku)",
            "model": TIER_TO_CLAUDE_MODEL["low"],
            "description": "Fastest, lowest cost - good for bulk processing",
            "icon": "zap",
            "badge": "~$0.01/op",
        },
        {
            "value": "middle",
            "label": "Middle (Sonnet)",
            "model": TIER_TO_CLAUDE_MODEL["middle"],
            "description": "Best quality/cost ratio - recommended for most tasks",
            "icon": "scale",
            "badge": "~$0.05/op",
        },
        {
            "value": "high",
            "label": "High (Opus)",
            "model": TIER_TO_CLAUDE_MODEL["high"],
            "description": "Highest quality - for critical extractions",
            "icon": "star",
            "badge": "~$0.25/op",
        },
    ]
