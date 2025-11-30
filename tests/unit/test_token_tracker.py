"""
Unit tests for src/common/token_tracker.py
"""

import pytest
import threading
import time
from datetime import datetime
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult, Generation

from src.common.token_tracker import (
    TokenTracker,
    TokenUsage,
    UsageSummary,
    BudgetExceededError,
    TokenTrackingCallback,
    Provider,
    TOKEN_COSTS_PER_MILLION,
    get_global_tracker,
    reset_global_tracker,
)


class TestTokenUsage:
    """Tests for TokenUsage dataclass."""

    def test_total_tokens_calculation(self):
        """Should calculate total tokens as sum of input and output."""
        usage = TokenUsage(
            provider="openai",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            estimated_cost_usd=0.015,
        )
        assert usage.total_tokens == 1500

    def test_zero_tokens(self):
        """Should handle zero tokens correctly."""
        usage = TokenUsage(
            provider="anthropic",
            model="claude-3-5-haiku-20241022",
            input_tokens=0,
            output_tokens=0,
            estimated_cost_usd=0.0,
        )
        assert usage.total_tokens == 0

    def test_optional_layer_field(self):
        """Should allow layer to be None."""
        usage = TokenUsage(
            provider="openai",
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            estimated_cost_usd=0.001,
        )
        assert usage.layer is None

    def test_layer_field_when_provided(self):
        """Should store layer when provided."""
        usage = TokenUsage(
            provider="openai",
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            estimated_cost_usd=0.001,
            layer="layer6_v2",
        )
        assert usage.layer == "layer6_v2"

    def test_timestamp_defaults_to_current_time(self):
        """Should set timestamp to current UTC time by default."""
        before = datetime.utcnow()
        usage = TokenUsage(
            provider="openai",
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            estimated_cost_usd=0.001,
        )
        after = datetime.utcnow()

        assert before <= usage.timestamp <= after


class TestUsageSummary:
    """Tests for UsageSummary dataclass."""

    def test_defaults_to_zero(self):
        """Should initialize with zero values."""
        summary = UsageSummary()
        assert summary.total_input_tokens == 0
        assert summary.total_output_tokens == 0
        assert summary.total_tokens == 0
        assert summary.total_cost_usd == 0.0
        assert summary.calls_count == 0
        assert summary.by_provider == {}
        assert summary.by_layer == {}


class TestBudgetExceededError:
    """Tests for BudgetExceededError exception."""

    def test_exception_message_includes_cost_and_budget(self):
        """Should include current cost, budget, and usage details in message."""
        summary = UsageSummary(
            total_cost_usd=55.5678,
            total_tokens=100000,
            calls_count=25,
        )
        error = BudgetExceededError(summary, budget_usd=50.0)

        assert "$55.5678" in str(error)
        assert "$50.00" in str(error)
        assert "100,000" in str(error)
        assert "25 calls" in str(error)

    def test_exception_stores_summary_and_budget(self):
        """Should store summary and budget as attributes."""
        summary = UsageSummary(total_cost_usd=60.0)
        error = BudgetExceededError(summary, budget_usd=50.0)

        assert error.summary == summary
        assert error.budget_usd == 50.0


