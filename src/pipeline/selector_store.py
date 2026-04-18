"""Mongo state helpers for iteration-3 selector runs and hit decisions."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.collection import Collection
from pymongo.database import Database

from src.pipeline.selector_common import POOL_MAX_AGE_HOURS, load_selector_profiles, utc_now

logger = logging.getLogger(__name__)


def build_selector_run_id(
    run_kind: str,
    scheduled_for: datetime,
    *,
    profile_name: Optional[str] = None,
) -> str:
    """Build a deterministic selector run id for one scheduled window."""
    timestamp = scheduled_for.strftime("%Y-%m-%dT%H-%M-%SZ")
    if run_kind == "profile":
        return f"selectorrun:profile:{profile_name}:{timestamp}"
    return f"selectorrun:main:{timestamp}"


def build_default_selection_state() -> dict[str, Any]:
    """Return the default selector scaffold for new discovery hits."""
    return {
        "main": {
            "status": "pending",
            "decision": "none",
            "selector_run_id": None,
            "reason": None,
            "rank": None,
            "selected_at": None,
            "level2_job_id": None,
            "level1_upserted_at": None,
            "history": [],
        },
        "pool": {
            "status": "not_applicable",
            "pooled_at": None,
            "expires_at": None,
        },
        "profiles": {},
    }


class SelectorStore:
    """Selector-specific Mongo helpers over scout_search_hits and selector_runs."""

    def __init__(self, db: Database):
        self.db = db
        self.search_hits: Collection = db["scout_search_hits"]
        self.selector_runs: Collection = db["selector_runs"]
        self.level2: Collection = db["level-2"]

    def ensure_indexes(self) -> None:
        """Create selector-stage indexes."""
        self.selector_runs.create_index([("run_id", ASCENDING)], unique=True, name="run_id_unique")
        self.selector_runs.create_index(
            [("run_kind", ASCENDING), ("scheduled_for", DESCENDING), ("status", ASCENDING)],
            name="run_kind_scheduled_for_status",
        )
        self.selector_runs.create_index(
            [("profile_name", ASCENDING), ("scheduled_for", DESCENDING)],
            name="profile_name_scheduled_for",
        )
        self.selector_runs.create_index([("status", ASCENDING), ("updated_at", DESCENDING)], name="status_updated_at")
        self.selector_runs.create_index([("scheduled_for", DESCENDING)], name="scheduled_for_desc")
        self.selector_runs.create_index(
            [("status", ASCENDING), ("scheduled_for", DESCENDING)],
            name="status_scheduled_for_desc",
        )

        self.search_hits.create_index(
            [("scrape.status", ASCENDING), ("scrape.completed_at", ASCENDING)],
            name="selector_scrape_status_completed_at",
        )
        self.search_hits.create_index(
            [("selection.main.status", ASCENDING), ("scrape.completed_at", ASCENDING)],
            name="selection_main_status_completed_at",
        )
        self.search_hits.create_index(
            [("selection.main.decision", ASCENDING), ("last_seen_at", DESCENDING)],
            name="selection_main_decision_last_seen_at",
        )
        self.search_hits.create_index(
            [("selection.pool.status", ASCENDING), ("selection.pool.expires_at", ASCENDING)],
            name="selection_pool_status_expires_at",
        )
        self.search_hits.create_index(
            [("selection.pool.status", ASCENDING), ("last_seen_at", DESCENDING)],
            name="selection_pool_status_last_seen_at",
        )
        self.search_hits.create_index(
            [("selection.main.selector_run_id", ASCENDING)],
            sparse=True,
            name="selection_main_selector_run_id",
        )
        self.search_hits.create_index(
            [("selection.main.level2_job_id", ASCENDING)],
            sparse=True,
            name="selection_main_level2_job_id",
        )
        for profile_name in load_selector_profiles().keys():
            self.search_hits.create_index(
                [(f"selection.profiles.{profile_name}.status", ASCENDING), ("scrape.completed_at", ASCENDING)],
                name=f"selection_profile_{profile_name}_status_completed_at",
            )

    def create_or_get_run(
        self,
        *,
        run_kind: str,
        scheduled_for: datetime,
        trigger_mode: str,
        profile_name: Optional[str] = None,
        cutoff_at: Optional[datetime] = None,
        now: Optional[datetime] = None,
    ) -> tuple[dict[str, Any], bool]:
        """Create or fetch an idempotent selector run for one schedule window."""
        current_time = now or utc_now()
        run_id = build_selector_run_id(run_kind, scheduled_for, profile_name=profile_name)
        existing = self.selector_runs.find_one({"run_id": run_id})
        if existing is not None:
            return existing, False

        document = {
            "run_id": run_id,
            "run_kind": run_kind,
            "profile_name": profile_name,
            "trigger_mode": trigger_mode,
            "status": "scheduled",
            "scheduled_for": scheduled_for,
            "started_at": None,
            "completed_at": None,
            "cutoff_at": cutoff_at or scheduled_for,
            "worker_id": None,
            "stats": {
                "candidates_seen": 0,
                "filtered_blacklist": 0,
                "filtered_non_english": 0,
                "filtered_score": 0,
                "duplicate_cross_location": 0,
                "duplicate_db": 0,
                "tier_low_level1": 0,
                "inserted_level2": 0,
                "selected_for_preenrich": 0,
                "discarded_quota": 0,
                "profile_selected": 0,
            },
            "errors": [],
            "decisions": [],
            "diff": None,
            "langfuse_session_id": run_id,
            "langfuse_trace_id": None,
            "langfuse_trace_url": None,
            "created_at": current_time,
            "updated_at": current_time,
        }
        self.selector_runs.insert_one(document)
        return self.selector_runs.find_one({"run_id": run_id}) or document, True

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        """Fetch one selector run document."""
        return self.selector_runs.find_one({"run_id": run_id})

    def claim_run(self, run_id: str, *, worker_id: str, now: Optional[datetime] = None) -> Optional[dict[str, Any]]:
        """Transition a scheduled or failed run into running ownership."""
        current_time = now or utc_now()
        return self.selector_runs.find_one_and_update(
            {"run_id": run_id, "status": {"$in": ["scheduled", "failed"]}},
            {
                "$set": {
                    "status": "running",
                    "started_at": current_time,
                    "worker_id": worker_id,
                    "updated_at": current_time,
                }
            },
            return_document=ReturnDocument.AFTER,
        )

    def finalize_run(
        self,
        run_id: str,
        *,
        status: str,
        stats: dict[str, int],
        errors: Optional[list[dict[str, Any]]] = None,
        decisions: Optional[list[dict[str, Any]]] = None,
        diff: Optional[dict[str, Any]] = None,
        now: Optional[datetime] = None,
    ) -> None:
        """Finalize a selector run with its durable summary."""
        current_time = now or utc_now()
        update: dict[str, Any] = {
            "status": status,
            "stats": stats,
            "errors": errors or [],
            "completed_at": current_time,
            "updated_at": current_time,
        }
        if decisions is not None:
            update["decisions"] = decisions[:100]
        if diff is not None:
            update["diff"] = diff
        self.selector_runs.update_one({"run_id": run_id}, {"$set": update})

    def touch_run(self, run_id: str, *, now: Optional[datetime] = None) -> None:
        """Refresh the run updated_at field during long processing."""
        self.selector_runs.update_one({"run_id": run_id}, {"$set": {"updated_at": now or utc_now()}})

    def attach_trace_metadata(
        self,
        run_id: str,
        *,
        trace_id: Optional[str],
        trace_url: Optional[str],
        now: Optional[datetime] = None,
    ) -> None:
        """Persist Langfuse trace metadata for one selector run."""
        update: dict[str, Any] = {"updated_at": now or utc_now()}
        if trace_id is not None:
            update["langfuse_trace_id"] = trace_id
        if trace_url is not None:
            update["langfuse_trace_url"] = trace_url
        self.selector_runs.update_one({"run_id": run_id}, {"$set": update})

    def load_main_candidates(self, *, cutoff_at: datetime, run_id: Optional[str] = None) -> list[dict[str, Any]]:
        """Load main-selector candidates from Mongo-authoritative payloads."""
        query: dict[str, Any] = {
            "scrape.status": "succeeded",
            "scrape.selector_payload": {"$exists": True, "$ne": None},
            "scrape.completed_at": {"$lte": cutoff_at},
            "$or": [
                {"selection.main.status": {"$in": ["pending", "failed"]}},
            ],
        }
        if run_id:
            query["$or"].append(
                {"selection.main.selector_run_id": run_id, "selection.main.status": {"$in": ["leased", "completed"]}}
            )
        documents = list(self.search_hits.find(query).sort([("scrape.completed_at", ASCENDING)]))
        return [self._hydrate_selector_candidate(document) for document in documents]

    def load_profile_candidates(
        self,
        *,
        profile_name: str,
        cutoff_at: datetime,
        now: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        """Load profile-selector candidates from the durable pool state."""
        current_time = now or utc_now()
        self.expire_pool_entries(now=current_time)

        decision_path = f"selection.profiles.{profile_name}.decision"
        query: dict[str, Any] = {
            "scrape.status": "succeeded",
            "scrape.selector_payload": {"$exists": True, "$ne": None},
            "scrape.completed_at": {"$lte": cutoff_at},
            "selection.pool.status": "available",
            "selection.pool.expires_at": {"$gt": current_time},
            "$or": [
                {decision_path: {"$exists": False}},
                {decision_path: {"$nin": ["profile_selected", "duplicate_db"]}},
            ],
        }
        documents = list(self.search_hits.find(query).sort([("selection.pool.pooled_at", DESCENDING)]))
        return [self._hydrate_selector_candidate(document) for document in documents]

    def mark_main_candidates_leased(self, hit_ids: list[Any], *, run_id: str, now: Optional[datetime] = None) -> None:
        """Mark a batch of main-selector candidates leased for one run."""
        current_time = now or utc_now()
        if not hit_ids:
            return
        self.search_hits.update_many(
            {"_id": {"$in": [_coerce_object_id(hit_id) for hit_id in hit_ids]}},
            {
                "$set": {
                    "selection.main.status": "leased",
                    "selection.main.selector_run_id": run_id,
                    "updated_at": current_time,
                }
            },
        )

    def release_main_leases_for_run(self, run_id: str, *, now: Optional[datetime] = None) -> None:
        """Reset stranded main-selector leases after a failed run."""
        current_time = now or utc_now()
        self.search_hits.update_many(
            {"selection.main.selector_run_id": run_id, "selection.main.status": "leased"},
            {"$set": {"selection.main.status": "failed", "updated_at": current_time}},
        )

    def apply_main_decision(
        self,
        hit_id: Any,
        *,
        run_id: str,
        decision: str,
        reason: Optional[str],
        rank: Optional[int] = None,
        selected_at: Optional[datetime] = None,
        level2_job_id: Optional[Any] = None,
        level1_upserted_at: Optional[datetime] = None,
        now: Optional[datetime] = None,
    ) -> None:
        """Persist one main-selector decision and append bounded history."""
        current_time = now or utc_now()
        set_doc: dict[str, Any] = {
            "selection.main.status": "completed",
            "selection.main.decision": decision,
            "selection.main.selector_run_id": run_id,
            "trace.selector_run_id": run_id,
            "selection.main.reason": reason,
            "selection.main.rank": rank,
            "selection.main.selected_at": selected_at,
            "selection.main.level2_job_id": str(level2_job_id) if level2_job_id is not None else None,
            "selection.main.level1_upserted_at": level1_upserted_at,
            "updated_at": current_time,
        }
        self.search_hits.update_one(
            {"_id": _coerce_object_id(hit_id)},
            {
                "$set": set_doc,
                "$push": {
                    "selection.main.history": {
                        "$each": [{"run_id": run_id, "decision": decision, "reason": reason, "at": current_time}],
                        "$slice": -20,
                    }
                },
            },
        )

    def set_pool_status(
        self,
        hit_id: Any,
        *,
        status: str,
        pooled_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
        now: Optional[datetime] = None,
    ) -> None:
        """Persist pool availability or expiry state on one hit."""
        current_time = now or utc_now()
        self.search_hits.update_one(
            {"_id": _coerce_object_id(hit_id)},
            {
                "$set": {
                    "selection.pool.status": status,
                    "selection.pool.pooled_at": pooled_at,
                    "selection.pool.expires_at": expires_at,
                    "updated_at": current_time,
                }
            },
        )

    def expire_pool_entries(self, *, now: Optional[datetime] = None) -> int:
        """Mark stale pool entries expired."""
        current_time = now or utc_now()
        result = self.search_hits.update_many(
            {"selection.pool.status": "available", "selection.pool.expires_at": {"$lte": current_time}},
            {"$set": {"selection.pool.status": "expired", "updated_at": current_time}},
        )
        return int(result.modified_count)

    def apply_profile_decision(
        self,
        hit_id: Any,
        *,
        profile_name: str,
        run_id: str,
        decision: str,
        reason: Optional[str],
        rank_score: Optional[float] = None,
        selected_at: Optional[datetime] = None,
        level2_job_id: Optional[Any] = None,
        now: Optional[datetime] = None,
    ) -> None:
        """Persist one per-profile decision and append bounded history."""
        current_time = now or utc_now()
        prefix = f"selection.profiles.{profile_name}"
        update: dict[str, Any] = {
            f"{prefix}.status": "completed",
            f"{prefix}.decision": decision,
            f"{prefix}.selector_run_id": run_id,
            "trace.selector_run_id": run_id,
            f"{prefix}.reason": reason,
            f"{prefix}.rank_score": rank_score,
            f"{prefix}.selected_at": selected_at,
            f"{prefix}.level2_job_id": str(level2_job_id) if level2_job_id is not None else None,
            "updated_at": current_time,
        }
        self.search_hits.update_one(
            {"_id": _coerce_object_id(hit_id)},
            {
                "$set": update,
                "$push": {
                    f"{prefix}.history": {
                        "$each": [{"run_id": run_id, "decision": decision, "reason": reason, "at": current_time}],
                        "$slice": -20,
                    }
                },
            },
        )

    def mark_profile_candidates_leased(
        self,
        hit_ids: list[Any],
        *,
        profile_name: str,
        run_id: str,
        now: Optional[datetime] = None,
    ) -> None:
        """Lease a batch of profile-selector candidates."""
        current_time = now or utc_now()
        if not hit_ids:
            return
        prefix = f"selection.profiles.{profile_name}"
        self.search_hits.update_many(
            {"_id": {"$in": [_coerce_object_id(hit_id) for hit_id in hit_ids]}},
            {"$set": {f"{prefix}.status": "leased", f"{prefix}.selector_run_id": run_id, "updated_at": current_time}},
        )

    def release_profile_leases_for_run(
        self,
        profile_name: str,
        run_id: str,
        *,
        now: Optional[datetime] = None,
    ) -> None:
        """Reset stranded profile-selector leases after a failed run."""
        current_time = now or utc_now()
        prefix = f"selection.profiles.{profile_name}"
        self.search_hits.update_many(
            {f"{prefix}.selector_run_id": run_id, f"{prefix}.status": "leased"},
            {"$set": {f"{prefix}.status": "failed", "updated_at": current_time}},
        )

    def get_level2_doc(self, level2_job_id: Optional[str]) -> Optional[dict[str, Any]]:
        """Fetch one linked level-2 document by stored id."""
        if not level2_job_id:
            return None
        try:
            return self.level2.find_one({"_id": ObjectId(level2_job_id)})
        except Exception:
            return None

    def _hydrate_selector_candidate(self, document: dict[str, Any]) -> dict[str, Any]:
        payload = dict((document.get("scrape") or {}).get("selector_payload") or {})
        payload["_hit_id"] = document["_id"]
        payload["_hit_document"] = document
        pooled_at = ((document.get("selection") or {}).get("pool") or {}).get("pooled_at")
        if pooled_at is not None:
            payload["pooled_at"] = pooled_at
        return payload


def pool_expiry_from(reference_time: datetime) -> datetime:
    """Return the durable pool expiry timestamp for one main-selector run."""
    return reference_time + timedelta(hours=POOL_MAX_AGE_HOURS)


def _coerce_object_id(value: Any) -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    return ObjectId(str(value))
