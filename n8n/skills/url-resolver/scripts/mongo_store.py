"""MongoDB storage layer for URL Resolver.

Queries and updates the `level-2` collection in the VPS MongoDB `jobs` database.
Finds jobs missing direct application URLs and records resolution results.
"""

import os
from datetime import datetime, timezone

from pymongo import MongoClient

from utils import setup_logging

logger = setup_logging("url-resolver-mongo")

# Singleton client — reused across calls within a process
_client: MongoClient | None = None


def get_db():
    """Return the `jobs` database handle, creating the client on first call."""
    global _client
    if _client is None:
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            raise RuntimeError("MONGODB_URI environment variable is not set")
        _client = MongoClient(uri)
    return _client["jobs"]


def get_jobs_needing_urls(limit: int = 10) -> list[dict]:
    """Find jobs that need application URL resolution.

    Criteria:
    - status == "under processing"
    - application_url is missing, null, empty, OR contains "linkedin.com"
    - url_resolution_attempts < max_resolution_attempts (default 3)
    """
    db = get_db()
    query = {
        "status": "under processing",
        "$or": [
            {"application_url": {"$exists": False}},
            {"application_url": None},
            {"application_url": ""},
            {"application_url": {"$regex": r"linkedin\.com", "$options": "i"}},
        ],
        "$expr": {
            "$lt": [
                {"$ifNull": ["$url_resolution_attempts", 0]},
                3,
            ]
        },
    }
    jobs = list(
        db["level-2"]
        .find(query)
        .sort("created_at", -1)
        .limit(limit)
    )
    logger.info("Found %d jobs needing URL resolution", len(jobs))
    return jobs


def update_resolved_url(
    job_id,
    url: str,
    source: str,
    confidence: float,
) -> None:
    """Update a job with a resolved application URL and tracking fields."""
    db = get_db()
    db["level-2"].update_one(
        {"_id": job_id},
        {
            "$set": {
                "application_url": url,
                "url_resolved_at": datetime.now(timezone.utc),
                "url_resolution_source": source,
                "url_resolution_confidence": confidence,
                "has_resolved_url": True,
            },
            "$inc": {"url_resolution_attempts": 1},
        },
    )
    logger.info("Updated job %s with URL: %s (confidence: %.2f)", job_id, url, confidence)


def increment_attempt(job_id, error: str) -> None:
    """Increment the attempt counter and record the error on failure."""
    db = get_db()
    db["level-2"].update_one(
        {"_id": job_id},
        {
            "$inc": {"url_resolution_attempts": 1},
            "$set": {
                "url_resolution_last_error": error,
            },
        },
    )
    logger.warning("Incremented attempt for job %s: %s", job_id, error)


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test URL Resolver MongoDB operations")
    parser.add_argument("--test", action="store_true", help="Run basic query test")
    args = parser.parse_args()

    if args.test:
        db = get_db()
        logger.info("Connected to MongoDB: %s", db.name)
        logger.info("Collections: %s", db.list_collection_names())

        jobs = get_jobs_needing_urls(limit=3)
        for job in jobs:
            logger.info(
                "Job: %s @ %s — current URL: %s — attempts: %d",
                job.get("title", "Unknown"),
                job.get("company", "Unknown"),
                job.get("application_url", "<none>"),
                job.get("url_resolution_attempts", 0),
            )
