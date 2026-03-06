"""
Unified Deduplication Module

Single source of truth for generating job deduplication keys across all sources.
Prioritizes source-specific unique IDs (jobId, job_key) over text-based keys.

Usage:
    from src.common.dedupe import generate_dedupe_key

    # With source ID (preferred - robust):
    key = generate_dedupe_key("linkedin", source_id="3847291058")
    # Result: "linkedin|3847291058"

    # Fallback (text-based - normalized):
    key = generate_dedupe_key("indeed", company="McKinsey & Co.", title="Senior Consultant", location="Riyadh, SA")
    # Result: "indeed|mckinseyco|seniorconsultant|riyadhsa"
"""

import re
from typing import Dict, List, Optional


def normalize_for_dedupe(text: Optional[str]) -> str:
    """
    Normalize text for deduplication - remove all non-alphanumeric characters.

    This ensures consistent matching regardless of:
    - Punctuation: "McKinsey & Company" vs "McKinsey and Company"
    - Spacing: "New York" vs "New  York"
    - Special chars: "Riyadh, Saudi Arabia" vs "Riyadh - Saudi Arabia"

    Args:
        text: Input text to normalize

    Returns:
        Lowercase alphanumeric-only string

    Examples:
        >>> normalize_for_dedupe("McKinsey & Company")
        'mckinseycompany'
        >>> normalize_for_dedupe("Riyadh, Saudi Arabia")
        'riyadhsaudiarabia'
        >>> normalize_for_dedupe(None)
        ''
    """
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def generate_dedupe_key(
    source: str,
    source_id: Optional[str] = None,
    company: Optional[str] = None,
    title: Optional[str] = None,
    location: Optional[str] = None,
) -> str:
    """
    Generate a deduplication key with source ID priority.

    Priority:
    1. If source_id exists: "{source}|{source_id}" (robust, immutable)
    2. Fallback: "{source}|{company}|{title}|{location}" (normalized text)

    The source_id approach is preferred because:
    - LinkedIn jobId, Indeed job_key, Himalayas id are unique and immutable
    - Text-based keys are fragile (company names vary, locations differ)

    Args:
        source: Job source identifier (e.g., "linkedin", "indeed", "himalayas_auto")
        source_id: Unique ID from the source (e.g., LinkedIn jobId, Indeed job_key)
        company: Company name (used in fallback)
        title: Job title (used in fallback)
        location: Job location (used in fallback)

    Returns:
        Deduplication key string

    Examples:
        >>> generate_dedupe_key("linkedin", source_id="3847291058")
        'linkedin|3847291058'

        >>> generate_dedupe_key("indeed", source_id="abc123def4567890")
        'indeed|abc123def4567890'

        >>> generate_dedupe_key("himalayas_auto", company="Acme Corp", title="Engineer", location="Remote")
        'himalayas_auto|acmecorp|engineer|remote'
    """
    # Primary: Use source_id if available (most reliable)
    if source_id:
        return f"{source}|{source_id}"

    # Fallback: Normalized text fields
    norm_company = normalize_for_dedupe(company)
    norm_title = normalize_for_dedupe(title)
    norm_location = normalize_for_dedupe(location)

    return f"{source}|{norm_company}|{norm_title}|{norm_location}"


def extract_source_id_from_url(url: str, source: str) -> Optional[str]:
    """
    Extract source-specific job ID from URL.

    Args:
        url: Job URL
        source: Source identifier to determine extraction pattern

    Returns:
        Extracted job ID or None if not found

    Examples:
        >>> extract_source_id_from_url("https://linkedin.com/jobs/view/3847291058", "linkedin")
        '3847291058'

        >>> extract_source_id_from_url("https://indeed.com/viewjob?jk=abc123def4567890", "indeed")
        'abc123def4567890'
    """
    if not url:
        return None

    patterns = {
        "linkedin": [
            r"-(\d+)(?:\?|$)",  # .../jobs/view/title-123456789
            r"/view/(\d+)",  # .../jobs/view/123456789
        ],
        "indeed": [
            r"[?&]jk=([a-f0-9]{16})",  # ?jk=abc123...
            r"[?&]vjk=([a-f0-9]{16})",  # ?vjk=abc123...
        ],
        "bayt": [
            r"/job/(\d+)/",  # /job/12345/
        ],
        "himalayas": [
            r"/jobs/([^/\?]+)",  # /jobs/job-slug-123
        ],
    }

    # Normalize source name for pattern lookup
    source_key = source.replace("_auto", "").replace("_import", "")

    if source_key not in patterns:
        return None

    for pattern in patterns[source_key]:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


