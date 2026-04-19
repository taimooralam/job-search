"""Rollback iteration-4 DAG ownership for docs with no durable stage output."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from pymongo import MongoClient


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def rollback_dag(db: Any, *, dry_run: bool = True, now: Optional[datetime] = None) -> dict[str, int]:
    """Rollback DAG ownership only for docs with no completed stages."""
    current_time = now or utc_now()
    stats = {"rolled_back_docs": 0, "preserved_docs": 0, "cancelled_work_items": 0}
    for doc in db["level-2"].find({"pre_enrichment.orchestration": "dag"}):
        stage_states = ((doc.get("pre_enrichment") or {}).get("stage_states")) or {}
        has_completed = any((state or {}).get("status") == "completed" for state in stage_states.values())
        if has_completed:
            stats["preserved_docs"] += 1
            continue

        stats["rolled_back_docs"] += 1
        if dry_run:
            stats["cancelled_work_items"] += db["work_items"].count_documents(
                {"lane": "preenrich", "subject_id": str(doc["_id"]), "status": "pending"}
            )
            continue

        db["level-2"].update_one(
            {"_id": doc["_id"], "pre_enrichment.orchestration": "dag"},
            {
                "$set": {
                    "pre_enrichment.orchestration": "legacy",
                    "updated_at": current_time,
                }
            },
        )
        result = db["work_items"].update_many(
            {"lane": "preenrich", "subject_id": str(doc["_id"]), "status": "pending"},
            {
                "$set": {
                    "status": "cancelled",
                    "updated_at": current_time,
                    "last_error": {
                        "class": "rollback_to_legacy",
                        "message": "cancelled during DAG rollback",
                        "at": current_time,
                    },
                }
            },
        )
        stats["cancelled_work_items"] += int(result.modified_count)
    return stats


def _get_db() -> Any:
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set")
    return MongoClient(uri)["jobs"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Rollback iteration-4 preenrich DAG ownership")
    parser.add_argument("--apply", action="store_true", help="Apply rollback instead of dry-run")
    args = parser.parse_args()
    print(json.dumps(rollback_dag(_get_db(), dry_run=not args.apply), indent=2, default=str))


if __name__ == "__main__":
    main()
