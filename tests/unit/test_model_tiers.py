"""
Unit tests for src/common/model_tiers.py

Tests the 3-tier model system for button-triggered pipeline operations.
"""

import pytest

from src.common.model_tiers import (
    ModelTier,
    TierModelConfig,
    TIER_CONFIGS,
    OPERATION_TASK_TYPES,
    get_model_for_operation,
    get_tier_cost_estimate,
    get_tier_from_string,
    get_tier_display_info,
)


class TestModelTierEnum:
    """Tests for ModelTier enum."""

    def test_has_three_tiers(self):
        """Should have exactly three tiers."""
        assert len(ModelTier) == 3

    def test_tier_values(self):
        """Should have correct string values."""
        assert ModelTier.FAST.value == "fast"
        assert ModelTier.BALANCED.value == "balanced"
        assert ModelTier.QUALITY.value == "quality"

    def test_is_string_enum(self):
        """Should be a string enum for easy serialization."""
        assert isinstance(ModelTier.FAST, str)
        assert ModelTier.FAST == "fast"

    def test_can_compare_with_string(self):
        """Should allow comparison with string values."""
        assert ModelTier.FAST == "fast"
        assert ModelTier.BALANCED == "balanced"
        assert ModelTier.QUALITY == "quality"


class TestTierModelConfig:
    """Tests for TierModelConfig dataclass."""

    def test_stores_all_fields(self):
        """Should store all required fields."""
        config = TierModelConfig(
            tier=ModelTier.FAST,
            complex_model="test-complex",
            analytical_model="test-analytical",
            simple_model="test-simple",
            cost_per_1k_input=0.001,
            cost_per_1k_output=0.002,
        )

        assert config.tier == ModelTier.FAST
        assert config.complex_model == "test-complex"
        assert config.analytical_model == "test-analytical"
        assert config.simple_model == "test-simple"
        assert config.cost_per_1k_input == 0.001
        assert config.cost_per_1k_output == 0.002


class TestTierConfigs:
    """Tests for TIER_CONFIGS dictionary."""

    def test_has_all_tiers(self):
        """Should have config for all three tiers."""
        assert ModelTier.FAST in TIER_CONFIGS
        assert ModelTier.BALANCED in TIER_CONFIGS
        assert ModelTier.QUALITY in TIER_CONFIGS

    def test_fast_tier_uses_mini_models(self):
        """Fast tier should use gpt-4o-mini for all operations."""
        config = TIER_CONFIGS[ModelTier.FAST]

        assert config.complex_model == "gpt-4o-mini"
        assert config.analytical_model == "gpt-4o-mini"
        assert config.simple_model == "gpt-4o-mini"

    def test_balanced_tier_mixes_models(self):
        """Balanced tier should use gpt-4o for complex, mini for others."""
        config = TIER_CONFIGS[ModelTier.BALANCED]

        assert config.complex_model == "gpt-4o"
        assert config.analytical_model == "gpt-4o-mini"
        assert config.simple_model == "gpt-4o-mini"

    def test_quality_tier_uses_best_models(self):
        """Quality tier should use Claude Sonnet for complex, gpt-4o for analytical."""
        config = TIER_CONFIGS[ModelTier.QUALITY]

        assert config.complex_model == "claude-opus-4-5-20251101"
        assert config.analytical_model == "gpt-4o"
        assert config.simple_model == "gpt-4o-mini"

    def test_fast_tier_has_lowest_cost(self):
        """Fast tier should have lowest cost per token."""
        fast_config = TIER_CONFIGS[ModelTier.FAST]
        balanced_config = TIER_CONFIGS[ModelTier.BALANCED]
        quality_config = TIER_CONFIGS[ModelTier.QUALITY]

        assert fast_config.cost_per_1k_input < balanced_config.cost_per_1k_input
        assert fast_config.cost_per_1k_input < quality_config.cost_per_1k_input

        assert fast_config.cost_per_1k_output < balanced_config.cost_per_1k_output
        assert fast_config.cost_per_1k_output < quality_config.cost_per_1k_output

    def test_quality_tier_has_highest_cost(self):
        """Quality tier should have highest cost per token."""
        balanced_config = TIER_CONFIGS[ModelTier.BALANCED]
        quality_config = TIER_CONFIGS[ModelTier.QUALITY]

        assert quality_config.cost_per_1k_input > balanced_config.cost_per_1k_input
        assert quality_config.cost_per_1k_output > balanced_config.cost_per_1k_output

    def test_all_configs_have_positive_costs(self):
        """All tier configs should have positive cost values."""
        for tier, config in TIER_CONFIGS.items():
            assert config.cost_per_1k_input > 0, f"{tier} has non-positive input cost"
            assert config.cost_per_1k_output > 0, f"{tier} has non-positive output cost"


