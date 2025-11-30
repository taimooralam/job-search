"""
Token Tracking Module (Gap BG-1).

Tracks token usage across LLM calls for budget enforcement.
Supports multiple providers: OpenAI, Anthropic, OpenRouter.

Usage:
    tracker = TokenTracker(budget_usd=50.0)

    # Track usage from LangChain response
    tracker.track_usage("openai", response)

    # Check if budget exceeded
    if tracker.is_budget_exceeded():
        raise BudgetExceededError(tracker.get_usage_summary())
"""

import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


class Provider(str, Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OPENROUTER = "openrouter"


# Approximate pricing per 1M tokens (as of Nov 2024)
# These are estimates - actual pricing varies by model
TOKEN_COSTS_PER_MILLION = {
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},

    # Anthropic
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},

    # OpenRouter (proxied models - slightly higher due to markup)
    "anthropic/claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "anthropic/claude-3-5-haiku-20241022": {"input": 1.00, "output": 5.00},

    # Default fallback
    "default": {"input": 2.00, "output": 8.00},
}


@dataclass
class TokenUsage:
    """Token usage for a single LLM call."""
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    layer: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def total_tokens(self) -> int:
        """Total tokens (input + output)."""
        return self.input_tokens + self.output_tokens


@dataclass
class UsageSummary:
    """Aggregated token usage summary."""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    calls_count: int = 0
    by_provider: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    by_layer: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class BudgetExceededError(Exception):
    """Raised when token budget is exceeded."""

    def __init__(self, summary: UsageSummary, budget_usd: float):
        self.summary = summary
        self.budget_usd = budget_usd
        super().__init__(
            f"Token budget exceeded: ${summary.total_cost_usd:.4f} / ${budget_usd:.2f} "
            f"({summary.total_tokens:,} tokens across {summary.calls_count} calls)"
        )


class TokenTracker:
    """
    Thread-safe token usage tracker with budget enforcement.

    Tracks token consumption across LLM calls and enforces budget limits.
    Can be used globally or per-job for isolated tracking.
    """

    def __init__(
        self,
        budget_usd: Optional[float] = None,
        enforce_budget: bool = True,
        job_id: Optional[str] = None,
    ):
        """
        Initialize token tracker.

        Args:
            budget_usd: Maximum budget in USD (None for unlimited)
            enforce_budget: Whether to raise BudgetExceededError when exceeded
            job_id: Optional job ID for per-job tracking
        """
        self.budget_usd = budget_usd
        self.enforce_budget = enforce_budget
        self.job_id = job_id
        self._usages: List[TokenUsage] = []
        self._lock = threading.Lock()

    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """
        Estimate cost for token usage.

        Args:
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Estimated cost in USD
        """
        # Normalize model name (strip provider prefix if present)
        model_key = model.split("/")[-1] if "/" in model else model

        # Get pricing (fallback to default)
        pricing = TOKEN_COSTS_PER_MILLION.get(model_key) or TOKEN_COSTS_PER_MILLION.get(model) or TOKEN_COSTS_PER_MILLION["default"]

        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]

        return input_cost + output_cost

    def track_usage(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        layer: Optional[str] = None,
    ) -> TokenUsage:
        """
        Track token usage from an LLM call.

        Args:
            provider: LLM provider (openai, anthropic, openrouter)
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            layer: Pipeline layer name (e.g., "layer2", "layer6_v2")

        Returns:
            TokenUsage record

        Raises:
            BudgetExceededError: If budget is exceeded and enforcement is enabled
        """
        cost = self.estimate_cost(model, input_tokens, output_tokens)

        usage = TokenUsage(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=cost,
            layer=layer,
        )

        with self._lock:
            self._usages.append(usage)

        # Check budget after tracking
        if self.enforce_budget and self.is_budget_exceeded():
            raise BudgetExceededError(self.get_summary(), self.budget_usd)

        return usage

    def track_langchain_response(
        self,
        provider: str,
        response: Any,
        layer: Optional[str] = None,
    ) -> Optional[TokenUsage]:
        """
        Track usage from a LangChain response object.

        Args:
            provider: LLM provider
            response: LangChain AIMessage or response object
            layer: Pipeline layer name

        Returns:
            TokenUsage if usage info available, None otherwise
        """
        # Extract usage from response metadata
        usage_info = None
        model = "unknown"

        # LangChain AIMessage has response_metadata with usage
        if hasattr(response, 'response_metadata'):
            metadata = response.response_metadata

            # OpenAI/OpenRouter format
            if 'token_usage' in metadata:
                usage_info = metadata['token_usage']
                model = metadata.get('model_name', metadata.get('model', 'unknown'))
            # Alternative format
            elif 'usage' in metadata:
                usage_info = metadata['usage']
                model = metadata.get('model_name', metadata.get('model', 'unknown'))

            # Try to get model from metadata
            if model == "unknown" and 'model_name' in metadata:
                model = metadata['model_name']

        # Also check usage_metadata (newer LangChain versions)
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage_meta = response.usage_metadata
            usage_info = {
                'prompt_tokens': usage_meta.get('input_tokens', 0),
                'completion_tokens': usage_meta.get('output_tokens', 0),
            }

        if not usage_info:
            return None

        # Normalize token field names
        input_tokens = usage_info.get('prompt_tokens', 0) or usage_info.get('input_tokens', 0)
        output_tokens = usage_info.get('completion_tokens', 0) or usage_info.get('output_tokens', 0)

        if input_tokens == 0 and output_tokens == 0:
            return None

        return self.track_usage(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            layer=layer,
        )

    def get_summary(self) -> UsageSummary:
        """
        Get aggregated usage summary.

        Returns:
            UsageSummary with totals and breakdowns
        """
        with self._lock:
            summary = UsageSummary()

            for usage in self._usages:
                summary.total_input_tokens += usage.input_tokens
                summary.total_output_tokens += usage.output_tokens
                summary.total_tokens += usage.total_tokens
                summary.total_cost_usd += usage.estimated_cost_usd
                summary.calls_count += 1

                # By provider
                if usage.provider not in summary.by_provider:
                    summary.by_provider[usage.provider] = {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cost_usd": 0.0,
                        "calls": 0,
                    }
                summary.by_provider[usage.provider]["input_tokens"] += usage.input_tokens
                summary.by_provider[usage.provider]["output_tokens"] += usage.output_tokens
                summary.by_provider[usage.provider]["cost_usd"] += usage.estimated_cost_usd
                summary.by_provider[usage.provider]["calls"] += 1

                # By layer
                layer_key = usage.layer or "unknown"
                if layer_key not in summary.by_layer:
                    summary.by_layer[layer_key] = {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cost_usd": 0.0,
                        "calls": 0,
                    }
                summary.by_layer[layer_key]["input_tokens"] += usage.input_tokens
                summary.by_layer[layer_key]["output_tokens"] += usage.output_tokens
                summary.by_layer[layer_key]["cost_usd"] += usage.estimated_cost_usd
                summary.by_layer[layer_key]["calls"] += 1

            return summary

    def is_budget_exceeded(self) -> bool:
        """
        Check if budget is exceeded.

        Returns:
            True if budget is set and exceeded
        """
        if self.budget_usd is None:
            return False

        summary = self.get_summary()
        return summary.total_cost_usd > self.budget_usd

    def get_remaining_budget(self) -> Optional[float]:
        """
        Get remaining budget.

        Returns:
            Remaining budget in USD, or None if unlimited
        """
        if self.budget_usd is None:
            return None

        summary = self.get_summary()
        return max(0.0, self.budget_usd - summary.total_cost_usd)

    def get_usages(self) -> List[TokenUsage]:
        """Get all tracked usages."""
        with self._lock:
            return list(self._usages)

    def reset(self) -> None:
        """Reset all tracked usage."""
        with self._lock:
            self._usages.clear()

    def to_dict(self) -> Dict[str, Any]:
        """
        Export tracker state as dictionary (for persistence).

        Returns:
            Dictionary with usage data
        """
        summary = self.get_summary()
        return {
            "job_id": self.job_id,
            "budget_usd": self.budget_usd,
            "total_input_tokens": summary.total_input_tokens,
            "total_output_tokens": summary.total_output_tokens,
            "total_tokens": summary.total_tokens,
            "total_cost_usd": summary.total_cost_usd,
            "calls_count": summary.calls_count,
            "by_provider": summary.by_provider,
            "by_layer": summary.by_layer,
            "usages": [
                {
                    "provider": u.provider,
                    "model": u.model,
                    "input_tokens": u.input_tokens,
                    "output_tokens": u.output_tokens,
                    "cost_usd": u.estimated_cost_usd,
                    "layer": u.layer,
                    "timestamp": u.timestamp.isoformat(),
                }
                for u in self._usages
            ],
        }


