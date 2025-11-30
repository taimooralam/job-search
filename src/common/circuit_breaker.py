"""
Circuit Breaker Pattern (Gap CB-1).

Prevents cascading failures by detecting repeated failures and
temporarily stopping calls to unhealthy services.

Usage:
    # Create a circuit breaker for a service
    pdf_breaker = CircuitBreaker(
        name="pdf_service",
        failure_threshold=5,
        recovery_timeout=30.0,
        half_open_max_calls=3,
    )

    # Use as decorator
    @pdf_breaker.protect
    async def call_pdf_service():
        ...

    # Or use as context manager
    async with pdf_breaker:
        await call_pdf_service()

    # Manual use
    if pdf_breaker.can_execute():
        try:
            result = await call_service()
            pdf_breaker.record_success()
        except Exception as e:
            pdf_breaker.record_failure(e)
            raise
"""

import asyncio
import functools
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation, calls pass through
    OPEN = "open"          # Failing, calls rejected immediately
    HALF_OPEN = "half_open"  # Testing recovery, limited calls allowed


class CircuitOpenError(Exception):
    """Raised when circuit is open and calls are rejected."""

    def __init__(
        self,
        breaker_name: str,
        time_remaining: float,
        last_failure: Optional[str] = None
    ):
        self.breaker_name = breaker_name
        self.time_remaining = time_remaining
        self.last_failure = last_failure
        super().__init__(
            f"Circuit '{breaker_name}' is OPEN. "
            f"Retry in {time_remaining:.1f}s. "
            f"Last failure: {last_failure or 'unknown'}"
        )


@dataclass
class CircuitBreakerStats:
    """Statistics for a circuit breaker."""
    state: CircuitState
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_at: Optional[datetime] = None
    last_failure_reason: Optional[str] = None
    last_success_at: Optional[datetime] = None
    last_state_change_at: Optional[datetime] = None
    time_in_current_state_seconds: float = 0.0


@dataclass
class CircuitBreakerConfig:
    """Configuration for a circuit breaker."""
    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 3  # Successes in half-open before closing
    recovery_timeout: float = 30.0  # Seconds before half-open
    half_open_max_calls: int = 3  # Max concurrent calls in half-open
    failure_rate_threshold: float = 0.5  # 50% failure rate triggers open
    min_calls_for_rate: int = 10  # Min calls before using failure rate
    excluded_exceptions: tuple = ()  # Exceptions that don't count as failures


