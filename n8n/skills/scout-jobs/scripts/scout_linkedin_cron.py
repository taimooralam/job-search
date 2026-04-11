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

# Add skill root to path
_SKILL_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _SKILL_ROOT)
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for sibling script imports

try:
    from dotenv import load_dotenv
    load_dotenv(Path(_SKILL_ROOT) / ".env")
except ImportError:
    pass  # In container, env vars come from docker-compose

from pymongo import MongoClient

from scripts.scout_linkedin_jobs import (
    SEARCH_PROFILES,
    search_jobs,
)
from src.common.proxy_pool import ProxyPool
from src.common.dedupe import generate_dedupe_key
from src.common.scout_queue import enqueue_jobs
from src.common.telegram import send_telegram
from src.common.blacklist import filter_blacklisted

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_TIME_FILTER = "r43200"  # last 12 hours
MAX_PAGES = 1


def _parse_time_window(value: str) -> str:
    """Convert human-readable time window to LinkedIn f_TPR value.

    Examples: '30m' -> 'r1800', '1h' -> 'r3600', '12h' -> 'r43200', '1d' -> 'r86400'
    """
    import re as _re
    m = _re.match(r"^(\d+)(m|h|d)$", value.strip().lower())
    if not m:
        raise ValueError(f"Invalid time window '{value}'. Use format like 30m, 1h, 12h, 1d")
    num, unit = int(m.group(1)), m.group(2)
    seconds = num * {"m": 60, "h": 3600, "d": 86400}[unit]
    return f"r{seconds}"