class TestTokenTracker:
    """Tests for TokenTracker class."""

    @pytest.fixture
    def tracker(self):
        """Create a basic tracker instance."""
        return TokenTracker(budget_usd=100.0, enforce_budget=True)

    @pytest.fixture
    def unlimited_tracker(self):
        """Create a tracker with no budget limit."""
        return TokenTracker(budget_usd=None)

    @pytest.fixture
    def non_enforcing_tracker(self):
        """Create a tracker that doesn't enforce budget."""
        return TokenTracker(budget_usd=50.0, enforce_budget=False)

    def test_initialization_with_defaults(self):
        """Should initialize with correct default values."""
        tracker = TokenTracker()
        assert tracker.budget_usd is None
        assert tracker.enforce_budget is True
        assert tracker.job_id is None
        assert tracker.get_summary().calls_count == 0

    def test_initialization_with_job_id(self):
        """Should store job_id when provided."""
        tracker = TokenTracker(job_id="test-job-123")
        assert tracker.job_id == "test-job-123"

    def test_estimate_cost_for_openai_gpt4o(self):
        """Should calculate correct cost for OpenAI GPT-4o."""
        tracker = TokenTracker()
        cost = tracker.estimate_cost("gpt-4o", input_tokens=1_000_000, output_tokens=1_000_000)
        # $2.50/M input + $10.00/M output
        assert cost == pytest.approx(12.50)

    def test_estimate_cost_for_anthropic_sonnet(self):
        """Should calculate correct cost for Anthropic Claude Sonnet."""
        tracker = TokenTracker()
        cost = tracker.estimate_cost("claude-3-5-sonnet-20241022", input_tokens=1_000_000, output_tokens=1_000_000)
        # $3.00/M input + $15.00/M output
        assert cost == pytest.approx(18.00)

    def test_estimate_cost_for_openrouter_model(self):
        """Should handle OpenRouter model names with provider prefix."""
        tracker = TokenTracker()
        cost = tracker.estimate_cost("anthropic/claude-3-5-haiku-20241022", input_tokens=1_000_000, output_tokens=1_000_000)
        # Note: The estimate_cost strips the provider prefix, so it uses base Anthropic pricing
        # $0.80/M input + $4.00/M output (base Anthropic pricing)
        assert cost == pytest.approx(4.80)

    def test_estimate_cost_for_unknown_model_uses_default(self):
        """Should use default pricing for unknown models."""
        tracker = TokenTracker()
        cost = tracker.estimate_cost("unknown-model-xyz", input_tokens=1_000_000, output_tokens=1_000_000)
        # $2.00/M input + $8.00/M output (default)
        assert cost == pytest.approx(10.00)

    def test_estimate_cost_with_small_token_counts(self):
        """Should calculate cost correctly for small token counts."""
        tracker = TokenTracker()
        cost = tracker.estimate_cost("gpt-4o", input_tokens=1000, output_tokens=500)
        # (1000/1M * $2.50) + (500/1M * $10.00)
        expected = (1000 / 1_000_000 * 2.50) + (500 / 1_000_000 * 10.00)
        assert cost == pytest.approx(expected)

    def test_estimate_cost_with_zero_tokens(self):
        """Should return zero cost for zero tokens."""
        tracker = TokenTracker()
        cost = tracker.estimate_cost("gpt-4o", input_tokens=0, output_tokens=0)
        assert cost == 0.0

    def test_track_usage_records_usage(self):
        """Should record usage and return TokenUsage."""
        tracker = TokenTracker()
        usage = tracker.track_usage(
            provider="openai",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            layer="layer2",
        )

        assert isinstance(usage, TokenUsage)
        assert usage.provider == "openai"
        assert usage.model == "gpt-4o"
        assert usage.input_tokens == 1000
        assert usage.output_tokens == 500
        assert usage.layer == "layer2"
        assert usage.estimated_cost_usd > 0

    def test_track_usage_updates_summary(self, tracker):
        """Should update summary with tracked usage."""
        tracker.track_usage("openai", "gpt-4o", 1000, 500)
        summary = tracker.get_summary()

        assert summary.total_input_tokens == 1000
        assert summary.total_output_tokens == 500
        assert summary.total_tokens == 1500
        assert summary.calls_count == 1

    def test_track_usage_multiple_calls_aggregate(self, tracker):
        """Should aggregate multiple calls correctly."""
        tracker.track_usage("openai", "gpt-4o", 1000, 500)
        tracker.track_usage("anthropic", "claude-3-5-haiku-20241022", 2000, 1000)

        summary = tracker.get_summary()
        assert summary.total_input_tokens == 3000
        assert summary.total_output_tokens == 1500
        assert summary.total_tokens == 4500
        assert summary.calls_count == 2

    def test_track_usage_raises_budget_exceeded_when_enforced(self):
        """Should raise BudgetExceededError when budget exceeded and enforced."""
        tracker = TokenTracker(budget_usd=0.001, enforce_budget=True)

        # First small call should be OK
        tracker.track_usage("openai", "gpt-4o-mini", 100, 50)

        # Large call should exceed budget
        with pytest.raises(BudgetExceededError) as exc_info:
            tracker.track_usage("openai", "gpt-4o", 1_000_000, 1_000_000)

        assert exc_info.value.budget_usd == 0.001

    def test_track_usage_does_not_raise_when_not_enforced(self, non_enforcing_tracker):
        """Should not raise even when budget exceeded if enforcement disabled."""
        # This would normally exceed budget
        non_enforcing_tracker.track_usage("openai", "gpt-4o", 10_000_000, 10_000_000)
        # Should not raise

    def test_track_usage_does_not_raise_with_unlimited_budget(self, unlimited_tracker):
        """Should not raise with unlimited budget (None)."""
        unlimited_tracker.track_usage("openai", "gpt-4o", 10_000_000, 10_000_000)
        # Should not raise

    def test_get_summary_by_provider_aggregation(self, tracker):
        """Should aggregate usage by provider correctly."""
        tracker.track_usage("openai", "gpt-4o", 1000, 500)
        tracker.track_usage("openai", "gpt-4o-mini", 2000, 1000)
        tracker.track_usage("anthropic", "claude-3-5-sonnet-20241022", 3000, 1500)

        summary = tracker.get_summary()

        assert "openai" in summary.by_provider
        assert summary.by_provider["openai"]["input_tokens"] == 3000
        assert summary.by_provider["openai"]["output_tokens"] == 1500
        assert summary.by_provider["openai"]["calls"] == 2

        assert "anthropic" in summary.by_provider
        assert summary.by_provider["anthropic"]["input_tokens"] == 3000
        assert summary.by_provider["anthropic"]["output_tokens"] == 1500
        assert summary.by_provider["anthropic"]["calls"] == 1

    def test_get_summary_by_layer_aggregation(self, tracker):
        """Should aggregate usage by layer correctly."""
        tracker.track_usage("openai", "gpt-4o", 1000, 500, layer="layer2")
        tracker.track_usage("openai", "gpt-4o", 2000, 1000, layer="layer2")
        tracker.track_usage("anthropic", "claude-3-5-sonnet-20241022", 3000, 1500, layer="layer6_v2")

        summary = tracker.get_summary()

        assert "layer2" in summary.by_layer
        assert summary.by_layer["layer2"]["input_tokens"] == 3000
        assert summary.by_layer["layer2"]["output_tokens"] == 1500
        assert summary.by_layer["layer2"]["calls"] == 2

        assert "layer6_v2" in summary.by_layer
        assert summary.by_layer["layer6_v2"]["input_tokens"] == 3000
        assert summary.by_layer["layer6_v2"]["output_tokens"] == 1500
        assert summary.by_layer["layer6_v2"]["calls"] == 1

    def test_get_summary_handles_none_layer(self, tracker):
        """Should aggregate usage without layer as 'unknown'."""
        tracker.track_usage("openai", "gpt-4o", 1000, 500)  # No layer

        summary = tracker.get_summary()
        assert "unknown" in summary.by_layer
        assert summary.by_layer["unknown"]["input_tokens"] == 1000

    def test_is_budget_exceeded_when_under_budget(self, tracker):
        """Should return False when under budget."""
        tracker.track_usage("openai", "gpt-4o-mini", 100, 50)  # Very cheap
        assert tracker.is_budget_exceeded() is False

    def test_is_budget_exceeded_when_over_budget(self):
        """Should return True when over budget."""
        tracker = TokenTracker(budget_usd=0.001, enforce_budget=False)
        tracker.track_usage("openai", "gpt-4o", 1_000_000, 1_000_000)  # Expensive
        assert tracker.is_budget_exceeded() is True

    def test_is_budget_exceeded_with_unlimited_budget(self, unlimited_tracker):
        """Should return False with unlimited budget."""
        unlimited_tracker.track_usage("openai", "gpt-4o", 10_000_000, 10_000_000)
        assert unlimited_tracker.is_budget_exceeded() is False

    def test_get_remaining_budget_calculates_correctly(self, tracker):
        """Should calculate remaining budget correctly."""
        initial_remaining = tracker.get_remaining_budget()
        assert initial_remaining == 100.0

        # Track some usage
        usage = tracker.track_usage("openai", "gpt-4o", 1000, 500)
        remaining = tracker.get_remaining_budget()

        assert remaining == pytest.approx(100.0 - usage.estimated_cost_usd)

    def test_get_remaining_budget_returns_none_for_unlimited(self, unlimited_tracker):
        """Should return None for unlimited budget."""
        assert unlimited_tracker.get_remaining_budget() is None

    def test_get_remaining_budget_never_negative(self):
        """Should return 0.0 when budget exceeded, not negative."""
        tracker = TokenTracker(budget_usd=0.001, enforce_budget=False)
        tracker.track_usage("openai", "gpt-4o", 1_000_000, 1_000_000)

        remaining = tracker.get_remaining_budget()
        assert remaining == 0.0

    def test_get_usages_returns_all_records(self, tracker):
        """Should return list of all tracked usages."""
        tracker.track_usage("openai", "gpt-4o", 1000, 500)
        tracker.track_usage("anthropic", "claude-3-5-haiku-20241022", 2000, 1000)

        usages = tracker.get_usages()
        assert len(usages) == 2
        assert all(isinstance(u, TokenUsage) for u in usages)

    def test_reset_clears_all_usage(self, tracker):
        """Should clear all tracked usage."""
        tracker.track_usage("openai", "gpt-4o", 1000, 500)
        tracker.track_usage("anthropic", "claude-3-5-haiku-20241022", 2000, 1000)

        tracker.reset()

        summary = tracker.get_summary()
        assert summary.calls_count == 0
        assert summary.total_tokens == 0
        assert summary.total_cost_usd == 0.0
        assert len(tracker.get_usages()) == 0

    def test_to_dict_exports_complete_state(self, tracker):
        """Should export complete tracker state as dictionary."""
        tracker.track_usage("openai", "gpt-4o", 1000, 500, layer="layer2")

        data = tracker.to_dict()

        assert data["budget_usd"] == 100.0
        assert data["total_input_tokens"] == 1000
        assert data["total_output_tokens"] == 500
        assert data["total_tokens"] == 1500
        assert data["calls_count"] == 1
        assert "openai" in data["by_provider"]
        assert "layer2" in data["by_layer"]
        assert len(data["usages"]) == 1

    def test_to_dict_includes_job_id(self):
        """Should include job_id in exported data."""
        tracker = TokenTracker(job_id="test-job-123")
        data = tracker.to_dict()
        assert data["job_id"] == "test-job-123"

    def test_to_dict_usages_serializable(self, tracker):
        """Should export usages with serializable timestamps."""
        tracker.track_usage("openai", "gpt-4o", 1000, 500)

        data = tracker.to_dict()
        usage = data["usages"][0]

        # Timestamp should be ISO format string
        assert isinstance(usage["timestamp"], str)
        datetime.fromisoformat(usage["timestamp"])  # Should not raise

    def test_track_langchain_response_with_response_metadata(self, tracker):
        """Should extract usage from LangChain response metadata."""
        response = AIMessage(
            content="Test response",
            response_metadata={
                "token_usage": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 500,
                },
                "model_name": "gpt-4o",
            },
        )

        usage = tracker.track_langchain_response("openai", response, layer="layer2")

        assert usage is not None
        assert usage.input_tokens == 1000
        assert usage.output_tokens == 500
        assert usage.model == "gpt-4o"
        assert usage.layer == "layer2"

    def test_track_langchain_response_with_usage_metadata(self, tracker):
        """Should extract usage from newer LangChain usage_metadata field."""
        response = MagicMock()
        response.usage_metadata = {
            "input_tokens": 1200,
            "output_tokens": 600,
        }
        response.response_metadata = {"model_name": "claude-3-5-sonnet-20241022"}

        usage = tracker.track_langchain_response("anthropic", response)

        assert usage is not None
        assert usage.input_tokens == 1200
        assert usage.output_tokens == 600

    def test_track_langchain_response_with_alternative_usage_format(self, tracker):
        """Should handle alternative usage format in metadata."""
        response = AIMessage(
            content="Test",
            response_metadata={
                "usage": {
                    "prompt_tokens": 800,
                    "completion_tokens": 400,
                },
                "model": "gpt-4o-mini",
            },
        )

        usage = tracker.track_langchain_response("openai", response)

        assert usage is not None
        assert usage.input_tokens == 800
        assert usage.output_tokens == 400
        assert usage.model == "gpt-4o-mini"

    def test_track_langchain_response_returns_none_for_missing_usage(self, tracker):
        """Should return None when usage info not available."""
        response = AIMessage(content="Test response")  # No metadata

        usage = tracker.track_langchain_response("openai", response)
        assert usage is None

    def test_track_langchain_response_returns_none_for_zero_tokens(self, tracker):
        """Should return None when usage shows zero tokens."""
        response = AIMessage(
            content="Test",
            response_metadata={
                "token_usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                },
            },
        )

        usage = tracker.track_langchain_response("openai", response)
        assert usage is None