class CircuitBreaker:
    """
    Circuit breaker implementation with async support.

    States:
    - CLOSED: Normal operation, all calls pass through
    - OPEN: Service unhealthy, calls rejected immediately
    - HALF_OPEN: Testing recovery, limited calls allowed

    Transitions:
    - CLOSED -> OPEN: When failure_threshold consecutive failures occur
    - OPEN -> HALF_OPEN: After recovery_timeout seconds
    - HALF_OPEN -> CLOSED: After success_threshold consecutive successes
    - HALF_OPEN -> OPEN: On any failure
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        success_threshold: int = 3,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
        failure_rate_threshold: float = 0.5,
        min_calls_for_rate: int = 10,
        excluded_exceptions: tuple = (),
        on_state_change: Optional[Callable[[str, CircuitState, CircuitState], None]] = None,
    ):
        """
        Initialize circuit breaker.

        Args:
            name: Identifier for this breaker (for logging/metrics)
            failure_threshold: Consecutive failures before opening circuit
            success_threshold: Successes in half-open before closing
            recovery_timeout: Seconds before transitioning from open to half-open
            half_open_max_calls: Max concurrent calls allowed in half-open state
            failure_rate_threshold: Failure rate (0-1) that triggers open state
            min_calls_for_rate: Minimum calls before using failure rate calculation
            excluded_exceptions: Exceptions that don't count as failures
            on_state_change: Callback when state changes (name, old_state, new_state)
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.failure_rate_threshold = failure_rate_threshold
        self.min_calls_for_rate = min_calls_for_rate
        self.excluded_exceptions = excluded_exceptions
        self.on_state_change = on_state_change

        # State tracking
        self._state = CircuitState.CLOSED
        self._lock = threading.RLock()
        self._failure_count = 0
        self._success_count = 0
        self._total_calls = 0
        self._successful_calls = 0
        self._failed_calls = 0
        self._rejected_calls = 0
        self._last_failure_time: Optional[float] = None
        self._last_failure_reason: Optional[str] = None
        self._last_success_time: Optional[float] = None
        self._state_change_time: float = time.time()
        self._half_open_calls = 0  # Current calls in half-open state

    @property
    def state(self) -> CircuitState:
        """Get current state, transitioning to half-open if recovery timeout elapsed."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                elapsed = time.time() - (self._last_failure_time or 0)
                if elapsed >= self.recovery_timeout:
                    self._transition_to(CircuitState.HALF_OPEN)
            return self._state

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self.state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (rejecting calls)."""
        return self.state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing recovery)."""
        return self.state == CircuitState.HALF_OPEN

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state."""
        old_state = self._state
        if old_state == new_state:
            return

        self._state = new_state
        self._state_change_time = time.time()

        # Reset counters on state change
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._half_open_calls = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0
            self._half_open_calls = 0
        elif new_state == CircuitState.OPEN:
            self._half_open_calls = 0

        logger.info(
            f"Circuit '{self.name}' state changed: {old_state.value} -> {new_state.value}"
        )

        # Call state change callback if provided
        if self.on_state_change:
            try:
                self.on_state_change(self.name, old_state, new_state)
            except Exception as e:
                logger.error(f"State change callback failed: {e}")

    def can_execute(self) -> bool:
        """
        Check if a call is allowed to proceed.

        Returns:
            True if call should proceed, False if rejected
        """
        with self._lock:
            current_state = self.state  # This triggers half-open transition if needed

            if current_state == CircuitState.CLOSED:
                return True

            if current_state == CircuitState.OPEN:
                return False

            # Half-open: allow limited calls
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True

            return False

    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            self._total_calls += 1
            self._successful_calls += 1
            self._last_success_time = time.time()
            self._failure_count = 0  # Reset consecutive failures

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                self._half_open_calls = max(0, self._half_open_calls - 1)

                if self._success_count >= self.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
                    logger.info(
                        f"Circuit '{self.name}' recovered after "
                        f"{self._success_count} successful calls"
                    )

    def record_failure(self, exception: Optional[Exception] = None) -> None:
        """
        Record a failed call.

        Args:
            exception: The exception that caused the failure
        """
        # Check if this exception should be excluded
        if exception and isinstance(exception, self.excluded_exceptions):
            return

        with self._lock:
            self._total_calls += 1
            self._failed_calls += 1
            self._failure_count += 1
            self._last_failure_time = time.time()
            self._last_failure_reason = str(exception) if exception else "Unknown"

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open goes back to open
                self._transition_to(CircuitState.OPEN)
                logger.warning(
                    f"Circuit '{self.name}' reopened due to failure: {exception}"
                )
            elif self._state == CircuitState.CLOSED:
                # Check if we should open the circuit
                should_open = False

                # Check consecutive failures
                if self._failure_count >= self.failure_threshold:
                    should_open = True
                    logger.warning(
                        f"Circuit '{self.name}' opening: "
                        f"{self._failure_count} consecutive failures"
                    )

                # Check failure rate
                elif self._total_calls >= self.min_calls_for_rate:
                    failure_rate = self._failed_calls / self._total_calls
                    if failure_rate >= self.failure_rate_threshold:
                        should_open = True
                        logger.warning(
                            f"Circuit '{self.name}' opening: "
                            f"failure rate {failure_rate:.1%} >= {self.failure_rate_threshold:.1%}"
                        )

                if should_open:
                    self._transition_to(CircuitState.OPEN)

    def record_rejection(self) -> None:
        """Record a rejected call (when circuit is open)."""
        with self._lock:
            self._rejected_calls += 1

    def get_time_remaining(self) -> float:
        """Get seconds remaining before circuit transitions to half-open."""
        with self._lock:
            if self._state != CircuitState.OPEN:
                return 0.0

            elapsed = time.time() - (self._last_failure_time or 0)
            remaining = self.recovery_timeout - elapsed
            return max(0.0, remaining)

    def get_stats(self) -> CircuitBreakerStats:
        """Get current circuit breaker statistics."""
        with self._lock:
            return CircuitBreakerStats(
                state=self._state,
                total_calls=self._total_calls,
                successful_calls=self._successful_calls,
                failed_calls=self._failed_calls,
                rejected_calls=self._rejected_calls,
                consecutive_failures=self._failure_count,
                consecutive_successes=self._success_count,
                last_failure_at=datetime.fromtimestamp(self._last_failure_time) if self._last_failure_time else None,
                last_failure_reason=self._last_failure_reason,
                last_success_at=datetime.fromtimestamp(self._last_success_time) if self._last_success_time else None,
                last_state_change_at=datetime.fromtimestamp(self._state_change_time),
                time_in_current_state_seconds=time.time() - self._state_change_time,
            )

    def reset(self) -> None:
        """Reset circuit breaker to initial closed state."""
        with self._lock:
            old_state = self._state
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._total_calls = 0
            self._successful_calls = 0
            self._failed_calls = 0
            self._rejected_calls = 0
            self._last_failure_time = None
            self._last_failure_reason = None
            self._last_success_time = None
            self._state_change_time = time.time()
            self._half_open_calls = 0

            if old_state != CircuitState.CLOSED:
                logger.info(f"Circuit '{self.name}' manually reset to CLOSED")

    def force_open(self) -> None:
        """Force circuit to open state (for testing/maintenance)."""
        with self._lock:
            self._transition_to(CircuitState.OPEN)
            self._last_failure_time = time.time()
            logger.info(f"Circuit '{self.name}' manually forced to OPEN")

    def to_dict(self) -> Dict[str, Any]:
        """Export circuit breaker state as dictionary."""
        stats = self.get_stats()
        return {
            "name": self.name,
            "state": stats.state.value,
            "config": {
                "failure_threshold": self.failure_threshold,
                "success_threshold": self.success_threshold,
                "recovery_timeout": self.recovery_timeout,
                "half_open_max_calls": self.half_open_max_calls,
            },
            "stats": {
                "total_calls": stats.total_calls,
                "successful_calls": stats.successful_calls,
                "failed_calls": stats.failed_calls,
                "rejected_calls": stats.rejected_calls,
                "consecutive_failures": stats.consecutive_failures,
                "consecutive_successes": stats.consecutive_successes,
                "last_failure_at": stats.last_failure_at.isoformat() if stats.last_failure_at else None,
                "last_failure_reason": stats.last_failure_reason,
                "last_success_at": stats.last_success_at.isoformat() if stats.last_success_at else None,
            },
            "time_remaining_seconds": self.get_time_remaining(),
        }

    # =========================================================================
    # Decorator Support
    # =========================================================================

    def protect(self, func: Callable) -> Callable:
        """
        Decorator to protect a function with this circuit breaker.

        Usage:
            @breaker.protect
            async def my_function():
                ...
        """
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                if not self.can_execute():
                    self.record_rejection()
                    raise CircuitOpenError(
                        self.name,
                        self.get_time_remaining(),
                        self._last_failure_reason
                    )
                try:
                    result = await func(*args, **kwargs)
                    self.record_success()
                    return result
                except Exception as e:
                    self.record_failure(e)
                    raise
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                if not self.can_execute():
                    self.record_rejection()
                    raise CircuitOpenError(
                        self.name,
                        self.get_time_remaining(),
                        self._last_failure_reason
                    )
                try:
                    result = func(*args, **kwargs)
                    self.record_success()
                    return result
                except Exception as e:
                    self.record_failure(e)
                    raise
            return sync_wrapper

    # =========================================================================
    # Context Manager Support
    # =========================================================================

    def __enter__(self):
        """Enter context manager (sync)."""
        if not self.can_execute():
            self.record_rejection()
            raise CircuitOpenError(
                self.name,
                self.get_time_remaining(),
                self._last_failure_reason
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager (sync)."""
        if exc_type is None:
            self.record_success()
        else:
            self.record_failure(exc_val)
        return False  # Don't suppress exceptions

    async def __aenter__(self):
        """Enter async context manager."""
        if not self.can_execute():
            self.record_rejection()
            raise CircuitOpenError(
                self.name,
                self.get_time_remaining(),
                self._last_failure_reason
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context manager."""
        if exc_type is None:
            self.record_success()
        else:
            self.record_failure(exc_val)
        return False


# =============================================================================
# Circuit Breaker Registry
# =============================================================================

class CircuitBreakerRegistry:
    """
    Global registry for managing multiple circuit breakers.

    Usage:
        registry = get_circuit_breaker_registry()
        pdf_breaker = registry.get_or_create("pdf_service", failure_threshold=5)
        llm_breaker = registry.get_or_create("openai", failure_threshold=3)
    """

    def __init__(self):
        """Initialize the registry."""
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get_or_create(
        self,
        name: str,
        **kwargs,
    ) -> CircuitBreaker:
        """
        Get existing circuit breaker or create a new one.

        Args:
            name: Identifier for the circuit breaker
            **kwargs: Arguments passed to CircuitBreaker constructor

        Returns:
            CircuitBreaker instance
        """
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name=name, **kwargs)
            return self._breakers[name]

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker by name if it exists."""
        with self._lock:
            return self._breakers.get(name)

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get stats for all registered circuit breakers."""
        with self._lock:
            return {
                name: breaker.to_dict()
                for name, breaker in self._breakers.items()
            }

    def reset_all(self) -> None:
        """Reset all circuit breakers to closed state."""
        with self._lock:
            for breaker in self._breakers.values():
                breaker.reset()


