#!/usr/bin/env python3
"""Backfill AI classification fields for existing jobs in MongoDB level-2.

Classifies all jobs (or only unclassified) using the shared AI classifier
and writes is_ai_job, ai_categories, ai_category_count, ai_classified_at
to each document.

Usage:
    # Dry run (preview only)
    .venv/bin/python scripts/backfill_ai_classification.py --dry-run

    # Backfill unclassified jobs only (default)
    .venv/bin/python scripts/backfill_ai_classification.py

    # Force re-classify all jobs
    .venv/bin/python scripts/backfill_ai_classification.py --force
"""

import argparse
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.common.ai_classifier import classify_job_document

load_dotenv()

BATCH_SIZE = 500


def main():
    parser = argparse.ArgumentParser(description="Backfill AI classification for level-2 jobs")
    parser.add_argument("--dry-run", action="store_true", help="Preview results without writing")
    parser.add_argument("--force", action="store_true", help="Re-classify all jobs (not just unclassified)")
    args = parser.parse_args()

    client = MongoClient(os.getenv("MONGODB_URI"))
    coll = client["jobs"]["level-2"]

    # Build query
    if args.force:
        query = {}
        print("Mode: FORCE — re-classifying ALL jobs")
    else:
        query = {"is_ai_job": {"$exists": False}}
        print("Mode: INCREMENTAL — classifying only unclassified jobs")

    total = coll.count_documents(query)
    print(f"Jobs to classify: {total:,}")

    if total == 0:
        print("Nothing to do.")
        return

    # Process in batches
    classified_count = 0
    ai_count = 0
    operations = []
    now = datetime.utcnow()

    cursor = coll.find(query)
    for i, doc in enumerate(cursor, 1):
        result = classify_job_document(doc)

        operations.append(UpdateOne(
            {"_id": doc["_id"]},
            {"$set": {
                "is_ai_job": result.is_ai_job,
                "ai_categories": result.ai_categories,
                "ai_category_count": result.ai_category_count,
                "ai_classified_at": now,
            }},
        ))

        if result.is_ai_job:
            ai_count += 1
        classified_count += 1

        # Flush batch
        if len(operations) >= BATCH_SIZE:
            if not args.dry_run:
                coll.bulk_write(operations, ordered=False)
            pct = classified_count / total * 100
            ai_pct = ai_count / classified_count * 100 if classified_count else 0
            print(f"  [{pct:5.1f}%] Processed {classified_count:,}/{total:,} — AI: {ai_count:,} ({ai_pct:.1f}%)")
            operations = []

    # Flush remaining
    if operations:
        if not args.dry_run:
            coll.bulk_write(operations, ordered=False)

    ai_pct = ai_count / classified_count * 100 if classified_count else 0
    print(f"\nDone! Classified {classified_count:,} jobs — {ai_count:,} AI ({ai_pct:.1f}%)")

    if args.dry_run:
        print("\n** DRY RUN — no changes written to MongoDB **")
    else:
        print("\nCreating sparse index on is_ai_job...")
        coll.create_index("is_ai_job", name="idx_is_ai_job", sparse=True)
        print("Index created.")


if __name__ == "__main__":
    main()
