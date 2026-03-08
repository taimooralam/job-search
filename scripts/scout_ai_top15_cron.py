#!/usr/bin/env python3
"""
6-Hourly AI Scout — Top 15 AI jobs worldwide with 24-hour lookback.

Searches LinkedIn for AI roles only across all regions, scores results,
deduplicates against MongoDB, selects top 15 by score, inserts into
level-2, and triggers the batch pipeline.

Run via cron every 6 hours:
    5 */6 * * * cd /root/scout-cron && .venv/bin/python scripts/scout_ai_top15_cron.py >> /var/log/scout-ai-top15.log 2>&1

Or manually for testing:
    python scripts/scout_ai_top15_cron.py --dry-run
    python scripts/scout_ai_top15_cron.py --dry-run --verbose
"""

import argparse
import logging
import os
import sys
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
from src.common.dedupe import generate_dedupe_key, consolidate_by_location
from src.common.telegram import send_telegram

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

QUOTA = 9
TIME_FILTER = "r86400"  # 24 hours
MAX_PAGES = 3

SEARCH_COMBOS = [
    # Global remote — catches remote roles worldwide without location bias
    (["remote"], True, True),
    (["remote"], True, False),
    # Priority regions — on-site/hybrid roles in target geographies
    (["emea", "pakistan", "asia_pacific"], False, True),
    (["emea", "pakistan", "asia_pacific"], False, False),
]

# Runner API
RUNNER_URL = os.getenv("RUNNER_URL", "https://runner.uqab.digital")
RUNNER_API_SECRET = os.getenv("RUNNER_API_SECRET", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("scout_ai_top15")


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
# Search (AI profiles only)
# ---------------------------------------------------------------------------


def run_all_searches() -> List[Dict[str, Any]]:
    """Run searches across AI profiles and all combos, deduped by job_id."""
    seen_ids: Set[str] = set()
    all_jobs: List[Dict[str, Any]] = []
    ai_keywords = SEARCH_PROFILES["ai"]

    for regions, remote_only, few_applicants in SEARCH_COMBOS:
        label = (
            f"regions={regions} remote={remote_only} "
            f"few_applicants={few_applicants}"
        )
        logger.info(f"Search pass: {label}")

        jobs = search_jobs(
            keywords_list=ai_keywords,
            time_filter=TIME_FILTER,
            regions=regions,
            max_pages=MAX_PAGES,
            few_applicants=few_applicants,
        )

        new_count = 0
        for job in jobs:
            if job["job_id"] not in seen_ids:
                seen_ids.add(job["job_id"])
                job["_search_profile"] = "ai"
                all_jobs.append(job)
                new_count += 1

        logger.info(f"  -> {len(jobs)} found, {new_count} new (cumulative: {len(all_jobs)})")

    return all_jobs


# ---------------------------------------------------------------------------
# Deduplication against MongoDB
# ---------------------------------------------------------------------------


def dedupe_against_db(jobs: List[Dict[str, Any]], collection) -> List[Dict[str, Any]]:
    """Remove jobs that already exist in MongoDB level-2."""
    if not jobs:
        return []

    dedupe_keys = []
    for job in jobs:
        dedupe_keys.append(generate_dedupe_key("linkedin_scout", source_id=job["job_id"]))
        dedupe_keys.append(generate_dedupe_key("linkedin_import", source_id=job["job_id"]))

    existing = set()
    cursor = collection.find(
        {"dedupeKey": {"$in": dedupe_keys}},
        {"dedupeKey": 1},
    )
    for doc in cursor:
        existing.add(doc["dedupeKey"])

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
            "source": "linkedin_scout_ai_top15",
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
                f"Inserted: {job.get('title')} @ {job.get('company')} -> {result.inserted_id}"
            )

    return inserted_ids


# ---------------------------------------------------------------------------
# Trigger batch pipeline
# ---------------------------------------------------------------------------


