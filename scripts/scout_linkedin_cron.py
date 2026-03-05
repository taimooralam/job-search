#!/usr/bin/env python3
"""
Automated LinkedIn Scout Cron — Hourly job discovery and pipeline injection.

Searches LinkedIn across all role categories and regions, scores results,
deduplicates against MongoDB, applies category quotas, inserts selected
jobs, and triggers the batch pipeline on the runner.

Run via cron every hour:
    0 * * * * cd /root/job-runner && .venv/bin/python scripts/scout_linkedin_cron.py >> /var/log/scout-cron.log 2>&1

Or manually for testing:
    python scripts/scout_linkedin_cron.py --dry-run
    python scripts/scout_linkedin_cron.py --dry-run --verbose
"""

import argparse
import logging
import math
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Set

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

import requests
from pymongo import MongoClient

from scripts.scout_linkedin_jobs import (
    SEARCH_PROFILES,
    search_jobs,
    fetch_details_and_score,
)
from src.common.dedupe import generate_dedupe_key

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HOURLY_QUOTA = 20
MAX_US_JOBS = 5  # Cap US-located jobs per batch to prioritize international roles

# US state abbreviations for location detection
_US_STATES = (
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
)
_US_STATE_SUFFIXES = tuple(f", {s}" for s in _US_STATES)

CATEGORY_WEIGHTS = {
    "ai": 0.40,
    "leadership": 0.20,
    "engineering": 0.20,
    "architect": 0.20,
}

# Map detected_role keys from rule_scorer → category bucket
ROLE_TO_CATEGORY = {
    "ai_engineer": "ai",
    "ai_architect": "ai",
    "genai_engineer": "ai",
    "llm_engineer": "ai",
    "agentic_ai_engineer": "ai",
    "applied_ai_engineer": "ai",
    "ai_leadership": "leadership",
    # Unmapped roles fall back to "engineering"
}

TIME_FILTER = "r3600"  # last hour
MAX_PAGES = 2

# Each combo: (regions, remote_only, few_applicants)
SEARCH_COMBOS = [
    # Remote jobs everywhere — both few and many applicants
    (["remote", "us", "emea", "mena", "asia_pacific"], True, True),
    (["remote", "us", "emea", "mena", "asia_pacific"], True, False),
    # MENA & Asia-Pacific: also search non-remote (on-site/hybrid)
    (["mena", "asia_pacific"], False, True),
    (["mena", "asia_pacific"], False, False),
]

