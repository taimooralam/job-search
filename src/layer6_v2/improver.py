"""
CV Improver (Phase 6).

Single-pass CV improvement based on grading feedback.
Targets the lowest-scoring dimension for focused improvement.

Strategy (user choice: cost control):
1. Grade once
2. Identify lowest-scoring dimension
3. Apply targeted fixes for that dimension
4. Accept result (no re-grading loop)

Usage:
    improver = CVImprover()
    result = improver.improve(cv_text, grade_result, extracted_jd)
"""

import re
from typing import List, Dict, Optional, Callable, Any

from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.logger import get_logger
from src.common.config import Config
from src.common.unified_llm import UnifiedLLM
from src.layer6_v2.types import (
    GradeResult,
    ImprovementResult,
)


# Pydantic models for structured LLM improvement output
class ImprovementResponse(BaseModel):
    """Structured response for CV improvement."""
    improved_cv: str = Field(description="The improved CV text")
    changes_made: List[str] = Field(description="List of changes made")
    improvement_summary: str = Field(description="Brief summary of improvements")


class CVImprover:
    """
    Single-pass CV improvement based on grading feedback.

    Focuses improvement effort on the lowest-scoring dimension
    to maximize impact with minimal LLM calls (cost control).
    """

    # Dimension-specific improvement strategies
    # NOTE: Anti-hallucination fix - DO NOT add JD keywords unless candidate has evidence
    IMPROVEMENT_STRATEGIES = {
        "ats_optimization": {
            "focus": "Keyword integration and format",
            "tactics": [
                "Naturally integrate JD keywords ONLY if the candidate has evidence of that skill",
                "Ensure standard section headers (Profile, Experience, Education)",
                "Use consistent bullet formatting",
                "NEVER add skills the candidate doesn't have - only use skills already in the CV",
            ],
        },
        "impact_clarity": {
            "focus": "Metrics and action verbs",
            "tactics": [
                "Add quantified metrics to bullets lacking them",
                "Replace weak verbs with strong action verbs (Led, Built, Designed)",
                "Make vague statements specific with numbers/outcomes",
                "Ensure every bullet shows measurable impact",
            ],
        },
        "jd_alignment": {
            "focus": "Pain points and role match",
            "tactics": [
                "Reframe bullets to address JD pain points",
                "Adjust language to match role category (IC vs leadership)",
                "Mirror JD terminology where natural",
                "Emphasize experiences matching JD responsibilities",
            ],
        },
        "executive_presence": {
            "focus": "Strategic framing and business outcomes",
            "tactics": [
                "Elevate tactical descriptions to strategic impact",
                "Add business outcomes (revenue, efficiency, growth)",
                "Show leadership progression and team impact",
                "Use board-ready language for senior roles",
            ],
        },
        "anti_hallucination": {
            "focus": "Accuracy and grounding",
            "tactics": [
                "Remove or rephrase any unverifiable claims",
                "Ensure all metrics match source exactly",
                "Remove any fabricated achievements",
                "Clarify ambiguous statements with source-grounded details",
            ],
        },
    }

    def __init__(
        self,
        model: Optional[str] = None,
        temperature: float = 0.3,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[str, str, Dict[str, Any]], None]] = None,
    ):
        """
        Initialize the improver.

        Args:
            model: LLM model to use (default: from step config)
            temperature: Temperature for improvement (default: 0.3)
            job_id: Job ID for tracking (optional)
            progress_callback: Optional callback for granular LLM progress events to Redis
        """
        self._logger = get_logger(__name__)
        self.temperature = temperature
        self._job_id = job_id or "unknown"
        self._progress_callback = progress_callback

        # Use UnifiedLLM with step config (high tier for improver)
        self._llm = UnifiedLLM(
            step_name="improver",
            job_id=self._job_id,
            progress_callback=progress_callback,
        )
        self._logger.info(
            f"CVImprover initialized with UnifiedLLM (step=improver, tier={self._llm.config.tier})"
        )

    def _build_improvement_prompt(
        self,
        cv_text: str,
        grade_result: GradeResult,
        extracted_jd: Dict,
        target_dimension: str,
    ) -> str:
        """Build targeted improvement prompt for the lowest dimension."""

        strategy = self.IMPROVEMENT_STRATEGIES.get(target_dimension, {})
        focus = strategy.get("focus", "general quality")
        tactics = strategy.get("tactics", ["Improve overall quality"])

        # Get dimension-specific feedback
        dim_score = grade_result.get_dimension(target_dimension)
        issues = dim_score.issues if dim_score else []
        current_score = dim_score.score if dim_score else 0

        # JD context
        jd_keywords = extracted_jd.get("top_keywords", [])
        pain_points = extracted_jd.get("implied_pain_points", [])
        role_category = extracted_jd.get("role_category", "engineering_manager")

        return f"""Improve this CV to score higher on {target_dimension.replace('_', ' ').title()}.

CURRENT SCORE: {current_score}/10
TARGET: 9+/10

IMPROVEMENT FOCUS: {focus}

SPECIFIC ISSUES TO FIX:
{chr(10).join(f'- {issue}' for issue in issues) if issues else '- General improvement needed'}

IMPROVEMENT TACTICS:
{chr(10).join(f'- {tactic}' for tactic in tactics)}

JD KEYWORDS (for reference only - DO NOT add skills the candidate doesn't have):
{', '.join(jd_keywords[:10])}

PAIN POINTS TO ADDRESS:
{chr(10).join(f'- {pp}' for pp in pain_points[:5]) if pain_points else '- See JD for context'}

ROLE CATEGORY: {role_category}

=== CURRENT CV ===
{cv_text}

=== CRITICAL ANTI-HALLUCINATION RULES ===
1. Make MINIMAL changes - only fix the specific dimension issues
2. Preserve all accurate information and metrics
3. Do NOT add fabricated achievements or inflated numbers
4. NEVER add skills, technologies, or keywords that the candidate doesn't demonstrate in the CV
5. JD keywords should ONLY be used if the candidate already has that skill evidenced
6. Do NOT add new skills to the Skills sections that aren't already mentioned
7. Maintain the overall structure and flow
8. Natural language only - no keyword stuffing

Return the improved CV with changes highlighted in your summary."""

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _call_improvement_llm(
        self,
        cv_text: str,
        grade_result: GradeResult,
        extracted_jd: Dict,
        target_dimension: str,
    ) -> ImprovementResponse:
        """Call LLM for CV improvement."""

        system_prompt = """You are a CV improvement specialist.

Your mission: Make targeted improvements to a CV based on specific grading feedback.

PRINCIPLES:
1. MINIMAL CHANGES: Only fix what's broken, don't rewrite everything
2. PRESERVE ACCURACY: Never add fabricated information
3. NATURAL INTEGRATION: Keywords should flow naturally, not be stuffed
4. MAINTAIN STRUCTURE: Keep the CV's overall organization
5. RESPECT METRICS: All numbers must match the source exactly

CRITICAL ANTI-HALLUCINATION RULE:
- NEVER add skills, technologies, or languages that aren't already in the CV
- JD keywords like "Solidity", "Rust", "Go", "Java" should ONLY be used if the candidate already has them
- If a JD asks for a skill the candidate doesn't have, DO NOT add it
- The goal is to optimize existing content, NOT to fabricate new skills

QUALITY STANDARDS:
- Every bullet should have a quantified outcome
- Strong action verbs at the start of each bullet
- JD keywords naturally integrated ONLY if candidate has that skill
- Strategic framing for leadership roles
- No vague statements or filler content

Return JSON matching this ImprovementResponse schema:
{
  "improved_cv": "The improved CV text",
  "changes_made": ["List of specific changes made"],
  "improvement_summary": "Brief summary of improvements"
}"""

        user_prompt = self._build_improvement_prompt(
            cv_text, grade_result, extracted_jd, target_dimension
        )

        # Use UnifiedLLM with JSON validation
        result = await self._llm.invoke(
            prompt=user_prompt,
            system=system_prompt,
            validate_json=True,
        )

        if not result.success:
            raise ValueError(f"LLM improvement failed: {result.error}")

        if not result.parsed_json:
            raise ValueError("LLM response was not valid JSON")

        # Parse into Pydantic model
        return ImprovementResponse(**result.parsed_json)

    async def improve(
        self,
        cv_text: str,
        grade_result: GradeResult,
        extracted_jd: Dict,
    ) -> ImprovementResult:
        """
        Improve CV based on grading feedback (single pass).

        Args:
            cv_text: The CV text to improve
            grade_result: Grading result with dimension scores
            extracted_jd: Extracted JD intelligence

        Returns:
            ImprovementResult with improved CV and change log
        """
        self._logger.info("Starting single-pass CV improvement...")

        # Check if improvement is needed
        if grade_result.passed:
            self._logger.info(f"CV passed with {grade_result.composite_score:.2f}/10. No improvement needed.")
            return ImprovementResult(
                improved=False,
                target_dimension="",
                changes_made=[],
                original_score=grade_result.composite_score,
                cv_text=cv_text,
                improvement_summary="CV already meets quality threshold.",
            )

        # Target the lowest-scoring dimension
        target_dimension = grade_result.lowest_dimension
        target_score = grade_result.get_dimension(target_dimension)
        original_score = target_score.score if target_score else 0

        self._logger.info(f"Targeting {target_dimension} (score: {original_score}/10)")

        try:
            response = await self._call_improvement_llm(
                cv_text, grade_result, extracted_jd, target_dimension
            )

            result = ImprovementResult(
                improved=True,
                target_dimension=target_dimension,
                changes_made=response.changes_made,
                original_score=original_score,
                cv_text=response.improved_cv,
                improvement_summary=response.improvement_summary,
            )

            self._logger.info(f"Improvement complete:")
            self._logger.info(f"  Target: {target_dimension}")
            self._logger.info(f"  Changes: {len(response.changes_made)}")
            self._logger.info(f"  Summary: {response.improvement_summary[:100]}...")

        except Exception as e:
            self._logger.error(f"LLM improvement failed: {e}")
            result = ImprovementResult(
                improved=False,
                target_dimension=target_dimension,
                changes_made=[],
                original_score=original_score,
                cv_text=cv_text,
                improvement_summary=f"Improvement failed: {str(e)}",
            )

        return result

    async def improve_specific_dimension(
        self,
        cv_text: str,
        target_dimension: str,
        grade_result: GradeResult,
        extracted_jd: Dict,
    ) -> ImprovementResult:
        """
        Improve a specific dimension (for manual override).

        Args:
            cv_text: The CV text to improve
            target_dimension: Dimension to target
            grade_result: Grading result with dimension scores
            extracted_jd: Extracted JD intelligence

        Returns:
            ImprovementResult with improved CV
        """
        self._logger.info(f"Improving specific dimension: {target_dimension}")

        target_score = grade_result.get_dimension(target_dimension)
        original_score = target_score.score if target_score else 0

        try:
            response = await self._call_improvement_llm(
                cv_text, grade_result, extracted_jd, target_dimension
            )

            return ImprovementResult(
                improved=True,
                target_dimension=target_dimension,
                changes_made=response.changes_made,
                original_score=original_score,
                cv_text=response.improved_cv,
                improvement_summary=response.improvement_summary,
            )

        except Exception as e:
            self._logger.error(f"Improvement failed: {e}")
            return ImprovementResult(
                improved=False,
                target_dimension=target_dimension,
                changes_made=[],
                original_score=original_score,
                cv_text=cv_text,
                improvement_summary=f"Failed: {str(e)}",
            )


async def improve_cv(
    cv_text: str,
    grade_result: GradeResult,
    extracted_jd: Dict,
    job_id: Optional[str] = None,
    progress_callback: Optional[Callable[[str, str, Dict[str, Any]], None]] = None,
) -> ImprovementResult:
    """
    Convenience function to improve a CV.

    Args:
        cv_text: The CV text to improve
        grade_result: Grading result from CVGrader
        extracted_jd: Extracted JD intelligence
        job_id: Job ID for tracking (optional)
        progress_callback: Optional callback for granular LLM progress events to Redis

    Returns:
        ImprovementResult with improved CV
    """
    improver = CVImprover(job_id=job_id, progress_callback=progress_callback)
    return await improver.improve(cv_text, grade_result, extracted_jd)
