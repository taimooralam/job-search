"""Tests for the iteration-4 preenrich sweepers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import mongomock
import pytest
from bson import ObjectId

from src.pipeline.queue import WorkItemQueue
from src.preenrich.checksums import company_checksum, jd_checksum
from src.preenrich.root_enqueuer import build_stage_states
from src.preenrich.schema import idempotency_key, input_snapshot_id
from src.preenrich.sweepers import (
    drain_pending_next_stages,
    finalize_cv_ready,
    invalidate_snapshot_if_changed,
    release_expired_stage_leases,
)


@pytest.fixture
def mock_db():
    client = mongomock.MongoClient()
    db = client["jobs"]
    WorkItemQueue(db).ensure_indexes()
    return db


def _insert_job(db: Any) -> tuple[ObjectId, str]:
    job_id = ObjectId()
    description = "Build reliable AI systems"
    company = "Acme"
    snapshot_id = input_snapshot_id(
        jd_checksum(description),
        company_checksum(company, None),
        "iteration4.v1",
    )
    states = build_stage_states(snapshot_id)
    db["level-2"].insert_one(
        {
            "_id": job_id,
            "job_id": f"job-{job_id}",
            "company": company,
            "description": description,
            "lifecycle": "preenriching",
            "pre_enrichment": {
                "orchestration": "dag",
                "dag_version": "iteration4.v1",
                "input_snapshot_id": snapshot_id,
                "jd_checksum": jd_checksum(description),
                "company_checksum": company_checksum(company, None),
                "stage_states": states,
                "pending_next_stages": [],
            },
            "observability": {"langfuse_session_id": f"job:{job_id}"},
        }
    )
    return job_id, snapshot_id


def test_drain_pending_next_stages_enqueues_once(mock_db):
    job_id, snapshot_id = _insert_job(mock_db)
    mock_db["level-2"].update_one(
        {"_id": job_id},
        {
            "$set": {
                "pre_enrichment.pending_next_stages": [
                    {
                        "idempotency_key": idempotency_key("jd_extraction", str(job_id), snapshot_id),
                        "task_type": "preenrich.jd_extraction",
                        "priority": 100,
                        "max_attempts": 3,
                        "correlation_id": f"job:{job_id}",
                        "payload": {
                            "stage_name": "jd_extraction",
                            "input_snapshot_id": snapshot_id,
                            "jd_checksum": jd_checksum("Build reliable AI systems"),
                            "company_checksum": company_checksum("Acme", None),
                            "dag_version": "iteration4.v1",
                            "schema_version": 2,
                            "langfuse_session_id": f"job:{job_id}",
                        },
                        "enqueued_at": None,
                    }
                ]
            }
        },
    )

    first = drain_pending_next_stages(mock_db, level2_id=job_id)
    second = drain_pending_next_stages(mock_db, level2_id=job_id)

    assert first["entries"] == 1
    assert second["entries"] == 0
    assert mock_db["work_items"].count_documents({"task_type": "preenrich.jd_extraction"}) == 1


def test_finalize_cv_ready_is_cas_suppressed_after_first_success(mock_db):
    job_id, snapshot_id = _insert_job(mock_db)
    set_doc = {"lifecycle": "preenriching"}
    for stage_name in (
        "jd_structure",
        "jd_extraction",
        "ai_classification",
        "pain_points",
        "annotations",
        "persona",
        "company_research",
        "role_research",
    ):
        set_doc[f"pre_enrichment.stage_states.{stage_name}.status"] = "completed"
        set_doc[f"pre_enrichment.stage_states.{stage_name}.input_snapshot_id"] = snapshot_id
    mock_db["level-2"].update_one({"_id": job_id}, {"$set": set_doc})

    first = finalize_cv_ready(mock_db, level2_id=job_id)
    second = finalize_cv_ready(mock_db, level2_id=job_id)

    assert first is True
    assert second is False
    doc = mock_db["level-2"].find_one({"_id": job_id})
    assert doc["lifecycle"] == "cv_ready"
    assert doc["pre_enrichment"]["cv_ready_at"] is not None


def test_release_expired_stage_leases_requeues_work_and_clears_stage_lease(mock_db):
    job_id, snapshot_id = _insert_job(mock_db)
    work_item = WorkItemQueue(mock_db).enqueue(
        task_type="preenrich.jd_structure",
        lane="preenrich",
        consumer_mode="native_stage_dag",
        subject_type="job",
        subject_id=str(job_id),
        priority=100,
        available_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        max_attempts=3,
        idempotency_key=idempotency_key("jd_structure", str(job_id), snapshot_id),
        correlation_id=f"job:{job_id}",
        payload={
            "stage_name": "jd_structure",
            "input_snapshot_id": snapshot_id,
            "jd_checksum": jd_checksum("Build reliable AI systems"),
            "company_checksum": company_checksum("Acme", None),
            "dag_version": "iteration4.v1",
            "schema_version": 2,
            "langfuse_session_id": f"job:{job_id}",
        },
    ).document
    expired_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    mock_db["work_items"].update_one(
        {"_id": work_item["_id"]},
        {
            "$set": {
                "status": "leased",
                "lease_owner": "worker-a",
                "lease_expires_at": expired_at,
                "attempt_count": 1,
            }
        },
    )
    mock_db["level-2"].update_one(
        {"_id": job_id},
        {
            "$set": {
                "pre_enrichment.stage_states.jd_structure.status": "leased",
                "pre_enrichment.stage_states.jd_structure.lease_owner": "worker-a",
                "pre_enrichment.stage_states.jd_structure.lease_expires_at": expired_at,
                "pre_enrichment.stage_states.jd_structure.attempt_count": 1,
            }
        },
    )

    stats = release_expired_stage_leases(mock_db)

    assert stats["released"] == 1
    item = mock_db["work_items"].find_one({"_id": work_item["_id"]})
    assert item["status"] == "pending"
    assert item["lease_owner"] is None
    assert item["attempt_count"] == 2
    state = mock_db["level-2"].find_one({"_id": job_id})["pre_enrichment"]["stage_states"]["jd_structure"]
    assert state["status"] == "pending"
    assert state["lease_owner"] is None
    assert state["attempt_count"] == 2


def test_invalidate_snapshot_if_changed_cancels_old_work_and_reseeds_root(mock_db):
    job_id, snapshot_id = _insert_job(mock_db)
    stale_item = WorkItemQueue(mock_db).enqueue(
        task_type="preenrich.jd_extraction",
        lane="preenrich",
        consumer_mode="native_stage_dag",
        subject_type="job",
        subject_id=str(job_id),
        priority=100,
        available_at=datetime.now(timezone.utc),
        max_attempts=3,
        idempotency_key=idempotency_key("jd_extraction", str(job_id), snapshot_id),
        correlation_id=f"job:{job_id}",
        payload={
            "stage_name": "jd_extraction",
            "input_snapshot_id": snapshot_id,
            "jd_checksum": jd_checksum("Build reliable AI systems"),
            "company_checksum": company_checksum("Acme", None),
            "dag_version": "iteration4.v1",
            "schema_version": 2,
            "langfuse_session_id": f"job:{job_id}",
        },
    ).document
    mock_db["level-2"].update_one({"_id": job_id}, {"$set": {"description": "A materially changed job description"}})

    changed = invalidate_snapshot_if_changed(mock_db, level2_id=job_id)

    assert changed is True
    doc = mock_db["level-2"].find_one({"_id": job_id})
    assert doc["pre_enrichment"]["input_snapshot_id"] != snapshot_id
    cancelled = mock_db["work_items"].find_one({"_id": stale_item["_id"]})
    assert cancelled["status"] == "cancelled"
    assert mock_db["work_items"].count_documents({"task_type": "preenrich.jd_structure", "status": "pending"}) == 1
