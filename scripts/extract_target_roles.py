#!/usr/bin/env python3
"""
Extract JDs for target roles using Claude CLI (no fallback).
Saves results incrementally in batches.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from bson import ObjectId
from pymongo import MongoClient, UpdateOne
from src.common.config import Config
from src.layer1_4.claude_jd_extractor import JDExtractor

# Target role query
QUERY = {
    'title': {
        '$regex': '^(VP engineering|Director Software Engineering|Head of Engineering|Staff Software Engineer|Principal Software Engineer|Lead Software Engineer|CTO|Head of Technology|Senior Software Engineer|Tech Lead)$',
        '$options': 'i'
    },
    'job_description': {'$exists': True, '$ne': ''},
    '$or': [
        {'extracted_jd': {'$exists': False}},
        {'extracted_jd': None},
    ]
}

BATCH_SIZE = 10  # Process in batches of 10, save after each batch


async def extract_batch(extractor, jobs, level2):
    """Extract a batch and save results immediately."""
    jobs_for_extraction = [
        {
            "job_id": str(job["_id"]),
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "job_description": job.get("job_description", ""),
        }
        for job in jobs
    ]

    results = await extractor.extract_batch(jobs_for_extraction, max_concurrent=BATCH_SIZE)

    # Save immediately
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
            print(f"  ❌ {result.job_id[:8]}: {result.error[:50] if result.error else 'Unknown'}")

    if updates:
        level2.bulk_write(updates)

    return succeeded, failed


async def main():
    print("=" * 60)
    print("EXTRACTING TARGET ROLES (Incremental)")
    print("=" * 60)

    client = MongoClient(Config.MONGODB_URI)
    level2 = client['jobs']['level-2']

    # Get jobs needing extraction
    jobs = list(level2.find(QUERY))
    total = len(jobs)
    print(f"\n📊 Found {total} jobs to extract\n")

    if not jobs:
        print("No jobs to extract.")
        return

    extractor = JDExtractor(tier="middle")

    total_succeeded = 0
    total_failed = 0
    start_time = datetime.now()

    # Process in batches
    for i in range(0, total, BATCH_SIZE):
        batch = jobs[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

        print(f"Batch {batch_num}/{total_batches} ({len(batch)} jobs)...")

        succeeded, failed = await extract_batch(extractor, batch, level2)
        total_succeeded += succeeded
        total_failed += failed

        elapsed = (datetime.now() - start_time).total_seconds()
        rate = total_succeeded / elapsed * 60 if elapsed > 0 else 0
        print(f"  ✅ {succeeded} succeeded, ❌ {failed} failed | Total: {total_succeeded}/{total} | {rate:.1f}/min\n")

    duration = (datetime.now() - start_time).total_seconds()

    # Summary
    print("=" * 60)
    print("EXTRACTION COMPLETE")
    print("=" * 60)
    print(f"Duration: {duration:.1f}s ({duration/60:.1f} min)")
    print(f"Succeeded: {total_succeeded}")
    print(f"Failed: {total_failed}")
    print(f"Rate: {total_succeeded/duration*60:.1f} jobs/min")

    # Role category distribution
    pipeline = [
        {'$match': {**QUERY, 'extracted_jd': {'$type': 'object'}}},
        {'$group': {'_id': '$extracted_jd.role_category', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}}
    ]
    # Remove the extraction filter for final query
    final_query = {
        'title': QUERY['title'],
        'job_description': QUERY['job_description'],
        'extracted_jd': {'$type': 'object'}
    }
    categories = list(level2.aggregate([
        {'$match': final_query},
        {'$group': {'_id': '$extracted_jd.role_category', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}}
    ]))

    print("\nRole categories:")
    for cat in categories:
        print(f"  {cat['_id']}: {cat['count']}")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
