"""
Claude Code CLI Wrapper with Three-Tier Model Support

Provides a reusable wrapper for invoking Claude Code CLI in headless mode.
Supports three Claude model tiers for cost/quality tradeoffs:
- Fast: Claude Haiku 4.5 (lowest cost, good for bulk)
- Balanced: Claude Sonnet 4.5 (DEFAULT - best quality/cost ratio)
- Quality: Claude Opus 4.5 (highest quality)

Usage:
    # Single invocation with default tier (Sonnet)
    cli = ClaudeCLI()
    result = cli.invoke(prompt, job_id="123")

    # With specific tier
    cli = ClaudeCLI(tier="fast")  # Haiku for bulk processing
    result = cli.invoke(prompt, job_id="123")

    # With quality tier
    cli = ClaudeCLI(tier="quality")  # Opus for critical extractions
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
    "fast": "claude-haiku-4-5-20251101",       # Lowest cost, good for bulk
    "balanced": "claude-sonnet-4-5-20251101",  # DEFAULT - best quality/cost
    "quality": "claude-opus-4-5-20251101",     # Highest quality
}

# Default tier for batch operations
DEFAULT_BATCH_TIER = "balanced"  # Sonnet 4.5 by default

# Approximate costs per 1K tokens (USD)
CLAUDE_TIER_COSTS = {
    "fast": {"input": 0.00025, "output": 0.00125},      # Haiku
    "balanced": {"input": 0.003, "output": 0.015},      # Sonnet
    "quality": {"input": 0.015, "output": 0.075},       # Opus
}

# Type alias for tier
TierType = Literal["fast", "balanced", "quality"]


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
        tier: Model tier ("fast", "balanced", "quality")
        model: Actual Claude model ID
        timeout: Maximum seconds to wait for CLI response
        log_callback: Optional callback for log streaming
    """

    def __init__(
        self,
        tier: TierType = "balanced",
        timeout: int = 180,
        log_callback: Optional[LogCallback] = None,
        model_override: Optional[str] = None,
    ):
        """
        Initialize the Claude CLI wrapper.

        Args:
            tier: Model tier - "fast" (Haiku), "balanced" (Sonnet), "quality" (Opus)
            timeout: CLI timeout in seconds (default 180s for complex operations)
            log_callback: Optional callback for log events (for Redis live-tail)
            model_override: Override model selection (for testing or special cases)
        """
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

        return CLAUDE_MODEL_TIERS.get(tier, CLAUDE_MODEL_TIERS["balanced"])

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

    def _parse_cli_output(self, stdout: str) -> tuple[Dict[str, Any], Optional[int], Optional[int], Optional[float]]:
        """
        Parse Claude CLI JSON output.

        CLI returns: {"result": "...", "cost": {...}, "model": "...", ...}
        Extracts the "result" field and parses cost information.

        Returns:
            Tuple of (parsed_data, input_tokens, output_tokens, cost_usd)
        """
        try:
            cli_output = json.loads(stdout)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse CLI output as JSON: {e}")

        result_text = cli_output.get("result", "")
        if not result_text:
            raise ValueError("CLI output missing 'result' field")

        # Extract cost information if available
        cost_info = cli_output.get("cost", {})
        input_tokens = cost_info.get("input_tokens")
        output_tokens = cost_info.get("output_tokens")
        cost_usd = cost_info.get("total_cost_usd")

        # Parse the actual result
        try:
            parsed_data = parse_llm_json(result_text)
        except ValueError as e:
            raise ValueError(f"Failed to parse result JSON: {e}")

        return parsed_data, input_tokens, output_tokens, cost_usd

    def invoke(
        self,
        prompt: str,
        job_id: str,
        max_turns: int = 1,
        validate_json: bool = True,
    ) -> CLIResult:
        """
        Execute Claude CLI with prompt and return parsed result.

        Runs: claude -p {prompt} --output-format json --model {model} --max-turns {max_turns}

        Args:
            prompt: Full prompt text (system + user combined)
            job_id: Tracking ID for this invocation
            max_turns: Maximum conversation turns (default 1 for extraction)
            validate_json: Whether to parse result as JSON (default True)

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
            result = subprocess.run(
                [
                    "claude", "-p", prompt,
                    "--output-format", "json",
                    "--model", self.model,
                    "--max-turns", str(max_turns)
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout
            )

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Check for CLI errors
            if result.returncode != 0:
                error_msg = result.stderr or f"CLI exited with code {result.returncode}"
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

            # Parse output
            if validate_json:
                parsed_data, input_tokens, output_tokens, cost_usd = self._parse_cli_output(result.stdout)
            else:
                # Return raw result without JSON parsing
                try:
                    cli_output = json.loads(result.stdout)
                    raw_result = cli_output.get("result", result.stdout)
                    cost_info = cli_output.get("cost", {})
                    input_tokens = cost_info.get("input_tokens")
                    output_tokens = cost_info.get("output_tokens")
                    cost_usd = cost_info.get("total_cost_usd")
                except json.JSONDecodeError:
                    raw_result = result.stdout
                    input_tokens, output_tokens, cost_usd = None, None, None

                return CLIResult(
                    job_id=job_id,
                    success=True,
                    result=None,
                    raw_result=raw_result,
                    error=None,
                    model=self.model,
                    tier=self.tier,
                    duration_ms=duration_ms,
                    invoked_at=start_time.isoformat(),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd
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
            tier: Model tier
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Estimated cost in USD
        """
        costs = CLAUDE_TIER_COSTS.get(tier, CLAUDE_TIER_COSTS["balanced"])
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
                "value": "fast",
                "label": "Fast",
                "model": "Claude Haiku 4.5",
                "description": "Lowest cost, good for bulk processing",
                "icon": "zap",
                "badge": "~$0.01/op",
            },
            {
                "value": "balanced",
                "label": "Balanced (Default)",
                "model": "Claude Sonnet 4.5",
                "description": "Best quality/cost ratio - recommended for most tasks",
                "icon": "scale",
                "badge": "~$0.05/op",
            },
            {
                "value": "quality",
                "label": "Quality",
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
    tier: TierType = "balanced",
    timeout: int = 180,
) -> CLIResult:
    """
    Convenience function for single Claude CLI invocation.

    Args:
        prompt: Full prompt text
        job_id: Tracking ID
        tier: Model tier (default "balanced" = Sonnet)
        timeout: CLI timeout in seconds

    Returns:
        CLIResult with invocation outcome
    """
    cli = ClaudeCLI(tier=tier, timeout=timeout)
    return cli.invoke(prompt, job_id)
