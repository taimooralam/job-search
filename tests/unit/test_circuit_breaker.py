"""
Unit tests for src/common/circuit_breaker.py

Tests the circuit breaker pattern implementation including:
- State transitions (CLOSED -> OPEN -> HALF_OPEN -> CLOSED)
- Failure threshold detection
- Success threshold in half-open state
- Recovery timeout behavior
- CircuitOpenError handling
- Decorator support (sync and async)
- Context manager support (sync and async)
- CircuitBreakerRegistry management
- Pre-configured breakers
- Thread safety
"""

import asyncio
import pytest
import threading
import time
from datetime import datetime
from unittest.mock import MagicMock, patch, call

from src.common.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitOpenError,
    CircuitState,
    CircuitBreakerStats,
    CircuitBreakerConfig,
    get_circuit_breaker,
    get_circuit_breaker_registry,
    reset_global_registry,
    get_pdf_service_breaker,
    get_openai_breaker,
    get_anthropic_breaker,
    get_firecrawl_breaker,
)


class TestCircuitState:
    """Tests for CircuitState enum."""

    def test_state_values(self):
        """Should have correct string values."""
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"


class TestCircuitOpenError:
    """Tests for CircuitOpenError exception."""

    def test_error_message_formatting(self):
        """Should format error message with circuit name and time remaining."""
        error = CircuitOpenError(
            breaker_name="pdf_service",
            time_remaining=45.5,
            last_failure="Connection timeout"
        )

        assert error.breaker_name == "pdf_service"
        assert error.time_remaining == 45.5
        assert error.last_failure == "Connection timeout"
        assert "pdf_service" in str(error)
        assert "45.5s" in str(error)
        assert "Connection timeout" in str(error)

    def test_error_without_last_failure(self):
        """Should handle missing last_failure gracefully."""
        error = CircuitOpenError("test_service", 30.0, None)

        assert error.last_failure is None
        assert "unknown" in str(error)

    def test_error_attributes_accessible(self):
        """Error attributes should be accessible for handling."""
        error = CircuitOpenError("api_service", 60.0, "Rate limit exceeded")

        assert error.breaker_name == "api_service"
        assert error.time_remaining == 60.0
        assert error.last_failure == "Rate limit exceeded"


class TestCircuitBreakerStats:
    """Tests for CircuitBreakerStats dataclass."""

    def test_stats_initialization(self):
        """Should initialize with correct defaults."""
        stats = CircuitBreakerStats(state=CircuitState.CLOSED)

        assert stats.state == CircuitState.CLOSED
        assert stats.total_calls == 0
        assert stats.successful_calls == 0
        assert stats.failed_calls == 0
        assert stats.rejected_calls == 0
        assert stats.consecutive_failures == 0
        assert stats.consecutive_successes == 0
        assert stats.last_failure_at is None
        assert stats.last_success_at is None


class TestCircuitBreakerConfig:
    """Tests for CircuitBreakerConfig dataclass."""

    def test_config_defaults(self):
        """Should have sensible default values."""
        config = CircuitBreakerConfig()

        assert config.failure_threshold == 5
        assert config.success_threshold == 3
        assert config.recovery_timeout == 30.0
        assert config.half_open_max_calls == 3
        assert config.failure_rate_threshold == 0.5
        assert config.min_calls_for_rate == 10
        assert config.excluded_exceptions == ()


class TestCircuitBreakerInit:
    """Tests for CircuitBreaker initialization."""

    def test_init_with_defaults(self):
        """Should initialize with default configuration."""
        breaker = CircuitBreaker(name="test")

        assert breaker.name == "test"
        assert breaker.failure_threshold == 5
        assert breaker.success_threshold == 3
        assert breaker.recovery_timeout == 30.0
        assert breaker.half_open_max_calls == 3
        assert breaker.is_closed is True

    def test_init_with_custom_config(self):
        """Should accept custom configuration."""
        breaker = CircuitBreaker(
            name="custom",
            failure_threshold=10,
            success_threshold=5,
            recovery_timeout=60.0,
            half_open_max_calls=2,
            failure_rate_threshold=0.7,
            min_calls_for_rate=20,
        )

        assert breaker.failure_threshold == 10
        assert breaker.success_threshold == 5
        assert breaker.recovery_timeout == 60.0
        assert breaker.half_open_max_calls == 2
        assert breaker.failure_rate_threshold == 0.7
        assert breaker.min_calls_for_rate == 20

    def test_init_with_excluded_exceptions(self):
        """Should accept excluded exceptions configuration."""
        breaker = CircuitBreaker(
            name="test",
            excluded_exceptions=(ValueError, TypeError)
        )

        assert breaker.excluded_exceptions == (ValueError, TypeError)

    def test_init_with_state_change_callback(self):
        """Should accept on_state_change callback."""
        callback = MagicMock()
        breaker = CircuitBreaker(name="test", on_state_change=callback)

        assert breaker.on_state_change == callback


