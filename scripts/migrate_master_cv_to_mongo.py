#!/usr/bin/env python3
"""
Migrate master-cv data from local JSON/MD files to MongoDB.

This script:
1. Loads role_metadata.json → master_cv_metadata collection
2. Loads role_skills_taxonomy.json → master_cv_taxonomy collection
3. Loads roles/*.md files → master_cv_roles collection
4. Creates indexes for efficient querying

Usage:
    python scripts/migrate_master_cv_to_mongo.py [--clear] [--dry-run]

Options:
    --clear      Clear existing data before migration (destructive!)
    --dry-run    Show what would be migrated without actually doing it
"""

import sys
import argparse
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.common.database import db
from src.common.master_cv_store import MasterCVStore, DEFAULT_DATA_DIR

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_metadata(data_dir: Path) -> dict:
    """Load role_metadata.json from data directory."""
    metadata_path = data_dir / "role_metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Metadata file not found: {metadata_path}")

    with open(metadata_path, "r") as f:
        return json.load(f)


def load_taxonomy(data_dir: Path) -> dict:
    """Load role_skills_taxonomy.json from data directory."""
    taxonomy_path = data_dir / "role_skills_taxonomy.json"
    if not taxonomy_path.exists():
        raise FileNotFoundError(f"Taxonomy file not found: {taxonomy_path}")

    with open(taxonomy_path, "r") as f:
        return json.load(f)


def load_roles(data_dir: Path) -> list:
    """Load all role markdown files from roles/ directory."""
    roles_dir = data_dir / "roles"
    if not roles_dir.exists():
        raise FileNotFoundError(f"Roles directory not found: {roles_dir}")

    roles = []
    for role_file in sorted(roles_dir.glob("*.md")):
        role_id = role_file.stem
        with open(role_file, "r") as f:
            content = f.read()
        roles.append({
            "role_id": role_id,
            "markdown_content": content,
            "parsed": None  # Parsing happens in the pipeline
        })

    return roles


def clear_collections(database) -> dict:
    """Clear all master-cv collections."""
    results = {}

    for collection_name in ["master_cv_metadata", "master_cv_taxonomy", "master_cv_roles", "master_cv_history"]:
        result = database[collection_name].delete_many({})
        results[collection_name] = result.deleted_count
        logger.info(f"  ✓ Cleared {result.deleted_count} documents from {collection_name}")

    return results


def migrate_metadata(database, metadata: dict, dry_run: bool = False) -> bool:
    """Migrate metadata to MongoDB."""
    doc = {
        "_id": "canonical",
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": "migration",
        "candidate": metadata.get("candidate", {}),
        "roles": metadata.get("roles", [])
    }

    if dry_run:
        logger.info(f"  [DRY RUN] Would insert metadata with {len(doc['roles'])} roles")
        return True

    database["master_cv_metadata"].replace_one(
        {"_id": "canonical"},
        doc,
        upsert=True
    )
    logger.info(f"  ✓ Migrated metadata with {len(doc['roles'])} roles")
    return True


def migrate_taxonomy(database, taxonomy: dict, dry_run: bool = False) -> bool:
    """Migrate taxonomy to MongoDB."""
    doc = {
        "_id": "canonical",
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": "migration",
        "target_roles": taxonomy.get("target_roles", {}),
        "skill_aliases": taxonomy.get("skill_aliases", {}),
        "default_fallback_role": taxonomy.get("default_fallback_role", "engineering_manager")
    }

    if dry_run:
        logger.info(f"  [DRY RUN] Would insert taxonomy with {len(doc['target_roles'])} target roles")
        return True

    database["master_cv_taxonomy"].replace_one(
        {"_id": "canonical"},
        doc,
        upsert=True
    )
    logger.info(f"  ✓ Migrated taxonomy with {len(doc['target_roles'])} target roles")
    return True


def migrate_roles(database, roles: list, dry_run: bool = False) -> dict:
    """Migrate role markdown files to MongoDB."""
    results = {"inserted": 0, "errors": 0}

    for role in roles:
        doc = {
            "role_id": role["role_id"],
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": "migration",
            "markdown_content": role["markdown_content"],
            "parsed": role.get("parsed")
        }

        if dry_run:
            logger.info(f"  [DRY RUN] Would insert role: {role['role_id']}")
            results["inserted"] += 1
            continue

        try:
            database["master_cv_roles"].replace_one(
                {"role_id": role["role_id"]},
                doc,
                upsert=True
            )
            results["inserted"] += 1
            logger.info(f"  ✓ Migrated role: {role['role_id']}")
        except Exception as e:
            logger.error(f"  ✗ Failed to migrate role {role['role_id']}: {e}")
            results["errors"] += 1

    return results


