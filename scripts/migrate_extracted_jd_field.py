#!/usr/bin/env python3
"""
One-time migration: extracted_jd_claude → extracted_jd

This script migrates the extraction field name from the Claude A/B testing
field to the primary extraction field, now that Claude is the only extractor.

Run: python scripts/migrate_extracted_jd_field.py

Options:
    --dry-run    Preview changes without modifying database
    --cleanup    Remove old extracted_jd_claude field after migration
"""

import os
import sys
import argparse
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient


def get_collection():
    """Get MongoDB collection."""
    mongo_uri = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
    db_name = os.getenv("MONGO_DB_NAME", "jobs")
    collection_name = os.getenv("MONGO_COLLECTION", "level-2")

    if not mongo_uri:
        raise ValueError("MONGODB_URI or MONGO_URI environment variable required")

    client = MongoClient(mongo_uri)
    db = client[db_name]
    return db[collection_name]


def migrate_extracted_jd(dry_run: bool = False, cleanup: bool = False):
    """
    Migrate extracted_jd_claude to extracted_jd.

    Only copies if:
    - extracted_jd_claude exists
    - extracted_jd does NOT exist (won't overwrite)
    """
    collection = get_collection()

    # Find documents with extracted_jd_claude but without extracted_jd
    query = {
        "extracted_jd_claude": {"$exists": True},
        "extracted_jd": {"$exists": False}
    }

    docs_to_migrate = list(collection.find(query, {"_id": 1, "title": 1}))

    print(f"\n{'='*60}")
    print(f"Migration: extracted_jd_claude → extracted_jd")
    print(f"{'='*60}")
    print(f"Documents to migrate: {len(docs_to_migrate)}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"Cleanup old field: {cleanup}")
    print(f"{'='*60}\n")

    if not docs_to_migrate:
        print("No documents need migration.")
        return

    if dry_run:
        print("Documents that would be migrated:")
        for doc in docs_to_migrate[:10]:  # Show first 10
            print(f"  - {doc['_id']}: {doc.get('title', 'No title')}")
        if len(docs_to_migrate) > 10:
            print(f"  ... and {len(docs_to_migrate) - 10} more")
        return

    # Perform migration
    migrated = 0
    errors = 0

    for doc in docs_to_migrate:
        try:
            # Get the full document to copy the field
            full_doc = collection.find_one({"_id": doc["_id"]})

            update_ops = {
                "$set": {
                    "extracted_jd": full_doc["extracted_jd_claude"],
                    "extracted_jd_migrated_at": datetime.utcnow()
                }
            }

            # Also migrate metadata if present
            if "extracted_jd_claude_metadata" in full_doc:
                update_ops["$set"]["extracted_jd_metadata"] = full_doc["extracted_jd_claude_metadata"]

            # Optionally remove old fields
            if cleanup:
                update_ops["$unset"] = {
                    "extracted_jd_claude": "",
                    "extracted_jd_claude_metadata": ""
                }

            collection.update_one({"_id": doc["_id"]}, update_ops)
            migrated += 1

            if migrated % 100 == 0:
                print(f"  Migrated {migrated}/{len(docs_to_migrate)}...")

        except Exception as e:
            print(f"  Error migrating {doc['_id']}: {e}")
            errors += 1

    print(f"\n{'='*60}")
    print(f"Migration complete!")
    print(f"  Migrated: {migrated}")
    print(f"  Errors: {errors}")
    print(f"{'='*60}")

    # Show stats
    total_with_extracted_jd = collection.count_documents({"extracted_jd": {"$exists": True}})
    total_with_claude = collection.count_documents({"extracted_jd_claude": {"$exists": True}})

    print(f"\nCurrent stats:")
    print(f"  Documents with extracted_jd: {total_with_extracted_jd}")
    print(f"  Documents with extracted_jd_claude: {total_with_claude}")


def main():
    parser = argparse.ArgumentParser(description="Migrate extracted_jd_claude to extracted_jd")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    parser.add_argument("--cleanup", action="store_true", help="Remove old field after migration")

    args = parser.parse_args()

    try:
        migrate_extracted_jd(dry_run=args.dry_run, cleanup=args.cleanup)
    except Exception as e:
        print(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
