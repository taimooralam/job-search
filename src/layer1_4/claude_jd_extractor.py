"""
Layer 1.4: JD Extractor (Primary Extractor)

Primary JD extraction module using Claude Code CLI (headless mode).
Uses Claude Max subscription via CLI authentication for high-quality extraction.

Architecture: Batch-ready with logging hooks for future Redis live-tail.

Usage:
    # Single extraction
    extractor = JDExtractor(model="claude-opus-4-5-20251101")
    result = extractor.extract(job_id, title, company, job_description)

    # Batch extraction
    results = await extractor.extract_batch(jobs, max_concurrent=3)

    # With Redis logging (future)
    extractor = JDExtractor(log_callback=redis_publisher)
"""

import subprocess
import json
import logging
import asyncio
import os
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from src.common.state import ExtractedJD
from src.common.json_utils import parse_llm_json
from src.layer1_4.prompts import (
    JD_EXTRACTION_SYSTEM_PROMPT,
    JD_EXTRACTION_USER_TEMPLATE,
)


# ===== SCHEMA VALIDATION =====

class RoleCategory(str, Enum):
    """Role category classification for CV tailoring."""
    ENGINEERING_MANAGER = "engineering_manager"
    STAFF_PRINCIPAL_ENGINEER = "staff_principal_engineer"
    DIRECTOR_OF_ENGINEERING = "director_of_engineering"
    HEAD_OF_ENGINEERING = "head_of_engineering"
    VP_ENGINEERING = "vp_engineering"  # VP/SVP Engineering - exec + operational at scale
    CTO = "cto"
    TECH_LEAD = "tech_lead"  # Covers Team Lead, Tech Lead, Lead Engineer
    SENIOR_ENGINEER = "senior_engineer"  # Fallback for senior IC roles


class SeniorityLevel(str, Enum):
    """Seniority level classification."""
    SENIOR = "senior"
    STAFF = "staff"
    PRINCIPAL = "principal"
    DIRECTOR = "director"
    VP = "vp"
    C_LEVEL = "c_level"


class RemotePolicy(str, Enum):
    """Remote work policy classification."""
    FULLY_REMOTE = "fully_remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    NOT_SPECIFIED = "not_specified"


class CompetencyWeightsModel(BaseModel):
    """Competency weights with sum validation."""
    delivery: int = Field(..., ge=0, le=100, description="Shipping features, product execution")
    process: int = Field(..., ge=0, le=100, description="CI/CD, testing, quality standards")
    architecture: int = Field(..., ge=0, le=100, description="System design, technical strategy")
    leadership: int = Field(..., ge=0, le=100, description="People management, team building")

    @model_validator(mode='after')
    def validate_sum(self) -> 'CompetencyWeightsModel':
        """Ensure weights sum to exactly 100."""
        total = self.delivery + self.process + self.architecture + self.leadership
        if total != 100:
            raise ValueError(f"Competency weights must sum to 100, got {total}")
        return self


class ExtractedJDModel(BaseModel):
    """Pydantic model for JD extraction validation."""

    # Basic Info
    title: str = Field(..., min_length=3, description="Job title")
    company: str = Field(..., min_length=1, description="Company name")
    location: str = Field(default="Not specified", description="Location")
    remote_policy: RemotePolicy = Field(default=RemotePolicy.NOT_SPECIFIED)

    # Role Classification
    role_category: RoleCategory = Field(..., description="Role category for CV tailoring")
    seniority_level: SeniorityLevel = Field(..., description="Seniority level")

    # Competency Mix
    competency_weights: CompetencyWeightsModel = Field(..., description="Competency weights (sum=100)")

    # Content Extraction
    responsibilities: List[str] = Field(
        ..., min_length=3, max_length=15,
        description="Key responsibilities"
    )
    qualifications: List[str] = Field(
        ..., min_length=2, max_length=12,
        description="Required qualifications"
    )
    nice_to_haves: List[str] = Field(
        default_factory=list, max_length=10,
        description="Optional qualifications"
    )
    technical_skills: List[str] = Field(
        default_factory=list, max_length=20,
        description="Technical skills mentioned"
    )
    soft_skills: List[str] = Field(
        default_factory=list, max_length=10,
        description="Soft skills mentioned"
    )

    # Pain Points (inferred)
    implied_pain_points: List[str] = Field(
        default_factory=list, max_length=8,
        description="Inferred problems this hire solves"
    )
    success_metrics: List[str] = Field(
        default_factory=list, max_length=8,
        description="How success will be measured"
    )

    # ATS Keywords
    top_keywords: List[str] = Field(
        ..., min_length=10, max_length=20,
        description="Top 15 ATS keywords"
    )

    # Background Requirements
    industry_background: Optional[str] = Field(default=None)
    years_experience_required: Optional[int] = Field(default=None, ge=0, le=50)
    education_requirements: Optional[str] = Field(default=None)

    @field_validator('responsibilities', 'qualifications')
    @classmethod
    def validate_non_empty_strings(cls, v: List[str]) -> List[str]:
        """Ensure all items are non-empty strings."""
        return [item.strip() for item in v if item and item.strip()]

    @field_validator('top_keywords')
    @classmethod
    def validate_keywords(cls, v: List[str]) -> List[str]:
        """Deduplicate and clean keywords."""
        seen = set()
        result = []
        for kw in v:
            kw_clean = kw.strip().lower()
            if kw_clean and kw_clean not in seen:
                seen.add(kw_clean)
                result.append(kw.strip())
        return result

    def to_extracted_jd(self) -> ExtractedJD:
        """Convert to TypedDict for state."""
        return ExtractedJD(
            title=self.title,
            company=self.company,
            location=self.location,
            remote_policy=self.remote_policy.value,
            role_category=self.role_category.value,
            seniority_level=self.seniority_level.value,
            competency_weights={
                "delivery": self.competency_weights.delivery,
                "process": self.competency_weights.process,
                "architecture": self.competency_weights.architecture,
                "leadership": self.competency_weights.leadership,
            },
            responsibilities=self.responsibilities,
            qualifications=self.qualifications,
            nice_to_haves=self.nice_to_haves,
            technical_skills=self.technical_skills,
            soft_skills=self.soft_skills,
            implied_pain_points=self.implied_pain_points,
            success_metrics=self.success_metrics,
            top_keywords=self.top_keywords,
            industry_background=self.industry_background,
            years_experience_required=self.years_experience_required,
            education_requirements=self.education_requirements,
        )

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