def create_indexes(database) -> None:
    """Create indexes for efficient querying."""
    # History collection indexes
    database["master_cv_history"].create_index(
        [("collection", 1), ("doc_id", 1), ("version", -1)],
        name="collection_doc_version"
    )
    database["master_cv_history"].create_index(
        [("timestamp", -1)],
        name="timestamp_desc"
    )

    # Roles collection indexes
    database["master_cv_roles"].create_index(
        [("role_id", 1)],
        name="role_id",
        unique=True
    )

    logger.info("  ✓ Created indexes")


def main():
    """Run the master-cv migration."""
    parser = argparse.ArgumentParser(
        description="Migrate master-cv data from local files to MongoDB"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing data before migration (destructive!)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without actually doing it"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=str(DEFAULT_DATA_DIR),
        help=f"Data directory containing master-cv files (default: {DEFAULT_DATA_DIR})"
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)

    logger.info("=" * 60)
    logger.info("Master-CV → MongoDB Migration")
    logger.info("=" * 60)

    if args.dry_run:
        logger.info("🔍 DRY RUN MODE - no changes will be made")

    # Step 1: Verify source files exist
    logger.info(f"\n📖 Step 1: Verifying source files in {data_dir}...")
    try:
        metadata = load_metadata(data_dir)
        logger.info(f"  ✓ Found role_metadata.json ({len(metadata.get('roles', []))} roles)")

        taxonomy = load_taxonomy(data_dir)
        logger.info(f"  ✓ Found role_skills_taxonomy.json ({len(taxonomy.get('target_roles', {}))} target roles)")

        roles = load_roles(data_dir)
        logger.info(f"  ✓ Found {len(roles)} role markdown files")
    except FileNotFoundError as e:
        logger.error(f"❌ {e}")
        return 1

    # Step 2: Connect to MongoDB
    logger.info("\n🔌 Step 2: Connecting to MongoDB...")
    if args.dry_run:
        logger.info("  [DRY RUN] Would connect to MongoDB")
        database = None
    else:
        try:
            db.connect()
            database = db.db
            logger.info(f"  ✓ Connected to database: {database.name}")
        except Exception as e:
            logger.error(f"❌ Failed to connect to MongoDB: {e}")
            logger.error("Check your MONGODB_URI in .env")
            return 1

    # Step 3: Clear existing data if requested
    if args.clear and not args.dry_run:
        logger.info("\n🗑️  Step 3: Clearing existing data...")
        logger.warning("⚠️  This will DELETE all existing master-cv data!")
        confirm = input("Type 'yes' to confirm: ")
        if confirm.lower() != 'yes':
            logger.info("❌ Aborted - no data cleared")
            return 1

        clear_collections(database)
    elif args.clear and args.dry_run:
        logger.info("\n🗑️  Step 3: [DRY RUN] Would clear existing data")
    else:
        logger.info("\n⏭️  Step 3: Skipping clear (use --clear to remove existing data)")

    # Step 4: Create indexes
    logger.info("\n📑 Step 4: Creating indexes...")
    if args.dry_run:
        logger.info("  [DRY RUN] Would create indexes")
    else:
        create_indexes(database)

    # Step 5: Migrate metadata
    logger.info("\n📋 Step 5: Migrating metadata...")
    if not migrate_metadata(database, metadata, args.dry_run):
        logger.error("❌ Failed to migrate metadata")
        return 1

    # Step 6: Migrate taxonomy
    logger.info("\n🏷️  Step 6: Migrating taxonomy...")
    if not migrate_taxonomy(database, taxonomy, args.dry_run):
        logger.error("❌ Failed to migrate taxonomy")
        return 1

    # Step 7: Migrate roles
    logger.info("\n📝 Step 7: Migrating role content...")
    role_results = migrate_roles(database, roles, args.dry_run)

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("MIGRATION SUMMARY")
    logger.info("=" * 60)
    logger.info(f"📋 Metadata: ✓ (candidate + {len(metadata.get('roles', []))} roles)")
    logger.info(f"🏷️  Taxonomy: ✓ ({len(taxonomy.get('target_roles', {}))} target roles)")
    logger.info(f"📝 Roles: {role_results['inserted']} migrated, {role_results['errors']} errors")

    if args.dry_run:
        logger.info("\n🔍 DRY RUN COMPLETE - no changes were made")
        logger.info("Run without --dry-run to perform actual migration")
    else:
        logger.info("\n🎉 Migration complete!")

        # Verify by reading back
        logger.info("\n📊 Verification:")
        store = MasterCVStore(use_mongodb=True)
        stats = store.get_stats()
        logger.info(f"  • Metadata version: {stats.get('metadata_version')}")
        logger.info(f"  • Taxonomy version: {stats.get('taxonomy_version')}")
        logger.info(f"  • Roles count: {stats.get('roles_count')}")

    logger.info("=" * 60)

    if not args.dry_run:
        db.disconnect()

    return 0


if __name__ == "__main__":
    sys.exit(main())
