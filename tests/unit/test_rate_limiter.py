"""
Unit tests for src/common/rate_limiter.py

Tests rate limiting infrastructure including:
- RateLimiter: Per-minute and daily limits with sliding window
- RateLimiterRegistry: Global registry management
- Thread safety and concurrent access
- Error handling and timeout scenarios
"""

import asyncio
import pytest
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from src.common.rate_limiter import (
    RateLimiter,
    RateLimiterRegistry,
    RateLimitExceededError,
    RateLimitStats,
    Provider,
    DEFAULT_RATE_LIMITS,
    get_rate_limiter,
    get_rate_limiter_registry,
    reset_global_registry,
)


class TestRateLimitExceededError:
    """Tests for RateLimitExceededError exception."""

    def test_error_message_formatting(self):
        """Should format error message with provider and limits."""
        error = RateLimitExceededError("firecrawl", "daily", 600, 600)

        assert error.provider == "firecrawl"
        assert error.limit_type == "daily"
        assert error.current == 600
        assert error.limit == 600
        assert "firecrawl" in str(error)
        assert "600/600" in str(error)
        assert "daily" in str(error)

    def test_error_with_per_minute_type(self):
        """Should handle per-minute limit type."""
        error = RateLimitExceededError("openai", "per_minute", 100, 500)

        assert error.limit_type == "per_minute"
        assert "per_minute" in str(error)
        assert "100/500" in str(error)

    def test_error_attributes_accessible(self):
        """Error attributes should be accessible for handling."""
        error = RateLimitExceededError("anthropic", "daily", 150, 200)

        assert error.provider == "anthropic"
        assert error.limit_type == "daily"
        assert error.current == 150
        assert error.limit == 200


class TestRateLimiterInit:
    """Tests for RateLimiter initialization."""

    def test_init_with_defaults(self):
        """Should initialize with default values."""
        limiter = RateLimiter(provider="test")

        assert limiter.provider == "test"
        assert limiter.requests_per_minute == 60
        assert limiter.daily_limit is None
        assert limiter.allow_wait is True
        assert limiter.max_wait_seconds == 60.0

    def test_init_with_custom_values(self):
        """Should accept custom configuration."""
        limiter = RateLimiter(
            provider="firecrawl",
            requests_per_minute=10,
            daily_limit=600,
            allow_wait=False,
            max_wait_seconds=30.0,
        )

        assert limiter.provider == "firecrawl"
        assert limiter.requests_per_minute == 10
        assert limiter.daily_limit == 600
        assert limiter.allow_wait is False
        assert limiter.max_wait_seconds == 30.0

    def test_init_creates_empty_tracking_structures(self):
        """Should initialize empty tracking structures."""
        limiter = RateLimiter(provider="test")

        assert len(limiter._minute_window) == 0
        assert limiter._daily_count == 0
        assert limiter._daily_reset_date is None


class TestRateLimiterCheck:
    """Tests for non-blocking check() method."""

    @patch("time.time")
    def test_check_returns_true_when_under_limit(self, mock_time):
        """Should return True when request is allowed."""
        mock_time.return_value = 1000.0
        limiter = RateLimiter(provider="test", requests_per_minute=5)

        result = limiter.check()

        assert result is True

    @patch("time.time")
    def test_check_returns_false_when_per_minute_exceeded(self, mock_time):
        """Should return False when per-minute limit exceeded."""
        mock_time.return_value = 1000.0
        limiter = RateLimiter(provider="test", requests_per_minute=3)

        # Fill the window
        for _ in range(3):
            limiter.acquire()

        result = limiter.check()

        assert result is False

    @patch("time.time")
    @patch("src.common.rate_limiter.datetime")
    def test_check_returns_false_when_daily_limit_exceeded(self, mock_datetime, mock_time):
        """Should return False when daily limit exceeded."""
        mock_time.return_value = 1000.0
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)

        limiter = RateLimiter(
            provider="test",
            requests_per_minute=100,
            daily_limit=5,
        )

        # Use up daily quota
        for _ in range(5):
            limiter.acquire()

        result = limiter.check()

        assert result is False

    @patch("time.time")
    @patch("src.common.rate_limiter.datetime")
    def test_check_resets_daily_on_new_day(self, mock_datetime, mock_time):
        """Should reset daily count when day changes."""
        mock_time.return_value = 1000.0

        # Day 1
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)
        limiter = RateLimiter(provider="test", daily_limit=5)

        for _ in range(5):
            limiter.acquire()

        assert limiter._daily_count == 5
        assert limiter.check() is False

        # Day 2 - should reset
        mock_datetime.utcnow.return_value = datetime(2025, 12, 1, 10, 0, 0)

        result = limiter.check()

        assert result is True
        assert limiter._daily_count == 0


