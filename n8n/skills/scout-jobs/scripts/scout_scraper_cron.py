#!/usr/bin/env python3
"""
Scout Scraper Cron — Phase 2: Dequeue jobs, fetch details via proxy, score, write to scored.jsonl + level-1.

Runs every 5 minutes. Processes a batch (default 15) per run.
Inserts all scored jobs into MongoDB level-1 (status: "scored").
The selector (Phase 3) promotes top jobs from scored pool to level-2.

Cron (every 2.5 min via two entries):
    */5 * * * *    cd /root/scout-cron && .venv/bin/python scripts/scout_scraper_cron.py >> /var/log/scout-scraper.log 2>&1
    2-57/5 * * * * cd /root/scout-cron && .venv/bin/python scripts/scout_scraper_cron.py >> /var/log/scout-scraper.log 2>&1

Manual:
    python scripts/scout_scraper_cron.py --dry-run -v
    python scripts/scout_scraper_cron.py --batch-size 3 --no-proxy -v
"""

import argparse
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add skill root to path
_SKILL_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _SKILL_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(_SKILL_ROOT) / ".env")
except ImportError:
    pass  # In container, env vars come from docker-compose

from src.common.scout_queue import (
    get_queue_dir,
    dequeue_batch,
    append_scored,
    purge_stale,
    move_to_dead_letter,
    queue_length,
)
from src.common.proxy_pool import load_proxy_pool, fetch_with_proxy
from src.common.rule_scorer import compute_rule_score
from src.services.linkedin_scraper import (
    HEADERS,
    LinkedInScraperError,
    RateLimitError,
    _parse_job_html,
    extract_job_id,
)
from src.common.blacklist import is_blacklisted
from src.common.telegram import send_telegram
from src.common.dedupe import generate_dedupe_key

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("scout_scraper")

MAX_RETRIES = 3
DETAIL_FETCH_DELAY = 1.5  # seconds between fetches

