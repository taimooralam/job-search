"""
Unit tests for structured_logger.py LLM extensions

Tests new LLM-specific logging functionality:
- LLM fields in LogEvent (backend, model, tier, cost_usd)
- emit_llm_call method for LLM invocation tracking
"""

import json
import pytest
from io import StringIO
from unittest.mock import patch, MagicMock
import time

from src.common.structured_logger import (
    StructuredLogger,
    LogEvent,
    get_structured_logger,
    EventType,
)


class TestLogEventLLMFields:
    """Tests for new LLM-specific fields in LogEvent."""

    def test_log_event_supports_backend_field(self):
        """LogEvent should support backend field for LLM attribution."""
        event = LogEvent(
            timestamp="2025-12-21T10:00:00Z",
            event="llm_call",
            job_id="test_001",
            backend="claude_cli"
        )

        event_json = json.loads(event.to_json())
        assert event_json["backend"] == "claude_cli"

    def test_log_event_supports_model_field(self):
        """LogEvent should support model field."""
        event = LogEvent(
            timestamp="2025-12-21T10:00:00Z",
            event="llm_call",
            job_id="test_001",
            model="claude-sonnet-4-5-20250929"
        )

        event_json = json.loads(event.to_json())
        assert event_json["model"] == "claude-sonnet-4-5-20250929"

    def test_log_event_supports_tier_field(self):
        """LogEvent should support tier field."""
        event = LogEvent(
            timestamp="2025-12-21T10:00:00Z",
            event="llm_call",
            job_id="test_001",
            tier="middle"
        )

        event_json = json.loads(event.to_json())
        assert event_json["tier"] == "middle"

    def test_log_event_supports_cost_usd_field(self):
        """LogEvent should support cost_usd field."""
        event = LogEvent(
            timestamp="2025-12-21T10:00:00Z",
            event="llm_call",
            job_id="test_001",
            cost_usd=0.025
        )

        event_json = json.loads(event.to_json())
        assert event_json["cost_usd"] == 0.025

    def test_log_event_all_llm_fields_together(self):
        """LogEvent should support all LLM fields together."""
        event = LogEvent(
            timestamp="2025-12-21T10:00:00Z",
            event="llm_call_complete",
            job_id="test_001",
            backend="claude_cli",
            model="claude-sonnet-4-5-20250929",
            tier="middle",
            duration_ms=1500,
            cost_usd=0.025,
            step_name="grader",
            metadata={
                "input_tokens": 1000,
                "output_tokens": 500,
            }
        )

        event_json = json.loads(event.to_json())

        assert event_json["backend"] == "claude_cli"
        assert event_json["model"] == "claude-sonnet-4-5-20250929"
        assert event_json["tier"] == "middle"
        assert event_json["duration_ms"] == 1500
        assert event_json["cost_usd"] == 0.025
        assert event_json["step_name"] == "grader"


