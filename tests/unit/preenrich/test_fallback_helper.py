"""
Tests for _call_llm_with_fallback() helper (Phase 2b).

Covers:
- Happy path: Codex succeeds → single attempt, provider_used="codex"
- Subprocess fail → fallback triggered → provider_used="claude"
- Schema fail → fallback triggered → provider_fallback_reason="error_schema"
- Both fail → RuntimeError raised
- Fallback call is made with correct model/job_id args
"""

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel


# ── Schema for testing validation path ────────────────────────────────────────


class _TestSchema(BaseModel):
    value: str
    count: int


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_codex_result(
    success: bool,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    model: str = "gpt-5.4",
) -> Any:
    """Build a mock CodexResult."""
    from dataclasses import dataclass

    @dataclass
    class _FakeCodexResult:
        success: bool
        result: Optional[Dict[str, Any]]
        error: Optional[str]
        model: str
        input_tokens: Optional[int] = None
        output_tokens: Optional[int] = None

    return _FakeCodexResult(success=success, result=result, error=error, model=model)


def _make_claude_invoker(
    return_value: Dict[str, Any],
    should_raise: bool = False,
    exc: Optional[Exception] = None,
):
    """Build a mock claude_invoker callable."""
    def _invoker(*, prompt: str, model: str, job_id: str) -> Dict[str, Any]:
        if should_raise:
            raise exc or RuntimeError("Claude fallback failed")
        return return_value

    return _invoker


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestCallLlmWithFallbackHappyPath:
    @patch("src.preenrich.stages.base.CodexCLI")
    def test_codex_success_single_attempt(self, mock_codex_cls):
        """Codex succeeds → 1 attempt, provider_used reflects codex."""
        from src.preenrich.stages.base import _call_llm_with_fallback

        mock_cli = MagicMock()
        mock_cli.invoke.return_value = _make_codex_result(
            success=True, result={"value": "hello", "count": 3}
        )
        mock_codex_cls.return_value = mock_cli

        claude_invoker = _make_claude_invoker({"value": "fallback", "count": 0})

        output, attempts = _call_llm_with_fallback(
            primary_provider="codex",
            primary_model="gpt-5.4",
            fallback_provider="claude",
            fallback_model="claude-haiku-4-5",
            prompt="test prompt",
            job_id="test-job-1",
            schema=None,
            claude_invoker=claude_invoker,
        )

        assert len(attempts) == 1
        assert attempts[0]["provider"] == "codex"
        assert attempts[0]["outcome"] == "success"
        assert output == {"value": "hello", "count": 3}

    @patch("src.preenrich.stages.base.CodexCLI")
    def test_codex_success_with_schema_validation(self, mock_codex_cls):
        """Codex succeeds with valid schema → 1 attempt, output validated."""
        from src.preenrich.stages.base import _call_llm_with_fallback

        mock_cli = MagicMock()
        mock_cli.invoke.return_value = _make_codex_result(
            success=True, result={"value": "hello", "count": 3}
        )
        mock_codex_cls.return_value = mock_cli

        claude_invoker = _make_claude_invoker({"value": "fallback", "count": 0})

        output, attempts = _call_llm_with_fallback(
            primary_provider="codex",
            primary_model="gpt-5.4",
            fallback_provider="claude",
            fallback_model="claude-haiku-4-5",
            prompt="test prompt",
            job_id="test-job-schema",
            schema=_TestSchema,
            claude_invoker=claude_invoker,
        )

        assert len(attempts) == 1
        assert attempts[0]["outcome"] == "success"
        assert output["value"] == "hello"
        assert output["count"] == 3


class TestCallLlmWithFallbackSubprocessFail:
    @patch("src.preenrich.stages.base.CodexCLI")
    def test_codex_subprocess_fail_triggers_fallback(self, mock_codex_cls):
        """
        Codex success=False → fallback triggered → 2 attempts.
        First attempt outcome="error_subprocess", second outcome="success".
        """
        from src.preenrich.stages.base import _call_llm_with_fallback

        mock_cli = MagicMock()
        mock_cli.invoke.return_value = _make_codex_result(
            success=False, error="codex exec exited with code 1"
        )
        mock_codex_cls.return_value = mock_cli

        fallback_output = {"value": "from_claude", "count": 7}
        claude_invoker = _make_claude_invoker(fallback_output)

        output, attempts = _call_llm_with_fallback(
            primary_provider="codex",
            primary_model="gpt-5.4",
            fallback_provider="claude",
            fallback_model="claude-haiku-4-5",
            prompt="test prompt",
            job_id="test-job-fail",
            schema=None,
            claude_invoker=claude_invoker,
        )

        assert len(attempts) == 2
        assert attempts[0]["provider"] == "codex"
        assert attempts[0]["outcome"] == "error_subprocess"
        assert attempts[1]["provider"] == "claude"
        assert attempts[1]["outcome"] == "success"
        assert output == fallback_output

    @patch("src.preenrich.stages.base.CodexCLI")
    def test_codex_exception_triggers_fallback(self, mock_codex_cls):
        """Codex raises exception → fallback triggered → outcome='error_exception'."""
        from src.preenrich.stages.base import _call_llm_with_fallback

        mock_cli = MagicMock()
        mock_cli.invoke.side_effect = RuntimeError("subprocess crashed")
        mock_codex_cls.return_value = mock_cli

        fallback_output = {"value": "recovered", "count": 1}
        claude_invoker = _make_claude_invoker(fallback_output)

        output, attempts = _call_llm_with_fallback(
            primary_provider="codex",
            primary_model="gpt-5.4",
            fallback_provider="claude",
            fallback_model="claude-sonnet-4-5",
            prompt="test prompt",
            job_id="test-job-exc",
            schema=None,
            claude_invoker=claude_invoker,
        )

        assert len(attempts) == 2
        assert attempts[0]["outcome"] == "error_exception"
        assert attempts[1]["outcome"] == "success"
        assert output == fallback_output