class TestCircuitBreakerStateProperties:
    """Tests for state property accessors."""

    @pytest.fixture
    def breaker(self):
        """Create a basic breaker instance."""
        return CircuitBreaker(name="test", failure_threshold=3)

    def test_is_closed_when_initialized(self, breaker):
        """Should start in CLOSED state."""
        assert breaker.is_closed is True
        assert breaker.is_open is False
        assert breaker.is_half_open is False
        assert breaker.state == CircuitState.CLOSED

    @patch("time.time")
    def test_is_open_after_threshold_failures(self, mock_time, breaker):
        """Should transition to OPEN after failure threshold."""
        mock_time.return_value = 1000.0

        # Cause failures to exceed threshold
        for _ in range(3):
            breaker.record_failure(Exception("Test failure"))

        assert breaker.is_open is True
        assert breaker.is_closed is False
        assert breaker.is_half_open is False
        assert breaker.state == CircuitState.OPEN

    @patch("time.time")
    def test_is_half_open_after_recovery_timeout(self, mock_time, breaker):
        """Should transition to HALF_OPEN after recovery timeout."""
        # Open the circuit at t=1000
        mock_time.return_value = 1000.0
        for _ in range(3):
            breaker.record_failure(Exception("Test"))

        assert breaker.is_open is True

        # Jump past recovery timeout (30s default)
        mock_time.return_value = 1031.0

        # Accessing state should trigger transition
        assert breaker.is_half_open is True
        assert breaker.is_open is False
        assert breaker.is_closed is False
        assert breaker.state == CircuitState.HALF_OPEN


class TestCircuitBreakerStateTransitions:
    """Tests for state transition logic."""

    @pytest.fixture
    def breaker(self):
        """Create a breaker with low thresholds for testing."""
        return CircuitBreaker(
            name="test",
            failure_threshold=3,
            success_threshold=2,
            recovery_timeout=30.0,
        )

    @patch("time.time")
    def test_transition_closed_to_open_on_consecutive_failures(self, mock_time, breaker):
        """Should open circuit after consecutive failures."""
        mock_time.return_value = 1000.0

        # Record failures
        breaker.record_failure(Exception("Fail 1"))
        breaker.record_failure(Exception("Fail 2"))
        assert breaker.is_closed is True

        breaker.record_failure(Exception("Fail 3"))
        assert breaker.is_open is True

    @patch("time.time")
    def test_transition_open_to_half_open_on_timeout(self, mock_time, breaker):
        """Should transition to half-open after recovery timeout."""
        # Open the circuit
        mock_time.return_value = 1000.0
        for _ in range(3):
            breaker.record_failure(Exception("Test"))

        assert breaker.is_open is True

        # Wait for recovery timeout
        mock_time.return_value = 1030.0
        assert breaker.state == CircuitState.HALF_OPEN

    @patch("time.time")
    def test_transition_half_open_to_closed_on_success(self, mock_time, breaker):
        """Should close circuit after success threshold in half-open."""
        mock_time.return_value = 1000.0

        # Open the circuit
        for _ in range(3):
            breaker.record_failure(Exception("Test"))

        # Transition to half-open
        mock_time.return_value = 1031.0
        assert breaker.state == CircuitState.HALF_OPEN

        # Record successes
        breaker.record_success()
        assert breaker.is_half_open is True

        breaker.record_success()
        assert breaker.is_closed is True

    @patch("time.time")
    def test_transition_half_open_to_open_on_failure(self, mock_time, breaker):
        """Should reopen circuit on any failure in half-open state."""
        mock_time.return_value = 1000.0

        # Open the circuit
        for _ in range(3):
            breaker.record_failure(Exception("Test"))

        # Transition to half-open
        mock_time.return_value = 1031.0
        assert breaker.state == CircuitState.HALF_OPEN

        # One success followed by failure
        breaker.record_success()
        assert breaker.is_half_open is True

        breaker.record_failure(Exception("Failed again"))
        assert breaker.is_open is True

    @patch("time.time")
    def test_success_resets_consecutive_failures_in_closed(self, mock_time, breaker):
        """Should reset consecutive failures on success in closed state."""
        mock_time.return_value = 1000.0

        # Some failures
        breaker.record_failure(Exception("Fail 1"))
        breaker.record_failure(Exception("Fail 2"))
        assert breaker._failure_count == 2

        # Success resets
        breaker.record_success()
        assert breaker._failure_count == 0
        assert breaker.is_closed is True


class TestCircuitBreakerFailureRateThreshold:
    """Tests for failure rate threshold detection."""

    @patch("time.time")
    def test_opens_when_failure_rate_exceeds_threshold(self, mock_time):
        """Should open circuit when failure rate exceeds threshold."""
        mock_time.return_value = 1000.0

        breaker = CircuitBreaker(
            name="test",
            failure_threshold=100,  # High threshold to test rate
            failure_rate_threshold=0.5,
            min_calls_for_rate=10,
        )

        # Need to interleave to avoid consecutive failures triggering first
        # Pattern: F, S, F, S, F, S, F, S, F, S, F, F = 7F, 5S = 58% failure rate
        breaker.record_failure(Exception("Test"))
        breaker.record_success()
        breaker.record_failure(Exception("Test"))
        breaker.record_success()
        breaker.record_failure(Exception("Test"))
        breaker.record_success()
        breaker.record_failure(Exception("Test"))
        breaker.record_success()
        breaker.record_failure(Exception("Test"))
        breaker.record_success()
        breaker.record_failure(Exception("Test"))
        breaker.record_failure(Exception("Test"))

        # Should be open due to 58% > 50% threshold (12 total calls, 7 failures)
        assert breaker.is_open is True

    @patch("time.time")
    def test_does_not_open_before_min_calls(self, mock_time):
        """Should not use failure rate until min_calls_for_rate reached."""
        mock_time.return_value = 1000.0

        breaker = CircuitBreaker(
            name="test",
            failure_threshold=100,
            failure_rate_threshold=0.5,
            min_calls_for_rate=10,
        )

        # Only 5 calls (< min), all failures = 100% failure rate
        for _ in range(5):
            breaker.record_failure(Exception("Test"))

        # Should still be closed (not enough calls)
        assert breaker.is_closed is True

    @patch("time.time")
    def test_stays_closed_when_failure_rate_below_threshold(self, mock_time):
        """Should stay closed when failure rate below threshold."""
        mock_time.return_value = 1000.0

        breaker = CircuitBreaker(
            name="test",
            failure_threshold=100,
            failure_rate_threshold=0.5,
            min_calls_for_rate=10,
        )

        # 4 failures + 6 successes = 40% failure rate
        for _ in range(4):
            breaker.record_failure(Exception("Test"))
        for _ in range(6):
            breaker.record_success()

        # Should stay closed (40% < 50%)
        assert breaker.is_closed is True


