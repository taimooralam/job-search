"""Mongo work-item queue primitives for discovery and native scrape migration slices."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from bson import ObjectId
from pymongo import ASCENDING, ReturnDocument
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class EnqueueResult:
    """Result of enqueueing one work item."""

    created: bool
    document: dict[str, Any]


class WorkItemQueue:
    """Queue semantics for iteration-1/2 scrape ownership and compatibility handoff."""

    def __init__(self, db: Database):
        self.db = db
        self.collection: Collection = db["work_items"]

    def ensure_indexes(self) -> None:
        """Create the indexes used by the discovery and scrape workers."""
        self.collection.create_index(
            [("idempotency_key", ASCENDING)],
            unique=True,
            name="idempotency_key_unique",
        )
        self.collection.create_index(
            [("status", ASCENDING), ("lane", ASCENDING), ("consumer_mode", ASCENDING), ("available_at", ASCENDING)],
            name="status_lane_consumer_available_at",
        )
        self.collection.create_index(
            [("subject_type", ASCENDING), ("subject_id", ASCENDING)],
            name="subject_lookup",
        )
        self.collection.create_index(
            [("task_type", ASCENDING), ("status", ASCENDING), ("available_at", ASCENDING)],
            name="task_status_available_at",
        )
        self.collection.create_index(
            [("lane", ASCENDING), ("status", ASCENDING), ("lease_expires_at", ASCENDING)],
            name="lane_status_lease_expires_at",
        )
        self.collection.create_index([("correlation_id", ASCENDING)], name="correlation_id")
        self.collection.create_index(
            [("task_type", ASCENDING), ("consumer_mode", ASCENDING), ("status", ASCENDING), ("updated_at", ASCENDING)],
            name="task_consumer_status_updated_at",
        )
        self.collection.create_index(
            [("task_type", ASCENDING), ("consumer_mode", ASCENDING), ("created_at", ASCENDING)],
            name="task_consumer_created_at",
        )
        self.collection.create_index(
            [
                ("lane", ASCENDING),
                ("consumer_mode", ASCENDING),
                ("status", ASCENDING),
                ("available_at", ASCENDING),
                ("priority", ASCENDING),
                ("created_at", ASCENDING),
            ],
            name="lane_consumer_status_available_priority_created",
        )

    def enqueue(
        self,
        *,
        task_type: str,
        lane: str,
        consumer_mode: str,
        subject_type: str,
        subject_id: ObjectId | str,
        priority: int,
        available_at: Optional[datetime],
        max_attempts: int,
        idempotency_key: str,
        correlation_id: str,
        payload: dict[str, Any],
        result_ref: Optional[dict[str, Any]] = None,
        revive_statuses: Optional[Iterable[str]] = None,
        now: Optional[datetime] = None,
    ) -> EnqueueResult:
        """Idempotently enqueue one work item."""
        current_time = now or utc_now()
        subject_value = str(subject_id)
        existing = self.collection.find_one({"idempotency_key": idempotency_key})
        if existing is not None:
            revivable = set(revive_statuses or ())
            if existing.get("status") in revivable:
                default_result_ref = result_ref or {
                    "legacy_queue_written": False,
                    "legacy_queue_written_at": None,
                    "scrape_status": None,
                    "scored_jsonl_written": False,
                    "scored_jsonl_written_at": None,
                    "level1_upserted": False,
                    "level1_upserted_at": None,
                }
                revived = self.collection.find_one_and_update(
                    {
                        "_id": existing["_id"],
                        "status": existing.get("status"),
                    },
                    {
                        "$set": {
                            "task_type": task_type,
                            "lane": lane,
                            "consumer_mode": consumer_mode,
                            "subject_type": subject_type,
                            "subject_id": subject_value,
                            "status": "pending",
                            "priority": priority,
                            "available_at": available_at or current_time,
                            "lease_owner": None,
                            "lease_expires_at": None,
                            "attempt_count": 0,
                            "max_attempts": max_attempts,
                            "correlation_id": correlation_id,
                            "payload": payload,
                            "result_ref": default_result_ref,
                            "last_error": None,
                            "updated_at": current_time,
                        }
                    },
                    return_document=ReturnDocument.AFTER,
                )
                if revived is not None:
                    return EnqueueResult(created=False, document=revived)
            return EnqueueResult(created=False, document=existing)

        document = {
            "task_type": task_type,
            "lane": lane,
            "consumer_mode": consumer_mode,
            "subject_type": subject_type,
            "subject_id": subject_value,
            "status": "pending",
            "priority": priority,
            "available_at": available_at or current_time,
            "lease_owner": None,
            "lease_expires_at": None,
            "attempt_count": 0,
            "max_attempts": max_attempts,
            "idempotency_key": idempotency_key,
            "correlation_id": correlation_id,
            "payload": payload,
            "result_ref": result_ref or {
                "legacy_queue_written": False,
                "legacy_queue_written_at": None,
                "scrape_status": None,
                "scored_jsonl_written": False,
                "scored_jsonl_written_at": None,
                "level1_upserted": False,
                "level1_upserted_at": None,
            },
            "last_error": None,
            "created_at": current_time,
            "updated_at": current_time,
        }
        try:
            inserted = self.collection.insert_one(document)
        except DuplicateKeyError:
            existing = self.collection.find_one({"idempotency_key": idempotency_key})
            if existing is None:
                raise
            return EnqueueResult(created=False, document=existing)
        document["_id"] = inserted.inserted_id
        return EnqueueResult(created=True, document=document)

    def claim_next(
        self,
        *,
        task_type: Optional[str] = None,
        lane: str,
        worker_name: str,
        consumer_mode: Optional[str] = None,
        lease_seconds: int = 300,
        exclude_ids: Optional[Iterable[str]] = None,
        now: Optional[datetime] = None,
    ) -> Optional[dict[str, Any]]:
        """Claim the next eligible work item with a lease."""
        current_time = now or utc_now()
        lease_expires_at = current_time + timedelta(seconds=lease_seconds)
        base_query: dict[str, Any] = {
            "lane": lane,
            "$or": [
                {
                    "status": {"$in": ["pending", "failed"]},
                    "available_at": {"$lte": current_time},
                },
                {
                    "status": "leased",
                    "lease_expires_at": {"$lte": current_time},
                },
            ],
        }
        if task_type is not None:
            base_query["task_type"] = task_type
        if consumer_mode is not None:
            base_query["consumer_mode"] = consumer_mode
        excluded = list(exclude_ids or [])
        if excluded:
            base_query["_id"] = {"$nin": [_coerce_object_id(item_id) for item_id in excluded]}

        candidates = list(
            self.collection.find(base_query)
            .sort([("priority", ASCENDING), ("created_at", ASCENDING)])
            .limit(25)
        )
        for candidate in candidates:
            if candidate.get("attempt_count", 0) >= candidate.get("max_attempts", 5):
                self.mark_deadletter(
                    candidate["_id"],
                    error="max_attempts_exhausted_before_claim",
                    now=current_time,
                )
                continue

            claim_query = {
                "_id": candidate["_id"],
                "$or": [
                    {
                        "status": {"$in": ["pending", "failed"]},
                        "available_at": {"$lte": current_time},
                    },
                    {
                        "status": "leased",
                        "lease_expires_at": {"$lte": current_time},
                    },
                ],
            }
            updated = self.collection.find_one_and_update(
                claim_query,
                {
                    "$set": {
                        "status": "leased",
                        "lease_owner": worker_name,
                        "lease_expires_at": lease_expires_at,
                        "updated_at": current_time,
                    },
                    "$inc": {
                        "attempt_count": 1,
                    },
                },
                return_document=ReturnDocument.AFTER,
            )
            if updated is not None:
                return updated

        return None

    def heartbeat(
        self,
        work_item_id: ObjectId | str,
        *,
        lease_owner: str,
        lease_seconds: int = 300,
        now: Optional[datetime] = None,
    ) -> bool:
        """Extend a lease for an owned work item."""
        current_time = now or utc_now()
        result = self.collection.update_one(
            {
                "_id": _coerce_object_id(work_item_id),
                "status": "leased",
                "lease_owner": lease_owner,
            },
            {
                "$set": {
                    "lease_expires_at": current_time + timedelta(seconds=lease_seconds),
                    "updated_at": current_time,
                }
            },
        )
        return result.modified_count == 1

    def mark_done(
        self,
        work_item_id: ObjectId | str,
        *,
        result_ref: Optional[dict[str, Any]] = None,
        now: Optional[datetime] = None,
    ) -> None:
        """Mark a work item done after a successful legacy handoff."""
        current_time = now or utc_now()
        update: dict[str, Any] = {
            "status": "done",
            "lease_owner": None,
            "lease_expires_at": None,
            "updated_at": current_time,
        }
        if result_ref is not None:
            update["result_ref"] = result_ref
        self.collection.update_one(
            {"_id": _coerce_object_id(work_item_id)},
            {"$set": update},
        )

    def patch_result_ref(
        self,
        work_item_id: ObjectId | str,
        *,
        patch: dict[str, Any],
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Merge a partial result_ref update into the work item."""
        current_time = now or utc_now()
        set_fields = {f"result_ref.{key}": value for key, value in patch.items()}
        set_fields["updated_at"] = current_time
        self.collection.update_one({"_id": _coerce_object_id(work_item_id)}, {"$set": set_fields})
        return self.collection.find_one({"_id": _coerce_object_id(work_item_id)}) or {}

    def mark_failed(
        self,
        work_item_id: ObjectId | str,
        *,
        error: str,
        retry_delay_seconds: Optional[int] = None,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Mark a work item failed, or deadletter if retries are exhausted."""
        current_time = now or utc_now()
        work_item = self.collection.find_one({"_id": _coerce_object_id(work_item_id)})
        if work_item is None:
            raise KeyError(f"Unknown work item: {work_item_id}")

        if work_item.get("attempt_count", 0) >= work_item.get("max_attempts", 5):
            self.mark_deadletter(work_item["_id"], error=error, now=current_time)
            return self.collection.find_one({"_id": work_item["_id"]}) or {}

        delay_seconds = retry_delay_seconds
        if delay_seconds is None:
            delay_seconds = min(300, 30 * max(1, work_item.get("attempt_count", 1)))

        self.collection.update_one(
            {"_id": work_item["_id"]},
            {
                "$set": {
                    "status": "failed",
                    "available_at": current_time + timedelta(seconds=delay_seconds),
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "last_error": {
                        "message": error,
                        "type": "retryable",
                        "failed_at": current_time,
                    },
                    "updated_at": current_time,
                }
            },
        )
        return self.collection.find_one({"_id": work_item["_id"]}) or {}

    def mark_deadletter(
        self,
        work_item_id: ObjectId | str,
        *,
        error: str,
        now: Optional[datetime] = None,
    ) -> None:
        """Move a work item to deadletter state."""
        current_time = now or utc_now()
        self.collection.update_one(
            {"_id": _coerce_object_id(work_item_id)},
            {
                "$set": {
                    "status": "deadletter",
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "last_error": {
                        "message": error,
                        "type": "deadletter",
                        "failed_at": current_time,
                    },
                    "updated_at": current_time,
                }
            },
        )

    def get_snapshot(
        self,
        *,
        task_type: Optional[str] = None,
        consumer_mode: Optional[str] = None,
    ) -> dict[str, int]:
        """Return coarse queue counts for the discovery UI."""
        query: dict[str, Any] = {}
        if task_type is not None:
            query["task_type"] = task_type
        if consumer_mode is not None:
            query["consumer_mode"] = consumer_mode
        return {
            status: self.collection.count_documents({**query, "status": status})
            for status in ("pending", "leased", "done", "failed", "deadletter")
        }

    def recent_failures(
        self,
        *,
        task_type: Optional[str] = None,
        consumer_mode: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return recent failed or deadlettered items."""
        query: dict[str, Any] = {"status": {"$in": ["failed", "deadletter"]}}
        if task_type is not None:
            query["task_type"] = task_type
        if consumer_mode is not None:
            query["consumer_mode"] = consumer_mode
        return list(
            self.collection.find(query)
            .sort([("updated_at", -1)])
            .limit(limit)
        )


def iter_active_statuses() -> Iterable[str]:
    """Statuses that still represent outstanding work."""
    return ("pending", "leased", "failed")


def _coerce_object_id(value: ObjectId | str) -> ObjectId:
    """Convert string ids back to ObjectId where possible."""
    if isinstance(value, ObjectId):
        return value
    return ObjectId(str(value))
