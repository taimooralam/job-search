#!/usr/bin/env python3
"""
Scout Dimensional Selector — profile-based regional/thematic job selection.

Reads from the scored pool (scored_pool.jsonl), applies regional filters and
dimensional ranking, dedupes against MongoDB, inserts top picks, triggers pipeline.

Each profile defines: location patterns, quota, ranking boosts.

Usage:
    python scripts/scout_dimensional_selector.py --profile uae_ksa_leadership
    python scripts/scout_dimensional_selector.py --profile global_remote --dry-run -v
    python scripts/scout_dimensional_selector.py --profile eea_remote
    python scripts/scout_dimensional_selector.py --profile eea_staff_architect

Cron (VPS):
    25 0,6,12,18 * * *  cd /root/scout-cron && .venv/bin/python scripts/scout_dimensional_selector.py --profile uae_ksa_leadership >> /var/log/scout-dimensional.log 2>&1
    25 2,5,8,11,14,17,20,23 * * *  cd /root/scout-cron && .venv/bin/python scripts/scout_dimensional_selector.py --profile global_remote >> /var/log/scout-dimensional.log 2>&1
    35 0,6,12,18 * * *  cd /root/scout-cron && .venv/bin/python scripts/scout_dimensional_selector.py --profile eea_remote >> /var/log/scout-dimensional.log 2>&1
    45 0,6,12,18 * * *  cd /root/scout-cron && .venv/bin/python scripts/scout_dimensional_selector.py --profile eea_staff_architect >> /var/log/scout-dimensional.log 2>&1
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

import requests
import yaml
from pymongo import MongoClient

from src.common.scout_queue import read_pool, purge_pool
from src.common.blacklist import filter_blacklisted
from src.common.dedupe import generate_dedupe_key, normalize_for_dedupe
from src.common.telegram import send_telegram

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("scout_dimensional")

PROFILES_PATH = Path(__file__).parent.parent / "data" / "selector_profiles.yaml"
RUNNER_URL = os.getenv("RUNNER_URL", "https://runner.uqab.digital")
RUNNER_API_SECRET = os.getenv("RUNNER_API_SECRET", "")


# ---------------------------------------------------------------------------
# Profile loading
# ---------------------------------------------------------------------------


def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile from selector_profiles.yaml."""
    with open(PROFILES_PATH, "r") as f:
        profiles = yaml.safe_load(f)
    if name not in profiles:
        available = ", ".join(profiles.keys())
        raise ValueError(f"Unknown profile '{name}'. Available: {available}")
    return profiles[name]


# ---------------------------------------------------------------------------
# Location filtering
# ---------------------------------------------------------------------------

LEADERSHIP_KEYWORDS = {
    "head", "lead", "director", "vp", "vice president",
    "chief", "principal", "staff", "manager", "cto", "cio",
}

STAFF_ARCHITECT_KEYWORDS = {
    "staff", "architect", "principal", "distinguished", "fellow",
}

AI_TITLE_KEYWORDS = {
    "ai", "artificial intelligence", "machine learning", "ml",
    "llm", "genai", "deep learning", "nlp", "computer vision",
    "data scientist", "data science",
}


def matches_location(job: Dict, patterns: List[str], mode: str = "any") -> bool:
    """Check if job location matches any of the location patterns.

    Args:
        mode: "any" = location contains any pattern (default)
              "require_any" = same as "any" but stricter intent (for remote)
    """
    location = (job.get("location") or "").lower()
    title = (job.get("title") or "").lower()
    combined = f"{location} {title}"

    for pattern in patterns:
        if pattern.lower() in combined:
            return True
    return False


def compute_rank_score(job: Dict, boosts: Dict[str, int]) -> float:
    """Compute a dimensional rank score based on profile boosts."""
    score = job.get("score", 0)
    title = (job.get("title") or "").lower()
    location = (job.get("location") or "").lower()

    # Leadership boost
    if boosts.get("leadership", 0) > 0:
        for kw in LEADERSHIP_KEYWORDS:
            if kw in title:
                score += boosts["leadership"]
                break

    # Staff/architect/principal boost
    if boosts.get("staff_architect", 0) > 0:
        for kw in STAFF_ARCHITECT_KEYWORDS:
            if kw in title:
                score += boosts["staff_architect"]
                break

    # Remote boost
    if boosts.get("remote", 0) > 0:
        if "remote" in location or "remote" in title:
            score += boosts["remote"]

    # Newest boost — jobs with more recent pooled_at get a boost
    if boosts.get("newest", 0) > 0:
        try:
            pooled = datetime.fromisoformat(job.get("pooled_at", "2000-01-01"))
            age_hours = (datetime.now(timezone.utc) - pooled).total_seconds() / 3600
            if age_hours < 6:
                score += boosts["newest"]
            elif age_hours < 12:
                score += boosts["newest"] * 0.7
            elif age_hours < 24:
                score += boosts["newest"] * 0.4
        except (ValueError, TypeError):
            pass

    # AI title boost (always apply — these are AI-focused selectors)
    for kw in AI_TITLE_KEYWORDS:
        if kw in title:
            score += 3
            break

    return score


