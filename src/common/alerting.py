"""
Error Alerting Module (Gap OB-2).

Provides centralized alerting for system events:
- Circuit breaker state changes
- Budget threshold warnings
- Rate limit exhaustion
- Pipeline failures

Supports multiple notification channels (Slack, console logging).
Includes duplicate suppression to prevent alert fatigue.

Usage:
    from src.common.alerting import get_alert_manager, AlertLevel

    manager = get_alert_manager()

    # Send an alert
    manager.alert(
        level=AlertLevel.WARNING,
        message="Circuit breaker 'openai' opened",
        source="circuit_breaker",
        metadata={"service": "openai", "failures": 5}
    )

    # Configure Slack webhook
    manager.configure_slack(webhook_url="https://hooks.slack.com/...")
"""

import hashlib
import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol

import requests

logger = logging.getLogger(__name__)


class AlertLevel(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Alert:
    """Represents a single alert."""
    level: AlertLevel
    message: str
    source: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    alert_id: str = ""

    def __post_init__(self):
        """Generate alert ID for deduplication."""
        if not self.alert_id:
            # Create hash from level, source, and message for deduplication
            content = f"{self.level.value}:{self.source}:{self.message}"
            self.alert_id = hashlib.md5(content.encode()).hexdigest()[:12]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "alert_id": self.alert_id,
            "level": self.level.value,
            "message": self.message,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


class AlertNotifier(ABC):
    """Abstract base class for alert notification channels."""

    @abstractmethod
    def send(self, alert: Alert) -> bool:
        """
        Send an alert notification.

        Args:
            alert: The alert to send

        Returns:
            True if sent successfully, False otherwise
        """
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if the notifier is properly configured."""
        pass


class ConsoleNotifier(AlertNotifier):
    """Logs alerts to console/logger."""

    def __init__(self, logger_instance: Optional[logging.Logger] = None):
        """Initialize console notifier."""
        self._logger = logger_instance or logger

    def send(self, alert: Alert) -> bool:
        """Log alert to console."""
        level_map = {
            AlertLevel.INFO: logging.INFO,
            AlertLevel.WARNING: logging.WARNING,
            AlertLevel.ERROR: logging.ERROR,
            AlertLevel.CRITICAL: logging.CRITICAL,
        }
        log_level = level_map.get(alert.level, logging.INFO)

        self._logger.log(
            log_level,
            f"[ALERT:{alert.level.value.upper()}] [{alert.source}] {alert.message}",
            extra={"alert_metadata": alert.metadata}
        )
        return True

    def is_configured(self) -> bool:
        """Console notifier is always configured."""
        return True


class SlackNotifier(AlertNotifier):
    """Sends alerts to Slack via webhook."""

    def __init__(self, webhook_url: Optional[str] = None, timeout: float = 10.0):
        """
        Initialize Slack notifier.

        Args:
            webhook_url: Slack webhook URL
            timeout: Request timeout in seconds
        """
        self._webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        self._timeout = timeout

    def is_configured(self) -> bool:
        """Check if webhook URL is set."""
        return bool(self._webhook_url)

    def send(self, alert: Alert) -> bool:
        """Send alert to Slack."""
        if not self.is_configured():
            logger.debug("Slack notifier not configured, skipping")
            return False

        # Build Slack message with blocks for better formatting
        emoji_map = {
            AlertLevel.INFO: ":information_source:",
            AlertLevel.WARNING: ":warning:",
            AlertLevel.ERROR: ":x:",
            AlertLevel.CRITICAL: ":rotating_light:",
        }
        color_map = {
            AlertLevel.INFO: "#36a64f",
            AlertLevel.WARNING: "#ffcc00",
            AlertLevel.ERROR: "#ff6600",
            AlertLevel.CRITICAL: "#ff0000",
        }

        emoji = emoji_map.get(alert.level, ":bell:")
        color = color_map.get(alert.level, "#808080")

        payload = {
            "attachments": [
                {
                    "color": color,
                    "blocks": [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": f"{emoji} {alert.level.value.upper()}: {alert.source}",
                                "emoji": True
                            }
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": alert.message
                            }
                        },
                        {
                            "type": "context",
                            "elements": [
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Time:* {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC"
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        # Add metadata fields if present
        if alert.metadata:
            metadata_text = " | ".join(
                f"*{k}:* {v}" for k, v in alert.metadata.items()
            )
            payload["attachments"][0]["blocks"].append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": metadata_text
                    }
                ]
            })

        try:
            response = requests.post(
                self._webhook_url,
                json=payload,
                timeout=self._timeout
            )
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"Failed to send Slack alert: {e}")
            return False


@dataclass
class AlertSuppressionRule:
    """Rule for suppressing duplicate alerts."""
    alert_id: str
    last_sent: datetime
    count: int = 1


class AlertManager:
    """
    Central manager for system alerts.

    Features:
    - Multiple notification channels
    - Duplicate suppression with configurable window
    - Alert history tracking
    - Async notification support
    """

    def __init__(
        self,
        suppression_window: float = 300.0,  # 5 minutes default
        max_history: int = 1000,
    ):
        """
        Initialize alert manager.

        Args:
            suppression_window: Seconds to suppress duplicate alerts
            max_history: Maximum alerts to keep in history
        """
        self._notifiers: List[AlertNotifier] = []
        self._suppression_window = suppression_window
        self._max_history = max_history
        self._suppression_rules: Dict[str, AlertSuppressionRule] = {}
        self._history: List[Alert] = []
        self._lock = threading.Lock()
        self._enabled = os.getenv("ENABLE_ALERTING", "true").lower() == "true"

        # Add console notifier by default
        self._notifiers.append(ConsoleNotifier())

        # Add Slack notifier if configured
        slack_notifier = SlackNotifier()
        if slack_notifier.is_configured():
            self._notifiers.append(slack_notifier)
            logger.info("Slack alerting configured")

    def configure_slack(self, webhook_url: str) -> None:
        """
        Configure Slack webhook for alerting.

        Args:
            webhook_url: Slack incoming webhook URL
        """
        # Remove existing Slack notifier if any
        self._notifiers = [n for n in self._notifiers if not isinstance(n, SlackNotifier)]

        # Add new Slack notifier
        notifier = SlackNotifier(webhook_url)
        if notifier.is_configured():
            self._notifiers.append(notifier)
            logger.info("Slack alerting reconfigured")

    def add_notifier(self, notifier: AlertNotifier) -> None:
        """Add a notification channel."""
        if notifier.is_configured():
            self._notifiers.append(notifier)

    def alert(
        self,
        level: AlertLevel,
        message: str,
        source: str,
        metadata: Optional[Dict[str, Any]] = None,
        force: bool = False,
    ) -> bool:
        """
        Send an alert through all configured channels.

        Args:
            level: Alert severity level
            message: Alert message
            source: Source component (e.g., "circuit_breaker", "budget_tracker")
            metadata: Additional context data
            force: If True, bypass suppression rules

        Returns:
            True if alert was sent, False if suppressed or failed
        """
        if not self._enabled:
            return False

        alert = Alert(
            level=level,
            message=message,
            source=source,
            metadata=metadata or {},
        )

        with self._lock:
            # Check suppression rules
            if not force and self._is_suppressed(alert):
                logger.debug(f"Alert suppressed: {alert.alert_id}")
                return False

            # Update suppression rules
            self._update_suppression(alert)

            # Add to history
            self._history.append(alert)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

        # Send through all notifiers
        success = False
        for notifier in self._notifiers:
            try:
                if notifier.send(alert):
                    success = True
            except Exception as e:
                logger.error(f"Notifier {type(notifier).__name__} failed: {e}")

        return success

    def _is_suppressed(self, alert: Alert) -> bool:
        """Check if alert should be suppressed."""
        rule = self._suppression_rules.get(alert.alert_id)
        if not rule:
            return False

        # Check if suppression window has passed
        elapsed = (datetime.utcnow() - rule.last_sent).total_seconds()
        return elapsed < self._suppression_window

    def _update_suppression(self, alert: Alert) -> None:
        """Update suppression rules for an alert."""
        rule = self._suppression_rules.get(alert.alert_id)
        if rule:
            rule.last_sent = datetime.utcnow()
            rule.count += 1
        else:
            self._suppression_rules[alert.alert_id] = AlertSuppressionRule(
                alert_id=alert.alert_id,
                last_sent=datetime.utcnow(),
            )

        # Clean up old suppression rules
        cutoff = datetime.utcnow() - timedelta(seconds=self._suppression_window * 2)
        self._suppression_rules = {
            k: v for k, v in self._suppression_rules.items()
            if v.last_sent > cutoff
        }

    def get_history(
        self,
        level: Optional[AlertLevel] = None,
        source: Optional[str] = None,
        limit: int = 100,
    ) -> List[Alert]:
        """
        Get alert history with optional filtering.

        Args:
            level: Filter by alert level
            source: Filter by source component
            limit: Maximum alerts to return

        Returns:
            List of alerts matching criteria
        """
        with self._lock:
            alerts = self._history.copy()

        if level:
            alerts = [a for a in alerts if a.level == level]
        if source:
            alerts = [a for a in alerts if a.source == source]

        return alerts[-limit:]

    def clear_history(self) -> None:
        """Clear alert history."""
        with self._lock:
            self._history.clear()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable alerting."""
        self._enabled = enabled

    @property
    def is_enabled(self) -> bool:
        """Check if alerting is enabled."""
        return self._enabled

    def get_stats(self) -> Dict[str, Any]:
        """Get alerting statistics."""
        with self._lock:
            by_level = {}
            by_source = {}
            for alert in self._history:
                by_level[alert.level.value] = by_level.get(alert.level.value, 0) + 1
                by_source[alert.source] = by_source.get(alert.source, 0) + 1

            return {
                "enabled": self._enabled,
                "notifiers": [type(n).__name__ for n in self._notifiers],
                "history_count": len(self._history),
                "suppression_rules_count": len(self._suppression_rules),
                "by_level": by_level,
                "by_source": by_source,
            }


# =============================================================================
# Convenience Functions for Common Alerts
# =============================================================================

def alert_circuit_breaker_opened(
    service: str,
    failures: int,
    last_error: Optional[str] = None,
) -> None:
    """Alert when a circuit breaker opens."""
    manager = get_alert_manager()
    manager.alert(
        level=AlertLevel.ERROR,
        message=f"Circuit breaker '{service}' OPENED after {failures} consecutive failures",
        source="circuit_breaker",
        metadata={
            "service": service,
            "consecutive_failures": failures,
            "last_error": last_error or "Unknown",
        }
    )


def alert_circuit_breaker_closed(service: str) -> None:
    """Alert when a circuit breaker recovers."""
    manager = get_alert_manager()
    manager.alert(
        level=AlertLevel.INFO,
        message=f"Circuit breaker '{service}' recovered (CLOSED)",
        source="circuit_breaker",
        metadata={"service": service}
    )


def alert_budget_warning(
    tracker: str,
    used_percent: float,
    used_usd: float,
    budget_usd: float,
) -> None:
    """Alert when budget reaches warning threshold."""
    manager = get_alert_manager()
    manager.alert(
        level=AlertLevel.WARNING,
        message=f"Budget warning: '{tracker}' at {used_percent:.1f}% (${used_usd:.2f}/${budget_usd:.2f})",
        source="budget_tracker",
        metadata={
            "tracker": tracker,
            "used_percent": used_percent,
            "used_usd": used_usd,
            "budget_usd": budget_usd,
        }
    )


def alert_budget_exceeded(
    tracker: str,
    used_usd: float,
    budget_usd: float,
) -> None:
    """Alert when budget is exceeded."""
    manager = get_alert_manager()
    manager.alert(
        level=AlertLevel.CRITICAL,
        message=f"BUDGET EXCEEDED: '{tracker}' at ${used_usd:.2f} (limit: ${budget_usd:.2f})",
        source="budget_tracker",
        metadata={
            "tracker": tracker,
            "used_usd": used_usd,
            "budget_usd": budget_usd,
            "overage_usd": used_usd - budget_usd,
        },
        force=True,  # Always send budget exceeded alerts
    )


def alert_rate_limit_exhausted(provider: str, limit_type: str = "daily") -> None:
    """Alert when rate limit is exhausted."""
    manager = get_alert_manager()
    manager.alert(
        level=AlertLevel.ERROR,
        message=f"Rate limit exhausted: '{provider}' {limit_type} limit reached",
        source="rate_limiter",
        metadata={
            "provider": provider,
            "limit_type": limit_type,
        }
    )


def alert_pipeline_failed(
    job_id: str,
    layer: str,
    error: str,
) -> None:
    """Alert when a pipeline run fails."""
    manager = get_alert_manager()
    manager.alert(
        level=AlertLevel.ERROR,
        message=f"Pipeline failed at {layer}: {error}",
        source="pipeline",
        metadata={
            "job_id": job_id,
            "layer": layer,
            "error": error,
        }
    )


# =============================================================================
# Global Manager Instance
# =============================================================================

_global_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """Get or create the global alert manager."""
    global _global_manager
    if _global_manager is None:
        _global_manager = AlertManager()
    return _global_manager


def reset_alert_manager() -> None:
    """Reset the global alert manager (for testing)."""
    global _global_manager
    if _global_manager:
        _global_manager.clear_history()
    _global_manager = None
