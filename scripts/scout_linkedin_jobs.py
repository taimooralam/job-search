#!/usr/bin/env python3
"""
LinkedIn AI Job Scout — Search, score, and filter AI roles from LinkedIn.

Searches LinkedIn's guest API for AI/GenAI/LLM roles, scores them using
rule_scorer.py, and outputs JSON to stdout for the scout-jobs skill.

Usage:
    python scripts/scout_linkedin_jobs.py --time hour --region eea --pages 2
    python scripts/scout_linkedin_jobs.py --time day --region eea,mena --pages 3 --limit 15 --remote
    python scripts/scout_linkedin_jobs.py --time week --region emea --min-score 40
    python scripts/scout_linkedin_jobs.py --time day --region pakistan --few-applicants
"""

import argparse
import json
import logging
import re
import sys
import time
from typing import Any, Dict, List, Set

import requests
from bs4 import BeautifulSoup

# Reuse existing LinkedIn scraper infrastructure
from src.services.linkedin_scraper import (
    HEADERS,
    REQUEST_TIMEOUT,
    extract_job_id,
    scrape_linkedin_job,
    LinkedInScraperError,
)
from src.common.rule_scorer import compute_rule_score

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,  # Logs to stderr, JSON output to stdout
)
logger = logging.getLogger(__name__)

# LinkedIn search API
LINKEDIN_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

# Search keyword profiles — organized by role category
SEARCH_PROFILES = {
    "ai": [
        "AI Engineer",
        "AI Architect",
        "GenAI Engineer",
        "LLM Engineer",
        "Agentic AI Engineer",
        "Applied AI Engineer",
        "Head of AI",
        "AI Tech Lead",
    ],
    "engineering": [
        "Staff Software Engineer",
        "Principal Engineer",
        "Software Architect",
        "Lead Software Engineer",
        "Tech Lead",
    ],
}

# Time filter mapping (f_TPR param)
TIME_FILTERS = {
    "hour": "r3600",
    "day": "r86400",
    "3days": "r259200",
    "week": "r604800",
    "month": "r2592000",
    "2months": "r5184000",
}

# Region mapping
REGION_CONFIGS = {
    "eea": {
        "locations": [
            # Western Europe
            "Germany", "Netherlands", "France", "Belgium", "Austria",
            # Nordics / Scandinavia
            "Sweden", "Denmark", "Norway", "Finland", "Iceland",
            # Southern Europe + Iberian peninsula
            "Italy", "Spain", "Portugal", "Greece",
            # Baltic states
            "Estonia", "Latvia", "Lithuania",
            # Other EEA
            "Ireland",
            # EEA-adjacent / Schengen
            "Switzerland",
        ]
    },
    "mena": {
        "locations": [
            "United Arab Emirates", "Saudi Arabia", "Qatar",
            "Kuwait", "Bahrain", "Oman",
            "Morocco",
        ]
    },
    "emea": {
        # Superset: EEA + UK + MENA + Turkey + South Africa
        "locations": [
            # All EEA locations
            "Germany", "Netherlands", "France", "Belgium", "Austria",
            "Sweden", "Denmark", "Norway", "Finland", "Iceland",
            "Italy", "Spain", "Portugal", "Greece",
            "Estonia", "Latvia", "Lithuania",
            "Ireland", "Switzerland",
            # Non-EEA Europe
            "Turkey",
            # MENA
            "United Arab Emirates", "Saudi Arabia", "Qatar",
            "Kuwait", "Bahrain", "Oman",
            "Morocco",
            # Africa
            "South Africa",
        ]
    },
    "pakistan": {"location": "Pakistan"},
    "asia_pacific": {
        "locations": [
            "Singapore", "Australia", "China", "Japan", "South Korea",
        ]
    },
}

# Rate limits
SEARCH_PAGE_DELAY = 1.5  # seconds between search pages
DETAIL_FETCH_DELAY = 1.0  # seconds between detail fetches


def parse_search_results(html: str) -> List[Dict[str, str]]:
    """Parse job listings from LinkedIn search results HTML."""
    if len(html) < 30:
        return []

    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    job_cards = soup.find_all("div", class_=re.compile(r"base-card"))

    for card in job_cards:
        try:
            title_elem = card.find(class_=re.compile(r"base-search-card__title"))
            title = title_elem.get_text(strip=True) if title_elem else None

            company_elem = card.find(class_=re.compile(r"base-search-card__subtitle"))
            company = company_elem.get_text(strip=True) if company_elem else None

            location_elem = card.find(class_=re.compile(r"job-search-card__location"))
            location = location_elem.get_text(strip=True) if location_elem else None

            link_elem = card.find("a", class_=re.compile(r"base-card__full-link"))
            job_url = link_elem.get("href") if link_elem else None

            job_id = None
            if job_url:
                try:
                    job_id = extract_job_id(job_url)
                except ValueError:
                    pass

            if title and job_id:
                jobs.append({
                    "job_id": job_id,
                    "title": title,
                    "company": company,
                    "location": location,
                    "job_url": job_url,
                })
        except Exception as e:
            logger.debug(f"Error parsing job card: {e}")
            continue

    return jobs