class TestCircuitBreakerExcludedExceptions:
    """Tests for excluded exceptions handling."""

    @patch("time.time")
    def test_excluded_exceptions_dont_count_as_failures(self, mock_time):
        """Should not count excluded exceptions as failures."""
        mock_time.return_value = 1000.0

        breaker = CircuitBreaker(
            name="test",
            failure_threshold=3,
            excluded_exceptions=(ValueError,)
        )

        # Record excluded exceptions
        for _ in range(5):
            breaker.record_failure(ValueError("Validation error"))

        # Should still be closed
        assert breaker.is_closed is True
        assert breaker._failure_count == 0

    @patch("time.time")
    def test_non_excluded_exceptions_count_as_failures(self, mock_time):
        """Should count non-excluded exceptions as failures."""
        mock_time.return_value = 1000.0

        breaker = CircuitBreaker(
            name="test",
            failure_threshold=3,
            excluded_exceptions=(ValueError,)
        )

        # Mix of excluded and non-excluded
        breaker.record_failure(ValueError("Excluded"))
        breaker.record_failure(RuntimeError("Not excluded"))
        breaker.record_failure(ValueError("Excluded"))
        breaker.record_failure(RuntimeError("Not excluded"))

        # Only 2 non-excluded failures counted
        assert breaker._failure_count == 2
        assert breaker.is_closed is True

        # One more non-excluded should open
        breaker.record_failure(RuntimeError("Third"))
        assert breaker.is_open is True


class TestCircuitBreakerCanExecute:
    """Tests for can_execute() method."""

    @pytest.fixture
    def breaker(self):
        """Create a breaker instance."""
        return CircuitBreaker(name="test", failure_threshold=2, half_open_max_calls=2)

    @patch("time.time")
    def test_can_execute_returns_true_when_closed(self, mock_time, breaker):
        """Should allow execution when circuit is closed."""
        mock_time.return_value = 1000.0
        assert breaker.can_execute() is True

    @patch("time.time")
    def test_can_execute_returns_false_when_open(self, mock_time, breaker):
        """Should reject execution when circuit is open."""
        mock_time.return_value = 1000.0

        # Open the circuit
        breaker.record_failure(Exception("Fail 1"))
        breaker.record_failure(Exception("Fail 2"))

        assert breaker.can_execute() is False

    @patch("time.time")
    def test_can_execute_allows_limited_calls_in_half_open(self, mock_time, breaker):
        """Should allow limited concurrent calls in half-open state."""
        mock_time.return_value = 1000.0

        # Open the circuit
        breaker.record_failure(Exception("Fail 1"))
        breaker.record_failure(Exception("Fail 2"))

        # Transition to half-open
        mock_time.return_value = 1031.0
        assert breaker.state == CircuitState.HALF_OPEN

        # Should allow up to half_open_max_calls (2)
        assert breaker.can_execute() is True
        assert breaker.can_execute() is True
        assert breaker.can_execute() is False  # 3rd call rejected

    @patch("time.time")
    def test_can_execute_resets_half_open_count_on_success(self, mock_time, breaker):
        """Should decrement half-open call count on success."""
        mock_time.return_value = 1000.0

        # Open and transition to half-open
        breaker.record_failure(Exception("Fail 1"))
        breaker.record_failure(Exception("Fail 2"))
        mock_time.return_value = 1031.0
        assert breaker.state == CircuitState.HALF_OPEN

        # Take 2 slots
        breaker.can_execute()
        breaker.can_execute()
        assert breaker.can_execute() is False

        # Record success should free a slot
        breaker.record_success()
        assert breaker.can_execute() is True


class TestCircuitBreakerRecordRejection:
    """Tests for record_rejection() method."""

    @patch("time.time")
    def test_record_rejection_increments_counter(self, mock_time):
        """Should track rejected calls."""
        mock_time.return_value = 1000.0

        breaker = CircuitBreaker(name="test", failure_threshold=2)

        # Open the circuit
        breaker.record_failure(Exception("Fail 1"))
        breaker.record_failure(Exception("Fail 2"))

        # Record rejections
        breaker.record_rejection()
        breaker.record_rejection()
        breaker.record_rejection()

        stats = breaker.get_stats()
        assert stats.rejected_calls == 3


