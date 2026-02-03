"""
Quick Job Scorer Service (GAP-065)

Lightweight scoring for imported jobs that haven't gone through the full pipeline.
Uses a cheap LLM (gpt-4o-mini) for cost-effective scoring.

This provides an initial fit assessment so users can quickly prioritize jobs
before running the full pipeline.
"""

import logging
import re
from pathlib import Path
from typing import Optional, Tuple

from src.common.config import Config
from src.common.unified_llm import invoke_unified_sync

logger = logging.getLogger(__name__)


# Simplified scoring prompt for quick assessment
QUICK_SCORE_SYSTEM = """You are a senior technical recruiter who quickly evaluates job-candidate fit.

Your task is to provide a QUICK initial fit score (0-100) based on:
1. Technical skills match
2. Experience level alignment
3. Role type fit (IC vs management, domain focus)
4. Location/logistics feasibility

SCORING GUIDELINES:
- 80-100: Strong fit - core skills match, right level, relevant domain
- 60-79: Good potential - most skills match, some gaps but learnable
- 40-59: Moderate fit - partial match, significant gaps
- 0-39: Weak fit - major misalignment in skills, level, or domain

Be realistic but optimistic. This is a QUICK assessment, not a deep dive.
"""

QUICK_SCORE_USER = """Rate this job's fit for the candidate profile below.

=== JOB ===
Title: {title}
Company: {company}
Location: {location}

Description:
{description}

=== CANDIDATE PROFILE ===
{candidate_profile}

=== YOUR OUTPUT ===
Provide:
1. SCORE: [0-100]
2. RATIONALE: [1-2 sentences explaining the key match/mismatch factors]

Example output:
SCORE: 75
RATIONALE: Strong match on cloud architecture and Python skills. The role requires ML expertise which candidate has demonstrated at scale. Minor gap in specific Kubernetes experience.
"""


def _format_profile_as_text(profile: dict) -> str:
    """Format profile dict as text for LLM consumption."""
    lines = []

    # Name and summary
    if profile.get("name"):
        lines.append(f"# {profile['name']}")
    if profile.get("summary"):
        lines.append(f"\n{profile['summary']}")

    # Skills
    if profile.get("skills"):
        lines.append(f"\n## Skills\n{', '.join(profile['skills'][:25])}")

    # Roles
    if profile.get("roles"):
        lines.append("\n## Experience")
        for role in profile.get("roles", [])[:6]:
            company = role.get("company", "Unknown")
            title = role.get("title", "Unknown")
            period = role.get("period", "")
            lines.append(f"\n### {company} - {title}")
            if period:
                lines.append(f"{period}")
            for achievement in role.get("achievements", [])[:5]:
                lines.append(f"- {achievement}")

    return "\n".join(lines) if lines else "Candidate profile not available."


def load_candidate_profile() -> str:
    """Load the master CV/candidate profile from MongoDB or file fallback."""
    # Try MongoDB first if enabled
    if Config.USE_MASTER_CV_MONGODB:
        try:
            from src.common.master_cv_store import MasterCVStore

            store = MasterCVStore(use_mongodb=True)
            profile = store.get_profile_for_suggestions()

            if profile:
                logger.debug("Loaded candidate profile from MongoDB")
                return _format_profile_as_text(profile)
        except Exception as e:
            logger.warning(f"MongoDB unavailable for profile, using file fallback: {e}")

    # File fallback
    profile_path = Path(Config.CANDIDATE_PROFILE_PATH)

    if not profile_path.exists():
        logger.warning(f"Candidate profile not found at {profile_path}")
        return "Candidate profile not available."

    try:
        return profile_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Error reading candidate profile: {e}")
        return "Candidate profile could not be loaded."


def quick_score_job(
    title: str,
    company: str,
    location: str,
    description: str,
    candidate_profile: Optional[str] = None,
) -> Tuple[Optional[int], Optional[str]]:
    """
    Generate a quick fit score for a job.

    Args:
        title: Job title
        company: Company name
        location: Job location
        description: Job description text
        candidate_profile: Optional override for candidate profile

    Returns:
        Tuple of (score, rationale) or (None, None) on failure
    """
    # Load candidate profile if not provided
    if candidate_profile is None:
        candidate_profile = load_candidate_profile()

    # Truncate description if too long (save tokens)
    max_desc_length = 4000
    if len(description) > max_desc_length:
        description = description[:max_desc_length] + "\n\n[... truncated for quick scoring ...]"

    # Build prompt
    user_message = QUICK_SCORE_USER.format(
        title=title,
        company=company,
        location=location,
        description=description,
        candidate_profile=candidate_profile[:6000],  # Limit profile too
    )

    try:
        # Use unified LLM with step config (tier="low", use_fallback=False)
        result = invoke_unified_sync(
            prompt=user_message,
            system=QUICK_SCORE_SYSTEM,
            step_name="quick_scorer",
            validate_json=False,  # Response is text with SCORE: and RATIONALE:
        )

        if not result.success:
            logger.error(f"Quick scoring LLM failed: {result.error}")
            return None, None

        # Parse response
        response_text = result.content
        score, rationale = _parse_score_response(response_text)

        logger.info(f"Quick score for {company} - {title}: {score}")
        return score, rationale

    except Exception as e:
        logger.error(f"Quick scoring failed: {e}")
        return None, None


def _parse_score_response(response_text: str) -> Tuple[Optional[int], Optional[str]]:
    """
    Parse the LLM response to extract score and rationale.

    Args:
        response_text: Raw LLM response

    Returns:
        Tuple of (score, rationale)
    """
    score = None
    rationale = None

    # Extract score using regex
    score_match = re.search(r'SCORE:\s*(\d+)', response_text, re.IGNORECASE)
    if score_match:
        try:
            score = int(score_match.group(1))
            # Clamp to valid range
            score = max(0, min(100, score))
        except ValueError:
            pass

    # Extract rationale
    rationale_match = re.search(
        r'RATIONALE:\s*(.+?)(?:\n\n|$)',
        response_text,
        re.IGNORECASE | re.DOTALL
    )
    if rationale_match:
        rationale = rationale_match.group(1).strip()
        # Clean up any trailing artifacts
        rationale = re.sub(r'\s+$', '', rationale)

    return score, rationale


def derive_tier_from_score(score: Optional[int]) -> Optional[str]:
    """
    Derive a tier label from the quick score.

    Args:
        score: Fit score 0-100

    Returns:
        Tier: "A" | "B" | "C" | "D" or None
    """
    if score is None:
        return None

    if score >= 80:
        return "A"
    elif score >= 60:
        return "B"
    elif score >= 40:
        return "C"
    else:
        return "D"