class JDExtractor:
    """
    Primary JD extractor using Claude Code CLI (headless mode).

    Extracts structured intelligence from job descriptions including:
    - Role classification (EM, Staff, Director, Head, CTO)
    - Competency weights (delivery, process, architecture, leadership)
    - ATS keywords (top 15 for optimization)
    - Structured content (responsibilities, qualifications, skills)

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
        Initialize the JD extractor.

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

        # Defensive truncation: Claude Opus 4.5 extracts more thoroughly than GPT-4o,
        # so truncate lists to schema max_length before Pydantic validation
        list_limits = {
            "responsibilities": 15,
            "qualifications": 12,
            "nice_to_haves": 10,
            "technical_skills": 20,
            "soft_skills": 10,
            "implied_pain_points": 8,
            "success_metrics": 8,
            "top_keywords": 20,
        }
        for field, limit in list_limits.items():
            if field in data and isinstance(data[field], list) and len(data[field]) > limit:
                logger.debug(f"Truncating {field} from {len(data[field])} to {limit} items")
                data[field] = data[field][:limit]

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
def extract_jd(
    job_id: str,
    title: str,
    company: str,
    job_description: str,
    model: Optional[str] = None
) -> ExtractionResult:
    """
    Convenience function for single JD extraction.

    Args:
        job_id: MongoDB job ID
        title: Job title
        company: Company name
        job_description: Full job description text
        model: Optional model override

    Returns:
        ExtractionResult with extraction outcome
    """
    extractor = JDExtractor(model=model)
    return extractor.extract(job_id, title, company, job_description)


# Backwards compatibility alias
ClaudeJDExtractor = JDExtractor
extract_jd_with_claude = extract_jd


# ===== LANGGRAPH NODE FUNCTION =====

def jd_extractor_node(state: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    LangGraph node for JD extraction (Layer 1.4).

    Extracts structured intelligence from job descriptions using Claude Code CLI.
    This node bridges the JDExtractor class to LangGraph's JobState pattern.

    Args:
        state: Current pipeline state (JobState)
        config: Runtime configuration (RunnableConfig)

    Returns:
        Dict with state updates:
        - extracted_jd: ExtractedJD dict if successful, None on failure
        - errors: Updated error list if extraction fails
    """
    # 1. Extract inputs from state
    job_id = state.get("job_id", "")
    title = state.get("title", "")
    company = state.get("company", "")
    job_description = state.get("job_description", "")

    logger.info(f"[JDExtractor] Starting extraction for job_id={job_id}")

    # 2. Validate inputs
    if not job_description:
        error_msg = "Missing job_description in state"
        logger.warning(f"[JDExtractor] {error_msg}")
        return {
            "extracted_jd": None,
            "errors": state.get("errors", []) + [f"Layer 1.4: {error_msg}"],
        }

    # 3. Get tier config for model selection (if available)
    tier_config = state.get("tier_config")
    model = None
    if tier_config and tier_config.get("research_model"):
        # Use tier-configured model for extraction
        model = tier_config.get("research_model")
        logger.debug(f"[JDExtractor] Using tier model: {model}")

    # 4. Process with error handling
    try:
        extractor = JDExtractor(model=model)

        # Check CLI availability first
        if not extractor.check_cli_available():
            error_msg = "Claude CLI not available or not authenticated"
            logger.error(f"[JDExtractor] {error_msg}")
            return {
                "extracted_jd": None,
                "errors": state.get("errors", []) + [f"Layer 1.4: {error_msg}"],
            }

        # Run extraction (synchronous - CLI-based)
        result: ExtractionResult = extractor.extract(
            job_id=job_id,
            title=title,
            company=company,
            job_description=job_description,
        )

        # 5. Handle result
        if result.success and result.extracted_jd:
            logger.info(
                f"[JDExtractor] Extraction complete: "
                f"role_category={result.extracted_jd.get('role_category')}, "
                f"keywords={len(result.extracted_jd.get('top_keywords', []))}, "
                f"duration={result.duration_ms}ms"
            )
            return {
                "extracted_jd": result.extracted_jd,
            }
        else:
            error_msg = result.error or "Unknown extraction error"
            logger.warning(f"[JDExtractor] Extraction failed: {error_msg}")
            return {
                "extracted_jd": None,
                "errors": state.get("errors", []) + [f"Layer 1.4: {error_msg}"],
            }

    except Exception as e:
        error_msg = f"Unexpected error in JD extraction: {str(e)}"
        logger.error(f"[JDExtractor] {error_msg}", exc_info=True)
        return {
            "extracted_jd": None,
            "errors": state.get("errors", []) + [f"Layer 1.4: {error_msg}"],
        }
