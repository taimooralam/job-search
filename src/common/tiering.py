"""
Tiered Job Execution Configuration (GAP-045).

Implements smart resource allocation based on job fit score and user selection.
Each tier defines which LLM models to use for different pipeline operations.

Design Philosophy:
- High-value operations (CV generation, role tailoring) always get premium models
- Analytical operations (research, pain points) use cost-effective models
- Lower tiers skip expensive operations (contacts, full CV) entirely
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Literal
from enum import Enum


class ProcessingTier(str, Enum):
    """Processing tier levels."""

    GOLD = "A"       # 85-100% fit: Full pipeline, premium models
    SILVER = "B"     # 70-84% fit: Full pipeline, mixed models
    BRONZE = "C"     # 50-69% fit: Abbreviated pipeline, economy models
    SKIP = "D"       # <50% fit: Mark as low-fit only, minimal processing
    AUTO = "auto"    # Auto-detect based on fit score (recommended)


@dataclass
class TierConfig:
    """Configuration for a processing tier."""

    tier: ProcessingTier
    description: str

    # Model assignments by operation type
    # High-value operations (CV, roles) - these benefit most from quality
    cv_model: str
    role_model: str

    # Analytical operations - cost-effective models work well
    research_model: str
    pain_points_model: str
    fit_scoring_model: str

    # Contact discovery settings
    max_contacts: int
    discover_contacts: bool

    # CV generation settings
    generate_cv: bool
    use_star_enforcement: bool

    # Outreach settings
    generate_outreach: bool

    # Cost estimate (approx USD per job)
    estimated_cost_usd: float


# Model constants
PREMIUM_MODEL = "gpt-4o"            # Best quality, highest cost
STANDARD_MODEL = "gpt-4o-mini"      # Good balance of quality/cost
ECONOMY_MODEL = "gpt-4o-mini"       # Cost-effective (same as standard for now)

# Claude models for CV generation (when USE_ANTHROPIC=true)
CLAUDE_PREMIUM = "claude-sonnet-4-20250514"
CLAUDE_STANDARD = "claude-3-5-haiku-20241022"


# Tier configurations
TIER_CONFIGS: Dict[ProcessingTier, TierConfig] = {
    ProcessingTier.GOLD: TierConfig(
        tier=ProcessingTier.GOLD,
        description="Full pipeline with premium models - for best-fit jobs",
        cv_model=CLAUDE_PREMIUM,
        role_model=PREMIUM_MODEL,
        research_model=STANDARD_MODEL,
        pain_points_model=STANDARD_MODEL,
        fit_scoring_model=STANDARD_MODEL,
        max_contacts=5,
        discover_contacts=True,
        generate_cv=True,
        use_star_enforcement=True,
        generate_outreach=True,
        estimated_cost_usd=0.50,
    ),
    ProcessingTier.SILVER: TierConfig(
        tier=ProcessingTier.SILVER,
        description="Full pipeline with standard models - for good-fit jobs",
        cv_model=CLAUDE_STANDARD,
        role_model=STANDARD_MODEL,
        research_model=ECONOMY_MODEL,
        pain_points_model=ECONOMY_MODEL,
        fit_scoring_model=ECONOMY_MODEL,
        max_contacts=3,
        discover_contacts=True,
        generate_cv=True,
        use_star_enforcement=True,
        generate_outreach=True,
        estimated_cost_usd=0.25,
    ),
    ProcessingTier.BRONZE: TierConfig(
        tier=ProcessingTier.BRONZE,
        description="Abbreviated pipeline - for moderate-fit jobs",
        cv_model=CLAUDE_STANDARD,
        role_model=ECONOMY_MODEL,
        research_model=ECONOMY_MODEL,
        pain_points_model=ECONOMY_MODEL,
        fit_scoring_model=ECONOMY_MODEL,
        max_contacts=2,
        discover_contacts=False,  # Skip contact discovery
        generate_cv=True,
        use_star_enforcement=False,  # Skip STAR enforcement for speed
        generate_outreach=False,  # Skip outreach generation
        estimated_cost_usd=0.15,
    ),
    ProcessingTier.SKIP: TierConfig(
        tier=ProcessingTier.SKIP,
        description="Minimal processing - marks as low-fit only",
        cv_model="",  # Not used
        role_model="",  # Not used
        research_model=ECONOMY_MODEL,  # Basic research only
        pain_points_model=ECONOMY_MODEL,
        fit_scoring_model=ECONOMY_MODEL,
        max_contacts=0,
        discover_contacts=False,
        generate_cv=False,
        use_star_enforcement=False,
        generate_outreach=False,
        estimated_cost_usd=0.05,
    ),
}


def get_tier_from_fit_score(fit_score: Optional[int]) -> ProcessingTier:
    """
    Determine processing tier based on fit score.

    Args:
        fit_score: Job fit score (0-100) or None if not yet scored

    Returns:
        Appropriate ProcessingTier based on score thresholds
    """
    if fit_score is None:
        # No score yet - use Silver as default (middle ground)
        return ProcessingTier.SILVER

    if fit_score >= 85:
        return ProcessingTier.GOLD
    elif fit_score >= 70:
        return ProcessingTier.SILVER
    elif fit_score >= 50:
        return ProcessingTier.BRONZE
    else:
        return ProcessingTier.SKIP


def get_tier_config(tier: ProcessingTier) -> TierConfig:
    """
    Get configuration for a processing tier.

    Args:
        tier: The processing tier

    Returns:
        TierConfig with model assignments and settings
    """
    if tier == ProcessingTier.AUTO:
        # AUTO defaults to SILVER until fit score is determined
        return TIER_CONFIGS[ProcessingTier.SILVER]
    return TIER_CONFIGS[tier]


def resolve_tier(
    requested_tier: Optional[str],
    fit_score: Optional[int] = None
) -> ProcessingTier:
    """
    Resolve the final processing tier from request and fit score.

    Args:
        requested_tier: User-specified tier or "auto"
        fit_score: Job fit score if available

    Returns:
        Resolved ProcessingTier
    """
    if requested_tier is None or requested_tier.lower() == "auto":
        return get_tier_from_fit_score(fit_score)

    # Map string to enum
    tier_map = {
        "a": ProcessingTier.GOLD,
        "b": ProcessingTier.SILVER,
        "c": ProcessingTier.BRONZE,
        "d": ProcessingTier.SKIP,
        "gold": ProcessingTier.GOLD,
        "silver": ProcessingTier.SILVER,
        "bronze": ProcessingTier.BRONZE,
        "skip": ProcessingTier.SKIP,
    }

    return tier_map.get(requested_tier.lower(), ProcessingTier.SILVER)


def get_tier_display_info() -> list:
    """
    Get tier information for UI display.

    Returns:
        List of tier display dictionaries for dropdown rendering
    """
    return [
        {
            "value": "auto",
            "label": "Recommended (Auto)",
            "description": "Automatically select tier based on fit score",
            "icon": "sparkles",
        },
        {
            "value": "A",
            "label": "Gold (Tier A)",
            "description": "Premium models, full pipeline, 5 contacts",
            "icon": "star",
            "badge": "Best Quality",
        },
        {
            "value": "B",
            "label": "Silver (Tier B)",
            "description": "Standard models, full pipeline, 3 contacts",
            "icon": "check-circle",
            "badge": "Balanced",
        },
        {
            "value": "C",
            "label": "Bronze (Tier C)",
            "description": "Economy models, abbreviated pipeline",
            "icon": "clock",
            "badge": "Fast",
        },
        {
            "value": "D",
            "label": "Skip (Tier D)",
            "description": "Minimal processing, marks as low-fit only",
            "icon": "x-circle",
            "badge": "Minimal",
        },
    ]