def fetch_search_page(
    keywords: str,
    start: int = 0,
    time_filter: str = None,
    location: str = None,
    remote_only: bool = False,
    few_applicants: bool = False,
    proxies: dict = None,
) -> str:
    """Fetch a single page of LinkedIn search results."""
    params: Dict[str, Any] = {
        "keywords": keywords,
        "start": start,
    }

    if time_filter:
        params["f_TPR"] = time_filter

    if location:
        params["location"] = location

    if remote_only:
        params["f_WT"] = "2"

    if few_applicants:
        params["f_JIYN"] = "true"

    try:
        response = requests.get(
            LINKEDIN_SEARCH_URL,
            params=params,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            proxies=proxies,
        )
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching search page: {e}")
        return ""


def search_jobs(
    keywords_list: List[str],
    time_filter: str,
    regions: List[str],
    max_pages: int,
    limit: int = 0,
    few_applicants: bool = False,
    remote_only: bool = False,
) -> List[Dict[str, str]]:
    """Search LinkedIn for jobs across keywords and regions, deduped."""
    seen_ids: Set[str] = set()
    all_jobs: List[Dict[str, str]] = []

    def _should_stop() -> bool:
        return limit > 0 and len(all_jobs) >= limit

    for region_key in regions:
        config = REGION_CONFIGS.get(region_key, {})

        # Build list of (location, remote_only) tuples to search
        search_params: List[Dict[str, Any]] = []
        if "locations" in config:
            for loc in config["locations"]:
                search_params.append({"location": loc, "remote_only": remote_only})
        elif "location" in config:
            search_params.append({"location": config["location"], "remote_only": remote_only})
        else:
            search_params.append({"location": None, "remote_only": remote_only})

        for sp in search_params:
            if _should_stop():
                break

            for kw in keywords_list:
                if _should_stop():
                    break

                loc_name = sp.get("location") or "Global"
                loc_label = f"{loc_name} [remote]" if sp.get("remote_only") else loc_name
                logger.info(f"Searching: '{kw}' in {loc_label} ({region_key})")

                for page in range(max_pages):
                    if _should_stop():
                        break

                    start = page * 25
                    html = fetch_search_page(
                        keywords=kw,
                        start=start,
                        time_filter=time_filter,
                        location=sp.get("location"),
                        remote_only=sp.get("remote_only", False),
                        few_applicants=few_applicants,
                    )

                    if len(html) < 30:
                        break

                    jobs = parse_search_results(html)
                    if not jobs:
                        break

                    new_count = 0
                    for job in jobs:
                        if job["job_id"] not in seen_ids:
                            seen_ids.add(job["job_id"])
                            all_jobs.append(job)
                            new_count += 1

                    logger.info(f"  Page {page}: {len(jobs)} found, {new_count} new (total: {len(all_jobs)})")

                    if new_count == 0:
                        break

                    time.sleep(SEARCH_PAGE_DELAY)

    return all_jobs[:limit] if limit > 0 else all_jobs


def fetch_details_and_score(jobs: List[Dict]) -> List[Dict]:
    """Fetch full job descriptions and score each job."""
    scored_jobs = []

    for i, job in enumerate(jobs):
        try:
            job_data = scrape_linkedin_job(job["job_id"])

            # Build scoring input matching rule_scorer expectations
            score_input = {
                "title": job_data.title,
                "job_description": job_data.description,
                "job_criteria": " ".join(filter(None, [
                    job_data.seniority_level,
                    job_data.employment_type,
                    job_data.job_function,
                ])),
                "location": job_data.location,
            }

            result = compute_rule_score(score_input)

            scored_jobs.append({
                "job_id": job["job_id"],
                "title": job_data.title,
                "company": job_data.company,
                "location": job_data.location,
                "job_url": f"https://linkedin.com/jobs/view/{job['job_id']}",
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
                "breakdown": result["breakdown"],
            })

            logger.info(
                f"  [{i + 1}/{len(jobs)}] Score: {result['score']} ({result['tier']}) "
                f"— {job_data.title} @ {job_data.company}"
            )

        except LinkedInScraperError as e:
            logger.warning(f"  [{i + 1}/{len(jobs)}] Skipped {job['job_id']}: {e}")
        except Exception as e:
            logger.warning(f"  [{i + 1}/{len(jobs)}] Error on {job['job_id']}: {e}")

        time.sleep(DETAIL_FETCH_DELAY)

    return scored_jobs