class TestOperationTaskTypes:
    """Tests for OPERATION_TASK_TYPES mapping."""

    def test_has_expected_operations(self):
        """Should have all expected operation mappings."""
        expected_operations = [
            "structure-jd",
            "research-company",
            "research-role",
            "generate-cv",
            "generate-linkedin",
            "generate-email",
            "validate",
        ]

        for op in expected_operations:
            assert op in OPERATION_TASK_TYPES, f"Missing operation: {op}"

    def test_cv_generation_is_complex(self):
        """CV generation should be a complex task."""
        assert OPERATION_TASK_TYPES["generate-cv"] == "complex"

    def test_linkedin_generation_is_complex(self):
        """LinkedIn optimization should be a complex task."""
        assert OPERATION_TASK_TYPES["generate-linkedin"] == "complex"

    def test_email_generation_is_complex(self):
        """Email generation should be a complex task."""
        assert OPERATION_TASK_TYPES["generate-email"] == "complex"

    def test_research_operations_are_analytical(self):
        """Research operations should be analytical tasks."""
        assert OPERATION_TASK_TYPES["research-company"] == "analytical"
        assert OPERATION_TASK_TYPES["research-role"] == "analytical"

    def test_structure_jd_is_analytical(self):
        """JD structuring should be an analytical task."""
        assert OPERATION_TASK_TYPES["structure-jd"] == "analytical"

    def test_validate_is_simple(self):
        """Validation should be a simple task."""
        assert OPERATION_TASK_TYPES["validate"] == "simple"

    def test_all_task_types_are_valid(self):
        """All task types should be one of: complex, analytical, simple."""
        valid_types = {"complex", "analytical", "simple"}

        for op, task_type in OPERATION_TASK_TYPES.items():
            assert task_type in valid_types, f"Invalid task type for {op}: {task_type}"


class TestGetModelForOperation:
    """Tests for get_model_for_operation function."""

    def test_returns_complex_model_for_cv_generation(self):
        """Should return complex model for CV generation."""
        assert get_model_for_operation(ModelTier.FAST, "generate-cv") == "gpt-4o-mini"
        assert get_model_for_operation(ModelTier.BALANCED, "generate-cv") == "gpt-4o"
        assert (
            get_model_for_operation(ModelTier.QUALITY, "generate-cv")
            == "claude-opus-4-5-20251101"
        )

    def test_returns_analytical_model_for_research(self):
        """Should return analytical model for research operations."""
        assert (
            get_model_for_operation(ModelTier.FAST, "research-company") == "gpt-4o-mini"
        )
        assert (
            get_model_for_operation(ModelTier.BALANCED, "research-company")
            == "gpt-4o-mini"
        )
        assert (
            get_model_for_operation(ModelTier.QUALITY, "research-company") == "gpt-4o"
        )

    def test_returns_simple_model_for_validation(self):
        """Should return simple model for validation."""
        assert get_model_for_operation(ModelTier.FAST, "validate") == "gpt-4o-mini"
        assert get_model_for_operation(ModelTier.BALANCED, "validate") == "gpt-4o-mini"
        assert get_model_for_operation(ModelTier.QUALITY, "validate") == "gpt-4o-mini"

    def test_unknown_operation_defaults_to_analytical(self):
        """Unknown operations should default to analytical model."""
        # Unknown operation should fall back to analytical
        assert (
            get_model_for_operation(ModelTier.FAST, "unknown-operation")
            == "gpt-4o-mini"
        )
        assert (
            get_model_for_operation(ModelTier.BALANCED, "unknown-operation")
            == "gpt-4o-mini"
        )
        assert (
            get_model_for_operation(ModelTier.QUALITY, "unknown-operation") == "gpt-4o"
        )

    def test_all_tiers_return_non_empty_model(self):
        """All tiers should return non-empty model names."""
        for tier in ModelTier:
            for operation in OPERATION_TASK_TYPES.keys():
                model = get_model_for_operation(tier, operation)
                assert model, f"Empty model for {tier}/{operation}"


