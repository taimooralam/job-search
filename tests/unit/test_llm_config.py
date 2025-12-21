"""
Unit tests for src/common/llm_config.py

Tests the per-step LLM configuration system including:
- StepConfig dataclass
- STEP_CONFIGS mapping
- get_step_config function with env var overrides
- Tier mappings
"""

import pytest
import os
from unittest.mock import patch
from dataclasses import asdict


class TestStepConfigDataclass:
    """Tests for StepConfig dataclass."""

    def test_step_config_default_values(self):
        """StepConfig should have sensible defaults for middle tier."""
        from src.common.llm_config import StepConfig

        config = StepConfig()

        assert config.tier == "middle"
        assert config.use_fallback is True
        assert config.timeout_seconds == 120
        assert config.max_retries == 2

    def test_step_config_accepts_all_tiers(self):
        """StepConfig should accept low, middle, and high tiers."""
        from src.common.llm_config import StepConfig

        low_config = StepConfig(tier="low")
        assert low_config.tier == "low"

        middle_config = StepConfig(tier="middle")
        assert middle_config.tier == "middle"

        high_config = StepConfig(tier="high")
        assert high_config.tier == "high"

    def test_step_config_get_claude_model(self):
        """StepConfig should return correct Claude model for tier."""
        from src.common.llm_config import StepConfig

        low = StepConfig(tier="low")
        assert "haiku" in low.get_claude_model().lower()

        middle = StepConfig(tier="middle")
        assert "sonnet" in middle.get_claude_model().lower()

        high = StepConfig(tier="high")
        assert "opus" in high.get_claude_model().lower()

    def test_step_config_get_fallback_model(self):
        """StepConfig should return correct fallback model for tier."""
        from src.common.llm_config import StepConfig

        low = StepConfig(tier="low")
        assert "gpt-4o-mini" in low.get_fallback_model()

        middle = StepConfig(tier="middle")
        assert "gpt-4o" in middle.get_fallback_model()

    def test_step_config_with_model_override(self):
        """StepConfig should allow model overrides."""
        from src.common.llm_config import StepConfig

        config = StepConfig(
            tier="middle",
            claude_model="custom-model-id"
        )

        assert config.get_claude_model() == "custom-model-id"

    def test_step_config_serialization(self):
        """StepConfig should be serializable to dict."""
        from src.common.llm_config import StepConfig

        config = StepConfig(tier="high")
        config_dict = asdict(config)

        assert config_dict["tier"] == "high"
        assert config_dict["use_fallback"] is True


class TestStepConfigsMapping:
    """Tests for STEP_CONFIGS dictionary."""

    def test_step_configs_is_dict(self):
        """STEP_CONFIGS should be a dictionary."""
        from src.common.llm_config import STEP_CONFIGS

        assert isinstance(STEP_CONFIGS, dict)
        assert len(STEP_CONFIGS) > 0

    def test_all_tier_assignments_are_valid(self):
        """All tier assignments should use low/middle/high."""
        from src.common.llm_config import STEP_CONFIGS

        valid_tiers = {"low", "middle", "high"}

        for step_name, config in STEP_CONFIGS.items():
            assert config.tier in valid_tiers, \
                f"{step_name} has invalid tier: {config.tier}"

    def test_grader_uses_low_tier(self):
        """Grader should use low tier for cost efficiency."""
        from src.common.llm_config import STEP_CONFIGS

        if "grader" in STEP_CONFIGS:
            assert STEP_CONFIGS["grader"].tier == "low"

    def test_improver_uses_high_tier(self):
        """Improver should use high tier for quality."""
        from src.common.llm_config import STEP_CONFIGS

        if "improver" in STEP_CONFIGS:
            assert STEP_CONFIGS["improver"].tier == "high"

    def test_persona_synthesis_uses_high_tier(self):
        """Persona synthesis should use high tier."""
        from src.common.llm_config import STEP_CONFIGS

        if "persona_synthesis" in STEP_CONFIGS:
            assert STEP_CONFIGS["persona_synthesis"].tier == "high"


class TestGetStepConfig:
    """Tests for get_step_config function."""

    def test_returns_config_for_known_step(self):
        """Should return StepConfig for known steps."""
        from src.common.llm_config import get_step_config, StepConfig

        config = get_step_config("grader")

        assert isinstance(config, StepConfig)
        assert config.tier in ["low", "middle", "high"]

    def test_returns_default_for_unknown_step(self):
        """Should return default config for unknown steps."""
        from src.common.llm_config import get_step_config, StepConfig

        config = get_step_config("nonexistent_step_xyz")

        assert isinstance(config, StepConfig)
        assert config.tier == "middle"  # Default

    def test_env_var_override_tier(self):
        """Environment variable should override tier."""
        from src.common.llm_config import get_step_config

        with patch.dict(os.environ, {"LLM_TIER_grader": "high"}):
            config = get_step_config("grader")
            assert config.tier == "high"

    def test_env_var_override_model(self):
        """Environment variable should override model."""
        from src.common.llm_config import get_step_config

        with patch.dict(os.environ, {"LLM_MODEL_grader": "custom-model"}):
            config = get_step_config("grader")
            assert config.claude_model == "custom-model"

    def test_env_var_override_timeout(self):
        """Environment variable should override timeout."""
        from src.common.llm_config import get_step_config

        with patch.dict(os.environ, {"LLM_TIMEOUT_grader": "300"}):
            config = get_step_config("grader")
            assert config.timeout_seconds == 300