# ---------------------------------------------------------------------------
# MongoDB dedup
# ---------------------------------------------------------------------------


def dedupe_against_db(jobs: List[Dict], db) -> List[Dict]:
    """Remove jobs already in MongoDB. Two-pass: dedupeKey + company+title."""
    if not jobs:
        return []

    # Primary: dedupeKey
    dedupe_keys = []
    for job in jobs:
        jid = job.get("job_id", "")
        dedupe_keys.append(generate_dedupe_key("linkedin_scout", source_id=jid))
        dedupe_keys.append(generate_dedupe_key("linkedin_import", source_id=jid))

    existing_keys = set()
    for coll_name in ("level-2", "level-1"):
        for doc in db[coll_name].find({"dedupeKey": {"$in": dedupe_keys}}, {"dedupeKey": 1}):
            existing_keys.add(doc["dedupeKey"])

    after_primary = []
    for job in jobs:
        jid = job.get("job_id", "")
        k1 = generate_dedupe_key("linkedin_scout", source_id=jid)
        k2 = generate_dedupe_key("linkedin_import", source_id=jid)
        if k1 not in existing_keys and k2 not in existing_keys:
            after_primary.append(job)

    primary_skip = len(jobs) - len(after_primary)
    if primary_skip:
        logger.info(f"Dedup (primary): {primary_skip} already in DB")

    if not after_primary:
        return []

    # Secondary: company+title
    existing_ct = set()
    for doc in db["level-2"].find(
        {"company": {"$exists": True}, "title": {"$exists": True}},
        {"company": 1, "title": 1},
    ):
        cn = normalize_for_dedupe(doc.get("company"))
        tn = normalize_for_dedupe(doc.get("title"))
        if cn and tn:
            existing_ct.add(f"{cn}|{tn}")

    new_jobs = []
    secondary_skip = 0
    for job in after_primary:
        cn = normalize_for_dedupe(job.get("company"))
        tn = normalize_for_dedupe(job.get("title"))
        if f"{cn}|{tn}" in existing_ct:
            secondary_skip += 1
        else:
            new_jobs.append(job)

    if secondary_skip:
        logger.info(f"Dedup (secondary): {secondary_skip} by company+title")

    total_skip = primary_skip + secondary_skip
    if total_skip:
        logger.info(f"Dedup total: {total_skip} skipped, {len(new_jobs)} new")

    return new_jobs


# ---------------------------------------------------------------------------
# MongoDB insertion (reuses logic from main selector)
# ---------------------------------------------------------------------------


def insert_jobs(jobs: List[Dict], collection, source_tag: str, dry_run: bool = False) -> List[str]:
    """Insert jobs into level-2. Returns list of inserted ObjectId strings."""
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
            "score": job.get("score"),
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
            logger.info(f"[DRY RUN] Would insert: {job.get('title')} @ {job.get('company')} (score={job.get('score')})")
        else:
            result = collection.update_one(
                {"dedupeKey": doc["dedupeKey"]},
                {"$setOnInsert": doc},
                upsert=True,
            )
            if result.upserted_id:
                inserted_ids.append(str(result.upserted_id))
                logger.info(f"Inserted: {job.get('title')} @ {job.get('company')} -> {result.upserted_id}")
            else:
                logger.info(f"Skipped (exists): {job.get('title')} @ {job.get('company')}")
    return inserted_ids


# ---------------------------------------------------------------------------
# Pipeline trigger
# ---------------------------------------------------------------------------


def trigger_batch_pipeline(job_ids: List[str]) -> Dict[str, int]:
    """Queue batch-pipeline for each inserted job."""
    if not RUNNER_API_SECRET:
        logger.warning("RUNNER_API_SECRET not set — skipping pipeline trigger")
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
# Telegram
# ---------------------------------------------------------------------------


