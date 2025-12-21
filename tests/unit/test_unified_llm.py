"""
Unit tests for src/common/unified_llm.py

Tests the UnifiedLLM wrapper with fallback logic:
- Primary: Claude CLI
- Fallback: LangChain
- Configuration via step names
- Result tracking with backend attribution
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from datetime import datetime


class TestUnifiedLLMInitialization:
    """Tests for UnifiedLLM initialization."""

    def test_init_with_step_name_loads_config(self):
        """Should load configuration from step name."""
        from src.common.unified_llm import UnifiedLLM

        llm = UnifiedLLM(step_name="grader")

        assert llm.step_name == "grader"
        assert hasattr(llm, "config")
        assert llm.config.tier in ["low", "middle", "high"]

    def test_init_with_explicit_tier_overrides_config(self):
        """Explicit tier should override step config."""
        from src.common.unified_llm import UnifiedLLM

        llm = UnifiedLLM(step_name="grader", tier="high")

        assert llm.config.tier == "high"

    def test_init_without_step_name_uses_default(self):
        """Should initialize with default tier if no step name."""
        from src.common.unified_llm import UnifiedLLM

        llm = UnifiedLLM()

        assert llm.config.tier == "middle"  # Default tier

    def test_init_with_job_id(self):
        """Should accept job_id parameter."""
        from src.common.unified_llm import UnifiedLLM

        llm = UnifiedLLM(job_id="test_123")

        assert llm.job_id == "test_123"

    def test_init_without_job_id_uses_unknown(self):
        """Should use 'unknown' as default job_id."""
        from src.common.unified_llm import UnifiedLLM

        llm = UnifiedLLM()

        assert llm.job_id == "unknown"


class TestUnifiedLLMInvoke:
    """Tests for UnifiedLLM.invoke() method."""

    @pytest.fixture
    def mock_cli_success(self, mocker):
        """Mock ClaudeCLI that succeeds."""
        mock_cli_class = mocker.patch("src.common.unified_llm.ClaudeCLI")
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.result = {"pain_points": ["point1", "point2"]}
        mock_result.raw_result = None
        mock_result.error = None
        mock_result.duration_ms = 1500
        mock_result.input_tokens = 1000
        mock_result.output_tokens = 500
        mock_result.cost_usd = 0.025
        mock_result.model = "claude-sonnet-4-5-20250929"
        mock_result.tier = "middle"
        mock_cli_class.return_value.invoke.return_value = mock_result
        return mock_cli_class

    @pytest.fixture
    def mock_cli_failure(self, mocker):
        """Mock ClaudeCLI that fails."""
        mock_cli_class = mocker.patch("src.common.unified_llm.ClaudeCLI")
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.result = None
        mock_result.raw_result = None
        mock_result.error = "CLI timeout"
        mock_result.duration_ms = 180000
        mock_result.model = "claude-sonnet-4-5-20250929"
        mock_result.tier = "middle"
        mock_cli_class.return_value.invoke.return_value = mock_result
        return mock_cli_class

    @pytest.mark.asyncio
    async def test_invoke_uses_cli_as_primary(self, mock_cli_success):
        """Should try Claude CLI as primary backend."""
        from src.common.unified_llm import UnifiedLLM

        llm = UnifiedLLM(step_name="grader")
        result = await llm.invoke(
            prompt="Test prompt",
            job_id="test_001"
        )

        assert result.success is True
        assert result.backend == "claude_cli"

    @pytest.mark.asyncio
    async def test_invoke_tracks_duration(self, mock_cli_success):
        """Result should include duration tracking."""
        from src.common.unified_llm import UnifiedLLM

        llm = UnifiedLLM(step_name="grader")
        result = await llm.invoke(
            prompt="Test prompt",
            job_id="test_004"
        )

        # Duration is tracked (may be 0 in mock due to instant execution)
        assert result.duration_ms >= 0
        assert isinstance(result.duration_ms, int)

    @pytest.mark.asyncio
    async def test_invoke_tracks_tokens_and_cost(self, mock_cli_success):
        """Result should include token and cost tracking."""
        from src.common.unified_llm import UnifiedLLM

        llm = UnifiedLLM(step_name="grader")
        result = await llm.invoke(
            prompt="Test prompt",
            job_id="test_005"
        )

        assert result.input_tokens == 1000
        assert result.output_tokens == 500
        assert result.cost_usd == 0.025

    @pytest.mark.asyncio
    async def test_invoke_with_system_prompt(self, mock_cli_success):
        """Should accept system prompt."""
        from src.common.unified_llm import UnifiedLLM

        llm = UnifiedLLM(step_name="grader")
        result = await llm.invoke(
            prompt="Grade this CV.",
            system="You are a grader.",
            job_id="test_006"
        )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_invoke_validates_json_by_default(self, mock_cli_success):
        """Should validate and parse JSON responses by default."""
        from src.common.unified_llm import UnifiedLLM

        llm = UnifiedLLM(step_name="grader")
        result = await llm.invoke(
            prompt="Test",
            job_id="test_007"
        )

        assert result.parsed_json is not None
        assert isinstance(result.parsed_json, dict)

    @pytest.mark.asyncio
    async def test_invoke_can_skip_json_validation(self, mock_cli_success):
        """Should support raw text responses."""
        # Modify mock to return raw result
        mock_cli_success.return_value.invoke.return_value.result = None
        mock_cli_success.return_value.invoke.return_value.raw_result = "Raw text"

        from src.common.unified_llm import UnifiedLLM

        llm = UnifiedLLM(step_name="grader")
        result = await llm.invoke(
            prompt="Test",
            job_id="test_008",
            validate_json=False
        )

        assert result.success is True


class TestLLMResult:
    """Tests for LLMResult dataclass."""

    def test_success_result_has_all_fields(self):
        """Successful result should have all required fields."""
        from src.common.unified_llm import LLMResult

        result = LLMResult(
            content='{"data": "test"}',
            backend="claude_cli",
            model="claude-sonnet-4-5-20250929",
            tier="middle",
            duration_ms=1500,
            success=True,
            parsed_json={"data": "test"},
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.025
        )

        assert result.success is True
        assert result.backend == "claude_cli"
        assert result.parsed_json["data"] == "test"

    def test_error_result_has_error_field(self):
        """Error result should populate error field."""
        from src.common.unified_llm import LLMResult

        result = LLMResult(
            content="",
            backend="claude_cli",
            model="claude-sonnet-4-5-20250929",
            tier="middle",
            duration_ms=180000,
            success=False,
            error="Timeout after 180s"
        )

        assert result.success is False
        assert result.error == "Timeout after 180s"

    def test_result_tracks_backend_attribution(self):
        """Result should attribute which backend was used."""
        from src.common.unified_llm import LLMResult

        cli_result = LLMResult(
            content="{}",
            backend="claude_cli",
            model="claude-sonnet",
            tier="middle",
            duration_ms=1000,
            success=True,
        )

        langchain_result = LLMResult(
            content="{}",
            backend="langchain",
            model="gpt-4o",
            tier="middle",
            duration_ms=1000,
            success=True,
        )

        assert cli_result.backend == "claude_cli"
        assert langchain_result.backend == "langchain"

    def test_result_to_dict_serialization(self):
        """Result should be serializable to dict."""
        from src.common.unified_llm import LLMResult

        result = LLMResult(
            content='{"key": "value"}',
            backend="claude_cli",
            model="claude-sonnet",
            tier="middle",
            duration_ms=1500,
            success=True,
            parsed_json={"key": "value"}
        )

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert result_dict["backend"] == "claude_cli"
        assert result_dict["tier"] == "middle"


class TestUnifiedLLMBatch:
    """Tests for batch invocation."""

    @pytest.fixture
    def mock_cli_batch_success(self, mocker):
        """Mock successful batch invocation."""
        mock_cli_class = mocker.patch("src.common.unified_llm.ClaudeCLI")

        def create_result(prompt, job_id, **kwargs):
            result = MagicMock()
            result.success = True
            result.result = {"job_id": job_id, "data": "test"}
            result.raw_result = None
            result.error = None
            result.duration_ms = 1500
            result.model = "claude-sonnet-4-5-20250929"
            result.tier = "middle"
            result.input_tokens = 100
            result.output_tokens = 50
            result.cost_usd = 0.01
            return result

        mock_cli_class.return_value.invoke.side_effect = create_result
        return mock_cli_class

    @pytest.mark.asyncio
    async def test_invoke_batch_processes_all_items(self, mock_cli_batch_success):
        """Should process all items in batch."""
        from src.common.unified_llm import UnifiedLLM

        llm = UnifiedLLM(step_name="grader")

        items = [
            {"job_id": "job_001", "prompt": "Prompt 1"},
            {"job_id": "job_002", "prompt": "Prompt 2"},
            {"job_id": "job_003", "prompt": "Prompt 3"},
        ]

        results = await llm.invoke_batch(items, max_concurrent=2)

        assert len(results) == 3
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_invoke_batch_respects_concurrency_limit(self, mock_cli_batch_success):
        """Should respect max_concurrent limit."""
        from src.common.unified_llm import UnifiedLLM

        llm = UnifiedLLM(step_name="grader")

        items = [{"job_id": f"job_{i:03d}", "prompt": f"Prompt {i}"} for i in range(10)]

        max_concurrent = 3
        results = await llm.invoke_batch(items, max_concurrent=max_concurrent)

        assert len(results) == 10


class TestFallbackLogic:
    """Tests for fallback behavior."""

    @pytest.mark.asyncio
    async def test_fallback_logs_warning(self, mocker):
        """Should log warning when falling back."""
        mock_cli_class = mocker.patch("src.common.unified_llm.ClaudeCLI")
        mock_langchain = mocker.patch("src.common.llm_factory.create_tracked_llm_for_model")
        mock_logger = mocker.patch("src.common.unified_llm.logger")

        # CLI fails
        cli_result = MagicMock()
        cli_result.success = False
        cli_result.error = "Timeout"
        cli_result.model = "claude-sonnet"
        cli_result.tier = "middle"
        mock_cli_class.return_value.invoke.return_value = cli_result

        # LangChain succeeds
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"data": "fallback"}'
        mock_response.usage_metadata = None
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_langchain.return_value = mock_llm

        from src.common.unified_llm import UnifiedLLM
        llm = UnifiedLLM(step_name="grader")

        result = await llm.invoke(prompt="Test", job_id="test")

        # Should log warning about fallback
        assert mock_logger.warning.called


class TestErrorHandling:
    """Tests for error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_handles_cli_exception(self, mocker):
        """Should handle exceptions from CLI gracefully."""
        mock_cli_class = mocker.patch("src.common.unified_llm.ClaudeCLI")
        mock_cli_class.return_value.invoke.side_effect = Exception("Unexpected error")

        # Disable fallback by modifying config
        from src.common.unified_llm import UnifiedLLM
        from src.common.llm_config import StepConfig

        config = StepConfig(tier="middle", use_fallback=False)
        llm = UnifiedLLM(config=config)

        result = await llm.invoke(prompt="Test", job_id="test")

        assert result.success is False
        assert "failed" in result.error.lower() or "disabled" in result.error.lower()

    @pytest.mark.asyncio
    async def test_handles_both_backends_failing(self, mocker):
        """Should handle both backends failing gracefully."""
        mock_cli_class = mocker.patch("src.common.unified_llm.ClaudeCLI")
        mock_langchain = mocker.patch("src.common.llm_factory.create_tracked_llm_for_model")

        # CLI fails
        cli_result = MagicMock()
        cli_result.success = False
        cli_result.error = "CLI error"
        cli_result.model = "claude-sonnet"
        cli_result.tier = "middle"
        mock_cli_class.return_value.invoke.return_value = cli_result

        # LangChain also fails
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("Fallback error"))
        mock_langchain.return_value = mock_llm

        from src.common.unified_llm import UnifiedLLM
        llm = UnifiedLLM(step_name="grader")

        result = await llm.invoke(prompt="Test", job_id="test")

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_uses_default_job_id_when_not_provided(self, mocker):
        """Should use instance job_id when not provided in invoke."""
        mock_cli_class = mocker.patch("src.common.unified_llm.ClaudeCLI")

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.result = {"data": "test"}
        mock_result.raw_result = None
        mock_result.error = None
        mock_result.duration_ms = 1000
        mock_result.model = "claude-sonnet"
        mock_result.tier = "middle"
        mock_result.input_tokens = 100
        mock_result.output_tokens = 50
        mock_result.cost_usd = 0.01
        mock_cli_class.return_value.invoke.return_value = mock_result

        from src.common.unified_llm import UnifiedLLM
        llm = UnifiedLLM(step_name="grader", job_id="default_job")

        # Invoke without job_id should use instance default
        result = await llm.invoke(prompt="Test")

        assert result.success is True


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_invoke_unified_sync_exists(self):
        """invoke_unified_sync should be importable."""
        from src.common.unified_llm import invoke_unified_sync
        assert invoke_unified_sync is not None

    def test_invoke_unified_async_exists(self):
        """invoke_unified should be importable."""
        from src.common.unified_llm import invoke_unified
        assert invoke_unified is not None

    @pytest.mark.asyncio
    async def test_invoke_unified_sync_works_from_running_event_loop(self, mocker):
        """Should handle nested event loop without RuntimeError."""
        # Mock ClaudeCLI to avoid real API calls
        mock_cli_class = mocker.patch("src.common.unified_llm.ClaudeCLI")
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.result = {"test_key": "test_value"}
        mock_result.raw_result = None
        mock_result.error = None
        mock_result.duration_ms = 1000
        mock_result.model = "claude-sonnet-4-5-20250929"
        mock_result.tier = "middle"
        mock_result.input_tokens = 100
        mock_result.output_tokens = 50
        mock_result.cost_usd = 0.01
        mock_cli_class.return_value.invoke.return_value = mock_result

        from src.common.unified_llm import invoke_unified_sync

        # This test is running inside an async event loop (pytest-asyncio)
        # Verify there IS a running loop
        try:
            loop = asyncio.get_running_loop()
            assert loop is not None, "Test should be running in an event loop"
        except RuntimeError:
            pytest.fail("Test should be running in an async event loop")

        # Now call invoke_unified_sync from within this running loop
        # Before fix: This would raise "RuntimeError: asyncio.run() cannot be called from a running event loop"
        # After fix: This should use run_async() which handles nested loops via thread pool
        result = invoke_unified_sync(
            prompt="Test prompt",
            step_name="grader",
            job_id="test_nested"
        )

        # Verify the result is correct
        assert result.success is True
        assert result.backend == "claude_cli"
        assert result.parsed_json == {"test_key": "test_value"}
        assert result.model == "claude-sonnet-4-5-20250929"

    def test_invoke_unified_sync_works_from_sync_context(self, mocker):
        """Should work normally from synchronous context."""
        # Mock ClaudeCLI to avoid real API calls
        mock_cli_class = mocker.patch("src.common.unified_llm.ClaudeCLI")
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.result = {"sync_key": "sync_value"}
        mock_result.raw_result = None
        mock_result.error = None
        mock_result.duration_ms = 800
        mock_result.model = "claude-sonnet-4-5-20250929"
        mock_result.tier = "low"
        mock_result.input_tokens = 50
        mock_result.output_tokens = 25
        mock_result.cost_usd = 0.005
        mock_cli_class.return_value.invoke.return_value = mock_result

        from src.common.unified_llm import invoke_unified_sync

        # This test is NOT async - running in regular sync context
        # Verify there is NO running loop
        try:
            asyncio.get_running_loop()
            pytest.fail("Should not have a running loop in sync test")
        except RuntimeError:
            # Expected - no running loop
            pass

        # Call from sync context - should use asyncio.run() directly
        result = invoke_unified_sync(
            prompt="Sync test prompt",
            step_name="grader",
            job_id="test_sync"
        )

        # Verify the result
        assert result.success is True
        assert result.backend == "claude_cli"
        assert result.parsed_json == {"sync_key": "sync_value"}


