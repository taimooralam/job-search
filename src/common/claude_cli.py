"""
Claude Code CLI Wrapper with Three-Tier Model Support

Provides a reusable wrapper for invoking Claude Code CLI in headless mode.
Supports three Claude model tiers for cost/quality tradeoffs:
- Low: Claude Haiku 4.5 (lowest cost, good for bulk)
- Middle: Claude Sonnet 4.5 (DEFAULT - best quality/cost ratio)
- High: Claude Opus 4.5 (highest quality)

Usage:
    # Single invocation with default tier (Sonnet)
    cli = ClaudeCLI()
    result = cli.invoke(prompt, job_id="123")

    # With specific tier
    cli = ClaudeCLI(tier="low")  # Haiku for bulk processing
    result = cli.invoke(prompt, job_id="123")

    # With high tier
    cli = ClaudeCLI(tier="high")  # Opus for critical extractions
    result = cli.invoke(prompt, job_id="123")

    # Batch invocation
    results = await cli.invoke_batch(prompts_with_ids, max_concurrent=3)
"""

import subprocess
import json
import logging
import asyncio
import os
import re
import sys
import uuid
from typing import Optional, Dict, Any, Callable, List, Literal, TYPE_CHECKING
from dataclasses import dataclass, asdict
from datetime import datetime

from src.common.json_utils import parse_llm_json

if TYPE_CHECKING:
    from src.common.structured_logger import StructuredLogger


logger = logging.getLogger(__name__)


# ===== CLAUDE MODEL TIERS =====

# Three-tier Claude model system
CLAUDE_MODEL_TIERS = {
    "low": "claude-haiku-4-5-20251001",       # Lowest cost, good for bulk
    "middle": "claude-sonnet-4-5-20250929",   # DEFAULT - best quality/cost
    "high": "claude-opus-4-5-20251101",       # Highest quality
}

# Legacy tier name aliases for backward compatibility
TIER_ALIASES = {
    "fast": "low",
    "balanced": "middle",
    "quality": "high",
}

# Default tier for batch operations
DEFAULT_BATCH_TIER = "middle"  # Sonnet 4.5 by default

# Approximate costs per 1K tokens (USD)
CLAUDE_TIER_COSTS = {
    "low": {"input": 0.00025, "output": 0.00125},      # Haiku
    "middle": {"input": 0.003, "output": 0.015},       # Sonnet
    "high": {"input": 0.015, "output": 0.075},         # Opus
}

# Type alias for tier
TierType = Literal["low", "middle", "high"]


@dataclass
class CLIResult:
    """
    Result of a Claude CLI invocation.

    Designed for consistent handling across all operations.
    Contains the parsed result plus metadata for cost tracking.
    """
    job_id: str
    success: bool
    result: Optional[Dict[str, Any]]  # Parsed JSON result
    raw_result: Optional[str]         # Raw result string from CLI
    error: Optional[str]
    model: str
    tier: str
    duration_ms: int
    invoked_at: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_usd: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


# Type alias for log callback (for Redis live-tail integration)
# Signature: (job_id, level, data) -> None
LogCallback = Callable[[str, str, Dict[str, Any]], None]


def _preview_text(text: str, n: int = 10) -> str:
    """
    Generate a preview of text showing first N and last N characters.

    Used for logging prompts and results without exposing full content.

    Args:
        text: Text to preview
        n: Number of characters to show at start and end

    Returns:
        Preview string like "First 10 c...last 10 ch" or full text if short
    """
    if not text:
        return ""
    if len(text) <= n * 2 + 3:
        return text
    return f"{text[:n]}...{text[-n:]}"