class TestEmitLLMCall:
    """Tests for emit_llm_call method."""

    @pytest.fixture
    def logger(self):
        """Create a logger instance."""
        return StructuredLogger(job_id="llm-test-123")

    def test_emit_llm_call_start_event(self, logger, capsys):
        """emit_llm_call with status='start' should emit correct event."""
        logger.emit_llm_call(
            step_name="grader",
            backend="claude_cli",
            model="claude-sonnet-4-5-20250929",
            tier="middle",
            status="start",
        )

        captured = capsys.readouterr()
        event = json.loads(captured.out.strip())

        assert event["event"] == "llm_call_start"
        assert event["job_id"] == "llm-test-123"
        assert event["step_name"] == "grader"
        assert event["backend"] == "claude_cli"

    def test_emit_llm_call_complete_event(self, logger, capsys):
        """emit_llm_call with status='complete' should include duration."""
        logger.emit_llm_call(
            step_name="grader",
            backend="claude_cli",
            model="claude-sonnet-4-5-20250929",
            tier="middle",
            status="complete",
            duration_ms=1500,
            cost_usd=0.025,
        )

        captured = capsys.readouterr()
        event = json.loads(captured.out.strip())

        assert event["event"] == "llm_call_complete"
        assert event["duration_ms"] == 1500
        assert event["cost_usd"] == 0.025

    def test_emit_llm_call_fallback_event(self, logger, capsys):
        """emit_llm_call with status='fallback' should log correctly."""
        logger.emit_llm_call(
            step_name="grader",
            backend="langchain",
            model="gpt-4o",
            tier="middle",
            status="fallback",
            metadata={"reason": "CLI timeout"}
        )

        captured = capsys.readouterr()
        event = json.loads(captured.out.strip())

        assert event["event"] == "llm_call_fallback"
        assert event["backend"] == "langchain"

    def test_emit_llm_call_error_event(self, logger, capsys):
        """emit_llm_call with status='error' should log error."""
        logger.emit_llm_call(
            step_name="grader",
            backend="claude_cli",
            model="claude-sonnet",
            tier="middle",
            status="error",
            error="Timeout after 180s"
        )

        captured = capsys.readouterr()
        event = json.loads(captured.out.strip())

        assert event["event"] == "llm_call_error"
        assert event["error"] == "Timeout after 180s"

    def test_emit_llm_call_includes_step_name(self, logger, capsys):
        """emit_llm_call should include step name."""
        logger.emit_llm_call(
            step_name="cv_generator",
            backend="claude_cli",
            model="claude-opus",
            tier="high",
            status="complete",
            duration_ms=5000
        )

        captured = capsys.readouterr()
        event = json.loads(captured.out.strip())

        assert event["step_name"] == "cv_generator"

    def test_emit_llm_call_with_metadata(self, logger, capsys):
        """emit_llm_call should support metadata."""
        logger.emit_llm_call(
            step_name="grader",
            backend="claude_cli",
            model="claude-sonnet",
            tier="middle",
            status="complete",
            duration_ms=2000,
            metadata={
                "input_tokens": 1500,
                "output_tokens": 750,
            }
        )

        captured = capsys.readouterr()
        event = json.loads(captured.out.strip())

        metadata = event.get("metadata", {})
        assert metadata.get("input_tokens") == 1500
        assert metadata.get("output_tokens") == 750

    def test_emit_llm_call_disabled_logger_no_output(self, capsys):
        """Disabled logger should not emit LLM call events."""
        logger = StructuredLogger(job_id="test", enabled=False)

        logger.emit_llm_call(
            step_name="grader",
            backend="claude_cli",
            model="claude-sonnet",
            tier="middle",
            status="complete"
        )

        captured = capsys.readouterr()
        assert captured.out == ""


class TestLLMEventTypes:
    """Tests for LLM-specific event types."""

    def test_llm_event_types_defined(self):
        """Should have LLM event types defined."""
        event_values = [e.value for e in EventType]

        assert "llm_call_start" in event_values
        assert "llm_call_complete" in event_values
        assert "llm_call_error" in event_values
        assert "llm_call_fallback" in event_values


class TestStructuredLoggerLLMHelpers:
    """Tests for helper methods on StructuredLogger for LLM tracking."""

    @pytest.fixture
    def logger(self):
        """Create a logger instance."""
        return StructuredLogger(job_id="helper-test-123")

    def test_logger_has_emit_llm_call_method(self, logger):
        """StructuredLogger should have emit_llm_call method."""
        assert hasattr(logger, "emit_llm_call")

    def test_logger_has_llm_call_start_method(self, logger):
        """StructuredLogger should have llm_call_start method."""
        assert hasattr(logger, "llm_call_start")

    def test_logger_has_llm_call_complete_method(self, logger):
        """StructuredLogger should have llm_call_complete method."""
        assert hasattr(logger, "llm_call_complete")

    def test_llm_call_start_emits_event(self, logger, capsys):
        """llm_call_start should emit start event."""
        logger.llm_call_start(
            step_name="grader",
            backend="claude_cli",
            model="claude-sonnet",
            tier="middle"
        )

        captured = capsys.readouterr()
        event = json.loads(captured.out.strip())

        assert event["event"] == "llm_call_start"

    def test_llm_call_complete_emits_event(self, logger, capsys):
        """llm_call_complete should emit complete event."""
        logger.llm_call_complete(
            step_name="grader",
            backend="claude_cli",
            model="claude-sonnet",
            tier="middle",
            duration_ms=1500
        )

        captured = capsys.readouterr()
        event = json.loads(captured.out.strip())

        assert event["event"] == "llm_call_complete"
        assert event["duration_ms"] == 1500