class TestCircuitBreakerGetTimeRemaining:
    """Tests for get_time_remaining() method."""

    @patch("time.time")
    def test_get_time_remaining_when_closed(self, mock_time):
        """Should return 0 when circuit is closed."""
        mock_time.return_value = 1000.0
        breaker = CircuitBreaker(name="test")

        assert breaker.get_time_remaining() == 0.0

    @patch("time.time")
    def test_get_time_remaining_when_open(self, mock_time):
        """Should return seconds until recovery when open."""
        breaker = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout=60.0)

        # Open at t=1000
        mock_time.return_value = 1000.0
        breaker.record_failure(Exception("Fail 1"))
        breaker.record_failure(Exception("Fail 2"))

        # Check at t=1020 (20s elapsed, 40s remaining)
        mock_time.return_value = 1020.0
        remaining = breaker.get_time_remaining()

        assert remaining == pytest.approx(40.0)

    @patch("time.time")
    def test_get_time_remaining_never_negative(self, mock_time):
        """Should return 0 when recovery time has passed."""
        breaker = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout=30.0)

        # Open at t=1000
        mock_time.return_value = 1000.0
        breaker.record_failure(Exception("Fail 1"))
        breaker.record_failure(Exception("Fail 2"))

        # Check at t=1100 (past recovery time)
        mock_time.return_value = 1100.0
        remaining = breaker.get_time_remaining()

        assert remaining == 0.0


class TestCircuitBreakerGetStats:
    """Tests for get_stats() method."""

    @patch("time.time")
    def test_get_stats_returns_complete_state(self, mock_time):
        """Should return CircuitBreakerStats with all fields."""
        mock_time.return_value = 1000.0

        breaker = CircuitBreaker(name="test", failure_threshold=3)

        # Record some activity
        breaker.record_success()
        breaker.record_success()
        breaker.record_failure(Exception("Test failure"))

        stats = breaker.get_stats()

        assert isinstance(stats, CircuitBreakerStats)
        assert stats.state == CircuitState.CLOSED
        assert stats.total_calls == 3
        assert stats.successful_calls == 2
        assert stats.failed_calls == 1
        assert stats.consecutive_failures == 1
        assert stats.last_failure_reason == "Test failure"
        assert stats.last_failure_at is not None
        assert stats.last_success_at is not None


class TestCircuitBreakerReset:
    """Tests for reset() method."""

    @patch("time.time")
    def test_reset_returns_to_closed_state(self, mock_time):
        """Should reset circuit to closed state."""
        mock_time.return_value = 1000.0

        breaker = CircuitBreaker(name="test", failure_threshold=2)

        # Open the circuit
        breaker.record_failure(Exception("Fail 1"))
        breaker.record_failure(Exception("Fail 2"))
        assert breaker.is_open is True

        # Reset
        breaker.reset()

        assert breaker.is_closed is True
        assert breaker._failure_count == 0
        assert breaker._success_count == 0

    @patch("time.time")
    def test_reset_clears_all_counters(self, mock_time):
        """Should clear all tracking counters."""
        mock_time.return_value = 1000.0

        breaker = CircuitBreaker(name="test")

        # Record activity
        breaker.record_success()
        breaker.record_failure(Exception("Test"))
        breaker.record_rejection()

        # Reset
        breaker.reset()

        stats = breaker.get_stats()
        assert stats.total_calls == 0
        assert stats.successful_calls == 0
        assert stats.failed_calls == 0
        assert stats.rejected_calls == 0
        assert stats.consecutive_failures == 0


class TestCircuitBreakerForceOpen:
    """Tests for force_open() method."""

    @patch("time.time")
    def test_force_open_transitions_to_open(self, mock_time):
        """Should force circuit to open state."""
        mock_time.return_value = 1000.0

        breaker = CircuitBreaker(name="test")
        assert breaker.is_closed is True

        breaker.force_open()

        assert breaker.is_open is True

    @patch("time.time")
    def test_force_open_sets_failure_time(self, mock_time):
        """Should set last failure time for recovery timeout."""
        mock_time.return_value = 1000.0

        breaker = CircuitBreaker(name="test", recovery_timeout=30.0)
        breaker.force_open()

        # Should be able to calculate time remaining
        mock_time.return_value = 1015.0
        remaining = breaker.get_time_remaining()
        assert remaining == pytest.approx(15.0)


class TestCircuitBreakerToDict:
    """Tests for to_dict() export method."""

    @patch("time.time")
    def test_to_dict_includes_all_fields(self, mock_time):
        """Should export complete state as dictionary."""
        mock_time.return_value = 1000.0

        breaker = CircuitBreaker(
            name="test_service",
            failure_threshold=5,
            success_threshold=3,
            recovery_timeout=60.0,
            half_open_max_calls=2,
        )

        breaker.record_success()
        breaker.record_failure(Exception("Test error"))

        result = breaker.to_dict()

        assert result["name"] == "test_service"
        assert result["state"] == "closed"
        assert result["config"]["failure_threshold"] == 5
        assert result["config"]["success_threshold"] == 3
        assert result["config"]["recovery_timeout"] == 60.0
        assert result["config"]["half_open_max_calls"] == 2
        assert result["stats"]["total_calls"] == 2
        assert result["stats"]["successful_calls"] == 1
        assert result["stats"]["failed_calls"] == 1
        assert "time_remaining_seconds" in result


