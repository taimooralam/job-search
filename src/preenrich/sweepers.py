"""Iteration-4 preenrich sweepers and shared finalizers."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId

from src.pipeline.queue import WorkItemQueue
from src.preenrich.stage_registry import get_stage_definition, iter_stage_definitions

logger = logging.getLogger(__name__)


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
    return result.modified_count == 1


def _coerce_object_id(value: ObjectId | str) -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    return ObjectId(str(value))
