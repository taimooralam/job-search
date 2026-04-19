"""Root enqueuer for the iteration-4 preenrich DAG."""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from bson import ObjectId
from pymongo import ReturnDocument

from src.pipeline.queue import WorkItemQueue
from src.pipeline.tracing import emit_standalone_event
from src.preenrich.schema import idempotency_key, input_snapshot_id
from src.preenrich.stage_registry import get_stage_definition, iter_stage_definitions

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2
DAG_VERSION = "iteration4.v1"
ROOT_STAGE = "jd_structure"
ROOT_TASK_TYPE = "preenrich.jd_structure"
DEFAULT_BATCH_LIMIT = 25


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def is_stage_dag_enabled() -> bool:
    """Return whether the preenrich DAG path is enabled."""
    return os.getenv("PREENRICH_STAGE_DAG_ENABLED", "false").lower() == "true"


def parse_canary_allowlist(raw: Optional[str]) -> set[str]:
    """Parse the canary allowlist from CSV text."""
    if not raw:
        return set()
    return {item.strip() for item in raw.split(",") if item.strip()}


def canary_allows(level2_id: str, *, allowlist: set[str], pct: int) -> bool:
    """Return whether a job is allowed into the DAG canary."""
    if allowlist:
        return level2_id in allowlist
    if pct <= 0:
        return False
    if pct >= 100:
        return True
    bucket = int(hashlib.sha256(level2_id.encode("utf-8")).hexdigest()[:8], 16) % 100
    return bucket < pct


def build_stage_states(snapshot_id: str) -> dict[str, dict[str, Any]]:
    """Initialize the stage-state scaffold for a new DAG-owned job."""
    states: dict[str, dict[str, Any]] = {}
    for stage in iter_stage_definitions():
        states[stage.name] = {
            "status": "pending",
            "attempt_count": 0,
            "lease_owner": None,
            "lease_expires_at": None,
            "started_at": None,
            "completed_at": None,
            "input_snapshot_id": snapshot_id,
            "attempt_token": None,
            "jd_checksum_at_completion": None,
            "provider": None,
            "model": None,
            "prompt_version": None,
            "output_ref": None,
            "last_error": None,
            "work_item_id": None,
            "tokens_input": None,
            "tokens_output": None,
            "cost_usd": None,
        }
    return states