class TestCircuitBreakerStateChangeCallback:
    """Tests for state change callback."""

    @patch("time.time")
    def test_callback_invoked_on_state_change(self, mock_time):
        """Should invoke callback when state changes."""
        mock_time.return_value = 1000.0
        callback = MagicMock()

        breaker = CircuitBreaker(
            name="test",
            failure_threshold=2,
            on_state_change=callback,
        )

        # Trigger state change
        breaker.record_failure(Exception("Fail 1"))
        breaker.record_failure(Exception("Fail 2"))

        # Should have called callback for CLOSED -> OPEN
        callback.assert_called_once_with("test", CircuitState.CLOSED, CircuitState.OPEN)

    @patch("time.time")
    def test_callback_not_invoked_if_state_unchanged(self, mock_time):
        """Should not invoke callback if state doesn't change."""
        mock_time.return_value = 1000.0
        callback = MagicMock()

        breaker = CircuitBreaker(
            name="test",
            failure_threshold=5,
            on_state_change=callback,
        )

        # Record failures but not enough to open
        breaker.record_failure(Exception("Fail 1"))
        breaker.record_failure(Exception("Fail 2"))

        # Should not have called callback
        callback.assert_not_called()

    @patch("time.time")
    def test_callback_exception_handled_gracefully(self, mock_time):
        """Should handle callback exceptions without breaking circuit."""
        mock_time.return_value = 1000.0

        def failing_callback(name, old, new):
            raise RuntimeError("Callback error")

        breaker = CircuitBreaker(
            name="test",
            failure_threshold=2,
            on_state_change=failing_callback,
        )

        # Should not raise despite callback failing
        breaker.record_failure(Exception("Fail 1"))
        breaker.record_failure(Exception("Fail 2"))

        assert breaker.is_open is True


class TestCircuitBreakerDecoratorSync:
    """Tests for protect decorator on synchronous functions."""

    @pytest.fixture
    def breaker(self):
        """Create a breaker for testing."""
        return CircuitBreaker(name="test", failure_threshold=2)

    @patch("time.time")
    def test_decorator_allows_call_when_closed(self, mock_time, breaker):
        """Should allow decorated function to execute when closed."""
        mock_time.return_value = 1000.0

        @breaker.protect
        def protected_function():
            return "success"

        result = protected_function()

        assert result == "success"
        assert breaker.get_stats().successful_calls == 1

    @patch("time.time")
    def test_decorator_raises_circuit_open_when_open(self, mock_time, breaker):
        """Should raise CircuitOpenError when circuit is open."""
        mock_time.return_value = 1000.0

        @breaker.protect
        def protected_function():
            return "success"

        # Open the circuit
        breaker.record_failure(Exception("Fail 1"))
        breaker.record_failure(Exception("Fail 2"))

        # Should raise
        with pytest.raises(CircuitOpenError) as exc_info:
            protected_function()

        assert exc_info.value.breaker_name == "test"
        assert breaker.get_stats().rejected_calls == 1

    @patch("time.time")
    def test_decorator_records_success(self, mock_time, breaker):
        """Should record success when function completes."""
        mock_time.return_value = 1000.0

        @breaker.protect
        def protected_function():
            return 42

        result = protected_function()

        assert result == 42
        assert breaker.get_stats().successful_calls == 1

    @patch("time.time")
    def test_decorator_records_failure_on_exception(self, mock_time, breaker):
        """Should record failure when function raises exception."""
        mock_time.return_value = 1000.0

        @breaker.protect
        def protected_function():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            protected_function()

        assert breaker.get_stats().failed_calls == 1

    @patch("time.time")
    def test_decorator_propagates_exception(self, mock_time, breaker):
        """Should propagate original exception after recording."""
        mock_time.return_value = 1000.0

        @breaker.protect
        def protected_function():
            raise RuntimeError("Original error")

        with pytest.raises(RuntimeError, match="Original error"):
            protected_function()

    @patch("time.time")
    def test_decorator_preserves_function_signature(self, mock_time, breaker):
        """Should preserve original function signature."""
        mock_time.return_value = 1000.0

        @breaker.protect
        def protected_function(a, b, c=10):
            """Test docstring."""
            return a + b + c

        assert protected_function.__name__ == "protected_function"
        assert protected_function.__doc__ == "Test docstring."
        assert protected_function(1, 2) == 13
        assert protected_function(1, 2, c=20) == 23


