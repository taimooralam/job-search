"""
Codex CLI subprocess wrapper — production transport for preenrich stages.

PRODUCTION STATUS (Phase 2b onwards):
This module is the primary LLM transport for preenrich stages that use Codex:
jd_extraction, ai_classification, pain_points, persona.  Claude remains the
automatic fallback when CodexResult.success=False or schema validation fails.
See src/preenrich/stages/base._call_llm_with_fallback() for the fallback contract.

IMPORTANT — CodexResult.success=False contract:
    CodexCLI.invoke() does NOT raise on subprocess non-zero exit codes or JSON
    parse failures.  It always returns a CodexResult.  Check result.success before
    using result.result.  Only CodexCLIError is raised for hard programming errors
    (not subprocess failures).

    Failure cases that set success=False:
      - Non-zero subprocess exit code (proc.returncode != 0)
      - validate_json=True and no JSON found in stdout
      - validate_json=True and JSON parse error
      - subprocess.TimeoutExpired (timeout exceeded)
      - FileNotFoundError (codex binary not installed)

Mirrors the interface of src/common/claude_cli.py: subprocess invocation,
JSON extraction from stdout, CodexCLIError exception class, configurable timeout.

Usage:
    cli = CodexCLI(model="gpt-5.4")
    result = cli.invoke(prompt, job_id="123")
    if result.success:
        data = result.result  # parsed dict
    else:
        # fallback to Claude — see _call_llm_with_fallback()
        ...
"""

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime
from queue import Empty, Queue
import threading
import time
from typing import Any, Dict, Optional

from src.common.json_utils import parse_llm_json

logger = logging.getLogger(__name__)

# Default Codex model for shadow runs
DEFAULT_CODEX_MODEL = "gpt-5.4"

def _optional_timeout_seconds(*env_names: str) -> int | None:
    for name in env_names:
        raw = os.getenv(name)
        if raw is None:
            continue
        raw = raw.strip()
        if not raw:
            return None
        try:
            value = int(raw)
        except Exception:
            continue
        if value <= 0:
            return None
        return value
    return None


# Timeout for codex exec subprocess (seconds). None means no timeout.
DEFAULT_TIMEOUT_SECONDS = _optional_timeout_seconds(
    "PREENRICH_CODEX_TIMEOUT_SECONDS",
    "CODEX_TIMEOUT_SECONDS",
)
DEFAULT_HEARTBEAT_SECONDS = int(
    os.getenv("PREENRICH_CODEX_HEARTBEAT_SECONDS")
    or os.getenv("CODEX_HEARTBEAT_SECONDS")
    or "20"
)


class CodexCLIError(Exception):
    """
    Raised when the codex exec subprocess returns a non-zero exit code,
    times out, or produces output that cannot be parsed as JSON.
    """

    def __init__(self, message: str, returncode: Optional[int] = None) -> None:
        super().__init__(message)
        self.returncode = returncode


@dataclass
class CodexResult:
    """
    Result of a Codex CLI invocation.

    Mirrors CLIResult from src/common/claude_cli.py for interface parity.
    """

    job_id: str
    success: bool
    result: Optional[Dict[str, Any]]
    raw_result: Optional[str]
    error: Optional[str]
    model: str
    duration_ms: int
    invoked_at: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_usd: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class MonitoredProcessResult:
    returncode: int
    stdout: str
    stderr: str
    pid: int | None
    timed_out: bool = False


def _extract_json_from_stdout(stdout: str) -> Optional[str]:
    """
    Extract the first JSON object or array from stdout.

    Codex exec may prefix JSON with reasoning text; this finds the first
    balanced JSON structure.

    Args:
        stdout: Raw stdout string from codex exec

    Returns:
        JSON substring if found, None otherwise
    """
    if not stdout:
        return None

    stdout = stdout.strip()

    # Try direct parse first
    if stdout.startswith("{") or stdout.startswith("["):
        return stdout

    # Look for JSON object or array embedded in text
    match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", stdout)
    if match:
        return match.group(1)

    return None


def _stream_reader(
    stream: Any,
    stream_name: str,
    queue: Queue[tuple[str, bytes | None]],
) -> None:
    try:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                break
            queue.put((stream_name, chunk))
    finally:
        queue.put((stream_name, None))


