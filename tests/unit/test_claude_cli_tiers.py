"""
Unit tests for claude_cli.py tier system (low/middle/high).

Tests verify that the three-tier system uses consistent naming:
- Tier naming: low/middle/high
- TierType literal
- Model mappings
- Cost mappings
- Display info
- Backward compatibility with legacy names (fast/balanced/quality)
"""

import pytest
from typing import Literal

from src.common.claude_cli import (
    CLAUDE_MODEL_TIERS,
    DEFAULT_BATCH_TIER,
    CLAUDE_TIER_COSTS,
    TIER_ALIASES,
    TierType,
    ClaudeCLI,
)


class TestTierTypeNaming:
    """Tests for TierType literal and naming conventions."""

    def test_tier_type_literal_accepts_valid_tiers(self):
        """TierType should accept low, middle, high."""
        tier1: TierType = "low"
        tier2: TierType = "middle"
        tier3: TierType = "high"

        assert tier1 == "low"
        assert tier2 == "middle"
        assert tier3 == "high"

    def test_tier_type_literal_definition(self):
        """TierType should be defined as Literal with three values."""
        import typing

        tier_args = typing.get_args(TierType)

        assert len(tier_args) == 3
        assert "low" in tier_args
        assert "middle" in tier_args
        assert "high" in tier_args


class TestModelTiersKeys:
    """Tests for CLAUDE_MODEL_TIERS dictionary keys."""

    def test_model_tiers_has_all_tier_keys(self):
        """CLAUDE_MODEL_TIERS should use low/middle/high keys."""
        assert "low" in CLAUDE_MODEL_TIERS
        assert "middle" in CLAUDE_MODEL_TIERS
        assert "high" in CLAUDE_MODEL_TIERS

    def test_model_tiers_only_has_valid_keys(self):
        """CLAUDE_MODEL_TIERS should only have the three tier keys."""
        valid_keys = {"low", "middle", "high"}
        assert set(CLAUDE_MODEL_TIERS.keys()) == valid_keys

    def test_low_tier_maps_to_haiku(self):
        """Low tier should map to Claude Haiku."""
        model = CLAUDE_MODEL_TIERS["low"]
        assert "haiku" in model.lower()

    def test_middle_tier_maps_to_sonnet(self):
        """Middle tier should map to Claude Sonnet (default)."""
        model = CLAUDE_MODEL_TIERS["middle"]
        assert "sonnet" in model.lower()

    def test_high_tier_maps_to_opus(self):
        """High tier should map to Claude Opus."""
        model = CLAUDE_MODEL_TIERS["high"]
        assert "opus" in model.lower()

    def test_all_models_are_valid_claude_ids(self):
        """All tier models should be valid Claude model IDs."""
        for tier, model in CLAUDE_MODEL_TIERS.items():
            assert isinstance(model, str)
            assert model.startswith("claude-")
            assert len(model) > 15  # Reasonable model ID length


class TestDefaultBatchTier:
    """Tests for DEFAULT_BATCH_TIER constant."""

    def test_default_batch_tier_is_middle(self):
        """DEFAULT_BATCH_TIER should be 'middle' (Sonnet)."""
        assert DEFAULT_BATCH_TIER == "middle"

    def test_default_batch_tier_is_valid(self):
        """DEFAULT_BATCH_TIER should be a valid tier."""
        assert DEFAULT_BATCH_TIER in CLAUDE_MODEL_TIERS


class TestTierCostsKeys:
    """Tests for CLAUDE_TIER_COSTS dictionary keys."""

    def test_tier_costs_has_all_tier_keys(self):
        """CLAUDE_TIER_COSTS should use low/middle/high keys."""
        assert "low" in CLAUDE_TIER_COSTS
        assert "middle" in CLAUDE_TIER_COSTS
        assert "high" in CLAUDE_TIER_COSTS

    def test_tier_costs_only_has_valid_keys(self):
        """CLAUDE_TIER_COSTS should only have the three tier keys."""
        valid_keys = {"low", "middle", "high"}
        assert set(CLAUDE_TIER_COSTS.keys()) == valid_keys

    def test_each_tier_has_input_output_costs(self):
        """Each tier should have input and output cost values."""
        for tier, costs in CLAUDE_TIER_COSTS.items():
            assert "input" in costs
            assert "output" in costs
            assert isinstance(costs["input"], (int, float))
            assert isinstance(costs["output"], (int, float))
            assert costs["input"] > 0
            assert costs["output"] > 0

    def test_costs_increase_with_tier_quality(self):
        """Costs should increase: low < middle < high."""
        low_input = CLAUDE_TIER_COSTS["low"]["input"]
        middle_input = CLAUDE_TIER_COSTS["middle"]["input"]
        high_input = CLAUDE_TIER_COSTS["high"]["input"]

        assert low_input < middle_input < high_input

        low_output = CLAUDE_TIER_COSTS["low"]["output"]
        middle_output = CLAUDE_TIER_COSTS["middle"]["output"]
        high_output = CLAUDE_TIER_COSTS["high"]["output"]

        assert low_output < middle_output < high_output

    def test_output_costs_higher_than_input(self):
        """Output costs should be higher than input costs for all tiers."""
        for tier, costs in CLAUDE_TIER_COSTS.items():
            assert costs["output"] > costs["input"], \
                f"{tier} tier: output cost should be > input cost"