# Global registry instance
_global_registry: Optional[CircuitBreakerRegistry] = None


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Get or create the global circuit breaker registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = CircuitBreakerRegistry()
    return _global_registry


def get_circuit_breaker(name: str, **kwargs) -> CircuitBreaker:
    """
    Get or create a circuit breaker from the global registry.

    Args:
        name: Identifier for the circuit breaker
        **kwargs: Configuration options

    Returns:
        CircuitBreaker instance
    """
    registry = get_circuit_breaker_registry()
    return registry.get_or_create(name, **kwargs)


def reset_global_registry() -> None:
    """Reset the global registry (useful for testing)."""
    global _global_registry
    if _global_registry:
        _global_registry.reset_all()
    _global_registry = None


# =============================================================================
# Pre-configured Circuit Breakers
# =============================================================================

def get_pdf_service_breaker() -> CircuitBreaker:
    """Get circuit breaker for PDF service."""
    return get_circuit_breaker(
        "pdf_service",
        failure_threshold=3,
        recovery_timeout=60.0,
        half_open_max_calls=1,
    )


def get_openai_breaker() -> CircuitBreaker:
    """Get circuit breaker for OpenAI API."""
    return get_circuit_breaker(
        "openai",
        failure_threshold=5,
        recovery_timeout=30.0,
        half_open_max_calls=2,
        excluded_exceptions=(ValueError,),  # Don't count validation errors
    )


def get_anthropic_breaker() -> CircuitBreaker:
    """Get circuit breaker for Anthropic API."""
    return get_circuit_breaker(
        "anthropic",
        failure_threshold=5,
        recovery_timeout=30.0,
        half_open_max_calls=2,
        excluded_exceptions=(ValueError,),
    )


def get_firecrawl_breaker() -> CircuitBreaker:
    """Get circuit breaker for FireCrawl API."""
    return get_circuit_breaker(
        "firecrawl",
        failure_threshold=3,
        recovery_timeout=120.0,  # Longer timeout for rate-limited service
        half_open_max_calls=1,
    )
