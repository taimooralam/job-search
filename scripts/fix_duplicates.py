#!/usr/bin/env python3
"""
One-time migration: remove duplicate jobs from level-2 and enforce uniqueness.

Steps:
1. Find all duplicate groups in level-2 (same normalized company + title).
2. Keep the oldest document in each group; delete the rest.
3. Create a unique index on dedupeKey to prevent future duplicates at the DB level.

Usage:
    python scripts/fix_duplicates.py
    python scripts/fix_duplicates.py --dry-run   # show what would be deleted
"""

import argparse
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from pymongo import MongoClient, ASCENDING

from src.common.dedupe import normalize_for_dedupe

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("fix_duplicates")


def get_db():
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set in environment")
    client = MongoClient(uri)
    return client["jobs"]


def find_duplicate_groups(collection) -> List[List[Dict[str, Any]]]:
    """Return groups of documents sharing the same normalized company+title.

    Each group has at least 2 documents. Within each group, documents are
    sorted oldest-first so index [0] is the one to keep.
    """
    logger.info("Scanning level-2 for documents...")
    docs = list(collection.find({}, {"_id": 1, "company": 1, "title": 1, "createdAt": 1, "dedupeKey": 1}))
    logger.info(f"Total documents in level-2: {len(docs)}")

    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for doc in docs:
        company_norm = normalize_for_dedupe(doc.get("company"))
        title_norm = normalize_for_dedupe(doc.get("title"))
        if not company_norm or not title_norm:
            continue
        key = f"{company_norm}|{title_norm}"
        groups[key].append(doc)

    duplicate_groups = []
    for key, group in groups.items():
        if len(group) > 1:
            # Sort oldest first (keep the first-inserted document)
            group.sort(key=lambda d: d.get("createdAt") or datetime.min)
            duplicate_groups.append(group)

    return duplicate_groups


def delete_duplicates(collection, duplicate_groups: List[List[Dict]], dry_run: bool) -> int:
    """Delete all but the oldest document in each duplicate group.

    Returns the number of documents deleted (or that would be deleted).
    """
    total_deleted = 0

    for group in duplicate_groups:
        keeper = group[0]
        to_delete = group[1:]

        keeper_info = (
            f"{keeper.get('company', '?')} | {keeper.get('title', '?')} "
            f"(id={keeper['_id']}, created={keeper.get('createdAt', 'unknown')})"
        )
        logger.info(f"Keeping: {keeper_info}")

        for dup in to_delete:
            dup_info = (
                f"  Delete: id={dup['_id']}, "
                f"dedupeKey={dup.get('dedupeKey', 'none')}, "
                f"created={dup.get('createdAt', 'unknown')}"
            )
            if dry_run:
                logger.info(f"[DRY RUN] Would delete: {dup_info}")
            else:
                collection.delete_one({"_id": dup["_id"]})
                logger.info(f"Deleted: {dup_info}")
            total_deleted += 1

    return total_deleted


def ensure_dedupe_key_index(collection, dry_run: bool) -> None:
    """Create a unique index on dedupeKey in level-2."""
    if dry_run:
        logger.info("[DRY RUN] Would create unique index on level-2.dedupeKey")
        return

    try:
        collection.create_index("dedupeKey", unique=True, background=True)
        logger.info("Created unique index on level-2.dedupeKey")
    except Exception as e:
        logger.warning(f"Index creation failed (may already exist): {e}")


def main():
    parser = argparse.ArgumentParser(
        description="One-time migration: remove duplicates from level-2 and add unique index"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without modifying anything",
    )
    args = parser.parse_args()

    if args.dry_run:
        logger.info("DRY RUN mode — no changes will be made")

    db = get_db()
    collection = db["level-2"]

    # Step 1: Find duplicate groups
    logger.info("Step 1: Finding duplicate groups...")
    duplicate_groups = find_duplicate_groups(collection)
    total_groups = len(duplicate_groups)
    total_duplicates = sum(len(g) - 1 for g in duplicate_groups)
    logger.info(f"Found {total_groups} duplicate groups, {total_duplicates} documents to delete")

    if total_groups == 0:
        logger.info("No duplicates found — collection is clean.")
    else:
        # Step 2: Delete duplicates (keep oldest)
        logger.info("Step 2: Deleting duplicates (keeping oldest in each group)...")
        deleted = delete_duplicates(collection, duplicate_groups, dry_run=args.dry_run)
        logger.info(f"{'Would delete' if args.dry_run else 'Deleted'}: {deleted} documents")

    # Step 3: Create unique index on dedupeKey
    logger.info("Step 3: Ensuring unique index on dedupeKey...")
    ensure_dedupe_key_index(collection, dry_run=args.dry_run)

    # Summary
    logger.info("=" * 60)
    logger.info("Migration Summary")
    logger.info(f"  Duplicate groups found: {total_groups}")
    logger.info(f"  Documents {'would be ' if args.dry_run else ''}deleted: {total_duplicates}")
    logger.info(f"  Unique index on dedupeKey: {'skipped (dry-run)' if args.dry_run else 'ensured'}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