class TestTierDisplayInfo:
    """Tests for get_tier_display_info() tier values."""

    def test_tier_display_info_returns_all_tiers(self):
        """get_tier_display_info() should return low/middle/high."""
        tier_info = ClaudeCLI.get_tier_display_info()

        assert len(tier_info) == 3

        tier_values = [t["value"] for t in tier_info]
        assert "low" in tier_values
        assert "middle" in tier_values
        assert "high" in tier_values

    def test_tier_display_info_structure(self):
        """Each tier info should have required fields."""
        tier_info = ClaudeCLI.get_tier_display_info()

        for tier in tier_info:
            assert "value" in tier
            assert "label" in tier
            assert "model" in tier
            assert "description" in tier
            assert tier["value"] in ["low", "middle", "high"]

    def test_low_tier_display_info(self):
        """Low tier should have Haiku info."""
        tier_info = ClaudeCLI.get_tier_display_info()
        low_tier = next(t for t in tier_info if t["value"] == "low")

        assert "low" in low_tier["label"].lower()
        assert "haiku" in low_tier["model"].lower()

    def test_middle_tier_display_info(self):
        """Middle tier should have Sonnet info."""
        tier_info = ClaudeCLI.get_tier_display_info()
        middle_tier = next(t for t in tier_info if t["value"] == "middle")

        assert "middle" in middle_tier["label"].lower()
        assert "sonnet" in middle_tier["model"].lower()

    def test_high_tier_display_info(self):
        """High tier should have Opus info."""
        tier_info = ClaudeCLI.get_tier_display_info()
        high_tier = next(t for t in tier_info if t["value"] == "high")

        assert "high" in high_tier["label"].lower()
        assert "opus" in high_tier["model"].lower()


class TestClaudeCLITierUsage:
    """Tests for ClaudeCLI using tier names."""

    def test_cli_init_accepts_low_tier(self):
        """ClaudeCLI should accept 'low' tier."""
        cli = ClaudeCLI(tier="low")
        assert cli.tier == "low"
        assert cli.model == CLAUDE_MODEL_TIERS["low"]

    def test_cli_init_accepts_middle_tier(self):
        """ClaudeCLI should accept 'middle' tier."""
        cli = ClaudeCLI(tier="middle")
        assert cli.tier == "middle"
        assert cli.model == CLAUDE_MODEL_TIERS["middle"]

    def test_cli_init_accepts_high_tier(self):
        """ClaudeCLI should accept 'high' tier."""
        cli = ClaudeCLI(tier="high")
        assert cli.tier == "high"
        assert cli.model == CLAUDE_MODEL_TIERS["high"]

    def test_cli_default_tier_is_middle(self):
        """ClaudeCLI should default to 'middle' tier."""
        cli = ClaudeCLI()
        assert cli.tier == "middle"

    def test_cli_get_tier_cost_estimate_uses_tier_names(self):
        """get_tier_cost_estimate() should accept tier names."""
        low_cost = ClaudeCLI.get_tier_cost_estimate(
            tier="low",
            input_tokens=1000,
            output_tokens=500
        )
        assert low_cost > 0

        middle_cost = ClaudeCLI.get_tier_cost_estimate(
            tier="middle",
            input_tokens=1000,
            output_tokens=500
        )
        assert middle_cost > low_cost

        high_cost = ClaudeCLI.get_tier_cost_estimate(
            tier="high",
            input_tokens=1000,
            output_tokens=500
        )
        assert high_cost > middle_cost