class TestCallLlmWithFallbackSchemaFail:
    @patch("src.preenrich.stages.base.CodexCLI")
    def test_codex_schema_fail_triggers_fallback(self, mock_codex_cls):
        """
        Codex output fails Pydantic schema → fallback triggered →
        first attempt outcome="error_schema", second outcome="success".
        """
        from src.preenrich.stages.base import _call_llm_with_fallback

        # Codex returns data that fails _TestSchema (missing "count" field)
        mock_cli = MagicMock()
        mock_cli.invoke.return_value = _make_codex_result(
            success=True, result={"value": "ok"}  # missing "count" — schema fail
        )
        mock_codex_cls.return_value = mock_cli

        fallback_output = {"value": "fallback_valid", "count": 5}
        claude_invoker = _make_claude_invoker(fallback_output)

        output, attempts = _call_llm_with_fallback(
            primary_provider="codex",
            primary_model="gpt-5.4",
            fallback_provider="claude",
            fallback_model="claude-haiku-4-5",
            prompt="test prompt",
            job_id="test-job-schema-fail",
            schema=_TestSchema,
            claude_invoker=claude_invoker,
        )

        assert len(attempts) == 2
        assert attempts[0]["outcome"] == "error_schema"
        assert "Schema validation failed" in (attempts[0]["error"] or "")
        assert attempts[1]["outcome"] == "success"
        assert output["count"] == 5


class TestCallLlmWithFallbackBothFail:
    @patch("src.preenrich.stages.base.CodexCLI")
    def test_both_fail_raises_runtime_error(self, mock_codex_cls):
        """Both primary and fallback fail → RuntimeError raised."""
        from src.preenrich.stages.base import _call_llm_with_fallback

        mock_cli = MagicMock()
        mock_cli.invoke.return_value = _make_codex_result(
            success=False, error="codex down"
        )
        mock_codex_cls.return_value = mock_cli

        claude_invoker = _make_claude_invoker(
            {}, should_raise=True, exc=RuntimeError("Claude also down")
        )

        with pytest.raises(RuntimeError, match="Both primary.*and fallback.*failed"):
            _call_llm_with_fallback(
                primary_provider="codex",
                primary_model="gpt-5.4",
                fallback_provider="claude",
                fallback_model="claude-haiku-4-5",
                prompt="test prompt",
                job_id="test-job-both-fail",
                schema=None,
                claude_invoker=claude_invoker,
                )


class TestCallLlmWithFallbackDisabledFallback:
    @patch("src.preenrich.stages.base.CodexCLI")
    def test_primary_failure_raises_when_no_fallback_is_configured(self, mock_codex_cls):
        from src.preenrich.stages.base import _call_llm_with_fallback

        mock_cli = MagicMock()
        mock_cli.invoke.return_value = _make_codex_result(
            success=False, error="codex down"
        )
        mock_codex_cls.return_value = mock_cli

        with pytest.raises(RuntimeError, match="no fallback is configured"):
            _call_llm_with_fallback(
                primary_provider="codex",
                primary_model="gpt-5.4",
                fallback_provider="none",
                fallback_model=None,
                prompt="test prompt",
                job_id="test-job-no-fallback",
                schema=None,
                claude_invoker=_make_claude_invoker({"value": "unused", "count": 1}),
            )


class TestCallLlmWithFallbackFallbackArgs:
    @patch("src.preenrich.stages.base.CodexCLI")
    def test_fallback_called_with_correct_model_and_job_id(self, mock_codex_cls):
        """Verify the fallback invoker is called with the correct model and job_id."""
        from src.preenrich.stages.base import _call_llm_with_fallback

        mock_cli = MagicMock()
        mock_cli.invoke.return_value = _make_codex_result(
            success=False, error="failure"
        )
        mock_codex_cls.return_value = mock_cli

        call_log: List[Dict[str, Any]] = []

        def _capturing_invoker(*, prompt: str, model: str, job_id: str) -> Dict[str, Any]:
            call_log.append({"prompt": prompt, "model": model, "job_id": job_id})
            return {"result": "ok"}

        _call_llm_with_fallback(
            primary_provider="codex",
            primary_model="gpt-5.4-mini",
            fallback_provider="claude",
            fallback_model="claude-sonnet-4-5",
            prompt="my prompt",
            job_id="job-xyz",
            schema=None,
            claude_invoker=_capturing_invoker,
        )

        assert len(call_log) == 1
        assert call_log[0]["model"] == "claude-sonnet-4-5"
        assert call_log[0]["job_id"] == "job-xyz"
