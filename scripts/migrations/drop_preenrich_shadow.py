"""
drop_preenrich_shadow.py — Shadow namespace rollback migration.

Removes pre_enrichment.shadow_legacy_fields and pre_enrichment.stages.*.shadow_output
from all level-2 documents. Safe to run multiple times (idempotent).

Usage:
    python -m scripts.migrations.drop_preenrich_shadow [--dry-run]

Environment:
    MONGODB_URI  — MongoDB connection string
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Stage names to unset shadow_output from
_STAGES = [
    "jd_structure",
    "jd_extraction",
    "ai_classification",
    "pain_points",
    "annotations",
    "persona",
    "company_research",
    "role_research",
]


def run(dry_run: bool = False, mongodb_uri: str | None = None) -> None:
    """
    Remove shadow namespace fields from all level-2 documents.

    Two operations are performed:
    1. Unset pre_enrichment.shadow_legacy_fields from all docs that have it.
    2. Unset pre_enrichment.stages.<stage>.shadow_output from all docs that
       have it, for every stage in STAGE_ORDER.

    Args:
        dry_run: If True, count affected docs but do not write.
        mongodb_uri: MongoDB URI. Falls back to MONGODB_URI env var.
    """
    import pymongo

    uri = mongodb_uri or os.environ.get("MONGODB_URI", "")
    if not uri:
        logger.error("MONGODB_URI not set")
        sys.exit(1)

    client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=10_000)
    db = client["jobs"]
    coll = db["level-2"]

    # -----------------------------------------------------------------------
    # Step 1: Remove shadow_legacy_fields
    # -----------------------------------------------------------------------
    shadow_fields_filter = {
        "pre_enrichment.shadow_legacy_fields": {"$exists": True}
    }
    count1 = coll.count_documents(shadow_fields_filter)
    logger.info(
        "%s %d document(s) with pre_enrichment.shadow_legacy_fields",
        "[DRY-RUN] Would update" if dry_run else "Updating",
        count1,
    )

    if not dry_run and count1 > 0:
        result1 = coll.update_many(
            shadow_fields_filter,
            {"$unset": {"pre_enrichment.shadow_legacy_fields": ""}},
        )
        logger.info(
            "Unset shadow_legacy_fields from %d document(s)", result1.modified_count
        )

    # -----------------------------------------------------------------------
    # Step 2: Remove shadow_output from each stage
    # -----------------------------------------------------------------------
    for stage_name in _STAGES:
        field_path = f"pre_enrichment.stages.{stage_name}.shadow_output"
        stage_filter = {field_path: {"$exists": True}}
        count_stage = coll.count_documents(stage_filter)

        if count_stage == 0:
            logger.debug("No documents have %s — skipping", field_path)
            continue

        logger.info(
            "%s %d document(s) with %s",
            "[DRY-RUN] Would update" if dry_run else "Updating",
            count_stage,
            field_path,
        )

        if not dry_run:
            result_stage = coll.update_many(
                stage_filter,
                {"$unset": {field_path: ""}},
            )
            logger.info(
                "Unset %s from %d document(s)",
                field_path,
                result_stage.modified_count,
            )

    client.close()
    logger.info("drop_preenrich_shadow migration complete (dry_run=%s)", dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rollback: remove shadow namespace fields from level-2 collection."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count affected documents without writing",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
