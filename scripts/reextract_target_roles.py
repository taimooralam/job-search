#!/usr/bin/env python3
"""
Re-extract JDs for specific target roles.

Queries MongoDB level-2 for jobs matching specific title patterns
and re-extracts them (even if already extracted).

Usage:
    python scripts/reextract_target_roles.py
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from bson import ObjectId
from pymongo import MongoClient, UpdateOne
from src.common.config import Config
from src.layer1_4.claude_jd_extractor import JDExtractor, ExtractionResult
from src.common.llm_config import STEP_CONFIGS, StepConfig

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Silence noisy loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Target role patterns - case insensitive matching
TARGET_PATTERNS = [
    "VP engineering",
    "VP of engineering",
    "Director Software Engineering",
    "Director of Software Engineering",
    "Director Engineering",
    "Director of Engineering",
    "Head of Engineering",
    "Head of Technology",
    "Staff Software Engineer",
    "Staff Engineer",
    "Principal Software Engineer",
    "Principal Engineer",
    "Lead Software Engineer",
    "Lead Engineer",
    "Tech Lead",
    "Technical Lead",
    "CTO",
    "Chief Technology Officer",
    "Chief Technical Officer",
]


def configure_mandatory_cli():
    """Configure JD extraction to use Claude CLI mandatory (no fallback)."""
    original_config = STEP_CONFIGS.get("jd_extraction", StepConfig())
    STEP_CONFIGS["jd_extraction"] = StepConfig(
        tier=original_config.tier,
        claude_model=original_config.claude_model,
        fallback_model=original_config.fallback_model,
        timeout_seconds=original_config.timeout_seconds,
        max_retries=original_config.max_retries,
        use_fallback=False,
    )
    logger.info("Configured Claude CLI mandatory (no fallback)")


def get_mongodb_client() -> MongoClient:
    """Get MongoDB client."""
    if not Config.MONGODB_URI:
        raise ValueError("MONGODB_URI not configured in .env")
    return MongoClient(Config.MONGODB_URI)


def query_target_jobs(client: MongoClient):
    """Query jobs matching target role patterns."""
    level2 = client['jobs']['level-2']

    # Build regex pattern from all target patterns
    # Escape special regex characters and join with OR
    import re
    escaped_patterns = [re.escape(p) for p in TARGET_PATTERNS]
    combined_pattern = "|".join(escaped_patterns)

    query = {
        "title": {"$regex": combined_pattern, "$options": "i"},
        "description": {"$exists": True, "$ne": ""},
    }

    jobs = list(level2.find(query))
    logger.info(f"Found {len(jobs)} jobs matching target role patterns")

    # Show breakdown by pattern match
    print("\nJobs found by title pattern:")
    for job in jobs:
        title = job.get("title", "N/A")
        company = job.get("company", "N/A")
        has_extraction = "extracted_jd" in job and job["extracted_jd"]
        status = "✓ extracted" if has_extraction else "○ needs extraction"
        print(f"  {status} | {title} @ {company}")

    return jobs


async def run_extraction(jobs, max_concurrent=3):
    """Run parallel extraction."""
    jobs_for_extraction = [
        {
            "job_id": str(job["_id"]),
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "job_description": job.get("description", ""),
        }
        for job in jobs
    ]

    extractor = JDExtractor(tier="middle")

    logger.info(f"Starting extraction of {len(jobs)} jobs with max_concurrent={max_concurrent}")
    start_time = datetime.now()

    results = await extractor.extract_batch(jobs_for_extraction, max_concurrent=max_concurrent)

    duration = (datetime.now() - start_time).total_seconds()
    logger.info(f"Extraction complete in {duration:.1f}s")

    return results


def save_results(client: MongoClient, results):
    """Save extraction results to MongoDB."""
    level2 = client['jobs']['level-2']

    updates = []
    succeeded = 0
    failed = 0

    for result in results:
        if result.success and result.extracted_jd:
            updates.append(UpdateOne(
                {"_id": ObjectId(result.job_id)},
                {"$set": {
                    "extracted_jd": result.extracted_jd,
                    "extraction_model": result.model,
                    "extraction_duration_ms": result.duration_ms,
                    "extracted_at": result.extracted_at,
                }}
            ))
            succeeded += 1
        else:
            failed += 1
            logger.warning(f"Extraction failed for {result.job_id}: {result.error}")

    if updates:
        level2.bulk_write(updates)
        logger.info(f"Saved {succeeded} extraction results to MongoDB")

    return {"succeeded": succeeded, "failed": failed}


async def main():
    print("\n" + "=" * 70)
    print("RE-EXTRACT TARGET ROLES")
    print("=" * 70)

    # Configure mandatory CLI
    configure_mandatory_cli()

    # Connect to MongoDB
    client = get_mongodb_client()

    # Query target jobs
    jobs = query_target_jobs(client)

    if not jobs:
        print("\n⚠️  No jobs found matching target patterns")
        client.close()
        return

    print(f"\n📊 Found {len(jobs)} jobs to extract")
    proceed = input("\nProceed with extraction? [y/N]: ").strip().lower()

    if proceed != 'y':
        print("Aborted.")
        client.close()
        return

    # Run extraction
    results = await run_extraction(jobs, max_concurrent=3)

    # Save results
    counts = save_results(client, results)

    # Summary
    print("\n" + "=" * 70)
    print("EXTRACTION COMPLETE")
    print("=" * 70)
    print(f"  Succeeded: {counts['succeeded']}")
    print(f"  Failed: {counts['failed']}")

    # Show role category distribution
    role_counts = {}
    for result in results:
        if result.success and result.extracted_jd:
            cat = result.extracted_jd.get("role_category", "unknown")
            role_counts[cat] = role_counts.get(cat, 0) + 1

    print("\nRole categories extracted:")
    for cat, count in sorted(role_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {cat}: {count}")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