class TestCircuitBreakerDecoratorAsync:
    """Tests for protect decorator on async functions."""

    @pytest.fixture
    def breaker(self):
        """Create a breaker for testing."""
        return CircuitBreaker(name="test", failure_threshold=2)

    @pytest.mark.asyncio
    @patch("time.time")
    async def test_decorator_allows_async_call_when_closed(self, mock_time, breaker):
        """Should allow decorated async function to execute when closed."""
        mock_time.return_value = 1000.0

        @breaker.protect
        async def protected_async():
            return "async success"

        result = await protected_async()

        assert result == "async success"
        assert breaker.get_stats().successful_calls == 1

    @pytest.mark.asyncio
    @patch("time.time")
    async def test_decorator_raises_circuit_open_for_async(self, mock_time, breaker):
        """Should raise CircuitOpenError for async function when open."""
        mock_time.return_value = 1000.0

        @breaker.protect
        async def protected_async():
            return "success"

        # Open the circuit
        breaker.record_failure(Exception("Fail 1"))
        breaker.record_failure(Exception("Fail 2"))

        # Should raise
        with pytest.raises(CircuitOpenError):
            await protected_async()

        assert breaker.get_stats().rejected_calls == 1

    @pytest.mark.asyncio
    @patch("time.time")
    async def test_decorator_records_async_success(self, mock_time, breaker):
        """Should record success for async function."""
        mock_time.return_value = 1000.0

        @breaker.protect
        async def protected_async():
            await asyncio.sleep(0.001)
            return 42

        result = await protected_async()

        assert result == 42
        assert breaker.get_stats().successful_calls == 1

    @pytest.mark.asyncio
    @patch("time.time")
    async def test_decorator_records_async_failure(self, mock_time, breaker):
        """Should record failure for async function exception."""
        mock_time.return_value = 1000.0

        @breaker.protect
        async def protected_async():
            raise ValueError("Async error")

        with pytest.raises(ValueError):
            await protected_async()

        assert breaker.get_stats().failed_calls == 1


class TestCircuitBreakerContextManagerSync:
    """Tests for context manager (sync)."""

    @pytest.fixture
    def breaker(self):
        """Create a breaker for testing."""
        return CircuitBreaker(name="test", failure_threshold=2)

    @patch("time.time")
    def test_context_manager_allows_entry_when_closed(self, mock_time, breaker):
        """Should allow context entry when closed."""
        mock_time.return_value = 1000.0

        with breaker:
            result = "success"

        assert result == "success"
        assert breaker.get_stats().successful_calls == 1

    @patch("time.time")
    def test_context_manager_raises_when_open(self, mock_time, breaker):
        """Should raise CircuitOpenError on entry when open."""
        mock_time.return_value = 1000.0

        # Open the circuit
        breaker.record_failure(Exception("Fail 1"))
        breaker.record_failure(Exception("Fail 2"))

        # Should raise on entry
        with pytest.raises(CircuitOpenError):
            with breaker:
                pass

        assert breaker.get_stats().rejected_calls == 1

    @patch("time.time")
    def test_context_manager_records_success_on_clean_exit(self, mock_time, breaker):
        """Should record success on clean context exit."""
        mock_time.return_value = 1000.0

        with breaker:
            pass  # Clean exit

        assert breaker.get_stats().successful_calls == 1

    @patch("time.time")
    def test_context_manager_records_failure_on_exception(self, mock_time, breaker):
        """Should record failure when exception raised in context."""
        mock_time.return_value = 1000.0

        with pytest.raises(ValueError):
            with breaker:
                raise ValueError("Context error")

        assert breaker.get_stats().failed_calls == 1

    @patch("time.time")
    def test_context_manager_does_not_suppress_exceptions(self, mock_time, breaker):
        """Should not suppress exceptions from context."""
        mock_time.return_value = 1000.0

        with pytest.raises(RuntimeError, match="Test error"):
            with breaker:
                raise RuntimeError("Test error")


class TestCircuitBreakerContextManagerAsync:
    """Tests for async context manager."""

    @pytest.fixture
    def breaker(self):
        """Create a breaker for testing."""
        return CircuitBreaker(name="test", failure_threshold=2)

    @pytest.mark.asyncio
    @patch("time.time")
    async def test_async_context_manager_allows_entry_when_closed(self, mock_time, breaker):
        """Should allow async context entry when closed."""
        mock_time.return_value = 1000.0

        async with breaker:
            result = "async success"

        assert result == "async success"
        assert breaker.get_stats().successful_calls == 1

    @pytest.mark.asyncio
    @patch("time.time")
    async def test_async_context_manager_raises_when_open(self, mock_time, breaker):
        """Should raise CircuitOpenError on async entry when open."""
        mock_time.return_value = 1000.0

        # Open the circuit
        breaker.record_failure(Exception("Fail 1"))
        breaker.record_failure(Exception("Fail 2"))

        # Should raise on entry
        with pytest.raises(CircuitOpenError):
            async with breaker:
                pass

        assert breaker.get_stats().rejected_calls == 1

    @pytest.mark.asyncio
    @patch("time.time")
    async def test_async_context_manager_records_success(self, mock_time, breaker):
        """Should record success on clean async context exit."""
        mock_time.return_value = 1000.0

        async with breaker:
            await asyncio.sleep(0.001)

        assert breaker.get_stats().successful_calls == 1

    @pytest.mark.asyncio
    @patch("time.time")
    async def test_async_context_manager_records_failure(self, mock_time, breaker):
        """Should record failure on async context exception."""
        mock_time.return_value = 1000.0

        with pytest.raises(ValueError):
            async with breaker:
                raise ValueError("Async context error")

        assert breaker.get_stats().failed_calls == 1


