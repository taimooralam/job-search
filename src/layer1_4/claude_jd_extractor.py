"""
Layer 1.4: Claude Code CLI JD Extractor

Parallel JD extraction module using Claude Code CLI (headless mode).
Runs alongside GPT-4o extraction for A/B quality comparison.
Uses Claude Max subscription via CLI authentication.

Architecture: Batch-ready with logging hooks for future Redis live-tail.

Usage:
    # Single extraction
    extractor = ClaudeJDExtractor(model="claude-opus-4-5-20251101")
    result = extractor.extract(job_id, title, company, job_description)

    # Batch extraction
    results = await extractor.extract_batch(jobs, max_concurrent=3)

    # With Redis logging (future)
    extractor = ClaudeJDExtractor(log_callback=redis_publisher)
"""

import subprocess
import json
import logging
import asyncio
import os
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
from pydantic import ValidationError

from src.common.state import ExtractedJD
from src.common.json_utils import parse_llm_json
from src.layer1_4.prompts import (
    JD_EXTRACTION_SYSTEM_PROMPT,
    JD_EXTRACTION_USER_TEMPLATE,
)
from src.layer1_4.jd_extractor import ExtractedJDModel

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """
    Result of a single extraction - batch-friendly structure.

    Designed for consistent handling in both single and batch operations.
    Contains all metadata needed for comparison analytics.
    """
    job_id: str
    success: bool
    extracted_jd: Optional[Dict[str, Any]]  # ExtractedJD as dict for JSON serialization
    error: Optional[str]
    model: str
    duration_ms: int
    extracted_at: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


# Type alias for log callback (future Redis integration)
# Signature: (job_id, level, data) -> None
LogCallback = Callable[[str, str, Dict[str, Any]], None]


