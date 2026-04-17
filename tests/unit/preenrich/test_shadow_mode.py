"""
Shadow mode tests (§9 Phase 3).

Validates:
- shadow_mode=True writes ONLY to pre_enrichment.stages.<stage>.shadow_output
  and pre_enrichment.shadow_legacy_fields.*
- shadow_mode=True NEVER writes to live top-level legacy fields
- shadow_mode=False (default) writes to live fields and NOT shadow namespace
- run_sequence respects shadow_mode from ctx across all stages
- Multiple stages each get their own shadow_output entry
"""

import pytest
from datetime import datetime, timezone
from bson import ObjectId
from unittest.mock import MagicMock, patch

import mongomock

from src.preenrich.types import (
    StageContext,
    StageResult,
    StageStatus,
    StepConfig,
)
from src.preenrich.dispatcher import single_stage, run_sequence


WORKER_ID = "shadow-test-worker"


@pytest.fixture
def mock_db():
    client = mongomock.MongoClient()
    return client["jobs"]


def _make_ctx(job_doc: dict, *, shadow_mode: bool = False) -> StageContext:
    return StageContext(
        job_doc=job_doc,
        jd_checksum="sha256:abc",
        company_checksum="sha256:co",
        input_snapshot_id="sha256:snap",
        attempt_number=1,
        config=StepConfig(provider="claude", prompt_version="v1"),
        shadow_mode=shadow_mode,
    )


def _make_stage(name: str, output: dict = None):
    stage = MagicMock()
    stage.name = name
    stage.dependencies = []
    stage.run.return_value = StageResult(
        output=output or {f"{name}_result": "value"},
        provider_used="claude",
        model_used="claude-haiku-4-5",
        prompt_version="v1",
        duration_ms=10,
    )
    return stage


def _insert_job(db) -> dict:
    doc = {
        "_id": ObjectId(),
        "lifecycle": "preenriching",
        "lease_owner": WORKER_ID,
        "description": "ML engineer role",
        "selected_at": datetime.now(timezone.utc),
    }
    db["level-2"].insert_one(doc)
    return doc


# ---------------------------------------------------------------------------
# Shadow mode: writes to shadow namespace, NOT live fields
# ---------------------------------------------------------------------------


def test_shadow_mode_does_not_write_live_fields(mock_db):
    """
    §9 Phase 3: shadow_mode=True must NOT write live top-level legacy fields.
    """
    job = _insert_job(mock_db)
    ctx = _make_ctx(job, shadow_mode=True)
    stage = _make_stage("jd_structure", output={"processed_jd_sections": ["sec1"]})

    single_stage(mock_db, ctx, stage, WORKER_ID)

    doc = mock_db["level-2"].find_one({"_id": job["_id"]})
    # Live field must NOT be written
    assert "processed_jd_sections" not in doc, (
        "shadow_mode=True must not write 'processed_jd_sections' to the top-level doc"
    )


def test_shadow_mode_writes_shadow_output_in_stage(mock_db):
    """
    §9 Phase 3: shadow_mode=True writes shadow_output inside the stage doc.
    """
    job = _insert_job(mock_db)
    ctx = _make_ctx(job, shadow_mode=True)
    stage = _make_stage("jd_structure", output={"processed_jd_sections": ["sec1"]})

    single_stage(mock_db, ctx, stage, WORKER_ID)

    doc = mock_db["level-2"].find_one({"_id": job["_id"]})
    stage_meta = doc["pre_enrichment"]["stages"]["jd_structure"]
    assert "shadow_output" in stage_meta
    assert stage_meta["shadow_output"] == {"processed_jd_sections": ["sec1"]}


def test_shadow_mode_writes_shadow_legacy_fields(mock_db):
    """
    §9 Phase 3: shadow_mode=True mirrors output into pre_enrichment.shadow_legacy_fields.
    """
    job = _insert_job(mock_db)
    ctx = _make_ctx(job, shadow_mode=True)
    stage = _make_stage("jd_structure", output={"processed_jd_sections": ["sec1"]})

    single_stage(mock_db, ctx, stage, WORKER_ID)

    doc = mock_db["level-2"].find_one({"_id": job["_id"]})
    shadow_fields = doc["pre_enrichment"].get("shadow_legacy_fields", {})
    assert shadow_fields.get("processed_jd_sections") == ["sec1"]