SEARCH_COMBOS = [
    # (region, remote_only, few_applicants, profile_override)
    # Each region searched with and without remote filter
    ("asia_pacific", False, True,  None),
    ("asia_pacific", True,  True,  None),
    ("mena",         False, True,  None),
    ("mena",         True,  True,  None),
    ("pakistan",      False, True,  None),
    ("pakistan",      True,  True,  None),
    ("eea",          False, True,  None),
    ("eea",          True,  True,  None),
    # GCC priority — wider net (no few_applicants filter), both profiles
    ("gcc_priority", False, False, None),
    ("gcc_priority", True,  False, None),
    ("gcc_priority", False, False, "ai_leadership"),
    ("gcc_priority", True,  False, "ai_leadership"),
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


def run_all_searches(
    region_filter: Optional[str] = None,
    profile_filter: Optional[str] = None,
    dry_run: bool = False,
    limit: Optional[int] = None,
    no_proxy: bool = False,
) -> int:
    """Run searches across all profiles and combos; dedup + enqueue per combo.

    Each combo's results are blacklist-filtered, deduped against MongoDB, and
    enqueued immediately so that jobs are never lost if the process dies
    mid-run.

    Args:
        region_filter: If set, only run combos matching this region.
        profile_filter: If set, only search this profile (overrides combo's profile_override).
        dry_run: If True, log what would be enqueued but don't write.
        limit: If set, stop after enqueueing this many total jobs.

    Returns:
        Total number of jobs enqueued across all combos.
    """
    seen_ids: Set[str] = set()
    total_enqueued = 0

    # Initialize proxy pool — optional, falls back to direct if unavailable
    proxy_pool: Optional[ProxyPool] = None
    if no_proxy:
        logger.info("Proxy pool skipped (--no-proxy)")
    else:
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

    db = get_db()

    for combo in SEARCH_COMBOS:
        if limit and total_enqueued >= limit:
            logger.info(f"Reached --limit {limit}, stopping early")
            break

        # Support both 3-tuple (legacy) and 4-tuple (with profile_override)
        if len(combo) == 4:
            region, remote_only, few_applicants, profile_override = combo
        else:
            region, remote_only, few_applicants = combo
            profile_override = None

        if region_filter and region != region_filter:
            continue

        # If profile_override is set, only search that profile; otherwise all
        if profile_override:
            profiles_to_search = {profile_override: SEARCH_PROFILES[profile_override]}
        else:
            profiles_to_search = SEARCH_PROFILES

        for profile_name, keywords in profiles_to_search.items():
            if profile_filter and profile_name != profile_filter:
                continue

            if limit and total_enqueued >= limit:
                logger.info(f"Reached --limit {limit}, stopping early")
                break

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

            # In-memory dedup across combos (same run)
            unique_jobs = []
            for job in jobs:
                if job["job_id"] not in seen_ids:
                    seen_ids.add(job["job_id"])
                    job["_search_profile"] = profile_name
                    unique_jobs.append(job)

            logger.info(f"  → {len(jobs)} found, {len(unique_jobs)} unique in-run")

            if not unique_jobs:
                continue

            # Blacklist filter
            unique_jobs = filter_blacklisted(unique_jobs)
            if not unique_jobs:
                logger.info("  → 0 after blacklist filter, skipping")
                continue

            # Apply limit cap before dedup to avoid unnecessary DB queries
            if limit:
                remaining = limit - total_enqueued
                unique_jobs = unique_jobs[:remaining]

            # Dedup against MongoDB immediately
            new_jobs = dedupe_against_db(unique_jobs, db)
            already_in_db = len(unique_jobs) - len(new_jobs)
            if already_in_db:
                logger.info(f"  → {already_in_db} already in DB")

            if not new_jobs:
                logger.info("  → 0 new after dedup, skipping enqueue")
                continue

            # Enqueue immediately — don't wait until the end
            if dry_run:
                logger.info(f"  [DRY RUN] Would enqueue {len(new_jobs)} jobs")
                combo_enqueued = len(new_jobs)
            else:
                combo_enqueued = enqueue_jobs(new_jobs, source_cron="hourly")
                logger.info(f"  → Enqueued {combo_enqueued} jobs (running total: {total_enqueued + combo_enqueued})")

            total_enqueued += combo_enqueued

    return total_enqueued


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
    label: str = "",
) -> bool:
    """Send Telegram summary for the search phase."""
    tag = f" {label}" if label else ""
    return send_telegram(f"&#128269;<b>Search{tag}</b>: {searched} found &#8594; {enqueued} new ({already_in_db} dupe)")


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
    parser.add_argument(
        "--region",
        type=str,
        default=None,
        help="Filter to specific region (eea, mena, asia_pacific, pakistan, gcc_priority, emea). If set, only combos matching this region run.",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Filter to specific search profile (ai, ai_leadership, staff_principal, engineering_leadership, architect). If set, only combos matching this profile run.",
    )
    parser.add_argument(
        "--remote",
        action="store_true",
        help="Add remote filter to search",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Stop after enqueueing N jobs (useful for testing, e.g. --region eea --profile ai --limit 10)",
    )
    parser.add_argument(
        "--time-window",
        type=str,
        default=None,
        metavar="WINDOW",
        help="Lookback window for job postings (e.g. 30m, 1h, 12h, 1d). Default: 12h",
    )
    parser.add_argument(
        "--no-proxy",
        action="store_true",
        help="Skip proxy pool, use direct requests (faster for testing)",
    )
    parser.add_argument(
        "--location",
        type=str,
        default=None,
        metavar="COUNTRY",
        help="Search a single country (e.g. 'United Arab Emirates'). Overrides --region.",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Resolve time window
    global TIME_FILTER
    if args.time_window:
        TIME_FILTER = _parse_time_window(args.time_window)
        logger.info(f"Time window override: {args.time_window} → {TIME_FILTER}")
    else:
        TIME_FILTER = DEFAULT_TIME_FILTER

    logger.info("=" * 60)
    logger.info(f"Scout cron started at {datetime.utcnow().isoformat()}")
    if args.region or args.profile:
        logger.info(
            f"Direct mode: region={args.region or 'all'} profile={args.profile or 'all'} "
            f"remote={args.remote} limit={args.limit}"
        )
    logger.info("=" * 60)

    if args.location or args.region or args.profile:
        # Direct mode: specific region/location + profile, search → dedup → enqueue immediately
        profile_name = args.profile or "ai"
        keywords = SEARCH_PROFILES.get(profile_name, SEARCH_PROFILES["ai_core"])

        # --location overrides --region with a single-country temp region
        if args.location:
            from scripts.scout_linkedin_jobs import REGION_CONFIGS as _RC
            region = f"_single_{args.location.replace(' ', '_').lower()}"
            _RC[region] = {"location": args.location}
            logger.info(
                f"Step 1: Searching {args.location} with profile={profile_name} "
                f"({len(keywords)} keywords) remote={args.remote}..."
            )
        else:
            region = args.region or "eea"
            logger.info(
                f"Step 1: Searching {region} with profile={profile_name} "
                f"({len(keywords)} keywords) remote={args.remote}..."
            )

        # Initialize proxy pool
        proxy_pool = None
        if args.no_proxy:
            logger.info("Proxy pool skipped (--no-proxy)")
        else:
            try:
                pool = ProxyPool()
                working = pool.initialize()
                if working >= 1:
                    proxy_pool = pool
                    logger.info(f"Proxy pool ready: {working} proxies")
            except Exception as e:
                logger.warning(f"Proxy pool failed: {e}")

        raw_jobs = search_jobs(
            keywords_list=keywords,
            time_filter=TIME_FILTER,
            regions=[region],
            max_pages=MAX_PAGES,
            limit=args.limit if args.limit else 0,
            few_applicants=not args.remote,  # few_applicants off when remote filter is on
            remote_only=args.remote,
            proxy_pool=proxy_pool,
        )
        # Tag jobs with search profile
        for job in raw_jobs:
            job["_search_profile"] = profile_name

        logger.info(f"Total unique jobs from search: {len(raw_jobs)}")

        if not raw_jobs:
            logger.info("No jobs found. Exiting.")
            return

        # Apply blacklist filter immediately
        raw_jobs = filter_blacklisted(raw_jobs)
        logger.info(f"After blacklist filter: {len(raw_jobs)}")

        # Apply --limit before DB query
        if args.limit:
            raw_jobs = raw_jobs[: args.limit]
            logger.info(f"After --limit {args.limit}: {len(raw_jobs)}")

        # Dedup against MongoDB immediately
        logger.info("Step 2: Deduplicating against MongoDB...")
        db = get_db()
        new_jobs = dedupe_against_db(raw_jobs, db)
        already_in_db = len(raw_jobs) - len(new_jobs)
        logger.info(f"After dedup: {len(new_jobs)} new jobs ({already_in_db} already in DB)")

        if not new_jobs:
            logger.info("All jobs already in DB. Exiting.")
            enqueued = 0
        elif args.dry_run:
            logger.info(f"[DRY RUN] Would enqueue {len(new_jobs)} jobs")
            enqueued = len(new_jobs)
        else:
            logger.info("Step 3: Enqueueing jobs for scraper...")
            enqueued = enqueue_jobs(new_jobs, source_cron="hourly")
            logger.info(f"Enqueued {enqueued} jobs immediately")

        searched_count = len(raw_jobs)

    else:
        # Full mode: run all SEARCH_COMBOS; each combo dedupes + enqueues incrementally
        logger.info("Step 1: Searching LinkedIn across all categories and regions (incremental)...")
        enqueued = run_all_searches(dry_run=args.dry_run, limit=args.limit, no_proxy=args.no_proxy)
        # In full mode, run_all_searches handles everything; totals are logged per-combo
        searched_count = 0  # not tracked in full mode (dedup is per-combo)
        already_in_db = 0

    # Summary
    logger.info("=" * 60)
    logger.info("Scout Cron Summary")
    if args.region or args.profile:
        logger.info(f"  Searched:      {searched_count} unique jobs from LinkedIn")
        logger.info(f"  Already in DB: {already_in_db}")
    logger.info(f"  Enqueued:      {enqueued} new jobs for scraping")
    logger.info("=" * 60)

    # Telegram notifications removed — selector sends 30-min summary instead


if __name__ == "__main__":
    main()
