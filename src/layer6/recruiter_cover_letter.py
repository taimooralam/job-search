"""
Layer 6b: Recruiter Cover Letter Generator

Generates cover letters specifically for recruitment agency jobs.
Key differences from standard cover letters:
- Shorter format (150-250 words)
- Focus on skills match and availability
- No company pain points/signals (irrelevant for agencies)
- Direct, professional tone

This is used when company_type == "recruitment_agency" in the pipeline.
"""

import logging
import re
from typing import List
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.config import Config
from src.common.unified_llm import invoke_unified_sync
from src.common.state import JobState


# ===== VALIDATION CONFIGURATION =====

GENERIC_BOILERPLATE_PHRASES = [
    "i am excited to apply",
    "dream job",
    "perfect fit for this role",
    "strong background",
    "team player",
    "hit the ground running",
    "ideal candidate",
    "passionate about"
]

METRIC_PATTERNS = [
    r'\d+%',
    r'\d+x',
    r'\d+X',
    r'\$\d+[KMB]',
    r'\d+\s+(min|hr|hour|day|week|month)',
    r'\d+[.,]\d+%',
]


# ===== PROMPTS =====

SYSTEM_PROMPT_RECRUITER = """You are writing a cover letter to a recruiter at a staffing/recruitment agency.

KEY CONTEXT:
- This recruiter is sourcing candidates for their CLIENT company (not their own company)
- They see hundreds of applications daily - be concise and direct
- They care about: skills match, availability, salary expectations (if known), immediate fit
- They DON'T care about: company signals, pain points, long-term vision (that's for the client)

TONE:
- Professional but direct
- Get to the point quickly
- Show you understand how agency recruiting works
- Make their job easier by clearly stating your fit

STRUCTURE (2-3 paragraphs, 150-250 words):

1. **Opening** (1 sentence): State the role you're applying for
2. **Skills Match** (1 paragraph): 2-3 relevant achievements with metrics that match job requirements
3. **Close** (1-2 sentences): Availability and next steps

REQUIREMENTS:
- Include at least 1 quantified metric from your actual experience
- Mention at least one specific skill from the job requirements
- End with: "I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"
- Keep under 250 words

DO NOT:
- Reference company pain points (you don't know the client company)
- Mention company signals or news (irrelevant)
- Use generic phrases like "excited to apply" or "passionate about"
- Write more than 250 words
"""

USER_PROMPT_RECRUITER_TEMPLATE = """Write a cover letter for this recruitment agency job:

=== JOB DETAILS ===
Title: {title}
Agency: {agency}
Recruiter: {recruiter_name} ({recruiter_role})

=== JOB REQUIREMENTS (from job description) ===
{job_requirements}

=== CANDIDATE ACHIEVEMENTS (use these as evidence) ===
{candidate_achievements}

=== YOUR TASK ===
Write a 150-250 word cover letter that:
1. Opens with the specific role name
2. Matches 2-3 achievements to job requirements (include metrics)
3. Closes with availability and Calendly link

End exactly with: "I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"

Cover Letter:"""


# ===== VALIDATION FUNCTION =====

def validate_recruiter_cover_letter(text: str, state: JobState) -> None:
    """
    Validate recruiter cover letter against quality gates.

    Simpler validation than standard cover letters since we don't have
    company context to validate against.

    Quality Gates:
    1. Word count: 120-280 words (relaxed from 150-250)
    2. Metric presence: At least 1 quantified metric
    3. No excessive boilerplate
    4. Has closing CTA

    Args:
        text: Cover letter text to validate
        state: JobState (used for context)

    Raises:
        ValueError: If any validation gate fails
    """
    # Gate 1: Word count (150-250 target, 120-280 with tolerance)
    words = text.split()
    word_count = len(words)

    if word_count < 120:
        raise ValueError(f"Cover letter too short: {word_count} words (minimum 120)")
    if word_count > 280:
        raise ValueError(f"Cover letter too long: {word_count} words (maximum 280)")

    # Gate 2: Metric presence (at least 1)
    metric_matches = []
    for pattern in METRIC_PATTERNS:
        matches = re.findall(pattern, text)
        metric_matches.extend(matches)

    if len(set(metric_matches)) < 1:
        raise ValueError(
            "Cover letter must include at least 1 quantified metric. "
            "Examples: 75%, 10x, $2M, 100K users"
        )

    # Gate 3: Generic boilerplate detection (max 1)
    text_lower = text.lower()
    boilerplate_count = sum(1 for phrase in GENERIC_BOILERPLATE_PHRASES if phrase in text_lower)

    if boilerplate_count > 1:
        raise ValueError(
            f"Cover letter contains {boilerplate_count} generic boilerplate phrases. "
            f"Keep it direct and specific."
        )

    # Gate 4: Closing CTA
    if "calendly.com/taimooralam/15min" not in text_lower:
        raise ValueError(
            "Cover letter must include Calendly link: calendly.com/taimooralam/15min"
        )


