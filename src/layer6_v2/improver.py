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

import json
import re
from datetime import datetime
from typing import List, Dict, Optional, Callable, Any, TYPE_CHECKING

from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential, RetryCallState

from src.common.logger import get_logger
from src.common.config import Config
from src.common.unified_llm import UnifiedLLM
from src.layer6_v2.types import (
    GradeResult,
    ImprovementResult,
)

if TYPE_CHECKING:
    from src.common.structured_logger import StructuredLogger


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
        struct_logger: Optional["StructuredLogger"] = None,  # Phase 0 Extension
        log_callback: Optional[Callable[[str], None]] = None,  # Phase 0 Extension: In-process logging
    ):
        """
        Initialize the improver.

        Args:
            model: LLM model to use (default: from step config)
            temperature: Temperature for improvement (default: 0.3)
            job_id: Job ID for tracking (optional)
            progress_callback: Optional callback for granular LLM progress events to Redis
            struct_logger: Optional StructuredLogger for Redis live-tail debugging (Phase 0 Extension)
            log_callback: Optional callback for in-process logging (Phase 0 Extension)
        """
        self._logger = get_logger(__name__)
        self.temperature = temperature
        self._job_id = job_id or "unknown"
        self._progress_callback = progress_callback
        self._struct_logger = struct_logger  # Phase 0 Extension
        self._log_callback = log_callback  # Phase 0 Extension: In-process logging
        self._retry_count = 0  # Track retry attempts for logging

        # Use UnifiedLLM with step config (high tier for improver)
        self._llm = UnifiedLLM(
            step_name="improver",
            job_id=self._job_id,
            progress_callback=progress_callback,
        )
        self._logger.info(
            f"CVImprover initialized with UnifiedLLM (step=improver, tier={self._llm.config.tier})"
        )

    def _emit_struct_log(self, event: str, metadata: dict) -> None:
        """
        Emit structured log event for Redis live-tail debugging (Phase 0 Extension).

        Emits through BOTH log_callback (in-process) and struct_logger (subprocess).
        """
        # Emit via log_callback (works in-process for CVGenerationService)
        if self._log_callback:
            try:
                data = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "layer": 6,
                    "layer_name": "cv_improver",
                    "event": f"cv_struct_{event}",
                    "message": metadata.get("message", event),
                    "job_id": self._job_id,
                    "metadata": metadata,
                }
                self._log_callback(json.dumps(data))
            except Exception as e:
                self._logger.warning(f"Failed to emit struct log via log_callback: {e}")

        # Also emit via struct_logger (works for subprocess runs)
        if self._struct_logger:
            try:
                self._struct_logger.emit(
                    event=event,
                    layer=6,
                    metadata={
                        "component": "cv_improver",
                        **metadata,
                    }
                )
            except Exception as e:
                self._logger.warning(f"Failed to emit struct log via struct_logger: {e}")

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

    def _preview_text(self, text: str, max_chars: int = 100) -> str:
        """Generate a preview of text for logging."""
        if not text:
            return ""
        if len(text) <= max_chars:
            return text
        return f"{text[:max_chars//2]}...{text[-max_chars//2:]}"

    def _on_retry(self, retry_state: RetryCallState) -> None:
        """Log retry attempts for transparency."""
        self._retry_count = retry_state.attempt_number
        self._emit_struct_log("retry_attempt", {
            "message": f"⚠️ Improvement LLM retry attempt {retry_state.attempt_number}",
            "attempt_number": retry_state.attempt_number,
            "wait_time": retry_state.next_action.sleep if retry_state.next_action else 0,
            "exception": str(retry_state.outcome.exception()) if retry_state.outcome and retry_state.outcome.exception() else None,
        })

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=lambda retry_state: None,  # Placeholder, handled in method
    )
    async def _call_improvement_llm(
        self,
        cv_text: str,
        grade_result: GradeResult,
        extracted_jd: Dict,
        target_dimension: str,
    ) -> ImprovementResponse:
        """Call LLM for CV improvement with comprehensive logging."""

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

        # Get the strategy being applied
        strategy = self.IMPROVEMENT_STRATEGIES.get(target_dimension, {})
        tactics = strategy.get("tactics", [])

        # Phase 0 Extension: Log LLM call start with FULL prompt details
        self._emit_struct_log("llm_call_start", {
            "message": f"🔄 Calling improvement LLM for {target_dimension}",
            "target_dimension": target_dimension,
            "strategy_focus": strategy.get("focus", "general"),
            "tactics_applied": tactics,
            "system_prompt_preview": self._preview_text(system_prompt, 200),
            "system_prompt_length": len(system_prompt),
            "user_prompt_preview": self._preview_text(user_prompt, 300),
            "user_prompt_length": len(user_prompt),
            "cv_text_length": len(cv_text),
            "issues_to_fix": grade_result.get_dimension(target_dimension).issues[:5] if grade_result.get_dimension(target_dimension) else [],
            "jd_keywords_available": extracted_jd.get("top_keywords", [])[:10],
            "pain_points_targeted": extracted_jd.get("implied_pain_points", [])[:5],
            "retry_attempt": self._retry_count + 1,
        })

        # Use UnifiedLLM with JSON validation
        result = await self._llm.invoke(
            prompt=user_prompt,
            system=system_prompt,
            validate_json=True,
        )

        if not result.success:
            # Log failure
            self._emit_struct_log("llm_call_error", {
                "message": f"❌ Improvement LLM failed: {result.error}",
                "error": result.error,
                "target_dimension": target_dimension,
            })
            raise ValueError(f"LLM improvement failed: {result.error}")

        if not result.parsed_json:
            # Log JSON parse failure
            self._emit_struct_log("llm_call_error", {
                "message": "❌ LLM response was not valid JSON",
                "error": "json_parse_failure",
                "content_preview": self._preview_text(result.content or "", 200),
            })
            raise ValueError("LLM response was not valid JSON")

        # Parse into Pydantic model
        try:
            response = ImprovementResponse(**result.parsed_json)
        except Exception as e:
            self._emit_struct_log("llm_call_error", {
                "message": f"❌ Pydantic validation failed: {e}",
                "error": str(e),
                "keys_in_response": list(result.parsed_json.keys()) if result.parsed_json else [],
            })
            raise ValueError(f"Response validation failed: {e}")

        # Phase 0 Extension: Log LLM call completion with FULL result details
        self._emit_struct_log("llm_call_complete", {
            "message": f"✅ Improvement complete for {target_dimension}",
            "target_dimension": target_dimension,
            "changes_made_count": len(response.changes_made),
            "changes_made": response.changes_made,  # Full list of changes
            "improvement_summary": response.improvement_summary,
            "improved_cv_length": len(response.improved_cv),
            "improved_cv_preview": self._preview_text(response.improved_cv, 300),
            "cv_length_delta": len(response.improved_cv) - len(cv_text),
        })

        return response

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

        # Reset retry counter for this improvement cycle
        self._retry_count = 0

        # Phase 0 Extension: Log improvement start with ALL dimensions analysis
        all_dimensions = {}
        for dim in grade_result.dimension_scores if hasattr(grade_result, 'dimension_scores') else []:
            dim_name = dim.dimension if hasattr(dim, 'dimension') else str(dim)
            all_dimensions[dim_name] = {
                "score": dim.score if hasattr(dim, 'score') else 0,
                "weight": dim.weight if hasattr(dim, 'weight') else 0,
                "issues_count": len(dim.issues) if hasattr(dim, 'issues') and dim.issues else 0,
                "issues": dim.issues[:3] if hasattr(dim, 'issues') and dim.issues else [],
                "strengths_count": len(dim.strengths) if hasattr(dim, 'strengths') and dim.strengths else 0,
            }

        # Log all available strategies for transparency
        all_strategies = {
            dim: {
                "focus": strategy.get("focus", "general"),
                "tactics_count": len(strategy.get("tactics", [])),
                "tactics": strategy.get("tactics", []),
            }
            for dim, strategy in self.IMPROVEMENT_STRATEGIES.items()
        }

        self._emit_struct_log("improvement_start", {
            "message": f"🔧 Starting CV improvement - analyzing {len(all_dimensions)} dimensions",
            "composite_score": grade_result.composite_score,
            "passed": grade_result.passed,
            "all_dimensions": all_dimensions,
            "all_strategies_available": all_strategies,
            "cv_text_length": len(cv_text),
        })

        # Check if improvement is needed
        if grade_result.passed:
            self._logger.info(f"CV passed with {grade_result.composite_score:.2f}/10. No improvement needed.")
            self._emit_struct_log("improvement_skipped", {
                "message": f"✅ CV passed ({grade_result.composite_score:.1f}/10) - no improvement needed",
                "composite_score": grade_result.composite_score,
                "reason": "passed_threshold",
            })
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

        # Phase 0 Extension: Log dimension targeting decision with all competing dimensions
        dimension_ranking = sorted(
            all_dimensions.items(),
            key=lambda x: x[1]["score"]
        )
        self._emit_struct_log("decision_point", {
            "message": f"🎯 Targeting lowest dimension: {target_dimension} ({original_score}/10)",
            "decision": "dimension_targeting",
            "target_dimension": target_dimension,
            "target_score": original_score,
            "target_issues": target_score.issues if target_score else [],
            "dimension_ranking": [
                {"dimension": dim, "score": data["score"], "issues_count": data["issues_count"]}
                for dim, data in dimension_ranking
            ],
            "strategy_to_apply": self.IMPROVEMENT_STRATEGIES.get(target_dimension, {}),
            "why_selected": f"Lowest scoring dimension at {original_score}/10",
        })

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

            # Phase 0 Extension: Log improvement result
            self._emit_struct_log("improvement_complete", {
                "message": f"✅ Improvement applied to {target_dimension}",
                "target_dimension": target_dimension,
                "original_score": original_score,
                "changes_made_count": len(response.changes_made),
                "changes_made": response.changes_made,
                "improvement_summary": response.improvement_summary,
                "cv_length_before": len(cv_text),
                "cv_length_after": len(response.improved_cv),
                "retries_used": self._retry_count,
            })

        except Exception as e:
            self._logger.error(f"LLM improvement failed: {e}")
            # Phase 0 Extension: Log improvement failure
            self._emit_struct_log("improvement_failed", {
                "message": f"❌ Improvement failed: {e}",
                "target_dimension": target_dimension,
                "original_score": original_score,
                "error": str(e),
                "retries_used": self._retry_count,
            })
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
    struct_logger: Optional["StructuredLogger"] = None,  # Phase 0 Extension
    log_callback: Optional[Callable[[str], None]] = None,  # Phase 0 Extension: In-process logging
) -> ImprovementResult:
    """
    Convenience function to improve a CV.

    Args:
        cv_text: The CV text to improve
        grade_result: Grading result from CVGrader
        extracted_jd: Extracted JD intelligence
        job_id: Job ID for tracking (optional)
        progress_callback: Optional callback for granular LLM progress events to Redis
        struct_logger: Optional StructuredLogger for Redis live-tail debugging (Phase 0 Extension)
        log_callback: Optional callback for in-process logging (Phase 0 Extension)

    Returns:
        ImprovementResult with improved CV
    """
    improver = CVImprover(
        job_id=job_id,
        progress_callback=progress_callback,
        struct_logger=struct_logger,  # Phase 0 Extension
        log_callback=log_callback,  # Phase 0 Extension: In-process logging
    )
    return await improver.improve(cv_text, grade_result, extracted_jd)
