"""Shared scrape and selector-compatibility logic for scout iteration 2."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import requests
from pymongo.collection import Collection

from src.common.blacklist import is_blacklisted
from src.common.dedupe import generate_dedupe_key
from src.common.proxy_pool import fetch_with_proxy
from src.common.rule_scorer import compute_rule_score
from src.services.linkedin_scraper import (
    HEADERS,
    JobNotFoundError,
    LinkedInScraperError,
    ParseError,
    RateLimitError,
    _parse_job_html,
)

LINKEDIN_JOB_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

_TITLE_PATTERNS = re.compile(
    r"\b("
    r"ai|artificial.intelligence|machine.learning|ml|"
    r"llm|genai|gen.ai|generative|gpt|"
    r"nlp|natural.language|deep.learning|neural|"
    r"computer.vision|agentic|rag|"
    r"software.engineer|backend.engineer|full.stack|fullstack|"
    r"platform.engineer|cloud.engineer|devops|sre|"
    r"data.engineer|data.scientist|data.science|"
    r"developer|programmer|"
    r"solution.architect|cloud.architect|system.architect|"
    r"enterprise.architect|technical.architect|it.architect|"
    r"data.architect|infrastructure.architect|"
    r"head.of.ai|head.of.data|head.of.engineering|"
    r"head.of.genai|head.of.llm|head.of.ml|"
    r"cto|vp.engineer|"
    r"tech.lead|engineering.lead|engineering.manager|"
    r"principal.engineer|staff.engineer|founding.engineer|"
    r"principal.architect|staff.architect|"
    r"director.of.ai|director.ai|ai.director|"
    r"director.of.engineering|director.engineering|"
    r"research.scientist|researcher|applied.scientist|"
    r"software.architect|vp.engineering|"
    r"staff.ai|principal.ai|staff.genai|staff.llm|"
    r"ai.solutions.architect|"
    r"head.of.ai.engineering|head.of.platform|"
    r"llmops|llm.ops|"
    r"founding.ai|forward.deployed|"
    r"ml.engineer|machine.learning.engineer"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ScrapeSkipResult:
    """Represents a pre-fetch skip."""

    status: str
    reason: str


@dataclass(frozen=True)
class ScrapeSuccessResult:
    """Represents a fetched, parsed, and scored job."""

    scored_job: dict[str, Any]
    http_status: int
    used_proxy: bool


@dataclass(frozen=True)
class FailureDisposition:
    """Whether a scrape failure should retry or deadletter immediately."""

    retryable: bool
    error_type: str


def title_passes_filter(title: str) -> bool:
    """Require at least one AI or technical signal in the title."""
    return bool(_TITLE_PATTERNS.search(title))


def evaluate_scrape_candidate(
    job: dict[str, Any],
    *,
    pool: list[str],
    use_proxy: bool,
) -> ScrapeSkipResult | ScrapeSuccessResult:
    """Apply skip checks, then fetch, parse, and score one job."""
    title = job.get("title", "")
    if is_blacklisted(job):
        return ScrapeSkipResult(
            status="skipped_blacklist",
            reason=f"blacklisted_company:{job.get('company', '')}".strip(":"),
        )
    if title and not title_passes_filter(title):
        return ScrapeSkipResult(
            status="skipped_title_filter",
            reason=f"title_filter:{title}",
        )
    return scrape_and_score(job, pool=pool, use_proxy=use_proxy)


def scrape_and_score(
    job: dict[str, Any],
    *,
    pool: list[str],
    use_proxy: bool = True,
) -> ScrapeSuccessResult:
    """Fetch LinkedIn HTML, parse it, and compute the rule score."""
    job_id = job["job_id"]
    url = LINKEDIN_JOB_URL.format(job_id=job_id)

    if use_proxy and pool:
        response = fetch_with_proxy(url, headers=HEADERS, timeout=15, pool=pool)
    else:
        response = requests.get(url, headers=HEADERS, timeout=15)

    if response.status_code == 429:
        raise RateLimitError(f"Rate limited on {job_id}")
    if response.status_code == 404:
        raise JobNotFoundError(f"Job {job_id} not found (404)")
    if response.status_code != 200:
        raise LinkedInScraperError(f"HTTP {response.status_code} for {job_id}")

    job_data = _parse_job_html(job_id, response.text)
    score_input = {
        "title": job_data.title,
        "job_description": job_data.description,
        "job_criteria": " ".join(
            filter(
                None,
                [job_data.seniority_level, job_data.employment_type, job_data.job_function],
            )
        ),
        "location": job_data.location,
    }
    result = compute_rule_score(score_input)
    scored_at = datetime.now(timezone.utc).isoformat()

    return ScrapeSuccessResult(
        scored_job={
            "job_id": job_id,
            "title": job_data.title,
            "company": job_data.company,
            "location": job_data.location,
            "job_url": f"https://linkedin.com/jobs/view/{job_id}",
            "score": result["score"],
            "tier": result["tier"],
            "detected_role": result["detectedRole"],
            "seniority_level": result.get("seniorityLevel", "unknown"),
            "is_target_role": result["isTargetRole"],
            "description": job_data.description,
            "seniority": job_data.seniority_level,
            "employment_type": job_data.employment_type,
            "job_function": job_data.job_function,
            "industries": job_data.industries,
            "work_mode": job_data.work_mode,
            "breakdown": result["breakdown"],
            "search_profile": job.get("search_profile", ""),
            "search_region": job.get("search_region", ""),
            "source_cron": job.get("source_cron", ""),
            "scored_at": scored_at,
        },
        http_status=response.status_code,
        used_proxy=bool(use_proxy and pool),
    )


def upsert_level1_scored_job(
    level1: Collection,
    scored: dict[str, Any],
    *,
    source: str = "scout_scraper",
    status: str = "scored",
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Upsert the selector-compatible level-1 staging row used by the legacy scraper."""
    created_at = now or datetime.now(timezone.utc)
    dedupe_key = generate_dedupe_key("linkedin_scout", source_id=scored["job_id"])
    result = level1.update_one(
        {"dedupeKey": dedupe_key},
        {
            "$setOnInsert": {
                "company": scored["company"],
                "title": scored["title"],
                "location": scored["location"],
                "jobUrl": scored["job_url"],
                "dedupeKey": dedupe_key,
                "createdAt": created_at,
                "source": source,
                "auto_discovered": True,
                "quick_score": scored["score"],
                "tier": scored["tier"],
                "status": status,
                "description": scored.get("description", ""),
                "detected_role": scored.get("detected_role"),
                "linkedin_metadata": {
                    "linkedin_job_id": scored["job_id"],
                    "seniority_level": scored.get("seniority"),
                    "employment_type": scored.get("employment_type"),
                    "job_function": scored.get("job_function"),
                    "industries": scored.get("industries"),
                    "work_mode": scored.get("work_mode"),
                    "rule_score_breakdown": scored.get("breakdown"),
                },
            }
        },
        upsert=True,
    )
    return {
        "dedupe_key": dedupe_key,
        "upserted": result.upserted_id is not None,
    }


def classify_scrape_exception(exc: Exception) -> FailureDisposition:
    """Classify scrape failures for retry/backoff handling."""
    if isinstance(exc, RateLimitError):
        return FailureDisposition(retryable=True, error_type="rate_limit")
    if isinstance(exc, JobNotFoundError):
        return FailureDisposition(retryable=False, error_type="job_not_found")
    if isinstance(exc, ParseError):
        return FailureDisposition(retryable=True, error_type="parse_error")
    if isinstance(exc, requests.Timeout):
        return FailureDisposition(retryable=True, error_type="timeout")
    if isinstance(exc, requests.RequestException):
        return FailureDisposition(retryable=True, error_type="network_error")
    if isinstance(exc, LinkedInScraperError):
        message = str(exc)
        if "HTTP 404" in message:
            return FailureDisposition(retryable=False, error_type="http_404")
        if "HTTP 5" in message or "HTTP 429" in message:
            return FailureDisposition(retryable=True, error_type="http_error")
        return FailureDisposition(retryable=True, error_type="linkedin_error")
    return FailureDisposition(retryable=True, error_type=exc.__class__.__name__.lower())
