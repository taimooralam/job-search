"""
Job Blacklist — loads data/blacklist.yaml and provides filtering functions.

Used by all 3 scout cron phases to reject jobs from blacklisted companies,
titles, or descriptions before they consume pipeline resources.
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import yaml

logger = logging.getLogger(__name__)

BLACKLIST_PATH = Path(__file__).parent.parent.parent / "data" / "blacklist.yaml"


@lru_cache(maxsize=1)
def _load_blacklist() -> Dict[str, List[str]]:
    """Load and cache the blacklist YAML. Returns empty dict on failure."""
    if not BLACKLIST_PATH.exists():
        logger.warning(f"Blacklist file not found: {BLACKLIST_PATH}")
        return {}
    try:
        with open(BLACKLIST_PATH, "r") as f:
            data = yaml.safe_load(f) or {}
        # Normalize all entries to lowercase for case-insensitive matching
        return {
            key: [v.lower().strip() for v in values if v]
            for key, values in data.items()
            if isinstance(values, list)
        }
    except Exception as e:
        logger.error(f"Failed to load blacklist: {e}")
        return {}


def reload_blacklist():
    """Clear cache and reload from disk (useful for tests or hot-reload)."""
    _load_blacklist.cache_clear()


def is_blacklisted(job: Dict[str, Any]) -> bool:
    """Check if a job matches any blacklist rule.

    Args:
        job: Dict with any of: company, title, description

    Returns:
        True if the job should be filtered out.
    """
    bl = _load_blacklist()
    if not bl:
        return False

    company = (job.get("company") or "").lower()
    title = (job.get("title") or "").lower()
    description = (job.get("description") or "").lower()

    for blocked in bl.get("companies", []):
        if blocked in company:
            return True

    for blocked in bl.get("titles", []):
        if blocked in title:
            return True

    for blocked in bl.get("keywords_in_description", []):
        if blocked in description:
            return True

    return False


def filter_blacklisted(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove blacklisted jobs from a list. Logs each removal.

    Returns:
        Filtered list with blacklisted jobs removed.
    """
    bl = _load_blacklist()
    if not bl:
        return jobs

    kept = []
    removed = 0
    for job in jobs:
        if is_blacklisted(job):
            removed += 1
            logger.info(
                f"[blacklist] Filtered: {job.get('title', '?')} @ {job.get('company', '?')}"
            )
        else:
            kept.append(job)

    if removed:
        logger.info(f"[blacklist] Removed {removed}/{len(jobs)} jobs")

    return kept
