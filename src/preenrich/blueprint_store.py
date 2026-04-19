"""Collection-backed artifact persistence helpers for iteration-4.1."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


BLUEPRINT_COLLECTIONS = (
    "jd_facts",
    "job_inference",
    "job_hypotheses",
    "research_enrichment",
    "cv_guidelines",
    "job_blueprint",
)


def upsert_artifact(
    db: Any,
    *,
    collection: str,
    unique_filter: dict[str, Any],
    document: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = now or utc_now()
    payload = dict(document)
    payload["updated_at"] = current_time
    db[collection].update_one(
        unique_filter,
        {
            "$set": payload,
            "$setOnInsert": {"created_at": current_time},
        },
        upsert=True,
    )
    stored = db[collection].find_one(unique_filter)
    if stored is None:
        raise RuntimeError(f"artifact upsert lost document in {collection}")
    return stored


def artifact_ref(stored: dict[str, Any], *, collection: str) -> dict[str, str]:
    identifier = stored.get("_id")
    if isinstance(identifier, ObjectId):
        identifier = str(identifier)
    return {"collection": collection, "id": str(identifier)}