# Title must contain at least one AI/tech signal to be worth scraping.
# This is a allowlist approach — if the title has zero tech relevance, skip it.
# Title must match at least one pattern to be worth scraping.
# Uses word-boundary regex to avoid substring false positives (e.g. "chain" matching "ai").
_TITLE_PATTERNS = re.compile(
    r"\b("
    # AI/ML core
    r"ai|artificial.intelligence|machine.learning|ml|"
    r"llm|genai|gen.ai|generative|gpt|"
    r"nlp|natural.language|deep.learning|neural|"
    r"computer.vision|agentic|rag|"
    # Engineering roles
    r"software.engineer|backend.engineer|full.stack|fullstack|"
    r"platform.engineer|cloud.engineer|devops|sre|"
    r"data.engineer|data.scientist|data.science|"
    r"developer|programmer|"
    # Architecture (tech)
    r"solution.architect|cloud.architect|system.architect|"
    r"enterprise.architect|technical.architect|it.architect|"
    r"data.architect|infrastructure.architect|"
    # Leadership with tech signal
    r"head.of.ai|head.of.data|head.of.engineering|"
    r"head.of.genai|head.of.llm|head.of.ml|"
    r"cto|vp.engineer|"
    r"tech.lead|engineering.lead|engineering.manager|"
    # Senior IC signals — keep principal/staff/founding titles in scope
    r"principal.engineer|staff.engineer|founding.engineer|"
    r"principal.architect|staff.architect|"
    # Director-level AI/tech leadership
    r"director.of.ai|director.ai|ai.director|"
    r"director.of.engineering|director.engineering|"
    # Researcher
    r"research.scientist|researcher|applied.scientist|"
    # AI-specific variants
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


def _title_passes_filter(title: str) -> bool:
    """Quick title check — require at least one tech/AI signal in the title."""
    return bool(_TITLE_PATTERNS.search(title))


# ---------------------------------------------------------------------------
# PID file overlap protection
# ---------------------------------------------------------------------------


def _pid_file_path() -> Path:
    return get_queue_dir() / "scraper.pid"


def _check_pid_file() -> bool:
    """Check if another scraper instance is running.

    Returns:
        True if safe to proceed, False if another instance is running.
    """
    pid_path = _pid_file_path()
    if pid_path.exists():
        try:
            old_pid = int(pid_path.read_text().strip())
            # Check if process is still alive
            os.kill(old_pid, 0)
            # Process exists
            return False
        except (ValueError, ProcessLookupError, PermissionError):
            # PID file is stale — process no longer exists
            pass
    # Write our PID
    pid_path.write_text(str(os.getpid()))
    return True


def _remove_pid_file():
    try:
        _pid_file_path().unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Scrape + Score
# ---------------------------------------------------------------------------

LINKEDIN_JOB_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"


def scrape_and_score(job: dict, pool: list, use_proxy: bool = True) -> dict:
    """Fetch job details and compute rule score.

    Args:
        job: Queue entry dict with job_id, job_url, etc.
        pool: Proxy pool for fetch_with_proxy
        use_proxy: Whether to use proxies (False for --no-proxy)

    Returns:
        Scored job dict ready for scored.jsonl

    Raises:
        LinkedInScraperError: On scrape failure
        Exception: On unexpected errors
    """
    job_id = job["job_id"]
    url = LINKEDIN_JOB_URL.format(job_id=job_id)

    # Fetch HTML
    if use_proxy and pool:
        response = fetch_with_proxy(url, headers=HEADERS, timeout=15, pool=pool)
    else:
        import requests
        response = requests.get(url, headers=HEADERS, timeout=15)

    if response.status_code == 429:
        raise RateLimitError(f"Rate limited on {job_id}")
    if response.status_code == 404:
        raise LinkedInScraperError(f"Job {job_id} not found (404)")
    if response.status_code != 200:
        raise LinkedInScraperError(f"HTTP {response.status_code} for {job_id}")

    # Parse HTML
    job_data = _parse_job_html(job_id, response.text)

    # Score
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

    return {
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
        "breakdown": result["breakdown"],
        "search_profile": job.get("search_profile", ""),
        "source_cron": job.get("source_cron", ""),
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Scout Scraper Cron (Phase 2)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and score but don't write to scored.jsonl",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=15,
        help="Number of jobs to process per run (default: 15)",
    )
    parser.add_argument(
        "--no-proxy",
        action="store_true",
        help="Skip proxy rotation, use direct requests",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # PID file check
    if not _check_pid_file():
        logger.info("Another scraper instance is running. Exiting.")
        return

    try:
        _run(args)
    finally:
        _remove_pid_file()


def _run(args):
    logger.info(f"Scraper started at {datetime.now(timezone.utc).isoformat()}")

    # MongoDB connection for level-1 insertion
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGODB_URI"])["jobs"]
    level1 = db["level-1"]

    # Purge stale queue entries
    purged = purge_stale(max_age_hours=48)
    if purged:
        logger.info(f"Purged {purged} stale entries")

    # Dequeue batch
    batch = dequeue_batch(args.batch_size)
    if not batch:
        logger.info(f"Queue empty (0 jobs). Exiting.")
        return

    logger.info(f"Processing {len(batch)} jobs (queue remaining: {queue_length()})")

    # Load proxy pool
    pool = []
    if not args.no_proxy:
        pool = load_proxy_pool()
        logger.info(f"Proxy pool: {len(pool)} proxies")

    # Process each job
    scored_count = 0
    retry_jobs = []
    dead_jobs = []

    skipped = 0
    for i, job in enumerate(batch):
        job_id = job.get("job_id", "unknown")
        retry_count = job.get("retry_count", 0)
        title = job.get("title", "")

        # Skip blacklisted companies before wasting a proxy request
        if is_blacklisted(job):
            skipped += 1
            logger.info(f"  [{i + 1}/{len(batch)}] Skipped (blacklist) — {title} @ {job.get('company', '?')}")
            continue

        # Skip obviously irrelevant titles before wasting a proxy request
        if title and not _title_passes_filter(title):
            skipped += 1
            logger.info(f"  [{i + 1}/{len(batch)}] Skipped (title filter) — {title}")
            continue

        try:
            scored = scrape_and_score(job, pool, use_proxy=not args.no_proxy)
            logger.info(
                f"  [{i + 1}/{len(batch)}] Score: {scored['score']} ({scored['tier']}) "
                f"— {scored['title']} @ {scored['company']}"
            )
            # Write each scored job immediately — never batch at the end
            if not args.dry_run:
                append_scored([scored])
                # Insert to level-1 for tracking all scored jobs
                dk = generate_dedupe_key("linkedin_scout", source_id=scored["job_id"])
                level1.update_one(
                    {"dedupeKey": dk},
                    {"$setOnInsert": {
                        "company": scored["company"], "title": scored["title"],
                        "location": scored["location"], "jobUrl": scored["job_url"],
                        "dedupeKey": dk, "createdAt": datetime.now(timezone.utc),
                        "source": "scout_scraper", "auto_discovered": True,
                        "quick_score": scored["score"], "tier": scored["tier"],
                        "status": "scored", "description": scored.get("description", ""),
                        "detected_role": scored.get("detected_role"),
                        "linkedin_metadata": {
                            "linkedin_job_id": scored["job_id"],
                            "seniority_level": scored.get("seniority"),
                            "employment_type": scored.get("employment_type"),
                            "rule_score_breakdown": scored.get("breakdown"),
                        },
                    }},
                    upsert=True,
                )
            else:
                logger.info(f"  [DRY RUN] Would append scored job: {scored['title']}")
            scored_count += 1
        except RateLimitError as e:
            logger.warning(f"  [{i + 1}/{len(batch)}] Rate limited: {job_id} — {e}")
            # Always re-enqueue rate limits (don't count as retry)
            retry_jobs.append(job)
        except Exception as e:
            logger.warning(f"  [{i + 1}/{len(batch)}] Failed {job_id}: {e}")
            if retry_count < MAX_RETRIES:
                job["retry_count"] = retry_count + 1
                retry_jobs.append(job)
            else:
                dead_jobs.append(job)

        if i < len(batch) - 1:
            time.sleep(DETAIL_FETCH_DELAY)

    # Re-enqueue retries
    if retry_jobs:
        from src.common.scout_queue import enqueue_jobs as _raw_enqueue, get_queue_dir, _file_lock, _read_jsonl, _append_jsonl
        queue_file = get_queue_dir() / "queue.jsonl"
        with _file_lock(queue_file, exclusive=True):
            _append_jsonl(queue_file, retry_jobs)
        logger.info(f"Re-enqueued {len(retry_jobs)} jobs for retry")

    # Dead letter
    if dead_jobs:
        move_to_dead_letter(dead_jobs, reason=f"Failed after {MAX_RETRIES} retries")

    # Summary
    logger.info(
        f"Scraper done: {scored_count}/{len(batch)} scored, "
        f"{skipped} skipped, {len(retry_jobs)} retried, {len(dead_jobs)} dead-lettered"
    )

    # Telegram (only if we actually processed jobs)
    if scored_count > 0 or skipped > 0:
        try:
            send_telegram(
                f"&#9881; <b>Scraper</b>: {len(batch)} dequeued &#8594; "
                f"{scored_count} scored, {skipped} skipped &#8594; {scored_count} to L1"
            )
        except Exception:
            pass


if __name__ == "__main__":
    main()
