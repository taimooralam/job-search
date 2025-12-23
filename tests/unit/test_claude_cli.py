"""
Unit tests for src/common/claude_cli.py

Tests the ClaudeCLI wrapper for invoking Claude Code CLI in headless mode.
Covers three-tier model support, JSON parsing, error handling, and batch operations.
"""

import json
import pytest
import subprocess
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from src.common.claude_cli import (
    ClaudeCLI,
    CLIResult,
    invoke_claude,
    CLAUDE_MODEL_TIERS,
    TierType,
)


# ===== FIXTURES =====

@pytest.fixture
def valid_cli_output():
    """Valid CLI text output - raw LLM JSON response (not wrapper).

    With --output-format text, CLI returns the raw LLM response directly.
    """
    return json.dumps({
        "pain_points": ["Pain 1", "Pain 2", "Pain 3"],
        "strategic_needs": ["Need 1", "Need 2", "Need 3"],
        "risks_if_unfilled": ["Risk 1", "Risk 2"],
        "success_metrics": ["Metric 1", "Metric 2", "Metric 3"]
    })


@pytest.fixture
def valid_cli_output_without_cost():
    """Valid CLI text output (no cost info with text format)."""
    return json.dumps({"status": "success", "data": "test"})


@pytest.fixture
def mock_successful_subprocess(valid_cli_output):
    """Mock subprocess.run that returns success."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = valid_cli_output
    mock_result.stderr = ""
    return mock_result


@pytest.fixture
def valid_cli_output_v2():
    """Valid CLI text output - same as valid_cli_output with text format.

    Note: With --output-format text, we don't get the wrapper metadata.
    This fixture now just returns the raw LLM JSON response.
    """
    return json.dumps({
        "pain_points": ["Pain 1", "Pain 2", "Pain 3"],
        "strategic_needs": ["Need 1", "Need 2", "Need 3"],
        "risks_if_unfilled": ["Risk 1", "Risk 2"],
        "success_metrics": ["Metric 1", "Metric 2", "Metric 3"]
    })


@pytest.fixture
def plain_text_output():
    """Plain text CLI output (non-JSON LLM response)."""
    return "This is a plain text response from Claude, not JSON."


# ===== INITIALIZATION TESTS =====

class TestClaudeCLIInitialization:
    """Test ClaudeCLI initialization and configuration."""

    def test_init_with_default_tier(self):
        """Should initialize with middle tier by default."""
        cli = ClaudeCLI()
        assert cli.tier == "middle"
        assert cli.model == CLAUDE_MODEL_TIERS["middle"]
        assert cli.timeout == 180

    def test_init_with_low_tier(self):
        """Should initialize with low tier (Haiku)."""
        cli = ClaudeCLI(tier="low")
        assert cli.tier == "low"
        assert cli.model == CLAUDE_MODEL_TIERS["low"]

    def test_init_with_high_tier(self):
        """Should initialize with high tier (Opus)."""
        cli = ClaudeCLI(tier="high")
        assert cli.tier == "high"
        assert cli.model == CLAUDE_MODEL_TIERS["high"]

    def test_init_with_custom_timeout(self):
        """Should accept custom timeout value."""
        cli = ClaudeCLI(timeout=300)
        assert cli.timeout == 300

    def test_init_with_model_override(self):
        """Should allow model override."""
        custom_model = "claude-3-opus-20240229"
        cli = ClaudeCLI(model_override=custom_model)
        assert cli.model == custom_model

    @patch.dict('os.environ', {'CLAUDE_CODE_MODEL': 'claude-test-model'})
    def test_init_respects_env_override(self):
        """Should use CLAUDE_CODE_MODEL env var if set."""
        cli = ClaudeCLI()
        assert cli.model == 'claude-test-model'

    def test_init_with_log_callback(self):
        """Should accept custom log callback."""
        mock_callback = MagicMock()
        cli = ClaudeCLI(log_callback=mock_callback)
        assert cli._log_callback == mock_callback


# ===== INVOKE METHOD TESTS =====

class TestClaudeCLIInvoke:
    """Test ClaudeCLI.invoke() method."""

    @patch('subprocess.run')
    def test_successful_invocation(self, mock_subprocess_run, mock_successful_subprocess):
        """Successful invocation returns CLIResult with parsed data."""
        mock_subprocess_run.return_value = mock_successful_subprocess

        cli = ClaudeCLI(tier="middle")
        result = cli.invoke(
            prompt="Extract pain points from this JD",
            job_id="test_001"
        )

        # Verify subprocess was called correctly
        mock_subprocess_run.assert_called_once()
        call_args = mock_subprocess_run.call_args[0][0]
        assert call_args[0] == "claude"
        assert "-p" in call_args
        assert "--output-format" in call_args
        assert "text" in call_args  # Changed from json to text format
        assert "--model" in call_args
        assert CLAUDE_MODEL_TIERS["middle"] in call_args

        # Verify result
        assert result.success is True
        assert result.job_id == "test_001"
        assert result.model == CLAUDE_MODEL_TIERS["middle"]
        assert result.tier == "middle"
        assert result.result is not None
        assert "pain_points" in result.result

    @patch('subprocess.run')
    def test_invocation_with_text_format(self, mock_subprocess_run, mock_successful_subprocess):
        """With text format, cost info is not available."""
        mock_subprocess_run.return_value = mock_successful_subprocess

        cli = ClaudeCLI()
        result = cli.invoke(prompt="test", job_id="test_002")

        # Text format doesn't include cost metadata
        assert result.input_tokens is None
        assert result.output_tokens is None
        assert result.cost_usd is None
        assert result.success is True

    @patch('subprocess.run')
    def test_invocation_handles_cli_error(self, mock_subprocess_run):
        """Should handle CLI errors gracefully."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""  # Empty stdout
        mock_result.stderr = "Authentication failed"
        mock_subprocess_run.return_value = mock_result

        cli = ClaudeCLI()
        result = cli.invoke(prompt="test", job_id="test_003")

        assert result.success is False
        assert result.error is not None
        assert "Authentication failed" in result.error

    @patch('subprocess.run')
    def test_invocation_handles_timeout(self, mock_subprocess_run):
        """Should handle subprocess timeout."""
        mock_subprocess_run.side_effect = subprocess.TimeoutExpired(
            cmd=["claude"], timeout=180
        )

        cli = ClaudeCLI(timeout=180)
        result = cli.invoke(prompt="test", job_id="test_004")

        assert result.success is False
        assert result.error is not None
        assert "timeout" in result.error.lower()

    @patch('subprocess.run')
    def test_invocation_handles_invalid_json_output(self, mock_subprocess_run):
        """Should handle invalid JSON from CLI."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Not valid JSON!"
        mock_subprocess_run.return_value = mock_result

        cli = ClaudeCLI()
        result = cli.invoke(prompt="test", job_id="test_005")

        assert result.success is False
        assert "JSON" in result.error

    @patch('subprocess.run')
    def test_invocation_handles_empty_response(self, mock_subprocess_run):
        """Should handle empty CLI response."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""  # Empty response
        mock_subprocess_run.return_value = mock_result

        cli = ClaudeCLI()
        result = cli.invoke(prompt="test", job_id="test_006")

        assert result.success is False
        assert "empty" in result.error.lower()

    @patch('subprocess.run')
    def test_invocation_with_max_turns(self, mock_subprocess_run, mock_successful_subprocess):
        """Should pass max_turns parameter to CLI."""
        mock_subprocess_run.return_value = mock_successful_subprocess

        cli = ClaudeCLI()
        cli.invoke(prompt="test", job_id="test_007", max_turns=3)

        call_args = mock_subprocess_run.call_args[0][0]
        assert "--max-turns" in call_args
        assert "3" in call_args

    @patch('subprocess.run')
    def test_invocation_without_json_validation(self, mock_subprocess_run, plain_text_output):
        """Should skip JSON parsing when validate_json=False."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = plain_text_output
        mock_subprocess_run.return_value = mock_result

        cli = ClaudeCLI()
        result = cli.invoke(
            prompt="test",
            job_id="test_008",
            validate_json=False
        )

        assert result.success is True
        assert result.raw_result == plain_text_output.strip()
        assert result.result is None

    @patch('subprocess.run')
    def test_invocation_handles_unexpected_exception(self, mock_subprocess_run):
        """Should handle unexpected exceptions during invocation."""
        mock_subprocess_run.side_effect = Exception("Unexpected error")

        cli = ClaudeCLI()
        result = cli.invoke(prompt="test", job_id="test_009")

        assert result.success is False
        assert "Unexpected error" in result.error


# NOTE: TestCLIJSONParsing class removed - we now use --output-format text
# which doesn't have the JSON wrapper format. The _parse_cli_output method was removed.


# ===== BATCH INVOCATION TESTS =====

class TestClaudeCLIBatch:
    """Test batch invocation functionality."""

    @pytest.mark.asyncio
    @patch('subprocess.run')
    async def test_batch_invocation(self, mock_subprocess_run, valid_cli_output):
        """Should invoke multiple items with concurrency control."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = valid_cli_output
        mock_subprocess_run.return_value = mock_result

        cli = ClaudeCLI()
        items = [
            {"job_id": "job_001", "prompt": "Prompt 1"},
            {"job_id": "job_002", "prompt": "Prompt 2"},
            {"job_id": "job_003", "prompt": "Prompt 3"},
        ]

        results = await cli.invoke_batch(items, max_concurrent=2)

        assert len(results) == 3
        assert all(r.success for r in results)
        assert results[0].job_id == "job_001"
        assert results[1].job_id == "job_002"
        assert results[2].job_id == "job_003"

    @pytest.mark.asyncio
    @patch('subprocess.run')
    async def test_batch_handles_failures(self, mock_subprocess_run):
        """Should handle individual failures in batch."""
        # First call succeeds, second fails
        def side_effect(*args, **kwargs):
            if not hasattr(side_effect, 'call_count'):
                side_effect.call_count = 0
            side_effect.call_count += 1

            if side_effect.call_count == 1:
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stdout = json.dumps({
                    "result": json.dumps({"status": "ok"})
                })
                return mock_result
            else:
                mock_result = MagicMock()
                mock_result.returncode = 1
                mock_result.stderr = "Error"
                return mock_result

        mock_subprocess_run.side_effect = side_effect

        cli = ClaudeCLI()
        items = [
            {"job_id": "job_001", "prompt": "Prompt 1"},
            {"job_id": "job_002", "prompt": "Prompt 2"},
        ]

        results = await cli.invoke_batch(items)

        assert len(results) == 2
        assert results[0].success is True
        assert results[1].success is False


