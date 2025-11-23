#!/usr/bin/env python3
"""
Load STAR records from knowledge-base.md into MongoDB.

This script:
1. Parses all STAR records from knowledge-base.md
2. Creates the star_records collection with indexes
3. Bulk inserts all records into MongoDB
4. Reports statistics

Usage:
    python scripts/load_stars_to_mongodb.py [--clear]

Options:
    --clear    Clear existing STAR records before loading (destructive!)
"""

import sys
import argparse
import logging
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.common.star_parser import parse_star_records
from src.common.database import db
from src.common.config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """Load STAR records into MongoDB."""
    parser = argparse.ArgumentParser(
        description="Load STAR records from knowledge-base.md into MongoDB"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing STAR records before loading (⚠️ destructive!)"
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("STAR Records → MongoDB Loader")
    logger.info("=" * 60)

    # Step 1: Parse STAR records from knowledge-base.md
    logger.info("\n📖 Step 1: Parsing STAR records from knowledge-base.md...")
    kb_path = Path(Config.CANDIDATE_PROFILE_PATH)

    if not kb_path.exists():
        logger.error(f"❌ Knowledge base not found: {kb_path}")
        return 1

    try:
        records = parse_star_records(str(kb_path))
        logger.info(f"✓ Parsed {len(records)} STAR records")
    except Exception as e:
        logger.error(f"❌ Failed to parse knowledge base: {e}")
        return 1

    # Step 2: Connect to MongoDB
    logger.info("\n🔌 Step 2: Connecting to MongoDB...")
    try:
        db.connect()
        logger.info(f"✓ Connected to database: {db.db.name}")
    except Exception as e:
        logger.error(f"❌ Failed to connect to MongoDB: {e}")
        logger.error("Check your MONGODB_URI in .env")
        return 1

    # Step 3: Create indexes
    logger.info("\n📑 Step 3: Creating indexes...")
    try:
        db.ensure_indexes()
        logger.info("✓ Indexes created")
    except Exception as e:
        logger.error(f"❌ Failed to create indexes: {e}")
        return 1

    # Step 4: Clear existing records if requested
    if args.clear:
        logger.info("\n🗑️  Step 4: Clearing existing STAR records...")
        logger.warning("⚠️  This will DELETE all existing STAR records!")
        confirm = input("Type 'yes' to confirm: ")
        if confirm.lower() != 'yes':
            logger.info("❌ Aborted - no data cleared")
            return 1

        count = db.clear_star_records()
        logger.info(f"✓ Cleared {count} existing records")
    else:
        logger.info("\n⏭️  Step 4: Skipping clear (use --clear to remove existing data)")

    # Step 5: Insert STAR records
    logger.info("\n💾 Step 5: Inserting STAR records into MongoDB...")
    try:
        results = db.bulk_insert_star_records(records)

        logger.info("\n" + "=" * 60)
        logger.info("RESULTS")
        logger.info("=" * 60)
        logger.info(f"✅ Inserted: {results['inserted']}")
        logger.info(f"⚠️  Duplicates: {results['duplicates']}")
        logger.info(f"❌ Errors: {results['errors']}")
        logger.info(f"📊 Total: {len(records)}")
        logger.info("=" * 60)

        if results['errors'] > 0:
            logger.warning(f"\n⚠️  {results['errors']} records failed to insert")
            return 1

        if results['inserted'] == 0:
            logger.warning("\n⚠️  No new records inserted (all duplicates)")
            logger.info("Use --clear to replace existing records")
            return 0

        logger.info(f"\n🎉 Successfully loaded {results['inserted']} STAR records!")
        return 0

    except Exception as e:
        logger.error(f"❌ Failed to insert records: {e}")
        return 1
    finally:
        db.disconnect()


if __name__ == "__main__":
    sys.exit(main())