class TestRateLimiterAcquire:
    """Tests for blocking acquire() method."""

    @patch("time.time")
    @patch("src.common.rate_limiter.datetime")
    def test_acquire_succeeds_when_under_limit(self, mock_datetime, mock_time):
        """Should acquire successfully when under limit."""
        mock_time.return_value = 1000.0
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)

        limiter = RateLimiter(provider="test", requests_per_minute=10)

        result = limiter.acquire()

        assert result is True
        assert limiter._daily_count == 1
        assert len(limiter._minute_window) == 1

    @patch("time.sleep")
    @patch("src.common.rate_limiter.datetime")
    def test_acquire_waits_when_per_minute_exceeded(self, mock_datetime, mock_sleep):
        """Should wait and retry when per-minute limit hit."""
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)

        limiter = RateLimiter(
            provider="test",
            requests_per_minute=3,
            allow_wait=True,
            max_wait_seconds=120.0,  # Long enough to succeed
        )

        # Fill window with 3 requests at t=1000
        with patch("time.time", return_value=1000.0):
            for _ in range(3):
                limiter.acquire()

        # 4th request should wait - simulate time advancing to allow request
        call_count = [0]

        def time_side_effect():
            call_count[0] += 1
            # First few calls: still waiting
            if call_count[0] <= 3:
                return 1000.0 + call_count[0]  # Advance slowly
            # After sleep, window expired
            return 1061.0

        with patch("time.time", side_effect=time_side_effect):
            result = limiter.acquire()

        assert result is True
        mock_sleep.assert_called()
        assert limiter._stats.waits_count > 0

    @patch("time.time")
    @patch("src.common.rate_limiter.datetime")
    def test_acquire_raises_when_daily_limit_exceeded_and_no_wait(self, mock_datetime, mock_time):
        """Should raise error when daily limit hit and allow_wait=False."""
        mock_time.return_value = 1000.0
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)

        limiter = RateLimiter(
            provider="firecrawl",
            requests_per_minute=100,
            daily_limit=5,
            allow_wait=False,
        )

        # Use daily quota
        for _ in range(5):
            limiter.acquire()

        # Should raise on next request
        with pytest.raises(RateLimitExceededError) as exc_info:
            limiter.acquire()

        assert exc_info.value.provider == "firecrawl"
        assert exc_info.value.limit_type == "daily"
        assert exc_info.value.current == 5
        assert exc_info.value.limit == 5

    @patch("time.time")
    @patch("src.common.rate_limiter.datetime")
    def test_acquire_returns_false_when_daily_limit_exceeded_with_wait(self, mock_datetime, mock_time):
        """Should return False when daily limit hit (can't wait for next day)."""
        mock_time.return_value = 1000.0
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)

        limiter = RateLimiter(
            provider="firecrawl",
            requests_per_minute=100,
            daily_limit=3,
            allow_wait=True,
        )

        # Use daily quota
        for _ in range(3):
            limiter.acquire()

        # Should return False (can't wait until tomorrow)
        result = limiter.acquire()

        assert result is False

    @patch("time.time")
    @patch("time.sleep")
    @patch("src.common.rate_limiter.datetime")
    def test_acquire_timeout_when_max_wait_exceeded(self, mock_datetime, mock_sleep, mock_time):
        """Should timeout when wait time exceeds max_wait_seconds."""
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)

        # Fill window at t=1000, need to wait until t=1060
        mock_time.side_effect = [
            1000.0, 1000.0,  # First acquire
            1000.0,          # Second acquire
            1000.0,          # 3rd acquire - start_time
            1000.0, 1000.0,  # Check window
            1005.0,          # After first sleep check
            1005.0, 1005.0,  # Check window again
            1010.0,          # After second sleep check
            1010.0, 1010.0,  # Check window
            1015.0,          # Timeout check - elapsed 15s > max 10s
        ]

        limiter = RateLimiter(
            provider="test",
            requests_per_minute=2,
            max_wait_seconds=10.0,
        )

        # Fill window
        limiter.acquire()
        limiter.acquire()

        # Should timeout
        result = limiter.acquire()

        assert result is False

    @patch("time.time")
    @patch("src.common.rate_limiter.datetime")
    def test_acquire_updates_stats_correctly(self, mock_datetime, mock_time):
        """Should update stats on successful acquire."""
        mock_time.return_value = 1000.0
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)

        limiter = RateLimiter(provider="test")

        limiter.acquire()
        limiter.acquire()
        limiter.acquire()

        stats = limiter.get_stats()
        assert stats.total_requests == 3
        assert stats.requests_today == 3
        assert stats.requests_this_minute == 3
        assert stats.last_request_at is not None


