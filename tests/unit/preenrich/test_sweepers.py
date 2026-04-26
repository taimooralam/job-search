"""Tests for the iteration-4 preenrich sweepers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import mongomock
import pytest
from bson import ObjectId

from src.pipeline.queue import WorkItemQueue
from src.preenrich import sweepers as sweepers_module
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
def capture_sweeper_events(monkeypatch):
    captured: list[dict] = []

    def _fake(**kwargs):
        captured.append(kwargs)
        return {"trace_id": None, "trace_url": None}

    monkeypatch.setattr(sweepers_module, "emit_preenrich_sweeper_event", _fake)
    return captured


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


def _assert_correlation_fields(event: dict[str, Any], *, job_id: ObjectId, task_type: str, stage_name: str) -> None:
    metadata = event["metadata"]
    assert event["level2_job_id"] == str(job_id)
    assert event["run_id"] == metadata["run_id"]
    assert metadata["job_id"] == f"job-{job_id}"
    assert metadata["level2_job_id"] == str(job_id)
    assert metadata["correlation_id"] == f"job:{job_id}"
    assert metadata["langfuse_session_id"] == f"job:{job_id}"
    assert metadata["run_id"].startswith("preenrich:sweeper:")
    assert metadata["worker_id"].endswith("-sweeper")
    assert metadata["task_type"] == task_type
    assert metadata["stage_name"] == stage_name
    assert "attempt_count" in metadata
    assert "attempt_token" in metadata
    assert "input_snapshot_id" in metadata
    assert "jd_checksum" in metadata
    assert "lifecycle_before" in metadata
    assert "lifecycle_after" in metadata
    assert "work_item_id" in metadata


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


def test_drain_pending_next_stages_emits_sweeper_event(mock_db, capture_sweeper_events):
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

    drain_pending_next_stages(mock_db, level2_id=job_id)

    names = [event["name"] for event in capture_sweeper_events]
    assert "scout.preenrich.enqueue_next" in names
    event = next(e for e in capture_sweeper_events if e["name"] == "scout.preenrich.enqueue_next")
    _assert_correlation_fields(
        event,
        job_id=job_id,
        task_type="preenrich.sweeper.enqueue_next",
        stage_name="sweeper",
    )
    assert event["metadata"]["source"] == "sweeper"
    assert event["metadata"]["entries_enqueued"] == 1
    assert event["metadata"]["stage_names"] == ["jd_extraction"]


def test_finalize_cv_ready_emits_sweeper_event(mock_db, capture_sweeper_events):
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

    assert finalize_cv_ready(mock_db, level2_id=job_id) is True

    names = [event["name"] for event in capture_sweeper_events]
    assert names == ["scout.preenrich.finalize_cv_ready"]
    event = capture_sweeper_events[0]
    _assert_correlation_fields(
        event,
        job_id=job_id,
        task_type="preenrich.sweeper.finalize_cv_ready",
        stage_name="sweeper",
    )
    assert event["metadata"]["lifecycle_after"] == "cv_ready"
    assert event["metadata"]["finalized"] is True


def test_release_expired_stage_leases_emits_sweeper_event(mock_db, capture_sweeper_events):
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
        {"$set": {"status": "leased", "lease_owner": "worker-a", "lease_expires_at": expired_at, "attempt_count": 1}},
    )

    release_expired_stage_leases(mock_db)

    names = [event["name"] for event in capture_sweeper_events]
    assert "scout.preenrich.release_lease" in names
    event = next(e for e in capture_sweeper_events if e["name"] == "scout.preenrich.release_lease")
    _assert_correlation_fields(
        event,
        job_id=job_id,
        task_type="preenrich.sweeper.release_lease",
        stage_name="jd_structure",
    )
    assert event["metadata"]["reason"] == "lease_expired"
    assert event["metadata"]["work_item_id"] == str(work_item["_id"])


def test_invalidate_snapshot_emits_sweeper_event(mock_db, capture_sweeper_events):
    job_id, _snapshot_id = _insert_job(mock_db)
    mock_db["level-2"].update_one({"_id": job_id}, {"$set": {"description": "A materially different description"}})

    assert invalidate_snapshot_if_changed(mock_db, level2_id=job_id) is True

    names = [event["name"] for event in capture_sweeper_events]
    assert "scout.preenrich.snapshot_invalidation" in names
    event = next(e for e in capture_sweeper_events if e["name"] == "scout.preenrich.snapshot_invalidation")
    _assert_correlation_fields(
        event,
        job_id=job_id,
        task_type="preenrich.sweeper.snapshot_invalidation",
        stage_name="sweeper",
    )
    assert event["metadata"]["rerooted"] is True
    assert event["metadata"]["old_input_snapshot_id"] != event["metadata"]["new_input_snapshot_id"]
