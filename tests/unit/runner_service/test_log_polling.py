"""
Unit tests for log_polling route - structured log parsing.

Tests the _parse_log_entry function which extracts backend attribution
metadata (backend, tier, cost_usd) from JSON-formatted structured logs.
"""

import json
import pytest

from runner_service.routes.log_polling import _parse_log_entry


class TestParseLogEntry:
    """Tests for _parse_log_entry function."""

    def test_plain_text_log(self):
        """Plain text logs are returned as-is."""
        result = _parse_log_entry("Starting pipeline...", 0)

        assert result == {
            "index": 0,
            "message": "Starting pipeline...",
        }

    def test_plain_text_with_special_chars(self):
        """Plain text with special characters works correctly."""
        result = _parse_log_entry("Processing 50% complete...", 5)

        assert result["index"] == 5
        assert result["message"] == "Processing 50% complete..."

    def test_llm_call_complete_with_backend(self):
        """LLM call complete logs include backend attribution."""
        log = json.dumps({
            "timestamp": "2024-01-15T10:30:00Z",
            "event": "llm_call_complete",
            "job_id": "abc123",
            "step_name": "grader",
            "backend": "claude_cli",
            "model": "claude-sonnet-4-5-20250929",
            "tier": "middle",
            "status": "complete",
            "duration_ms": 1500,
            "cost_usd": 0.05,
        })

        result = _parse_log_entry(log, 3)

        assert result["index"] == 3
        assert result["backend"] == "claude_cli"
        assert result["tier"] == "middle"
        assert result["cost_usd"] == 0.05
        assert result["event"] == "llm_call_complete"
        assert result["model"] == "claude-sonnet-4-5-20250929"
        assert "grader" in result["message"]

    def test_llm_call_with_langchain_fallback(self):
        """LangChain fallback logs are correctly parsed."""
        log = json.dumps({
            "event": "llm_call_fallback",
            "job_id": "def456",
            "step_name": "header_generator",
            "backend": "langchain",
            "model": "claude-sonnet-4-5-20250929",
            "tier": "high",
            "status": "fallback",
            "metadata": {
                "from_backend": "claude_cli",
                "to_backend": "langchain",
                "reason": "claude_cli_unavailable",
            },
        })

        result = _parse_log_entry(log, 7)

        assert result["backend"] == "langchain"
        assert result["tier"] == "high"
        assert result["event"] == "llm_call_fallback"

    def test_layer_start_event(self):
        """Layer start events generate readable messages."""
        log = json.dumps({
            "timestamp": "2024-01-15T10:30:00Z",
            "event": "layer_start",
            "job_id": "xyz789",
            "layer": 2,
            "layer_name": "pain_point_miner",
        })

        result = _parse_log_entry(log, 1)

        assert result["index"] == 1
        assert "pain_point_miner" in result["message"]
        assert "layer_start" in result["message"]
        # No backend for layer events
        assert "backend" not in result

    def test_layer_complete_with_duration(self):
        """Layer complete events include duration in message."""
        log = json.dumps({
            "event": "layer_complete",
            "job_id": "xyz789",
            "layer": 4,
            "layer_name": "opportunity_mapper",
            "status": "success",
            "duration_ms": 4500,
        })

        result = _parse_log_entry(log, 2)

        assert "opportunity_mapper" in result["message"]
        assert "4500ms" in result["message"]

    def test_explicit_message_field(self):
        """Explicit message field takes priority."""
        log = json.dumps({
            "event": "layer_complete",
            "message": "Custom message from layer",
            "layer": 1,
            "layer_name": "jd_extractor",
        })

        result = _parse_log_entry(log, 0)

        assert result["message"] == "Custom message from layer"

    def test_cost_usd_zero(self):
        """Zero cost is included in output."""
        log = json.dumps({
            "event": "llm_call_complete",
            "step_name": "test",
            "backend": "claude_cli",
            "tier": "low",
            "cost_usd": 0,
        })

        result = _parse_log_entry(log, 0)

        assert result["cost_usd"] == 0

    def test_invalid_json_treated_as_text(self):
        """Invalid JSON is treated as plain text."""
        result = _parse_log_entry("{invalid json", 0)

        assert result["message"] == "{invalid json"
        assert "backend" not in result

    def test_json_without_known_event(self):
        """JSON without known event uses event as message."""
        log = json.dumps({
            "event": "custom_event",
            "data": "some data",
        })

        result = _parse_log_entry(log, 0)

        assert result["message"] == "custom_event"
        assert result["event"] == "custom_event"

    def test_empty_string(self):
        """Empty string is handled gracefully."""
        result = _parse_log_entry("", 0)

        assert result["index"] == 0
        assert result["message"] == ""

    def test_whitespace_before_json(self):
        """Whitespace before JSON is handled."""
        log = "  " + json.dumps({
            "event": "test",
            "backend": "claude_cli",
        })

        result = _parse_log_entry(log, 0)

        # Should still parse as JSON (strip() is called)
        assert result["backend"] == "claude_cli"

    def test_llm_call_error(self):
        """LLM call error events are parsed correctly."""
        log = json.dumps({
            "event": "llm_call_error",
            "step_name": "fit_scorer",
            "backend": "claude_cli",
            "tier": "middle",
            "status": "error",
            "error": "Rate limit exceeded",
            "duration_ms": 500,
        })

        result = _parse_log_entry(log, 0)

        assert result["backend"] == "claude_cli"
        assert result["tier"] == "middle"
        assert result["event"] == "llm_call_error"
        assert "fit_scorer" in result["message"]
        assert "error" in result["message"]