def main():
    parser = argparse.ArgumentParser(description="LinkedIn AI Job Scout")
    parser.add_argument(
        "--time",
        choices=list(TIME_FILTERS.keys()),
        default="hour",
        help="Time filter for job postings (default: hour)",
    )
    parser.add_argument(
        "--region",
        default="eea",
        help="Comma-separated regions: eea,mena,emea,pakistan,asia_pacific (default: eea)",
    )
    parser.add_argument(
        "--remote",
        action="store_true",
        help="Add remote filter (f_WT=2) to all searches",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=2,
        help="Max pages per search query (default: 2)",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=0,
        help="Minimum score threshold (default: 0)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max total jobs to return, 0 for unlimited (default: 0)",
    )
    parser.add_argument(
        "--few-applicants",
        action="store_true",
        default=False,
        help="Only show jobs with fewer than 10 applicants (LinkedIn f_JIYN filter)",
    )
    parser.add_argument(
        "--profile",
        default="ai",
        help="Comma-separated search profiles: ai,engineering (default: ai)",
    )

    args = parser.parse_args()

    # Parse regions (normalize hyphens to underscores: asia-pacific → asia_pacific)
    regions = [r.strip().replace("-", "_") for r in args.region.split(",")]
    invalid = [r for r in regions if r not in REGION_CONFIGS]
    if invalid:
        logger.error(f"Unknown regions: {invalid}. Valid: {list(REGION_CONFIGS.keys())}")
        sys.exit(1)

    time_filter = TIME_FILTERS[args.time]

    # Resolve search profiles into keyword list (deduped, order-preserved)
    profiles = [p.strip() for p in args.profile.split(",")]
    invalid_profiles = [p for p in profiles if p not in SEARCH_PROFILES]
    if invalid_profiles:
        logger.error(f"Unknown profiles: {invalid_profiles}. Valid: {list(SEARCH_PROFILES.keys())}")
        sys.exit(1)

    seen_kw: Set[str] = set()
    keywords: List[str] = []
    for prof in profiles:
        for kw in SEARCH_PROFILES[prof]:
            if kw not in seen_kw:
                seen_kw.add(kw)
                keywords.append(kw)

    # Step 1: Search
    logger.info(f"Scout config: time={args.time}, regions={regions}, profiles={profiles}, pages={args.pages}, min_score={args.min_score}, limit={args.limit}, few_applicants={args.few_applicants}, remote={args.remote}")
    logger.info(f"Search keywords ({len(keywords)}): {keywords}")
    jobs = search_jobs(keywords, time_filter, regions, args.pages, args.limit, args.few_applicants, remote_only=args.remote)
    logger.info(f"Found {len(jobs)} unique jobs across all searches")

    if not jobs:
        json.dump({"jobs": [], "summary": {"found": 0, "scored": 0, "filtered": 0}}, sys.stdout, indent=2)
        return

    # Step 2: Fetch details & score
    logger.info("Fetching job details and scoring...")
    scored = fetch_details_and_score(jobs)

    # Step 3: Filter score=0 and below min-score
    filtered = [j for j in scored if j["score"] > 0 and j["score"] >= args.min_score]

    # Step 4: Sort descending by score
    filtered.sort(key=lambda j: j["score"], reverse=True)

    # Step 5: Output JSON to stdout
    # Strip descriptions to minimize token usage — descriptions are only needed
    # for MongoDB insertion, which the skill handles by re-fetching or using
    # a separate descriptions file.
    slim_jobs = []
    descriptions = {}  # job_id → description, written to separate file
    for j in filtered:
        desc = j.pop("description", "")
        descriptions[j["job_id"]] = desc
        slim_jobs.append(j)

    output = {
        "jobs": slim_jobs,
        "summary": {
            "found": len(jobs),
            "scored": len(scored),
            "filtered": len(filtered),
            "min_score": args.min_score,
            "time_filter": args.time,
            "regions": regions,
        },
    }

    # Write descriptions to a sidecar file so the skill can read them for insertion
    desc_path = "/tmp/scout_jobs_descriptions.json"
    with open(desc_path, "w") as df:
        json.dump(descriptions, df)
    logger.info(f"Descriptions written to {desc_path} ({len(descriptions)} jobs)")

    json.dump(output, sys.stdout, indent=2)
    logger.info(f"Done: {len(jobs)} found → {len(scored)} scored → {len(filtered)} passed filter")


if __name__ == "__main__":
    main()