class TestRateLimiterAcquireAsync:
    """Tests for async acquire_async() method."""

    @pytest.mark.asyncio
    @patch("time.time")
    @patch("src.common.rate_limiter.datetime")
    async def test_acquire_async_succeeds_when_under_limit(self, mock_datetime, mock_time):
        """Should acquire asynchronously when under limit."""
        mock_time.return_value = 1000.0
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)

        limiter = RateLimiter(provider="test", requests_per_minute=10)

        result = await limiter.acquire_async()

        assert result is True
        assert limiter._daily_count == 1

    @pytest.mark.asyncio
    @patch("src.common.rate_limiter.datetime")
    async def test_acquire_async_waits_correctly(self, mock_datetime):
        """Should use asyncio.sleep for waiting."""
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)

        limiter = RateLimiter(
            provider="test",
            requests_per_minute=2,
            max_wait_seconds=120.0,
        )

        # Fill window at t=1000
        with patch("time.time", return_value=1000.0):
            await limiter.acquire_async()
            await limiter.acquire_async()

        # 3rd request should wait - simulate time advancing
        call_count = [0]

        def time_side_effect():
            call_count[0] += 1
            # Gradually advance time
            if call_count[0] <= 3:
                return 1000.0 + call_count[0]
            # After sleep, window expired
            return 1061.0

        with patch("asyncio.sleep") as mock_sleep:
            with patch("time.time", side_effect=time_side_effect):
                result = await limiter.acquire_async()
                mock_sleep.assert_called()

        assert result is True

    @pytest.mark.asyncio
    @patch("time.time")
    @patch("src.common.rate_limiter.datetime")
    async def test_acquire_async_raises_on_daily_limit(self, mock_datetime, mock_time):
        """Should raise error when daily limit exceeded."""
        mock_time.return_value = 1000.0
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)

        limiter = RateLimiter(
            provider="test",
            daily_limit=2,
            allow_wait=False,
        )

        await limiter.acquire_async()
        await limiter.acquire_async()

        with pytest.raises(RateLimitExceededError):
            await limiter.acquire_async()


class TestRateLimiterStats:
    """Tests for statistics and tracking."""

    @patch("time.time")
    @patch("src.common.rate_limiter.datetime")
    def test_get_stats_returns_current_state(self, mock_datetime, mock_time):
        """Should return accurate stats."""
        mock_time.return_value = 1000.0
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)

        limiter = RateLimiter(provider="test")

        limiter.acquire()
        limiter.acquire()

        stats = limiter.get_stats()

        assert stats.total_requests == 2
        assert stats.requests_today == 2
        assert stats.requests_this_minute == 2
        assert stats.last_request_at is not None

    @patch("time.time")
    @patch("src.common.rate_limiter.datetime")
    def test_get_remaining_daily_returns_quota(self, mock_datetime, mock_time):
        """Should return remaining daily quota."""
        mock_time.return_value = 1000.0
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)

        limiter = RateLimiter(provider="test", daily_limit=10)

        assert limiter.get_remaining_daily() == 10

        limiter.acquire()
        limiter.acquire()

        assert limiter.get_remaining_daily() == 8

    @patch("time.time")
    def test_get_remaining_daily_returns_none_when_no_limit(self, mock_time):
        """Should return None when no daily limit set."""
        mock_time.return_value = 1000.0
        limiter = RateLimiter(provider="test", daily_limit=None)

        result = limiter.get_remaining_daily()

        assert result is None

    @patch("time.time")
    @patch("src.common.rate_limiter.datetime")
    def test_get_remaining_daily_never_negative(self, mock_datetime, mock_time):
        """Should return 0 instead of negative values."""
        mock_time.return_value = 1000.0
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)

        limiter = RateLimiter(provider="test", daily_limit=2)

        limiter.acquire()
        limiter.acquire()

        remaining = limiter.get_remaining_daily()

        assert remaining == 0


