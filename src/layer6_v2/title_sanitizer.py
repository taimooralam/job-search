"""
Title Sanitizer — strips structural noise from JD titles.

Two-layer approach:
1. Regex pass (sync, always runs) — strips gender markers, language tags,
   location suffixes, work-mode tags, and trailing country codes.
2. Haiku LLM pass (async, optional) — catches patterns regex misses
   (e.g., embedded locations, non-English titles).

Anti-hallucination: LLM result must be a substring of the original title.
If not, the regex-only result is used.
"""

import re
from typing import Optional

from src.common.logger import get_logger

logger = get_logger(__name__)

# ---- Regex patterns (order matters — applied sequentially) ----

# Gender markers: (m/w/d), (f/m/x), (f/m/d), (alle Geschlechter), (gn), (m/f/x), etc.
_GENDER_RE = re.compile(
    r"\s*\(\s*(?:m\s*/\s*[wf]\s*/\s*[dxn]|f\s*/\s*m\s*/\s*[dxn]|"
    r"all(?:e)?\s+geschlechter|gn|all\s+genders?|"
    r"m\s*/\s*f(?:\s*/\s*[dxn])?)\s*\)",
    re.IGNORECASE,
)

# Language with "with/mit": "with French", "mit Deutsch", "with fluent German"
_LANGUAGE_WITH_RE = re.compile(
    r"\s*(?:with|mit)\s+(?:fluent\s+)?(?:French|German|Deutsch|English|Dutch|"
    r"Italian|Spanish|Mandarin|Arabic|Japanese|Portuguese|Swedish|Norwegian|"
    r"Danish|Finnish|Polish|Czech|Hungarian|Romanian|Turkish|Russian|"
    r"Flemish|Cantonese|Korean|Hindi)\b",
    re.IGNORECASE,
)

# Location after dash/em-dash: "- Schweiz", "- Berlin", "– DACH", "- Remote"
_LOCATION_DASH_RE = re.compile(
    r"\s*[–—-]\s*(?:[A-Z][a-zA-Zäöüß]+(?:\s+[A-Z][a-zA-Zäöüß]+)*|DACH|EMEA|APAC|MENA)\s*$",
)

# Work-mode/contract tags: (Remote), (Hybrid), (Contract), (Freelance), (Permanent)
_WORKMODE_RE = re.compile(
    r"\s*\(\s*(?:Remote|Hybrid|On-?site|Contract|Freelance|Permanent|"
    r"Full-?time|Part-?time|Teilzeit|Vollzeit|100%|80-100%)\s*\)",
    re.IGNORECASE,
)

# Trailing country codes: ", DE", ", CH", ", AT", ", NL", ", UK", ", US"
_COUNTRY_CODE_RE = re.compile(
    r",\s*(?:DE|CH|AT|NL|UK|US|BE|FR|ES|IT|SE|NO|DK|FI|PL|CZ|HU|RO|SG|AE|SA|QA)\s*$",
)

# Trailing whitespace/punctuation cleanup
_TRAILING_CLEANUP_RE = re.compile(r"[\s,\-–—|]+$")

_REGEX_PATTERNS = [
    _GENDER_RE,
    _WORKMODE_RE,
    _LANGUAGE_WITH_RE,
    _LOCATION_DASH_RE,
    _COUNTRY_CODE_RE,
]


def sanitize_job_title(raw_title: str) -> str:
    """
    Regex pass: strip known structural patterns from a job title.

    Always runs (sync, free, fast). Returns cleaned title.
    """
    if not raw_title or not raw_title.strip():
        return ""

    result = raw_title.strip()

    for pattern in _REGEX_PATTERNS:
        result = pattern.sub("", result)

    # Final cleanup
    result = _TRAILING_CLEANUP_RE.sub("", result).strip()

    if result != raw_title.strip():
        logger.debug(f"Title sanitized: '{raw_title.strip()}' → '{result}'")

    return result or raw_title.strip()


async def sanitize_job_title_llm(
    raw_title: str,
    regex_result: str,
    job_id: Optional[str] = None,
) -> str:
    """
    Haiku LLM validation pass: catches patterns regex misses.

    Args:
        raw_title: Original title from JD
        regex_result: Result of regex sanitization
        job_id: Optional job ID for tracking

    Returns:
        Cleaned title. Falls back to regex_result if LLM fails
        or returns a non-substring.
    """
    # Skip LLM if regex already cleaned to a short, simple title
    if regex_result == raw_title.strip():
        # No regex changes — still worth checking with LLM for embedded patterns
        pass

    try:
        from src.common.unified_llm import UnifiedLLM

        llm = UnifiedLLM(
            step_name="title_sanitizer",
            job_id=job_id or "unknown",
        )

        prompt = (
            f'Given this job title, return ONLY the clean professional role title.\n'
            f'You may ONLY remove words, never add or rephrase.\n'
            f'Remove: gender markers, language requirements, location suffixes, '
            f'work-mode tags, contract types, country codes.\n'
            f'If already clean, return as-is.\n\n'
            f'Job title: "{raw_title}"\n\n'
            f'Clean title:'
        )

        result = await llm.invoke(
            prompt=prompt,
            system="You clean job titles by removing non-essential suffixes. Return ONLY the title, nothing else.",
            validate_json=False,
        )

        if result.success and result.content:
            llm_title = result.content.strip().strip('"').strip("'").strip()

            # Anti-hallucination: LLM result must be a substring of the original
            if llm_title and llm_title in raw_title:
                logger.info(f"LLM title sanitizer: '{raw_title}' → '{llm_title}'")
                return llm_title
            else:
                logger.warning(
                    f"LLM title not a substring of original — discarding. "
                    f"LLM='{llm_title}', original='{raw_title}'"
                )
                return regex_result
        else:
            logger.warning(f"LLM title sanitizer failed: {result.error}")
            return regex_result

    except Exception as e:
        logger.warning(f"LLM title sanitizer exception: {e}")
        return regex_result
