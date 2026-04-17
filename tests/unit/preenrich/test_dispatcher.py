"""
T5 — Dispatcher: state transitions, atomic write, retry counting, idempotency.

Covers BDD scenarios:
- S1: Selected job enters pre-enrichment → stages run, lifecycle → ready
- S2: Mid-sequence failure is resumable (retry_count increments)
- S6: Mongo write crash → re-run produces same attempt_token (idempotent)
- Prerequisites enforcement and force-bypass
- shadow_mode writes to shadow namespace only

Uses mongomock for Mongo isolation.
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
from src.preenrich.dispatcher import (
    single_stage,
    run_sequence,
    PrerequisiteNotMet,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


WORKER_ID = "test-worker-abc"


@pytest.fixture
def mock_db():
    client = mongomock.MongoClient()
    return client["jobs"]


def _make_job(db, *, lifecycle="preenriching", pre_enrichment=None) -> dict:
    """Insert a job into the mock DB and return the full document."""
    doc = {
        "_id": ObjectId(),
        "description": "We are hiring ML engineers.",
        "title": "ML Engineer",
        "company": "TestCo",
        "lifecycle": lifecycle,
        "lease_owner": WORKER_ID,
        "selected_at": datetime.now(timezone.utc),
    }
    if pre_enrichment is not None:
        doc["pre_enrichment"] = pre_enrichment
    db["level-2"].insert_one(doc)
    return doc


def _make_ctx(job_doc, *, shadow_mode=False) -> StageContext:
    return StageContext(
        job_doc=job_doc,
        jd_checksum="sha256:abc123",
        company_checksum="sha256:co",
        input_snapshot_id="sha256:snap",
        attempt_number=1,
        config=StepConfig(provider="claude", prompt_version="v1"),
        shadow_mode=shadow_mode,
    )


def _make_stage(name: str, output: dict = None, fail: bool = False, deps=None):
    """Create a minimal mock stage.

    Note: deps here is for the stage object's .dependencies attribute.
    Prerequisite checks in single_stage use _DEPENDENCIES from dag.py,
    so tests use stage names with no entries in _DEPENDENCIES (e.g. "jd_structure")
    or patch _DEPENDENCIES to be empty.
    """
    stage = MagicMock()
    stage.name = name
    stage.dependencies = deps or []
    if fail:
        stage.run.side_effect = RuntimeError(f"Simulated failure in {name}")
    else:
        stage.run.return_value = StageResult(
            output=output or {f"{name}_result": "ok"},
            provider_used="claude",
            model_used="claude-haiku-4-5",
            prompt_version="v1",
            duration_ms=100,
        )
    return stage


# ---------------------------------------------------------------------------
# single_stage — basic success
# ---------------------------------------------------------------------------


def test_single_stage_success(mock_db):
    """single_stage runs the stage and writes completion to Mongo."""
    job = _make_job(mock_db)
    ctx = _make_ctx(job)
    stage = _make_stage("jd_structure", output={"processed_jd_sections": []})

    result = single_stage(mock_db, ctx, stage, WORKER_ID)

    assert result is not None
    assert result.output == {"processed_jd_sections": []}

    # Mongo should reflect completion
    doc = mock_db["level-2"].find_one({"_id": job["_id"]})
    stage_meta = doc["pre_enrichment"]["stages"]["jd_structure"]
    assert stage_meta["status"] == StageStatus.COMPLETED
    assert stage_meta["jd_checksum_at_completion"] == "sha256:abc123"
    assert "attempt_token" in stage_meta


def test_single_stage_writes_legacy_output(mock_db):
    """single_stage writes stage output to top-level legacy fields."""
    job = _make_job(mock_db)
    ctx = _make_ctx(job)
    stage = _make_stage("jd_structure", output={"processed_jd_sections": ["sec1"]})

    single_stage(mock_db, ctx, stage, WORKER_ID)

    doc = mock_db["level-2"].find_one({"_id": job["_id"]})
    assert doc["processed_jd_sections"] == ["sec1"]


def test_single_stage_skips_completed_at_current_checksum(mock_db):
    """Already-completed stage at current checksum is skipped."""
    pre = {
        "stages": {
            "jd_structure": {
                "status": StageStatus.COMPLETED,
                "jd_checksum_at_completion": "sha256:abc123",
                "attempt_token": "tok123",
            }
        }
    }
    job = _make_job(mock_db, pre_enrichment=pre)
    ctx = _make_ctx(job)
    stage = _make_stage("jd_structure")

    result = single_stage(mock_db, ctx, stage, WORKER_ID)

    # Stage.run should NOT have been called
    stage.run.assert_not_called()
    assert result.skip_reason == "already_completed_at_current_checksum"


# ---------------------------------------------------------------------------
# Prerequisites enforcement
# ---------------------------------------------------------------------------


def test_single_stage_blocks_on_unmet_prerequisites(mock_db):
    """single_stage raises PrerequisiteNotMet when deps not completed."""
    job = _make_job(mock_db)
    ctx = _make_ctx(job)

    # jd_extraction depends on jd_structure — jd_structure not completed here
    stage = _make_stage("jd_extraction", deps=["jd_structure"])

    with pytest.raises(PrerequisiteNotMet) as exc_info:
        single_stage(mock_db, ctx, stage, WORKER_ID)

    assert "jd_structure" in exc_info.value.missing


def test_single_stage_force_bypasses_prerequisites(mock_db):
    """force=True bypasses prerequisite check and tags provenance.forced=True."""
    job = _make_job(mock_db)
    ctx = _make_ctx(job)

    stage = _make_stage("jd_extraction", deps=["jd_structure"])
    stage.dependencies = ["jd_structure"]

    with patch("src.preenrich.dispatcher.send_telegram", side_effect=Exception("no telegram")) if False else MagicMock():
        result = single_stage(mock_db, ctx, stage, WORKER_ID, force=True)

    assert result is not None

    doc = mock_db["level-2"].find_one({"_id": job["_id"]})
    stage_meta = doc["pre_enrichment"]["stages"]["jd_extraction"]
    assert stage_meta["status"] == StageStatus.COMPLETED
    # Provenance forced flag
    assert stage_meta.get("provenance", {}).get("forced") is True


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


def test_single_stage_failure_increments_retry_count(mock_db):
    """Failing stage increments retry_count in Mongo."""
    job = _make_job(mock_db)
    ctx = _make_ctx(job)
    stage = _make_stage("jd_structure", fail=True)

    with pytest.raises(RuntimeError):
        single_stage(mock_db, ctx, stage, WORKER_ID)

    doc = mock_db["level-2"].find_one({"_id": job["_id"]})
    stage_meta = doc["pre_enrichment"]["stages"]["jd_structure"]
    assert stage_meta["retry_count"] == 1
    assert stage_meta["status"] in (StageStatus.FAILED, StageStatus.FAILED_TERMINAL)


def test_single_stage_third_failure_marks_terminal(mock_db):
    """After 3 failures, stage is marked FAILED_TERMINAL."""
    # Existing doc with retry_count=2 (about to hit threshold)
    pre = {
        "stages": {
            "jd_structure": {
                "status": StageStatus.FAILED,
                "retry_count": 2,
                "jd_checksum_at_completion": "sha256:abc123",
                "attempt_token": "differenttoken",
            }
        }
    }
    job = _make_job(mock_db, pre_enrichment=pre)
    ctx = _make_ctx(job)
    stage = _make_stage("jd_structure", fail=True)

    with pytest.raises(RuntimeError):
        single_stage(mock_db, ctx, stage, WORKER_ID)

    doc = mock_db["level-2"].find_one({"_id": job["_id"]})
    stage_meta = doc["pre_enrichment"]["stages"]["jd_structure"]
    assert stage_meta["status"] == StageStatus.FAILED_TERMINAL
    assert stage_meta["retry_count"] == 3


# ---------------------------------------------------------------------------
# Idempotency (S6)
# ---------------------------------------------------------------------------


def test_single_stage_idempotent_on_same_attempt_token(mock_db):
    """
    S6: When Mongo write crashes and worker restarts, re-run produces the same
    attempt_token and the idempotency guard ($ne check) prevents duplicate write.

    We simulate this by pre-populating the stage doc with the token that
    single_stage would generate, then calling single_stage again.
    """
    from src.preenrich.types import attempt_token

    job = _make_job(mock_db)
    ctx = _make_ctx(job)
    stage = _make_stage("jd_structure")

    # Compute the token that single_stage will generate
    token = attempt_token(
        job_id=str(job["_id"]),
        stage="jd_structure",
        jd_checksum="sha256:abc123",
        prompt_version="v1",
        attempt_number=1,
    )

    # Pre-populate the stage as already written (simulates successful prior write)
    mock_db["level-2"].update_one(
        {"_id": job["_id"]},
        {
            "$set": {
                "pre_enrichment.stages.jd_structure": {
                    "status": StageStatus.COMPLETED,
                    "jd_checksum_at_completion": "sha256:abc123",
                    "attempt_token": token,
                }
            }
        },
    )

    # Reload job_doc to include the pre_enrichment state
    job_doc = mock_db["level-2"].find_one({"_id": job["_id"]})
    ctx2 = _make_ctx(job_doc)

    # Re-running should be skipped (already completed at current checksum)
    result = single_stage(mock_db, ctx2, stage, WORKER_ID)
    assert result.skip_reason == "already_completed_at_current_checksum"
    # Stage.run should NOT have been called again
    stage.run.assert_not_called()


# ---------------------------------------------------------------------------
# run_sequence — full sequence (S1)
# ---------------------------------------------------------------------------


def test_run_sequence_all_stages_complete(mock_db):
    """
    S1: All stages complete → summary shows all completed; lifecycle='ready'.

    Uses patch on _DEPENDENCIES to disable prerequisite enforcement for
    the test stages (stage names have no real DAG entries otherwise).
    """
    job = _make_job(mock_db)
    ctx = _make_ctx(job)

    stage1 = _make_stage("jd_structure")
    stage2 = _make_stage("jd_extraction")

    # Patch _DEPENDENCIES so jd_extraction has no deps (isolated test)
    with patch("src.preenrich.dispatcher._DEPENDENCIES", {"jd_structure": [], "jd_extraction": []}):
        summary = run_sequence(mock_db, ctx, [stage1, stage2], WORKER_ID)

    assert "jd_structure" in summary["completed"]
    assert "jd_extraction" in summary["completed"]
    assert summary["failed"] == []

    doc = mock_db["level-2"].find_one({"_id": job["_id"]})
    assert doc["lifecycle"] == "ready"
    assert "ready_at" in doc


def test_run_sequence_stops_on_failure(mock_db):
    """
    S2: Failed stage stops sequence; subsequent stages not run.
    """
    job = _make_job(mock_db)
    ctx = _make_ctx(job)

    stage1 = _make_stage("jd_structure", fail=True)
    stage2 = _make_stage("jd_extraction")

    with patch("src.preenrich.dispatcher._DEPENDENCIES", {"jd_structure": [], "jd_extraction": []}):
        summary = run_sequence(mock_db, ctx, [stage1, stage2], WORKER_ID)

    assert "jd_structure" in summary["failed"]
    # stage2 should NOT have been run
    stage2.run.assert_not_called()
    # Lifecycle should not be "ready"
    doc = mock_db["level-2"].find_one({"_id": job["_id"]})
    assert doc.get("lifecycle") != "ready"


# ---------------------------------------------------------------------------
# shadow_mode — writes to shadow namespace only (§9 Phase 3)
# ---------------------------------------------------------------------------


def test_single_stage_shadow_mode_writes_shadow_namespace(mock_db):
    """
    shadow_mode=True writes to shadow_output and shadow_legacy_fields,
    NOT to live top-level fields.
    """
    job = _make_job(mock_db)
    ctx = _make_ctx(job, shadow_mode=True)
    stage = _make_stage("jd_structure", output={"processed_jd_sections": ["s1"]})

    single_stage(mock_db, ctx, stage, WORKER_ID)

    doc = mock_db["level-2"].find_one({"_id": job["_id"]})

    # Live field should NOT be written
    assert "processed_jd_sections" not in doc

    # Shadow namespace should be written
    stage_meta = doc["pre_enrichment"]["stages"]["jd_structure"]
    assert "shadow_output" in stage_meta
    assert stage_meta["shadow_output"] == {"processed_jd_sections": ["s1"]}

    # shadow_legacy_fields mirrors the output
    assert doc["pre_enrichment"]["shadow_legacy_fields"]["processed_jd_sections"] == ["s1"]


def test_single_stage_live_mode_writes_live_fields(mock_db):
    """
    shadow_mode=False (default) writes to live top-level fields.
    """
    job = _make_job(mock_db)
    ctx = _make_ctx(job, shadow_mode=False)
    stage = _make_stage("jd_structure", output={"processed_jd_sections": ["s1"]})

    single_stage(mock_db, ctx, stage, WORKER_ID)

    doc = mock_db["level-2"].find_one({"_id": job["_id"]})

    # Live field should be written
    assert doc["processed_jd_sections"] == ["s1"]

    # shadow_legacy_fields should NOT be present
    assert "shadow_legacy_fields" not in doc.get("pre_enrichment", {})
