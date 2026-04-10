#!/usr/bin/env python3
"""
Scout Selector Cron — Phase 3: Global rank all scored jobs, apply quotas, insert, trigger pipeline.

Runs at :55 past every 3rd hour — just before the next search cycle.
Reads ALL scored jobs from the cycle, ranks globally, applies quotas,
inserts into MongoDB, and triggers the batch pipeline.

Cron:
    55 2,5,8,11,14,17,20,23 * * *  cd /root/scout-cron && .venv/bin/python scripts/scout_selector_cron.py >> /var/log/scout-selector.log 2>&1

Manual:
    python scripts/scout_selector_cron.py --dry-run -v
    python scripts/scout_selector_cron.py --dry-run --hourly-quota 3 --ai-quota 7 -v
"""

import argparse
import json
import logging
import math
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Add skill root to path
_SKILL_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _SKILL_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # In container, env vars come from docker-compose

import requests
from pymongo import MongoClient

from src.common.scout_queue import read_and_clear_scored, append_to_pool, purge_pool
from src.common.dedupe import generate_dedupe_key, consolidate_by_location
from src.common.telegram import send_telegram
from src.common.blacklist import filter_blacklisted

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("scout_selector")

# ---------------------------------------------------------------------------
# Discarded jobs log — keeps jobs not selected by quota for debugging
# ---------------------------------------------------------------------------

DISCARDED_PATH = Path(os.getenv("SCOUT_QUEUE_DIR", str(Path(_SKILL_ROOT) / "data" / "scout"))) / "discarded.jsonl"
DISCARDED_MAX_AGE_SECONDS = 3 * 86400  # 3 days


def _append_discarded(jobs: List[Dict]) -> None:
    """Append discarded jobs to discarded.jsonl with a timestamp."""
    now = datetime.now(timezone.utc).isoformat()
    with open(DISCARDED_PATH, "a") as f:
        for job in jobs:
            job["discarded_at"] = now
            f.write(json.dumps(job) + "\n")


def _purge_old_discarded() -> int:
    """Remove entries older than 3 days from discarded.jsonl. Returns count purged."""
    if not DISCARDED_PATH.exists():
        return 0
    cutoff = time.time() - DISCARDED_MAX_AGE_SECONDS
    kept = []
    purged = 0
    for line in DISCARDED_PATH.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            ts = datetime.fromisoformat(entry.get("discarded_at", "2000-01-01"))
            if ts.timestamp() >= cutoff:
                kept.append(line)
            else:
                purged += 1
        except (json.JSONDecodeError, ValueError):
            purged += 1
    if purged:
        DISCARDED_PATH.write_text("\n".join(kept) + "\n" if kept else "")
    return purged


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HOURLY_QUOTA = 1   # jobs per 3h cycle from hourly cron
AI_TOP15_QUOTA = 0  # jobs per 3h cycle from ai_top15 cron

CATEGORY_WEIGHTS = {
    "ai": 1.0,
}

ROLE_TO_CATEGORY = {
    "ai_engineer": "ai",
    "ai_architect": "ai",
    "genai_engineer": "ai",
    "llm_engineer": "ai",
    "agentic_ai_engineer": "ai",
    "applied_ai_engineer": "ai",
}

# Runner API
RUNNER_URL = os.getenv("RUNNER_URL", "https://runner.uqab.digital")
RUNNER_API_SECRET = os.getenv("RUNNER_API_SECRET", "")


# ---------------------------------------------------------------------------
# MongoDB
# ---------------------------------------------------------------------------


def get_db():
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set in environment")
    client = MongoClient(uri)
    return client["jobs"]


# ---------------------------------------------------------------------------
# Deduplication against MongoDB
# ---------------------------------------------------------------------------


