#!/usr/bin/env python3
"""
Migration: Add pre-enrichment indexes and backfill lifecycle=legacy.

Creates compound indexes required by the pre-enrichment worker lease model (§5):
    1. { lifecycle:1, lease_expires_at:1, selected_at:1 }  — claim query
    2. { "pre_enrichment.jd_checksum":1 }                  — stale detection
    3. { "pre_enrichment.company_checksum":1 }              — company cache
    4. { lease_owner:1, lease_heartbeat_at:1 }              — operator debugging

Backfills existing level-2 documents that have no pre_enrichment field with
lifecycle="legacy" so the worker ignores them (BDD S11, T16).

Idempotent: safe to run multiple times. Indexes are created with
background=True (PyMongo 3.x) / no-op if already exist (PyMongo 4.x).

Usage:
    python scripts/migrations/add_preenrich_indexes.py
    python scripts/migrations/add_preenrich_indexes.py --dry-run
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Allow running from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("preenrich_migration")


def get_db():
    """Connect to MongoDB and return the jobs database."""
    from pymongo import MongoClient

    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set in environment")
    client = MongoClient(uri)
    return client["jobs"]


def create_indexes(collection, dry_run: bool) -> None:
    """Create compound indexes on the level-2 collection."""
    from pymongo import ASCENDING

    indexes = [
        # Claim query: find claimable jobs sorted by selected_at
        {
            "keys": [
                ("lifecycle", ASCENDING),
                ("lease_expires_at", ASCENDING),
                ("selected_at", ASCENDING),
            ],
            "name": "preenrich_claim_idx",
        },
        # Stale detection by JD checksum
        {
            "keys": [("pre_enrichment.jd_checksum", ASCENDING)],
            "name": "preenrich_jd_checksum_idx",
        },
        # Stale detection by company checksum
        {
            "keys": [("pre_enrichment.company_checksum", ASCENDING)],
            "name": "preenrich_company_checksum_idx",
        },
        # Operator debugging: who owns what, last heartbeat
        {
            "keys": [
                ("lease_owner", ASCENDING),
                ("lease_heartbeat_at", ASCENDING),
            ],
            "name": "preenrich_lease_owner_idx",
        },
    ]

    for idx in indexes:
        if dry_run:
            logger.info("[DRY RUN] Would create index: %s", idx["name"])
            continue

        try:
            collection.create_index(idx["keys"], name=idx["name"], background=True)
            logger.info("Created index: %s", idx["name"])
        except Exception as exc:
            # IndexKeySpecsConflict or similar — already exists
            logger.info("Index %s: %s (may already exist)", idx["name"], exc)


def backfill_legacy(collection, dry_run: bool) -> int:
    """
    Backfill existing docs without pre_enrichment field as lifecycle=legacy.

    Returns the count of documents that were (or would be) updated.
    """
    query = {"pre_enrichment": {"$exists": False}}
    count = collection.count_documents(query)

    if count == 0:
        logger.info("Backfill: no documents need lifecycle=legacy")
        return 0

    logger.info(
        "Backfill: %d document(s) without pre_enrichment → lifecycle=legacy", count
    )

    if dry_run:
        logger.info("[DRY RUN] Would update %d documents", count)
        return count

    result = collection.update_many(
        query,
        {"$set": {"lifecycle": "legacy"}},
    )
    logger.info(
        "Backfill complete: %d matched, %d modified",
        result.matched_count,
        result.modified_count,
    )
    return result.modified_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add pre-enrichment indexes and backfill lifecycle=legacy"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without making changes",
    )
    args = parser.parse_args()

    if args.dry_run:
        logger.info("DRY RUN mode — no changes will be made")

    db = get_db()
    collection = db["level-2"]

    logger.info("Creating indexes on level-2 collection...")
    create_indexes(collection, dry_run=args.dry_run)

    logger.info("Backfilling lifecycle=legacy for pre-existing documents...")
    updated = backfill_legacy(collection, dry_run=args.dry_run)

    logger.info(
        "Migration complete (dry_run=%s). Indexes: 4. Legacy backfill: %d docs.",
        args.dry_run,
        updated,
    )


if __name__ == "__main__":
    main()