def notify(profile_name: str, pool_size: int, matched: int, inserted: int, queued: int, failed: int, jobs: List[Dict]):
    """Send Telegram summary."""
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    icon = "&#9888;" if failed > 0 else "&#9989;"
    lines = [
        f"{icon} <b>Dimensional Selector: {profile_name}</b> ({now})",
        f"Pool: {pool_size} | Region match: {matched} | Inserted: {inserted} | Queued: {queued}",
    ]
    if failed:
        lines.append(f"Queue failures: {failed}")
    if jobs:
        lines.append("")
        for j in jobs[:8]:
            lines.append(f"  &#8226; {j.get('title', '?')} @ {j.get('company', '?')} [{j.get('score', 0)}]")
    send_telegram("\n".join(lines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Scout Dimensional Selector")
    parser.add_argument("--profile", required=True, help="Profile name from selector_profiles.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Don't insert or trigger pipeline")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    profile = load_profile(args.profile)
    quota = profile["quota"]
    patterns = profile["location_patterns"]
    boosts = profile.get("rank_boosts", {})
    source_tag = profile.get("source_tag", f"scout_dim_{args.profile}")
    loc_mode = profile.get("location_mode", "any")

    logger.info("=" * 60)
    logger.info(f"Dimensional Selector [{args.profile}] started at {datetime.now(timezone.utc).isoformat()}")
    logger.info(f"  {profile.get('description', '')}")
    logger.info(f"  Quota: {quota}, Patterns: {len(patterns)}, Boosts: {boosts}")
    logger.info("=" * 60)

    # Step 1: Read pool
    pool = read_pool()
    if not pool:
        logger.info("Pool empty. Exiting.")
        return

    logger.info(f"Pool size: {len(pool)} jobs")

    # Step 2: Blacklist filter
    pool = filter_blacklisted(pool)

    # Step 3: Score > 0
    pool = [j for j in pool if j.get("score", 0) > 0]
    logger.info(f"After score>0: {len(pool)}")

    # Step 4: Location filter
    matched = [j for j in pool if matches_location(j, patterns, mode=loc_mode)]
    logger.info(f"Location match: {len(matched)}/{len(pool)}")

    if not matched:
        logger.info("No jobs match location filter. Exiting.")
        return

    # Step 5: Dedupe against MongoDB
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set")
    db = MongoClient(uri)["jobs"]
    new_jobs = dedupe_against_db(matched, db)
    logger.info(f"After DB dedup: {len(new_jobs)} new")

    if not new_jobs:
        logger.info("All matched jobs already in DB. Exiting.")
        return

    # Step 6: Dimensional ranking
    for job in new_jobs:
        job["_rank_score"] = compute_rank_score(job, boosts)

    new_jobs.sort(key=lambda j: j["_rank_score"], reverse=True)

    selected = new_jobs[:quota]
    logger.info(f"Selected top {len(selected)} (quota: {quota})")
    for i, j in enumerate(selected):
        logger.info(
            f"  #{i+1}: {j.get('title')} @ {j.get('company')} "
            f"[score={j.get('score')}, rank={j['_rank_score']:.0f}] "
            f"loc={j.get('location')}"
        )

    # Step 7: Insert
    collection = db["level-2"]
    inserted_ids = insert_jobs(selected, collection, source_tag=source_tag, dry_run=args.dry_run)

    # Step 8: Trigger pipeline
    trigger_stats = {"queued": 0, "failed": 0}
    if not args.dry_run and inserted_ids:
        logger.info("Triggering batch pipeline...")
        trigger_stats = trigger_batch_pipeline(inserted_ids)
        logger.info(f"Pipeline: queued={trigger_stats['queued']}, failed={trigger_stats['failed']}")

    # Summary
    logger.info("=" * 60)
    logger.info(f"Dimensional Selector [{args.profile}] Summary")
    logger.info(f"  Pool:           {len(pool)}")
    logger.info(f"  Location match: {len(matched)}")
    logger.info(f"  After dedup:    {len(new_jobs)}")
    logger.info(f"  Selected:       {len(selected)} (quota: {quota})")
    logger.info(f"  Inserted:       {len(inserted_ids)}")
    logger.info(f"  Pipeline queued: {trigger_stats['queued']}")
    logger.info("=" * 60)

    # Telegram
    try:
        notify(args.profile, len(pool), len(matched), len(inserted_ids),
               trigger_stats["queued"], trigger_stats["failed"], selected)
    except Exception:
        pass


if __name__ == "__main__":
    main()