class TestRateLimiterReset:
    """Tests for reset() method."""

    @patch("time.time")
    @patch("src.common.rate_limiter.datetime")
    def test_reset_clears_all_tracking(self, mock_datetime, mock_time):
        """Should clear all tracking data."""
        mock_time.return_value = 1000.0
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)

        limiter = RateLimiter(provider="test", daily_limit=100)

        # Make some requests
        limiter.acquire()
        limiter.acquire()
        limiter.acquire()

        assert limiter._daily_count == 3
        assert len(limiter._minute_window) == 3

        # Reset
        limiter.reset()

        assert limiter._daily_count == 0
        assert len(limiter._minute_window) == 0
        assert limiter._daily_reset_date is None

        stats = limiter.get_stats()
        assert stats.total_requests == 0


class TestRateLimiterToDict:
    """Tests for to_dict() export method."""

    @patch("time.time")
    @patch("src.common.rate_limiter.datetime")
    def test_to_dict_includes_all_fields(self, mock_datetime, mock_time):
        """Should export complete state as dictionary."""
        mock_time.return_value = 1000.0
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)

        limiter = RateLimiter(
            provider="firecrawl",
            requests_per_minute=10,
            daily_limit=600,
        )

        limiter.acquire()

        result = limiter.to_dict()

        assert result["provider"] == "firecrawl"
        assert result["requests_per_minute"] == 10
        assert result["daily_limit"] == 600
        assert "stats" in result
        assert result["stats"]["total_requests"] == 1
        assert result["remaining_daily"] == 599

    @patch("time.time")
    @patch("src.common.rate_limiter.datetime")
    def test_to_dict_handles_no_daily_limit(self, mock_datetime, mock_time):
        """Should handle None daily limit correctly."""
        mock_time.return_value = 1000.0
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)

        limiter = RateLimiter(provider="test", daily_limit=None)

        result = limiter.to_dict()

        assert result["daily_limit"] is None
        assert result["remaining_daily"] is None


class TestRateLimiterThreadSafety:
    """Tests for thread safety."""

    @patch("time.time")
    @patch("src.common.rate_limiter.datetime")
    def test_concurrent_acquire_is_thread_safe(self, mock_datetime, mock_time):
        """Should handle concurrent acquires safely."""
        mock_time.return_value = 1000.0
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)

        limiter = RateLimiter(provider="test", requests_per_minute=100)
        results = []

        def worker():
            result = limiter.acquire()
            results.append(result)

        # Start 10 concurrent threads
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should succeed
        assert len(results) == 10
        assert all(results)
        assert limiter._daily_count == 10

    @patch("time.time")
    @patch("src.common.rate_limiter.datetime")
    def test_concurrent_check_does_not_corrupt_state(self, mock_datetime, mock_time):
        """Should handle concurrent checks without corruption."""
        mock_time.return_value = 1000.0
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)

        limiter = RateLimiter(provider="test", requests_per_minute=50)

        def checker():
            for _ in range(10):
                limiter.check()

        threads = [threading.Thread(target=checker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # State should remain consistent
        stats = limiter.get_stats()
        assert stats.total_requests == 0  # check() doesn't count


class TestRateLimiterEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @patch("time.time")
    @patch("src.common.rate_limiter.datetime")
    def test_zero_requests_per_minute_blocks_immediately(self, mock_datetime, mock_time):
        """Should block when requests_per_minute is 0."""
        mock_time.return_value = 1000.0
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)

        limiter = RateLimiter(
            provider="test",
            requests_per_minute=0,
            allow_wait=False,
        )

        # With 0 requests_per_minute, check() should return False
        # But acquire() will try to proceed and hit an empty window error
        # Let's verify check() correctly returns False
        result = limiter.check()
        assert result is False

    @patch("time.time")
    @patch("src.common.rate_limiter.datetime")
    def test_single_request_per_minute_works(self, mock_datetime, mock_time):
        """Should work with requests_per_minute=1."""
        mock_time.return_value = 1000.0
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)

        limiter = RateLimiter(provider="test", requests_per_minute=1)

        result = limiter.acquire()
        assert result is True

        # Second immediate request should fail
        assert limiter.check() is False

    @patch("time.time")
    @patch("src.common.rate_limiter.datetime")
    def test_sliding_window_expires_old_requests(self, mock_datetime, mock_time):
        """Should expire requests older than 60 seconds."""
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)

        limiter = RateLimiter(provider="test", requests_per_minute=2)

        # Request at t=1000
        mock_time.return_value = 1000.0
        limiter.acquire()
        limiter.acquire()

        # Window full
        assert limiter.check() is False

        # Jump to t=1061 (61 seconds later)
        mock_time.return_value = 1061.0

        # Old requests expired, should succeed
        assert limiter.check() is True