class TestLLMCostTracking:
    """Tests for cost tracking in log events."""

    @pytest.fixture
    def logger(self):
        """Create a logger instance."""
        return StructuredLogger(job_id="cost-test-123")

    def test_cost_included_in_complete_event(self, logger, capsys):
        """Complete event should include cost information."""
        logger.emit_llm_call(
            step_name="grader",
            backend="claude_cli",
            model="claude-sonnet",
            tier="middle",
            status="complete",
            duration_ms=1500,
            cost_usd=0.025
        )

        captured = capsys.readouterr()
        event = json.loads(captured.out.strip())

        assert event["cost_usd"] == 0.025

    def test_zero_cost_included(self, logger, capsys):
        """Zero cost should be included (not treated as None)."""
        logger.emit_llm_call(
            step_name="grader",
            backend="claude_cli",
            model="claude-haiku",
            tier="low",
            status="complete",
            cost_usd=0.0
        )

        captured = capsys.readouterr()
        event = json.loads(captured.out.strip())

        assert event.get("cost_usd") == 0.0

    def test_cost_aggregation_across_calls(self, logger, capsys):
        """Multiple LLM calls should emit separate cost events."""
        logger.emit_llm_call(
            step_name="grader",
            backend="claude_cli",
            model="claude-sonnet",
            tier="middle",
            status="complete",
            cost_usd=0.025
        )

        logger.emit_llm_call(
            step_name="improver",
            backend="claude_cli",
            model="claude-opus",
            tier="high",
            status="complete",
            cost_usd=0.150
        )

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")

        assert len(lines) == 2

        event1 = json.loads(lines[0])
        event2 = json.loads(lines[1])

        assert event1["cost_usd"] == 0.025
        assert event2["cost_usd"] == 0.150


class TestBackendAttribution:
    """Tests for backend attribution in logs."""

    @pytest.fixture
    def logger(self):
        """Create a logger instance."""
        return StructuredLogger(job_id="backend-test-123")

    def test_claude_cli_backend_attribution(self, logger, capsys):
        """CLI backend should be properly attributed."""
        logger.emit_llm_call(
            step_name="grader",
            backend="claude_cli",
            model="claude-sonnet",
            tier="middle",
            status="complete"
        )

        captured = capsys.readouterr()
        event = json.loads(captured.out.strip())

        assert event["backend"] == "claude_cli"

    def test_langchain_backend_attribution(self, logger, capsys):
        """LangChain fallback should be properly attributed."""
        logger.emit_llm_call(
            step_name="grader",
            backend="langchain",
            model="gpt-4o",
            tier="middle",
            status="complete"
        )

        captured = capsys.readouterr()
        event = json.loads(captured.out.strip())

        assert event["backend"] == "langchain"


class TestFactoryFunctionExtensions:
    """Tests for factory function with LLM support."""

    def test_get_structured_logger_creates_llm_capable_logger(self):
        """Factory should create logger with LLM capabilities."""
        logger = get_structured_logger("test-llm-123")

        assert isinstance(logger, StructuredLogger)
        assert hasattr(logger, "emit_llm_call")

    def test_logger_can_emit_llm_and_layer_events(self, capsys):
        """Logger should support both layer and LLM events."""
        logger = get_structured_logger("dual-test-123")

        # Emit layer event
        logger.layer_start(2)

        # Emit LLM event
        logger.emit_llm_call(
            step_name="test",
            backend="claude_cli",
            model="claude-sonnet",
            tier="middle",
            status="complete"
        )

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")

        # Should have two events
        assert len(lines) == 2


class TestTierValues:
    """Tests for tier field validation."""

    @pytest.fixture
    def logger(self):
        """Create a logger instance."""
        return StructuredLogger(job_id="tier-test-123")

    def test_low_tier_logged_correctly(self, logger, capsys):
        """Low tier should be logged as 'low'."""
        logger.emit_llm_call(
            step_name="grader",
            backend="claude_cli",
            model="claude-haiku",
            tier="low",
            status="complete"
        )

        captured = capsys.readouterr()
        event = json.loads(captured.out.strip())

        assert event["tier"] == "low"

    def test_middle_tier_logged_correctly(self, logger, capsys):
        """Middle tier should be logged as 'middle'."""
        logger.emit_llm_call(
            step_name="grader",
            backend="claude_cli",
            model="claude-sonnet",
            tier="middle",
            status="complete"
        )

        captured = capsys.readouterr()
        event = json.loads(captured.out.strip())

        assert event["tier"] == "middle"

    def test_high_tier_logged_correctly(self, logger, capsys):
        """High tier should be logged as 'high'."""
        logger.emit_llm_call(
            step_name="grader",
            backend="claude_cli",
            model="claude-opus",
            tier="high",
            status="complete"
        )

        captured = capsys.readouterr()
        event = json.loads(captured.out.strip())

        assert event["tier"] == "high"
