"""
Unified Metrics Module (Gap OB-1).

Aggregates metrics from all infrastructure components:
- Token Tracker (BG-1): Usage and cost data
- Rate Limiter (BG-2): Request counts and wait times
- Circuit Breaker (CB-1): State and failure counts

Provides a single point of access for metrics dashboards.

Usage:
    from src.common.metrics import get_metrics_collector, MetricsSnapshot

    collector = get_metrics_collector()

    # Get all metrics
    snapshot = collector.get_snapshot()

    # Get specific component metrics
    token_metrics = collector.get_token_metrics()
    rate_metrics = collector.get_rate_limit_metrics()
    circuit_metrics = collector.get_circuit_breaker_metrics()

    # Export for API response
    metrics_dict = snapshot.to_dict()
"""

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import logging

from .token_tracker import (
    get_token_tracker_registry,
    TokenTrackerRegistry,
    TokenTracker,
)
from .rate_limiter import (
    get_rate_limiter_registry,
    RateLimiterRegistry,
    RateLimiter,
)
from .circuit_breaker import (
    get_circuit_breaker_registry,
    CircuitBreakerRegistry,
    CircuitBreaker,
    CircuitState,
)

logger = logging.getLogger(__name__)


@dataclass
class TokenMetrics:
    """Metrics for token usage across providers."""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    by_provider: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    by_layer: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "by_provider": self.by_provider,
            "by_layer": self.by_layer,
        }


@dataclass
class BudgetStatus:
    """Budget status for a single tracker."""
    name: str
    budget_usd: Optional[float] = None
    used_usd: float = 0.0
    remaining_usd: Optional[float] = None
    used_percent: float = 0.0
    is_exceeded: bool = False
    status: str = "ok"  # ok, warning, critical, exceeded

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "budget_usd": self.budget_usd,
            "used_usd": round(self.used_usd, 4),
            "remaining_usd": round(self.remaining_usd, 4) if self.remaining_usd is not None else None,
            "used_percent": round(self.used_percent, 1),
            "is_exceeded": self.is_exceeded,
            "status": self.status,
        }


@dataclass
class BudgetMetrics:
    """Aggregated budget metrics across all trackers."""
    total_budget_usd: Optional[float] = None  # None if any tracker has no budget
    total_used_usd: float = 0.0
    total_remaining_usd: Optional[float] = None
    overall_used_percent: float = 0.0
    trackers_exceeded: int = 0
    trackers_warning: int = 0  # 80-99% usage
    trackers_critical: int = 0  # 90-99% usage
    by_tracker: Dict[str, BudgetStatus] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_budget_usd": round(self.total_budget_usd, 2) if self.total_budget_usd is not None else None,
            "total_used_usd": round(self.total_used_usd, 4),
            "total_remaining_usd": round(self.total_remaining_usd, 4) if self.total_remaining_usd is not None else None,
            "overall_used_percent": round(self.overall_used_percent, 1),
            "trackers_exceeded": self.trackers_exceeded,
            "trackers_warning": self.trackers_warning,
            "trackers_critical": self.trackers_critical,
            "by_tracker": {k: v.to_dict() for k, v in self.by_tracker.items()},
        }


@dataclass
class RateLimitMetrics:
    """Metrics for rate limiting across providers."""
    total_requests: int = 0
    total_waits: int = 0
    total_wait_time_seconds: float = 0.0
    by_provider: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_requests": self.total_requests,
            "total_waits": self.total_waits,
            "total_wait_time_seconds": round(self.total_wait_time_seconds, 2),
            "by_provider": self.by_provider,
        }


@dataclass
class CircuitBreakerMetrics:
    """Metrics for circuit breakers."""
    total_breakers: int = 0
    open_breakers: int = 0
    half_open_breakers: int = 0
    closed_breakers: int = 0
    total_calls: int = 0
    total_failures: int = 0
    total_rejections: int = 0
    by_service: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_breakers": self.total_breakers,
            "open_breakers": self.open_breakers,
            "half_open_breakers": self.half_open_breakers,
            "closed_breakers": self.closed_breakers,
            "total_calls": self.total_calls,
            "total_failures": self.total_failures,
            "total_rejections": self.total_rejections,
            "by_service": self.by_service,
        }


