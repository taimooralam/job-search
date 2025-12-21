"""
Unified LLM Wrapper - Claude CLI Primary, LangChain Fallback.

Provides a consistent interface for all LLM invocations across the pipeline.
Uses Claude Code CLI as primary with automatic LangChain fallback when CLI
fails or is unavailable.

Key Features:
    - Claude CLI as primary backend (uses Claude Code for high-quality responses)
    - Automatic LangChain fallback when CLI fails
    - Per-step configuration via llm_config.py
    - Backend attribution in all responses for transparency
    - Comprehensive logging and metrics

Usage:
    from src.common.unified_llm import UnifiedLLM

    # With step name (auto-loads config from llm_config.py)
    llm = UnifiedLLM(step_name="grader")
    result = await llm.invoke(prompt, system=system_prompt, job_id="123")

    # With explicit tier (overrides step config)
    llm = UnifiedLLM(tier="high")
    result = await llm.invoke(prompt, job_id="123")

    # Check result backend attribution
    print(f"Used backend: {result.backend}")  # "claude_cli" or "langchain"
    print(f"Model: {result.model}")
    print(f"Duration: {result.duration_ms}ms")

    # Batch invocation
    prompts = [{"job_id": "1", "prompt": "..."}, {"job_id": "2", "prompt": "..."}]
    results = await llm.invoke_batch(prompts, max_concurrent=3)
"""

import asyncio
import logging
import json
import subprocess
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List
from datetime import datetime

from src.common.claude_cli import ClaudeCLI, CLIResult
from src.common.llm_config import (
    get_step_config,
    StepConfig,
    TIER_TO_CLAUDE_MODEL,
    TIER_TO_FALLBACK_MODEL,
    TierType,
)
from src.common.json_utils import parse_llm_json
from src.common.utils import run_async

# Import TYPE_CHECKING to avoid circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.common.structured_logger import StructuredLogger

logger = logging.getLogger(__name__)