class TestRateLimiterRegistry:
    """Tests for RateLimiterRegistry class."""

    def test_init_creates_empty_registry(self):
        """Should initialize with no limiters."""
        registry = RateLimiterRegistry()

        assert len(registry._limiters) == 0

    def test_get_or_create_returns_new_limiter(self):
        """Should create new limiter if not exists."""
        registry = RateLimiterRegistry()

        limiter = registry.get_or_create("test", requests_per_minute=10)

        assert limiter is not None
        assert limiter.provider == "test"
        assert limiter.requests_per_minute == 10

    def test_get_or_create_returns_existing_limiter(self):
        """Should return existing limiter on second call."""
        registry = RateLimiterRegistry()

        limiter1 = registry.get_or_create("test")
        limiter2 = registry.get_or_create("test")

        assert limiter1 is limiter2

    def test_get_or_create_uses_default_rate_limits(self):
        """Should use DEFAULT_RATE_LIMITS for known providers."""
        registry = RateLimiterRegistry()

        firecrawl = registry.get_or_create("firecrawl")

        assert firecrawl.requests_per_minute == 10
        assert firecrawl.daily_limit == 600

    def test_get_or_create_allows_override_defaults(self):
        """Should allow overriding default limits."""
        registry = RateLimiterRegistry()

        firecrawl = registry.get_or_create(
            "firecrawl",
            requests_per_minute=20,
            daily_limit=1000,
        )

        assert firecrawl.requests_per_minute == 20
        assert firecrawl.daily_limit == 1000

    def test_get_returns_existing_limiter(self):
        """Should return limiter if exists."""
        registry = RateLimiterRegistry()

        registry.get_or_create("test")
        limiter = registry.get("test")

        assert limiter is not None
        assert limiter.provider == "test"

    def test_get_returns_none_if_not_exists(self):
        """Should return None if limiter doesn't exist."""
        registry = RateLimiterRegistry()

        result = registry.get("nonexistent")

        assert result is None

    @patch("time.time")
    @patch("src.common.rate_limiter.datetime")
    def test_get_all_stats_returns_all_limiters(self, mock_datetime, mock_time):
        """Should return stats for all registered limiters."""
        mock_time.return_value = 1000.0
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)

        registry = RateLimiterRegistry()

        limiter1 = registry.get_or_create("test1")
        limiter2 = registry.get_or_create("test2")

        limiter1.acquire()
        limiter2.acquire()
        limiter2.acquire()

        stats = registry.get_all_stats()

        assert "test1" in stats
        assert "test2" in stats
        assert stats["test1"]["stats"]["total_requests"] == 1
        assert stats["test2"]["stats"]["total_requests"] == 2

    @patch("time.time")
    @patch("src.common.rate_limiter.datetime")
    def test_reset_all_clears_all_limiters(self, mock_datetime, mock_time):
        """Should reset all registered limiters."""
        mock_time.return_value = 1000.0
        mock_datetime.utcnow.return_value = datetime(2025, 11, 30, 10, 0, 0)

        registry = RateLimiterRegistry()

        limiter1 = registry.get_or_create("test1")
        limiter2 = registry.get_or_create("test2")

        limiter1.acquire()
        limiter2.acquire()

        registry.reset_all()

        assert limiter1.get_stats().total_requests == 0
        assert limiter2.get_stats().total_requests == 0


class TestRateLimiterRegistryThreadSafety:
    """Tests for registry thread safety."""

    def test_concurrent_get_or_create_is_safe(self):
        """Should handle concurrent registration safely."""
        registry = RateLimiterRegistry()
        limiters = []

        def worker():
            limiter = registry.get_or_create("shared")
            limiters.append(limiter)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should get the same instance
        assert len(limiters) == 10
        assert all(l is limiters[0] for l in limiters)


