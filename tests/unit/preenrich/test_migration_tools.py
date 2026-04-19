"""Tests for iteration-4 migration and rollback tooling."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import mongomock
from bson import ObjectId

from scripts.backfill_preenrich_states import run_backfill
from scripts.drain_preenrich_outbox import finalize_or_mark_stranded
from scripts.rollback_preenrich_dag import rollback_dag
from src.preenrich.root_enqueuer import build_stage_states
from src.preenrich.stage_registry import iter_stage_definitions


def _db():
    return mongomock.MongoClient()["jobs"]


def _completed_stage_states(snapshot_id: str = "sha256:snapshot") -> dict:
    states = build_stage_states(snapshot_id)
    completed_at = datetime(2026, 4, 19, 12, 0, tzinfo=timezone.utc)
    for index, stage in enumerate(iter_stage_definitions()):
        states[stage.name]["status"] = "completed"
        states[stage.name]["completed_at"] = completed_at + timedelta(minutes=index)
    return states


def test_backfill_is_idempotent_for_ready_to_cv_ready(tmp_path):
    db = _db()
    now = datetime(2026, 4, 19, 12, 30, tzinfo=timezone.utc)
    db["level-2"].insert_one(
        {
            "_id": ObjectId(),
            "lifecycle": "ready",
            "pre_enrichment": {
                "stage_states": _completed_stage_states(),
            },
        }
    )

    first = run_backfill(db, now=now, dry_run=False, report_path=tmp_path / "first.json")
    second = run_backfill(db, now=now, dry_run=False, report_path=tmp_path / "second.json")

    doc = db["level-2"].find_one({"lifecycle": "cv_ready"})
    assert doc is not None
    assert first["transition_counts"]["ready_to_cv_ready"] == 1
    assert second["changed_docs"] == []


def test_backfill_bootstraps_stage_states_and_remaps_failed_terminal(tmp_path):
    db = _db()
    now = datetime(2026, 4, 19, 12, 30, tzinfo=timezone.utc)
    db["level-2"].insert_one(
        {
            "_id": ObjectId(),
            "lifecycle": "preenriching",
            "pre_enrichment": {
                "stages": {
                    "jd_structure": {
                        "status": "completed",
                        "completed_at": now,
                    },
                    "jd_extraction": {
                        "status": "failed_terminal",
                        "failure_context": "schema violation",
                        "last_error_at": now,
                    },
                }
            },
        }
    )

    run_backfill(db, now=now, dry_run=False, report_path=tmp_path / "bootstrap.json")
    doc = db["level-2"].find_one()
    assert doc["pre_enrichment"]["orchestration"] == "legacy"
    assert doc["pre_enrichment"]["stage_states"]["jd_structure"]["status"] == "completed"
    assert doc["pre_enrichment"]["stage_states"]["jd_extraction"]["status"] == "deadletter"


def test_finalize_or_mark_stranded_updates_only_when_not_dry_run():
    db = _db()
    now = datetime(2026, 4, 19, 13, 0, tzinfo=timezone.utc)
    ready_id = ObjectId()
    running_id = ObjectId()
    db["level-2"].insert_many(
        [
            {
                "_id": ready_id,
                "lifecycle": "ready",
                "pre_enrichment": {"stage_states": _completed_stage_states()},
            },
            {
                "_id": running_id,
                "lifecycle": "running",
                "pre_enrichment": {"stage_states": build_stage_states("sha256:other")},
            },
        ]
    )

    dry_run = finalize_or_mark_stranded(db, now=now, dry_run=True)
    assert dry_run == {"cv_ready": 1, "stale": 1}
    assert db["level-2"].find_one({"_id": ready_id})["lifecycle"] == "ready"

    apply_run = finalize_or_mark_stranded(db, now=now, dry_run=False)
    assert apply_run == {"cv_ready": 1, "stale": 1}
    assert db["level-2"].find_one({"_id": ready_id})["lifecycle"] == "cv_ready"
    assert db["level-2"].find_one({"_id": running_id})["lifecycle"] == "stale"


def test_rollback_dag_only_reverts_docs_without_completed_stages():
    db = _db()
    now = datetime(2026, 4, 19, 13, 30, tzinfo=timezone.utc)
    rollback_id = ObjectId()
    preserved_id = ObjectId()
    rollback_states = build_stage_states("sha256:a")
    preserved_states = _completed_stage_states("sha256:b")
    db["level-2"].insert_many(
        [
            {
                "_id": rollback_id,
                "lifecycle": "preenriching",
                "pre_enrichment": {"orchestration": "dag", "stage_states": rollback_states},
            },
            {
                "_id": preserved_id,
                "lifecycle": "preenriching",
                "pre_enrichment": {"orchestration": "dag", "stage_states": preserved_states},
            },
        ]
    )
    db["work_items"].insert_one(
        {
            "_id": ObjectId(),
            "lane": "preenrich",
            "subject_id": str(rollback_id),
            "status": "pending",
        }
    )

    stats = rollback_dag(db, dry_run=False, now=now)
    assert stats["rolled_back_docs"] == 1
    assert stats["preserved_docs"] == 1
    assert db["level-2"].find_one({"_id": rollback_id})["pre_enrichment"]["orchestration"] == "legacy"
    assert db["level-2"].find_one({"_id": preserved_id})["pre_enrichment"]["orchestration"] == "dag"
    assert db["work_items"].find_one({"subject_id": str(rollback_id)})["status"] == "cancelled"