def _run_monitored_codex_subprocess(
    *,
    cmd: list[str],
    timeout: int | None,
    job_id: str,
    logger: logging.Logger,
) -> MonitoredProcessResult:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        cwd=None,
        text=False,
        bufsize=0,
    )
    pid = proc.pid
    logger.info(
        "Codex subprocess spawned: job=%s pid=%s timeout_s=%s",
        job_id,
        pid,
        "none" if timeout is None else timeout,
    )
    assert proc.stdout is not None
    assert proc.stderr is not None

    queue: Queue[tuple[str, bytes | None]] = Queue()
    stdout_chunks = bytearray()
    stderr_chunks = bytearray()
    stream_state = {"stdout": False, "stderr": False}
    partial_lines = {"stdout": "", "stderr": ""}
    last_output_monotonic = time.monotonic()
    start_monotonic = last_output_monotonic
    last_heartbeat = start_monotonic

    threads = [
        threading.Thread(target=_stream_reader, args=(proc.stdout, "stdout", queue), daemon=True),
        threading.Thread(target=_stream_reader, args=(proc.stderr, "stderr", queue), daemon=True),
    ]
    for thread in threads:
        thread.start()

    try:
        while True:
            now = time.monotonic()
            if timeout is not None and now - start_monotonic > timeout:
                proc.kill()
                logger.warning(
                    "Codex subprocess timeout: job=%s pid=%s elapsed_s=%d stdout_bytes=%d stderr_bytes=%d",
                    job_id,
                    pid,
                    int(now - start_monotonic),
                    len(stdout_chunks),
                    len(stderr_chunks),
                )
                return MonitoredProcessResult(
                    returncode=-9,
                    stdout=stdout_chunks.decode("utf-8", errors="replace"),
                    stderr=stderr_chunks.decode("utf-8", errors="replace"),
                    pid=pid,
                    timed_out=True,
                )

            try:
                stream_name, chunk = queue.get(timeout=1.0)
                if chunk is None:
                    stream_state[stream_name] = True
                else:
                    last_output_monotonic = time.monotonic()
                    if stream_name == "stdout":
                        stdout_chunks.extend(chunk)
                    else:
                        stderr_chunks.extend(chunk)
                    text = chunk.decode("utf-8", errors="replace")
                    partial_lines[stream_name] += text
                    while "\n" in partial_lines[stream_name]:
                        line, remainder = partial_lines[stream_name].split("\n", 1)
                        partial_lines[stream_name] = remainder
                        line = line.rstrip()
                        if line:
                            log_fn = logger.debug if stream_name == "stdout" else logger.warning
                            log_fn("Codex %s: job=%s pid=%s %s", stream_name, job_id, pid, line)
            except Empty:
                pass

            now = time.monotonic()
            if now - last_heartbeat >= DEFAULT_HEARTBEAT_SECONDS:
                logger.info(
                    "Codex subprocess heartbeat: job=%s pid=%s alive=%s elapsed_s=%d stdout_bytes=%d stderr_bytes=%d last_output_age_s=%.1f",
                    job_id,
                    pid,
                    proc.poll() is None,
                    int(now - start_monotonic),
                    len(stdout_chunks),
                    len(stderr_chunks),
                    max(0.0, now - last_output_monotonic),
                )
                last_heartbeat = now

            if proc.poll() is not None and all(stream_state.values()) and queue.empty():
                break
    finally:
        for thread in threads:
            thread.join(timeout=0.1)
        try:
            proc.stdout.close()
        except Exception:
            pass
        try:
            proc.stderr.close()
        except Exception:
            pass

    for stream_name, remainder in partial_lines.items():
        remainder = remainder.strip()
        if remainder:
            log_fn = logger.debug if stream_name == "stdout" else logger.warning
            log_fn("Codex %s: job=%s pid=%s %s", stream_name, job_id, pid, remainder)

    return MonitoredProcessResult(
        returncode=proc.returncode or 0,
        stdout=stdout_chunks.decode("utf-8", errors="replace"),
        stderr=stderr_chunks.decode("utf-8", errors="replace"),
        pid=pid,
        timed_out=False,
    )


