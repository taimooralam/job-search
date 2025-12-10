"""
Model Tier System for Button-Triggered Pipeline Operations

Provides Fast/Balanced/Quality tier selection for independent operations.
Each tier maps to specific models for different task types.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


class ModelTier(str, Enum):
    """Model quality tiers for operation execution."""

    FAST = "fast"  # Cheapest, fastest - ~$0.02/op
    BALANCED = "balanced"  # Good quality/cost tradeoff - ~$0.05/op
    QUALITY = "quality"  # Best quality, highest cost - ~$0.15/op


@dataclass
class TierModelConfig:
    """Model assignments for each tier."""

    tier: ModelTier
    complex_model: str  # CV generation, outreach
    analytical_model: str  # Research, extraction
    simple_model: str  # Validation, parsing
    cost_per_1k_input: float
    cost_per_1k_output: float


TIER_CONFIGS: Dict[ModelTier, TierModelConfig] = {
    ModelTier.FAST: TierModelConfig(
        tier=ModelTier.FAST,
        complex_model="gpt-4o-mini",
        analytical_model="gpt-4o-mini",
        simple_model="gpt-4o-mini",
        cost_per_1k_input=0.00015,
        cost_per_1k_output=0.0006,
    ),
    ModelTier.BALANCED: TierModelConfig(
        tier=ModelTier.BALANCED,
        complex_model="gpt-4o",
        analytical_model="gpt-4o-mini",
        simple_model="gpt-4o-mini",
        cost_per_1k_input=0.00125,
        cost_per_1k_output=0.005,
    ),
    ModelTier.QUALITY: TierModelConfig(
        tier=ModelTier.QUALITY,
        complex_model="claude-sonnet-4-20250514",
        analytical_model="gpt-4o",
        simple_model="gpt-4o-mini",
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
    ),
}

# Operation to task type mapping
OPERATION_TASK_TYPES: Dict[str, str] = {
    "structure-jd": "analytical",
    "research-company": "analytical",
    "research-role": "analytical",
    "generate-cv": "complex",
    "generate-linkedin": "complex",
    "generate-email": "complex",
    "validate": "simple",
}


def get_model_for_operation(tier: ModelTier, operation: str) -> str:
    """
    Get the appropriate model for an operation based on tier.

    Args:
        tier: The model tier (FAST, BALANCED, or QUALITY)
        operation: The operation name (e.g., "generate-cv", "research-company")

    Returns:
        Model name string appropriate for the tier and operation type
    """
    config = TIER_CONFIGS[tier]
    task_type = OPERATION_TASK_TYPES.get(operation, "analytical")

    if task_type == "complex":
        return config.complex_model
    elif task_type == "simple":
        return config.simple_model
    else:
        return config.analytical_model


def get_tier_cost_estimate(
    tier: ModelTier, input_tokens: int, output_tokens: int
) -> float:
    """
    Estimate cost for token usage at given tier.

    Args:
        tier: The model tier
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens

    Returns:
        Estimated cost in USD
    """
    config = TIER_CONFIGS[tier]
    input_cost = (input_tokens / 1000) * config.cost_per_1k_input
    output_cost = (output_tokens / 1000) * config.cost_per_1k_output
    return input_cost + output_cost


def get_tier_from_string(tier_str: str) -> Optional[ModelTier]:
    """
    Convert a string to ModelTier enum.

    Args:
        tier_str: String representation of tier ("fast", "balanced", "quality")

    Returns:
        ModelTier enum value or None if invalid
    """
    tier_map = {
        "fast": ModelTier.FAST,
        "balanced": ModelTier.BALANCED,
        "quality": ModelTier.QUALITY,
    }
    return tier_map.get(tier_str.lower())


def get_tier_display_info() -> list:
    """
    Get tier information for UI display.

    Returns:
        List of tier display dictionaries for dropdown rendering
    """
    return [
        {
            "value": "fast",
            "label": "Fast",
            "description": "Cheapest, fastest - uses gpt-4o-mini for all tasks",
            "icon": "zap",
            "badge": "~$0.02/op",
        },
        {
            "value": "balanced",
            "label": "Balanced",
            "description": "Good quality/cost tradeoff - gpt-4o for complex, mini for simple",
            "icon": "scale",
            "badge": "~$0.05/op",
        },
        {
            "value": "quality",
            "label": "Quality",
            "description": "Best quality - Claude Sonnet for complex, gpt-4o for analytical",
            "icon": "star",
            "badge": "~$0.15/op",
        },
    ]