class TokenTrackingCallback(BaseCallbackHandler):
    """
    LangChain callback handler for automatic token tracking.

    Attach to LLM instances to automatically track all token usage.

    Usage:
        tracker = TokenTracker(budget_usd=50.0)
        callback = TokenTrackingCallback(tracker, provider="openai", layer="layer6")
        llm = ChatOpenAI(..., callbacks=[callback])
    """

    def __init__(
        self,
        tracker: TokenTracker,
        provider: str,
        layer: Optional[str] = None,
    ):
        """
        Initialize callback handler.

        Args:
            tracker: TokenTracker instance
            provider: LLM provider name
            layer: Pipeline layer name
        """
        super().__init__()
        self.tracker = tracker
        self.provider = provider
        self.layer = layer

    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        """
        Called when LLM completes.

        Extracts token usage from response and tracks it.
        """
        # LLMResult has generations and llm_output
        if response.llm_output:
            usage = response.llm_output.get('token_usage', {})
            model = response.llm_output.get('model_name', 'unknown')

            input_tokens = usage.get('prompt_tokens', 0) or usage.get('input_tokens', 0)
            output_tokens = usage.get('completion_tokens', 0) or usage.get('output_tokens', 0)

            if input_tokens > 0 or output_tokens > 0:
                self.tracker.track_usage(
                    provider=self.provider,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    layer=self.layer,
                )


# Global tracker instance (for simple usage)
_global_tracker: Optional[TokenTracker] = None


def get_global_tracker() -> TokenTracker:
    """
    Get or create global token tracker.

    Uses environment variables for configuration:
    - TOKEN_BUDGET_USD: Budget limit (default: 100.0)
    - ENFORCE_TOKEN_BUDGET: Whether to enforce (default: false in dev)
    """
    global _global_tracker

    if _global_tracker is None:
        budget = float(os.getenv("TOKEN_BUDGET_USD", "100.0"))
        enforce = os.getenv("ENFORCE_TOKEN_BUDGET", "false").lower() == "true"
        _global_tracker = TokenTracker(budget_usd=budget, enforce_budget=enforce)

    return _global_tracker


def reset_global_tracker() -> None:
    """Reset the global tracker."""
    global _global_tracker
    if _global_tracker:
        _global_tracker.reset()