class TestGetTierCostEstimate:
    """Tests for get_tier_cost_estimate function."""

    def test_zero_tokens_returns_zero_cost(self):
        """Zero tokens should return zero cost."""
        assert get_tier_cost_estimate(ModelTier.FAST, 0, 0) == 0.0
        assert get_tier_cost_estimate(ModelTier.BALANCED, 0, 0) == 0.0
        assert get_tier_cost_estimate(ModelTier.QUALITY, 0, 0) == 0.0

    def test_cost_increases_with_tokens(self):
        """Cost should increase proportionally with token count."""
        cost_1k = get_tier_cost_estimate(ModelTier.FAST, 1000, 1000)
        cost_2k = get_tier_cost_estimate(ModelTier.FAST, 2000, 2000)

        assert cost_2k == pytest.approx(cost_1k * 2)

    def test_fast_tier_is_cheapest(self):
        """Fast tier should have lowest cost for same token counts."""
        fast_cost = get_tier_cost_estimate(ModelTier.FAST, 1000, 500)
        balanced_cost = get_tier_cost_estimate(ModelTier.BALANCED, 1000, 500)
        quality_cost = get_tier_cost_estimate(ModelTier.QUALITY, 1000, 500)

        assert fast_cost < balanced_cost
        assert fast_cost < quality_cost

    def test_quality_tier_is_most_expensive(self):
        """Quality tier should have highest cost for same token counts."""
        balanced_cost = get_tier_cost_estimate(ModelTier.BALANCED, 1000, 500)
        quality_cost = get_tier_cost_estimate(ModelTier.QUALITY, 1000, 500)

        assert quality_cost > balanced_cost

    def test_output_tokens_cost_more_than_input(self):
        """Output tokens should cost more than input tokens."""
        for tier in ModelTier:
            config = TIER_CONFIGS[tier]
            assert (
                config.cost_per_1k_output > config.cost_per_1k_input
            ), f"{tier} output cost should exceed input cost"

    def test_cost_calculation_accuracy(self):
        """Cost calculation should be mathematically correct."""
        # Fast tier: 0.00015/1k input, 0.0006/1k output
        config = TIER_CONFIGS[ModelTier.FAST]
        input_tokens = 1000
        output_tokens = 500

        expected_cost = (input_tokens / 1000) * config.cost_per_1k_input + (
            output_tokens / 1000
        ) * config.cost_per_1k_output
        actual_cost = get_tier_cost_estimate(ModelTier.FAST, input_tokens, output_tokens)

        assert actual_cost == pytest.approx(expected_cost)

    def test_typical_operation_cost_estimate(self):
        """Test realistic token counts produce reasonable costs."""
        # Typical CV generation: ~3000 input, ~2000 output
        fast_cost = get_tier_cost_estimate(ModelTier.FAST, 3000, 2000)
        quality_cost = get_tier_cost_estimate(ModelTier.QUALITY, 3000, 2000)

        # Fast should be around $0.001-$0.005
        assert 0.0001 < fast_cost < 0.01

        # Quality (Opus 4.5) should be around $0.15-$0.25
        assert 0.10 < quality_cost < 0.30