class ClaudeJDExtractor:
    """
    Extract job descriptions using Claude Code CLI (headless mode).

    Uses the same prompts as GPT-4o extractor for fair A/B comparison.
    Designed for both single and batch operations with pluggable logging.

    Attributes:
        model: Claude model ID (e.g., "claude-opus-4-5-20251101")
        timeout: Maximum seconds to wait for CLI response
        log_callback: Optional callback for log streaming (Redis live-tail)
    """

    # Default model - can be overridden via CLAUDE_CODE_MODEL env var
    DEFAULT_MODEL = "claude-opus-4-5-20251101"

    def __init__(
        self,
        model: Optional[str] = None,
        timeout: int = 120,
        log_callback: Optional[LogCallback] = None
    ):
        """
        Initialize the Claude JD extractor.

        Args:
            model: Claude model ID. Defaults to CLAUDE_CODE_MODEL env var or Opus 4.5.
            timeout: CLI timeout in seconds (default 120s).
            log_callback: Optional callback for log events (for Redis live-tail).
        """
        self.model = model or os.getenv("CLAUDE_CODE_MODEL", self.DEFAULT_MODEL)
        self.timeout = timeout
        self._log_callback = log_callback or self._default_log

    def _default_log(self, job_id: str, level: str, data: Dict[str, Any]) -> None:
        """Default logging - replace with Redis publisher later."""
        log_level = getattr(logging, level.upper(), logging.INFO)
        message = data.get("message", str(data))
        logger.log(log_level, f"[Claude:{job_id}] {message}")

    def _emit_log(self, job_id: str, level: str, **kwargs) -> None:
        """
        Emit log event - hook for Redis live-tail.

        All log events go through this method, making it easy to
        swap in Redis publishing later.
        """
        self._log_callback(job_id, level, {
            "timestamp": datetime.utcnow().isoformat(),
            "extractor": "claude-code-cli",
            "model": self.model,
            **kwargs
        })

    def _build_prompt(self, title: str, company: str, job_description: str) -> str:
        """
        Build the full prompt for Claude CLI.

        Combines system prompt + user template for CLI's single-prompt interface.
        Uses same prompts as GPT-4o extractor for fair comparison.
        """
        # Truncate JD to same limit as GPT-4o extractor (12000 chars)
        truncated_jd = job_description[:12000]

        user_content = JD_EXTRACTION_USER_TEMPLATE.format(
            title=title,
            company=company,
            job_description=truncated_jd
        )

        return f"""{JD_EXTRACTION_SYSTEM_PROMPT}

---

{user_content}

Return ONLY valid JSON matching the ExtractedJD schema. No markdown, no explanation."""

    def _parse_cli_output(self, stdout: str) -> Dict[str, Any]:
        """
        Parse Claude CLI JSON output.

        CLI returns: {"result": "...", "cost": {...}, "model": "...", ...}
        We need to extract and parse the "result" field which contains the JD JSON.
        """
        try:
            cli_output = json.loads(stdout)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse CLI output as JSON: {e}")

        result_text = cli_output.get("result", "")
        if not result_text:
            raise ValueError("CLI output missing 'result' field")

        # Parse the actual extraction result
        try:
            extracted_data = parse_llm_json(result_text)
        except ValueError as e:
            raise ValueError(f"Failed to parse extraction result: {e}")

        return extracted_data

    def _validate_and_convert(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate extracted data using same Pydantic model as GPT-4o extractor.

        Returns ExtractedJD as dictionary for JSON serialization.
        """
        # Normalize enum values (handle case variations from LLM)
        if "role_category" in data:
            data["role_category"] = data["role_category"].lower().replace(" ", "_").replace("-", "_")
        if "seniority_level" in data:
            data["seniority_level"] = data["seniority_level"].lower().replace(" ", "_").replace("-", "_")
        if "remote_policy" in data:
            data["remote_policy"] = data["remote_policy"].lower().replace(" ", "_").replace("-", "_")

        try:
            validated = ExtractedJDModel(**data)
            # Convert to TypedDict, then to dict for JSON serialization
            extracted_jd = validated.to_extracted_jd()
            return dict(extracted_jd)
        except ValidationError as e:
            error_msgs = [f"{' -> '.join(str(x) for x in err['loc'])}: {err['msg']}"
                        for err in e.errors()]
            raise ValueError(
                f"Schema validation failed:\n" +
                "\n".join(f"  - {msg}" for msg in error_msgs)
            )

    def extract(
        self,
        job_id: str,
        title: str,
        company: str,
        job_description: str
    ) -> ExtractionResult:
        """
        Extract structured JD using Claude Code CLI.

        Returns ExtractionResult for consistent batch handling.
        Retries are handled by the CLI itself (built-in retry logic).

        Args:
            job_id: MongoDB job ID for tracking
            title: Job title
            company: Company name
            job_description: Full job description text

        Returns:
            ExtractionResult with success/failure status and extracted data
        """
        start_time = datetime.utcnow()
        self._emit_log(job_id, "info", message=f"Starting extraction with {self.model}")

        # Build the prompt
        prompt = self._build_prompt(title, company, job_description)
        self._emit_log(job_id, "debug", message=f"Prompt length: {len(prompt)} chars")

        try:
            self._emit_log(job_id, "debug", message="Invoking Claude CLI...")

            # Run Claude CLI in headless mode
            result = subprocess.run(
                [
                    "claude", "-p", prompt,
                    "--output-format", "json",
                    "--model", self.model,
                    "--max-turns", "1"  # Single turn for extraction
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
                return ExtractionResult(
                    job_id=job_id,
                    success=False,
                    extracted_jd=None,
                    error=error_msg,
                    model=self.model,
                    duration_ms=duration_ms,
                    extracted_at=start_time.isoformat()
                )

            # Parse CLI output
            extracted_data = self._parse_cli_output(result.stdout)

            # Validate and convert
            validated_jd = self._validate_and_convert(extracted_data)

            self._emit_log(
                job_id, "info",
                message=f"Extraction complete: {validated_jd.get('role_category', 'unknown')}",
                duration_ms=duration_ms,
                role_category=validated_jd.get("role_category"),
                keywords_count=len(validated_jd.get("top_keywords", []))
            )

            return ExtractionResult(
                job_id=job_id,
                success=True,
                extracted_jd=validated_jd,
                error=None,
                model=self.model,
                duration_ms=duration_ms,
                extracted_at=start_time.isoformat()
            )

        except subprocess.TimeoutExpired:
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            error_msg = f"CLI timeout after {self.timeout}s"
            self._emit_log(job_id, "error", message=error_msg)
            return ExtractionResult(
                job_id=job_id,
                success=False,
                extracted_jd=None,
                error=error_msg,
                model=self.model,
                duration_ms=duration_ms,
                extracted_at=start_time.isoformat()
            )

        except ValueError as e:
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            error_msg = str(e)
            self._emit_log(job_id, "error", message=f"Validation error: {error_msg}")
            return ExtractionResult(
                job_id=job_id,
                success=False,
                extracted_jd=None,
                error=error_msg,
                model=self.model,
                duration_ms=duration_ms,
                extracted_at=start_time.isoformat()
            )

        except Exception as e:
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            error_msg = f"Unexpected error: {str(e)}"
            self._emit_log(job_id, "error", message=error_msg)
            return ExtractionResult(
                job_id=job_id,
                success=False,
                extracted_jd=None,
                error=error_msg,
                model=self.model,
                duration_ms=duration_ms,
                extracted_at=start_time.isoformat()
            )

    async def extract_batch(
        self,
        jobs: List[Dict[str, str]],
        max_concurrent: int = 3
    ) -> List[ExtractionResult]:
        """
        Extract multiple jobs with controlled concurrency.

        Designed for batch endpoint integration. Uses asyncio semaphore
        to limit concurrent CLI processes.

        Args:
            jobs: List of job dicts with keys: job_id, title, company, job_description
            max_concurrent: Maximum concurrent extractions (default 3)

        Returns:
            List of ExtractionResult in same order as input jobs
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def extract_with_limit(job: Dict[str, str]) -> ExtractionResult:
            async with semaphore:
                # Run sync extraction in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None,
                    lambda: self.extract(
                        job["job_id"],
                        job["title"],
                        job["company"],
                        job["job_description"]
                    )
                )

        tasks = [extract_with_limit(job) for job in jobs]
        return await asyncio.gather(*tasks)

    def check_cli_available(self) -> bool:
        """
        Check if Claude CLI is installed and authenticated.

        Useful for health checks and graceful degradation.
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


# Convenience function for quick extraction
def extract_jd_with_claude(
    job_id: str,
    title: str,
    company: str,
    job_description: str,
    model: Optional[str] = None
) -> ExtractionResult:
    """
    Convenience function for single JD extraction with Claude.

    Args:
        job_id: MongoDB job ID
        title: Job title
        company: Company name
        job_description: Full job description text
        model: Optional model override

    Returns:
        ExtractionResult with extraction outcome
    """
    extractor = ClaudeJDExtractor(model=model)
    return extractor.extract(job_id, title, company, job_description)