class TestCircuitBreakerRegistry:
    """Tests for CircuitBreakerRegistry class."""

    def test_init_creates_empty_registry(self):
        """Should initialize with no breakers."""
        registry = CircuitBreakerRegistry()

        assert len(registry._breakers) == 0

    def test_get_or_create_returns_new_breaker(self):
        """Should create new breaker if not exists."""
        registry = CircuitBreakerRegistry()

        breaker = registry.get_or_create("test", failure_threshold=10)

        assert breaker is not None
        assert breaker.name == "test"
        assert breaker.failure_threshold == 10

    def test_get_or_create_returns_existing_breaker(self):
        """Should return existing breaker on second call."""
        registry = CircuitBreakerRegistry()

        breaker1 = registry.get_or_create("test")
        breaker2 = registry.get_or_create("test")

        assert breaker1 is breaker2

    def test_get_returns_existing_breaker(self):
        """Should return breaker if exists."""
        registry = CircuitBreakerRegistry()

        registry.get_or_create("test")
        breaker = registry.get("test")

        assert breaker is not None
        assert breaker.name == "test"

    def test_get_returns_none_if_not_exists(self):
        """Should return None if breaker doesn't exist."""
        registry = CircuitBreakerRegistry()

        result = registry.get("nonexistent")

        assert result is None

    @patch("time.time")
    def test_get_all_stats_returns_all_breakers(self, mock_time):
        """Should return stats for all registered breakers."""
        mock_time.return_value = 1000.0

        registry = CircuitBreakerRegistry()

        breaker1 = registry.get_or_create("test1")
        breaker2 = registry.get_or_create("test2")

        breaker1.record_success()
        breaker2.record_failure(Exception("Test"))

        stats = registry.get_all_stats()

        assert "test1" in stats
        assert "test2" in stats
        assert stats["test1"]["stats"]["successful_calls"] == 1
        assert stats["test2"]["stats"]["failed_calls"] == 1

    @patch("time.time")
    def test_reset_all_clears_all_breakers(self, mock_time):
        """Should reset all registered breakers."""
        mock_time.return_value = 1000.0

        registry = CircuitBreakerRegistry()

        breaker1 = registry.get_or_create("test1")
        breaker2 = registry.get_or_create("test2")

        breaker1.record_success()
        breaker2.record_success()

        registry.reset_all()

        assert breaker1.get_stats().successful_calls == 0
        assert breaker2.get_stats().successful_calls == 0


class TestCircuitBreakerRegistryThreadSafety:
    """Tests for registry thread safety."""

    def test_concurrent_get_or_create_is_safe(self):
        """Should handle concurrent registration safely."""
        registry = CircuitBreakerRegistry()
        breakers = []

        def worker():
            breaker = registry.get_or_create("shared")
            breakers.append(breaker)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should get the same instance
        assert len(breakers) == 10
        assert all(b is breakers[0] for b in breakers)


class TestGetCircuitBreaker:
    """Tests for get_circuit_breaker() global function."""

    def test_returns_breaker_from_global_registry(self):
        """Should return breaker from global registry."""
        reset_global_registry()

        breaker = get_circuit_breaker("test", failure_threshold=7)

        assert breaker is not None
        assert breaker.name == "test"
        assert breaker.failure_threshold == 7

    def test_returns_same_instance_on_repeated_calls(self):
        """Should return same breaker instance via global registry."""
        reset_global_registry()

        breaker1 = get_circuit_breaker("test")
        breaker2 = get_circuit_breaker("test")

        assert breaker1 is breaker2


class TestGetCircuitBreakerRegistry:
    """Tests for get_circuit_breaker_registry() global function."""

    def test_returns_singleton_registry(self):
        """Should return same registry instance."""
        reset_global_registry()

        registry1 = get_circuit_breaker_registry()
        registry2 = get_circuit_breaker_registry()

        assert registry1 is registry2

    def test_creates_registry_on_first_call(self):
        """Should create registry if not exists."""
        reset_global_registry()

        registry = get_circuit_breaker_registry()

        assert registry is not None
        assert isinstance(registry, CircuitBreakerRegistry)


class TestResetGlobalRegistry:
    """Tests for reset_global_registry() function."""

    @patch("time.time")
    def test_reset_clears_all_breakers(self, mock_time):
        """Should reset all breakers in global registry."""
        mock_time.return_value = 1000.0

        # Create and use a breaker
        breaker = get_circuit_breaker("test")
        breaker.record_success()

        # Reset
        reset_global_registry()

        # Stats should be cleared
        assert breaker.get_stats().successful_calls == 0

    def test_reset_recreates_registry_on_next_call(self):
        """Should create new registry after reset."""
        registry1 = get_circuit_breaker_registry()
        reset_global_registry()
        registry2 = get_circuit_breaker_registry()

        # Should be different instances after reset
        assert registry1 is not registry2