class ClaudeCLI:
    """
    Reusable Claude Code CLI wrapper with tier support.

    Provides a consistent interface for invoking Claude CLI across all
    pipeline operations. Supports three model tiers for cost/quality
    tradeoffs.

    Attributes:
        tier: Model tier ("low", "middle", "high")
        model: Actual Claude model ID
        timeout: Maximum seconds to wait for CLI response
        log_callback: Optional callback for log streaming
    """

    def __init__(
        self,
        tier: TierType = "middle",
        timeout: int = 300,
        log_callback: Optional[LogCallback] = None,
        model_override: Optional[str] = None,
    ):
        """
        Initialize the Claude CLI wrapper.

        Args:
            tier: Model tier - "low" (Haiku), "middle" (Sonnet), "high" (Opus)
            timeout: CLI timeout in seconds (default 300s / 5 minutes for complex operations)
            log_callback: Optional callback for log events (for Redis live-tail)
            model_override: Override model selection (for testing or special cases)
        """
        # Handle legacy tier names for backward compatibility
        if tier in TIER_ALIASES:
            tier = TIER_ALIASES[tier]  # type: ignore
        self.tier = tier
        self.model = model_override or self._get_model_for_tier(tier)
        self.timeout = timeout
        self._log_callback = log_callback or self._default_log

    def _get_model_for_tier(self, tier: TierType) -> str:
        """Get Claude model ID for the given tier."""
        # Allow env var override for testing
        env_override = os.getenv("CLAUDE_CODE_MODEL")
        if env_override:
            logger.debug(f"Using model from CLAUDE_CODE_MODEL env: {env_override}")
            return env_override

        return CLAUDE_MODEL_TIERS.get(tier, CLAUDE_MODEL_TIERS["middle"])

    def _default_log(self, job_id: str, level: str, data: Dict[str, Any]) -> None:
        """Default logging with verbose context for debugging CLI errors."""
        log_level = getattr(logging, level.upper(), logging.INFO)
        message = data.get("message", str(data))

        # Format verbose context for error debugging
        context_parts = []
        if "cli_error" in data:
            context_parts.append(f"error={data['cli_error']}")
        if "prompt_length" in data:
            context_parts.append(f"prompt_len={data['prompt_length']}")
        if "max_turns" in data:
            context_parts.append(f"max_turns={data['max_turns']}")

        context_str = f" [{', '.join(context_parts)}]" if context_parts else ""
        full_message = f"[ClaudeCLI:{job_id}] {message}{context_str}"

        # For errors, print directly to stderr to guarantee console visibility
        # (Python logger may be filtered or redirected elsewhere)
        if log_level >= logging.ERROR:
            print(f"[ERROR] {full_message}", file=sys.stderr)
            if "prompt_preview" in data:
                print(f"[ERROR] [ClaudeCLI:{job_id}] Prompt preview: {data['prompt_preview']}", file=sys.stderr)
        else:
            logger.log(log_level, full_message)

    def _emit_log(self, job_id: str, level: str, **kwargs) -> None:
        """
        Emit log event - hook for Redis live-tail.

        All log events go through this method, making it easy to
        swap in Redis publishing later.
        """
        self._log_callback(job_id, level, {
            "timestamp": datetime.utcnow().isoformat(),
            "invoker": "claude-code-cli",
            "model": self.model,
            "tier": self.tier,
            **kwargs
        })

    def _extract_cost_info(
        self, cli_output: Dict[str, Any]
    ) -> tuple[Optional[int], Optional[int], Optional[float]]:
        """
        Extract cost/usage information from CLI output.

        Supports both new format (v2.0.75+) and legacy format for backwards compatibility.

        New format (v2.0.75+):
            - usage.input_tokens, usage.output_tokens, etc.
            - total_cost_usd at top level

        Legacy format:
            - cost.input_tokens, cost.output_tokens, cost.total_cost_usd

        Returns:
            Tuple of (input_tokens, output_tokens, cost_usd)
        """
        # Try new format first (v2.0.75+)
        usage_info = cli_output.get("usage", {})
        if usage_info:
            input_tokens = usage_info.get("input_tokens")
            output_tokens = usage_info.get("output_tokens")
            # New format has top-level total_cost_usd
            cost_usd = cli_output.get("total_cost_usd")
            return input_tokens, output_tokens, cost_usd

        # Fall back to legacy format (cost field)
        cost_info = cli_output.get("cost", {})
        input_tokens = cost_info.get("input_tokens")
        output_tokens = cost_info.get("output_tokens")
        cost_usd = cost_info.get("total_cost_usd")
        return input_tokens, output_tokens, cost_usd

    # NOTE: _parse_cli_output method removed - we now use --output-format text
    # which returns the raw LLM response directly, avoiding the known bug (#8126)
    # where --output-format json sometimes returns empty result field.

    def _estimate_cost_from_chars(self, input_chars: int, output_chars: int) -> float:
        """
        Estimate cost based on character counts.

        Approximate conversion: ~4 characters per token (rough average).

        Args:
            input_chars: Number of input characters
            output_chars: Number of output characters

        Returns:
            Estimated cost in USD
        """
        # Rough approximation: 4 chars per token
        input_tokens = input_chars // 4
        output_tokens = output_chars // 4
        return self.get_tier_cost_estimate(self.tier, input_tokens, output_tokens)

    def _extract_cli_error(self, stdout: str, stderr: str, returncode: int) -> str:
        """
        Extract meaningful error message from CLI failure.

        With --output-format text, errors are typically in stderr.
        Falls back to stdout if stderr is empty.

        Args:
            stdout: CLI stdout (plain text with text format)
            stderr: CLI stderr (traditional error output)
            returncode: CLI exit code

        Returns:
            Human-readable error message
        """
        # Prefer stderr for error messages
        if stderr and stderr.strip():
            return stderr.strip()

        # Fall back to stdout
        if stdout and stdout.strip():
            return stdout.strip()

        # Generic fallback
        return f"CLI exited with code {returncode}"

    def _detect_cli_error_in_stdout(self, stdout: str) -> Optional[str]:
        """
        Detect CLI error messages in stdout that occur with returncode=0.

        With --output-format text, some CLI errors are written to stdout
        instead of stderr and don't set a non-zero return code. This method
        detects known error patterns before attempting JSON parsing.

        Known patterns:
        - "Error: Reached max turns (N)" - max turns limit hit
        - "Error: " prefix - general CLI errors

        Args:
            stdout: CLI stdout text

        Returns:
            Error message if detected, None otherwise
        """
        if not stdout:
            return None

        stdout_stripped = stdout.strip()

        # Pattern 1: "Error: Reached max turns (N)"
        if re.match(r'^Error: Reached max turns \(\d+\)$', stdout_stripped):
            return stdout_stripped

        # Pattern 2: General "Error: " prefix (but not inside JSON)
        # Only match if the entire output starts with "Error: "
        if stdout_stripped.startswith("Error: ") and not stdout_stripped.startswith("{"):
            return stdout_stripped

        return None

    def invoke(
        self,
        prompt: str,
        job_id: str,
        validate_json: bool = True,
        allow_tools: bool = False,
        system_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None,
        struct_logger: Optional['StructuredLogger'] = None,
    ) -> CLIResult:
        """
        Execute Claude CLI with prompt and return parsed result.

        Runs: claude -p {prompt} --output-format text --model {model}

        Args:
            prompt: Full prompt text (system + user combined)
            job_id: Tracking ID for this invocation
            validate_json: Whether to parse result as JSON (default True)
            allow_tools: Whether to enable CLI tools (WebSearch, WebFetch, Read).
                        Default False to prevent tool_use responses.
                        Set True for research tasks that need web search.
            system_prompt: Optional system prompt (for logging only, if provided separately)
            user_prompt: Optional user prompt (for logging only, if provided separately)
            struct_logger: Optional StructuredLogger for Redis live-tail integration

        Returns:
            CLIResult with success/failure status and parsed data
        """
        start_time = datetime.utcnow()
        self._emit_log(job_id, "info", message=f"Starting CLI invocation with {self.tier} tier ({self.model})")

        # Generate unique session ID for this invocation
        session_id = f"claude_{uuid.uuid4().hex[:8]}"

        # Extract system/user prompts for logging if not provided separately
        if system_prompt is None and user_prompt is None:
            # Try to split on common delimiter patterns
            if "\n\n---\n\n" in prompt:
                parts = prompt.split("\n\n---\n\n", 1)
                system_prompt, user_prompt = parts[0], parts[1]
            elif "\n\nUser Request:\n" in prompt:
                parts = prompt.split("\n\nUser Request:\n", 1)
                system_prompt, user_prompt = parts[0], parts[1]
            else:
                # Can't split - treat entire prompt as user prompt
                system_prompt = ""
                user_prompt = prompt

        # Emit structured log for Redis live-tail (start)
        if struct_logger:
            struct_logger.emit_llm_call(
                step_name=f"claude_cli:{job_id}",
                backend="claude_cli",
                model=self.model,
                tier=self.tier,
                status="start",
                metadata={
                    "session_id": session_id,
                    "system_prompt_preview": _preview_text(system_prompt or ""),
                    "user_prompt_preview": _preview_text(user_prompt or ""),
                    "prompt_length": len(prompt),
                }
            )

        # Log prompt stats with previews (goes through log_callback for CV generation flow)
        # This is the PRIMARY path for showing prompt previews - struct_logger goes to stdout
        # which isn't captured in the in-process CV generation flow.
        sys_preview = _preview_text(system_prompt or "", n=20)
        user_preview = _preview_text(user_prompt or "", n=30)
        self._emit_log(
            job_id, "info",
            message=f"⏳ CLI invocation started ({len(prompt):,} chars) - may take 20-30s",
            prompt_length=len(prompt),
            system_prompt_preview=sys_preview,
            user_prompt_preview=user_preview,
            session_id=session_id,
        )
        # Emit prompt details as separate log for visibility
        if user_preview:
            self._emit_log(
                job_id, "debug",
                message=f"  📝 Prompt: {user_preview}",
            )

        try:

            # Run Claude CLI in headless mode
            # --dangerously-skip-permissions skips permission prompts
            # Using --output-format text to avoid known CLI bug (#8126) where
            # --output-format json returns empty result field ~40% of the time
            cmd = [
                "claude", "-p", prompt,
                "--output-format", "text",
                "--model", self.model,
                "--dangerously-skip-permissions",
                "--tools", "",  # Disable all tools (proper syntax for --print mode)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Check for CLI errors
            if result.returncode != 0:
                error_msg = self._extract_cli_error(result.stdout, result.stderr, result.returncode)
                self._emit_log(job_id, "error", message=f"CLI failed: {error_msg}")
                # Emit structured error log for Redis live-tail
                if struct_logger:
                    struct_logger.emit_llm_call(
                        step_name=f"claude_cli:{job_id}",
                        backend="claude_cli",
                        model=self.model,
                        tier=self.tier,
                        status="error",
                        duration_ms=duration_ms,
                        error=error_msg,
                        metadata={
                            "session_id": session_id,
                            "returncode": result.returncode,
                        }
                    )
                return CLIResult(
                    job_id=job_id,
                    success=False,
                    result=None,
                    raw_result=None,
                    error=error_msg,
                    model=self.model,
                    tier=self.tier,
                    duration_ms=duration_ms,
                    invoked_at=start_time.isoformat()
                )

            # Parse output - with text format, stdout IS the LLM response directly
            # (no JSON wrapper, no metadata - but reliable response)
            raw_output = result.stdout.strip()

            # Log completion with output preview
            result_preview = _preview_text(raw_output, n=40)
            self._emit_log(
                job_id, "info",
                message=f"✅ CLI complete ({len(raw_output):,} chars, {duration_ms:,}ms)",
                result_length=len(raw_output),
                duration_ms=duration_ms,
                result_preview=result_preview,
            )
            # Log first part of response for debugging (separate line for readability)
            if raw_output:
                first_line = raw_output.split('\n')[0][:100]
                self._emit_log(
                    job_id, "debug",
                    message=f"  📄 Response: {first_line}{'...' if len(first_line) >= 100 else ''}",
                )

            # Emit structured log for Redis live-tail (complete)
            if struct_logger:
                # Estimate cost based on prompt and output lengths
                estimated_cost = self._estimate_cost_from_chars(len(prompt), len(raw_output))
                struct_logger.emit_llm_call(
                    step_name=f"claude_cli:{job_id}",
                    backend="claude_cli",
                    model=self.model,
                    tier=self.tier,
                    status="complete",
                    duration_ms=duration_ms,
                    cost_usd=estimated_cost,
                    metadata={
                        "session_id": session_id,
                        "result_preview": _preview_text(raw_output),
                        "result_length": len(raw_output),
                    }
                )

            if not raw_output:
                raise ValueError("CLI returned empty response")

            # Check for CLI error messages in stdout (e.g., "Error: Reached max turns (1)")
            # These occur with returncode=0 but should be treated as failures
            cli_error = self._detect_cli_error_in_stdout(raw_output)
            if cli_error:
                # Verbose error logging for debugging prompts
                prompt_preview = prompt[:500] + "..." if len(prompt) > 500 else prompt
                self._emit_log(
                    job_id, "error",
                    message=f"CLI error in stdout: {cli_error}",
                    cli_error=cli_error,
                    prompt_length=len(prompt),
                    prompt_preview=prompt_preview,
                    model=self.model,
                )
                return CLIResult(
                    job_id=job_id,
                    success=False,
                    result=None,
                    raw_result=raw_output,  # Include raw output for debugging
                    error=cli_error,
                    model=self.model,
                    tier=self.tier,
                    duration_ms=duration_ms,
                    invoked_at=start_time.isoformat()
                )

            if validate_json:
                # Parse the LLM response as JSON
                try:
                    parsed_data = parse_llm_json(raw_output)
                except ValueError as e:
                    # Verbose error logging for JSON parse failures
                    response_preview = raw_output[:500] + "..." if len(raw_output) > 500 else raw_output
                    self._emit_log(
                        job_id, "error",
                        message=f"Failed to parse LLM response as JSON: {e}",
                        response_preview=response_preview,
                        prompt_length=len(prompt),
                        model=self.model,
                    )
                    raise ValueError(f"Failed to parse LLM response as JSON: {e}")

                # No cost metadata with text format
                input_tokens, output_tokens, cost_usd = None, None, None
            else:
                # Return raw text result
                self._emit_log(
                    job_id, "info",
                    message=f"CLI invocation complete",
                    duration_ms=duration_ms,
                    input_tokens=None,
                    output_tokens=None,
                    cost_usd=None
                )
                return CLIResult(
                    job_id=job_id,
                    success=True,
                    result=None,
                    raw_result=raw_output,
                    error=None,
                    model=self.model,
                    tier=self.tier,
                    duration_ms=duration_ms,
                    invoked_at=start_time.isoformat(),
                    input_tokens=None,
                    output_tokens=None,
                    cost_usd=None
                )

            self._emit_log(
                job_id, "info",
                message=f"CLI invocation complete",
                duration_ms=duration_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd
            )

            return CLIResult(
                job_id=job_id,
                success=True,
                result=parsed_data,
                raw_result=None,
                error=None,
                model=self.model,
                tier=self.tier,
                duration_ms=duration_ms,
                invoked_at=start_time.isoformat(),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd
            )

        except subprocess.TimeoutExpired:
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            error_msg = f"CLI timeout after {self.timeout}s"
            self._emit_log(job_id, "error", message=error_msg)
            # Emit structured error log for Redis live-tail
            if struct_logger:
                struct_logger.emit_llm_call(
                    step_name=f"claude_cli:{job_id}",
                    backend="claude_cli",
                    model=self.model,
                    tier=self.tier,
                    status="error",
                    duration_ms=duration_ms,
                    error=error_msg,
                    metadata={"session_id": session_id, "error_type": "timeout"}
                )
            return CLIResult(
                job_id=job_id,
                success=False,
                result=None,
                raw_result=None,
                error=error_msg,
                model=self.model,
                tier=self.tier,
                duration_ms=duration_ms,
                invoked_at=start_time.isoformat()
            )

        except ValueError as e:
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            error_msg = str(e)
            self._emit_log(job_id, "error", message=f"Parse error: {error_msg}")
            # Emit structured error log for Redis live-tail
            if struct_logger:
                struct_logger.emit_llm_call(
                    step_name=f"claude_cli:{job_id}",
                    backend="claude_cli",
                    model=self.model,
                    tier=self.tier,
                    status="error",
                    duration_ms=duration_ms,
                    error=error_msg,
                    metadata={"session_id": session_id, "error_type": "parse_error"}
                )
            return CLIResult(
                job_id=job_id,
                success=False,
                result=None,
                raw_result=None,
                error=error_msg,
                model=self.model,
                tier=self.tier,
                duration_ms=duration_ms,
                invoked_at=start_time.isoformat()
            )

        except Exception as e:
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            error_msg = f"Unexpected error: {str(e)}"
            self._emit_log(job_id, "error", message=error_msg)
            # Emit structured error log for Redis live-tail
            if struct_logger:
                struct_logger.emit_llm_call(
                    step_name=f"claude_cli:{job_id}",
                    backend="claude_cli",
                    model=self.model,
                    tier=self.tier,
                    status="error",
                    duration_ms=duration_ms,
                    error=error_msg,
                    metadata={"session_id": session_id, "error_type": "unexpected"}
                )
            return CLIResult(
                job_id=job_id,
                success=False,
                result=None,
                raw_result=None,
                error=error_msg,
                model=self.model,
                tier=self.tier,
                duration_ms=duration_ms,
                invoked_at=start_time.isoformat()
            )

    async def invoke_batch(
        self,
        items: List[Dict[str, str]],
        max_concurrent: int = 3
    ) -> List[CLIResult]:
        """
        Invoke CLI for multiple items with controlled concurrency.

        Designed for batch operations. Uses asyncio semaphore to limit
        concurrent CLI processes.

        Args:
            items: List of dicts with keys: job_id, prompt
            max_concurrent: Maximum concurrent invocations (default 3)

        Returns:
            List of CLIResult in same order as input items
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def invoke_with_limit(item: Dict[str, str]) -> CLIResult:
            async with semaphore:
                # Run sync invocation in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None,
                    lambda: self.invoke(
                        item["prompt"],
                        item["job_id"]
                    )
                )

        tasks = [invoke_with_limit(item) for item in items]
        return await asyncio.gather(*tasks)

    def check_cli_available(self) -> bool:
        """
        Check if Claude CLI is installed and authenticated.

        Useful for health checks and graceful degradation.

        Returns:
            True if CLI is available and working
        """
        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    @staticmethod
    def get_tier_cost_estimate(tier: TierType, input_tokens: int, output_tokens: int) -> float:
        """
        Estimate cost for token usage at given tier.

        Args:
            tier: Model tier ("low", "middle", "high")
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Estimated cost in USD
        """
        # Handle legacy tier names
        if tier in TIER_ALIASES:
            tier = TIER_ALIASES[tier]  # type: ignore
        costs = CLAUDE_TIER_COSTS.get(tier, CLAUDE_TIER_COSTS["middle"])
        input_cost = (input_tokens / 1000) * costs["input"]
        output_cost = (output_tokens / 1000) * costs["output"]
        return input_cost + output_cost

    @staticmethod
    def get_tier_display_info() -> list:
        """
        Get tier information for UI display.

        Returns:
            List of tier display dictionaries for dropdown rendering
        """
        return [
            {
                "value": "low",
                "label": "Low (Haiku)",
                "model": "Claude Haiku 4.5",
                "description": "Lowest cost, good for bulk processing",
                "icon": "zap",
                "badge": "~$0.01/op",
            },
            {
                "value": "middle",
                "label": "Middle (Sonnet)",
                "model": "Claude Sonnet 4.5",
                "description": "Best quality/cost ratio - recommended for most tasks",
                "icon": "scale",
                "badge": "~$0.05/op",
            },
            {
                "value": "high",
                "label": "High (Opus)",
                "model": "Claude Opus 4.5",
                "description": "Highest quality for critical extractions",
                "icon": "star",
                "badge": "~$0.25/op",
            },
        ]


# Convenience function for quick invocation
def invoke_claude(
    prompt: str,
    job_id: str,
    tier: TierType = "middle",
    timeout: int = 300,
) -> CLIResult:
    """
    Convenience function for single Claude CLI invocation.

    Args:
        prompt: Full prompt text
        job_id: Tracking ID
        tier: Model tier (default "middle" = Sonnet)
        timeout: CLI timeout in seconds

    Returns:
        CLIResult with invocation outcome
    """
    cli = ClaudeCLI(tier=tier, timeout=timeout)
    return cli.invoke(prompt, job_id)
