"""
Rate Limiting Module (Gap BG-2).

Provides rate limiting for external API calls to prevent hitting provider limits.
Supports FireCrawl (daily limits) and LLM providers (per-minute limits).

Uses token bucket algorithm with configurable refill rates.

Usage:
    # Per-minute rate limiting for LLM
    limiter = RateLimiter(requests_per_minute=60)

    await limiter.acquire()  # Waits if rate limit exceeded
    response = await llm.invoke(...)

    # Daily rate limiting for FireCrawl
    firecrawl_limiter = RateLimiter(
        requests_per_minute=10,  # Spread requests
        daily_limit=600,         # Hard daily cap
    )
"""

import asyncio
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
from collections import deque


class Provider(str, Enum):
    """API providers with rate limits."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OPENROUTER = "openrouter"
    FIRECRAWL = "firecrawl"


# Default rate limits per provider
DEFAULT_RATE_LIMITS = {
    Provider.OPENAI: {"requests_per_minute": 500, "daily_limit": None},
    Provider.ANTHROPIC: {"requests_per_minute": 100, "daily_limit": None},
    Provider.OPENROUTER: {"requests_per_minute": 60, "daily_limit": None},
    Provider.FIRECRAWL: {"requests_per_minute": 10, "daily_limit": 600},
}


@dataclass
class RateLimitStats:
    """Statistics for rate limiting."""
    total_requests: int = 0
    requests_today: int = 0
    requests_this_minute: int = 0
    waits_count: int = 0
    total_wait_time_seconds: float = 0.0
    last_request_at: Optional[datetime] = None
    daily_reset_at: Optional[datetime] = None


class RateLimitExceededError(Exception):
    """Raised when rate limit is exceeded and waiting is not allowed."""

    def __init__(self, provider: str, limit_type: str, current: int, limit: int):
        self.provider = provider
        self.limit_type = limit_type
        self.current = current
        self.limit = limit
        super().__init__(
            f"Rate limit exceeded for {provider}: {current}/{limit} ({limit_type})"
        )


class RateLimiter:
    """
    Thread-safe rate limiter using sliding window algorithm.

    Tracks requests per minute and optionally per day.
    Provides both blocking (wait) and non-blocking (check) modes.
    """

    def __init__(
        self,
        provider: str,
        requests_per_minute: int = 60,
        daily_limit: Optional[int] = None,
        allow_wait: bool = True,
        max_wait_seconds: float = 60.0,
    ):
        """
        Initialize rate limiter.

        Args:
            provider: Provider name for logging/stats
            requests_per_minute: Maximum requests per minute
            daily_limit: Maximum requests per day (None for unlimited)
            allow_wait: If True, wait when limit hit; if False, raise error
            max_wait_seconds: Maximum time to wait before giving up
        """
        self.provider = provider
        self.requests_per_minute = requests_per_minute
        self.daily_limit = daily_limit
        self.allow_wait = allow_wait
        self.max_wait_seconds = max_wait_seconds

        # Sliding window for per-minute tracking
        self._minute_window: deque = deque()
        self._lock = threading.Lock()

        # Daily tracking
        self._daily_count = 0
        self._daily_reset_date: Optional[datetime] = None

        # Stats
        self._stats = RateLimitStats()

    def _clean_minute_window(self) -> None:
        """Remove entries older than 1 minute from the sliding window."""
        cutoff = time.time() - 60.0
        while self._minute_window and self._minute_window[0] < cutoff:
            self._minute_window.popleft()

    def _reset_daily_if_needed(self) -> None:
        """Reset daily counter if we're on a new day."""
        today = datetime.utcnow().date()
        if self._daily_reset_date is None or self._daily_reset_date < today:
            self._daily_count = 0
            self._daily_reset_date = today
            self._stats.daily_reset_at = datetime.utcnow()

    def _get_wait_time(self) -> float:
        """
        Calculate how long to wait before next request is allowed.

        Returns:
            Wait time in seconds (0.0 if no wait needed)
        """
        self._clean_minute_window()

        if len(self._minute_window) < self.requests_per_minute:
            return 0.0

        # Need to wait until oldest request expires from window
        oldest = self._minute_window[0]
        wait_until = oldest + 60.0
        wait_time = wait_until - time.time()

        return max(0.0, wait_time)

    def check(self) -> bool:
        """
        Check if a request is allowed without waiting.

        Returns:
            True if request allowed, False if rate limited
        """
        with self._lock:
            self._reset_daily_if_needed()
            self._clean_minute_window()

            # Check daily limit
            if self.daily_limit and self._daily_count >= self.daily_limit:
                return False

            # Check per-minute limit
            if len(self._minute_window) >= self.requests_per_minute:
                return False

            return True

    def acquire(self) -> bool:
        """
        Acquire permission for a request (blocking).

        Waits if rate limit is exceeded, up to max_wait_seconds.

        Returns:
            True if acquired, False if timed out

        Raises:
            RateLimitExceededError: If allow_wait is False and limit exceeded
        """
        start_time = time.time()

        while True:
            with self._lock:
                self._reset_daily_if_needed()
                self._clean_minute_window()

                # Check daily limit (hard cap, no waiting helps)
                if self.daily_limit and self._daily_count >= self.daily_limit:
                    if not self.allow_wait:
                        raise RateLimitExceededError(
                            self.provider, "daily", self._daily_count, self.daily_limit
                        )
                    # For daily limits, we can't wait - must fail
                    return False

                # Check per-minute limit
                if len(self._minute_window) < self.requests_per_minute:
                    # Can proceed - record the request
                    now = time.time()
                    self._minute_window.append(now)
                    self._daily_count += 1

                    # Update stats
                    self._stats.total_requests += 1
                    self._stats.requests_today = self._daily_count
                    self._stats.requests_this_minute = len(self._minute_window)
                    self._stats.last_request_at = datetime.utcnow()

                    return True

                # Rate limited - need to wait
                wait_time = self._get_wait_time()

            # Check if we've exceeded max wait time
            elapsed = time.time() - start_time
            if elapsed + wait_time > self.max_wait_seconds:
                if not self.allow_wait:
                    raise RateLimitExceededError(
                        self.provider,
                        "per_minute",
                        len(self._minute_window),
                        self.requests_per_minute,
                    )
                return False

            # Wait and retry
            self._stats.waits_count += 1
            self._stats.total_wait_time_seconds += min(wait_time, 1.0)
            time.sleep(min(wait_time, 1.0))  # Sleep in small increments

    async def acquire_async(self) -> bool:
        """
        Async version of acquire().

        Returns:
            True if acquired, False if timed out
        """
        start_time = time.time()

        while True:
            with self._lock:
                self._reset_daily_if_needed()
                self._clean_minute_window()

                # Check daily limit
                if self.daily_limit and self._daily_count >= self.daily_limit:
                    if not self.allow_wait:
                        raise RateLimitExceededError(
                            self.provider, "daily", self._daily_count, self.daily_limit
                        )
                    return False

                # Check per-minute limit
                if len(self._minute_window) < self.requests_per_minute:
                    now = time.time()
                    self._minute_window.append(now)
                    self._daily_count += 1

                    self._stats.total_requests += 1
                    self._stats.requests_today = self._daily_count
                    self._stats.requests_this_minute = len(self._minute_window)
                    self._stats.last_request_at = datetime.utcnow()

                    return True

                wait_time = self._get_wait_time()

            elapsed = time.time() - start_time
            if elapsed + wait_time > self.max_wait_seconds:
                if not self.allow_wait:
                    raise RateLimitExceededError(
                        self.provider,
                        "per_minute",
                        len(self._minute_window),
                        self.requests_per_minute,
                    )
                return False

            self._stats.waits_count += 1
            self._stats.total_wait_time_seconds += min(wait_time, 0.5)
            await asyncio.sleep(min(wait_time, 0.5))

    def get_stats(self) -> RateLimitStats:
        """Get rate limiting statistics."""
        with self._lock:
            self._clean_minute_window()
            self._stats.requests_this_minute = len(self._minute_window)
            return RateLimitStats(
                total_requests=self._stats.total_requests,
                requests_today=self._stats.requests_today,
                requests_this_minute=self._stats.requests_this_minute,
                waits_count=self._stats.waits_count,
                total_wait_time_seconds=self._stats.total_wait_time_seconds,
                last_request_at=self._stats.last_request_at,
                daily_reset_at=self._stats.daily_reset_at,
            )

    def get_remaining_daily(self) -> Optional[int]:
        """Get remaining daily requests (None if no daily limit)."""
        if self.daily_limit is None:
            return None
        with self._lock:
            self._reset_daily_if_needed()
            return max(0, self.daily_limit - self._daily_count)

    def reset(self) -> None:
        """Reset all rate limit tracking."""
        with self._lock:
            self._minute_window.clear()
            self._daily_count = 0
            self._daily_reset_date = None
            self._stats = RateLimitStats()

    def to_dict(self) -> Dict[str, Any]:
        """Export limiter state as dictionary."""
        stats = self.get_stats()
        return {
            "provider": self.provider,
            "requests_per_minute": self.requests_per_minute,
            "daily_limit": self.daily_limit,
            "stats": {
                "total_requests": stats.total_requests,
                "requests_today": stats.requests_today,
                "requests_this_minute": stats.requests_this_minute,
                "waits_count": stats.waits_count,
                "total_wait_time_seconds": stats.total_wait_time_seconds,
                "last_request_at": stats.last_request_at.isoformat() if stats.last_request_at else None,
            },
            "remaining_daily": self.get_remaining_daily(),
        }


