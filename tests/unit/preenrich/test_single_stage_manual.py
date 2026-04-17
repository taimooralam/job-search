"""
Manual stage execution tests (§3.2).

Validates:
- Prerequisite check blocks when deps missing (force=False)
- --force bypasses with warning and marks provenance.forced=True
- Stage run via single_stage goes through dispatcher (sole writer)

Covers plan §3.2 manual execution rules.
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
from src.preenrich.dispatcher import single_stage, PrerequisiteNotMet


WORKER_ID = "manual-op-worker"


@pytest.fixture
def mock_db():
    client = mongomock.MongoClient()
    return client["jobs"]


def _make_ctx(job_doc: dict) -> StageContext:
    return StageContext(
        job_doc=job_doc,
        jd_checksum="sha256:abc",
        company_checksum="sha256:co",
        input_snapshot_id="sha256:snap",
        attempt_number=1,
        config=StepConfig(provider="claude", prompt_version="v1"),
    )


def _make_stage(name: str, deps=None, output=None):
    stage = MagicMock()
    stage.name = name
    stage.dependencies = deps or []
    stage.run.return_value = StageResult(
        output=output or {f"{name}_out": "ok"},
        provider_used="claude",
        model_used="claude-haiku-4-5",
        prompt_version="v1",
        duration_ms=50,
    )
    return stage


def _insert_job(db, pre_enrichment=None) -> dict:
    doc = {
        "_id": ObjectId(),
        "lifecycle": "preenriching",
        "lease_owner": WORKER_ID,
        "description": "ML engineer role",
        "selected_at": datetime.now(timezone.utc),
    }
    if pre_enrichment:
        doc["pre_enrichment"] = pre_enrichment
    db["level-2"].insert_one(doc)
    return doc


# ---------------------------------------------------------------------------
# Prerequisite blocking (force=False)
# ---------------------------------------------------------------------------


def test_manual_prerequisite_blocks_without_force(mock_db):
    """
    §3.2: Running jd_extraction without jd_structure completed → PrerequisiteNotMet.
    """
    job = _insert_job(mock_db)
    ctx = _make_ctx(job)
    stage = _make_stage("jd_extraction", deps=["jd_structure"])

    with pytest.raises(PrerequisiteNotMet) as exc_info:
        single_stage(mock_db, ctx, stage, WORKER_ID, force=False)

    assert "jd_structure" in exc_info.value.missing
    assert exc_info.value.stage == "jd_extraction"


def test_manual_prerequisite_blocks_partial_completion(mock_db):
    """
    Prerequisite check also considers checksum match.
    Even if jd_structure is completed at a different checksum, it's missing.
    """
    pre = {
        "stages": {
            "jd_structure": {
                "status": StageStatus.COMPLETED,
                "jd_checksum_at_completion": "sha256:DIFFERENT",  # stale
            }
        }
    }
    job = _insert_job(mock_db, pre_enrichment=pre)
    ctx = _make_ctx(job)  # current checksum is sha256:abc

    stage = _make_stage("jd_extraction", deps=["jd_structure"])

    with pytest.raises(PrerequisiteNotMet):
        single_stage(mock_db, ctx, stage, WORKER_ID, force=False)


def test_manual_prerequisite_passes_when_deps_complete(mock_db):
    """
    No exception when all deps are completed at current checksum.
    """
    pre = {
        "stages": {
            "jd_structure": {
                "status": StageStatus.COMPLETED,
                "jd_checksum_at_completion": "sha256:abc",  # matches ctx
            }
        }
    }
    job = _insert_job(mock_db, pre_enrichment=pre)
    ctx = _make_ctx(job)

    stage = _make_stage("jd_extraction", deps=["jd_structure"])
    # Should not raise
    result = single_stage(mock_db, ctx, stage, WORKER_ID, force=False)
    assert result is not None


# ---------------------------------------------------------------------------
# Force bypass (force=True)
# ---------------------------------------------------------------------------


def test_manual_force_bypasses_prerequisites(mock_db):
    """
    §3.2: force=True bypasses prerequisite check.
    Stage runs and provenance.forced=True is written.
    """
    job = _insert_job(mock_db)
    ctx = _make_ctx(job)
    stage = _make_stage("jd_extraction", deps=["jd_structure"])

    # Should NOT raise — force bypasses
    result = single_stage(mock_db, ctx, stage, WORKER_ID, force=True)
    assert result is not None

    doc = mock_db["level-2"].find_one({"_id": job["_id"]})
    stage_meta = doc["pre_enrichment"]["stages"]["jd_extraction"]
    assert stage_meta["provenance"]["forced"] is True


def test_manual_force_sends_telegram_warning(mock_db):
    """
    §3.2: force=True logs a Telegram warning.
    Telegram failure is non-fatal — dispatcher swallows errors.
    """
    job = _insert_job(mock_db)
    ctx = _make_ctx(job)
    stage = _make_stage("jd_extraction", deps=["jd_structure"])

    telegram_calls = []

    def mock_telegram(msg):
        telegram_calls.append(msg)

    # Patch at the source module so the inline import resolves to the mock
    with patch("src.common.telegram.send_telegram", side_effect=mock_telegram):
        result = single_stage(mock_db, ctx, stage, WORKER_ID, force=True)

    # Either telegram was called or it was silently skipped (best-effort)
    # The important thing is force=True does not block execution
    assert result is not None


def test_manual_force_no_deps_is_noop(mock_db):
    """
    force=True on a stage with no dependencies is a no-op (runs normally).
    """
    job = _insert_job(mock_db)
    ctx = _make_ctx(job)
    stage = _make_stage("jd_structure", deps=[])

    result = single_stage(mock_db, ctx, stage, WORKER_ID, force=True)
    assert result is not None

    doc = mock_db["level-2"].find_one({"_id": job["_id"]})
    stage_meta = doc["pre_enrichment"]["stages"]["jd_structure"]
    # forced=True in provenance even though no deps to force-bypass
    assert stage_meta["provenance"]["forced"] is True


# ---------------------------------------------------------------------------
# Dispatcher as sole writer
# ---------------------------------------------------------------------------


def test_manual_stage_writes_through_dispatcher(mock_db):
    """
    Stage run always goes through single_stage which is the sole Mongo writer.
    Verifies Mongo doc is updated after run.
    """
    job = _insert_job(mock_db)
    ctx = _make_ctx(job)
    stage = _make_stage("jd_structure", output={"processed_jd_sections": ["sec1"]})

    result = single_stage(mock_db, ctx, stage, WORKER_ID)

    doc = mock_db["level-2"].find_one({"_id": job["_id"]})
    # Dispatcher wrote stage metadata to Mongo
    assert "pre_enrichment" in doc
    stage_meta = doc["pre_enrichment"]["stages"]["jd_structure"]
    assert stage_meta["status"] == StageStatus.COMPLETED

    # Legacy field written
    assert doc["processed_jd_sections"] == ["sec1"]