def trigger_batch_pipeline(job_ids: List[str]) -> Dict[str, int]:
    """Queue batch-pipeline for each inserted job via runner API."""
    if not RUNNER_API_SECRET:
        logger.warning("RUNNER_API_SECRET not set -- skipping batch pipeline trigger")
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
# Telegram notification
# ---------------------------------------------------------------------------


def notify_ai_top15_complete(
    searched: int,
    scored: int,
    new_after_dedup: int,
    inserted: int,
    queued: int,
    failed: int = 0,
) -> bool:
    """Send Telegram summary for the 6-hourly AI top-15 cron."""
    from datetime import timezone

    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    status = "&#9888;" if failed > 0 else "&#9989;"

    lines = [
        f"{status} <b>AI Top-15 Scout</b> ({now})",
        f"Searched: {searched} | Scored: {scored}",
        f"New: {new_after_dedup} | Inserted: {inserted}",
        f"Queued: {queued}",
    ]
    if failed > 0:
        lines.append(f"Queue failures: {failed}")

    return send_telegram("\n".join(lines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="AI Top-15 Scout (6-hourly)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Search and score but don't insert or trigger pipeline",
    )
    parser.add_argument(
        "--quota",
        type=int,
        default=QUOTA,
        help=f"Max jobs to insert per run (default: {QUOTA})",
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
    logger.info(f"AI Top-15 Scout started at {datetime.utcnow().isoformat()}")
    logger.info(f"Config: quota={args.quota}, time_filter={TIME_FILTER}, max_pages={MAX_PAGES}")
    logger.info("=" * 60)

    # Step 1: Search LinkedIn (AI profiles only)
    logger.info("Step 1: Searching LinkedIn (AI profiles, 24h window)...")
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

    # Step 2b: Cross-location dedup
    logger.info("Step 2b: Consolidating cross-location duplicates...")
    scored_jobs = consolidate_by_location(scored_jobs)
    logger.info(f"After cross-location dedup: {len(scored_jobs)}")

    # Step 3: Deduplicate against MongoDB
    logger.info("Step 3: Deduplicating against MongoDB...")
    db = get_db()
    collection = db["level-2"]
    new_jobs = dedupe_against_db(scored_jobs, collection)
    logger.info(f"After dedup: {len(new_jobs)} new jobs")

    if not new_jobs:
        logger.info("All jobs already in DB. Exiting.")
        return

    # Step 4: Sort by score descending, take top N (no category weighting)
    logger.info("Step 4: Selecting top jobs by score...")
    new_jobs.sort(key=lambda j: j.get("score", 0), reverse=True)
    selected = new_jobs[:args.quota]
    logger.info(f"Selected: {len(selected)} jobs (quota: {args.quota})")

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
    logger.info("AI Top-15 Scout Summary")
    logger.info(f"  Searched:   {len(raw_jobs)} unique jobs from LinkedIn")
    logger.info(f"  Scored:     {len(scored_jobs)} jobs with score > 0")
    logger.info(f"  New:        {len(new_jobs)} not in MongoDB")
    logger.info(f"  Selected:   {len(selected)} after quota (cap: {args.quota})")
    logger.info(f"  Inserted:   {len(inserted_ids)} into level-2")
    logger.info(f"  Queued:     {trigger_stats['queued']} for batch pipeline")
    if trigger_stats["failed"]:
        logger.info(f"  Failed:     {trigger_stats['failed']} queue failures")
    logger.info("=" * 60)

    # Notify via Telegram (non-blocking, best-effort)
    try:
        notify_ai_top15_complete(
            searched=len(raw_jobs),
            scored=len(scored_jobs),
            new_after_dedup=len(new_jobs),
            inserted=len(inserted_ids),
            queued=trigger_stats["queued"],
            failed=trigger_stats["failed"],
        )
    except Exception:
        pass  # Telegram is best-effort, never block cron


if __name__ == "__main__":
    main()
