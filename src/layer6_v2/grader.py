"""
CV Grader (Phase 6).

Multi-dimensional CV grading system that evaluates the generated CV
across 5 key dimensions with weighted scoring.

Grading Dimensions:
- ATS Optimization (20%): Keyword coverage, format, parsability
- Impact & Clarity (25%): Metrics, action verbs, specificity
- JD Alignment (25%): Pain point coverage, role match, terminology
- Executive Presence (15%): Strategic framing, leadership evidence
- Anti-Hallucination (15%): Factual accuracy, grounding in source

Usage:
    grader = CVGrader()
    result = grader.grade(cv_text, extracted_jd, master_cv_text)
"""

import logging
import re
from typing import TYPE_CHECKING, List, Dict, Set, Optional, Tuple, Callable, Any
from collections import Counter

if TYPE_CHECKING:
    from src.common.structured_logger import StructuredLogger

from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log, retry_if_exception_type

from src.common.logger import get_logger
from src.common.config import Config
from src.common.unified_llm import UnifiedLLM
from src.common.utils import coerce_to_list
from src.layer6_v2.types import (
    DimensionScore,
    GradeResult,
)

# Module-level logger for retry decorator (instance logger not available at class definition time)
logger = logging.getLogger(__name__)


# Pydantic models for structured LLM grading output
class DimensionGrade(BaseModel):
    """Single dimension grade from LLM."""
    score: float = Field(ge=1, le=10, description="Score 1-10")
    feedback: str = Field(description="Specific feedback")
    issues: List[str] = Field(default_factory=list, description="Issues found")
    strengths: List[str] = Field(default_factory=list, description="Strengths")


class GradingResponse(BaseModel):
    """Complete grading response from LLM."""
    ats_optimization: DimensionGrade
    impact_clarity: DimensionGrade
    jd_alignment: DimensionGrade
    executive_presence: DimensionGrade
    anti_hallucination: DimensionGrade
    exemplary_sections: List[str] = Field(default_factory=list)