class TestBackwardCompatibility:
    """Tests for backward compatibility with legacy tier names."""

    def test_tier_aliases_exist(self):
        """TIER_ALIASES should map legacy names to new names."""
        assert "fast" in TIER_ALIASES
        assert "balanced" in TIER_ALIASES
        assert "quality" in TIER_ALIASES

    def test_tier_aliases_map_correctly(self):
        """Legacy names should map to correct new names."""
        assert TIER_ALIASES["fast"] == "low"
        assert TIER_ALIASES["balanced"] == "middle"
        assert TIER_ALIASES["quality"] == "high"

    def test_cli_accepts_legacy_fast_tier(self):
        """ClaudeCLI should accept legacy 'fast' tier."""
        cli = ClaudeCLI(tier="fast")
        assert cli.tier == "low"  # Converted to new name
        assert cli.model == CLAUDE_MODEL_TIERS["low"]

    def test_cli_accepts_legacy_balanced_tier(self):
        """ClaudeCLI should accept legacy 'balanced' tier."""
        cli = ClaudeCLI(tier="balanced")
        assert cli.tier == "middle"  # Converted to new name

    def test_cli_accepts_legacy_quality_tier(self):
        """ClaudeCLI should accept legacy 'quality' tier."""
        cli = ClaudeCLI(tier="quality")
        assert cli.tier == "high"  # Converted to new name

    def test_cost_estimate_accepts_legacy_names(self):
        """get_tier_cost_estimate should accept legacy tier names."""
        fast_cost = ClaudeCLI.get_tier_cost_estimate(
            tier="fast",
            input_tokens=1000,
            output_tokens=500
        )
        low_cost = ClaudeCLI.get_tier_cost_estimate(
            tier="low",
            input_tokens=1000,
            output_tokens=500
        )
        assert fast_cost == low_cost


class TestTierNamingConsistency:
    """Tests for consistency across all tier-related constants."""

    def test_all_constants_use_same_tier_keys(self):
        """All tier-related constants should use low/middle/high keys."""
        tier_keys = set(CLAUDE_MODEL_TIERS.keys())
        cost_keys = set(CLAUDE_TIER_COSTS.keys())
        display_keys = {t["value"] for t in ClaudeCLI.get_tier_display_info()}

        assert tier_keys == cost_keys == display_keys == {"low", "middle", "high"}

    def test_new_tier_names_in_source(self):
        """Should use new tier names (low/middle/high) in source."""
        import inspect
        import src.common.claude_cli as cli_module

        source = inspect.getsource(cli_module)

        # Check that we're using low/middle/high
        assert '"low"' in source
        assert '"middle"' in source
        assert '"high"' in source


class TestTierDocumentation:
    """Tests for tier documentation and help text."""

    def test_module_docstring_mentions_tiers(self):
        """Module docstring should document tier system."""
        import src.common.claude_cli as cli_module

        docstring = cli_module.__doc__
        assert docstring is not None

        docstring_lower = docstring.lower()
        has_tier_info = (
            "low" in docstring_lower or
            "middle" in docstring_lower or
            "high" in docstring_lower or
            "haiku" in docstring_lower or
            "sonnet" in docstring_lower or
            "opus" in docstring_lower
        )
        assert has_tier_info

    def test_tier_type_has_documentation(self):
        """TierType should be well-documented."""
        import src.common.claude_cli

        assert hasattr(src.common.claude_cli, "TierType")
        assert src.common.claude_cli.TierType is not None


class TestConstantsImport:
    """Tests to ensure API stability."""

    def test_tier_type_is_importable(self):
        """TierType should be importable from claude_cli."""
        from src.common.claude_cli import TierType
        assert TierType is not None

    def test_tier_constants_are_importable(self):
        """All tier-related constants should be importable."""
        from src.common.claude_cli import (
            CLAUDE_MODEL_TIERS,
            DEFAULT_BATCH_TIER,
            CLAUDE_TIER_COSTS,
            TIER_ALIASES,
        )

        assert CLAUDE_MODEL_TIERS is not None
        assert DEFAULT_BATCH_TIER is not None
        assert CLAUDE_TIER_COSTS is not None
        assert TIER_ALIASES is not None

    def test_claude_cli_tier_parameter(self):
        """ClaudeCLI should accept tier parameter in __init__."""
        import inspect
        from src.common.claude_cli import ClaudeCLI

        init_signature = inspect.signature(ClaudeCLI.__init__)
        assert "tier" in init_signature.parameters

    def test_get_tier_cost_estimate_signature(self):
        """get_tier_cost_estimate should have correct signature."""
        import inspect

        sig = inspect.signature(ClaudeCLI.get_tier_cost_estimate)
        params = sig.parameters

        assert "tier" in params
        assert "input_tokens" in params
        assert "output_tokens" in params