def test_shadow_mode_stage_status_still_completed(mock_db):
    """
    shadow_mode=True still marks stage as COMPLETED (so dispatcher knows it ran).
    """
    job = _insert_job(mock_db)
    ctx = _make_ctx(job, shadow_mode=True)
    stage = _make_stage("jd_structure", output={"processed_jd_sections": []})

    single_stage(mock_db, ctx, stage, WORKER_ID)

    doc = mock_db["level-2"].find_one({"_id": job["_id"]})
    stage_meta = doc["pre_enrichment"]["stages"]["jd_structure"]
    assert stage_meta["status"] == StageStatus.COMPLETED


# ---------------------------------------------------------------------------
# Live mode: writes live fields, not shadow namespace
# ---------------------------------------------------------------------------


def test_live_mode_writes_live_fields(mock_db):
    """shadow_mode=False writes output to live top-level fields."""
    job = _insert_job(mock_db)
    ctx = _make_ctx(job, shadow_mode=False)
    stage = _make_stage("jd_structure", output={"processed_jd_sections": ["s1"]})

    single_stage(mock_db, ctx, stage, WORKER_ID)

    doc = mock_db["level-2"].find_one({"_id": job["_id"]})
    assert doc["processed_jd_sections"] == ["s1"]


def test_live_mode_does_not_write_shadow_fields(mock_db):
    """shadow_mode=False must NOT write shadow_legacy_fields."""
    job = _insert_job(mock_db)
    ctx = _make_ctx(job, shadow_mode=False)
    stage = _make_stage("jd_structure", output={"processed_jd_sections": ["s1"]})

    single_stage(mock_db, ctx, stage, WORKER_ID)

    doc = mock_db["level-2"].find_one({"_id": job["_id"]})
    assert "shadow_legacy_fields" not in doc.get("pre_enrichment", {})


def test_live_mode_does_not_write_shadow_output_in_stage(mock_db):
    """shadow_mode=False must NOT write shadow_output inside stage doc."""
    job = _insert_job(mock_db)
    ctx = _make_ctx(job, shadow_mode=False)
    stage = _make_stage("jd_structure", output={"processed_jd_sections": ["s1"]})

    single_stage(mock_db, ctx, stage, WORKER_ID)

    doc = mock_db["level-2"].find_one({"_id": job["_id"]})
    stage_meta = doc["pre_enrichment"]["stages"]["jd_structure"]
    assert "shadow_output" not in stage_meta


# ---------------------------------------------------------------------------
# run_sequence respects shadow_mode across all stages
# ---------------------------------------------------------------------------


def test_run_sequence_shadow_mode_all_stages_shadow_only(mock_db):
    """
    run_sequence with shadow_mode=True: no live fields written across all stages.
    Patches _DEPENDENCIES so stage2 has no prereqs (isolated test).
    """
    job = _insert_job(mock_db)
    ctx = _make_ctx(job, shadow_mode=True)

    stage1 = _make_stage("jd_structure", output={"processed_jd_sections": ["s1"]})
    stage2 = _make_stage("jd_extraction", output={"extracted_jd": {"title": "ML"}})

    with patch("src.preenrich.dispatcher._DEPENDENCIES", {"jd_structure": [], "jd_extraction": []}):
        run_sequence(mock_db, ctx, [stage1, stage2], WORKER_ID)

    doc = mock_db["level-2"].find_one({"_id": job["_id"]})

    # No live legacy fields
    assert "processed_jd_sections" not in doc
    assert "extracted_jd" not in doc

    # Both stages have shadow_output
    stages = doc["pre_enrichment"]["stages"]
    assert "shadow_output" in stages["jd_structure"]
    assert "shadow_output" in stages["jd_extraction"]

    # shadow_legacy_fields contains both outputs
    shadow_fields = doc["pre_enrichment"]["shadow_legacy_fields"]
    assert "processed_jd_sections" in shadow_fields
    assert "extracted_jd" in shadow_fields


def test_run_sequence_multiple_shadow_outputs_accumulate(mock_db):
    """
    Each stage contributes its own keys to shadow_legacy_fields without
    overwriting other stages' keys.
    """
    job = _insert_job(mock_db)
    ctx = _make_ctx(job, shadow_mode=True)

    stage1 = _make_stage("jd_structure", output={"field_a": "value_a"})
    stage2 = _make_stage("jd_extraction", output={"field_b": "value_b"})

    with patch("src.preenrich.dispatcher._DEPENDENCIES", {"jd_structure": [], "jd_extraction": []}):
        run_sequence(mock_db, ctx, [stage1, stage2], WORKER_ID)

    doc = mock_db["level-2"].find_one({"_id": job["_id"]})
    shadow_fields = doc["pre_enrichment"]["shadow_legacy_fields"]
    assert shadow_fields["field_a"] == "value_a"
    assert shadow_fields["field_b"] == "value_b"
