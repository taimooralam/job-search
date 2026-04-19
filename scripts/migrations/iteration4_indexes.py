#!/usr/bin/env python3
"""Create iteration-4 preenrich DAG indexes."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any

from pymongo import ASCENDING, DESCENDING

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

logger = logging.getLogger("iteration4_indexes")

TERMINAL_WORK_ITEM_STATUSES = ("done", "deadletter", "cancelled")
TERMINAL_WORK_ITEM_TTL_SECONDS = 30 * 24 * 60 * 60


def get_db() -> Any:
    """Connect to MongoDB and return the jobs database."""
    from pymongo import MongoClient

    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set in environment")
    return MongoClient(uri)["jobs"]


def build_index_plan() -> dict[str, list[dict[str, Any]]]:
    """Return the full iteration-4 index specification plan."""
    return {
        "level-2": [
            {
                "keys": [
                    ("lifecycle", ASCENDING),
                    ("pre_enrichment.orchestration", ASCENDING),
                    ("selected_at", ASCENDING),
                ],
                "kwargs": {"name": "preenrich_root_enqueue_scan"},
            },
            {
                "keys": [("pre_enrichment.cv_ready_at", ASCENDING)],
                "kwargs": {"name": "preenrich_cv_ready_at"},
            },
            {
                "keys": [("pre_enrichment.input_snapshot_id", ASCENDING)],
                "kwargs": {"name": "preenrich_input_snapshot_id"},
            },
            {
                "keys": [("pre_enrichment.pending_next_stages.idempotency_key", ASCENDING)],
                "kwargs": {"name": "preenrich_pending_next_stages"},
            },
        ],
        "work_items": [
            {
                "keys": [
                    ("status", ASCENDING),
                    ("task_type", ASCENDING),
                    ("available_at", ASCENDING),
                    ("priority", DESCENDING),
                ],
                "kwargs": {"name": "preenrich_claim"},
            },
            {
                "keys": [("lane", ASCENDING), ("status", ASCENDING), ("lease_expires_at", ASCENDING)],
                "kwargs": {"name": "preenrich_stage_sweeper"},
            },
            {
                "keys": [("idempotency_key", ASCENDING)],
                "kwargs": {"name": "preenrich_idempotency_key_unique", "unique": True},
            },
            {
                "keys": [("subject_id", ASCENDING), ("task_type", ASCENDING), ("status", ASCENDING)],
                "kwargs": {"name": "preenrich_subject_task_status"},
            },
            {
                # MongoDB TTL indexes cannot be compound. This is the valid
                # equivalent of the plan's partial TTL requirement in §4.5.
                "keys": [("updated_at", ASCENDING)],
                "kwargs": {
                    "name": "preenrich_terminal_work_items_ttl",
                    "expireAfterSeconds": TERMINAL_WORK_ITEM_TTL_SECONDS,
                    "partialFilterExpression": {"status": {"$in": list(TERMINAL_WORK_ITEM_STATUSES)}},
                },
            },
        ],
        "preenrich_stage_runs": [
            {
                "keys": [("started_at", ASCENDING), ("status", ASCENDING)],
                "kwargs": {"name": "stage_runs_started_status"},
            },
            {
                "keys": [("job_id", ASCENDING), ("stage", ASCENDING), ("started_at", DESCENDING)],
                "kwargs": {"name": "stage_runs_job_stage_started_desc"},
            },
        ],
        "preenrich_job_runs": [
            {
                "keys": [("started_at", ASCENDING), ("status", ASCENDING)],
                "kwargs": {"name": "job_runs_started_status"},
            }
        ],
    }


def ensure_iteration4_indexes(db: Any, *, dry_run: bool = False) -> list[str]:
    """Create the iteration-4 indexes idempotently."""
    created: list[str] = []
    for collection_name, specs in build_index_plan().items():
        collection = db[collection_name]
        for spec in specs:
            name = spec["kwargs"]["name"]
            if dry_run:
                logger.info("[DRY RUN] Would create %s on %s", name, collection_name)
                created.append(name)
                continue
            collection.create_index(spec["keys"], **spec["kwargs"])
            logger.info("Ensured index %s on %s", name, collection_name)
            created.append(name)
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Create iteration-4 preenrich DAG indexes")
    parser.add_argument("--dry-run", action="store_true", help="Print planned indexes without writing")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    db = get_db()
    created = ensure_iteration4_indexes(db, dry_run=args.dry_run)
    logger.info("Iteration-4 index migration complete (%d indexes)", len(created))


if __name__ == "__main__":
    main()
