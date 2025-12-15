#!/usr/bin/env python3
"""
Migrate existing LinkedIn URLs to canonical format.

This script normalizes all LinkedIn job URLs in the database to the canonical
format: https://linkedin.com/jobs/view/<jobId>

This removes country subdomains (de.linkedin.com), slugified titles, and
query parameters, keeping only the essential job ID.

Usage:
    python scripts/normalize_linkedin_urls.py [--dry-run]

Options:
    --dry-run    Show what would be migrated without actually doing it
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo import MongoClient
from dotenv import load_dotenv

from src.services.linkedin_scraper import normalize_linkedin_url

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_db_client() -> MongoClient:
    """Get MongoDB client from environment variables."""
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        raise ValueError("MONGO_URI environment variable not set")
    return MongoClient(mongo_uri)


def normalize_urls(dry_run: bool = False) -> dict:
    """
    Normalize all LinkedIn URLs in the database.

    Args:
        dry_run: If True, only show what would be changed without making changes

    Returns:
        Dictionary with migration statistics
    """
    stats = {
        "total_jobs": 0,
        "linkedin_jobs": 0,
        "already_normalized": 0,
        "normalized": 0,
        "failed": 0,
        "non_linkedin": 0,
    }

    client = get_db_client()
    try:
        db_name = os.getenv("MONGO_DB_NAME", "jobs")
        db = client[db_name]
        collection = db["level-2"]

        # Find all jobs with LinkedIn URLs
        # Check both job_url and jobUrl fields
        linkedin_query = {
            "$or": [
                {"job_url": {"$regex": "linkedin", "$options": "i"}},
                {"jobUrl": {"$regex": "linkedin", "$options": "i"}},
            ]
        }

        jobs = list(collection.find(linkedin_query, {"_id": 1, "job_url": 1, "jobUrl": 1, "title": 1}))
        stats["total_jobs"] = collection.count_documents({})
        stats["linkedin_jobs"] = len(jobs)

        logger.info(f"Found {stats['linkedin_jobs']} LinkedIn jobs out of {stats['total_jobs']} total jobs")

        for job in jobs:
            job_id = job["_id"]
            current_url = job.get("job_url") or job.get("jobUrl")
            title = job.get("title", "Unknown")

            if not current_url:
                continue

            normalized_url = normalize_linkedin_url(current_url)

            if normalized_url is None:
                # Not a valid LinkedIn URL
                stats["non_linkedin"] += 1
                logger.warning(f"Could not normalize URL for job '{title}': {current_url}")
                continue

            if normalized_url == current_url:
                # Already normalized
                stats["already_normalized"] += 1
                continue

            # URL needs normalization
            if dry_run:
                logger.info(f"[DRY RUN] Would normalize: {current_url} -> {normalized_url}")
                stats["normalized"] += 1
            else:
                try:
                    result = collection.update_one(
                        {"_id": job_id},
                        {
                            "$set": {
                                "job_url": normalized_url,
                                "jobUrl": normalized_url,
                                "linkedin_url_normalized_at": datetime.now(timezone.utc),
                            }
                        },
                    )
                    if result.modified_count > 0:
                        stats["normalized"] += 1
                        logger.info(f"Normalized: {current_url} -> {normalized_url}")
                    else:
                        stats["failed"] += 1
                        logger.warning(f"Failed to update job {job_id}")
                except Exception as e:
                    stats["failed"] += 1
                    logger.error(f"Error updating job {job_id}: {e}")

        return stats

    finally:
        client.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Normalize LinkedIn job URLs to canonical format"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("LinkedIn URL Normalization Script")
    logger.info("=" * 60)

    if args.dry_run:
        logger.info("Running in DRY RUN mode - no changes will be made")

    stats = normalize_urls(dry_run=args.dry_run)

    logger.info("=" * 60)
    logger.info("Summary:")
    logger.info(f"  Total jobs in database:     {stats['total_jobs']}")
    logger.info(f"  LinkedIn jobs found:        {stats['linkedin_jobs']}")
    logger.info(f"  Already normalized:         {stats['already_normalized']}")
    logger.info(f"  {'Would normalize' if args.dry_run else 'Normalized'}:            {stats['normalized']}")
    logger.info(f"  Failed:                     {stats['failed']}")
    logger.info(f"  Invalid LinkedIn URLs:      {stats['non_linkedin']}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