class RateLimiterRegistry:
    """
    Registry for managing rate limiters across providers.

    Provides a single point of access for all rate limiters in the application.
    """

    def __init__(self):
        """Initialize the registry."""
        self._limiters: Dict[str, RateLimiter] = {}
        self._lock = threading.Lock()

    def get_or_create(
        self,
        provider: str,
        requests_per_minute: Optional[int] = None,
        daily_limit: Optional[int] = None,
        **kwargs,
    ) -> RateLimiter:
        """
        Get existing limiter or create new one for provider.

        Args:
            provider: Provider name
            requests_per_minute: Override default RPM
            daily_limit: Override default daily limit
            **kwargs: Additional RateLimiter arguments

        Returns:
            RateLimiter instance for the provider
        """
        with self._lock:
            if provider not in self._limiters:
                # Get defaults for known providers
                defaults = DEFAULT_RATE_LIMITS.get(
                    provider,
                    {"requests_per_minute": 60, "daily_limit": None}
                )

                self._limiters[provider] = RateLimiter(
                    provider=provider,
                    requests_per_minute=requests_per_minute or defaults["requests_per_minute"],
                    daily_limit=daily_limit if daily_limit is not None else defaults["daily_limit"],
                    **kwargs,
                )

            return self._limiters[provider]

    def get(self, provider: str) -> Optional[RateLimiter]:
        """Get limiter for provider if it exists."""
        with self._lock:
            return self._limiters.get(provider)

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get stats for all registered limiters."""
        with self._lock:
            return {
                provider: limiter.to_dict()
                for provider, limiter in self._limiters.items()
            }

    def reset_all(self) -> None:
        """Reset all limiters."""
        with self._lock:
            for limiter in self._limiters.values():
                limiter.reset()


# Global registry instance
_global_registry: Optional[RateLimiterRegistry] = None


def get_rate_limiter_registry() -> RateLimiterRegistry:
    """Get or create the global rate limiter registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = RateLimiterRegistry()
    return _global_registry


