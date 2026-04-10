#!/usr/bin/env python3
"""
6-Hourly AI Scout — Search-only phase for AI roles.

Searches LinkedIn for AI roles only across all regions with 24-hour lookback,
deduplicates against MongoDB, and enqueues new jobs to queue.jsonl for the
scraper cron (Phase 2) to process.

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

# Add skill root to path
_SKILL_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _SKILL_ROOT)
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for sibling script imports

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # In container, env vars come from docker-compose

from pymongo import MongoClient

from scripts.scout_linkedin_jobs import (
    SEARCH_PROFILES,
    search_jobs,
)
from src.common.dedupe import generate_dedupe_key
from src.common.scout_queue import enqueue_jobs
from src.common.telegram import send_telegram

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TIME_FILTER = "r86400"  # 24 hours
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


def run_all_searches(dry_run: bool = False) -> int:
    """Run searches across AI profiles and all combos; dedup + enqueue per combo.

    Each combo's results are deduped against MongoDB and enqueued immediately
    so that jobs are never lost if the process dies mid-run.

    Args:
        dry_run: If True, log what would be enqueued but don't write.

    Returns:
        Total number of jobs enqueued across all combos.
    """
    seen_ids: Set[str] = set()
    total_enqueued = 0
    ai_keywords = SEARCH_PROFILES["ai"]

    db = get_db()

    for region, remote_only, few_applicants in SEARCH_COMBOS:
        label = (
            f"region={region} remote={remote_only} "
            f"few_applicants={few_applicants}"
        )
        logger.info(f"Search pass: {label}")

        jobs = search_jobs(
            keywords_list=ai_keywords,
            time_filter=TIME_FILTER,
            regions=[region],
            max_pages=MAX_PAGES,
            few_applicants=few_applicants,
            remote_only=remote_only,
        )

        # In-memory dedup across combos (same run)
        unique_jobs = []
        for job in jobs:
            if job["job_id"] not in seen_ids:
                seen_ids.add(job["job_id"])
                job["_search_profile"] = "ai"
                unique_jobs.append(job)

        logger.info(f"  -> {len(jobs)} found, {len(unique_jobs)} unique in-run")

        if not unique_jobs:
            continue

        # Dedup against MongoDB immediately
        new_jobs = dedupe_against_db(unique_jobs, db)
        already_in_db = len(unique_jobs) - len(new_jobs)
        if already_in_db:
            logger.info(f"  -> {already_in_db} already in DB")

        if not new_jobs:
            logger.info("  -> 0 new after dedup, skipping enqueue")
            continue

        # Enqueue immediately — don't wait until the end
        if dry_run:
            logger.info(f"  [DRY RUN] Would enqueue {len(new_jobs)} jobs")
            combo_enqueued = len(new_jobs)
        else:
            combo_enqueued = enqueue_jobs(new_jobs, source_cron="ai_top15", search_profile="ai")
            logger.info(f"  -> Enqueued {combo_enqueued} jobs (running total: {total_enqueued + combo_enqueued})")

        total_enqueued += combo_enqueued

    return total_enqueued


# ---------------------------------------------------------------------------
# Deduplication against MongoDB
# ---------------------------------------------------------------------------


def dedupe_against_db(jobs: List[Dict[str, Any]], db) -> List[Dict[str, Any]]:
    """Remove jobs that already exist in MongoDB (checks both level-1 and level-2)."""
    if not jobs:
        return []

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
    """Send Telegram summary for the AI search phase."""
    from datetime import timezone
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")

    lines = [
        f"&#128269; <b>AI Top-15 Search</b> ({now})",
        f"Searched: {searched} unique AI jobs (24h window)",
        f"Already in DB: {already_in_db}",
        f"Enqueued: {enqueued} new jobs",
    ]
    return send_telegram("\n".join(lines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="AI Top-15 Scout (Search-Only)")
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
    logger.info(f"AI Top-15 Scout started at {datetime.utcnow().isoformat()}")
    logger.info(f"Config: time_filter={TIME_FILTER}, max_pages={MAX_PAGES}")
    logger.info("=" * 60)

    # Search LinkedIn (AI profiles only); dedup + enqueue incrementally per combo
    logger.info("Step 1: Searching LinkedIn (AI profiles, 24h window, incremental)...")
    enqueued = run_all_searches(dry_run=args.dry_run)

    # Summary
    logger.info("=" * 60)
    logger.info("AI Top-15 Scout Summary")
    logger.info(f"  Enqueued: {enqueued} new jobs for scraping")
    logger.info("=" * 60)

    # Notify via Telegram (non-blocking, best-effort)
    try:
        notify_search_complete(
            searched=0,   # not tracked in incremental mode (dedup is per-combo)
            already_in_db=0,
            enqueued=enqueued,
        )
    except Exception:
        pass  # Telegram is best-effort, never block cron


if __name__ == "__main__":
    main()