class TestPreconfiguredBreakers:
    """Tests for pre-configured circuit breakers."""

    def test_get_pdf_service_breaker_configuration(self):
        """Should return PDF service breaker with correct config."""
        reset_global_registry()

        breaker = get_pdf_service_breaker()

        assert breaker.name == "pdf_service"
        assert breaker.failure_threshold == 3
        assert breaker.recovery_timeout == 60.0
        assert breaker.half_open_max_calls == 1

    def test_get_openai_breaker_configuration(self):
        """Should return OpenAI breaker with correct config."""
        reset_global_registry()

        breaker = get_openai_breaker()

        assert breaker.name == "openai"
        assert breaker.failure_threshold == 5
        assert breaker.recovery_timeout == 30.0
        assert breaker.half_open_max_calls == 2
        assert ValueError in breaker.excluded_exceptions

    def test_get_anthropic_breaker_configuration(self):
        """Should return Anthropic breaker with correct config."""
        reset_global_registry()

        breaker = get_anthropic_breaker()

        assert breaker.name == "anthropic"
        assert breaker.failure_threshold == 5
        assert breaker.recovery_timeout == 30.0
        assert breaker.half_open_max_calls == 2
        assert ValueError in breaker.excluded_exceptions

    def test_get_firecrawl_breaker_configuration(self):
        """Should return FireCrawl breaker with correct config."""
        reset_global_registry()

        breaker = get_firecrawl_breaker()

        assert breaker.name == "firecrawl"
        assert breaker.failure_threshold == 3
        assert breaker.recovery_timeout == 120.0
        assert breaker.half_open_max_calls == 1

    def test_preconfigured_breakers_are_singletons(self):
        """Should return same instance on multiple calls."""
        reset_global_registry()

        breaker1 = get_pdf_service_breaker()
        breaker2 = get_pdf_service_breaker()

        assert breaker1 is breaker2


class TestCircuitBreakerThreadSafety:
    """Tests for circuit breaker thread safety."""

    @patch("time.time")
    def test_concurrent_record_success_is_thread_safe(self, mock_time):
        """Should handle concurrent success recording safely."""
        mock_time.return_value = 1000.0

        breaker = CircuitBreaker(name="test")
        num_threads = 10
        calls_per_thread = 100

        def record_repeatedly():
            for _ in range(calls_per_thread):
                breaker.record_success()

        threads = [threading.Thread(target=record_repeatedly) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        stats = breaker.get_stats()
        expected = num_threads * calls_per_thread
        assert stats.successful_calls == expected
        assert stats.total_calls == expected

    @patch("time.time")
    def test_concurrent_record_failure_is_thread_safe(self, mock_time):
        """Should handle concurrent failure recording safely."""
        mock_time.return_value = 1000.0

        breaker = CircuitBreaker(name="test", failure_threshold=1000)

        def record_failures():
            for _ in range(50):
                breaker.record_failure(Exception("Test"))

        threads = [threading.Thread(target=record_failures) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        stats = breaker.get_stats()
        assert stats.failed_calls == 250

    @patch("time.time")
    def test_concurrent_can_execute_is_thread_safe(self, mock_time):
        """Should handle concurrent can_execute checks safely."""
        mock_time.return_value = 1000.0

        breaker = CircuitBreaker(name="test")
        results = []

        def check_repeatedly():
            for _ in range(100):
                result = breaker.can_execute()
                results.append(result)

        threads = [threading.Thread(target=check_repeatedly) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should return True (circuit is closed)
        assert all(results)


class TestCircuitBreakerEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @patch("time.time")
    def test_zero_failure_threshold_never_opens(self, mock_time):
        """Should handle zero failure threshold (always open)."""
        mock_time.return_value = 1000.0

        # Note: In practice, 0 threshold doesn't make sense, but let's test it
        breaker = CircuitBreaker(name="test", failure_threshold=0)

        # Even with no failures, should stay closed (threshold not reached)
        assert breaker.is_closed is True

    @patch("time.time")
    def test_single_failure_threshold_opens_immediately(self, mock_time):
        """Should open on first failure with threshold=1."""
        mock_time.return_value = 1000.0

        breaker = CircuitBreaker(name="test", failure_threshold=1)

        breaker.record_failure(Exception("First failure"))

        assert breaker.is_open is True

    @patch("time.time")
    def test_zero_recovery_timeout_allows_immediate_retry(self, mock_time):
        """Should transition to half-open immediately with zero timeout."""
        breaker = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout=0.0)

        # Open the circuit
        mock_time.return_value = 1000.0
        breaker.record_failure(Exception("Fail 1"))
        breaker.record_failure(Exception("Fail 2"))

        # With zero timeout, accessing state immediately transitions to half-open
        # because elapsed time (0) >= recovery_timeout (0)
        assert breaker.state == CircuitState.HALF_OPEN

        # Even with same time, stays half-open
        assert breaker.state == CircuitState.HALF_OPEN

    @patch("time.time")
    def test_half_open_with_zero_max_calls_blocks_all(self, mock_time):
        """Should block all calls in half-open with max_calls=0."""
        breaker = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=0.0,
            half_open_max_calls=0,
        )

        # Open the circuit
        mock_time.return_value = 1000.0
        breaker.record_failure(Exception("Fail 1"))
        breaker.record_failure(Exception("Fail 2"))

        # Transition to half-open
        mock_time.return_value = 1000.1
        assert breaker.state == CircuitState.HALF_OPEN

        # Should not allow any calls
        assert breaker.can_execute() is False

    @patch("time.time")
    def test_success_threshold_one_closes_on_first_success(self, mock_time):
        """Should close on first success in half-open with threshold=1."""
        breaker = CircuitBreaker(
            name="test",
            failure_threshold=2,
            success_threshold=1,
            recovery_timeout=0.0,
        )

        # Open and transition to half-open
        mock_time.return_value = 1000.0
        breaker.record_failure(Exception("Fail 1"))
        breaker.record_failure(Exception("Fail 2"))
        mock_time.return_value = 1000.1
        assert breaker.state == CircuitState.HALF_OPEN

        # First success should close
        breaker.record_success()
        assert breaker.is_closed is True