class CVGrader:
    """
    Multi-dimensional CV grading system.

    Evaluates CV quality across 5 dimensions with configurable weights.
    Uses both rule-based checks and LLM evaluation for comprehensive grading.
    """

    # Dimension weights (must sum to 1.0)
    DIMENSION_WEIGHTS = {
        "ats_optimization": 0.20,
        "impact_clarity": 0.25,
        "jd_alignment": 0.25,
        "executive_presence": 0.15,
        "anti_hallucination": 0.15,
    }

    # Strong action verbs for impact scoring
    STRONG_ACTION_VERBS = {
        "led", "built", "designed", "architected", "scaled", "transformed",
        "launched", "delivered", "drove", "established", "optimized", "reduced",
        "increased", "improved", "automated", "implemented", "created", "developed",
        "managed", "mentored", "hired", "coached", "negotiated", "secured",
    }

    def __init__(
        self,
        model: Optional[str] = None,
        passing_threshold: float = 8.5,
        use_llm_grading: bool = True,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[str, str, Dict[str, Any]], None]] = None,
        struct_logger: Optional["StructuredLogger"] = None,  # Phase 0 Extension
        log_callback: Optional[Callable[[str], None]] = None,  # Phase 0 Extension: In-process logging
    ):
        """
        Initialize the grader.

        Args:
            model: LLM model to use (default: from step config)
            passing_threshold: Score threshold for passing (default: 8.5)
            use_llm_grading: Whether to use LLM for grading (default: True)
            job_id: Job ID for tracking (optional)
            progress_callback: Optional callback for granular LLM progress events to Redis
            struct_logger: Optional StructuredLogger for Redis live-tail debugging (Phase 0 Extension)
            log_callback: Optional callback for in-process logging (Phase 0 Extension)
        """
        self._logger = get_logger(__name__)
        self.passing_threshold = passing_threshold
        self.use_llm_grading = use_llm_grading
        self._job_id = job_id or "unknown"
        self._progress_callback = progress_callback
        self._struct_logger = struct_logger  # Phase 0 Extension
        self._log_callback = log_callback  # Phase 0 Extension: In-process logging

        # Use UnifiedLLM with step config (low tier for grader)
        self._llm = UnifiedLLM(
            step_name="grader",
            job_id=self._job_id,
            progress_callback=progress_callback,
        )
        self._logger.info(
            f"CVGrader initialized with UnifiedLLM (step=grader, tier={self._llm.config.tier})"
        )

    def _emit_struct_log(self, event: str, metadata: dict) -> None:
        """
        Emit structured log event for Redis live-tail debugging (Phase 0 Extension).

        Emits through BOTH log_callback (in-process) and struct_logger (subprocess).
        """
        # Emit via log_callback (works in-process for CVGenerationService)
        if self._log_callback:
            try:
                import json
                from datetime import datetime
                data = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "layer": 6,
                    "layer_name": "cv_grader",
                    "event": f"cv_struct_{event}",
                    "message": metadata.get("message", event),
                    "job_id": self._job_id,
                    "metadata": metadata,
                }
                self._log_callback(json.dumps(data))
            except Exception:
                pass  # Fire-and-forget

        # Also emit via struct_logger stdout (works in subprocess mode)
        if self._struct_logger:
            try:
                self._struct_logger.emit(
                    event=event,
                    layer=6,
                    layer_name="cv_grader",
                    metadata=metadata,
                )
            except Exception:
                pass  # Fire-and-forget - never break grading for logging

    def _count_keywords(self, text: str, keywords: List[str]) -> Tuple[int, List[str]]:
        """Count how many keywords appear in text."""
        text_lower = text.lower()
        found = []
        for kw in keywords:
            if kw.lower() in text_lower:
                found.append(kw)
        return len(found), found

    def _count_metrics(self, text: str) -> int:
        """Count quantified metrics in text."""
        # Percentages
        percentages = len(re.findall(r'\d+(?:\.\d+)?%', text))
        # Numbers with context
        numbers = len(re.findall(r'\b\d+(?:,\d{3})*(?:\.\d+)?(?:x|X|M|K|B)?\b', text))
        # Dollar amounts
        dollars = len(re.findall(r'\$\d+(?:,\d{3})*(?:\.\d+)?(?:M|K|B)?', text))
        return percentages + numbers + dollars

    def _count_action_verbs(self, text: str) -> Tuple[int, List[str]]:
        """Count strong action verbs at start of bullets."""
        bullets = re.findall(r'[•\-\*]\s*(\w+)', text)
        found = []
        for word in bullets:
            if word.lower() in self.STRONG_ACTION_VERBS:
                found.append(word)
        return len(found), found

    def _check_keyword_front_loading(
        self,
        cv_text: str,
        jd_keywords: List[str],
    ) -> Tuple[float, int, int]:
        """
        Check if JD keywords appear in the first 3 words of bullets.

        This helps recruiters quickly match experience to requirements during
        their 6-7 second initial CV scan.

        Args:
            cv_text: The CV text to analyze
            jd_keywords: JD keywords to check for front-loading

        Returns:
            Tuple of (front_load_ratio, front_loaded_count, keyword_addressable_count)
        """
        if not jd_keywords:
            return 1.0, 0, 0  # No keywords to check

        jd_keywords_lower = {kw.lower() for kw in jd_keywords}

        # Extract bullets from CV
        bullets = re.findall(r'[•\-\*]\s*([^\n]+)', cv_text)

        front_loaded_count = 0
        keyword_addressable_count = 0

        for bullet in bullets:
            words = bullet.lower().split()
            first_three = ' '.join(words[:3]) if len(words) >= 3 else bullet.lower()
            full_bullet = bullet.lower()

            # Check if bullet contains any JD keyword
            has_keyword = any(kw in full_bullet for kw in jd_keywords_lower)

            if has_keyword:
                keyword_addressable_count += 1
                # Check if keyword is front-loaded (in first 3 words)
                if any(kw in first_three for kw in jd_keywords_lower):
                    front_loaded_count += 1

        if keyword_addressable_count == 0:
            return 1.0, 0, 0  # No keywords to front-load = perfect score

        ratio = front_loaded_count / keyword_addressable_count
        return ratio, front_loaded_count, keyword_addressable_count

    def _grade_ats_optimization(
        self,
        cv_text: str,
        jd_keywords: List[str],
    ) -> DimensionScore:
        """
        Grade ATS optimization (keyword coverage, format).

        Scoring:
        - 10+ keywords: 10 points
        - 8-9 keywords: 9 points
        - 6-7 keywords: 8 points
        - 4-5 keywords: 7 points
        - <4 keywords: 6 points or below
        """
        found_count, found_keywords = self._count_keywords(cv_text, jd_keywords)
        coverage_ratio = found_count / len(jd_keywords) if jd_keywords else 0

        # Calculate score based on coverage
        if coverage_ratio >= 0.67:  # 10+/15
            base_score = 10
        elif coverage_ratio >= 0.53:  # 8-9/15
            base_score = 9
        elif coverage_ratio >= 0.40:  # 6-7/15
            base_score = 8
        elif coverage_ratio >= 0.27:  # 4-5/15
            base_score = 7
        else:
            base_score = 5 + (coverage_ratio * 5)

        # Check format compliance
        has_sections = all(s in cv_text for s in ["Profile", "Experience", "Education"])
        has_bullets = "•" in cv_text or "-" in cv_text
        format_bonus = 0.5 if has_sections and has_bullets else 0

        # Check keyword front-loading (keywords in first 3 words of bullets)
        front_load_ratio, front_loaded, addressable = self._check_keyword_front_loading(
            cv_text, jd_keywords
        )
        # Apply bonus for good front-loading (0.5 point bonus if >50% front-loaded)
        front_load_bonus = 0.5 if front_load_ratio >= 0.5 else 0

        score = min(10, base_score + format_bonus + front_load_bonus)

        missing_keywords = [k for k in jd_keywords if k.lower() not in cv_text.lower()]

        # Build feedback with front-loading metrics
        front_load_info = f", {front_loaded}/{addressable} front-loaded ({front_load_ratio:.0%})" if addressable > 0 else ""

        # Build issues list
        issues = []
        if missing_keywords:
            issues.append(f"Missing keywords: {', '.join(missing_keywords[:5])}")
        if addressable > 0 and front_load_ratio < 0.5:
            issues.append(f"Low keyword front-loading: only {front_load_ratio:.0%} of keyword bullets have JD terms in first 3 words")

        return DimensionScore(
            dimension="ats_optimization",
            score=score,
            weight=self.DIMENSION_WEIGHTS["ats_optimization"],
            feedback=f"Found {found_count}/{len(jd_keywords)} keywords ({coverage_ratio:.0%} coverage){front_load_info}",
            issues=issues,
            strengths=[f"Found keywords: {', '.join(found_keywords[:5])}"] if found_keywords else [],
        )

    def _grade_impact_clarity(self, cv_text: str) -> DimensionScore:
        """
        Grade impact and clarity (metrics, action verbs, specificity).

        Scoring:
        - Metrics: 3 points max (1 per 5 metrics)
        - Action verbs: 3 points max (1 per 5 verbs)
        - Specificity: 4 points (based on bullet length and detail)
        """
        metrics_count = self._count_metrics(cv_text)
        verbs_count, found_verbs = self._count_action_verbs(cv_text)

        # Metrics score (max 3)
        metrics_score = min(3, metrics_count / 5)

        # Action verbs score (max 3)
        verbs_score = min(3, verbs_count / 5)

        # Specificity score based on average bullet length
        bullets = re.findall(r'[•\-\*]\s*([^\n]+)', cv_text)
        if bullets:
            avg_words = sum(len(b.split()) for b in bullets) / len(bullets)
            specificity_score = min(4, 1 + (avg_words / 10) * 3)
        else:
            specificity_score = 2

        score = metrics_score + verbs_score + specificity_score

        issues = []
        if metrics_count < 10:
            issues.append(f"Only {metrics_count} metrics found (aim for 10+)")
        if verbs_count < 10:
            issues.append(f"Only {verbs_count} strong action verbs (aim for 10+)")

        return DimensionScore(
            dimension="impact_clarity",
            score=score,
            weight=self.DIMENSION_WEIGHTS["impact_clarity"],
            feedback=f"{metrics_count} metrics, {verbs_count} action verbs",
            issues=issues,
            strengths=[f"Strong verbs used: {', '.join(list(set(found_verbs))[:5])}"] if found_verbs else [],
        )

    def _grade_jd_alignment(
        self,
        cv_text: str,
        extracted_jd: Dict,
    ) -> DimensionScore:
        """
        Grade JD alignment (pain points, role match, terminology).

        Scoring based on:
        - Pain point coverage (4 points)
        - Role category match (3 points)
        - JD terminology usage (3 points)
        """
        # Pain point coverage (use coerce_to_list for LLM output)
        pain_points = coerce_to_list(extracted_jd.get("implied_pain_points"))
        responsibilities = coerce_to_list(extracted_jd.get("responsibilities"))
        all_pain_areas = pain_points + responsibilities

        cv_lower = cv_text.lower()
        pain_coverage = sum(
            1 for p in all_pain_areas
            if any(word.lower() in cv_lower for word in p.split()[:3])
        )
        pain_score = min(4, (pain_coverage / max(1, len(all_pain_areas))) * 4)

        # Role category indicators
        role_category = extracted_jd.get("role_category", "")
        category_keywords = {
            "engineering_manager": ["team", "led", "managed", "hired", "mentored"],
            "staff_principal_engineer": ["architecture", "designed", "technical", "system"],
            "director_of_engineering": ["organization", "scaled", "strategy", "directors"],
            "head_of_engineering": ["built", "function", "executive", "transformation"],
            "cto": ["vision", "board", "technology", "business", "transformation"],
        }
        category_kws = category_keywords.get(role_category, [])
        category_match = sum(1 for kw in category_kws if kw in cv_lower)
        role_score = min(3, (category_match / max(1, len(category_kws))) * 3)

        # JD terminology (use coerce_to_list for LLM output)
        technical_skills = coerce_to_list(extracted_jd.get("technical_skills"))
        soft_skills = coerce_to_list(extracted_jd.get("soft_skills"))
        all_skills = technical_skills + soft_skills
        skills_found = sum(1 for s in all_skills if s.lower() in cv_lower)
        terminology_score = min(3, (skills_found / max(1, len(all_skills))) * 3)

        score = pain_score + role_score + terminology_score

        return DimensionScore(
            dimension="jd_alignment",
            score=score,
            weight=self.DIMENSION_WEIGHTS["jd_alignment"],
            feedback=f"Pain points: {pain_score:.1f}/4, Role match: {role_score:.1f}/3, Terminology: {terminology_score:.1f}/3",
            issues=[f"Consider addressing: {', '.join(pain_points[:3])}"] if pain_score < 3 else [],
            strengths=[f"Skills demonstrated: {', '.join([s for s in all_skills if s.lower() in cv_lower][:5])}"],
        )

    def _grade_executive_presence(
        self,
        cv_text: str,
        role_category: str,
    ) -> DimensionScore:
        """
        Grade executive presence (strategic framing, leadership evidence).

        Scoring based on:
        - Strategic language (4 points)
        - Leadership evidence (3 points)
        - Business outcomes (3 points)
        """
        cv_lower = cv_text.lower()

        # Strategic language
        strategic_terms = [
            "strategy", "strategic", "vision", "roadmap", "transformation",
            "initiative", "program", "portfolio", "stakeholder", "executive",
        ]
        strategic_count = sum(1 for t in strategic_terms if t in cv_lower)
        strategic_score = min(4, strategic_count / 2)

        # Leadership evidence
        leadership_terms = [
            "led", "managed", "team of", "engineers", "hired", "mentored",
            "coached", "scaled", "built team", "organization",
        ]
        leadership_count = sum(1 for t in leadership_terms if t in cv_lower)
        leadership_score = min(3, leadership_count / 3)

        # Business outcomes
        business_terms = [
            "revenue", "cost", "efficiency", "growth", "market", "customer",
            "retention", "acquisition", "profit", "savings", "$",
        ]
        business_count = sum(1 for t in business_terms if t in cv_lower)
        business_score = min(3, business_count / 2)

        score = strategic_score + leadership_score + business_score

        # Adjust based on role category expectations
        if role_category in ["cto", "head_of_engineering", "director_of_engineering"]:
            # Higher expectations for senior roles
            if score < 7:
                score = max(5, score - 1)  # Penalize slightly

        return DimensionScore(
            dimension="executive_presence",
            score=score,
            weight=self.DIMENSION_WEIGHTS["executive_presence"],
            feedback=f"Strategic: {strategic_score:.1f}/4, Leadership: {leadership_score:.1f}/3, Business: {business_score:.1f}/3",
            issues=["Add more strategic framing and business outcomes"] if score < 7 else [],
            strengths=["Strong executive positioning"] if score >= 8 else [],
        )

    def _grade_anti_hallucination(
        self,
        cv_text: str,
        master_cv_text: str,
    ) -> DimensionScore:
        """
        Grade anti-hallucination (factual accuracy, grounding).

        Scoring based on:
        - Metric preservation (5 points)
        - Company/role preservation (3 points)
        - No fabrication detected (2 points)
        """
        # Extract metrics from both texts
        cv_metrics = set(re.findall(r'\d+(?:\.\d+)?%', cv_text))
        master_metrics = set(re.findall(r'\d+(?:\.\d+)?%', master_cv_text))

        # Check metric preservation
        if cv_metrics:
            preserved_metrics = cv_metrics & master_metrics
            metric_score = (len(preserved_metrics) / len(cv_metrics)) * 5
        else:
            metric_score = 5  # No metrics to verify

        # Extract company names (simplified check)
        cv_lower = cv_text.lower()
        master_lower = master_cv_text.lower()

        # Check for suspicious additions (companies not in master)
        # This is a simplified heuristic
        fabrication_score = 2  # Start with full score
        suspicious_patterns = [
            r'founded\s+\w+',
            r'co-founder',
            r'startup\s+\w+',
        ]
        for pattern in suspicious_patterns:
            if re.search(pattern, cv_lower) and not re.search(pattern, master_lower):
                fabrication_score -= 0.5

        # Company preservation (simplified)
        company_score = 3  # Default full score

        score = metric_score + company_score + max(0, fabrication_score)

        issues = []
        if metric_score < 4:
            issues.append("Some metrics may not be from source")

        return DimensionScore(
            dimension="anti_hallucination",
            score=min(10, score),
            weight=self.DIMENSION_WEIGHTS["anti_hallucination"],
            feedback=f"Metric preservation: {metric_score:.1f}/5, Accuracy: {fabrication_score:.1f}/2",
            issues=issues,
            strengths=["Well-grounded in source material"] if score >= 9 else [],
        )

    def _create_retry_callback(self):
        """Create a retry callback that emits to struct_logger for frontend visibility."""
        def before_retry(retry_state):
            # Log to Python logger
            logger.warning(
                f"Grading retry attempt {retry_state.attempt_number} after error: "
                f"{retry_state.outcome.exception() if retry_state.outcome else 'unknown'}"
            )
            # Emit to struct_logger for frontend visibility
            self._emit_struct_log("retry_attempt", {
                "message": f"⚠️ Grading retry attempt {retry_state.attempt_number}",
                "attempt": retry_state.attempt_number,
                "error": str(retry_state.outcome.exception()) if retry_state.outcome else "unknown",
                "wait_seconds": retry_state.next_action.sleep if hasattr(retry_state.next_action, 'sleep') else 0,
            })
        return before_retry

    async def _grade_with_llm(
        self,
        cv_text: str,
        extracted_jd: Dict,
        master_cv_text: str,
    ) -> GradingResponse:
        """
        Grade CV using LLM for nuanced evaluation.

        Uses tenacity retry with exponential backoff.
        Falls back to rule-based if LLM fails after retries.
        """
        # Create retry decorator with struct_logger callback
        retry_decorator = retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            before_sleep=self._create_retry_callback(),
            reraise=True,
        )

        @retry_decorator
        async def _do_grade():
            return await self._grade_with_llm_inner(cv_text, extracted_jd, master_cv_text)

        return await _do_grade()

    async def _grade_with_llm_inner(
        self,
        cv_text: str,
        extracted_jd: Dict,
        master_cv_text: str,
    ) -> GradingResponse:
        """Inner grading logic (wrapped by retry)."""
        system_prompt = """You are an expert CV grader. Grade this CV on 5 dimensions (1-10 each).

DIMENSION 1: ATS OPTIMIZATION (weight: 20%)
- Keyword coverage: Do JD keywords appear naturally?
- Keyword front-loading: Are JD keywords in first 3 words of bullets?
- Format compliance: Standard headers, clean structure?
- Parsability: Would ATS extract sections correctly?

DIMENSION 2: IMPACT & CLARITY (weight: 25%)
- Metrics presence: Does every bullet have quantified outcome?
- Action verbs: Strong, varied, role-appropriate?
- Specificity: Concrete achievements, not vague?

DIMENSION 3: JD ALIGNMENT (weight: 25%)
- Pain point coverage: Does CV address implied pain points?
- Role category match: Emphasis matches IC vs leadership?
- Terminology: CV mirrors JD language?

DIMENSION 4: EXECUTIVE PRESENCE (weight: 15%)
- Strategic framing: Business outcomes, not just tasks?
- Leadership evidence: Progression, team impact?
- Board-ready language: Appropriate for senior stakeholders?

DIMENSION 5: ANTI-HALLUCINATION (weight: 15%)
- Factual accuracy: All claims verifiable from master CV?
- Metric preservation: Numbers exact, not inflated?
- No fabrication: No invented achievements?

Return JSON matching the GradingResponse schema exactly with these fields:
- ats_optimization: {score, feedback, issues, strengths}
- impact_clarity: {score, feedback, issues, strengths}
- jd_alignment: {score, feedback, issues, strengths}
- executive_presence: {score, feedback, issues, strengths}
- anti_hallucination: {score, feedback, issues, strengths}
- exemplary_sections: []"""

        user_prompt = f"""Grade this CV:

=== CV TEXT ===
{cv_text[:3000]}

=== JD KEYWORDS ===
{', '.join(extracted_jd.get('top_keywords', [])[:15])}

=== ROLE CATEGORY ===
{extracted_jd.get('role_category', 'engineering_manager')}

=== MASTER CV (for anti-hallucination check) ===
{master_cv_text[:2000]}

Grade each dimension 1-10 with specific feedback."""

        # Use UnifiedLLM with JSON validation
        result = await self._llm.invoke(
            prompt=user_prompt,
            system=system_prompt,
            validate_json=True,
        )

        if not result.success:
            error_msg = f"LLM grading failed: {result.error}"
            self._emit_struct_log("grading_error", {
                "message": f"❌ {error_msg}",
                "error_type": "llm_failure",
                "error": str(result.error),
                "content_preview": result.content[:200] if result.content else None,
            })
            raise ValueError(error_msg)

        if not result.parsed_json:
            # Log the raw content that couldn't be parsed
            content_preview = result.content[:500] if result.content else "empty"
            error_msg = "LLM response was not valid JSON"
            self._emit_struct_log("grading_error", {
                "message": f"❌ {error_msg}",
                "error_type": "json_parse_failure",
                "content_preview": content_preview,
                "content_length": len(result.content) if result.content else 0,
            })
            raise ValueError(error_msg)

        # Parse into Pydantic model with error logging
        try:
            grading_response = GradingResponse(**result.parsed_json)
            # Log successful parse
            self._emit_struct_log("grading_parsed", {
                "message": "✅ Grading response parsed successfully",
                "dimensions_parsed": list(result.parsed_json.keys()),
            })
            return grading_response
        except Exception as e:
            # Log validation error details to BOTH loggers for visibility
            keys_in_response = list(result.parsed_json.keys()) if result.parsed_json else []
            self._logger.error(
                f"Pydantic validation failed: {e}\n"
                f"Keys in response: {keys_in_response}"
            )
            # Emit to struct_logger for frontend visibility
            self._emit_struct_log("grading_error", {
                "message": f"❌ Pydantic validation failed: {e}",
                "error_type": "pydantic_validation",
                "error": str(e),
                "keys_in_response": keys_in_response,
                "sample_values": {
                    k: str(v)[:100] for k, v in list(result.parsed_json.items())[:3]
                } if result.parsed_json else {},
            })
            raise ValueError(f"Grading response validation failed: {e}")

    async def grade(
        self,
        cv_text: str,
        extracted_jd: Dict,
        master_cv_text: str,
    ) -> GradeResult:
        """
        Grade a CV across all dimensions.

        Args:
            cv_text: The CV text to grade
            extracted_jd: Extracted JD intelligence
            master_cv_text: Original master CV for hallucination check

        Returns:
            GradeResult with dimension scores and composite
        """
        self._logger.info("Grading CV across 5 dimensions...")

        jd_keywords = extracted_jd.get("top_keywords", [])
        role_category = extracted_jd.get("role_category", "engineering_manager")

        if self.use_llm_grading:
            try:
                llm_response = await self._grade_with_llm(cv_text, extracted_jd, master_cv_text)

                # Convert LLM response to DimensionScores
                dimension_scores = [
                    DimensionScore(
                        dimension="ats_optimization",
                        score=llm_response.ats_optimization.score,
                        weight=self.DIMENSION_WEIGHTS["ats_optimization"],
                        feedback=llm_response.ats_optimization.feedback,
                        issues=llm_response.ats_optimization.issues,
                        strengths=llm_response.ats_optimization.strengths,
                    ),
                    DimensionScore(
                        dimension="impact_clarity",
                        score=llm_response.impact_clarity.score,
                        weight=self.DIMENSION_WEIGHTS["impact_clarity"],
                        feedback=llm_response.impact_clarity.feedback,
                        issues=llm_response.impact_clarity.issues,
                        strengths=llm_response.impact_clarity.strengths,
                    ),
                    DimensionScore(
                        dimension="jd_alignment",
                        score=llm_response.jd_alignment.score,
                        weight=self.DIMENSION_WEIGHTS["jd_alignment"],
                        feedback=llm_response.jd_alignment.feedback,
                        issues=llm_response.jd_alignment.issues,
                        strengths=llm_response.jd_alignment.strengths,
                    ),
                    DimensionScore(
                        dimension="executive_presence",
                        score=llm_response.executive_presence.score,
                        weight=self.DIMENSION_WEIGHTS["executive_presence"],
                        feedback=llm_response.executive_presence.feedback,
                        issues=llm_response.executive_presence.issues,
                        strengths=llm_response.executive_presence.strengths,
                    ),
                    DimensionScore(
                        dimension="anti_hallucination",
                        score=llm_response.anti_hallucination.score,
                        weight=self.DIMENSION_WEIGHTS["anti_hallucination"],
                        feedback=llm_response.anti_hallucination.feedback,
                        issues=llm_response.anti_hallucination.issues,
                        strengths=llm_response.anti_hallucination.strengths,
                    ),
                ]

                exemplary = llm_response.exemplary_sections

            except Exception as e:
                self._logger.warning(f"LLM grading failed: {e}. Using rule-based grading.")
                dimension_scores, exemplary = self._grade_rule_based(
                    cv_text, extracted_jd, master_cv_text
                )
        else:
            dimension_scores, exemplary = self._grade_rule_based(
                cv_text, extracted_jd, master_cv_text
            )

        # Build GradeResult
        result = GradeResult(
            dimension_scores=dimension_scores,
            passing_threshold=self.passing_threshold,
            exemplary_sections=exemplary,
        )

        # Log results
        self._logger.info(f"Grading complete:")
        self._logger.info(f"  Composite score: {result.composite_score:.2f}/10")
        self._logger.info(f"  Passed: {result.passed}")
        self._logger.info(f"  Lowest dimension: {result.lowest_dimension}")
        for dim in result.dimension_scores:
            self._logger.info(f"  - {dim.dimension}: {dim.score:.1f}/10")

        # Phase 0 Extension: Log comprehensive grading decision point
        self._emit_struct_log("decision_point", {
            "decision": "cv_grade",
            "composite_score": round(result.composite_score, 2),
            "passed": result.passed,
            "threshold": self.passing_threshold,
            "grading_method": "llm" if self.use_llm_grading else "rule_based",
            "dimensions": {
                dim.dimension: {
                    "score": round(dim.score, 2),
                    "weight": round(dim.weight, 2),
                    "weighted_score": round(dim.score * dim.weight, 2),
                    "issues_count": len(dim.issues) if dim.issues else 0,
                    "issues": dim.issues[:3] if dim.issues else [],  # Top 3 issues
                    "strengths_count": len(dim.strengths) if dim.strengths else 0,
                    "strengths": dim.strengths[:3] if dim.strengths else [],  # Top 3 strengths
                }
                for dim in result.dimension_scores
            },
            "lowest_dimension": result.lowest_dimension,
            "highest_dimension": max(result.dimension_scores, key=lambda d: d.score).dimension if result.dimension_scores else None,
            "improvement_needed": not result.passed,
            "exemplary_sections_count": len(result.exemplary_sections) if result.exemplary_sections else 0,
        })

        return result

    def _grade_rule_based(
        self,
        cv_text: str,
        extracted_jd: Dict,
        master_cv_text: str,
    ) -> Tuple[List[DimensionScore], List[str]]:
        """Fallback rule-based grading."""
        jd_keywords = extracted_jd.get("top_keywords", [])
        role_category = extracted_jd.get("role_category", "engineering_manager")

        dimension_scores = [
            self._grade_ats_optimization(cv_text, jd_keywords),
            self._grade_impact_clarity(cv_text),
            self._grade_jd_alignment(cv_text, extracted_jd),
            self._grade_executive_presence(cv_text, role_category),
            self._grade_anti_hallucination(cv_text, master_cv_text),
        ]

        exemplary = []
        for dim in dimension_scores:
            if dim.score >= 9:
                exemplary.append(f"{dim.dimension} is excellent")

        return dimension_scores, exemplary