@dataclass
class SystemHealth:
    """Overall system health status."""
    status: str = "healthy"  # healthy, degraded, unhealthy
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status,
            "issues": self.issues,
            "warnings": self.warnings,
        }


@dataclass
class MetricsSnapshot:
    """Complete metrics snapshot at a point in time."""
    timestamp: datetime
    tokens: TokenMetrics
    rate_limits: RateLimitMetrics
    circuit_breakers: CircuitBreakerMetrics
    system_health: SystemHealth
    budget: Optional[BudgetMetrics] = None
    uptime_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        result = {
            "timestamp": self.timestamp.isoformat(),
            "uptime_seconds": round(self.uptime_seconds, 1),
            "system_health": self.system_health.to_dict(),
            "tokens": self.tokens.to_dict(),
            "rate_limits": self.rate_limits.to_dict(),
            "circuit_breakers": self.circuit_breakers.to_dict(),
        }
        if self.budget:
            result["budget"] = self.budget.to_dict()
        return result


class MetricsCollector:
    """
    Unified metrics collector for all infrastructure components.

    Aggregates data from:
    - TokenTrackerRegistry: Token usage and costs
    - RateLimiterRegistry: Request counts and rate limiting
    - CircuitBreakerRegistry: Circuit states and failures
    """

    def __init__(
        self,
        token_registry: Optional[TokenTrackerRegistry] = None,
        rate_registry: Optional[RateLimiterRegistry] = None,
        circuit_registry: Optional[CircuitBreakerRegistry] = None,
    ):
        """
        Initialize metrics collector.

        Args:
            token_registry: Optional token tracker registry (uses global if None)
            rate_registry: Optional rate limiter registry (uses global if None)
            circuit_registry: Optional circuit breaker registry (uses global if None)
        """
        self._token_registry = token_registry
        self._rate_registry = rate_registry
        self._circuit_registry = circuit_registry
        self._start_time = time.time()
        self._lock = threading.Lock()

    @property
    def token_registry(self) -> TokenTrackerRegistry:
        """Get token tracker registry."""
        if self._token_registry is None:
            self._token_registry = get_token_tracker_registry()
        return self._token_registry

    @property
    def rate_registry(self) -> RateLimiterRegistry:
        """Get rate limiter registry."""
        if self._rate_registry is None:
            self._rate_registry = get_rate_limiter_registry()
        return self._rate_registry

    @property
    def circuit_registry(self) -> CircuitBreakerRegistry:
        """Get circuit breaker registry."""
        if self._circuit_registry is None:
            self._circuit_registry = get_circuit_breaker_registry()
        return self._circuit_registry

    def get_token_metrics(self) -> TokenMetrics:
        """
        Collect token usage metrics from all trackers.

        Returns:
            TokenMetrics with aggregated token data
        """
        metrics = TokenMetrics()

        try:
            all_stats = self.token_registry.get_all_stats()

            for tracker_name, stats in all_stats.items():
                # Aggregate totals
                provider_input = stats.get("total_input_tokens", 0)
                provider_output = stats.get("total_output_tokens", 0)
                provider_cost = stats.get("total_cost_usd", 0.0)

                metrics.total_input_tokens += provider_input
                metrics.total_output_tokens += provider_output
                metrics.total_cost_usd += provider_cost

                # Store by provider
                metrics.by_provider[tracker_name] = {
                    "input_tokens": provider_input,
                    "output_tokens": provider_output,
                    "cost_usd": round(provider_cost, 4),
                    "call_count": stats.get("call_count", 0),
                }

                # Aggregate by layer if available
                by_layer = stats.get("by_layer", {})
                for layer, layer_data in by_layer.items():
                    if layer not in metrics.by_layer:
                        metrics.by_layer[layer] = {
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "cost_usd": 0.0,
                        }
                    metrics.by_layer[layer]["input_tokens"] += layer_data.get("input_tokens", 0)
                    metrics.by_layer[layer]["output_tokens"] += layer_data.get("output_tokens", 0)
                    metrics.by_layer[layer]["cost_usd"] += layer_data.get("cost_usd", 0.0)

        except Exception as e:
            logger.error(f"Failed to collect token metrics: {e}")

        return metrics

    def get_rate_limit_metrics(self) -> RateLimitMetrics:
        """
        Collect rate limiting metrics from all limiters.

        Returns:
            RateLimitMetrics with aggregated rate data
        """
        metrics = RateLimitMetrics()

        try:
            all_stats = self.rate_registry.get_all_stats()

            for provider, data in all_stats.items():
                stats = data.get("stats", {})

                # Aggregate totals
                requests = stats.get("total_requests", 0)
                waits = stats.get("waits_count", 0)
                wait_time = stats.get("total_wait_time_seconds", 0.0)

                metrics.total_requests += requests
                metrics.total_waits += waits
                metrics.total_wait_time_seconds += wait_time

                # Store by provider
                metrics.by_provider[provider] = {
                    "total_requests": requests,
                    "requests_today": stats.get("requests_today", 0),
                    "requests_this_minute": stats.get("requests_this_minute", 0),
                    "waits_count": waits,
                    "wait_time_seconds": round(wait_time, 2),
                    "remaining_daily": data.get("remaining_daily"),
                    "daily_limit": data.get("daily_limit"),
                    "requests_per_minute": data.get("requests_per_minute"),
                }

        except Exception as e:
            logger.error(f"Failed to collect rate limit metrics: {e}")

        return metrics

    def get_circuit_breaker_metrics(self) -> CircuitBreakerMetrics:
        """
        Collect circuit breaker metrics from all breakers.

        Returns:
            CircuitBreakerMetrics with aggregated circuit data
        """
        metrics = CircuitBreakerMetrics()

        try:
            all_stats = self.circuit_registry.get_all_stats()

            for service, data in all_stats.items():
                state = data.get("state", "closed")
                stats = data.get("stats", {})

                # Count breaker states
                metrics.total_breakers += 1
                if state == CircuitState.OPEN.value:
                    metrics.open_breakers += 1
                elif state == CircuitState.HALF_OPEN.value:
                    metrics.half_open_breakers += 1
                else:
                    metrics.closed_breakers += 1

                # Aggregate call stats
                calls = stats.get("total_calls", 0)
                failures = stats.get("failed_calls", 0)
                rejections = stats.get("rejected_calls", 0)

                metrics.total_calls += calls
                metrics.total_failures += failures
                metrics.total_rejections += rejections

                # Store by service
                metrics.by_service[service] = {
                    "state": state,
                    "total_calls": calls,
                    "successful_calls": stats.get("successful_calls", 0),
                    "failed_calls": failures,
                    "rejected_calls": rejections,
                    "consecutive_failures": stats.get("consecutive_failures", 0),
                    "last_failure_at": stats.get("last_failure_at"),
                    "last_failure_reason": stats.get("last_failure_reason"),
                    "time_remaining_seconds": data.get("time_remaining_seconds", 0),
                    "config": data.get("config", {}),
                }

        except Exception as e:
            logger.error(f"Failed to collect circuit breaker metrics: {e}")

        return metrics

    def get_system_health(self) -> SystemHealth:
        """
        Determine overall system health based on metrics.

        Returns:
            SystemHealth with status and any issues/warnings
        """
        health = SystemHealth()

        try:
            # Check circuit breakers
            circuit_metrics = self.get_circuit_breaker_metrics()
            if circuit_metrics.open_breakers > 0:
                for service, data in circuit_metrics.by_service.items():
                    if data["state"] == CircuitState.OPEN.value:
                        health.issues.append(
                            f"Circuit breaker '{service}' is OPEN: {data['last_failure_reason']}"
                        )
                health.status = "unhealthy"

            if circuit_metrics.half_open_breakers > 0:
                for service, data in circuit_metrics.by_service.items():
                    if data["state"] == CircuitState.HALF_OPEN.value:
                        health.warnings.append(
                            f"Circuit breaker '{service}' is recovering (HALF_OPEN)"
                        )
                if health.status == "healthy":
                    health.status = "degraded"

            # Check rate limits
            rate_metrics = self.get_rate_limit_metrics()
            for provider, data in rate_metrics.by_provider.items():
                remaining = data.get("remaining_daily")
                daily_limit = data.get("daily_limit")
                if remaining is not None and daily_limit is not None:
                    usage_percent = ((daily_limit - remaining) / daily_limit) * 100
                    if usage_percent >= 90:
                        health.warnings.append(
                            f"Rate limit for '{provider}' at {usage_percent:.0f}% "
                            f"({remaining} remaining)"
                        )
                        if health.status == "healthy":
                            health.status = "degraded"
                    elif usage_percent >= 100:
                        health.issues.append(
                            f"Rate limit for '{provider}' EXHAUSTED (0 remaining)"
                        )
                        health.status = "unhealthy"

            # Check token budget
            token_metrics = self.get_token_metrics()
            # Budget warnings would come from individual trackers
            # Add check if total cost exceeds configured threshold
            # (This would need budget config from Config class)

        except Exception as e:
            logger.error(f"Failed to determine system health: {e}")
            health.issues.append(f"Health check error: {str(e)}")
            health.status = "unhealthy"

        return health

    def get_budget_metrics(self) -> BudgetMetrics:
        """
        Collect budget metrics from all token trackers.

        Returns:
            BudgetMetrics with budget status for each tracker
        """
        metrics = BudgetMetrics()

        try:
            all_stats = self.token_registry.get_all_stats()

            has_unlimited_tracker = False
            total_budget = 0.0
            total_remaining = 0.0

            for tracker_name, stats in all_stats.items():
                budget_usd = stats.get("budget_usd")
                used_usd = stats.get("total_cost_usd", 0.0)
                remaining_usd = stats.get("budget_remaining_usd")
                used_percent = stats.get("budget_used_percent", 0.0)
                is_exceeded = stats.get("budget_exceeded", False)

                # Determine status based on usage percentage
                if budget_usd is None:
                    status = "ok"  # Unlimited budget
                    has_unlimited_tracker = True
                elif is_exceeded:
                    status = "exceeded"
                    metrics.trackers_exceeded += 1
                elif used_percent >= 90:
                    status = "critical"
                    metrics.trackers_critical += 1
                elif used_percent >= 80:
                    status = "warning"
                    metrics.trackers_warning += 1
                else:
                    status = "ok"

                # Create budget status for this tracker
                budget_status = BudgetStatus(
                    name=tracker_name,
                    budget_usd=budget_usd,
                    used_usd=used_usd,
                    remaining_usd=remaining_usd,
                    used_percent=used_percent,
                    is_exceeded=is_exceeded,
                    status=status,
                )
                metrics.by_tracker[tracker_name] = budget_status

                # Aggregate totals
                metrics.total_used_usd += used_usd
                if budget_usd is not None:
                    total_budget += budget_usd
                if remaining_usd is not None:
                    total_remaining += remaining_usd

            # Set total budget (None if any tracker is unlimited)
            if not has_unlimited_tracker and total_budget > 0:
                metrics.total_budget_usd = total_budget
                metrics.total_remaining_usd = total_remaining
                metrics.overall_used_percent = (metrics.total_used_usd / total_budget) * 100

        except Exception as e:
            logger.error(f"Failed to collect budget metrics: {e}")

        return metrics

    def get_snapshot(self) -> MetricsSnapshot:
        """
        Get complete metrics snapshot.

        Returns:
            MetricsSnapshot with all current metrics
        """
        with self._lock:
            return MetricsSnapshot(
                timestamp=datetime.utcnow(),
                tokens=self.get_token_metrics(),
                rate_limits=self.get_rate_limit_metrics(),
                circuit_breakers=self.get_circuit_breaker_metrics(),
                system_health=self.get_system_health(),
                budget=self.get_budget_metrics(),
                uptime_seconds=time.time() - self._start_time,
            )

    def reset(self) -> None:
        """Reset all metrics (for testing)."""
        self._start_time = time.time()


# =============================================================================
# Global Collector Instance
# =============================================================================

_global_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get or create the global metrics collector."""
    global _global_collector
    if _global_collector is None:
        _global_collector = MetricsCollector()
    return _global_collector


def reset_metrics_collector() -> None:
    """Reset the global metrics collector (for testing)."""
    global _global_collector
    if _global_collector:
        _global_collector.reset()
    _global_collector = None
