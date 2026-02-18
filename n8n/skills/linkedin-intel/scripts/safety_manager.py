"""Rate limiting and safety engine for LinkedIn API calls.

Enforces daily/session limits, warmup periods, cooldowns, and rest days
to protect the LinkedIn account from detection and suspension.
"""

import os
import random
import time
from datetime import datetime, timedelta, timezone

import requests

import mongo_store
from utils import load_config, setup_logging

logger = setup_logging("safety-manager")


class SafetyManager:
    """Enforces rate limits and safety rules for LinkedIn scraping."""

    def __init__(self):
        self.config = load_config("safety-config")
        self.rate_limits = self.config["rate_limits"]
        self.warmup = self.config["warmup"]
        self.cooldowns = self.config["cooldowns"]
        self.session_calls = 0
        self.session_start = datetime.now(timezone.utc)

    def can_make_call(self) -> tuple[bool, str]:
        """Check if it's safe to make another API call.

        Returns:
            (allowed, reason) — reason explains why if not allowed.
        """
        # Rest day check
        if self._is_rest_day():
            return False, "Rest day (Sunday) — no scraping"

        # Cooldown check
        cooldown = mongo_store.get_cooldown_state()
        if cooldown:
            remaining = cooldown["expires_at"] - datetime.now(timezone.utc)
            return False, f"Cooldown active ({cooldown['status_code']}), {remaining} remaining"

        # Session limit
        if self.session_calls >= self.rate_limits["max_calls_per_session"]:
            return False, f"Session limit reached ({self.session_calls}/{self.rate_limits['max_calls_per_session']})"

        # Session duration
        elapsed = (datetime.now(timezone.utc) - self.session_start).total_seconds() / 60
        if elapsed >= self.rate_limits["session_max_duration_minutes"]:
            return False, f"Session duration exceeded ({elapsed:.0f} min)"

        # Daily limit (warmup-aware)
        daily_count = mongo_store.get_today_call_count() + self.session_calls
        daily_limit = self._get_daily_limit()
        if daily_count >= daily_limit:
            return False, f"Daily limit reached ({daily_count}/{daily_limit})"

        return True, "OK"

    def wait_between_calls(self) -> float:
        """Sleep a randomized interval between API calls.

        Uses uniform random + gaussian jitter for human-like patterns.
        Returns the actual delay in seconds.
        """
        base = random.uniform(
            self.rate_limits["min_delay_seconds"],
            self.rate_limits["max_delay_seconds"],
        )
        jitter = random.gauss(0, 2)
        delay = max(3.0, base + jitter)  # Minimum 3 seconds
        logger.debug("Waiting %.1fs between calls", delay)
        time.sleep(delay)
        return delay

    def record_call(self) -> None:
        """Increment the session call counter."""
        self.session_calls += 1
        logger.debug("Session calls: %d", self.session_calls)

    def handle_error(self, status_code: int) -> None:
        """Handle LinkedIn API error responses with appropriate cooldowns and alerts."""
        code_str = str(status_code)
        if code_str in self.cooldowns:
            cooldown_hours = self.cooldowns[code_str]["hours"]
            description = self.cooldowns[code_str]["description"]

            if cooldown_hours > 0:
                mongo_store.set_cooldown(status_code, cooldown_hours)
                logger.warning("Cooldown set: %dh for HTTP %d — %s", cooldown_hours, status_code, description)

            self._send_alert(
                f"⚠️ LinkedIn Intel Alert\n\n"
                f"HTTP {status_code}: {description}\n"
                f"Cooldown: {cooldown_hours}h\n"
                f"Session calls before error: {self.session_calls}"
            )
        else:
            logger.warning("Unhandled HTTP %d — continuing with caution", status_code)

    def is_warmup_period(self) -> bool:
        """Check if we're still in the initial warmup period."""
        first_session = mongo_store.get_first_session_date()
        if first_session is None:
            return True  # No sessions yet — definitely warmup
        # MongoDB may return naive datetimes — normalize to UTC-aware
        if first_session.tzinfo is None:
            first_session = first_session.replace(tzinfo=timezone.utc)
        days_active = (datetime.now(timezone.utc) - first_session).days
        return days_active < self.warmup["warmup_period_days"]

    def get_session_summary(self) -> dict:
        """Return a summary of the current session for logging."""
        elapsed = (datetime.now(timezone.utc) - self.session_start).total_seconds() / 60
        return {
            "session_calls": self.session_calls,
            "session_duration_minutes": round(elapsed, 1),
            "daily_total": mongo_store.get_today_call_count() + self.session_calls,
            "daily_limit": self._get_daily_limit(),
            "is_warmup": self.is_warmup_period(),
        }

    # --- Private helpers ---

    def _get_daily_limit(self) -> int:
        """Return the effective daily limit (lower during warmup)."""
        if self.is_warmup_period():
            return self.warmup["warmup_max_calls_per_day"]
        return self.rate_limits["max_calls_per_day"]

    def _is_rest_day(self) -> bool:
        """Check if today is the configured rest day."""
        today = datetime.now(timezone.utc).strftime("%A").lower()
        return today == self.config["rest_day"]

    def _send_alert(self, message: str) -> None:
        """Send a Telegram alert message."""
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            logger.warning("Telegram credentials not set — alert not sent: %s", message)
            return
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
        except Exception as e:
            logger.error("Failed to send Telegram alert: %s", e)


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test safety manager")
    parser.add_argument("--test", action="store_true", help="Run safety checks")
    args = parser.parse_args()

    if args.test:
        sm = SafetyManager()
        logger.info("Config loaded: %s", sm.config)

        allowed, reason = sm.can_make_call()
        logger.info("Can make call: %s (%s)", allowed, reason)
        logger.info("Is warmup: %s", sm.is_warmup_period())
        logger.info("Daily limit: %d", sm._get_daily_limit())
        logger.info("Is rest day: %s", sm._is_rest_day())
        logger.info("Session summary: %s", sm.get_session_summary())
