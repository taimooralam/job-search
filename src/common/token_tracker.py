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
from datetime import datetime, timedelta
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
    run_id: Optional[str] = None
    job_id: Optional[str] = None
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
        run_id: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> TokenUsage:
        """
        Track token usage from an LLM call.

        Args:
            provider: LLM provider (openai, anthropic, openrouter)
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            layer: Pipeline layer name (e.g., "layer2", "layer6_v2")
            run_id: Pipeline run identifier for per-run cost tracking
            job_id: Job identifier for per-job cost tracking

        Returns:
            TokenUsage record

        Raises:
            BudgetExceededError: If budget is exceeded and enforcement is enabled
        """
        cost = self.estimate_cost(model, input_tokens, output_tokens)

        # Use instance-level job_id if not provided
        effective_job_id = job_id or self.job_id

        usage = TokenUsage(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=cost,
            layer=layer,
            run_id=run_id,
            job_id=effective_job_id,
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
        run_id: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> Optional[TokenUsage]:
        """
        Track usage from a LangChain response object.

        Args:
            provider: LLM provider
            response: LangChain AIMessage or response object
            layer: Pipeline layer name
            run_id: Pipeline run identifier for per-run cost tracking
            job_id: Job identifier for per-job cost tracking

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
            run_id=run_id,
            job_id=job_id,
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
                    "run_id": u.run_id,
                    "job_id": u.job_id,
                    "timestamp": u.timestamp.isoformat(),
                }
                for u in self._usages
            ],
        }

    def get_hourly_costs(self, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Get costs aggregated by hour for the last N hours.

        Args:
            hours: Number of hours to look back (default 24)

        Returns:
            List of dicts with 'hour', 'cost_usd', 'calls' keys
        """
        from collections import defaultdict

        now = datetime.utcnow()
        cutoff = now - timedelta(hours=hours)

        with self._lock:
            hourly = defaultdict(lambda: {"cost_usd": 0.0, "calls": 0})

            for usage in self._usages:
                if usage.timestamp >= cutoff:
                    hour_key = usage.timestamp.strftime("%Y-%m-%d %H:00")
                    hourly[hour_key]["cost_usd"] += usage.estimated_cost_usd
                    hourly[hour_key]["calls"] += 1

        # Generate all hours in range (including zeros)
        result = []
        for i in range(hours):
            hour = now - timedelta(hours=hours - 1 - i)
            hour_key = hour.strftime("%Y-%m-%d %H:00")
            data = hourly.get(hour_key, {"cost_usd": 0.0, "calls": 0})
            result.append({
                "hour": hour_key,
                "cost_usd": round(data["cost_usd"], 6),
                "calls": data["calls"],
            })

        return result

    def get_daily_costs(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get costs aggregated by day for the last N days.

        Args:
            days: Number of days to look back (default 7)

        Returns:
            List of dicts with 'date', 'cost_usd', 'calls' keys
        """
        from collections import defaultdict

        now = datetime.utcnow()
        cutoff = now - timedelta(days=days)

        with self._lock:
            daily = defaultdict(lambda: {"cost_usd": 0.0, "calls": 0})

            for usage in self._usages:
                if usage.timestamp >= cutoff:
                    day_key = usage.timestamp.strftime("%Y-%m-%d")
                    daily[day_key]["cost_usd"] += usage.estimated_cost_usd
                    daily[day_key]["calls"] += 1

        # Generate all days in range (including zeros)
        result = []
        for i in range(days):
            day = now - timedelta(days=days - 1 - i)
            day_key = day.strftime("%Y-%m-%d")
            data = daily.get(day_key, {"cost_usd": 0.0, "calls": 0})
            result.append({
                "date": day_key,
                "cost_usd": round(data["cost_usd"], 6),
                "calls": data["calls"],
            })

        return result

    # =========================================================================
    # Per-Run Cost Tracking (BG-3)
    # =========================================================================

    def get_runs(self) -> List[str]:
        """
        Get all unique run_ids that have been tracked.

        Returns:
            List of run_id strings (excludes None)
        """
        with self._lock:
            return list(set(u.run_id for u in self._usages if u.run_id))

    def get_run_usages(self, run_id: str) -> List[TokenUsage]:
        """
        Get all usages for a specific run.

        Args:
            run_id: Pipeline run identifier

        Returns:
            List of TokenUsage records for the run
        """
        with self._lock:
            return [u for u in self._usages if u.run_id == run_id]

    def get_run_summary(self, run_id: str) -> UsageSummary:
        """
        Get aggregated usage summary for a specific run.

        Args:
            run_id: Pipeline run identifier

        Returns:
            UsageSummary with totals and breakdowns for the run
        """
        with self._lock:
            summary = UsageSummary()

            for usage in self._usages:
                if usage.run_id != run_id:
                    continue

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

    def get_run_cost(self, run_id: str) -> float:
        """
        Get total cost for a specific run.

        Args:
            run_id: Pipeline run identifier

        Returns:
            Total cost in USD for the run
        """
        summary = self.get_run_summary(run_id)
        return summary.total_cost_usd

    def export_run_to_file(self, run_id: str, path: str) -> None:
        """
        Export cost data for a specific run to JSON file.

        Args:
            run_id: Pipeline run identifier
            path: Output file path
        """
        import json
        from pathlib import Path

        usages = self.get_run_usages(run_id)
        summary = self.get_run_summary(run_id)

        data = {
            "run_id": run_id,
            "summary": {
                "total_input_tokens": summary.total_input_tokens,
                "total_output_tokens": summary.total_output_tokens,
                "total_tokens": summary.total_tokens,
                "total_cost_usd": round(summary.total_cost_usd, 6),
                "calls_count": summary.calls_count,
                "by_provider": summary.by_provider,
                "by_layer": summary.by_layer,
            },
            "calls": [
                {
                    "provider": u.provider,
                    "model": u.model,
                    "input_tokens": u.input_tokens,
                    "output_tokens": u.output_tokens,
                    "cost_usd": round(u.estimated_cost_usd, 6),
                    "layer": u.layer,
                    "job_id": u.job_id,
                    "timestamp": u.timestamp.isoformat(),
                }
                for u in usages
            ],
        }

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def get_job_cost(self, job_id: str) -> float:
        """
        Get total cost for a specific job across all runs.

        Args:
            job_id: Job identifier

        Returns:
            Total cost in USD for the job
        """
        with self._lock:
            return sum(
                u.estimated_cost_usd for u in self._usages
                if u.job_id == job_id
            )


class TokenTrackingCallback(BaseCallbackHandler):
    """
    LangChain callback handler for automatic token tracking.

    Attach to LLM instances to automatically track all token usage.

    Usage:
        tracker = TokenTracker(budget_usd=50.0)
        callback = TokenTrackingCallback(tracker, provider="openai", layer="layer6")
        llm = ChatOpenAI(..., callbacks=[callback])

    For per-run tracking:
        callback = TokenTrackingCallback(tracker, provider="openai", layer="layer2", run_id="run_123")
    """

    def __init__(
        self,
        tracker: TokenTracker,
        provider: str,
        layer: Optional[str] = None,
        run_id: Optional[str] = None,
        job_id: Optional[str] = None,
    ):
        """
        Initialize callback handler.

        Args:
            tracker: TokenTracker instance
            provider: LLM provider name
            layer: Pipeline layer name
            run_id: Pipeline run identifier for per-run cost tracking
            job_id: Job identifier for per-job cost tracking
        """
        super().__init__()
        self.tracker = tracker
        self.provider = provider
        self.layer = layer
        self.run_id = run_id
        self.job_id = job_id

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
                    run_id=self.run_id,
                    job_id=self.job_id,
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


# =============================================================================
# Token Tracker Registry (for metrics aggregation)
# =============================================================================

class TokenTrackerRegistry:
    """
    Registry for managing multiple token trackers.

    Allows metrics collection across all trackers.
    """

    def __init__(self):
        """Initialize the registry."""
        self._trackers: Dict[str, TokenTracker] = {}
        self._lock = threading.Lock()

    def get_or_create(
        self,
        name: str,
        budget_usd: Optional[float] = None,
        **kwargs,
    ) -> TokenTracker:
        """
        Get existing tracker or create a new one.

        Args:
            name: Identifier for the tracker (e.g., provider name)
            budget_usd: Optional budget for this tracker
            **kwargs: Additional TokenTracker arguments

        Returns:
            TokenTracker instance
        """
        with self._lock:
            if name not in self._trackers:
                self._trackers[name] = TokenTracker(
                    budget_usd=budget_usd,
                    **kwargs,
                )
            return self._trackers[name]

    def get(self, name: str) -> Optional[TokenTracker]:
        """Get tracker by name if it exists."""
        with self._lock:
            return self._trackers.get(name)

    def register(self, name: str, tracker: TokenTracker) -> None:
        """Register an existing tracker."""
        with self._lock:
            self._trackers[name] = tracker

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Get stats for all registered trackers.

        Returns:
            Dict mapping tracker names to their stats
        """
        with self._lock:
            result = {}
            for name, tracker in self._trackers.items():
                summary = tracker.get_summary()
                # Calculate budget metrics
                budget_usd = tracker.budget_usd
                remaining = tracker.get_remaining_budget()
                used_percent = 0.0
                if budget_usd and budget_usd > 0:
                    used_percent = (summary.total_cost_usd / budget_usd) * 100

                result[name] = {
                    "total_input_tokens": summary.total_input_tokens,
                    "total_output_tokens": summary.total_output_tokens,
                    "total_cost_usd": summary.total_cost_usd,
                    "call_count": summary.calls_count,
                    "budget_usd": budget_usd,
                    "budget_remaining_usd": remaining,
                    "budget_used_percent": round(used_percent, 1),
                    "budget_exceeded": tracker.is_budget_exceeded(),
                    "by_provider": summary.by_provider,
                    "by_layer": summary.by_layer,
                }
            return result

    def reset_all(self) -> None:
        """Reset all trackers."""
        with self._lock:
            for tracker in self._trackers.values():
                tracker.reset()


# Global registry instance
_global_registry: Optional[TokenTrackerRegistry] = None


def get_token_tracker_registry() -> TokenTrackerRegistry:
    """Get or create the global token tracker registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = TokenTrackerRegistry()
        # Register the global tracker if it exists
        if _global_tracker is not None:
            _global_registry.register("default", _global_tracker)
    return _global_registry


def reset_token_tracker_registry() -> None:
    """Reset the global registry (for testing)."""
    global _global_registry
    if _global_registry:
        _global_registry.reset_all()
    _global_registry = None


# =============================================================================
# Run Cost Tracker Context Manager (BG-3)
# =============================================================================

@dataclass
class RunCostSummary:
    """Summary of costs for a pipeline run."""
    run_id: str
    job_id: Optional[str]
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    calls_count: int
    duration_seconds: float
    by_layer: Dict[str, Dict[str, Any]]
    by_provider: Dict[str, Dict[str, Any]]


class RunCostTracker:
    """
    Context manager for tracking costs of a full pipeline run.

    Provides a clean way to track all LLM costs within a pipeline execution
    and get a summary when the run completes.

    Usage:
        with RunCostTracker(tracker, run_id="run_123", job_id="job_456") as run:
            # All track_usage calls within this block will be associated
            # with run_id="run_123" and job_id="job_456"
            response = llm.invoke(messages)
            run.track_response(provider="openai", response=response, layer="layer2")

        # After the context exits, get the summary
        print(f"Run cost: ${run.summary.total_cost_usd:.4f}")

    Alternative usage with automatic callback:
        with RunCostTracker(tracker, run_id="run_123", job_id="job_456") as run:
            callback = run.get_callback(provider="openai", layer="layer2")
            llm = ChatOpenAI(..., callbacks=[callback])
            # LLM calls will be automatically tracked
    """

    def __init__(
        self,
        tracker: TokenTracker,
        run_id: str,
        job_id: Optional[str] = None,
        export_path: Optional[str] = None,
    ):
        """
        Initialize run cost tracker.

        Args:
            tracker: TokenTracker instance to use
            run_id: Unique identifier for this pipeline run
            job_id: Optional job identifier
            export_path: Optional path to export costs when run completes
        """
        self.tracker = tracker
        self.run_id = run_id
        self.job_id = job_id
        self.export_path = export_path
        self._start_time: Optional[datetime] = None
        self._end_time: Optional[datetime] = None
        self._summary: Optional[RunCostSummary] = None

    def __enter__(self) -> "RunCostTracker":
        """Start tracking the run."""
        self._start_time = datetime.utcnow()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Complete run tracking and generate summary."""
        self._end_time = datetime.utcnow()

        # Generate summary
        usage_summary = self.tracker.get_run_summary(self.run_id)
        duration = (self._end_time - self._start_time).total_seconds()

        self._summary = RunCostSummary(
            run_id=self.run_id,
            job_id=self.job_id,
            total_cost_usd=usage_summary.total_cost_usd,
            total_input_tokens=usage_summary.total_input_tokens,
            total_output_tokens=usage_summary.total_output_tokens,
            total_tokens=usage_summary.total_tokens,
            calls_count=usage_summary.calls_count,
            duration_seconds=duration,
            by_layer=usage_summary.by_layer,
            by_provider=usage_summary.by_provider,
        )

        # Export if path specified
        if self.export_path:
            self.tracker.export_run_to_file(self.run_id, self.export_path)

    @property
    def summary(self) -> Optional[RunCostSummary]:
        """Get run summary (available after context exits)."""
        return self._summary

    def track(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        layer: Optional[str] = None,
    ) -> TokenUsage:
        """
        Track token usage for this run.

        Args:
            provider: LLM provider
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            layer: Pipeline layer name

        Returns:
            TokenUsage record
        """
        return self.tracker.track_usage(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            layer=layer,
            run_id=self.run_id,
            job_id=self.job_id,
        )

    def track_response(
        self,
        provider: str,
        response: Any,
        layer: Optional[str] = None,
    ) -> Optional[TokenUsage]:
        """
        Track usage from a LangChain response for this run.

        Args:
            provider: LLM provider
            response: LangChain AIMessage or response object
            layer: Pipeline layer name

        Returns:
            TokenUsage if usage info available, None otherwise
        """
        return self.tracker.track_langchain_response(
            provider=provider,
            response=response,
            layer=layer,
            run_id=self.run_id,
            job_id=self.job_id,
        )

    def get_callback(
        self,
        provider: str,
        layer: Optional[str] = None,
    ) -> TokenTrackingCallback:
        """
        Get a LangChain callback handler for this run.

        Args:
            provider: LLM provider name
            layer: Pipeline layer name

        Returns:
            TokenTrackingCallback configured for this run
        """
        return TokenTrackingCallback(
            tracker=self.tracker,
            provider=provider,
            layer=layer,
            run_id=self.run_id,
            job_id=self.job_id,
        )

    def get_current_cost(self) -> float:
        """Get current cost for this run (can be called during execution)."""
        return self.tracker.get_run_cost(self.run_id)
