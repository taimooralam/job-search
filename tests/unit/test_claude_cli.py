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
    """Valid CLI JSON output with result and cost info."""
    return json.dumps({
        "result": json.dumps({
            "pain_points": ["Pain 1", "Pain 2", "Pain 3"],
            "strategic_needs": ["Need 1", "Need 2", "Need 3"],
            "risks_if_unfilled": ["Risk 1", "Risk 2"],
            "success_metrics": ["Metric 1", "Metric 2", "Metric 3"]
        }),
        "cost": {
            "input_tokens": 1000,
            "output_tokens": 500,
            "total_cost_usd": 0.025
        },
        "model": "claude-sonnet-4-5-20250929"
    })


@pytest.fixture
def valid_cli_output_without_cost():
    """Valid CLI output without cost information."""
    return json.dumps({
        "result": json.dumps({"status": "success", "data": "test"})
    })


@pytest.fixture
def mock_successful_subprocess(valid_cli_output):
    """Mock subprocess.run that returns success."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = valid_cli_output
    mock_result.stderr = ""
    return mock_result


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
        assert "json" in call_args
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
    def test_invocation_with_cost_tracking(self, mock_subprocess_run, mock_successful_subprocess):
        """Should extract cost information from CLI output."""
        mock_subprocess_run.return_value = mock_successful_subprocess

        cli = ClaudeCLI()
        result = cli.invoke(prompt="test", job_id="test_002")

        assert result.input_tokens == 1000
        assert result.output_tokens == 500
        assert result.cost_usd == 0.025

    @patch('subprocess.run')
    def test_invocation_handles_cli_error(self, mock_subprocess_run):
        """Should handle CLI errors gracefully."""
        mock_result = MagicMock()
        mock_result.returncode = 1
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
    def test_invocation_handles_missing_result_field(self, mock_subprocess_run):
        """Should handle CLI output missing 'result' field."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"other_field": "value"})
        mock_subprocess_run.return_value = mock_result

        cli = ClaudeCLI()
        result = cli.invoke(prompt="test", job_id="test_006")

        assert result.success is False
        assert "missing 'result' field" in result.error.lower()

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
    def test_invocation_without_json_validation(self, mock_subprocess_run):
        """Should skip JSON parsing when validate_json=False."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "result": "Plain text result, not JSON",
            "cost": {"input_tokens": 100, "output_tokens": 50}
        })
        mock_subprocess_run.return_value = mock_result

        cli = ClaudeCLI()
        result = cli.invoke(
            prompt="test",
            job_id="test_008",
            validate_json=False
        )

        assert result.success is True
        assert result.raw_result == "Plain text result, not JSON"
        assert result.result is None

    @patch('subprocess.run')
    def test_invocation_handles_unexpected_exception(self, mock_subprocess_run):
        """Should handle unexpected exceptions during invocation."""
        mock_subprocess_run.side_effect = Exception("Unexpected error")

        cli = ClaudeCLI()
        result = cli.invoke(prompt="test", job_id="test_009")

        assert result.success is False
        assert "Unexpected error" in result.error


# ===== JSON PARSING TESTS =====

class TestCLIJSONParsing:
    """Test JSON parsing logic."""

    def test_parse_clean_json(self):
        """Should parse clean JSON output."""
        cli = ClaudeCLI()
        stdout = json.dumps({
            "result": json.dumps({"status": "success"}),
            "cost": {"input_tokens": 100, "output_tokens": 50}
        })

        parsed_data, input_tok, output_tok, cost = cli._parse_cli_output(stdout)

        assert parsed_data["status"] == "success"
        assert input_tok == 100
        assert output_tok == 50

    def test_parse_json_with_missing_cost(self):
        """Should handle missing cost information."""
        cli = ClaudeCLI()
        stdout = json.dumps({
            "result": json.dumps({"status": "success"})
        })

        parsed_data, input_tok, output_tok, cost = cli._parse_cli_output(stdout)

        assert parsed_data["status"] == "success"
        assert input_tok is None
        assert output_tok is None
        assert cost is None

    def test_parse_invalid_result_json(self):
        """Should raise error when result field contains invalid JSON."""
        cli = ClaudeCLI()
        stdout = json.dumps({
            "result": "Not valid JSON",
            "cost": {}
        })

        with pytest.raises(ValueError, match="Failed to parse result JSON"):
            cli._parse_cli_output(stdout)

    def test_parse_malformed_cli_output(self):
        """Should raise error for malformed CLI output."""
        cli = ClaudeCLI()

        with pytest.raises(ValueError, match="Failed to parse CLI output"):
            cli._parse_cli_output("Not JSON at all")


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
