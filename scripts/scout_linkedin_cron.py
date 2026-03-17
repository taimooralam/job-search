#!/usr/bin/env python3
"""
Automated LinkedIn Scout Cron — Hourly job discovery (search-only).

Searches LinkedIn across all role categories and regions, deduplicates
against MongoDB (pre-filter known IDs), and enqueues new jobs to
queue.jsonl for the scraper cron (Phase 2) to process.

Run via cron every 3 hours:
    5 */3 * * * cd /root/scout-cron && .venv/bin/python scripts/scout_linkedin_cron.py >> /var/log/scout-cron.log 2>&1

Or manually for testing:
    python scripts/scout_linkedin_cron.py --dry-run
    python scripts/scout_linkedin_cron.py --dry-run --verbose
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from pymongo import MongoClient

from scripts.scout_linkedin_jobs import (
    SEARCH_PROFILES,
    search_jobs,
)
from src.common.proxy_pool import ProxyPool
from src.common.dedupe import generate_dedupe_key
from src.common.scout_queue import enqueue_jobs
from src.common.telegram import send_telegram

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TIME_FILTER = "r43200"  # last 12 hours
MAX_PAGES = 1

SEARCH_COMBOS = [
    # (region, remote_only, few_applicants)
    # Each region searched with and without remote filter
    ("asia_pacific", False, True),
    ("asia_pacific", True,  True),
    ("mena",         False, True),
    ("mena",         True,  True),
    ("pakistan",      False, True),
    ("pakistan",      True,  True),
    ("eea",          False, True),
    ("eea",          True,  True),
]

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

    # Initialize proxy pool — optional, falls back to direct if unavailable
    proxy_pool: Optional[ProxyPool] = None
    try:
        pool = ProxyPool()
        working = pool.initialize()
        if working >= 1:
            proxy_pool = pool
            logger.info(f"Proxy pool ready: {working} working proxies")
        else:
            logger.warning("Proxy pool returned 0 working proxies — using direct requests")
    except Exception as e:
        logger.warning(f"Proxy pool initialization failed: {e} — using direct requests")

    for region, remote_only, few_applicants in SEARCH_COMBOS:
        for profile_name, keywords in SEARCH_PROFILES.items():
            label = (
                f"profile={profile_name} region={region} "
                f"remote={remote_only} few_applicants={few_applicants}"
            )
            logger.info(f"Search pass: {label}")

            jobs = search_jobs(
                keywords_list=keywords,
                time_filter=TIME_FILTER,
                regions=[region],
                max_pages=MAX_PAGES,
                few_applicants=few_applicants,
                remote_only=remote_only,
                proxy_pool=proxy_pool,
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


def dedupe_against_db(jobs: List[Dict[str, Any]], db) -> List[Dict[str, Any]]:
    """Remove jobs that already exist in MongoDB (checks both level-1 and level-2)."""
    if not jobs:
        return []

    # Build all possible dedupe keys for each job
    dedupe_keys = []
    for job in jobs:
        dedupe_keys.append(generate_dedupe_key("linkedin_scout", source_id=job["job_id"]))
        dedupe_keys.append(generate_dedupe_key("linkedin_import", source_id=job["job_id"]))

    # Batch query both collections
    existing = set()
    for coll_name in ("level-2", "level-1"):
        cursor = db[coll_name].find(
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
# Telegram notification
# ---------------------------------------------------------------------------


def notify_search_complete(
    searched: int,
    already_in_db: int,
    enqueued: int,
) -> bool:
    """Send Telegram summary for the search phase."""
    from datetime import timezone
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")

    lines = [
        f"&#128269; <b>Scout Search</b> ({now})",
        f"Searched: {searched} unique jobs",
        f"Already in DB: {already_in_db}",
        f"Enqueued: {enqueued} new jobs",
    ]
    return send_telegram("\n".join(lines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="LinkedIn Scout Cron (Search-Only)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Search and dedupe but don't enqueue",
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

    # Step 2: Pre-filter against MongoDB (avoid enqueueing known jobs)
    logger.info("Step 2: Deduplicating against MongoDB...")
    db = get_db()
    new_jobs = dedupe_against_db(raw_jobs, db)
    already_in_db = len(raw_jobs) - len(new_jobs)
    logger.info(f"After dedup: {len(new_jobs)} new jobs ({already_in_db} already in DB)")

    if not new_jobs:
        logger.info("All jobs already in DB. Exiting.")
        return

    # Step 3: Enqueue for scraper
    if args.dry_run:
        logger.info(f"[DRY RUN] Would enqueue {len(new_jobs)} jobs")
        enqueued = len(new_jobs)
    else:
        logger.info("Step 3: Enqueueing jobs for scraper...")
        enqueued = enqueue_jobs(new_jobs, source_cron="hourly")

    # Summary
    logger.info("=" * 60)
    logger.info("Scout Cron Summary")
    logger.info(f"  Searched:     {len(raw_jobs)} unique jobs from LinkedIn")
    logger.info(f"  Already in DB: {already_in_db}")
    logger.info(f"  Enqueued:     {enqueued} new jobs for scraping")
    logger.info("=" * 60)

    # Notify via Telegram (non-blocking, best-effort)
    try:
        notify_search_complete(
            searched=len(raw_jobs),
            already_in_db=already_in_db,
            enqueued=enqueued,
        )
    except Exception:
        pass  # Telegram is best-effort, never block cron


if __name__ == "__main__":
    main()