def dedupe_against_db(jobs: List[Dict[str, Any]], db) -> List[Dict[str, Any]]:
    """Remove jobs that already exist in MongoDB (checks both level-1 and level-2).

    Two-pass deduplication:
    1. Primary: exact dedupeKey match (linkedin_scout|<job_id> or linkedin_import|<job_id>)
    2. Secondary: normalized company+title match against level-2, catching the same job
       posted with a different LinkedIn job_id (e.g. different location variants).
    """
    from src.common.dedupe import normalize_for_dedupe

    if not jobs:
        return []

    # --- Primary dedup: exact dedupeKey match ---
    dedupe_keys = []
    for job in jobs:
        dedupe_keys.append(generate_dedupe_key("linkedin_scout", source_id=job["job_id"]))
        dedupe_keys.append(generate_dedupe_key("linkedin_import", source_id=job["job_id"]))

    # Batch query both collections
    existing_keys = set()
    for coll_name in ("level-2", "level-1"):
        cursor = db[coll_name].find(
            {"dedupeKey": {"$in": dedupe_keys}},
            {"dedupeKey": 1},
        )
        for doc in cursor:
            existing_keys.add(doc["dedupeKey"])

    after_primary = []
    for job in jobs:
        key_scout = generate_dedupe_key("linkedin_scout", source_id=job["job_id"])
        key_import = generate_dedupe_key("linkedin_import", source_id=job["job_id"])
        if key_scout not in existing_keys and key_import not in existing_keys:
            after_primary.append(job)

    primary_skipped = len(jobs) - len(after_primary)
    if primary_skipped:
        logger.info(f"Dedup (primary): {primary_skipped} already in DB by dedupeKey")

    if not after_primary:
        return []

    # --- Secondary dedup: normalized company+title match in level-2 ---
    # Builds a set of "company_norm|title_norm" strings already in level-2 so
    # that the same job posted under a fresh LinkedIn job_id is still caught.
    existing_ct: set = set()
    cursor = db["level-2"].find(
        {"company": {"$exists": True}, "title": {"$exists": True}},
        {"company": 1, "title": 1},
    )
    for doc in cursor:
        company_norm = normalize_for_dedupe(doc.get("company"))
        title_norm = normalize_for_dedupe(doc.get("title"))
        if company_norm and title_norm:
            existing_ct.add(f"{company_norm}|{title_norm}")

    new_jobs = []
    secondary_skipped = 0
    for job in after_primary:
        company_norm = normalize_for_dedupe(job.get("company"))
        title_norm = normalize_for_dedupe(job.get("title"))
        ct_key = f"{company_norm}|{title_norm}"
        if ct_key in existing_ct:
            secondary_skipped += 1
            logger.debug(
                f"Dedup (secondary): skipping '{job.get('title')} @ {job.get('company')}' "
                f"— same company+title already in level-2"
            )
        else:
            new_jobs.append(job)

    if secondary_skipped:
        logger.info(
            f"Dedup (secondary): {secondary_skipped} already in DB by company+title"
        )

    total_skipped = primary_skipped + secondary_skipped
    if total_skipped:
        logger.info(f"Dedup total: {total_skipped} skipped, {len(new_jobs)} new")

    return new_jobs


# ---------------------------------------------------------------------------
# Category quota selection (for hourly cron jobs)
# ---------------------------------------------------------------------------


def categorize_job(job: Dict[str, Any]) -> str:
    role = job.get("detected_role")
    if role and role in ROLE_TO_CATEGORY:
        return ROLE_TO_CATEGORY[role]
    return job.get("search_profile", "engineering")


def apply_quota(jobs: List[Dict[str, Any]], quota: int) -> List[Dict[str, Any]]:
    """Select top jobs respecting category quotas with overflow redistribution."""
    groups: Dict[str, List[Dict]] = defaultdict(list)
    for job in jobs:
        cat = categorize_job(job)
        groups[cat].append(job)

    for cat in groups:
        groups[cat].sort(key=lambda j: j.get("score", 0), reverse=True)

    allocations = {cat: max(1, math.floor(quota * weight)) for cat, weight in CATEGORY_WEIGHTS.items()}

    allocated_total = sum(allocations.values())
    if allocated_total < quota:
        top_cat = max(CATEGORY_WEIGHTS, key=CATEGORY_WEIGHTS.get)
        allocations[top_cat] += quota - allocated_total

    # Overflow redistribution
    surplus = 0
    for cat in list(allocations.keys()):
        available = len(groups.get(cat, []))
        if available < allocations[cat]:
            surplus += allocations[cat] - available
            allocations[cat] = available

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

    selected = []
    for cat, n in allocations.items():
        selected.extend(groups.get(cat, [])[:n])

    selected.sort(key=lambda j: j.get("score", 0), reverse=True)

    dist = defaultdict(int)
    for job in selected:
        dist[categorize_job(job)] += 1
    logger.info(f"Quota selection: {dict(dist)} (total: {len(selected)}/{quota})")

    return selected[:quota]


# ---------------------------------------------------------------------------
# MongoDB insertion
# ---------------------------------------------------------------------------


