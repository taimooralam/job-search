#!/usr/bin/env python3
"""
Automated Job Ingestion Cron Script

Fetches jobs from multiple sources, scores them, and ingests high-scoring
jobs into the MongoDB level-2 collection.

Supports incremental fetching (only new jobs since last run) via --incremental flag.

Run via cron every hour (recommended with incremental):
    0 * * * * cd /path/to/job-search && .venv/bin/python scripts/ingest_jobs_cron.py --incremental

Run via cron every 6 hours (legacy full fetch):
    0 */6 * * * cd /path/to/job-search && .venv/bin/python scripts/ingest_jobs_cron.py

Or manually for testing:
    python scripts/ingest_jobs_cron.py --dry-run
    python scripts/ingest_jobs_cron.py --source himalaya --incremental
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Load environment before other imports
load_dotenv()

from pymongo import MongoClient

from src.common.config import Config
from src.common.ingest_config import get_ingest_config, IngestConfig
from src.services.job_sources import IndeedSource, HimalayasSource, JobSource, JobData
from src.services.quick_scorer import quick_score_job, derive_tier_from_score


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("job_ingestion")


def get_db():
    """Get MongoDB database connection."""
    client = MongoClient(Config.MONGODB_URI)
    return client["jobs"]


def generate_dedupe_key(job: JobData, source_name: str) -> str:
    """
    Generate a deduplication key for a job.

    Format: company|title|location|source (lowercase, normalized)
    """
    company = (job.company or "").lower().strip()
    title = (job.title or "").lower().strip()
    location = (job.location or "").lower().strip()

    return f"{company}|{title}|{location}|{source_name}"


def create_job_document(
    job: JobData,
    source_name: str,
    score: int,
    rationale: str,
) -> Dict[str, Any]:
    """
    Create a MongoDB document for a job.

    Follows the level-2 schema from linkedin_scraper.py.
    """
    return {
        "company": job.company,
        "title": job.title,
        "location": job.location,
        "jobUrl": job.url,
        "description": job.description,
        "dedupeKey": generate_dedupe_key(job, source_name),
        "createdAt": datetime.utcnow(),
        "status": "not processed",
        "source": source_name,
        "auto_discovered": True,
        "quick_score": score,
        "quick_score_rationale": rationale,
        "tier": derive_tier_from_score(score),
        # Optional fields
        "salary": job.salary,
        "jobType": job.job_type,
        "postedDate": job.posted_date,
        "sourceId": job.source_id,
    }


def run_ingestion(
    config: IngestConfig,
    dry_run: bool = False,
    skip_scoring: bool = False,
) -> Dict[str, Any]:
    """
    Run the job ingestion pipeline.

    Args:
        config: Ingestion configuration
        dry_run: If True, don't actually insert jobs
        skip_scoring: If True, skip LLM scoring (for testing)

    Returns:
        Statistics dictionary
    """
    if not config.enabled:
        logger.info("Auto-ingestion is disabled")
        return {"status": "disabled"}

    db = get_db()
    collection = db["level-2"]

    stats = {
        "start_time": datetime.utcnow().isoformat(),
        "fetched": 0,
        "scored": 0,
        "ingested": 0,
        "duplicates": 0,
        "below_threshold": 0,
        "errors": 0,
        "sources": {},
        "dry_run": dry_run,
    }

    # Initialize sources
    sources: List[tuple[JobSource, List[dict]]] = []

    # Add Indeed source with all search configs
    indeed_source = IndeedSource()
    indeed_configs = config.get_indeed_search_configs()
    if indeed_configs:
        sources.append((indeed_source, indeed_configs))
        logger.info(f"Queued {len(indeed_configs)} Indeed search configs")

    # Add Himalayas source
    himalayas_source = HimalayasSource()
    himalayas_config = config.get_himalayas_config()
    if himalayas_config.get("keywords") or not indeed_configs:
        # Always include Himalayas if no Indeed configs, or if keywords specified
        sources.append((himalayas_source, [himalayas_config]))
        logger.info("Queued Himalayas source")

    if not sources:
        logger.warning("No job sources configured. Check INDEED_SEARCH_TERMS or HIMALAYAS_KEYWORDS")
        stats["status"] = "no_sources"
        return stats

    # Process each source
    for source, search_configs in sources:
        source_name = source.get_source_name()
        source_stats = {"fetched": 0, "ingested": 0, "duplicates": 0, "errors": 0}

        for search_config in search_configs:
            try:
                # Fetch jobs
                jobs = source.fetch_jobs(search_config)
                source_stats["fetched"] += len(jobs)
                stats["fetched"] += len(jobs)

                # Process each job
                for job in jobs:
                    try:
                        # Check for duplicates
                        dedupe_key = generate_dedupe_key(job, source_name)
                        if collection.find_one({"dedupeKey": dedupe_key}):
                            stats["duplicates"] += 1
                            source_stats["duplicates"] += 1
                            continue

                        # Quick score
                        if skip_scoring:
                            score, rationale = 75, "Scoring skipped (test mode)"
                        else:
                            score, rationale = quick_score_job(
                                title=job.title,
                                company=job.company,
                                location=job.location,
                                description=job.description or "",
                            )
                        stats["scored"] += 1

                        # Check threshold
                        if score is None or score < config.score_threshold:
                            stats["below_threshold"] += 1
                            logger.debug(
                                f"Below threshold: {job.company} - {job.title} "
                                f"(score: {score}, threshold: {config.score_threshold})"
                            )
                            continue

                        # Create document
                        doc = create_job_document(job, source_name, score, rationale or "")

                        # Insert if not dry run
                        if not dry_run:
                            collection.insert_one(doc)
                            logger.info(
                                f"Ingested: {job.company} - {job.title} "
                                f"(score: {score}, tier: {doc['tier']})"
                            )
                        else:
                            logger.info(
                                f"[DRY RUN] Would ingest: {job.company} - {job.title} "
                                f"(score: {score})"
                            )

                        stats["ingested"] += 1
                        source_stats["ingested"] += 1

                    except Exception as e:
                        logger.error(f"Error processing job {job.company} - {job.title}: {e}")
                        stats["errors"] += 1
                        source_stats["errors"] += 1

            except Exception as e:
                logger.error(f"Error fetching from {source_name}: {e}")
                stats["errors"] += 1
                source_stats["errors"] += 1

        stats["sources"][source_name] = source_stats

    stats["end_time"] = datetime.utcnow().isoformat()
    stats["status"] = "completed"

    # Log summary
    logger.info(
        f"Ingestion complete: fetched={stats['fetched']}, "
        f"scored={stats['scored']}, ingested={stats['ingested']}, "
        f"duplicates={stats['duplicates']}, below_threshold={stats['below_threshold']}, "
        f"errors={stats['errors']}"
    )

    return stats


def save_run_stats(stats: Dict[str, Any], output_dir: Optional[Path] = None):
    """Save run statistics to a JSON file."""
    if output_dir is None:
        output_dir = Path(__file__).parent.parent / "logs"

    output_dir.mkdir(parents=True, exist_ok=True)

    # Save latest run
    latest_file = output_dir / "ingest_latest.json"
    with open(latest_file, "w") as f:
        json.dump(stats, f, indent=2, default=str)

    # Save timestamped run
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    history_file = output_dir / f"ingest_{timestamp}.json"
    with open(history_file, "w") as f:
        json.dump(stats, f, indent=2, default=str)

    logger.info(f"Stats saved to {latest_file}")


async def run_incremental_ingestion(
    source_name: str,
    config: IngestConfig,
    dry_run: bool = False,
    skip_scoring: bool = False,
    use_claude_scorer: bool = False,
) -> Dict[str, Any]:
    """
    Run incremental ingestion using IngestService.

    This mode uses the system_state collection to track last fetch time
    and only processes new jobs since then.

    Args:
        source_name: Source to fetch from ("himalaya" or "indeed")
        config: Ingestion configuration
        dry_run: If True, don't actually insert jobs
        skip_scoring: If True, skip LLM scoring
        use_claude_scorer: If True, use Claude CLI for scoring

    Returns:
        Statistics dictionary
    """
    from src.services.job_ingest_service import IngestService

    db = get_db()
    ingest_service = IngestService(db, use_claude_scorer=use_claude_scorer)

    # Determine source and fetch jobs
    if source_name == "himalaya":
        source = HimalayasSource()
        # Use Indeed search terms as keywords (user preference)
        keywords = config.indeed_search_terms or config.himalayas_keywords
        search_config = {
            "keywords": keywords,
            "max_results": config.himalayas_max_results,
            "worldwide_only": config.himalayas_worldwide_only,
        }
        source_key = "himalayas_auto"
    else:
        # Indeed not yet supported for incremental (would need to track per-search-config)
        logger.warning("Incremental mode not yet supported for Indeed, falling back to full fetch")
        return run_ingestion(config, dry_run, skip_scoring)

    logger.info(f"Running incremental ingestion for {source_key}")

    # Fetch jobs
    jobs = source.fetch_jobs(search_config)
    logger.info(f"Fetched {len(jobs)} jobs from {source_key}")

    if not jobs:
        return {
            "status": "completed",
            "source": source_key,
            "fetched": 0,
            "ingested": 0,
            "mode": "incremental",
        }

    # Use IngestService for processing
    if dry_run:
        # Dry run - just count without inserting
        last_fetch = ingest_service.get_last_fetch_timestamp(source_key)
        new_jobs = [j for j in jobs if not last_fetch or (j.posted_date and j.posted_date > last_fetch)]
        return {
            "status": "dry_run",
            "source": source_key,
            "fetched": len(jobs),
            "new_since_last_fetch": len(new_jobs),
            "last_fetch_at": last_fetch.isoformat() if last_fetch else None,
            "mode": "incremental",
        }

    # Run actual ingestion
    result = await ingest_service.ingest_jobs(
        jobs=jobs,
        source_name=source_key,
        score_threshold=config.score_threshold,
        skip_scoring=skip_scoring,
        incremental=True,
    )

    return {
        "status": "completed",
        "source": source_key,
        "mode": "incremental",
        **result.to_dict()["stats"],
        "last_fetch_at": result.last_fetch_at.isoformat() if result.last_fetch_at else None,
    }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Automated job ingestion from Indeed and Himalayas"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and score jobs but don't insert into database",
    )
    parser.add_argument(
        "--skip-scoring",
        action="store_true",
        help="Skip LLM scoring (for testing)",
    )
    parser.add_argument(
        "--no-stats",
        action="store_true",
        help="Don't save run statistics to file",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (debug) logging",
    )
    parser.add_argument(
        "--source",
        choices=["himalaya", "indeed", "all"],
        default="all",
        help="Source to fetch from (default: all)",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Only fetch jobs newer than last run (uses system_state collection)",
    )
    parser.add_argument(
        "--use-claude",
        action="store_true",
        help="Use Claude CLI for scoring (free with Max subscription)",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("Starting job ingestion...")

    # Load config
    config = get_ingest_config()
    logger.info(
        f"Config: enabled={config.enabled}, threshold={config.score_threshold}, "
        f"indeed_terms={config.indeed_search_terms}, "
        f"himalayas_keywords={config.himalayas_keywords}"
    )

    # Run appropriate ingestion mode
    if args.incremental and args.source in ["himalaya", "all"]:
        # Use new incremental mode with IngestService
        logger.info("Running in incremental mode")
        try:
            stats = asyncio.run(run_incremental_ingestion(
                source_name="himalaya",
                config=config,
                dry_run=args.dry_run,
                skip_scoring=args.skip_scoring,
                use_claude_scorer=args.use_claude,
            ))
        except Exception as e:
            # SAFETY: Fall back to legacy mode if incremental fails
            logger.error(f"Incremental mode failed: {e}. Falling back to legacy mode.")
            stats = run_ingestion(
                config=config,
                dry_run=args.dry_run,
                skip_scoring=args.skip_scoring,
            )
    else:
        # Use legacy full fetch mode
        stats = run_ingestion(
            config=config,
            dry_run=args.dry_run,
            skip_scoring=args.skip_scoring,
        )

    # Save stats
    if not args.no_stats:
        save_run_stats(stats)

    # Exit with error code if there were errors
    if stats.get("errors", 0) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