async def grade_cv(
    cv_text: str,
    extracted_jd: Dict,
    master_cv_text: str,
    passing_threshold: float = 8.5,
    job_id: Optional[str] = None,
    progress_callback: Optional[Callable[[str, str, Dict[str, Any]], None]] = None,
    struct_logger: Optional["StructuredLogger"] = None,  # Phase 0 Extension
    log_callback: Optional[Callable[[str], None]] = None,  # Phase 0 Extension: In-process logging
) -> GradeResult:
    """
    Convenience function to grade a CV.

    Args:
        cv_text: The CV text to grade
        extracted_jd: Extracted JD intelligence
        master_cv_text: Original master CV for hallucination check
        passing_threshold: Score threshold for passing
        job_id: Job ID for tracking (optional)
        progress_callback: Optional callback for granular LLM progress events to Redis
        struct_logger: Optional StructuredLogger for Redis live-tail debugging (Phase 0 Extension)
        log_callback: Optional callback for in-process logging (Phase 0 Extension)

    Returns:
        GradeResult with dimension scores and composite
    """
    grader = CVGrader(
        passing_threshold=passing_threshold,
        job_id=job_id,
        progress_callback=progress_callback,
        struct_logger=struct_logger,  # Phase 0 Extension
        log_callback=log_callback,  # Phase 0 Extension: In-process logging
    )
    return await grader.grade(cv_text, extracted_jd, master_cv_text)