def insert_jobs(
    jobs: List[Dict[str, Any]],
    collection,
    source_tag: str = "linkedin_scout_cron",
    dry_run: bool = False,
) -> List[str]:
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
            "source": source_tag,
            "auto_discovered": True,
            "quick_score": job.get("score"),
            "quick_score_rationale": (
                f"Rule scorer: {job.get('tier')} tier, "
                f"role={job.get('detected_role')}, "
                f"seniority={job.get('seniority_level')}"
            ),
            "tier": job.get("tier"),
            "score": job.get("score"),  # Seed with rule score; full LLM score overwrites later
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
            result = collection.update_one(
                {"dedupeKey": doc["dedupeKey"]},
                {"$setOnInsert": doc},
                upsert=True,
            )
            if result.upserted_id is not None:
                inserted_ids.append(str(result.upserted_id))
                logger.info(
                    f"Inserted: {job.get('title')} @ {job.get('company')} -> {result.upserted_id}"
                )
            else:
                logger.info(
                    f"Skipped (already exists): {job.get('title')} @ {job.get('company')}"
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
# Telegram notification
# ---------------------------------------------------------------------------


def notify_selector_complete(
    total_scored: int,
    hourly_selected: int,
    ai_selected: int,
    inserted: int,
    queued: int,
    failed: int = 0,
    job_summaries: List[str] = None,
) -> bool:
    """Send Telegram summary when selector finishes scoring and queues pipeline."""
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    status = "&#9888;" if failed > 0 else "&#9989;"

    lines = [
        f"{status} <b>Scout Selector</b> ({now})",
        f"Scored pool: {total_scored} jobs",
        f"Selected: {hourly_selected} hourly + {ai_selected} ai_top15",
        f"Inserted: {inserted} | Pipeline queued: {queued}",
    ]
    if failed > 0:
        lines.append(f"Queue failures: {failed}")

    if job_summaries:
        lines.append("")
        lines.append("<b>Jobs queued to pipeline:</b>")
        for summary in job_summaries[:10]:  # Cap at 10 for message length
            lines.append(f"  • {summary}")

    return send_telegram("\n".join(lines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Scout Selector Cron (Phase 3)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Rank and select but don't insert or trigger pipeline",
    )
    parser.add_argument(
        "--hourly-quota",
        type=int,
        default=HOURLY_QUOTA,
        help=f"Max hourly-cron jobs to insert (default: {HOURLY_QUOTA})",
    )
    parser.add_argument(
        "--ai-quota",
        type=int,
        default=AI_TOP15_QUOTA,
        help=f"Max ai_top15-cron jobs to insert (default: {AI_TOP15_QUOTA})",
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
    logger.info(f"Scout Selector started at {datetime.now(timezone.utc).isoformat()}")
    logger.info("=" * 60)

    # Step 0: Purge old discarded entries (>3 days) and stale pool entries (>48h)
    purged = _purge_old_discarded()
    if purged:
        logger.info(f"Purged {purged} old entries from discarded.jsonl")
    purge_pool()

    # Step 1: Read and clear scored.jsonl (atomic)
    scored_jobs = read_and_clear_scored()
    if not scored_jobs:
        logger.info("No scored jobs. Exiting.")
        return

    logger.info(f"Read {len(scored_jobs)} scored jobs from scored.jsonl")

    # Step 1b: Apply blacklist filter
    scored_jobs = filter_blacklisted(scored_jobs)
    logger.info(f"After blacklist filter: {len(scored_jobs)}")

    # Step 2: Filter score > 0
    scored_jobs = [j for j in scored_jobs if j.get("score", 0) > 0]
    logger.info(f"After score>0 filter: {len(scored_jobs)}")

    if not scored_jobs:
        logger.info("No jobs with score > 0. Exiting.")
        return

    # Step 3: Cross-location dedup
    logger.info("Consolidating cross-location duplicates...")
    scored_jobs = consolidate_by_location(scored_jobs)
    logger.info(f"After cross-location dedup: {len(scored_jobs)}")

    # Step 4: Dedupe against MongoDB
    logger.info("Deduplicating against MongoDB...")
    db = get_db()
    collection = db["level-2"]  # Inserts still go to level-2
    new_jobs = dedupe_against_db(scored_jobs, db)
    logger.info(f"After DB dedup: {len(new_jobs)} new jobs")

    # Step 4b: Feed scored pool for dimensional selectors
    append_to_pool(new_jobs if new_jobs else [])

    if not new_jobs:
        logger.info("All jobs already in DB. Exiting.")
        return

    # Step 5: Split by source_cron and apply quotas
    hourly_jobs = [j for j in new_jobs if j.get("source_cron") == "hourly"]
    ai_jobs = [j for j in new_jobs if j.get("source_cron") == "ai_top15"]
    other_jobs = [j for j in new_jobs if j.get("source_cron") not in ("hourly", "ai_top15")]

    logger.info(f"By source: hourly={len(hourly_jobs)}, ai_top15={len(ai_jobs)}, other={len(other_jobs)}")

    # Hourly: category-weighted quota
    selected_hourly = []
    if hourly_jobs:
        selected_hourly = apply_quota(hourly_jobs, quota=args.hourly_quota)
        logger.info(f"Hourly selected: {len(selected_hourly)} (quota: {args.hourly_quota})")

    # AI top-15: simple top-N by score
    selected_ai = []
    if ai_jobs:
        ai_jobs.sort(key=lambda j: j.get("score", 0), reverse=True)
        selected_ai = ai_jobs[:args.ai_quota]
        logger.info(f"AI top-15 selected: {len(selected_ai)} (quota: {args.ai_quota})")

    # Other (shouldn't happen, but handle gracefully): top-3 by score
    selected_other = []
    if other_jobs:
        other_jobs.sort(key=lambda j: j.get("score", 0), reverse=True)
        selected_other = other_jobs[:3]
        logger.info(f"Other selected: {len(selected_other)}")

    all_selected = selected_hourly + selected_ai + selected_other

    # Insert discarded jobs into level-1 (discovered but not promoted to level-2)
    selected_ids = {j.get("job_id") for j in all_selected}
    discarded = [j for j in new_jobs if j.get("job_id") not in selected_ids]
    if discarded:
        _append_discarded(discarded)  # Keep file log for debugging
        if not args.dry_run:
            level1 = db["level-1"]
            level1_inserted = 0
            for job in discarded:
                dedupe_key = generate_dedupe_key("linkedin_scout", source_id=job["job_id"])
                result = level1.update_one(
                    {"dedupeKey": dedupe_key},
                    {"$setOnInsert": {
                        "company": job.get("company"),
                        "title": job.get("title"),
                        "location": job.get("location"),
                        "jobUrl": job.get("job_url"),
                        "dedupeKey": dedupe_key,
                        "createdAt": datetime.utcnow(),
                        "source": "scout_discarded",
                        "auto_discovered": True,
                        "quick_score": job.get("score"),
                        "tier": job.get("tier"),
                        "status": "discovered",
                        "linkedin_metadata": {
                            "linkedin_job_id": job["job_id"],
                            "seniority_level": job.get("seniority"),
                            "employment_type": job.get("employment_type"),
                        },
                    }},
                    upsert=True,
                )
                if result.upserted_id:
                    level1_inserted += 1
            logger.info(f"Discarded: {len(discarded)} total, {level1_inserted} new inserted to level-1")

    if not all_selected:
        logger.info("No jobs selected after quotas. Exiting.")
        return

    # Step 6: Insert into MongoDB
    logger.info(f"Inserting {len(all_selected)} jobs into MongoDB...")

    # Insert hourly jobs with hourly source tag
    hourly_ids = []
    if selected_hourly:
        hourly_ids = insert_jobs(
            selected_hourly, collection,
            source_tag="linkedin_scout_cron",
            dry_run=args.dry_run,
        )

    # Insert AI jobs with ai_top15 source tag
    ai_ids = []
    if selected_ai:
        ai_ids = insert_jobs(
            selected_ai, collection,
            source_tag="linkedin_scout_ai_top15",
            dry_run=args.dry_run,
        )

    # Insert other jobs
    other_ids = []
    if selected_other:
        other_ids = insert_jobs(
            selected_other, collection,
            source_tag="linkedin_scout_cron",
            dry_run=args.dry_run,
        )

    all_inserted_ids = hourly_ids + ai_ids + other_ids

    # Step 7: Trigger batch pipeline
    trigger_stats = {"queued": 0, "failed": 0}
    if not args.dry_run and all_inserted_ids:
        logger.info("Triggering batch pipeline...")
        trigger_stats = trigger_batch_pipeline(all_inserted_ids)
        logger.info(f"Pipeline: queued={trigger_stats['queued']}, failed={trigger_stats['failed']}")

    # Summary
    logger.info("=" * 60)
    logger.info("Selector Summary")
    logger.info(f"  Scored pool:     {len(scored_jobs)} jobs")
    logger.info(f"  Hourly selected: {len(selected_hourly)} (quota: {args.hourly_quota})")
    logger.info(f"  AI selected:     {len(selected_ai)} (quota: {args.ai_quota})")
    logger.info(f"  Total inserted:  {len(all_inserted_ids)}")
    logger.info(f"  Pipeline queued: {trigger_stats['queued']}")
    if trigger_stats["failed"]:
        logger.info(f"  Queue failures:  {trigger_stats['failed']}")
    logger.info("=" * 60)

    # Build job summaries for Telegram
    job_summaries = []
    for job in all_selected:
        src = job.get("source_cron", "?")
        job_summaries.append(
            f"{job.get('title', '?')} @ {job.get('company', '?')} "
            f"[{job.get('tier', '?')}/{job.get('score', 0)}] ({src})"
        )

    # Telegram notification
    try:
        notify_selector_complete(
            total_scored=len(scored_jobs),
            hourly_selected=len(selected_hourly),
            ai_selected=len(selected_ai),
            inserted=len(all_inserted_ids),
            queued=trigger_stats["queued"],
            failed=trigger_stats["failed"],
            job_summaries=job_summaries,
        )
    except Exception:
        pass  # Best-effort


if __name__ == "__main__":
    main()