class CodexCLI:
    """
    Subprocess wrapper for `codex exec --model <model> --skip-git-repo-check "<prompt>"`.

    Shadow-only in Phase 0/1. Used for evaluation and parity testing against
    Claude outputs. Not wired into UnifiedLLM until Phase 6 per-stage cutover.
    """

    def __init__(
        self,
        model: str = DEFAULT_CODEX_MODEL,
        timeout: int | None = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """
        Initialize the Codex CLI wrapper.

        Args:
            model: Codex model identifier (e.g. "gpt-5.4", "gpt-5.4-mini")
            timeout: Subprocess timeout in seconds
        """
        self.model = model
        self.timeout = timeout

    def invoke(
        self,
        prompt: str,
        job_id: str,
        validate_json: bool = True,
    ) -> CodexResult:
        """
        Execute `codex exec` with the given prompt and return parsed result.

        Runs:
            codex exec --model <model> --skip-git-repo-check "<prompt>"

        Args:
            prompt: Full prompt text
            job_id: Tracking ID for this invocation
            validate_json: Whether to parse result as JSON (default True)

        Returns:
            CodexResult with success/failure status and parsed data

        Raises:
            CodexCLIError: On subprocess failure or JSON parse error when
                           validate_json=True and output is not valid JSON.
        """
        start_time = datetime.utcnow()
        logger.info(
            "Codex shadow invoke: model=%s, job_id=%s, prompt_len=%d",
            self.model, job_id, len(prompt),
        )

        try:
            cmd = [
                "codex",
                "exec",
                "--model", self.model,
                "--skip-git-repo-check",
                prompt,
            ]

            proc = _run_monitored_codex_subprocess(
                cmd=cmd,
                timeout=self.timeout,
                job_id=job_id,
                logger=logger,
            )

            duration_ms = int(
                (datetime.utcnow() - start_time).total_seconds() * 1000
            )

            if proc.returncode != 0:
                error_msg = (
                    f"codex exec timeout after {self.timeout}s"
                    if proc.timed_out
                    else (proc.stderr.strip() or proc.stdout.strip()
                          or f"codex exec exited with code {proc.returncode}")
                )
                logger.warning(
                    "Codex exec failed for job %s: %s", job_id, error_msg
                )
                return CodexResult(
                    job_id=job_id,
                    success=False,
                    result=None,
                    raw_result=proc.stdout or None,
                    error=error_msg,
                    model=self.model,
                    duration_ms=duration_ms,
                    invoked_at=start_time.isoformat(),
                )

            raw_output = proc.stdout

            if not validate_json:
                return CodexResult(
                    job_id=job_id,
                    success=True,
                    result=None,
                    raw_result=raw_output,
                    error=None,
                    model=self.model,
                    duration_ms=duration_ms,
                    invoked_at=start_time.isoformat(),
                )

            json_str = _extract_json_from_stdout(raw_output)
            if not json_str:
                error_msg = "No JSON found in codex exec output"
                logger.warning("Codex JSON parse failed for job %s: %s", job_id, error_msg)
                return CodexResult(
                    job_id=job_id,
                    success=False,
                    result=None,
                    raw_result=raw_output,
                    error=error_msg,
                    model=self.model,
                    duration_ms=duration_ms,
                    invoked_at=start_time.isoformat(),
                )

            try:
                parsed = parse_llm_json(json_str)
            except (ValueError, json.JSONDecodeError) as exc:
                error_msg = f"JSON parse error: {exc}"
                logger.warning(
                    "Codex JSON parse failed for job %s: %s", job_id, error_msg
                )
                return CodexResult(
                    job_id=job_id,
                    success=False,
                    result=None,
                    raw_result=raw_output,
                    error=error_msg,
                    model=self.model,
                    duration_ms=duration_ms,
                    invoked_at=start_time.isoformat(),
                )

            logger.info(
                "Codex shadow complete: job=%s model=%s duration=%dms",
                job_id, self.model, duration_ms,
            )

            return CodexResult(
                job_id=job_id,
                success=True,
                result=parsed,
                raw_result=None,
                error=None,
                model=self.model,
                duration_ms=duration_ms,
                invoked_at=start_time.isoformat(),
            )

        except FileNotFoundError:
            duration_ms = int(
                (datetime.utcnow() - start_time).total_seconds() * 1000
            )
            error_msg = "codex binary not found — Codex CLI not installed"
            logger.warning("Codex not available for job %s: %s", job_id, error_msg)
            return CodexResult(
                job_id=job_id,
                success=False,
                result=None,
                raw_result=None,
                error=error_msg,
                model=self.model,
                duration_ms=duration_ms,
                invoked_at=start_time.isoformat(),
            )

        except Exception as exc:
            duration_ms = int(
                (datetime.utcnow() - start_time).total_seconds() * 1000
            )
            error_msg = f"Unexpected error: {exc}"
            logger.error("Codex unexpected error for job %s: %s", job_id, error_msg)
            return CodexResult(
                job_id=job_id,
                success=False,
                result=None,
                raw_result=None,
                error=error_msg,
                model=self.model,
                duration_ms=duration_ms,
                invoked_at=start_time.isoformat(),
            )

    def check_available(self) -> bool:
        """
        Check if codex CLI is installed and accessible.

        Returns:
            True if `codex --version` succeeds, False otherwise.
        """
        try:
            result = subprocess.run(
                ["codex", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