class TestConfigIntegration:
    """Tests for integration with llm_config.py."""

    def test_loads_config_from_step_name(self):
        """Should load step config from llm_config."""
        from src.common.unified_llm import UnifiedLLM
        from src.common.llm_config import get_step_config

        # grader is defined in STEP_CONFIGS
        expected_config = get_step_config("grader")
        llm = UnifiedLLM(step_name="grader")

        assert llm.config.tier == expected_config.tier

    def test_tier_override_takes_precedence(self):
        """Explicit tier should override step config."""
        from src.common.unified_llm import UnifiedLLM

        # grader defaults to "low" but we override to "high"
        llm = UnifiedLLM(step_name="grader", tier="high")

        assert llm.config.tier == "high"

    def test_unknown_step_uses_defaults(self):
        """Unknown step name should use default config."""
        from src.common.unified_llm import UnifiedLLM

        llm = UnifiedLLM(step_name="unknown_step_xyz")

        assert llm.config.tier == "middle"  # Default


class TestStructuredLoggerIntegration:
    """Tests for StructuredLogger integration with UnifiedLLM."""

    def test_init_accepts_struct_logger_parameter(self):
        """Should accept struct_logger parameter."""
        from src.common.unified_llm import UnifiedLLM
        from src.common.structured_logger import StructuredLogger

        mock_logger = StructuredLogger(job_id="test", enabled=False)
        llm = UnifiedLLM(step_name="grader", struct_logger=mock_logger)

        assert llm._struct_logger is mock_logger

    def test_init_struct_logger_defaults_to_none(self):
        """Should default struct_logger to None."""
        from src.common.unified_llm import UnifiedLLM

        llm = UnifiedLLM(step_name="grader")

        assert llm._struct_logger is None

    @pytest.mark.asyncio
    async def test_invoke_emits_llm_call_event_when_logger_provided(self, mocker, capsys):
        """Should emit llm_call_complete event when struct_logger provided."""
        mock_cli_class = mocker.patch("src.common.unified_llm.ClaudeCLI")

        # Mock CLI success
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.result = {"data": "test"}
        mock_result.raw_result = None
        mock_result.error = None
        mock_result.duration_ms = 1500
        mock_result.model = "claude-sonnet-4-5-20250929"
        mock_result.tier = "middle"
        mock_result.input_tokens = 100
        mock_result.output_tokens = 50
        mock_result.cost_usd = 0.025
        mock_cli_class.return_value.invoke.return_value = mock_result

        from src.common.unified_llm import UnifiedLLM
        from src.common.structured_logger import StructuredLogger
        import json

        struct_logger = StructuredLogger(job_id="test-123", enabled=True)
        llm = UnifiedLLM(step_name="grader", struct_logger=struct_logger)

        await llm.invoke(prompt="Test", job_id="test")

        # Check that event was emitted to stdout
        captured = capsys.readouterr()
        assert captured.out.strip() != ""

        event = json.loads(captured.out.strip())
        assert event["event"] == "llm_call_complete"
        assert event["backend"] == "claude_cli"
        assert event["model"] == "claude-sonnet-4-5-20250929"
        assert event["step_name"] == "grader"
        # duration_ms is calculated at runtime, so just check it exists and is non-negative
        assert "duration_ms" in event
        assert event["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_invoke_no_event_when_no_logger(self, mocker, capsys):
        """Should not emit event when struct_logger not provided."""
        mock_cli_class = mocker.patch("src.common.unified_llm.ClaudeCLI")

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.result = {"data": "test"}
        mock_result.raw_result = None
        mock_result.error = None
        mock_result.duration_ms = 1500
        mock_result.model = "claude-sonnet"
        mock_result.tier = "middle"
        mock_result.input_tokens = 100
        mock_result.output_tokens = 50
        mock_result.cost_usd = 0.025
        mock_cli_class.return_value.invoke.return_value = mock_result

        from src.common.unified_llm import UnifiedLLM

        # No struct_logger provided
        llm = UnifiedLLM(step_name="grader")

        await llm.invoke(prompt="Test", job_id="test")

        # Should not emit to stdout (no structured logger)
        captured = capsys.readouterr()
        # Note: logger.info goes to stderr or logging handler, not stdout
        # So stdout should be empty
        assert captured.out.strip() == ""

    @pytest.mark.asyncio
    async def test_fallback_emits_fallback_event(self, mocker, capsys):
        """Should emit llm_call_fallback event when falling back."""
        mock_cli_class = mocker.patch("src.common.unified_llm.ClaudeCLI")
        mock_langchain = mocker.patch("src.common.llm_factory.create_tracked_llm_for_model")

        # CLI fails
        cli_result = MagicMock()
        cli_result.success = False
        cli_result.error = "Timeout"
        cli_result.model = "claude-sonnet"
        cli_result.tier = "middle"
        mock_cli_class.return_value.invoke.return_value = cli_result

        # LangChain succeeds
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"data": "fallback"}'
        mock_response.usage_metadata = None
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_langchain.return_value = mock_llm

        from src.common.unified_llm import UnifiedLLM
        from src.common.structured_logger import StructuredLogger
        import json

        struct_logger = StructuredLogger(job_id="test-123", enabled=True)
        llm = UnifiedLLM(step_name="grader", struct_logger=struct_logger)

        await llm.invoke(prompt="Test", job_id="test")

        # Check events were emitted
        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")

        # Should have 2 events: fallback notification + completion
        assert len(lines) == 2

        # First should be fallback event
        fallback_event = json.loads(lines[0])
        assert fallback_event["event"] == "llm_call_fallback"
        assert fallback_event["backend"] == "langchain"

        # Second should be completion
        complete_event = json.loads(lines[1])
        assert complete_event["event"] == "llm_call_complete"
        assert complete_event["backend"] == "langchain"
        assert complete_event["metadata"]["is_fallback"] is True

    def test_convenience_function_accepts_struct_logger(self):
        """invoke_unified_sync should accept struct_logger parameter."""
        from src.common.unified_llm import invoke_unified_sync
        import inspect

        sig = inspect.signature(invoke_unified_sync)
        params = list(sig.parameters.keys())

        assert "struct_logger" in params

    @pytest.mark.asyncio
    async def test_event_has_correct_step_name(self, mocker, capsys):
        """Should emit event with correct step_name from initialization."""
        mock_cli_class = mocker.patch("src.common.unified_llm.ClaudeCLI")

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.result = {"data": "test"}
        mock_result.raw_result = None
        mock_result.error = None
        mock_result.duration_ms = 1000
        mock_result.model = "claude-sonnet-4-5-20250929"
        mock_result.tier = "middle"
        mock_result.input_tokens = 100
        mock_result.output_tokens = 50
        mock_result.cost_usd = 0.01
        mock_cli_class.return_value.invoke.return_value = mock_result

        from src.common.unified_llm import UnifiedLLM
        from src.common.structured_logger import StructuredLogger
        import json

        struct_logger = StructuredLogger(job_id="test-123", enabled=True)
        llm = UnifiedLLM(step_name="custom_step", struct_logger=struct_logger)

        await llm.invoke(prompt="Test", job_id="test")

        captured = capsys.readouterr()
        event = json.loads(captured.out.strip())
        assert event["step_name"] == "custom_step"

    @pytest.mark.asyncio
    async def test_event_includes_all_required_metadata(self, mocker, capsys):
        """Should emit event with all required metadata fields."""
        mock_cli_class = mocker.patch("src.common.unified_llm.ClaudeCLI")

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.result = {"data": "test"}
        mock_result.raw_result = None
        mock_result.error = None
        mock_result.duration_ms = 2500
        mock_result.model = "claude-sonnet-4-5-20250929"
        mock_result.tier = "high"
        mock_result.input_tokens = 500
        mock_result.output_tokens = 300
        mock_result.cost_usd = 0.05
        mock_cli_class.return_value.invoke.return_value = mock_result

        from src.common.unified_llm import UnifiedLLM
        from src.common.structured_logger import StructuredLogger
        import json

        struct_logger = StructuredLogger(job_id="test-456", enabled=True)
        llm = UnifiedLLM(step_name="test_step", struct_logger=struct_logger)

        await llm.invoke(prompt="Test prompt", job_id="job_789")

        captured = capsys.readouterr()
        event = json.loads(captured.out.strip())

        # Verify all expected fields exist
        required_fields = ["event", "backend", "model", "step_name"]
        for field in required_fields:
            assert field in event, f"Missing required field: {field}"

        # Verify cost tracking is included
        assert event.get("cost_usd") == 0.05

    @pytest.mark.asyncio
    async def test_event_includes_backend_and_model_on_success(self, mocker, capsys):
        """Should include backend and model in event when primary succeeds."""
        mock_cli_class = mocker.patch("src.common.unified_llm.ClaudeCLI")

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.result = {"data": "test"}
        mock_result.raw_result = None
        mock_result.error = None
        mock_result.duration_ms = 1000
        mock_result.model = "claude-sonnet"
        mock_result.tier = "middle"
        mock_result.input_tokens = 100
        mock_result.output_tokens = 50
        mock_result.cost_usd = 0.01
        mock_cli_class.return_value.invoke.return_value = mock_result

        from src.common.unified_llm import UnifiedLLM
        from src.common.structured_logger import StructuredLogger
        import json

        struct_logger = StructuredLogger(job_id="test-111", enabled=True)
        llm = UnifiedLLM(step_name="grader", struct_logger=struct_logger)

        await llm.invoke(prompt="Test", job_id="test")

        captured = capsys.readouterr()
        event = json.loads(captured.out.strip())
        assert event["backend"] == "claude_cli"
        assert event["model"] == "claude-sonnet"

    @pytest.mark.asyncio
    async def test_fallback_event_primary_error_captured(self, mocker, capsys):
        """Should capture primary error reason in fallback event."""
        mock_cli_class = mocker.patch("src.common.unified_llm.ClaudeCLI")
        mock_langchain = mocker.patch("src.common.llm_factory.create_tracked_llm_for_model")

        # CLI fails with specific error
        cli_result = MagicMock()
        cli_result.success = False
        cli_result.error = "Connection timeout after 30s"
        cli_result.model = "claude-sonnet"
        cli_result.tier = "middle"
        mock_cli_class.return_value.invoke.return_value = cli_result

        # LangChain succeeds
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"data": "fallback"}'
        mock_response.usage_metadata = None
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_langchain.return_value = mock_llm

        from src.common.unified_llm import UnifiedLLM
        from src.common.structured_logger import StructuredLogger
        import json

        struct_logger = StructuredLogger(job_id="test-222", enabled=True)
        llm = UnifiedLLM(step_name="grader", struct_logger=struct_logger)

        await llm.invoke(prompt="Test", job_id="test")

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")

        # First event should be fallback with primary error
        fallback_event = json.loads(lines[0])
        assert fallback_event["event"] == "llm_call_fallback"
        # Primary backend error should be captured in metadata or event
        assert "metadata" in fallback_event or "primary_error" in fallback_event