# Region priority for cross-location dedup (higher = preferred)
REGION_PRIORITY = {
    "asia_pacific": 6,
    "emea": 5,
    "eea": 4,
    "eu": 3,
    "us": 2,
    "pakistan": 1,
    "remote": 3,  # Treat remote as neutral priority
    "unknown": 0,
}

# Region detection keywords
_REGION_KEYWORDS = {
    "asia_pacific": [
        "singapore", "hong kong", "japan", "tokyo", "australia", "sydney",
        "melbourne", "india", "bangalore", "mumbai", "delhi", "hyderabad",
        "seoul", "korea", "taiwan", "thailand", "bangkok", "vietnam",
        "indonesia", "jakarta", "malaysia", "kuala lumpur", "philippines",
        "manila", "china", "shanghai", "beijing", "shenzhen",
    ],
    "emea": [
        "dubai", "abu dhabi", "uae", "united arab emirates", "saudi",
        "riyadh", "jeddah", "qatar", "doha", "bahrain", "kuwait",
        "oman", "cairo", "egypt", "south africa", "johannesburg",
        "cape town", "nairobi", "kenya", "nigeria", "lagos",
        "israel", "tel aviv", "turkey", "istanbul",
    ],
    "eea": [
        "london", "united kingdom", "uk", "germany", "berlin", "munich",
        "france", "paris", "netherlands", "amsterdam", "ireland", "dublin",
        "spain", "madrid", "barcelona", "italy", "milan", "rome",
        "switzerland", "zurich", "geneva", "sweden", "stockholm",
        "norway", "oslo", "denmark", "copenhagen", "finland", "helsinki",
        "belgium", "brussels", "austria", "vienna", "portugal", "lisbon",
        "poland", "warsaw", "czech", "prague", "romania", "bucharest",
        "greece", "athens",
    ],
    "pakistan": [
        "pakistan", "karachi", "lahore", "islamabad", "rawalpindi",
    ],
    "us": [
        "united states", ", usa", "new york", "san francisco",
        "los angeles", "chicago", "seattle", "boston", "austin",
        "denver", "atlanta", "dallas", "houston", "miami",
        "washington, dc", "washington dc", "portland", "phoenix",
        "san jose", "san diego", "minneapolis", "detroit",
        "philadelphia", "pittsburgh", "raleigh", "charlotte",
    ],
}


def detect_region(location: str) -> str:
    """Detect region from a job location string.

    Args:
        location: Job location (e.g., "Singapore", "Dubai, UAE", "San Francisco, CA")

    Returns:
        Region key from REGION_PRIORITY, or "unknown"
    """
    if not location:
        return "unknown"

    loc_lower = location.lower().strip()

    if "remote" in loc_lower:
        return "remote"

    for region, keywords in _REGION_KEYWORDS.items():
        for kw in keywords:
            if kw in loc_lower:
                return region

    # Check US state abbreviations (", CA", ", NY", etc.)
    us_states = (
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
        "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
        "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
        "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
        "WI", "WY", "DC",
    )
    for state in us_states:
        if location.endswith(f", {state}") or location.endswith(f" {state}"):
            return "us"

    return "unknown"


def consolidate_by_location(jobs: List[Dict]) -> List[Dict]:
    """Consolidate duplicate jobs across locations.

    Groups by normalized(company) + normalized(title), keeps the one from
    the highest-priority region. Tie-breaks by score.

    Args:
        jobs: List of scored job dicts with company, title, location, score keys

    Returns:
        Deduplicated list of jobs
    """
    import logging
    from collections import defaultdict

    groups: Dict[str, List[Dict]] = defaultdict(list)

    for job in jobs:
        company_norm = normalize_for_dedupe(job.get("company"))
        title_norm = normalize_for_dedupe(job.get("title"))
        key = f"{company_norm}|{title_norm}"
        groups[key].append(job)

    result = []
    consolidated_count = 0

    for key, group in groups.items():
        if len(group) == 1:
            result.append(group[0])
            continue

        # Sort by region priority (desc), then score (desc)
        group.sort(
            key=lambda j: (
                REGION_PRIORITY.get(detect_region(j.get("location", "")), 0),
                j.get("score", 0),
            ),
            reverse=True,
        )
        result.append(group[0])
        consolidated_count += len(group) - 1

    if consolidated_count > 0:
        logging.getLogger(__name__).info(
            f"Cross-location dedup: consolidated {consolidated_count} duplicates "
            f"({len(jobs)} → {len(result)})"
        )

    return result