# ===== RECRUITER COVER LETTER GENERATOR =====

class RecruiterCoverLetterGenerator:
    """
    Cover letter generator for recruitment agency jobs.

    Key differences from CoverLetterGenerator:
    - Shorter format (150-250 words vs 220-380)
    - No company pain point/signal requirements
    - Focus on skills match and availability
    - Simpler validation gates
    """

    def __init__(self):
        """Initialize cover letter generator."""
        self.logger = logging.getLogger(__name__)
        self.max_validation_retries = 2

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _call_llm(self, system: str, user_prompt: str) -> str:
        """Call LLM with retry logic using unified LLM."""
        result = invoke_unified_sync(
            prompt=user_prompt,
            system=system,
            step_name="recruiter_cover_letter",
            validate_json=False,  # Response is plain text cover letter
        )

        if not result.success:
            raise RuntimeError(f"Recruiter cover letter generation failed: {result.error}")

        return result.content.strip()

    def _extract_job_requirements(self, state: JobState) -> str:
        """Extract key requirements from job description."""
        jd = state.get("job_description", "")
        if not jd:
            return "No specific requirements provided."

        # Use extracted JD if available
        extracted_jd = state.get("extracted_jd")
        if extracted_jd:
            parts = []
            if extracted_jd.get("technical_skills"):
                parts.append(f"Technical Skills: {', '.join(extracted_jd['technical_skills'][:5])}")
            if extracted_jd.get("responsibilities"):
                parts.append(f"Responsibilities: {', '.join(extracted_jd['responsibilities'][:3])}")
            if extracted_jd.get("qualifications"):
                parts.append(f"Qualifications: {', '.join(extracted_jd['qualifications'][:3])}")
            if parts:
                return "\n".join(parts)

        # Fallback: first 800 chars of JD
        return jd[:800]

    def _format_candidate_achievements(self, state: JobState) -> str:
        """Format candidate achievements for prompt."""
        # Try selected STARs first
        selected_stars = state.get("selected_stars") or []
        if selected_stars:
            achievements = []
            for i, star in enumerate(selected_stars[:3], 1):
                achievements.append(
                    f"{i}. {star.get('company', 'Company')} - {star.get('role', 'Role')}: "
                    f"{star.get('results', 'Achievement')} "
                    f"(Metrics: {star.get('metrics', 'N/A')})"
                )
            return "\n".join(achievements)

        # Fallback to candidate profile snippet
        profile = state.get("candidate_profile", "")
        if profile:
            return profile[:600] + "..."

        return "No achievements provided."

    def _get_recruiter_info(self, state: JobState) -> tuple:
        """Get recruiter name and role from contacts."""
        primary_contacts = state.get("primary_contacts") or []
        if primary_contacts:
            contact = primary_contacts[0]
            return contact.get("name", "Recruiter"), contact.get("role", "Recruiter")
        return "Recruiter", "Recruiter"

    def _generate_with_retry(self, state: JobState, attempt: int = 1) -> str:
        """Generate cover letter with validation and retry."""
        recruiter_name, recruiter_role = self._get_recruiter_info(state)

        user_prompt = USER_PROMPT_RECRUITER_TEMPLATE.format(
            title=state.get("title", "the role"),
            agency=state.get("company", "the agency"),
            recruiter_name=recruiter_name,
            recruiter_role=recruiter_role,
            job_requirements=self._extract_job_requirements(state),
            candidate_achievements=self._format_candidate_achievements(state)
        )

        cover_letter = self._call_llm(SYSTEM_PROMPT_RECRUITER, user_prompt)

        try:
            validate_recruiter_cover_letter(cover_letter, state)
            return cover_letter
        except ValueError as e:
            if attempt <= self.max_validation_retries:
                self.logger.warning(
                    f"Recruiter cover letter validation failed "
                    f"(attempt {attempt}/{self.max_validation_retries + 1}): {e}"
                )
                return self._generate_with_retry(state, attempt + 1)
            else:
                raise ValueError(
                    f"Recruiter cover letter validation failed after "
                    f"{self.max_validation_retries + 1} attempts: {e}"
                )

    def generate_cover_letter(self, state: JobState) -> str:
        """
        Generate validated recruiter cover letter.

        Args:
            state: JobState with job details and candidate achievements

        Returns:
            Cover letter text (150-250 words)

        Raises:
            ValueError: If validation fails after retries
        """
        self.logger.info("Generating recruiter-specific cover letter")
        return self._generate_with_retry(state, attempt=1)
