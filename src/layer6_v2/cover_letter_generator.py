"""
Cover Letter Generator (Phase 7 of CV Gen V2).

Generates hyper-personalized 3-paragraph cover letters using the rich
context already available after CV generation phases 1-6.

Uses Haiku tier for cost efficiency (~$0.005 per job).

Usage:
    generator = CoverLetterGenerator(job_id="abc123")
    cover_letter = generator.generate(
        job_title="Engineering Manager",
        company="Acme Corp",
        candidate_name="John Doe",
        cv_text=cv_text,
        extracted_jd=extracted_jd,
        pain_points=pain_points,
        company_research=company_research,
        fit_rationale=fit_rationale,
        persona_statement=persona_statement,
    )
"""

import logging
from typing import Any, Dict, List, Optional

from src.common.unified_llm import invoke_unified_sync
from src.layer6_v2.prompts.cover_letter_prompts import (
    COVER_LETTER_SYSTEM_PROMPT,
    build_cover_letter_user_prompt,
)

logger = logging.getLogger(__name__)


class CoverLetterGenerator:
    """
    Generates cover letters using pipeline context from V2 orchestrator.

    Runs as Phase 7 after CV generation is complete. Uses Haiku tier
    since cover letters are structured and templated.
    """

    def __init__(self, job_id: str = "unknown"):
        self._job_id = job_id

    def generate(
        self,
        job_title: str,
        company: str,
        candidate_name: str,
        cv_text: str,
        extracted_jd: Optional[Dict[str, Any]] = None,
        pain_points: Optional[List[str]] = None,
        company_research: Optional[Dict[str, Any]] = None,
        fit_rationale: Optional[str] = None,
        persona_statement: Optional[str] = None,
    ) -> Optional[str]:
        """
        Generate a cover letter using pipeline context.

        Args:
            job_title: Target job title
            company: Target company name
            candidate_name: Candidate's name
            cv_text: Generated CV text (source of truth for achievements)
            extracted_jd: Parsed JD intelligence
            pain_points: Company/role pain points
            company_research: Company research signals
            fit_rationale: Why candidate is a good fit
            persona_statement: Candidate's professional identity

        Returns:
            Cover letter text or None if generation fails
        """
        if not cv_text:
            logger.warning("No CV text available for cover letter generation")
            return None

        logger.info(f"Generating cover letter for {company} - {job_title}")

        user_prompt = build_cover_letter_user_prompt(
            job_title=job_title,
            company=company,
            candidate_name=candidate_name,
            cv_text=cv_text,
            extracted_jd=extracted_jd,
            pain_points=pain_points,
            company_research=company_research,
            fit_rationale=fit_rationale,
            persona_statement=persona_statement,
        )

        result = invoke_unified_sync(
            prompt=user_prompt,
            step_name="cover_letter_generation",
            system=COVER_LETTER_SYSTEM_PROMPT,
            job_id=self._job_id,
            validate_json=False,  # Cover letter is plain text
        )

        if result.success and result.content:
            cover_letter = result.content.strip()
            word_count = len(cover_letter.split())
            logger.info(f"Cover letter generated: {word_count} words")

            if word_count < 50:
                logger.warning(f"Cover letter too short ({word_count} words), discarding")
                return None

            return cover_letter

        logger.warning(f"Cover letter generation failed: {result.error}")
        return None