class TestGetTierFromString:
    """Tests for get_tier_from_string function."""

    def test_converts_fast(self):
        """Should convert 'fast' to ModelTier.FAST."""
        assert get_tier_from_string("fast") == ModelTier.FAST

    def test_converts_balanced(self):
        """Should convert 'balanced' to ModelTier.BALANCED."""
        assert get_tier_from_string("balanced") == ModelTier.BALANCED

    def test_converts_quality(self):
        """Should convert 'quality' to ModelTier.QUALITY."""
        assert get_tier_from_string("quality") == ModelTier.QUALITY

    def test_case_insensitive(self):
        """Should be case insensitive."""
        assert get_tier_from_string("FAST") == ModelTier.FAST
        assert get_tier_from_string("Fast") == ModelTier.FAST
        assert get_tier_from_string("BALANCED") == ModelTier.BALANCED
        assert get_tier_from_string("Quality") == ModelTier.QUALITY

    def test_invalid_string_returns_none(self):
        """Should return None for invalid tier strings."""
        assert get_tier_from_string("invalid") is None
        assert get_tier_from_string("") is None
        assert get_tier_from_string("premium") is None
        assert get_tier_from_string("economy") is None


class TestGetTierDisplayInfo:
    """Tests for get_tier_display_info function."""

    def test_returns_list(self):
        """Should return a list."""
        info = get_tier_display_info()
        assert isinstance(info, list)

    def test_has_three_entries(self):
        """Should have exactly three entries for three tiers."""
        info = get_tier_display_info()
        assert len(info) == 3

    def test_all_entries_have_required_fields(self):
        """All entries should have required display fields."""
        info = get_tier_display_info()
        required_fields = {"value", "label", "description", "icon", "badge"}

        for entry in info:
            for field in required_fields:
                assert field in entry, f"Missing field: {field}"

    def test_values_match_tier_values(self):
        """Display values should match ModelTier values."""
        info = get_tier_display_info()
        values = {entry["value"] for entry in info}

        assert "fast" in values
        assert "balanced" in values
        assert "quality" in values

    def test_labels_are_user_friendly(self):
        """Labels should be user-friendly strings."""
        info = get_tier_display_info()

        for entry in info:
            label = entry["label"]
            assert isinstance(label, str)
            assert len(label) > 0
            # Labels should be capitalized
            assert label[0].isupper()

    def test_badges_show_cost_estimates(self):
        """Badges should show cost estimates."""
        info = get_tier_display_info()

        for entry in info:
            badge = entry["badge"]
            assert "$" in badge or "op" in badge.lower()


class TestModelTierIntegration:
    """Integration tests for the model tier system."""

    def test_full_operation_flow(self):
        """Test selecting model and estimating cost for a full operation."""
        tier = ModelTier.BALANCED
        operation = "generate-cv"

        # Get model
        model = get_model_for_operation(tier, operation)
        assert model == "gpt-4o"

        # Estimate cost
        cost = get_tier_cost_estimate(tier, 3000, 2000)
        assert cost > 0

    def test_tier_selection_from_user_input(self):
        """Test converting user input to tier and using it."""
        user_input = "quality"

        tier = get_tier_from_string(user_input)
        assert tier == ModelTier.QUALITY

        model = get_model_for_operation(tier, "generate-cv")
        assert model == "claude-opus-4-5-20251101"

    def test_display_info_matches_actual_tiers(self):
        """Display info should accurately represent actual tier configurations."""
        info = get_tier_display_info()

        for entry in info:
            tier_value = entry["value"]
            tier = get_tier_from_string(tier_value)

            assert tier is not None, f"Display value {tier_value} doesn't map to tier"
            assert tier in TIER_CONFIGS, f"Tier {tier} not in configs"