@dataclass
class LLMResult:
    """
    Result of a UnifiedLLM invocation with backend attribution.

    Contains the response content along with metadata about which backend
    was used, timing, costs, and any errors that occurred.

    Attributes:
        content: The LLM response content (text or parsed JSON string)
        parsed_json: Parsed JSON object if validate_json was True, else None
        backend: Which backend produced the response ("claude_cli" or "langchain")
        model: The model identifier used for the response
        tier: The tier level used ("low", "middle", "high")
        duration_ms: Time taken for the invocation in milliseconds
        success: Whether the invocation succeeded
        error: Error message if invocation failed
        input_tokens: Number of input tokens (if available)
        output_tokens: Number of output tokens (if available)
        cost_usd: Estimated cost in USD (if available)
    """

    content: str
    backend: str  # "claude_cli" or "langchain"
    model: str
    tier: str
    duration_ms: int
    success: bool
    parsed_json: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_usd: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class UnifiedLLM:
    """
    Unified LLM interface - Claude CLI primary, LangChain fallback.

    This class provides a single, consistent interface for all LLM invocations
    in the pipeline. It uses Claude CLI as the primary backend for best quality,
    with automatic fallback to LangChain when CLI fails.

    The backend used is always reported in the result for transparency and
    debugging purposes.

    Attributes:
        config: StepConfig with tier, model, and behavior settings
        step_name: Name of the pipeline step (for logging/tracking)
        job_id: Default job ID for tracking
    """

    def __init__(
        self,
        step_name: Optional[str] = None,
        tier: Optional[TierType] = None,
        config: Optional[StepConfig] = None,
        job_id: Optional[str] = None,
        struct_logger: Optional["StructuredLogger"] = None,
    ):
        """
        Initialize the UnifiedLLM wrapper.

        Args:
            step_name: Pipeline step name to load config for (e.g., "grader")
            tier: Explicit tier override ("low", "middle", "high")
            config: Explicit StepConfig (overrides step_name lookup)
            job_id: Default job ID for tracking (can be overridden per-call)
            struct_logger: Optional StructuredLogger for emitting LLM call events
                to the frontend log stream. When provided, LLM calls will be
                visible in the pipeline execution logs.

        Note:
            If step_name is provided, config is loaded from STEP_CONFIGS.
            If tier is also provided, it overrides the loaded config's tier.
            If config is provided directly, it takes precedence over step_name.
        """
        # Load config from step name or use provided
        if step_name:
            self.config = get_step_config(step_name)
            self.step_name = step_name
        elif config:
            self.config = config
            self.step_name = "custom"
        else:
            self.config = StepConfig(tier=tier or "middle")
            self.step_name = "unnamed"

        # Override tier if explicitly provided
        if tier:
            self.config.tier = tier

        self.job_id = job_id or "unknown"
        self._cli: Optional[ClaudeCLI] = None
        self._langchain_llm = None
        self._struct_logger = struct_logger

    @property
    def cli(self) -> ClaudeCLI:
        """Lazy-initialize Claude CLI client."""
        if self._cli is None:
            self._cli = ClaudeCLI(
                tier=self.config.tier,
                timeout=self.config.timeout_seconds,
            )
        return self._cli

    def _should_use_cli(self) -> bool:
        """
        Determine if Claude CLI should be attempted.

        Returns True unless CLI is explicitly disabled or unavailable.
        """
        # Check for explicit disable via environment
        import os
        if os.getenv("DISABLE_CLAUDE_CLI", "").lower() == "true":
            return False
        return True

    async def invoke(
        self,
        prompt: str,
        system: Optional[str] = None,
        job_id: Optional[str] = None,
        validate_json: bool = True,
    ) -> LLMResult:
        """
        Invoke LLM with Claude CLI primary, LangChain fallback.

        This method first attempts to use Claude CLI. If that fails (timeout,
        error, etc.) and fallback is enabled, it automatically tries the
        LangChain backend.

        The backend used is always reported in the result for transparency.

        Args:
            prompt: The user prompt to send to the LLM
            system: Optional system prompt (combined with user prompt for CLI)
            job_id: Job ID for tracking (overrides default)
            validate_json: Whether to parse response as JSON (default True)

        Returns:
            LLMResult with response and backend attribution

        Example:
            >>> llm = UnifiedLLM(step_name="grader")
            >>> result = await llm.invoke("Grade this CV", system="You are a CV grader")
            >>> print(f"Grade: {result.content}, via {result.backend}")
        """
        job_id = job_id or self.job_id
        combined_prompt = f"{system}\n\n{prompt}" if system else prompt

        # Track specific CLI error reason for fallback logging
        cli_error_reason: Optional[str] = None

        # Try Claude CLI first
        if self._should_use_cli():
            try:
                result = await self._invoke_cli(combined_prompt, job_id, validate_json)
                if result.success:
                    self._log_success("claude_cli", result, job_id)
                    return result
                # CLI failed, capture specific error reason
                cli_error_reason = f"CLI returned error: {result.error}"
                logger.warning(
                    f"[UnifiedLLM:{self.step_name}] Claude CLI failed: {result.error}"
                )
            except subprocess.TimeoutExpired as e:
                cli_error_reason = f"CLI timeout after {e.timeout}s"
                logger.warning(
                    f"[UnifiedLLM:{self.step_name}] {cli_error_reason}"
                )
            except FileNotFoundError:
                cli_error_reason = "Claude CLI not found in PATH"
                logger.warning(
                    f"[UnifiedLLM:{self.step_name}] {cli_error_reason}"
                )
            except Exception as e:
                cli_error_reason = f"CLI exception: {type(e).__name__}: {e}"
                logger.warning(
                    f"[UnifiedLLM:{self.step_name}] Claude CLI exception: {e}"
                )
        else:
            cli_error_reason = "CLI disabled via DISABLE_CLAUDE_CLI env var"

        # Fallback to LangChain
        if self.config.use_fallback:
            logger.info(
                f"[UnifiedLLM:{self.step_name}] Falling back to LangChain"
            )
            # Log fallback event with specific reason for visibility
            self._log_fallback(job_id, cli_error_reason or "CLI unavailable")
            return await self._invoke_langchain(prompt, system, job_id, validate_json)
        else:
            return LLMResult(
                content="",
                backend="none",
                model="",
                tier=self.config.tier,
                duration_ms=0,
                success=False,
                error="Claude CLI failed and fallback is disabled",
            )

    async def _invoke_cli(
        self,
        prompt: str,
        job_id: str,
        validate_json: bool,
    ) -> LLMResult:
        """
        Invoke Claude CLI backend.

        Runs the CLI in a thread pool to avoid blocking the event loop.

        Args:
            prompt: Combined system + user prompt
            job_id: Job ID for tracking
            validate_json: Whether to parse response as JSON

        Returns:
            LLMResult from CLI invocation
        """
        start_time = datetime.utcnow()

        # Run sync CLI in thread pool
        loop = asyncio.get_event_loop()
        cli_result: CLIResult = await loop.run_in_executor(
            None,
            lambda: self.cli.invoke(prompt, job_id, validate_json=validate_json),
        )

        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        if cli_result.success:
            # Extract content based on whether JSON was validated
            if validate_json and cli_result.result:
                content = json.dumps(cli_result.result)
                parsed_json = cli_result.result
            else:
                content = cli_result.raw_result or ""
                parsed_json = None

            return LLMResult(
                content=content,
                parsed_json=parsed_json,
                backend="claude_cli",
                model=cli_result.model,
                tier=cli_result.tier,
                duration_ms=duration_ms,
                success=True,
                input_tokens=cli_result.input_tokens,
                output_tokens=cli_result.output_tokens,
                cost_usd=cli_result.cost_usd,
            )
        else:
            return LLMResult(
                content="",
                backend="claude_cli",
                model=cli_result.model,
                tier=cli_result.tier,
                duration_ms=duration_ms,
                success=False,
                error=cli_result.error,
            )

    async def _invoke_langchain(
        self,
        prompt: str,
        system: Optional[str],
        job_id: str,
        validate_json: bool,
    ) -> LLMResult:
        """
        Invoke LangChain fallback backend.

        Uses the fallback model configured for this step's tier.

        Args:
            prompt: User prompt
            system: System prompt (kept separate for LangChain)
            job_id: Job ID for tracking
            validate_json: Whether to parse response as JSON

        Returns:
            LLMResult from LangChain invocation
        """
        from src.common.llm_factory import create_tracked_llm_for_model

        start_time = datetime.utcnow()
        fallback_model = self.config.get_fallback_model()

        try:
            # Create LangChain LLM with tracking
            llm = create_tracked_llm_for_model(
                model=fallback_model,
                layer=self.step_name,
                job_id=job_id,
            )

            # Build messages
            from langchain_core.messages import SystemMessage, HumanMessage

            messages = []
            if system:
                messages.append(SystemMessage(content=system))
            messages.append(HumanMessage(content=prompt))

            # Invoke LLM
            response = await llm.ainvoke(messages)
            content = response.content if hasattr(response, 'content') else str(response)

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Parse JSON if requested
            parsed_json = None
            if validate_json:
                try:
                    parsed_json = parse_llm_json(content)
                except ValueError as e:
                    logger.warning(f"[UnifiedLLM:{self.step_name}] JSON parse failed: {e}")

            # Extract token usage if available
            input_tokens = None
            output_tokens = None
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                input_tokens = response.usage_metadata.get('input_tokens')
                output_tokens = response.usage_metadata.get('output_tokens')

            self._log_success("langchain", None, job_id, duration_ms, fallback_model, is_fallback=True)

            return LLMResult(
                content=content,
                parsed_json=parsed_json,
                backend="langchain",
                model=fallback_model,
                tier=self.config.tier,
                duration_ms=duration_ms,
                success=True,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        except Exception as e:
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            error_msg = f"LangChain fallback failed: {str(e)}"
            logger.error(f"[UnifiedLLM:{self.step_name}] {error_msg}")

            return LLMResult(
                content="",
                backend="langchain",
                model=fallback_model,
                tier=self.config.tier,
                duration_ms=duration_ms,
                success=False,
                error=error_msg,
            )

    async def invoke_batch(
        self,
        items: List[Dict[str, str]],
        system: Optional[str] = None,
        max_concurrent: int = 3,
        validate_json: bool = True,
    ) -> List[LLMResult]:
        """
        Invoke LLM for multiple items with controlled concurrency.

        Each item gets its own invocation with the shared system prompt.
        Results are returned in the same order as input items.

        Args:
            items: List of dicts with keys: job_id, prompt
            system: Shared system prompt for all items
            max_concurrent: Maximum concurrent invocations (default 3)
            validate_json: Whether to parse responses as JSON

        Returns:
            List of LLMResult in same order as input items

        Example:
            >>> items = [
            ...     {"job_id": "1", "prompt": "Grade CV 1"},
            ...     {"job_id": "2", "prompt": "Grade CV 2"},
            ... ]
            >>> results = await llm.invoke_batch(items, system="You are a grader")
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def invoke_with_limit(item: Dict[str, str]) -> LLMResult:
            async with semaphore:
                return await self.invoke(
                    prompt=item["prompt"],
                    system=system,
                    job_id=item["job_id"],
                    validate_json=validate_json,
                )

        tasks = [invoke_with_limit(item) for item in items]
        return await asyncio.gather(*tasks)

    def _log_success(
        self,
        backend: str,
        result: Optional[LLMResult],
        job_id: str,
        duration_ms: Optional[int] = None,
        model: Optional[str] = None,
        is_fallback: bool = False,
    ) -> None:
        """
        Log successful invocation for transparency.

        Logs to both Python logger (for debug) and structured logger (for frontend).

        Args:
            backend: Which backend was used ("claude_cli" or "langchain")
            result: LLMResult if available (for CLI results)
            job_id: Job ID for tracking
            duration_ms: Duration in milliseconds (for LangChain results)
            model: Model used (for LangChain results)
            is_fallback: Whether this was a fallback invocation
        """
        if result:
            duration_ms = result.duration_ms
            model = result.model
            cost_usd = result.cost_usd
        else:
            cost_usd = None

        # Log to Python logger (for debug/file logs)
        fallback_marker = " [fallback]" if is_fallback else ""
        logger.info(
            f"[UnifiedLLM:{self.step_name}] "
            f"Backend={backend}, Model={model}, "
            f"Duration={duration_ms}ms, Job={job_id}{fallback_marker}"
        )

        # Emit to structured logger if available (for frontend logs)
        if self._struct_logger:
            self._struct_logger.llm_call_complete(
                step_name=self.step_name,
                backend=backend,
                model=model or "unknown",
                tier=self.config.tier,
                duration_ms=duration_ms or 0,
                cost_usd=cost_usd,
                metadata={"is_fallback": is_fallback} if is_fallback else None,
            )

    def _log_fallback(self, job_id: str, reason: str) -> None:
        """
        Log when falling back from Claude CLI to LangChain.

        Args:
            job_id: Job ID for tracking
            reason: Reason for the fallback
        """
        fallback_model = self.config.get_fallback_model()

        logger.info(
            f"[UnifiedLLM:{self.step_name}] "
            f"Falling back: claude_cli -> langchain ({fallback_model}), "
            f"Reason={reason}, Job={job_id}"
        )

        # Emit to structured logger if available
        if self._struct_logger:
            self._struct_logger.llm_call_fallback(
                step_name=self.step_name,
                from_backend="claude_cli",
                to_backend="langchain",
                model=fallback_model,
                tier=self.config.tier,
                reason=reason,
            )

    def check_cli_available(self) -> bool:
        """
        Check if Claude CLI is installed and authenticated.

        Useful for health checks and graceful degradation.

        Returns:
            True if CLI is available and working
        """
        return self.cli.check_cli_available()


# ===== CONVENIENCE FUNCTIONS =====

async def invoke_unified(
    prompt: str,
    step_name: Optional[str] = None,
    tier: Optional[TierType] = None,
    system: Optional[str] = None,
    job_id: str = "unknown",
    validate_json: bool = True,
    struct_logger: Optional["StructuredLogger"] = None,
) -> LLMResult:
    """
    Convenience function for single UnifiedLLM invocation.

    Creates a UnifiedLLM instance and invokes it once.

    Args:
        prompt: User prompt
        step_name: Pipeline step name for config lookup
        tier: Explicit tier override
        system: System prompt
        job_id: Job ID for tracking
        validate_json: Whether to parse response as JSON
        struct_logger: Optional StructuredLogger for frontend visibility

    Returns:
        LLMResult with response and backend attribution

    Example:
        >>> result = await invoke_unified(
        ...     "Grade this CV",
        ...     step_name="grader",
        ...     system="You are a CV grader",
        ...     job_id="job_123"
        ... )
    """
    llm = UnifiedLLM(step_name=step_name, tier=tier, job_id=job_id, struct_logger=struct_logger)
    return await llm.invoke(prompt, system=system, validate_json=validate_json)


def invoke_unified_sync(
    prompt: str,
    step_name: Optional[str] = None,
    tier: Optional[TierType] = None,
    system: Optional[str] = None,
    job_id: str = "unknown",
    validate_json: bool = True,
    struct_logger: Optional["StructuredLogger"] = None,
) -> LLMResult:
    """
    Synchronous convenience function for UnifiedLLM invocation.

    Creates a new event loop if needed to run the async invocation.

    Args:
        prompt: User prompt
        step_name: Pipeline step name for config lookup
        tier: Explicit tier override
        system: System prompt
        job_id: Job ID for tracking
        validate_json: Whether to parse response as JSON
        struct_logger: Optional StructuredLogger for frontend visibility

    Returns:
        LLMResult with response and backend attribution

    Example:
        >>> result = invoke_unified_sync(
        ...     "Grade this CV",
        ...     step_name="grader",
        ...     system="You are a CV grader",
        ...     job_id="job_123"
        ... )
    """
    return run_async(invoke_unified(
        prompt=prompt,
        step_name=step_name,
        tier=tier,
        system=system,
        job_id=job_id,
        validate_json=validate_json,
        struct_logger=struct_logger,
    ))