# ===== HEALTH CHECK TESTS =====

class TestCLIHealthCheck:
    """Test CLI availability checking."""

    @patch('subprocess.run')
    def test_check_cli_available_success(self, mock_subprocess_run):
        """Should return True when CLI is available."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_subprocess_run.return_value = mock_result

        cli = ClaudeCLI()
        assert cli.check_cli_available() is True

    @patch('subprocess.run')
    def test_check_cli_not_available(self, mock_subprocess_run):
        """Should return False when CLI is not installed."""
        mock_subprocess_run.side_effect = FileNotFoundError()

        cli = ClaudeCLI()
        assert cli.check_cli_available() is False

    @patch('subprocess.run')
    def test_check_cli_timeout(self, mock_subprocess_run):
        """Should return False on timeout."""
        mock_subprocess_run.side_effect = subprocess.TimeoutExpired(
            cmd=["claude"], timeout=10
        )

        cli = ClaudeCLI()
        assert cli.check_cli_available() is False


# ===== COST ESTIMATION TESTS =====

class TestCostEstimation:
    """Test cost estimation methods."""

    def test_estimate_cost_for_fast_tier(self):
        """Should calculate correct cost for fast tier."""
        cost = ClaudeCLI.get_tier_cost_estimate(
            tier="fast",
            input_tokens=1000,
            output_tokens=500
        )

        # Fast tier: input $0.00025/1K, output $0.00125/1K
        expected = (1000 / 1000) * 0.00025 + (500 / 1000) * 0.00125
        assert cost == pytest.approx(expected, rel=1e-5)

    def test_estimate_cost_for_balanced_tier(self):
        """Should calculate correct cost for balanced tier."""
        cost = ClaudeCLI.get_tier_cost_estimate(
            tier="balanced",
            input_tokens=1000,
            output_tokens=500
        )

        # Balanced tier: input $0.003/1K, output $0.015/1K
        expected = (1000 / 1000) * 0.003 + (500 / 1000) * 0.015
        assert cost == pytest.approx(expected, rel=1e-5)

    def test_estimate_cost_for_quality_tier(self):
        """Should calculate correct cost for quality tier."""
        cost = ClaudeCLI.get_tier_cost_estimate(
            tier="quality",
            input_tokens=1000,
            output_tokens=500
        )

        # Quality tier: input $0.015/1K, output $0.075/1K
        expected = (1000 / 1000) * 0.015 + (500 / 1000) * 0.075
        assert cost == pytest.approx(expected, rel=1e-5)


# ===== TIER INFO TESTS =====

class TestTierDisplayInfo:
    """Test tier display information for UI."""

    def test_get_tier_display_info(self):
        """Should return tier information for UI rendering."""
        tiers = ClaudeCLI.get_tier_display_info()

        assert len(tiers) == 3
        assert all("value" in tier for tier in tiers)
        assert all("label" in tier for tier in tiers)
        assert all("model" in tier for tier in tiers)

        # Verify tier values
        tier_values = [t["value"] for t in tiers]
        assert "low" in tier_values
        assert "middle" in tier_values
        assert "high" in tier_values


# ===== CLIRESULT DATACLASS TESTS =====

class TestCLIResult:
    """Test CLIResult dataclass."""

    def test_create_success_result(self):
        """Should create valid success result."""
        result = CLIResult(
            job_id="test_001",
            success=True,
            result={"data": "test"},
            raw_result=None,
            error=None,
            model="claude-sonnet-4-5-20250929",
            tier="balanced",
            duration_ms=1500,
            invoked_at="2024-01-01T00:00:00Z",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.025
        )

        assert result.success is True
        assert result.job_id == "test_001"
        assert result.result["data"] == "test"
        assert result.cost_usd == 0.025

    def test_create_failure_result(self):
        """Should create valid failure result."""
        result = CLIResult(
            job_id="test_002",
            success=False,
            result=None,
            raw_result=None,
            error="CLI timeout",
            model="claude-sonnet-4-5-20250929",
            tier="balanced",
            duration_ms=180000,
            invoked_at="2024-01-01T00:00:00Z"
        )

        assert result.success is False
        assert result.error == "CLI timeout"
        assert result.result is None

    def test_cliresult_to_dict(self):
        """Should convert CLIResult to dictionary."""
        result = CLIResult(
            job_id="test_003",
            success=True,
            result={"data": "test"},
            raw_result=None,
            error=None,
            model="claude-sonnet-4-5-20250929",
            tier="balanced",
            duration_ms=1500,
            invoked_at="2024-01-01T00:00:00Z"
        )

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert result_dict["job_id"] == "test_003"
        assert result_dict["success"] is True
        assert result_dict["tier"] == "balanced"


# ===== CONVENIENCE FUNCTION TESTS =====

class TestConvenienceFunction:
    """Test invoke_claude convenience function."""

    @patch('subprocess.run')
    def test_invoke_claude_convenience(self, mock_subprocess_run, mock_successful_subprocess):
        """invoke_claude() should work as convenience wrapper."""
        mock_subprocess_run.return_value = mock_successful_subprocess

        result = invoke_claude(
            prompt="test prompt",
            job_id="test_001",
            tier="low",
            timeout=120
        )

        assert result.success is True
        assert result.tier == "low"
        assert result.job_id == "test_001"


# ===== LOG CALLBACK TESTS =====

class TestLogCallback:
    """Test log callback functionality."""

    @patch('subprocess.run')
    def test_log_callback_invoked(self, mock_subprocess_run, mock_successful_subprocess):
        """Custom log callback should be invoked during execution."""
        mock_subprocess_run.return_value = mock_successful_subprocess
        mock_callback = MagicMock()

        cli = ClaudeCLI(log_callback=mock_callback)
        cli.invoke(prompt="test", job_id="test_001")

        # Callback should have been called multiple times
        assert mock_callback.call_count >= 2  # At least start and complete

    def test_default_log_callback(self):
        """Default log callback should use logger."""
        cli = ClaudeCLI()

        # Should not raise
        cli._default_log("test_job", "info", {"message": "test"})


# ===== CLI v2.0.75 FORMAT TESTS =====

class TestTextFormat:
    """Test handling of --output-format text (the default format now).

    Note: With text format, we don't get metadata like cost/tokens.
    Error detection happens via returncode != 0 or empty response.
    """

    @patch('subprocess.run')
    def test_text_format_success(self, mock_subprocess_run, valid_cli_output):
        """Should correctly parse text format response as JSON."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = valid_cli_output
        mock_result.stderr = ""
        mock_subprocess_run.return_value = mock_result

        cli = ClaudeCLI()
        result = cli.invoke(prompt="test", job_id="test_text_001")

        assert result.success is True
        # No cost metadata with text format
        assert result.input_tokens is None
        assert result.output_tokens is None
        assert result.cost_usd is None
        # But we get the parsed data
        assert "pain_points" in result.result

    @patch('subprocess.run')
    def test_text_format_cli_error_returncode(self, mock_subprocess_run):
        """Should detect CLI errors via returncode."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Credit balance is too low"
        mock_subprocess_run.return_value = mock_result

        cli = ClaudeCLI()
        result = cli.invoke(prompt="test", job_id="test_error_001")

        assert result.success is False
        assert "Credit balance is too low" in result.error

    @patch('subprocess.run')
    def test_text_format_empty_response(self, mock_subprocess_run):
        """Should fail on empty CLI response."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_subprocess_run.return_value = mock_result

        cli = ClaudeCLI()
        result = cli.invoke(prompt="test", job_id="test_empty_001")

        assert result.success is False
        assert "empty" in result.error.lower()

    @patch('subprocess.run')
    def test_text_format_raw_mode(self, mock_subprocess_run, plain_text_output):
        """Should return raw text when validate_json=False."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = plain_text_output
        mock_result.stderr = ""
        mock_subprocess_run.return_value = mock_result

        cli = ClaudeCLI()
        result = cli.invoke(prompt="test", job_id="test_raw_001", validate_json=False)

        assert result.success is True
        assert result.raw_result == plain_text_output.strip()
        assert result.result is None

    def test_extract_cost_info_legacy_format(self):
        """Should extract cost from legacy format (backward compat helper)."""
        cli = ClaudeCLI()
        cli_output = {
            "cost": {
                "input_tokens": 200,
                "output_tokens": 100,
                "total_cost_usd": 0.10
            }
        }
        input_tok, output_tok, cost = cli._extract_cost_info(cli_output)

        assert input_tok == 200
        assert output_tok == 100
        assert cost == 0.10

    def test_extract_cost_info_no_cost_data(self):
        """Should return None values when no cost data present."""
        cli = ClaudeCLI()
        cli_output = {"result": "some result"}
        input_tok, output_tok, cost = cli._extract_cost_info(cli_output)

        assert input_tok is None
        assert output_tok is None
        assert cost is None


# NOTE: Tests for errors array handling removed since we now use --output-format text
# which doesn't include JSON wrapper metadata. Error detection is now via returncode or empty response.
# ===== ERRORS ARRAY HANDLING TESTS =====

class TestErrorsArrayHandling:
    """Test handling of errors array in CLI output (v2.0.75+ behavior)."""

    @pytest.fixture
    def errors_array_cli_output(self):
        """CLI output with errors array but no is_error flag."""
        return json.dumps({
            "type": "result",
            "subtype": "success",
            "duration_ms": 5324,
            "duration_api_ms": 4823,
            "is_error": False,
            "num_turns": 1,
            "session_id": "test-session",
            "total_cost_usd": 0.05,
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "modelUsage": {},
            "permission_denials": [],
            "uuid": "test-uuid",
            "errors": [
                {"message": "Context window exceeded", "type": "context_length_error"},
                {"message": "Rate limit reached", "type": "rate_limit_error"}
            ]
        })

    @pytest.fixture
    def errors_array_string_cli_output(self):
        """CLI output with errors array containing string errors."""
        return json.dumps({
            "type": "result",
            "is_error": False,
            "errors": ["Simple error message", "Another error"]
        })

    @pytest.fixture
    def errors_array_empty_cli_output(self):
        """CLI output with empty errors array (should succeed)."""
        return json.dumps({
            "type": "result",
            "is_error": False,
            "result": json.dumps({"status": "success"}),
            "errors": []
        })

    def test_parse_errors_array_with_dict_errors(self, errors_array_cli_output):
        """Should detect errors array with dict error objects."""
        cli = ClaudeCLI()

        with pytest.raises(ValueError, match="CLI returned errors:"):
            cli._parse_cli_output(errors_array_cli_output)

    def test_parse_errors_array_extracts_messages(self, errors_array_cli_output):
        """Should extract error messages from dict error objects."""
        cli = ClaudeCLI()

        try:
            cli._parse_cli_output(errors_array_cli_output)
            pytest.fail("Expected ValueError")
        except ValueError as e:
            assert "Context window exceeded" in str(e)
            assert "Rate limit reached" in str(e)

    def test_parse_errors_array_with_string_errors(self, errors_array_string_cli_output):
        """Should handle errors array with string errors."""
        cli = ClaudeCLI()

        with pytest.raises(ValueError, match="CLI returned errors:.*Simple error message"):
            cli._parse_cli_output(errors_array_string_cli_output)

    def test_parse_empty_errors_array_succeeds(self, errors_array_empty_cli_output):
        """Should succeed when errors array is empty."""
        cli = ClaudeCLI()

        parsed_data, _, _, _ = cli._parse_cli_output(errors_array_empty_cli_output)
        assert parsed_data["status"] == "success"

    @patch('subprocess.run')
    def test_invoke_handles_errors_array(self, mock_subprocess_run, errors_array_cli_output):
        """Should fail invocation when errors array present."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = errors_array_cli_output
        mock_result.stderr = ""
        mock_subprocess_run.return_value = mock_result

        cli = ClaudeCLI()
        result = cli.invoke(prompt="test", job_id="test_errors_001")

        assert result.success is False
        assert "Context window exceeded" in result.error
        assert "Rate limit reached" in result.error

    @patch('subprocess.run')
    def test_invoke_raw_mode_handles_errors_array(self, mock_subprocess_run, errors_array_cli_output):
        """Should fail invocation in raw mode when errors array present."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = errors_array_cli_output
        mock_result.stderr = ""
        mock_subprocess_run.return_value = mock_result

        cli = ClaudeCLI()
        result = cli.invoke(prompt="test", job_id="test_errors_002", validate_json=False)

        assert result.success is False
        assert "CLI returned errors:" in result.error

    @patch('subprocess.run')
    def test_is_error_takes_precedence_over_errors_array(self, mock_subprocess_run):
        """When both is_error and errors array present, is_error is checked first."""
        cli_output = json.dumps({
            "type": "result",
            "is_error": True,
            "result": "Primary error message",
            "errors": [{"message": "Secondary error"}]
        })
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = cli_output
        mock_result.stderr = ""
        mock_subprocess_run.return_value = mock_result

        cli = ClaudeCLI()
        result = cli.invoke(prompt="test", job_id="test_precedence")

        assert result.success is False
        # Should use is_error result, not errors array
        assert "Primary error message" in result.error

    def test_parse_errors_array_with_type_fallback(self):
        """Should use type field if message is missing."""
        cli = ClaudeCLI()
        cli_output = json.dumps({
            "type": "result",
            "is_error": False,
            "errors": [{"type": "unknown_error_type"}]
        })

        with pytest.raises(ValueError, match="unknown_error_type"):
            cli._parse_cli_output(cli_output)
