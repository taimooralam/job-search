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
from typing import Optional, Dict, Any, Callable, List, Literal
from dataclasses import dataclass, asdict
from datetime import datetime

from src.common.json_utils import parse_llm_json


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
        timeout: int = 180,
        log_callback: Optional[LogCallback] = None,
        model_override: Optional[str] = None,
    ):
        """
        Initialize the Claude CLI wrapper.

        Args:
            tier: Model tier - "low" (Haiku), "middle" (Sonnet), "high" (Opus)
            timeout: CLI timeout in seconds (default 180s for complex operations)
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
        """Default logging - replace with Redis publisher if needed."""
        log_level = getattr(logging, level.upper(), logging.INFO)
        message = data.get("message", str(data))
        logger.log(log_level, f"[ClaudeCLI:{job_id}] {message}")

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
    def _parse_cli_output(self, stdout: str) -> tuple[Dict[str, Any], Optional[int], Optional[int], Optional[float]]:
        """
        Parse Claude CLI JSON output.

        CLI returns (v2.0.75+): {"result": "...", "is_error": false, "usage": {...}, "total_cost_usd": N, ...}
        Or legacy:             {"result": "...", "cost": {...}, "model": "...", ...}
        Extracts the "result" field and parses cost information.

        Returns:
            Tuple of (parsed_data, input_tokens, output_tokens, cost_usd)

        Raises:
            ValueError: If CLI returned an error or result cannot be parsed
        """
        try:
            cli_output = json.loads(stdout)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse CLI output as JSON: {e}")

        # Check for error response first (v2.0.75+)
        # CLI may return is_error=true even with returncode=0
        if cli_output.get("is_error"):
            error_text = cli_output.get("result", "Unknown CLI error")
            raise ValueError(f"CLI returned error: {error_text}")

        # Check for errors array (can occur even when is_error is absent/false)
        # CLI v2.0.75+ may return errors array without setting is_error=true
        errors = cli_output.get("errors", [])
        if errors:
            error_messages = []
            for e in errors:
                if isinstance(e, dict):
                    error_messages.append(e.get("message", e.get("type", str(e))))
                else:
                    error_messages.append(str(e))
            if error_messages:
                raise ValueError(f"CLI returned errors: {'; '.join(error_messages)}")

        # Check for tool_use response (model tried to use a tool but max_turns=1 prevents completion)
        # This happens when --allowedTools is set but the model's response is tool use
        response_type = cli_output.get("type", "")
        if response_type == "tool_use":
            tool_name = cli_output.get("name", "unknown")
            raise ValueError(
                f"Model attempted tool use ({tool_name}) but conversation ended before completion. "
                f"Disable tools with allow_tools=False or increase max_turns."
            )

        result_text = cli_output.get("result", "")
        if not result_text:
            # Include response type in error for debugging
            raise ValueError(
                f"CLI output missing 'result' field. "
                f"Response type: {response_type or 'unknown'}, keys: {list(cli_output.keys())}"
            )

        # Extract cost information (supports both new and legacy formats)
        input_tokens, output_tokens, cost_usd = self._extract_cost_info(cli_output)

        # Parse the actual result
        try:
            parsed_data = parse_llm_json(result_text)
        except ValueError as e:
            raise ValueError(f"Failed to parse result JSON: {e}")

        return parsed_data, input_tokens, output_tokens, cost_usd

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

    def invoke(
        self,
        prompt: str,
        job_id: str,
        max_turns: int = 1,
        validate_json: bool = True,
        allow_tools: bool = False,
    ) -> CLIResult:
        """
        Execute Claude CLI with prompt and return parsed result.

        Runs: claude -p {prompt} --output-format json --model {model} --max-turns {max_turns}

        Args:
            prompt: Full prompt text (system + user combined)
            job_id: Tracking ID for this invocation
            max_turns: Maximum conversation turns (default 1 for extraction)
            validate_json: Whether to parse result as JSON (default True)
            allow_tools: Whether to enable CLI tools (WebSearch, WebFetch, Read).
                        Default False to prevent tool_use responses with max_turns=1.
                        Set True for research tasks that need web search.

        Returns:
            CLIResult with success/failure status and parsed data
        """
        start_time = datetime.utcnow()
        self._emit_log(job_id, "info", message=f"Starting CLI invocation with {self.tier} tier ({self.model})")

        # Log prompt stats
        self._emit_log(job_id, "debug", message=f"Prompt length: {len(prompt)} chars")

        try:
            self._emit_log(job_id, "debug", message="Invoking Claude CLI...")

            # Run Claude CLI in headless mode
            # --dangerously-skip-permissions skips permission prompts
            # Using --output-format text to avoid known CLI bug (#8126) where
            # --output-format json returns empty result field ~40% of the time
            cmd = [
                "claude", "-p", prompt,
                "--output-format", "text",
                "--model", self.model,
                "--max-turns", str(max_turns),
                "--dangerously-skip-permissions",
            ]
            # Only enable tools when explicitly requested
            # With max_turns=1, tool_use responses would exit before completion
            if allow_tools:
                cmd.extend(["--allowedTools", "WebSearch,WebFetch,Read"])

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

            if not raw_output:
                raise ValueError("CLI returned empty response")

            if validate_json:
                # Parse the LLM response as JSON
                try:
                    parsed_data = parse_llm_json(raw_output)
                except ValueError as e:
                    raise ValueError(f"Failed to parse LLM response as JSON: {e}")
                    cli_output = json.loads(result.stdout)

                    # Check for error response first (v2.0.75+)
                    # CLI may return is_error=true even with returncode=0
                    if cli_output.get("is_error"):
                        error_text = cli_output.get("result", "Unknown CLI error")
                        self._emit_log(job_id, "error", message=f"CLI error: {error_text}")
                        return CLIResult(
                            job_id=job_id,
                            success=False,
                            result=None,
                            raw_result=None,
                            error=error_text,
                            model=self.model,
                            tier=self.tier,
                            duration_ms=duration_ms,
                            invoked_at=start_time.isoformat()
                        )

                    # Check for errors array (can occur even when is_error is absent/false)
                    errors = cli_output.get("errors", [])
                    if errors:
                        error_messages = []
                        for e in errors:
                            if isinstance(e, dict):
                                error_messages.append(e.get("message", e.get("type", str(e))))
                            else:
                                error_messages.append(str(e))
                        if error_messages:
                            error_text = f"CLI returned errors: {'; '.join(error_messages)}"
                            self._emit_log(job_id, "error", message=error_text)
                            return CLIResult(
                                job_id=job_id,
                                success=False,
                                result=None,
                                raw_result=None,
                                error=error_text,
                                model=self.model,
                                tier=self.tier,
                                duration_ms=duration_ms,
                                invoked_at=start_time.isoformat()
                            )

                    raw_result = cli_output.get("result", result.stdout)
                    input_tokens, output_tokens, cost_usd = self._extract_cost_info(cli_output)
                except json.JSONDecodeError:
                    raw_result = result.stdout
                    input_tokens, output_tokens, cost_usd = None, None, None

                # No cost metadata with text format
                input_tokens, output_tokens, cost_usd = None, None, None
            else:
                # Return raw text result
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
    timeout: int = 180,
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
