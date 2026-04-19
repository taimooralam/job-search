"""Tests for the iteration-4 shared preenrich stage worker."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import mongomock
import pytest
from bson import ObjectId

from src.pipeline.queue import WorkItemQueue
from src.preenrich.checksums import company_checksum, jd_checksum
from src.preenrich.root_enqueuer import build_stage_states
from src.preenrich.schema import idempotency_key, input_snapshot_id
from src.preenrich.stage_worker import StageWorker
from src.preenrich.sweepers import drain_pending_next_stages
from src.preenrich.types import StageResult


@pytest.fixture
def mock_db():
    client = mongomock.MongoClient()
    db = client["jobs"]
    WorkItemQueue(db).ensure_indexes()
    return db


def _insert_job(db: Any, *, description: str = "Build reliable AI systems", company: str = "Acme") -> ObjectId:
    job_id = ObjectId()
    jd_cs = jd_checksum(description)
    company_cs = company_checksum(company, None)
    snapshot_id = input_snapshot_id(
        jd_cs,
        company_cs,
        "iteration4.v1",
    )
    db["level-2"].insert_one(
        {
            "_id": job_id,
            "job_id": f"job-{job_id}",
            "title": "AI Platform Engineer",
            "company": company,
            "description": description,
            "lifecycle": "preenriching",
            "pre_enrichment": {
                "orchestration": "dag",
                "dag_version": "iteration4.v1",
                "input_snapshot_id": snapshot_id,
                "jd_checksum": jd_cs,
                "company_checksum": company_cs,
                "stage_states": build_stage_states(snapshot_id),
                "pending_next_stages": [],
            },
            "observability": {"langfuse_session_id": f"job:{job_id}"},
            "selected_at": datetime.now(timezone.utc),
        }
    )
    return job_id


def _enqueue_stage(db: Any, *, job_id: ObjectId, stage_name: str, snapshot_id: str, work_item_idempotency: str | None = None):
    queue = WorkItemQueue(db)
    return queue.enqueue(
        task_type=f"preenrich.{stage_name}",
        lane="preenrich",
        consumer_mode="native_stage_dag",
        subject_type="job",
        subject_id=str(job_id),
        priority=100,
        available_at=datetime.now(timezone.utc),
        max_attempts=3,
        idempotency_key=work_item_idempotency or idempotency_key(stage_name, str(job_id), snapshot_id),
        correlation_id=f"job:{job_id}",
        payload={
            "stage_name": stage_name,
            "input_snapshot_id": snapshot_id,
            "jd_checksum": "unused-for-test",
            "company_checksum": "unused-for-test",
            "dag_version": "iteration4.v1",
            "schema_version": 2,
            "langfuse_session_id": f"job:{job_id}",
        },
    ).document


class _HappyStage:
    name = "jd_structure"

    def run(self, ctx):
        return StageResult(
            output={"processed_jd_sections": [{"section_type": "summary", "content": "ok"}]},
            provider_used="codex",
            model_used="gpt-5.4",
            prompt_version="v1",
            duration_ms=5,
        )


class _ExplodingStage:
    name = "jd_structure"

    def run(self, ctx):
        raise RuntimeError("provider timeout")


def test_claim_race_exactly_one_worker_wins(mock_db):
    job_id = _insert_job(mock_db)
    snapshot_id = mock_db["level-2"].find_one({"_id": job_id})["pre_enrichment"]["input_snapshot_id"]
    _enqueue_stage(mock_db, job_id=job_id, stage_name="jd_structure", snapshot_id=snapshot_id)

    factories = {"jd_structure": _HappyStage}
    worker_a = StageWorker(mock_db, stage_name="jd_structure", worker_id="worker-a", stage_factories=factories)
    worker_b = StageWorker(mock_db, stage_name="jd_structure", worker_id="worker-b", stage_factories=factories)

    first = worker_a.claim_next_work_item()
    second = worker_b.claim_next_work_item()

    assert first is not None
    assert second is None
    doc = mock_db["work_items"].find_one({"_id": first["_id"]})
    assert doc["status"] == "leased"
    assert doc["lease_owner"] == "worker-a"


def test_prerequisite_guard_requeues_without_running_stage(mock_db):
    job_id = _insert_job(mock_db)
    snapshot_id = mock_db["level-2"].find_one({"_id": job_id})["pre_enrichment"]["input_snapshot_id"]
    work_item = _enqueue_stage(mock_db, job_id=job_id, stage_name="jd_extraction", snapshot_id=snapshot_id)

    called = {"count": 0}

    class _ShouldNotRun:
        name = "jd_extraction"

        def run(self, ctx):
            called["count"] += 1
            return StageResult(output={"extracted_jd": {}}, provider_used="codex", model_used="gpt-5.4")

    worker = StageWorker(
        mock_db,
        stage_name="jd_extraction",
        worker_id="worker-a",
        stage_factories={"jd_extraction": _ShouldNotRun},
    )

    result = worker.process_one()

    assert result["status"] == "retry_pending"
    assert called["count"] == 0
    reloaded = mock_db["work_items"].find_one({"_id": work_item["_id"]})
    assert reloaded["status"] == "pending"
    stage_state = mock_db["level-2"].find_one({"_id": job_id})["pre_enrichment"]["stage_states"]["jd_extraction"]
    assert stage_state["status"] == "retry_pending"


def test_snapshot_mismatch_cancels_work_item(mock_db):
    job_id = _insert_job(mock_db)
    doc = mock_db["level-2"].find_one({"_id": job_id})
    current_snapshot = doc["pre_enrichment"]["input_snapshot_id"]
    stale_snapshot = "sha256:stale-snapshot"
    work_item = _enqueue_stage(
        mock_db,
        job_id=job_id,
        stage_name="jd_structure",
        snapshot_id=stale_snapshot,
        work_item_idempotency=f"preenrich.jd_structure:{job_id}:{stale_snapshot}",
    )

    worker = StageWorker(
        mock_db,
        stage_name="jd_structure",
        worker_id="worker-a",
        stage_factories={"jd_structure": _HappyStage},
    )
    result = worker.process_one()

    assert result["status"] == "cancelled"
    cancelled = mock_db["work_items"].find_one({"_id": work_item["_id"]})
    assert cancelled["status"] == "cancelled"
    stage_state = mock_db["level-2"].find_one({"_id": job_id})["pre_enrichment"]["stage_states"]["jd_structure"]
    assert stage_state["status"] == "cancelled"
    assert stage_state["input_snapshot_id"] != stale_snapshot
    assert current_snapshot == mock_db["level-2"].find_one({"_id": job_id})["pre_enrichment"]["input_snapshot_id"]


def test_phase_a_success_can_be_drained_by_sweeper_when_inline_enqueue_is_skipped(mock_db):
    job_id = _insert_job(mock_db)
    snapshot_id = mock_db["level-2"].find_one({"_id": job_id})["pre_enrichment"]["input_snapshot_id"]
    _enqueue_stage(mock_db, job_id=job_id, stage_name="jd_structure", snapshot_id=snapshot_id)

    class _StageWorkerNoInline(StageWorker):
        def _inline_phase_b_enqueue(self, *, level2_id, now=None):
            return {"jobs": 0, "entries": 0}

    worker = _StageWorkerNoInline(
        mock_db,
        stage_name="jd_structure",
        worker_id="worker-a",
        stage_factories={"jd_structure": _HappyStage},
    )

    result = worker.process_one()
    assert result["status"] == "completed"

    doc = mock_db["level-2"].find_one({"_id": job_id})
    pending = doc["pre_enrichment"]["pending_next_stages"]
    assert pending
    assert pending[0]["enqueued_at"] is None
    assert mock_db["work_items"].count_documents({"task_type": "preenrich.jd_extraction"}) == 0

    sweep_stats = drain_pending_next_stages(mock_db, level2_id=job_id)
    assert sweep_stats["entries"] == 1
    drained = mock_db["level-2"].find_one({"_id": job_id})["pre_enrichment"]["pending_next_stages"]
    assert drained[0]["enqueued_at"] is not None
    assert mock_db["work_items"].count_documents({"task_type": "preenrich.jd_extraction"}) == 1


def test_retryable_stage_failure_sets_retry_pending(mock_db):
    job_id = _insert_job(mock_db)
    snapshot_id = mock_db["level-2"].find_one({"_id": job_id})["pre_enrichment"]["input_snapshot_id"]
    work_item = _enqueue_stage(mock_db, job_id=job_id, stage_name="jd_structure", snapshot_id=snapshot_id)

    worker = StageWorker(
        mock_db,
        stage_name="jd_structure",
        worker_id="worker-a",
        stage_factories={"jd_structure": _ExplodingStage},
    )
    result = worker.process_one()

    assert result["status"] == "retry_pending"
    doc = mock_db["work_items"].find_one({"_id": work_item["_id"]})
    assert doc["status"] == "pending"
    stage_state = mock_db["level-2"].find_one({"_id": job_id})["pre_enrichment"]["stage_states"]["jd_structure"]
    assert stage_state["status"] == "retry_pending"