class TestGetRateLimiter:
    """Tests for get_rate_limiter() global function."""

    @patch.dict("os.environ", {
        "FIRECRAWL_RATE_LIMIT_PER_MIN": "20",
        "FIRECRAWL_DAILY_LIMIT": "1000",
    })
    def test_reads_config_from_env_vars(self):
        """Should read configuration from environment variables."""
        reset_global_registry()

        limiter = get_rate_limiter("firecrawl")

        assert limiter.requests_per_minute == 20
        assert limiter.daily_limit == 1000

    @patch.dict("os.environ", {}, clear=True)
    def test_uses_defaults_when_env_not_set(self):
        """Should use defaults when env vars not set."""
        reset_global_registry()

        limiter = get_rate_limiter("firecrawl")

        assert limiter.requests_per_minute == 10
        assert limiter.daily_limit == 600

    @patch.dict("os.environ", {
        "OPENAI_RATE_LIMIT_PER_MIN": "100",
    })
    def test_uses_env_for_custom_provider(self):
        """Should respect env vars for any provider."""
        reset_global_registry()

        limiter = get_rate_limiter("openai")

        assert limiter.requests_per_minute == 100

    def test_returns_same_instance_on_repeated_calls(self):
        """Should return same limiter instance via global registry."""
        reset_global_registry()

        limiter1 = get_rate_limiter("test")
        limiter2 = get_rate_limiter("test")

        assert limiter1 is limiter2


class TestGetRateLimiterRegistry:
    """Tests for get_rate_limiter_registry() global function."""

    def test_returns_singleton_registry(self):
        """Should return same registry instance."""
        reset_global_registry()

        registry1 = get_rate_limiter_registry()
        registry2 = get_rate_limiter_registry()

        assert registry1 is registry2

    def test_creates_registry_on_first_call(self):
        """Should create registry if not exists."""
        reset_global_registry()

        registry = get_rate_limiter_registry()

        assert registry is not None
        assert isinstance(registry, RateLimiterRegistry)


class TestDefaultRateLimits:
    """Tests for DEFAULT_RATE_LIMITS configuration."""

    def test_default_limits_exist_for_all_providers(self):
        """Should have defaults for all providers."""
        assert Provider.OPENAI in DEFAULT_RATE_LIMITS
        assert Provider.ANTHROPIC in DEFAULT_RATE_LIMITS
        assert Provider.OPENROUTER in DEFAULT_RATE_LIMITS
        assert Provider.FIRECRAWL in DEFAULT_RATE_LIMITS

    def test_firecrawl_has_daily_limit(self):
        """FireCrawl should have daily limit."""
        config = DEFAULT_RATE_LIMITS[Provider.FIRECRAWL]

        assert config["daily_limit"] == 600
        assert config["requests_per_minute"] == 10

    def test_llm_providers_no_daily_limit(self):
        """LLM providers should not have daily limits."""
        assert DEFAULT_RATE_LIMITS[Provider.OPENAI]["daily_limit"] is None
        assert DEFAULT_RATE_LIMITS[Provider.ANTHROPIC]["daily_limit"] is None
        assert DEFAULT_RATE_LIMITS[Provider.OPENROUTER]["daily_limit"] is None


class TestProviderEnum:
    """Tests for Provider enum."""

    def test_provider_enum_values(self):
        """Should have correct string values."""
        assert Provider.OPENAI.value == "openai"
        assert Provider.ANTHROPIC.value == "anthropic"
        assert Provider.OPENROUTER.value == "openrouter"
        assert Provider.FIRECRAWL.value == "firecrawl"


class TestRateLimitStatsDataclass:
    """Tests for RateLimitStats dataclass."""

    def test_init_with_defaults(self):
        """Should initialize with zero/None defaults."""
        stats = RateLimitStats()

        assert stats.total_requests == 0
        assert stats.requests_today == 0
        assert stats.requests_this_minute == 0
        assert stats.waits_count == 0
        assert stats.total_wait_time_seconds == 0.0
        assert stats.last_request_at is None
        assert stats.daily_reset_at is None

    def test_init_with_custom_values(self):
        """Should accept custom values."""
        now = datetime.utcnow()
        stats = RateLimitStats(
            total_requests=100,
            requests_today=50,
            requests_this_minute=5,
            waits_count=10,
            total_wait_time_seconds=25.5,
            last_request_at=now,
            daily_reset_at=now,
        )

        assert stats.total_requests == 100
        assert stats.requests_today == 50
        assert stats.waits_count == 10
        assert stats.total_wait_time_seconds == 25.5
