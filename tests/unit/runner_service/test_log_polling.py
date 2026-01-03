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
        """Plain text logs are returned with source='python'."""
        result = _parse_log_entry("Starting pipeline...", 0)

        assert result == {
            "index": 0,
            "message": "Starting pipeline...",
            "source": "python",
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

    def test_none_log_handled_gracefully(self):
        """None log value is handled gracefully."""
        result = _parse_log_entry(None, 0)

        assert result["index"] == 0
        assert result["message"] == ""
        assert result["source"] == "unknown"

    def test_python_logger_format_with_timestamp(self):
        """Python logger format with timestamp is parsed correctly."""
        log = "2025-01-15 10:22:33 [INFO] module.name: Starting CV generation"
        result = _parse_log_entry(log, 0)

        assert result["source"] == "python"
        assert result["level"] == "info"
        assert result["message"] == "Starting CV generation"

    def test_python_logger_format_without_timestamp(self):
        """Python logger format without timestamp is parsed."""
        log = "[ERROR] pipeline.runner: Something went wrong"
        result = _parse_log_entry(log, 5)

        assert result["source"] == "python"
        assert result["level"] == "error"
        assert result["message"] == "Something went wrong"

    def test_component_log_format(self):
        """Component log format [Component:context] is parsed."""
        log = "[ClaudeCLI:job123] Invoking Claude CLI with max_turns=3"
        result = _parse_log_entry(log, 2)

        assert result["source"] == "python"
        assert result["component"] == "ClaudeCLI"
        assert result["context"] == "job123"
        assert result["message"] == "Invoking Claude CLI with max_turns=3"

    def test_verbose_context_fields_extracted(self):
        """Verbose context fields (prompt_length, prompt_preview, max_turns) are extracted."""
        log = json.dumps({
            "event": "llm_call_error",
            "step_name": "header_generator",
            "backend": "claude_cli",
            "error": "CLI error",
            "prompt_length": 4523,
            "prompt_preview": "You are a professional CV writer...",
            "max_turns": 3,
        })

        result = _parse_log_entry(log, 0)

        assert result["source"] == "structured"
        assert result["prompt_length"] == 4523
        assert result["prompt_preview"] == "You are a professional CV writer..."
        assert result["max_turns"] == 3

    def test_structured_log_has_source_structured(self):
        """JSON structured logs have source='structured'."""
        log = json.dumps({
            "event": "layer_start",
            "layer_name": "fetch_job",
        })

        result = _parse_log_entry(log, 0)

        assert result["source"] == "structured"

    def test_invalid_json_has_source_python(self):
        """Invalid JSON starting with { has source='python'."""
        result = _parse_log_entry("{incomplete json", 0)

        assert result["source"] == "python"
        assert result["message"] == "{incomplete json"

    def test_error_fields_extracted_for_browser_visibility(self):
        """Error fields (error, cli_error, duration_ms) are extracted for browser console visibility.

        These fields were previously dropped by whitelist-based extraction,
        preventing the browser from seeing CLI error details.
        """
        log = json.dumps({
            "event": "llm_error",
            "message": "Claude CLI failed: Error: Reached max turns (3)",
            "backend": "claude_cli",
            "error": "Error: Reached max turns (3)",
            "cli_error": "Reached max turns (3)",
            "duration_ms": 2500,
            "prompt_length": 5000,
            "prompt_preview": "You are a professional CV writer...",
            "max_turns": 3,
        })

        result = _parse_log_entry(log, 0)

        # Verify error fields are now extracted (the fix for log bubbling)
        assert result["error"] == "Error: Reached max turns (3)"
        assert result["cli_error"] == "Reached max turns (3)"
        assert result["duration_ms"] == 2500
        # Also verify other context fields still work
        assert result["prompt_length"] == 5000
        assert result["max_turns"] == 3

    def test_embedded_json_with_traceback(self):
        """
        Embedded JSON format '❌ layer_key: {json}' is parsed correctly.

        This format is used by create_layer_callback for structured error logs
        with traceback metadata for CLI panel display.
        """
        # Note: In real usage, json.dumps properly escapes newlines as \\n
        traceback_text = "Traceback (most recent call last):\\n  File test.py, line 10"
        embedded_json = json.dumps({
            "timestamp": "2025-01-01T00:00:00",
            "event": "cv_struct_error",
            "message": "CV generation failed: TypeError",
            "job_id": "abc123",
            "layer": 6,
            "layer_name": "cv_generator_v2",
            "metadata": {
                "traceback": traceback_text,
                "error_type": "TypeError",
                "error_message": "can only concatenate list",
            }
        })
        log = f"❌ cv_struct_error: {embedded_json}"

        result = _parse_log_entry(log, 0)

        # Verify it's recognized as structured_embedded (not plain text)
        assert result["source"] == "structured_embedded"
        assert result["message"] == "CV generation failed: TypeError"
        assert result["event"] == "cv_struct_error"
        assert result["layer"] == 6
        assert result["layer_name"] == "cv_generator_v2"

        # Critical: Verify traceback is extracted for CLI panel
        assert result["metadata"]["traceback"] == traceback_text
        assert result["traceback"] == traceback_text
        assert result["error_type"] == "TypeError"

    def test_embedded_json_with_invalid_json_falls_through(self):
        """
        If embedded JSON looks valid but isn't, fall through to plain text.
        """
        log = "❌ cv_struct_error: {this is not valid json}"

        result = _parse_log_entry(log, 0)

        # Should fall through to plain text parsing
        assert result["source"] == "python"
        assert "cv_struct_error" in result["message"]

    def test_regular_colon_in_text_not_parsed_as_json(self):
        """
        Regular text with colons but no JSON should not be parsed as JSON.
        """
        log = "Processing: this is a message with colon"

        result = _parse_log_entry(log, 0)

        assert result["source"] == "python"
        assert result["message"] == "Processing: this is a message with colon"


class TestCVGenerationEvents:
    """Tests for CV generation-specific event parsing."""

    def test_phase_start_event(self):
        """Phase start events are formatted with emoji and phase message."""
        log = json.dumps({
            "event": "phase_start",
            "phase": 2,
            "metadata": {
                "message": "Generating role bullets"
            }
        })

        result = _parse_log_entry(log, 0)

        assert "📋" in result["message"]
        assert "Generating role bullets" in result["message"]
        assert result["phase"] == 2

    def test_phase_complete_event(self):
        """Phase complete events include duration and checkmark."""
        log = json.dumps({
            "event": "phase_complete",
            "phase": 2,
            "duration_ms": 5000,
            "metadata": {
                "message": "Role bullets generated"
            }
        })

        result = _parse_log_entry(log, 0)

        assert "✅" in result["message"]
        assert "5000ms" in result["message"]
        assert result["phase"] == 2

    def test_subphase_start_event(self):
        """Subphase start events show role info."""
        log = json.dumps({
            "event": "subphase_start",
            "metadata": {
                "subphase": "role_Anthropic",
                "role_title": "Solutions Engineer"
            }
        })

        result = _parse_log_entry(log, 0)

        assert "🔹" in result["message"]
        assert "role_Anthropic" in result["message"]
        assert "Solutions Engineer" in result["message"]
        assert result["subphase"] == "role_Anthropic"

    def test_subphase_complete_event(self):
        """Subphase complete events show bullet count and duration."""
        log = json.dumps({
            "event": "subphase_complete",
            "duration_ms": 3500,
            "metadata": {
                "subphase": "role_Anthropic",
                "bullets_generated": 5
            }
        })

        result = _parse_log_entry(log, 0)

        assert "✓" in result["message"]
        assert "5 bullets" in result["message"]
        assert "3500ms" in result["message"]

    def test_decision_point_bullet_generation(self):
        """Decision point for bullet generation shows count and persona."""
        log = json.dumps({
            "event": "decision_point",
            "metadata": {
                "decision": "bullet_generation",
                "output": {
                    "bullets_count": 5,
                    "persona_used": "METRIC_MAESTRO"
                }
            }
        })

        result = _parse_log_entry(log, 0)

        assert "📝" in result["message"]
        assert "5 bullets" in result["message"]
        assert "METRIC_MAESTRO" in result["message"]
        assert result["decision"] == "bullet_generation"

    def test_decision_point_cv_grade(self):
        """Decision point for grading shows score and pass/fail."""
        log = json.dumps({
            "event": "decision_point",
            "metadata": {
                "decision": "cv_grade",
                "composite_score": 8.7,
                "passed": True
            }
        })

        result = _parse_log_entry(log, 0)

        assert "✅" in result["message"]
        assert "8.7" in result["message"]
        assert result["decision"] == "cv_grade"

    def test_decision_point_cv_grade_failed(self):
        """Decision point for failed grading shows fail icon."""
        log = json.dumps({
            "event": "decision_point",
            "metadata": {
                "decision": "cv_grade",
                "composite_score": 6.5,
                "passed": False
            }
        })

        result = _parse_log_entry(log, 0)

        assert "❌" in result["message"]
        assert "6.5" in result["message"]

    def test_validation_result_ats_passed(self):
        """Validation result for ATS coverage shows percentage."""
        log = json.dumps({
            "event": "validation_result",
            "metadata": {
                "validation": "ats_coverage",
                "passed": True,
                "coverage_pct": 87
            }
        })

        result = _parse_log_entry(log, 0)

        assert "✅" in result["message"]
        assert "ATS Coverage" in result["message"]
        assert "87%" in result["message"]
        assert result["validation"] == "ats_coverage"
        assert result["validation_passed"] is True

    def test_validation_result_keyword_failed(self):
        """Validation result for keyword placement shows warning on fail."""
        log = json.dumps({
            "event": "validation_result",
            "metadata": {
                "validation": "keyword_placement",
                "passed": False,
                "top_third_pct": 35
            }
        })

        result = _parse_log_entry(log, 0)

        assert "⚠️" in result["message"]
        assert "35%" in result["message"]
        assert result["validation_passed"] is False

    def test_retry_attempt_event(self):
        """Retry attempt events show attempt number and error."""
        log = json.dumps({
            "event": "retry_attempt",
            "metadata": {
                "attempt": 2,
                "error": "Pydantic validation failed: missing field 'composite_score'"
            }
        })

        result = _parse_log_entry(log, 0)

        assert "⚠️" in result["message"]
        assert "Retry attempt 2" in result["message"]
        assert "Pydantic" in result["message"]
        assert result["level"] == "warning"

    def test_grading_error_event(self):
        """Grading error events show error type and message."""
        log = json.dumps({
            "event": "grading_error",
            "metadata": {
                "error_type": "pydantic_validation",
                "error": "3 validation errors: missing composite_score"
            }
        })

        result = _parse_log_entry(log, 0)

        assert "❌" in result["message"]
        assert "pydantic_validation" in result["message"]
        assert result["level"] == "error"

    def test_grading_parsed_success(self):
        """Grading parsed event shows final score."""
        log = json.dumps({
            "event": "grading_parsed",
            "metadata": {
                "composite_score": 8.5,
                "passed": True
            }
        })

        result = _parse_log_entry(log, 0)

        assert "✅" in result["message"]
        assert "8.5" in result["message"]
        assert "Grading complete" in result["message"]

    def test_cv_struct_llm_call_start(self):
        """CV struct LLM call start events are formatted."""
        log = json.dumps({
            "event": "cv_struct_llm_call_start",
            "step_name": "cv_grader",
            "backend": "claude_cli"
        })

        result = _parse_log_entry(log, 0)

        assert "🔄" in result["message"]
        assert "cv_grader" in result["message"]
        assert "claude_cli" in result["message"]

    def test_cv_struct_llm_call_complete(self):
        """CV struct LLM call complete events show duration."""
        log = json.dumps({
            "event": "cv_struct_llm_call_complete",
            "step_name": "cv_grader",
            "backend": "claude_cli",
            "duration_ms": 2500
        })

        result = _parse_log_entry(log, 0)

        assert "✓" in result["message"]
        assert "2500ms" in result["message"]
