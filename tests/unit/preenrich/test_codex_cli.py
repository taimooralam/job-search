"""
T15 — CodexCLI subprocess wrapper.

Validates:
- monitored Codex subprocess wrapper is called with correct codex exec command
- JSON is extracted from stdout
- Non-zero returncode maps to CodexCLIError-style failure (success=False)
- TimeoutExpired maps to timeout error
- FileNotFoundError maps to "codex not found" error
- validate_json=False skips JSON parsing
"""

import subprocess
import pytest
from unittest.mock import patch

from src.common.codex_cli import CodexCLI, CodexResult, MonitoredProcessResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_process_result(
    *,
    returncode: int = 0,
    stdout: str = '{"result": "ok"}',
    stderr: str = "",
    timed_out: bool = False,
) -> MonitoredProcessResult:
    return MonitoredProcessResult(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        pid=12345,
        timed_out=timed_out,
    )


def _make_completed_process(
    returncode: int = 0,
    stdout: str = '{"result": "ok"}',
    stderr: str = "",
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["codex", "--version"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


# ---------------------------------------------------------------------------
# subprocess mock — success
# ---------------------------------------------------------------------------


def test_codex_cli_success():
    """Successful codex exec returns CodexResult with success=True and parsed result."""
    cli = CodexCLI(model="gpt-5.4")

    with patch("src.common.codex_cli._run_monitored_codex_subprocess", return_value=_make_process_result(
        stdout='{"answer": 42}'
    )) as mock_run:
        result = cli.invoke("What is 6x7?", job_id="j1")

    assert result.success is True
    assert result.result == {"answer": 42}
    assert result.model == "gpt-5.4"
    assert result.job_id == "j1"

    mock_run.assert_called_once()
    cmd = mock_run.call_args.kwargs["cmd"]
    assert "codex" in cmd
    assert "--model" in cmd
    assert "gpt-5.4" in cmd
    assert "--skip-git-repo-check" in cmd


def test_codex_cli_json_extracted_from_prefix_text():
    """JSON is extracted even when preceded by reasoning text."""
    cli = CodexCLI(model="gpt-5.4")

    stdout = 'Let me think about this... {"key": "value"}'
    with patch("src.common.codex_cli._run_monitored_codex_subprocess", return_value=_make_process_result(stdout=stdout)):
        result = cli.invoke("prompt", job_id="j1")

    assert result.success is True
    assert result.result == {"key": "value"}


def test_codex_cli_validate_json_false():
    """validate_json=False skips JSON parsing and returns raw_result."""
    cli = CodexCLI()

    with patch("src.common.codex_cli._run_monitored_codex_subprocess", return_value=_make_process_result(
        stdout="not json output"
    )):
        result = cli.invoke("prompt", job_id="j1", validate_json=False)

    assert result.success is True
    assert result.result is None
    assert result.raw_result == "not json output"


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


def test_codex_cli_nonzero_returncode_returns_failure():
    """Non-zero exit code → success=False with error message."""
    cli = CodexCLI()

    with patch("src.common.codex_cli._run_monitored_codex_subprocess", return_value=_make_process_result(
        returncode=1,
        stderr="Authentication failed",
    )):
        result = cli.invoke("prompt", job_id="j1")

    assert result.success is False
    assert result.error is not None
    assert "Authentication failed" in result.error or "1" in result.error


def test_codex_cli_timeout_maps_to_error():
    """Timed-out monitored subprocess maps to success=False with timeout message."""
    cli = CodexCLI(timeout=1)

    with patch(
        "src.common.codex_cli._run_monitored_codex_subprocess",
        return_value=_make_process_result(returncode=-9, timed_out=True),
    ):
        result = cli.invoke("prompt", job_id="j1")

    assert result.success is False
    assert "timeout" in result.error.lower()


def test_codex_cli_not_found_maps_to_error():
    """FileNotFoundError (codex not installed) maps to success=False."""
    cli = CodexCLI()

    with patch("src.common.codex_cli._run_monitored_codex_subprocess", side_effect=FileNotFoundError("No such file")):
        result = cli.invoke("prompt", job_id="j1")

    assert result.success is False
    assert "not found" in result.error.lower() or "not installed" in result.error.lower()


def test_codex_cli_no_json_in_output():
    """Stdout with no JSON → success=False when validate_json=True."""
    cli = CodexCLI()

    with patch("src.common.codex_cli._run_monitored_codex_subprocess", return_value=_make_process_result(
        stdout="This is not JSON at all."
    )):
        result = cli.invoke("prompt", job_id="j1")

    assert result.success is False
    assert result.error is not None


# ---------------------------------------------------------------------------
# check_available
# ---------------------------------------------------------------------------


def test_check_available_true():
    """check_available returns True when codex --version succeeds."""
    cli = CodexCLI()

    with patch("subprocess.run", return_value=_make_completed_process(
        stdout="codex 1.0.0"
    )):
        assert cli.check_available() is True


def test_check_available_false_on_not_found():
    """check_available returns False when codex is not installed."""
    cli = CodexCLI()

    with patch("subprocess.run", side_effect=FileNotFoundError):
        assert cli.check_available() is False


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


def test_codex_result_has_required_fields():
    """CodexResult includes all required fields."""
    r = CodexResult(
        job_id="j1",
        success=True,
        result={"ok": True},
        raw_result=None,
        error=None,
        model="gpt-5.4",
        duration_ms=123,
        invoked_at="2026-01-01T00:00:00",
    )
    assert r.job_id == "j1"
    assert r.model == "gpt-5.4"
    assert r.duration_ms == 123


def test_codex_result_to_dict():
    """CodexResult.to_dict() returns a serializable dict."""
    r = CodexResult(
        job_id="j1",
        success=True,
        result={"ok": True},
        raw_result=None,
        error=None,
        model="gpt-5.4",
        duration_ms=123,
        invoked_at="2026-01-01T00:00:00",
    )
    d = r.to_dict()
    assert isinstance(d, dict)
    assert d["job_id"] == "j1"
    assert d["model"] == "gpt-5.4"