class TestTokenTrackerThreadSafety:
    """Tests for thread safety of TokenTracker."""

    def test_concurrent_track_usage_is_thread_safe(self):
        """Should handle concurrent track_usage calls safely."""
        tracker = TokenTracker()
        num_threads = 10
        calls_per_thread = 100

        def track_repeatedly():
            for _ in range(calls_per_thread):
                tracker.track_usage("openai", "gpt-4o-mini", 100, 50)

        threads = [threading.Thread(target=track_repeatedly) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        summary = tracker.get_summary()
        expected_calls = num_threads * calls_per_thread
        assert summary.calls_count == expected_calls
        assert summary.total_input_tokens == expected_calls * 100
        assert summary.total_output_tokens == expected_calls * 50

    def test_concurrent_get_summary_is_thread_safe(self):
        """Should handle concurrent get_summary calls safely."""
        tracker = TokenTracker()
        tracker.track_usage("openai", "gpt-4o", 1000, 500)

        results = []

        def get_summary_repeatedly():
            for _ in range(100):
                summary = tracker.get_summary()
                results.append(summary.total_tokens)

        threads = [threading.Thread(target=get_summary_repeatedly) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All results should be consistent
        assert all(r == 1500 for r in results)

    def test_concurrent_reset_is_thread_safe(self):
        """Should handle concurrent reset calls safely."""
        tracker = TokenTracker()

        def track_and_reset():
            tracker.track_usage("openai", "gpt-4o-mini", 100, 50)
            time.sleep(0.001)
            tracker.reset()

        threads = [threading.Thread(target=track_and_reset) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should not crash, final state should be valid
        summary = tracker.get_summary()
        assert summary.calls_count >= 0


class TestTokenTrackingCallback:
    """Tests for TokenTrackingCallback handler."""

    @pytest.fixture
    def tracker(self):
        """Create a tracker instance."""
        return TokenTracker()

    @pytest.fixture
    def callback(self, tracker):
        """Create a callback handler."""
        return TokenTrackingCallback(tracker, provider="openai", layer="layer2")

    def test_initialization_stores_tracker_and_provider(self, tracker):
        """Should store tracker, provider, and layer."""
        callback = TokenTrackingCallback(tracker, provider="anthropic", layer="layer6")

        assert callback.tracker == tracker
        assert callback.provider == "anthropic"
        assert callback.layer == "layer6"

    def test_on_llm_end_tracks_usage(self, tracker, callback):
        """Should track usage when LLM completes."""
        llm_result = LLMResult(
            generations=[[Generation(text="Test response")]],
            llm_output={
                "token_usage": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 500,
                },
                "model_name": "gpt-4o",
            },
        )

        callback.on_llm_end(llm_result)

        summary = tracker.get_summary()
        assert summary.calls_count == 1
        assert summary.total_input_tokens == 1000
        assert summary.total_output_tokens == 500

    def test_on_llm_end_uses_alternative_token_field_names(self, tracker, callback):
        """Should handle alternative token field names."""
        llm_result = LLMResult(
            generations=[[Generation(text="Test")]],
            llm_output={
                "token_usage": {
                    "input_tokens": 800,
                    "output_tokens": 400,
                },
                "model_name": "gpt-4o-mini",
            },
        )

        callback.on_llm_end(llm_result)

        summary = tracker.get_summary()
        assert summary.total_input_tokens == 800
        assert summary.total_output_tokens == 400

    def test_on_llm_end_ignores_zero_tokens(self, tracker, callback):
        """Should not track when tokens are zero."""
        llm_result = LLMResult(
            generations=[[Generation(text="Test")]],
            llm_output={
                "token_usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                },
            },
        )

        callback.on_llm_end(llm_result)

        summary = tracker.get_summary()
        assert summary.calls_count == 0

    def test_on_llm_end_handles_missing_llm_output(self, tracker, callback):
        """Should handle LLMResult without llm_output."""
        llm_result = LLMResult(
            generations=[[Generation(text="Test")]],
        )

        callback.on_llm_end(llm_result)

        summary = tracker.get_summary()
        assert summary.calls_count == 0

    def test_on_llm_end_includes_layer(self, tracker):
        """Should include layer in tracked usage."""
        callback = TokenTrackingCallback(tracker, provider="openai", layer="layer6_v2")

        llm_result = LLMResult(
            generations=[[Generation(text="Test")]],
            llm_output={
                "token_usage": {"prompt_tokens": 100, "completion_tokens": 50},
                "model_name": "gpt-4o",
            },
        )

        callback.on_llm_end(llm_result)

        usages = tracker.get_usages()
        assert len(usages) == 1
        assert usages[0].layer == "layer6_v2"


class TestGlobalTracker:
    """Tests for global tracker functions."""

    def test_get_global_tracker_returns_singleton(self):
        """Should return the same instance on multiple calls."""
        reset_global_tracker()  # Clear first

        tracker1 = get_global_tracker()
        tracker2 = get_global_tracker()

        assert tracker1 is tracker2

    def test_get_global_tracker_uses_env_budget(self, monkeypatch):
        """Should use TOKEN_BUDGET_USD from environment."""
        # Need to clear the global instance and set env before first call
        import src.common.token_tracker as tt_module
        tt_module._global_tracker = None
        monkeypatch.setenv("TOKEN_BUDGET_USD", "250.0")

        tracker = get_global_tracker()
        assert tracker.budget_usd == 250.0

    def test_get_global_tracker_defaults_to_100(self, monkeypatch):
        """Should default to $100 budget."""
        # Need to clear the global instance and set env before first call
        import src.common.token_tracker as tt_module
        tt_module._global_tracker = None
        monkeypatch.delenv("TOKEN_BUDGET_USD", raising=False)

        tracker = get_global_tracker()
        assert tracker.budget_usd == 100.0

    def test_get_global_tracker_uses_env_enforcement(self, monkeypatch):
        """Should use ENFORCE_TOKEN_BUDGET from environment."""
        # Need to clear the global instance and set env before first call
        import src.common.token_tracker as tt_module
        tt_module._global_tracker = None
        monkeypatch.setenv("ENFORCE_TOKEN_BUDGET", "true")

        tracker = get_global_tracker()
        assert tracker.enforce_budget is True

    def test_get_global_tracker_defaults_to_no_enforcement(self, monkeypatch):
        """Should default to no enforcement in development."""
        # Need to clear the global instance and set env before first call
        import src.common.token_tracker as tt_module
        tt_module._global_tracker = None
        monkeypatch.delenv("ENFORCE_TOKEN_BUDGET", raising=False)

        tracker = get_global_tracker()
        assert tracker.enforce_budget is False

    def test_reset_global_tracker_clears_usage(self):
        """Should clear global tracker usage."""
        tracker = get_global_tracker()
        tracker.track_usage("openai", "gpt-4o-mini", 100, 50)

        reset_global_tracker()

        summary = tracker.get_summary()
        assert summary.calls_count == 0


class TestProviderEnum:
    """Tests for Provider enum."""

    def test_provider_values(self):
        """Should have correct string values."""
        assert Provider.OPENAI.value == "openai"
        assert Provider.ANTHROPIC.value == "anthropic"
        assert Provider.OPENROUTER.value == "openrouter"


class TestTokenCostsPricing:
    """Tests to ensure TOKEN_COSTS_PER_MILLION is complete."""

    def test_has_openai_models(self):
        """Should include OpenAI models."""
        assert "gpt-4o" in TOKEN_COSTS_PER_MILLION
        assert "gpt-4o-mini" in TOKEN_COSTS_PER_MILLION
        assert "gpt-4-turbo" in TOKEN_COSTS_PER_MILLION
        assert "gpt-3.5-turbo" in TOKEN_COSTS_PER_MILLION

    def test_has_anthropic_models(self):
        """Should include Anthropic models."""
        assert "claude-3-5-sonnet-20241022" in TOKEN_COSTS_PER_MILLION
        assert "claude-3-5-haiku-20241022" in TOKEN_COSTS_PER_MILLION
        assert "claude-3-opus-20240229" in TOKEN_COSTS_PER_MILLION

    def test_has_openrouter_models(self):
        """Should include OpenRouter models."""
        assert "anthropic/claude-3-5-sonnet-20241022" in TOKEN_COSTS_PER_MILLION
        assert "anthropic/claude-3-5-haiku-20241022" in TOKEN_COSTS_PER_MILLION

    def test_has_default_fallback(self):
        """Should have default pricing."""
        assert "default" in TOKEN_COSTS_PER_MILLION

    def test_all_models_have_input_and_output_costs(self):
        """All models should have both input and output cost keys."""
        for model, pricing in TOKEN_COSTS_PER_MILLION.items():
            assert "input" in pricing, f"{model} missing input cost"
            assert "output" in pricing, f"{model} missing output cost"
            assert isinstance(pricing["input"], (int, float))
            assert isinstance(pricing["output"], (int, float))