# Runner API
RUNNER_URL = os.getenv("RUNNER_URL", "https://runner.uqab.digital")
RUNNER_API_SECRET = os.getenv("RUNNER_API_SECRET", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("scout_cron")


# ---------------------------------------------------------------------------
# MongoDB
# ---------------------------------------------------------------------------


def get_db():
    """Get MongoDB database connection."""
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set in environment")
    client = MongoClient(uri)
    return client["jobs"]


# ---------------------------------------------------------------------------
# Search all combos
# ---------------------------------------------------------------------------


def run_all_searches() -> List[Dict[str, Any]]:
    """Run searches across all profiles and combos, deduped by job_id."""
    seen_ids: Set[str] = set()
    all_jobs: List[Dict[str, Any]] = []

    for regions, remote_only, few_applicants in SEARCH_COMBOS:
        for profile_name, keywords in SEARCH_PROFILES.items():
            label = (
                f"profile={profile_name} regions={regions} "
                f"remote={remote_only} few_applicants={few_applicants}"
            )
            logger.info(f"Search pass: {label}")

            # search_jobs handles per-region × per-keyword iteration internally.
            # For non-remote combos we pass regions directly; for remote combos
            # the regions list already contains "remote" which sets f_WT=2.
            #
            # When remote_only=True but the region isn't "remote", we still want
            # to search with f_WT=2 + a location filter. search_jobs doesn't
            # support that natively, so we handle it by passing just the region
            # key and relying on the remote filter being embedded in the params.
            # For the remote combo, the "remote" region already sets f_WT=2.
            #
            # Actually, looking at fetch_search_page, remote_only is a separate
            # bool passed alongside location. But search_jobs doesn't expose
            # remote_only as a parameter — it derives it from the region config.
            # So for the remote combos, "remote" is already in the region list.
            # For non-remote combos (MENA/APAC), we just use the region directly.

            jobs = search_jobs(
                keywords_list=keywords,
                time_filter=TIME_FILTER,
                regions=regions,
                max_pages=MAX_PAGES,
                few_applicants=few_applicants,
            )

            new_count = 0
            for job in jobs:
                if job["job_id"] not in seen_ids:
                    seen_ids.add(job["job_id"])
                    job["_search_profile"] = profile_name
                    all_jobs.append(job)
                    new_count += 1

            logger.info(f"  → {len(jobs)} found, {new_count} new (cumulative: {len(all_jobs)})")

    return all_jobs


# ---------------------------------------------------------------------------
# Deduplication against MongoDB
# ---------------------------------------------------------------------------


def dedupe_against_db(jobs: List[Dict[str, Any]], collection) -> List[Dict[str, Any]]:
    """Remove jobs that already exist in MongoDB level-2."""
    if not jobs:
        return []

    # Build all possible dedupe keys for each job
    dedupe_keys = []
    for job in jobs:
        # Check both source variants (scout vs import)
        dedupe_keys.append(generate_dedupe_key("linkedin_scout", source_id=job["job_id"]))
        dedupe_keys.append(generate_dedupe_key("linkedin_import", source_id=job["job_id"]))

    # Batch query
    existing = set()
    cursor = collection.find(
        {"dedupeKey": {"$in": dedupe_keys}},
        {"dedupeKey": 1},
    )
    for doc in cursor:
        existing.add(doc["dedupeKey"])

    # Filter
    new_jobs = []
    for job in jobs:
        key_scout = generate_dedupe_key("linkedin_scout", source_id=job["job_id"])
        key_import = generate_dedupe_key("linkedin_import", source_id=job["job_id"])
        if key_scout not in existing and key_import not in existing:
            new_jobs.append(job)

    skipped = len(jobs) - len(new_jobs)
    if skipped:
        logger.info(f"Dedup: {skipped} already in DB, {len(new_jobs)} new")

    return new_jobs


# ---------------------------------------------------------------------------
# Category quota selection
# ---------------------------------------------------------------------------


def categorize_job(job: Dict[str, Any]) -> str:
    """Map a scored job to a category bucket."""
    role = job.get("detected_role")
    if role and role in ROLE_TO_CATEGORY:
        return ROLE_TO_CATEGORY[role]
    # Fallback: use the search profile that found it
    return job.get("_search_profile", "engineering")


def apply_quota(jobs: List[Dict[str, Any]], quota: int = HOURLY_QUOTA) -> List[Dict[str, Any]]:
    """
    Select top jobs respecting category quotas with overflow redistribution.

    Algorithm:
    1. Group jobs by category, sort each group by score descending
    2. Allocate initial slots per category weights
    3. If a category has fewer jobs than its quota, redistribute surplus
    4. Take top-N from each category
    """
    # Group by category
    groups: Dict[str, List[Dict]] = defaultdict(list)
    for job in jobs:
        cat = categorize_job(job)
        groups[cat].append(job)

    # Sort each group by score descending
    for cat in groups:
        groups[cat].sort(key=lambda j: j.get("score", 0), reverse=True)

    # Initial allocation
    allocations = {cat: max(1, math.floor(quota * weight)) for cat, weight in CATEGORY_WEIGHTS.items()}

    # Adjust to match total quota (rounding may cause mismatch)
    allocated_total = sum(allocations.values())
    if allocated_total < quota:
        # Give extra slots to highest-weight category
        top_cat = max(CATEGORY_WEIGHTS, key=CATEGORY_WEIGHTS.get)
        allocations[top_cat] += quota - allocated_total

    # Overflow redistribution: if a category has fewer jobs than its quota,
    # redistribute surplus to other categories proportionally
    surplus = 0
    for cat in list(allocations.keys()):
        available = len(groups.get(cat, []))
        if available < allocations[cat]:
            surplus += allocations[cat] - available
            allocations[cat] = available

    # Distribute surplus to categories that have excess jobs
    if surplus > 0:
        eligible = {
            cat: CATEGORY_WEIGHTS.get(cat, 0)
            for cat in allocations
            if len(groups.get(cat, [])) > allocations[cat]
        }
        total_weight = sum(eligible.values()) or 1
        for cat, weight in eligible.items():
            extra = math.floor(surplus * weight / total_weight)
            allocations[cat] += extra

    # Select top-N from each category
    selected = []
    for cat, n in allocations.items():
        selected.extend(groups.get(cat, [])[:n])

    # Final sort by score for logging clarity
    selected.sort(key=lambda j: j.get("score", 0), reverse=True)

    # Log distribution
    dist = defaultdict(int)
    for job in selected:
        dist[categorize_job(job)] += 1
    logger.info(f"Quota selection: {dict(dist)} (total: {len(selected)}/{quota})")

    return selected[:quota]


# ---------------------------------------------------------------------------
# US location cap
# ---------------------------------------------------------------------------


def is_us_job(job: Dict[str, Any]) -> bool:
    """Detect if a job is located in the United States."""
    location = (job.get("location") or "").strip()
    if not location:
        return False
    loc_lower = location.lower()
    if "united states" in loc_lower or ", usa" in loc_lower:
        return True
    # Match ", CA", ", NY", ", TX" etc. at end of location string
    return location.endswith(_US_STATE_SUFFIXES)


def cap_us_jobs(
    selected: List[Dict[str, Any]],
    remaining_pool: List[Dict[str, Any]],
    max_us: int = MAX_US_JOBS,
) -> List[Dict[str, Any]]:
    """
    Enforce a cap on US jobs, backfilling with non-US jobs from the pool.

    Takes the selected list (from apply_quota), removes excess US jobs
    (keeping top-scored ones), and backfills from remaining_pool with
    non-US jobs sorted by score.
    """
    us_jobs = [j for j in selected if is_us_job(j)]
    non_us_jobs = [j for j in selected if not is_us_job(j)]

    if len(us_jobs) <= max_us:
        logger.info(f"US cap: {len(us_jobs)} US jobs (within limit of {max_us})")
        return selected

    # Keep top-scored US jobs up to cap
    us_jobs.sort(key=lambda j: j.get("score", 0), reverse=True)
    kept_us = us_jobs[:max_us]
    dropped_count = len(us_jobs) - max_us

    # Build set of selected job IDs to avoid duplicates when backfilling
    selected_ids = {j["job_id"] for j in kept_us + non_us_jobs}

    # Backfill from remaining pool with non-US jobs
    backfill_candidates = [
        j for j in remaining_pool
        if j["job_id"] not in selected_ids and not is_us_job(j)
    ]
    backfill_candidates.sort(key=lambda j: j.get("score", 0), reverse=True)
    backfill = backfill_candidates[:dropped_count]

    result = non_us_jobs + kept_us + backfill
    result.sort(key=lambda j: j.get("score", 0), reverse=True)

    logger.info(
        f"US cap: {len(us_jobs)} US found → kept {max_us}, "
        f"backfilled {len(backfill)} non-US jobs"
    )
    return result


# ---------------------------------------------------------------------------
# MongoDB insertion
# ---------------------------------------------------------------------------


def insert_jobs(jobs: List[Dict[str, Any]], collection, dry_run: bool = False) -> List[str]:
    """Insert jobs into MongoDB level-2. Returns list of inserted ObjectId strings."""
    inserted_ids = []

    for job in jobs:
        dedupe_key = generate_dedupe_key("linkedin_scout", source_id=job["job_id"])

        doc = {
            "company": job.get("company"),
            "title": job.get("title"),
            "location": job.get("location"),
            "jobUrl": job.get("job_url"),
            "description": job.get("description", ""),
            "dedupeKey": dedupe_key,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
            "status": "under processing",
            "batch_added_at": datetime.utcnow(),
            "source": "linkedin_scout_cron",
            "auto_discovered": True,
            "quick_score": job.get("score"),
            "quick_score_rationale": (
                f"Rule scorer: {job.get('tier')} tier, "
                f"role={job.get('detected_role')}, "
                f"seniority={job.get('seniority_level')}"
            ),
            "tier": job.get("tier"),
            "score": None,
            "starred": job.get("tier") == "A",
            "starredAt": datetime.utcnow() if job.get("tier") == "A" else None,
            "salary": None,
            "jobType": job.get("employment_type"),
            "linkedin_metadata": {
                "linkedin_job_id": job["job_id"],
                "seniority_level": job.get("seniority"),
                "employment_type": job.get("employment_type"),
                "job_function": job.get("job_function"),
                "industries": job.get("industries"),
                "rule_score_breakdown": job.get("breakdown"),
            },
        }

        if dry_run:
            logger.info(
                f"[DRY RUN] Would insert: {job.get('title')} @ {job.get('company')} "
                f"(score={job.get('score')}, tier={job.get('tier')})"
            )
        else:
            result = collection.insert_one(doc)
            inserted_ids.append(str(result.inserted_id))
            logger.info(
                f"Inserted: {job.get('title')} @ {job.get('company')} → {result.inserted_id}"
            )

    return inserted_ids


# ---------------------------------------------------------------------------
# Trigger batch pipeline
# ---------------------------------------------------------------------------


def trigger_batch_pipeline(job_ids: List[str]) -> Dict[str, int]:
    """Queue batch-pipeline for each inserted job via runner API."""
    if not RUNNER_API_SECRET:
        logger.warning("RUNNER_API_SECRET not set — skipping batch pipeline trigger")
        return {"queued": 0, "failed": 0}

    stats = {"queued": 0, "failed": 0}

    for job_id in job_ids:
        try:
            url = f"{RUNNER_URL}/api/jobs/{job_id}/operations/batch-pipeline/queue"
            resp = requests.post(
                url,
                json={"tier": "quality"},
                headers={
                    "Authorization": f"Bearer {RUNNER_API_SECRET}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            if resp.status_code in (200, 201, 202):
                stats["queued"] += 1
            else:
                logger.warning(f"Failed to queue {job_id}: HTTP {resp.status_code}")
                stats["failed"] += 1
        except requests.RequestException as e:
            logger.warning(f"Failed to queue {job_id}: {e}")
            stats["failed"] += 1

    return stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="LinkedIn Scout Cron")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Search and score but don't insert or trigger pipeline",
    )
    parser.add_argument(
        "--quota",
        type=int,
        default=HOURLY_QUOTA,
        help=f"Max jobs to insert per run (default: {HOURLY_QUOTA})",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 60)
    logger.info(f"Scout cron started at {datetime.utcnow().isoformat()}")
    logger.info("=" * 60)

    # Step 1: Search LinkedIn
    logger.info("Step 1: Searching LinkedIn across all categories and regions...")
    raw_jobs = run_all_searches()
    logger.info(f"Total unique jobs from search: {len(raw_jobs)}")

    if not raw_jobs:
        logger.info("No jobs found. Exiting.")
        return

    # Step 2: Fetch details and score
    logger.info("Step 2: Fetching job details and scoring...")
    scored_jobs = fetch_details_and_score(raw_jobs)
    logger.info(f"Scored: {len(scored_jobs)} (skipped {len(raw_jobs) - len(scored_jobs)} failures)")

    # Filter out score=0
    scored_jobs = [j for j in scored_jobs if j.get("score", 0) > 0]
    logger.info(f"After filtering score>0: {len(scored_jobs)}")

    if not scored_jobs:
        logger.info("No scored jobs remaining. Exiting.")
        return

    # Step 3: Deduplicate against MongoDB
    logger.info("Step 3: Deduplicating against MongoDB...")
    db = get_db()
    collection = db["level-2"]
    new_jobs = dedupe_against_db(scored_jobs, collection)
    logger.info(f"After dedup: {len(new_jobs)} new jobs")

    if not new_jobs:
        logger.info("All jobs already in DB. Exiting.")
        return

    # Step 4: Apply category quota
    logger.info("Step 4: Applying category quotas...")
    selected = apply_quota(new_jobs, quota=args.quota)
    logger.info(f"Selected: {len(selected)} jobs (quota: {args.quota})")

    # Step 4b: Cap US jobs and backfill with international roles
    logger.info("Step 4b: Applying US location cap...")
    selected = cap_us_jobs(selected, remaining_pool=new_jobs, max_us=MAX_US_JOBS)
    logger.info(f"After US cap: {len(selected)} jobs")

    # Step 5: Insert into MongoDB
    logger.info("Step 5: Inserting into MongoDB...")
    inserted_ids = insert_jobs(selected, collection, dry_run=args.dry_run)

    # Step 6: Trigger batch pipeline
    if not args.dry_run and inserted_ids:
        logger.info("Step 6: Triggering batch pipeline...")
        trigger_stats = trigger_batch_pipeline(inserted_ids)
        logger.info(f"Pipeline: queued={trigger_stats['queued']}, failed={trigger_stats['failed']}")
    else:
        trigger_stats = {"queued": 0, "failed": 0}

    # Summary
    logger.info("=" * 60)
    logger.info("Scout Cron Summary")
    logger.info(f"  Searched:   {len(raw_jobs)} unique jobs from LinkedIn")
    logger.info(f"  Scored:     {len(scored_jobs)} jobs with score > 0")
    logger.info(f"  New:        {len(new_jobs)} not in MongoDB")
    logger.info(f"  Selected:   {len(selected)} after quota")
    logger.info(f"  Inserted:   {len(inserted_ids)} into level-2")
    logger.info(f"  Queued:     {trigger_stats['queued']} for batch pipeline")
    if trigger_stats["failed"]:
        logger.info(f"  Failed:     {trigger_stats['failed']} queue failures")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
