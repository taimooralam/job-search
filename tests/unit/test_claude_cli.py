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


# ===== CLI ERROR DETECTION IN STDOUT TESTS =====

class TestCLIErrorDetectionInStdout:
    """Test detection of CLI error messages in stdout that occur with returncode=0.

    With --output-format text, some CLI errors are written to stdout instead of
    stderr and don't set a non-zero return code. These tests verify we detect
    such errors before attempting JSON parsing.
    """

    def test_detect_cli_error_directly_unit_test(self):
        """Unit test for _detect_cli_error_in_stdout() method - no subprocess mock."""
        cli = ClaudeCLI()

        # Pattern 1: Max turns error
        max_turns_error = "Error: Reached max turns (1)"
        detected = cli._detect_cli_error_in_stdout(max_turns_error)
        assert detected == max_turns_error

        # Pattern 2: General error
        general_error = "Error: Some CLI error occurred"
        detected = cli._detect_cli_error_in_stdout(general_error)
        assert detected == general_error

        # Valid JSON - should NOT be detected as error
        valid_json = json.dumps({"status": "success", "data": "test"})
        detected = cli._detect_cli_error_in_stdout(valid_json)
        assert detected is None

        # Empty stdout
        detected = cli._detect_cli_error_in_stdout("")
        assert detected is None

        # Whitespace only
        detected = cli._detect_cli_error_in_stdout("   \n  ")
        assert detected is None

    def test_detect_max_turns_error_pattern(self):
        """Should detect 'Error: Reached max turns (N)' pattern."""
        cli = ClaudeCLI()

        test_cases = [
            ("Error: Reached max turns (1)", "Error: Reached max turns (1)"),
            ("Error: Reached max turns (5)", "Error: Reached max turns (5)"),
            ("Error: Reached max turns (10)", "Error: Reached max turns (10)"),
        ]

        for stdout, expected_error in test_cases:
            detected = cli._detect_cli_error_in_stdout(stdout)
            assert detected == expected_error

    def test_detect_general_error_prefix(self):
        """Should detect general 'Error: ' prefix when not inside JSON."""
        cli = ClaudeCLI()

        test_cases = [
            "Error: Some CLI error",
            "Error: Authentication failed",
            "Error: Credit balance is too low",
            "Error: Invalid request",
        ]

        for error_msg in test_cases:
            detected = cli._detect_cli_error_in_stdout(error_msg)
            assert detected == error_msg

    def test_does_not_detect_error_inside_json(self):
        """Should NOT detect 'Error: ' when it's inside valid JSON."""
        cli = ClaudeCLI()

        # Valid JSON that happens to contain "Error: " in the data
        json_with_error_text = json.dumps({
            "message": "Error: This is part of the data",
            "status": "success"
        })

        detected = cli._detect_cli_error_in_stdout(json_with_error_text)
        assert detected is None

    def test_does_not_detect_error_in_valid_json_response(self):
        """Should NOT detect error when stdout contains valid JSON."""
        cli = ClaudeCLI()

        valid_responses = [
            json.dumps({"pain_points": ["p1", "p2"], "strategic_needs": ["s1"]}),
            json.dumps({"status": "complete", "data": {"key": "value"}}),
            json.dumps({"result": "success"}),
        ]

        for valid_json in valid_responses:
            detected = cli._detect_cli_error_in_stdout(valid_json)
            assert detected is None

    def test_handles_whitespace_in_error_detection(self):
        """Should handle leading/trailing whitespace when detecting errors."""
        cli = ClaudeCLI()

        # Max turns error with whitespace
        max_turns_with_space = "  Error: Reached max turns (1)  \n"
        detected = cli._detect_cli_error_in_stdout(max_turns_with_space)
        assert detected == "Error: Reached max turns (1)"

        # General error with whitespace
        general_with_space = "\n  Error: Some error  \n"
        detected = cli._detect_cli_error_in_stdout(general_with_space)
        assert detected == "Error: Some error"

    def test_does_not_match_partial_max_turns_pattern(self):
        """Should NOT match partial or malformed max turns patterns."""
        cli = ClaudeCLI()

        # These should NOT match the strict max turns pattern
        non_matching = [
            "Error: Reached max turns",  # Missing (N)
            "Error: Reached max turns ()",  # Empty parens
            "Error: Reached max turns (abc)",  # Non-numeric
            "Prefix Error: Reached max turns (1)",  # Extra prefix
            "Error: Reached max turns (1) Suffix",  # Extra suffix
        ]

        for text in non_matching:
            detected = cli._detect_cli_error_in_stdout(text)
            # These might match the general error pattern instead
            if text.strip().startswith("Error: ") and not text.strip().startswith("{"):
                # General pattern match is OK
                assert detected is not None
            else:
                assert detected is None

    @patch('subprocess.run')
    def test_invoke_detects_max_turns_error_in_stdout(self, mock_subprocess_run):
        """Integration test: invoke() detects max turns error with returncode=0."""
        # Simulate CLI returning error message in stdout with successful exit code
        mock_result = MagicMock()
        mock_result.returncode = 0  # Success exit code, but error in stdout
        mock_result.stdout = "Error: Reached max turns (1)"
        mock_result.stderr = ""
        mock_subprocess_run.return_value = mock_result

        cli = ClaudeCLI()
        result = cli.invoke(prompt="test prompt", job_id="test_max_turns_001")

        # Should detect as error despite returncode=0
        assert result.success is False
        assert result.error == "Error: Reached max turns (1)"
        assert result.result is None
        assert result.raw_result == "Error: Reached max turns (1)"

    @patch('subprocess.run')
    def test_invoke_detects_general_cli_error_in_stdout(self, mock_subprocess_run):
        """Integration test: invoke() detects general CLI error with returncode=0."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Error: Credit balance is too low"
        mock_result.stderr = ""
        mock_subprocess_run.return_value = mock_result

        cli = ClaudeCLI()
        result = cli.invoke(prompt="test prompt", job_id="test_cli_error_001")

        assert result.success is False
        assert result.error == "Error: Credit balance is too low"
        assert result.result is None

    @patch('subprocess.run')
    def test_invoke_valid_json_not_detected_as_error(self, mock_subprocess_run, valid_cli_output):
        """Integration test: Valid JSON response should NOT be detected as error."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = valid_cli_output
        mock_result.stderr = ""
        mock_subprocess_run.return_value = mock_result

        cli = ClaudeCLI()
        result = cli.invoke(prompt="test prompt", job_id="test_valid_json_001")

        # Should successfully parse JSON, not detect as error
        assert result.success is True
        assert result.error is None
        assert result.result is not None
        assert "pain_points" in result.result

    @patch('subprocess.run')
    def test_invoke_logs_cli_error_with_prompt_context(self, mock_subprocess_run):
        """Integration test: Should log detailed error info when CLI error detected."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Error: Reached max turns (1)"
        mock_result.stderr = ""
        mock_subprocess_run.return_value = mock_result

        # Use custom log callback to verify logging
        log_events = []
        def capture_log(job_id, level, data):
            log_events.append((job_id, level, data))

        cli = ClaudeCLI(log_callback=capture_log)
        result = cli.invoke(prompt="Test prompt that is quite long" * 10, job_id="test_logging_001")

        assert result.success is False

        # Verify error was logged with context
        error_logs = [e for e in log_events if e[1] == "error"]
        assert len(error_logs) > 0

        # Check that error log contains expected fields
        error_log_data = error_logs[0][2]
        assert "cli_error" in error_log_data
        assert "prompt_length" in error_log_data
        assert "prompt_preview" in error_log_data

    @patch('subprocess.run')
    def test_invoke_prioritizes_returncode_over_stdout_error(self, mock_subprocess_run):
        """When returncode != 0, should use stderr error (not stdout detection)."""
        # Both returncode error AND stdout error present
        mock_result = MagicMock()
        mock_result.returncode = 1  # Non-zero exit code
        mock_result.stdout = "Error: Reached max turns (1)"
        mock_result.stderr = "Authentication failed"
        mock_subprocess_run.return_value = mock_result

        cli = ClaudeCLI()
        result = cli.invoke(prompt="test", job_id="test_priority_001")

        # Should use stderr error from returncode check (not stdout detection)
        assert result.success is False
        assert result.error == "Authentication failed"

    @patch('subprocess.run')
    def test_invoke_handles_edge_case_error_in_multiline_stdout(self, mock_subprocess_run):
        """Should detect error even if stdout has multiple lines."""
        # Multi-line output where first line is error
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Error: Reached max turns (1)\nAdditional context\nMore info"
        mock_result.stderr = ""
        mock_subprocess_run.return_value = mock_result

        cli = ClaudeCLI()
        result = cli.invoke(prompt="test", job_id="test_multiline_001")

        # Should NOT match because of extra content (strict pattern)
        # But might match general error pattern - depends on implementation
        # Current implementation uses strip() then checks startswith
        # "Error: Reached max turns (1)\nAdditional context\nMore info".strip()
        # would be the full string, so max turns pattern won't match (not just that line)
        # and general pattern also won't match (doesn't end with just error)
        # Actually, looking at code: it strips the whole thing and checks if it starts with Error:
        # So this WOULD match the general pattern
        assert result.success is False
        assert "Error:" in result.error
