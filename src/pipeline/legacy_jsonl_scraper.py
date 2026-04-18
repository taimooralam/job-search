"""Legacy JSONL scraper runner that now reuses the shared scrape logic."""

from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

from src.common.proxy_pool import load_proxy_pool
from src.common.scout_queue import (
    _append_jsonl,
    _file_lock,
    append_scored,
    dequeue_batch,
    get_queue_dir,
    move_to_dead_letter,
    purge_stale,
    queue_length,
)
from src.pipeline.scrape_common import (
    ScrapeSkipResult,
    ScrapeSuccessResult,
    classify_scrape_exception,
    evaluate_scrape_candidate,
    upsert_level1_scored_job,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("scout_scraper")

MAX_RETRIES = 3
DETAIL_FETCH_DELAY = 1.5


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the legacy JSONL scraper."""
    parser = argparse.ArgumentParser(description="Scout Scraper Cron (legacy JSONL consumer)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and score but do not write downstream state")
    parser.add_argument("--batch-size", type=int, default=15, help="Number of jobs to process per run (default: 15)")
    parser.add_argument("--no-proxy", action="store_true", help="Skip proxy rotation, use direct requests")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint used by both scraper wrappers and the VPS cron."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")

    if not _env_flag("SCOUT_SCRAPE_ENABLE_LEGACY_JSONL_CONSUMER", True):
        logger.info("Legacy JSONL scraper disabled by SCOUT_SCRAPE_ENABLE_LEGACY_JSONL_CONSUMER=false")
        return 0

    if not _check_pid_file():
        logger.info("Another scraper instance is running. Exiting.")
        return 0

    try:
        _run(args)
        return 0
    finally:
        _remove_pid_file()


def _run(args: argparse.Namespace) -> None:
    logger.info("Scraper started at %s", datetime.now(timezone.utc).isoformat())

    mongodb_uri = os.environ.get("MONGODB_URI")
    if not mongodb_uri:
        raise RuntimeError("MONGODB_URI not set in environment")
    level1 = MongoClient(mongodb_uri)["jobs"]["level-1"]

    purged = purge_stale(max_age_hours=48)
    if purged:
        logger.info("Purged %s stale entries", purged)

    batch = dequeue_batch(args.batch_size)
    if not batch:
        logger.info("Queue empty (0 jobs). Exiting.")
        return

    logger.info("Processing %s jobs (queue remaining: %s)", len(batch), queue_length())

    pool: list[str] = []
    if not args.no_proxy:
        pool = load_proxy_pool()
        logger.info("Proxy pool: %s proxies", len(pool))

    scored_count = 0
    skipped = 0
    retry_jobs: list[dict] = []
    dead_jobs: list[dict] = []

    for index, job in enumerate(batch, start=1):
        job_id = job.get("job_id", "unknown")
        retry_count = job.get("retry_count", 0)

        try:
            outcome = evaluate_scrape_candidate(job, pool=pool, use_proxy=not args.no_proxy)
            if isinstance(outcome, ScrapeSkipResult):
                skipped += 1
                if outcome.status == "skipped_blacklist":
                    logger.info("  [%s/%s] Skipped (blacklist) — %s @ %s", index, len(batch), job.get("title", ""), job.get("company", "?"))
                else:
                    logger.info("  [%s/%s] Skipped (title filter) — %s", index, len(batch), job.get("title", ""))
                continue

            assert isinstance(outcome, ScrapeSuccessResult)
            scored = outcome.scored_job
            logger.info(
                "  [%s/%s] Score: %s (%s) — %s @ %s",
                index,
                len(batch),
                scored["score"],
                scored["tier"],
                scored["title"],
                scored["company"],
            )
            if not args.dry_run:
                append_scored([scored])
                upsert_level1_scored_job(level1, scored, source="scout_scraper", status="scored")
            else:
                logger.info("  [DRY RUN] Would append scored job: %s", scored["title"])
            scored_count += 1
        except Exception as exc:
            disposition = classify_scrape_exception(exc)
            if disposition.retryable and retry_count < MAX_RETRIES:
                logger.warning("  [%s/%s] Failed %s: %s", index, len(batch), job_id, exc)
                job["retry_count"] = retry_count + 1
                retry_jobs.append(job)
            elif disposition.retryable and retry_count >= MAX_RETRIES:
                logger.warning("  [%s/%s] Failed %s after retries: %s", index, len(batch), job_id, exc)
                dead_jobs.append(job)
            else:
                logger.warning("  [%s/%s] Terminal failure %s: %s", index, len(batch), job_id, exc)
                dead_jobs.append(job)

        if index < len(batch):
            time.sleep(DETAIL_FETCH_DELAY)

    if retry_jobs:
        queue_file = get_queue_dir() / "queue.jsonl"
        with _file_lock(queue_file, exclusive=True):
            _append_jsonl(queue_file, retry_jobs)
        logger.info("Re-enqueued %s jobs for retry", len(retry_jobs))

    if dead_jobs:
        move_to_dead_letter(dead_jobs, reason=f"Failed after {MAX_RETRIES} retries")

    logger.info(
        "Scraper done: %s/%s scored, %s skipped, %s retried, %s dead-lettered",
        scored_count,
        len(batch),
        skipped,
        len(retry_jobs),
        len(dead_jobs),
    )


def _pid_file_path() -> Path:
    return get_queue_dir() / "scraper.pid"


def _check_pid_file() -> bool:
    pid_path = _pid_file_path()
    if pid_path.exists():
        try:
            old_pid = int(pid_path.read_text().strip())
            os.kill(old_pid, 0)
            return False
        except (ValueError, ProcessLookupError, PermissionError):
            pass
    pid_path.write_text(str(os.getpid()))
    return True


def _remove_pid_file() -> None:
    try:
        _pid_file_path().unlink(missing_ok=True)
    except OSError:
        pass


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