class RootEnqueuer:
    """Own selected jobs for the DAG path and seed the root stage work item."""

    def __init__(self, db: Any, *, queue: Optional[WorkItemQueue] = None) -> None:
        self.db = db
        self.level2 = db["level-2"]
        self.queue = queue or WorkItemQueue(db)

    def enqueue_ready_roots(self, *, limit: int = DEFAULT_BATCH_LIMIT, now: Optional[datetime] = None) -> dict[str, int]:
        """Enqueue up to `limit` selected jobs into the DAG path."""
        current_time = now or utc_now()
        if not is_stage_dag_enabled():
            return {"claimed": 0, "enqueued": 0, "skipped": 0}

        allowlist = parse_canary_allowlist(os.getenv("PREENRICH_DAG_CANARY_ALLOWLIST", ""))
        pct = int(os.getenv("PREENRICH_DAG_CANARY_PCT", "0") or "0")
        stats = {"claimed": 0, "enqueued": 0, "skipped": 0}

        cursor = self.level2.find(
            {
                "lifecycle": "selected",
                "pre_enrichment.orchestration": {"$in": [None, "legacy"]},
            },
            sort=[("selected_at", 1)],
            limit=limit,
        )
        for doc in cursor:
            level2_id = str(doc["_id"])
            if not canary_allows(level2_id, allowlist=allowlist, pct=pct):
                stats["skipped"] += 1
                continue
            created = self.enqueue_one(doc["_id"], now=current_time)
            if created:
                stats["claimed"] += 1
                stats["enqueued"] += 1
        return stats

    def enqueue_one(self, level2_id: ObjectId | str, *, now: Optional[datetime] = None) -> bool:
        """CAS ownership to the DAG path and seed the root work item."""
        current_time = now or utc_now()
        document = self.level2.find_one({"_id": _coerce_object_id(level2_id)})
        if document is None:
            return False

        jd_checksum = str(((document.get("pre_enrichment") or {}).get("jd_checksum")) or _checksum_or_empty(document.get("description", "")))
        company_checksum = str(
            ((document.get("pre_enrichment") or {}).get("company_checksum"))
            or _checksum_or_empty(document.get("company", ""))
        )
        snapshot_id = input_snapshot_id(jd_checksum, company_checksum, DAG_VERSION)
        session_id = f"job:{document['_id']}"

        claimed = self.level2.find_one_and_update(
            {
                "_id": document["_id"],
                "lifecycle": "selected",
                "pre_enrichment.orchestration": {"$in": [None, "legacy"]},
            },
            {
                "$set": {
                    "lifecycle": "preenriching",
                    "pre_enrichment.schema_version": SCHEMA_VERSION,
                    "pre_enrichment.dag_version": DAG_VERSION,
                    "pre_enrichment.input_snapshot_id": snapshot_id,
                    "pre_enrichment.jd_checksum": jd_checksum,
                    "pre_enrichment.company_checksum": company_checksum,
                    "pre_enrichment.orchestration": "dag",
                    "pre_enrichment.stage_states": build_stage_states(snapshot_id),
                    "pre_enrichment.pending_next_stages": [],
                    "pre_enrichment.cv_ready_at": None,
                    "pre_enrichment.last_error": None,
                    "pre_enrichment.deadletter_reason": None,
                    "observability.langfuse_session_id": session_id,
                    "updated_at": current_time,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if claimed is None:
            return False

        root_stage = get_stage_definition(ROOT_STAGE)
        enqueue_result = self.queue.enqueue(
            task_type=root_stage.task_type,
            lane="preenrich",
            consumer_mode="native_stage_dag",
            subject_type="job",
            subject_id=str(claimed["_id"]),
            priority=root_stage.default_priority,
            available_at=current_time,
            max_attempts=root_stage.max_attempts,
            idempotency_key=idempotency_key(ROOT_STAGE, str(claimed["_id"]), snapshot_id),
            correlation_id=session_id,
            payload={
                "stage_name": ROOT_STAGE,
                "input_snapshot_id": snapshot_id,
                "jd_checksum": jd_checksum,
                "company_checksum": company_checksum,
                "dag_version": DAG_VERSION,
                "schema_version": SCHEMA_VERSION,
                "langfuse_session_id": session_id,
            },
        )
        work_item_id = enqueue_result.document.get("_id")
        if work_item_id is not None:
            self.level2.update_one(
                {"_id": claimed["_id"]},
                {"$set": {f"pre_enrichment.stage_states.{ROOT_STAGE}.work_item_id": work_item_id}},
            )

        emit_standalone_event(
            name="scout.preenrich.enqueue_root",
            session_id=session_id,
            metadata={
                "job_id": str(claimed.get("job_id") or claimed["_id"]),
                "level2_job_id": str(claimed["_id"]),
                "stage_name": ROOT_STAGE,
                "input_snapshot_id": snapshot_id,
                "work_item_id": str(work_item_id) if work_item_id is not None else None,
                "lifecycle_before": "selected",
                "lifecycle_after": "preenriching",
            },
        )
        return True


def run_once(db: Any, *, limit: int = DEFAULT_BATCH_LIMIT, now: Optional[datetime] = None) -> dict[str, int]:
    """Run one root-enqueue scan against the provided database."""
    return RootEnqueuer(db).enqueue_ready_roots(limit=limit, now=now)


def _get_db() -> Any:
    """Connect to the jobs database from environment."""
    from pymongo import MongoClient

    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set")
    return MongoClient(uri)["jobs"]


def main() -> None:
    """CLI entrypoint for the root enqueuer one-shot job."""
    parser = argparse.ArgumentParser(description="Iteration-4 preenrich DAG root enqueuer")
    parser.add_argument("--limit", type=int, default=DEFAULT_BATCH_LIMIT, help="Max selected jobs to scan")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    stats = run_once(_get_db(), limit=args.limit)
    logger.info("preenrich root enqueuer stats=%s", stats)


def _checksum_or_empty(value: str) -> str:
    raw = value or ""
    return f"sha256:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


def _coerce_object_id(value: ObjectId | str) -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    return ObjectId(str(value))


if __name__ == "__main__":
    main()
