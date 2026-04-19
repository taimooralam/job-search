"""Iteration-4 preenrich sweepers and shared finalizers."""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from bson import ObjectId
from pymongo import ReturnDocument

from src.pipeline.queue import WorkItemQueue
from src.preenrich.checksums import company_checksum, jd_checksum
from src.preenrich.root_enqueuer import DAG_VERSION, ROOT_STAGE, SCHEMA_VERSION, build_stage_states
from src.preenrich.schema import idempotency_key, input_snapshot_id
from src.preenrich.stage_registry import get_stage_definition, iter_stage_definitions

logger = logging.getLogger(__name__)
RETRY_BACKOFF_SECONDS = (30, 120, 600, 1800, 3600)


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def drain_pending_next_stages(
    db: Any,
    *,
    level2_id: Optional[ObjectId | str] = None,
    now: Optional[datetime] = None,
    limit: int = 50,
) -> dict[str, int]:
    """Drain stage-outbox entries whose downstream work item is not yet enqueued."""
    current_time = now or utc_now()
    queue = WorkItemQueue(db)
    level2 = db["level-2"]

    query: dict[str, Any] = {"pre_enrichment.pending_next_stages": {"$elemMatch": {"enqueued_at": None}}}
    if level2_id is not None:
        query["_id"] = _coerce_object_id(level2_id)

    stats = {"jobs": 0, "entries": 0}
    cursor = level2.find(query).limit(limit)
    for doc in cursor:
        pending = list(((doc.get("pre_enrichment") or {}).get("pending_next_stages")) or [])
        if not pending:
            continue

        changed = False
        stats["jobs"] += 1
        stage_state_updates: dict[str, Any] = {}
        for entry in pending:
            if entry.get("enqueued_at") is not None:
                continue

            result = queue.enqueue(
                task_type=entry["task_type"],
                lane="preenrich",
                consumer_mode="native_stage_dag",
                subject_type="job",
                subject_id=str(doc["_id"]),
                priority=int(entry.get("priority", 100)),
                available_at=current_time,
                max_attempts=int(entry["max_attempts"]),
                idempotency_key=entry["idempotency_key"],
                correlation_id=entry["correlation_id"],
                payload=dict(entry["payload"]),
            )
            entry["enqueued_at"] = current_time
            changed = True
            stats["entries"] += 1
            stage_name = str(entry["payload"]["stage_name"])
            stage_state_updates[f"pre_enrichment.stage_states.{stage_name}.work_item_id"] = result.document.get("_id")

        if changed:
            set_doc = {"pre_enrichment.pending_next_stages": pending, "updated_at": current_time}
            set_doc.update(stage_state_updates)
            level2.update_one({"_id": doc["_id"]}, {"$set": set_doc})

    return stats


def finalize_cv_ready(
    db: Any,
    *,
    level2_id: ObjectId | str,
    now: Optional[datetime] = None,
) -> bool:
    """Atomically finalize a DAG-owned job to `cv_ready` when all required stages are complete."""
    current_time = now or utc_now()
    level2 = db["level-2"]
    doc = level2.find_one({"_id": _coerce_object_id(level2_id)})
    if doc is None:
        return False

    pre = doc.get("pre_enrichment") or {}
    snapshot_id = pre.get("input_snapshot_id")
    if not snapshot_id:
        return False

    required_stages = [stage.name for stage in iter_stage_definitions() if stage.required_for_cv_ready]
    stage_states = pre.get("stage_states") or {}
    for stage_name in required_stages:
        state = stage_states.get(stage_name) or {}
        if state.get("status") != "completed":
            return False
        if state.get("input_snapshot_id") != snapshot_id:
            return False

    for entry in pre.get("pending_next_stages") or []:
        if entry.get("enqueued_at") is None:
            return False

    result = level2.update_one(
        {
            "_id": doc["_id"],
            "lifecycle": "preenriching",
            "$or": [
                {"pre_enrichment.cv_ready_at": {"$exists": False}},
                {"pre_enrichment.cv_ready_at": None},
            ],
            "pre_enrichment.input_snapshot_id": snapshot_id,
        },
        {
            "$set": {
                "lifecycle": "cv_ready",
                "pre_enrichment.cv_ready_at": current_time,
                "updated_at": current_time,
            }
        },
    )
    if result.modified_count == 1:
        db["preenrich_job_runs"].update_one(
            {"level2_job_id": str(doc["_id"]), "status": {"$ne": "completed"}},
            {"$set": {"status": "completed", "updated_at": current_time, "completed_at": current_time}},
        )
        return True
    return False


