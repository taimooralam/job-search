"""Tests for the iteration-4 preenrich root enqueuer."""

from __future__ import annotations

from datetime import datetime, timezone

import mongomock
import pytest
from bson import ObjectId

from src.preenrich.blueprint_config import current_input_snapshot_id
from src.preenrich.checksums import company_checksum, jd_checksum
from src.preenrich.root_enqueuer import (
    ROOT_STAGE,
    DAG_VERSION,
    RootEnqueuer,
    build_stage_states,
    canary_allows,
    parse_canary_allowlist,
)
from src.preenrich.schema import input_snapshot_id


@pytest.fixture
def mock_db():
    client = mongomock.MongoClient()
    return client["jobs"]


def _insert_selected_job(db, *, orchestration=None) -> ObjectId:
    oid = ObjectId()
    doc = {
        "_id": oid,
        "job_id": f"job-{oid}",
        "lifecycle": "selected",
        "selected_at": datetime(2026, 4, 19, 12, 0, tzinfo=timezone.utc),
        "description": "Build and run AI platforms at scale",
        "company": "Acme AI",
    }
    if orchestration is not None:
        doc["pre_enrichment"] = {"orchestration": orchestration}
    db["level-2"].insert_one(doc)
    return oid


def test_root_enqueuer_is_idempotent_for_same_job(monkeypatch, mock_db):
    monkeypatch.setenv("PREENRICH_STAGE_DAG_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_DAG_CANARY_PCT", "100")

    job_id = _insert_selected_job(mock_db)
    enqueuer = RootEnqueuer(mock_db)
    now = datetime(2026, 4, 19, 12, 5, tzinfo=timezone.utc)

    first = enqueuer.enqueue_one(job_id, now=now)
    second = enqueuer.enqueue_one(job_id, now=now)

    assert first is True
    assert second is False
    assert mock_db["work_items"].count_documents({"lane": "preenrich"}) == 1

    level2_doc = mock_db["level-2"].find_one({"_id": job_id})
    assert level2_doc["lifecycle"] == "preenriching"
    assert level2_doc["pre_enrichment"]["orchestration"] == "dag"
    assert level2_doc["pre_enrichment"]["stage_states"][ROOT_STAGE]["status"] == "pending"


def test_root_enqueuer_reclaims_legacy_selected_jobs_per_plan(monkeypatch, mock_db):
    monkeypatch.setenv("PREENRICH_STAGE_DAG_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_DAG_CANARY_PCT", "100")

    job_id = _insert_selected_job(mock_db, orchestration="legacy")
    enqueuer = RootEnqueuer(mock_db)

    assert enqueuer.enqueue_one(job_id) is True

    level2_doc = mock_db["level-2"].find_one({"_id": job_id})
    assert level2_doc["pre_enrichment"]["orchestration"] == "dag"
    assert mock_db["work_items"].count_documents({"lane": "preenrich"}) == 1


def test_root_enqueuer_honors_canary_allowlist(monkeypatch, mock_db):
    monkeypatch.setenv("PREENRICH_STAGE_DAG_ENABLED", "true")
    allowed = _insert_selected_job(mock_db)
    skipped = _insert_selected_job(mock_db)
    monkeypatch.setenv("PREENRICH_DAG_CANARY_ALLOWLIST", str(allowed))
    monkeypatch.setenv("PREENRICH_DAG_CANARY_PCT", "0")

    enqueuer = RootEnqueuer(mock_db)
    stats = enqueuer.enqueue_ready_roots(limit=10)

    assert stats == {"claimed": 1, "enqueued": 1, "skipped": 1}
    assert mock_db["work_items"].count_documents({"lane": "preenrich", "subject_id": str(allowed)}) == 1
    assert mock_db["work_items"].count_documents({"lane": "preenrich", "subject_id": str(skipped)}) == 0


def test_root_enqueuer_honors_canary_percentage(monkeypatch, mock_db):
    monkeypatch.setenv("PREENRICH_STAGE_DAG_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_DAG_CANARY_ALLOWLIST", "")
    monkeypatch.setenv("PREENRICH_DAG_CANARY_PCT", "0")
    _insert_selected_job(mock_db)

    enqueuer = RootEnqueuer(mock_db)
    stats = enqueuer.enqueue_ready_roots(limit=10)

    assert stats == {"claimed": 0, "enqueued": 0, "skipped": 1}
    assert mock_db["work_items"].count_documents({"lane": "preenrich"}) == 0