class TestTierMappings:
    """Tests for tier to model mappings."""

    def test_tier_to_claude_model_mapping(self):
        """TIER_TO_CLAUDE_MODEL should map all tiers."""
        from src.common.llm_config import TIER_TO_CLAUDE_MODEL

        assert "low" in TIER_TO_CLAUDE_MODEL
        assert "middle" in TIER_TO_CLAUDE_MODEL
        assert "high" in TIER_TO_CLAUDE_MODEL

    def test_tier_to_fallback_model_mapping(self):
        """TIER_TO_FALLBACK_MODEL should map all tiers."""
        from src.common.llm_config import TIER_TO_FALLBACK_MODEL

        assert "low" in TIER_TO_FALLBACK_MODEL
        assert "middle" in TIER_TO_FALLBACK_MODEL
        assert "high" in TIER_TO_FALLBACK_MODEL

    def test_low_tier_uses_haiku(self):
        """Low tier should use Haiku."""
        from src.common.llm_config import TIER_TO_CLAUDE_MODEL

        assert "haiku" in TIER_TO_CLAUDE_MODEL["low"].lower()

    def test_middle_tier_uses_sonnet(self):
        """Middle tier should use Sonnet."""
        from src.common.llm_config import TIER_TO_CLAUDE_MODEL

        assert "sonnet" in TIER_TO_CLAUDE_MODEL["middle"].lower()

    def test_high_tier_uses_opus(self):
        """High tier should use Opus."""
        from src.common.llm_config import TIER_TO_CLAUDE_MODEL

        assert "opus" in TIER_TO_CLAUDE_MODEL["high"].lower()


class TestTierCosts:
    """Tests for tier cost information."""

    def test_tier_costs_defined(self):
        """TIER_COSTS should be defined for all tiers."""
        from src.common.llm_config import TIER_COSTS

        assert "low" in TIER_COSTS
        assert "middle" in TIER_COSTS
        assert "high" in TIER_COSTS

    def test_costs_have_input_output(self):
        """Each tier should have input and output costs."""
        from src.common.llm_config import TIER_COSTS

        for tier, costs in TIER_COSTS.items():
            assert "input" in costs
            assert "output" in costs
            assert costs["input"] > 0
            assert costs["output"] > 0

    def test_costs_increase_with_tier(self):
        """Costs should increase: low < middle < high."""
        from src.common.llm_config import TIER_COSTS

        assert TIER_COSTS["low"]["input"] < TIER_COSTS["middle"]["input"]
        assert TIER_COSTS["middle"]["input"] < TIER_COSTS["high"]["input"]


class TestGetAllStepConfigs:
    """Tests for get_all_step_configs function."""

    def test_returns_all_configs(self):
        """get_all_step_configs should return all step configs."""
        from src.common.llm_config import get_all_step_configs, STEP_CONFIGS

        all_configs = get_all_step_configs()

        assert len(all_configs) == len(STEP_CONFIGS)

    def test_returns_resolved_configs(self):
        """get_all_step_configs should return resolved StepConfig instances."""
        from src.common.llm_config import get_all_step_configs, StepConfig

        all_configs = get_all_step_configs()

        for step_name, config in all_configs.items():
            assert isinstance(config, StepConfig)


class TestTierDisplayInfo:
    """Tests for get_tier_display_info function."""

    def test_returns_list(self):
        """get_tier_display_info should return a list."""
        from src.common.llm_config import get_tier_display_info

        info = get_tier_display_info()

        assert isinstance(info, list)
        assert len(info) == 3  # low, middle, high

    def test_contains_all_tiers(self):
        """Should contain info for all three tiers."""
        from src.common.llm_config import get_tier_display_info

        info = get_tier_display_info()
        tier_values = [t["value"] for t in info]

        assert "low" in tier_values
        assert "middle" in tier_values
        assert "high" in tier_values

    def test_each_tier_has_required_fields(self):
        """Each tier should have required display fields."""
        from src.common.llm_config import get_tier_display_info

        info = get_tier_display_info()

        for tier in info:
            assert "value" in tier
            assert "label" in tier
            assert "model" in tier
            assert "description" in tier