def get_rate_limiter(provider: str) -> RateLimiter:
    """
    Get rate limiter for a provider using global registry.

    Reads configuration from environment variables:
    - {PROVIDER}_RATE_LIMIT_PER_MIN: Per-minute limit
    - {PROVIDER}_DAILY_LIMIT: Daily limit (optional)

    Args:
        provider: Provider name (openai, anthropic, openrouter, firecrawl)

    Returns:
        Configured RateLimiter for the provider
    """
    registry = get_rate_limiter_registry()

    # Read config from environment
    provider_upper = provider.upper()
    rpm = int(os.getenv(f"{provider_upper}_RATE_LIMIT_PER_MIN", "0"))
    daily = os.getenv(f"{provider_upper}_DAILY_LIMIT")
    daily_limit = int(daily) if daily else None

    # Use defaults if not configured
    if rpm == 0:
        defaults = DEFAULT_RATE_LIMITS.get(provider, {})
        rpm = defaults.get("requests_per_minute", 60)
        if daily_limit is None:
            daily_limit = defaults.get("daily_limit")

    return registry.get_or_create(
        provider=provider,
        requests_per_minute=rpm,
        daily_limit=daily_limit,
    )


def reset_global_registry() -> None:
    """Reset the global registry (useful for testing)."""
    global _global_registry
    if _global_registry:
        _global_registry.reset_all()
    _global_registry = None