def release_expired_stage_leases(
    db: Any,
    *,
    now: Optional[datetime] = None,
    limit: int = 100,
) -> dict[str, int]:
    """Return expired leased stage work items to the queue with backoff applied."""
    current_time = now or utc_now()
    work_items = db["work_items"]
    level2 = db["level-2"]
    query = {
        "lane": "preenrich",
        "status": "leased",
        **_lte_now("lease_expires_at", current_time, collection=work_items),
    }
    stats = {"released": 0}
    cursor = work_items.find(query).limit(limit)
    for item in cursor:
        new_attempt_count = int(item.get("attempt_count", 0)) + 1
        available_at = current_time + timedelta(seconds=retry_delay_seconds(new_attempt_count))
        updated = work_items.find_one_and_update(
            {
                "_id": item["_id"],
                "status": "leased",
                **_lte_now("lease_expires_at", current_time, collection=work_items),
            },
            {
                "$set": {
                    "status": "pending",
                    "available_at": available_at,
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "updated_at": current_time,
                    "last_error": {
                        "class": "lease_expired",
                        "message": "leased stage work item expired before completion",
                        "at": current_time,
                    },
                },
                "$setOnInsert": {},
                "$inc": {"attempt_count": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            continue

        payload = item.get("payload") or {}
        stage_name = str(payload.get("stage_name") or _task_type_to_stage(item["task_type"]))
        level2.update_one(
            {"_id": _coerce_object_id(item["subject_id"])},
            {
                "$set": {
                    f"pre_enrichment.stage_states.{stage_name}.status": "pending",
                    f"pre_enrichment.stage_states.{stage_name}.attempt_count": new_attempt_count,
                    f"pre_enrichment.stage_states.{stage_name}.lease_owner": None,
                    f"pre_enrichment.stage_states.{stage_name}.lease_expires_at": None,
                    f"pre_enrichment.stage_states.{stage_name}.last_error": {
                        "class": "lease_expired",
                        "message": "leased stage work item expired before completion",
                        "at": current_time,
                    },
                    "updated_at": current_time,
                }
            },
        )
        stats["released"] += 1

    return stats


def invalidate_snapshot_if_changed(
    db: Any,
    *,
    level2_id: ObjectId | str,
    now: Optional[datetime] = None,
) -> bool:
    """Invalidate stale stage work when a DAG-owned job's snapshot has changed."""
    current_time = now or utc_now()
    queue = WorkItemQueue(db)
    level2 = db["level-2"]
    doc = level2.find_one({"_id": _coerce_object_id(level2_id)})
    if doc is None:
        return False

    pre = doc.get("pre_enrichment") or {}
    if pre.get("orchestration") != "dag":
        return False
    if doc.get("lifecycle") != "preenriching":
        return False

    dag_version = str(pre.get("dag_version") or DAG_VERSION)
    new_jd_checksum = jd_checksum(doc.get("description", "") or doc.get("job_description", "") or "")
    new_company_checksum = company_checksum(doc.get("company"), doc.get("company_domain"))
    new_snapshot = input_snapshot_id(new_jd_checksum, new_company_checksum, dag_version)
    if new_snapshot == pre.get("input_snapshot_id"):
        return False

    session_id = ((doc.get("observability") or {}).get("langfuse_session_id")) or f"job:{doc['_id']}"
    cancelled_states = build_stage_states(new_snapshot)
    for stage_name, old_state in ((pre.get("stage_states") or {}).items()):
        if stage_name not in cancelled_states:
            continue
        if old_state.get("output_ref") is not None:
            cancelled_states[stage_name]["output_ref"] = old_state["output_ref"]
        cancelled_states[stage_name]["last_error"] = {
            "class": "snapshot_changed",
            "message": "stage invalidated because the job snapshot changed",
            "at": current_time,
        }

    queue.collection.update_many(
        {
            "lane": "preenrich",
            "subject_id": str(doc["_id"]),
            "status": {"$in": ["pending", "leased", "failed"]},
            "payload.input_snapshot_id": {"$ne": new_snapshot},
        },
        {
            "$set": {
                "status": "cancelled",
                "lease_owner": None,
                "lease_expires_at": None,
                "updated_at": current_time,
                "last_error": {
                    "class": "snapshot_changed",
                    "message": "work item invalidated because the job snapshot changed",
                    "at": current_time,
                },
            }
        },
    )

    root_definition = get_stage_definition(ROOT_STAGE)
    root_result = queue.enqueue(
        task_type=root_definition.task_type,
        lane="preenrich",
        consumer_mode="native_stage_dag",
        subject_type="job",
        subject_id=str(doc["_id"]),
        priority=root_definition.default_priority,
        available_at=current_time,
        max_attempts=root_definition.max_attempts,
        idempotency_key=idempotency_key(ROOT_STAGE, str(doc["_id"]), new_snapshot),
        correlation_id=session_id,
        payload={
            "stage_name": ROOT_STAGE,
            "input_snapshot_id": new_snapshot,
            "jd_checksum": new_jd_checksum,
            "company_checksum": new_company_checksum,
            "dag_version": dag_version,
            "schema_version": SCHEMA_VERSION,
            "langfuse_session_id": session_id,
        },
    )
    cancelled_states[ROOT_STAGE]["work_item_id"] = root_result.document.get("_id")

    level2.update_one(
        {"_id": doc["_id"]},
        {
            "$set": {
                "pre_enrichment.input_snapshot_id": new_snapshot,
                "pre_enrichment.jd_checksum": new_jd_checksum,
                "pre_enrichment.company_checksum": new_company_checksum,
                "pre_enrichment.stage_states": cancelled_states,
                "pre_enrichment.pending_next_stages": [],
                "pre_enrichment.last_error": {
                    "stage": ROOT_STAGE,
                    "class": "snapshot_changed",
                    "message": "job snapshot changed; DAG stages reset to the new snapshot",
                    "at": current_time,
                },
                "pre_enrichment.snapshot_revalidated_at": current_time,
                "updated_at": current_time,
            }
        },
    )
    return True


def retry_delay_seconds(attempt_count: int) -> int:
    """Return the configured retry backoff for a stage attempt count."""
    index = max(0, min(attempt_count - 1, len(RETRY_BACKOFF_SECONDS) - 1))
    return RETRY_BACKOFF_SECONDS[index]


def _coerce_object_id(value: ObjectId | str) -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    return ObjectId(str(value))


def _lte_now(field_name: str, current_time: datetime, *, collection: Any) -> dict[str, Any]:
    """Build a `$lte now` filter using `$$NOW` in production and a local fallback in mongomock tests."""
    module_name = type(collection).__module__
    if "mongomock" in module_name:
        return {field_name: {"$lte": current_time}}
    return {"$expr": {"$lte": [f"${field_name}", "$$NOW"]}}


def _task_type_to_stage(task_type: str) -> str:
    """Convert `preenrich.<stage>` task names back to stage names."""
    return task_type.split(".", 1)[1]


def finalize_cv_ready_scan(db: Any, *, now: Optional[datetime] = None, limit: int = 100) -> dict[str, int]:
    """Scan preenriching DAG jobs and attempt cv_ready finalization."""
    current_time = now or utc_now()
    level2 = db["level-2"]
    stats = {"finalized": 0}
    cursor = level2.find(
        {
            "lifecycle": "preenriching",
            "pre_enrichment.orchestration": "dag",
        }
    ).limit(limit)
    for doc in cursor:
        if finalize_cv_ready(db, level2_id=doc["_id"], now=current_time):
            stats["finalized"] += 1
    return stats


def snapshot_invalidator_scan(db: Any, *, now: Optional[datetime] = None, limit: int = 100) -> dict[str, int]:
    """Scan DAG-owned preenriching jobs and invalidate any changed snapshots."""
    current_time = now or utc_now()
    level2 = db["level-2"]
    revalidate_window_seconds = int(os.getenv("PREENRICH_SNAPSHOT_REVALIDATE_WINDOW_SECONDS", "120"))
    stats = {"invalidated": 0}
    cursor = level2.find(
        {
            "lifecycle": "preenriching",
            "pre_enrichment.orchestration": "dag",
        }
    ).limit(limit)
    for doc in cursor:
        last_checked = ((doc.get("pre_enrichment") or {}).get("snapshot_revalidated_at"))
        if isinstance(last_checked, datetime):
            if (current_time - _ensure_utc(last_checked)).total_seconds() < revalidate_window_seconds:
                continue
        if invalidate_snapshot_if_changed(db, level2_id=doc["_id"], now=current_time):
            stats["invalidated"] += 1
    return stats


def _get_db() -> Any:
    from pymongo import MongoClient

    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set")
    return MongoClient(uri)["jobs"]


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Iteration-4 preenrich sweeper entrypoint")
    parser.add_argument(
        "command",
        choices=("next-stage", "stage", "cv-ready", "snapshot"),
        help="Which sweeper to run",
    )
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    db = _get_db()
    if args.command == "next-stage":
        stats = drain_pending_next_stages(db, limit=args.limit)
    elif args.command == "stage":
        stats = release_expired_stage_leases(db, limit=args.limit)
    elif args.command == "cv-ready":
        stats = finalize_cv_ready_scan(db, limit=args.limit)
    else:
        stats = snapshot_invalidator_scan(db, limit=args.limit)
    logger.info("preenrich sweeper command=%s stats=%s", args.command, stats)


if __name__ == "__main__":
    main()