def test_root_enqueuer_initializes_stage_state_snapshot(monkeypatch, mock_db):
    monkeypatch.setenv("PREENRICH_STAGE_DAG_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_DAG_CANARY_PCT", "100")

    job_id = _insert_selected_job(mock_db)
    enqueuer = RootEnqueuer(mock_db)
    enqueuer.enqueue_one(job_id)

    doc = mock_db["level-2"].find_one({"_id": job_id})
    snapshot_id = input_snapshot_id(
        doc["pre_enrichment"]["jd_checksum"],
        doc["pre_enrichment"]["company_checksum"],
        DAG_VERSION,
    )
    assert doc["pre_enrichment"]["input_snapshot_id"] == snapshot_id
    expected = build_stage_states(snapshot_id)
    expected[ROOT_STAGE]["work_item_id"] = doc["pre_enrichment"]["stage_states"][ROOT_STAGE]["work_item_id"]
    assert doc["pre_enrichment"]["stage_states"] == expected


def test_root_enqueuer_uses_shared_checksums_for_blueprint_snapshot(monkeypatch, mock_db):
    monkeypatch.setenv("PREENRICH_STAGE_DAG_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_DAG_CANARY_PCT", "100")
    monkeypatch.setenv("PREENRICH_BLUEPRINT_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_BLUEPRINT_SNAPSHOT_WRITE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_BLUEPRINT_UI_READ_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_BLUEPRINT_COMPAT_PROJECTIONS_ENABLED", "true")

    job_id = _insert_selected_job(mock_db)
    mock_db["level-2"].update_one(
        {"_id": job_id},
        {
            "$set": {
                "description": "  Build and RUN AI   Platforms\n\nAt Scale  ",
                "company": "  Acme AI  ",
                "company_domain": "ACME.example.com ",
            }
        },
    )

    enqueuer = RootEnqueuer(mock_db)
    assert enqueuer.enqueue_one(job_id) is True

    doc = mock_db["level-2"].find_one({"_id": job_id})
    expected_jd_checksum = jd_checksum("  Build and RUN AI   Platforms\n\nAt Scale  ")
    expected_company_checksum = company_checksum("  Acme AI  ", "ACME.example.com ")
    expected_snapshot = current_input_snapshot_id(
        expected_jd_checksum,
        expected_company_checksum,
        dag_version="iteration4.1.v1",
    )

    assert doc["pre_enrichment"]["jd_checksum"] == expected_jd_checksum
    assert doc["pre_enrichment"]["company_checksum"] == expected_company_checksum
    assert doc["pre_enrichment"]["input_snapshot_id"] == expected_snapshot
    assert doc["pre_enrichment"]["stage_states"][ROOT_STAGE]["input_snapshot_id"] == expected_snapshot

    work_item = mock_db["work_items"].find_one({"subject_id": str(job_id)})
    assert work_item["payload"]["input_snapshot_id"] == expected_snapshot
    assert work_item["payload"]["jd_checksum"] == expected_jd_checksum
    assert work_item["payload"]["company_checksum"] == expected_company_checksum


def test_root_enqueuer_revives_terminal_root_work_item_for_same_snapshot(monkeypatch, mock_db):
    monkeypatch.setenv("PREENRICH_STAGE_DAG_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_DAG_CANARY_PCT", "100")
    monkeypatch.setenv("PREENRICH_BLUEPRINT_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_BLUEPRINT_SNAPSHOT_WRITE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_BLUEPRINT_UI_READ_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_BLUEPRINT_COMPAT_PROJECTIONS_ENABLED", "true")

    job_id = _insert_selected_job(mock_db)
    enqueuer = RootEnqueuer(mock_db)
    now = datetime(2026, 4, 19, 12, 5, tzinfo=timezone.utc)
    assert enqueuer.enqueue_one(job_id, now=now) is True

    work_item = mock_db["work_items"].find_one({"subject_id": str(job_id)})
    mock_db["work_items"].update_one(
        {"_id": work_item["_id"]},
        {
            "$set": {
                "status": "deadletter",
                "attempt_count": 2,
                "last_error": {"message": "boom", "type": "deadletter"},
            }
        },
    )
    mock_db["level-2"].update_one(
        {"_id": job_id},
        {
            "$set": {
                "lifecycle": "selected",
                "pre_enrichment.orchestration": "legacy",
            }
        },
    )

    assert enqueuer.enqueue_one(job_id, now=now) is True

    revived = mock_db["work_items"].find_one({"_id": work_item["_id"]})
    assert revived["status"] == "pending"
    assert revived["attempt_count"] == 0
    assert revived["last_error"] is None
    assert mock_db["work_items"].count_documents({"subject_id": str(job_id)}) == 1


def test_parse_canary_allowlist_ignores_empty_entries():
    assert parse_canary_allowlist("a,, b, ,c") == {"a", "b", "c"}


def test_canary_allowlist_takes_precedence_over_pct():
    assert canary_allows("a", allowlist={"a"}, pct=0) is True
    assert canary_allows("b", allowlist={"a"}, pct=100) is False
