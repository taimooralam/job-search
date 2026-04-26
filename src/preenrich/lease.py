"""
Lease-based job claim for the pre-enrichment worker.

Implements an atomic findOneAndUpdate pattern so multiple worker replicas
can safely compete for work without PID files or cron coordination (§2.2).

A job in lifecycle "selected" or "stale" is claimable when its lease has
expired or has never been set. The claiming worker sets lifecycle to
"preenriching", records its identity, and must renew the lease every
HEARTBEAT_SECONDS seconds.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from pymongo import ASCENDING, ReturnDocument

from src.pipeline.tracing import emit_standalone_event

logger = logging.getLogger(__name__)

# Lease duration constants
LEASE_MINUTES: int = 10
HEARTBEAT_SECONDS: int = 60


def _now_utc() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(timezone.utc)


def _emit_legacy_lease_event(
    *,
    name: str,
    job_id: Any,
    worker_id: str,
    lifecycle_before: str,
    lifecycle_after: str,
) -> None:
    level2_job_id = str(job_id)
    session_id = f"job:{level2_job_id}"
    metadata: Dict[str, Any] = {
        "job_id": level2_job_id,
        "level2_job_id": level2_job_id,
        "correlation_id": session_id,
        "langfuse_session_id": session_id,
        "run_id": f"preenrich:legacy:{name}:{level2_job_id}",
        "worker_id": worker_id,
        "task_type": name,
        "stage_name": "legacy",
        "attempt_count": None,
        "attempt_token": None,
        "input_snapshot_id": None,
        "jd_checksum": None,
        "lifecycle_before": lifecycle_before,
        "lifecycle_after": lifecycle_after,
        "work_item_id": None,
        "source": "legacy_lease",
    }
    try:
        emit_standalone_event(name=name, session_id=session_id, metadata=metadata)
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("Lease tracing failed for %s %s: %s", name, level2_job_id, exc)


def claim_one(
    db: Any,
    worker_id: str,
    now: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """
    Atomically claim one job from the "selected" or "stale" lifecycle state.

    Uses findOneAndUpdate to ensure only one worker acquires the lease even
    under concurrent execution (§2.2 / BDD S5).

    Args:
        db: Motor or PyMongo database handle (must have a "level-2" collection)
        worker_id: Unique worker identity string (hostname + pid + uuid)
        now: Override for current time (default: UTC now). Used in tests.

    Returns:
        The updated job document (with "preenriching" lifecycle) or None if
        no claimable job is available.
    """
    if now is None:
        now = _now_utc()

    lease_expires_at = now + timedelta(minutes=LEASE_MINUTES)

    result = db["level-2"].find_one_and_update(
        {
            "lifecycle": {"$in": ["selected", "stale"]},
            "pre_enrichment.orchestration": {"$ne": "dag"},
            "$or": [
                {"lease_expires_at": {"$lt": now}},
                {"lease_expires_at": None},
                {"lease_expires_at": {"$exists": False}},
            ],
        },
        {
            "$set": {
                "lifecycle": "preenriching",
                "lease_owner": worker_id,
                "lease_expires_at": lease_expires_at,
                "lease_heartbeat_at": now,
            }
        },
        sort=[("selected_at", ASCENDING)],
        return_document=ReturnDocument.AFTER,
    )
    if result is not None:
        _emit_legacy_lease_event(
            name="scout.preenrich.legacy_claim",
            job_id=result["_id"],
            worker_id=worker_id,
            lifecycle_before="selected_or_stale",
            lifecycle_after="preenriching",
        )
    return result


def heartbeat(
    db: Any,
    job_id: Any,
    worker_id: str,
    now: Optional[datetime] = None,
) -> bool:
    """
    Renew the lease for a job the worker currently holds.

    Updates lease_expires_at and lease_heartbeat_at only if the worker_id
    matches the current lease_owner, preventing a crashed worker from
    inadvertently renewing a lease that another worker has taken over.

    Args:
        db: Database handle
        job_id: MongoDB _id of the job document
        worker_id: This worker's identity string
        now: Override for current time (default: UTC now). Used in tests.

    Returns:
        True if the heartbeat was applied, False if lease was lost.
    """
    if now is None:
        now = _now_utc()

    lease_expires_at = now + timedelta(minutes=LEASE_MINUTES)

    result = db["level-2"].update_one(
        {"_id": job_id, "lease_owner": worker_id},
        {
            "$set": {
                "lease_expires_at": lease_expires_at,
                "lease_heartbeat_at": now,
            }
        },
    )
    renewed = result.matched_count > 0
    if not renewed:
        logger.warning(
            "Heartbeat failed for job %s: lease_owner mismatch or job not found. "
            "Another worker may have claimed it.",
            job_id,
        )
    else:
        _emit_legacy_lease_event(
            name="scout.preenrich.legacy_heartbeat",
            job_id=job_id,
            worker_id=worker_id,
            lifecycle_before="preenriching",
            lifecycle_after="preenriching",
        )
    return renewed


def release(
    db: Any,
    job_id: Any,
    worker_id: str,
    new_lifecycle: str,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Release a job lease and transition it to a new lifecycle state.

    Uses a compare-and-set on lease_owner so only the owning worker can
    release. If the lease was already taken by another worker (e.g. after
    expiry), this is a no-op.

    Args:
        db: Database handle
        job_id: MongoDB _id of the job document
        worker_id: This worker's identity string
        new_lifecycle: Target lifecycle value (e.g. "ready", "failed")
        extra_fields: Additional $set fields to apply together with lifecycle

    Returns:
        True if the release was applied, False if lease was already lost.
    """
    set_doc: Dict[str, Any] = {"lifecycle": new_lifecycle}
    if extra_fields:
        set_doc.update(extra_fields)

    result = db["level-2"].update_one(
        {"_id": job_id, "lease_owner": worker_id},
        {"$set": set_doc},
    )
    released = result.matched_count > 0
    if not released:
        logger.warning(
            "Release failed for job %s: lease_owner mismatch. "
            "Lease may have expired and been claimed by another worker.",
            job_id,
        )
    else:
        _emit_legacy_lease_event(
            name="scout.preenrich.legacy_release",
            job_id=job_id,
            worker_id=worker_id,
            lifecycle_before="preenriching",
            lifecycle_after=new_lifecycle,
        )
    return released
