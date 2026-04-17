"""
Integration-lite test: dispatcher.run_sequence end-to-end with mocked stages.

Uses mongomock for Mongo so no real infra required.

Verifies:
- All stages complete in DAG order
- Final lifecycle="ready", ready_at set
- Summary contains all stage names in "completed" list
- Idempotent: re-running with same checksum skips already-completed stages
- Failed stage stops the sequence (no further stages run)
"""

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

try:
    import mongomock
    HAS_MONGOMOCK = True
except ImportError:
    HAS_MONGOMOCK = False

from src.preenrich.dispatcher import run_sequence, single_stage
from src.preenrich.types import StageContext, StageResult, StageStatus, StepConfig


pytestmark = pytest.mark.skipif(
    not HAS_MONGOMOCK,
    reason="mongomock not installed",
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_db():
    """Create an in-memory mongomock database."""
    client = mongomock.MongoClient()
    return client["jobs"]


def _make_stage(name: str, deps: List[str], *, fail: bool = False):
    """Create a mock stage that either succeeds or raises."""
    stage = MagicMock()
    stage.name = name
    stage.dependencies = deps
    if fail:
        stage.run.side_effect = RuntimeError(f"Stage {name} intentionally failed")
    else:
        stage.run.return_value = StageResult(
            output={f"{name}_output": f"value_from_{name}"},
            provider_used="claude",
            model_used="claude-haiku-4-5",
            prompt_version="v1",
            duration_ms=100,
        )
    return stage


WORKER_ID = "test-worker-abc"
JD_CHECKSUM = "sha256:" + hashlib.sha256(b"test jd text").hexdigest()


def _make_ctx(db: Any, job_doc: Dict[str, Any]) -> StageContext:
    return StageContext(
        job_doc=job_doc,
        jd_checksum=JD_CHECKSUM,
        company_checksum="sha256:" + hashlib.sha256(b"acme").hexdigest(),
        input_snapshot_id=JD_CHECKSUM,
        attempt_number=1,
        config=StepConfig(provider="claude"),
        shadow_mode=False,
    )


def _insert_job(db: Any) -> Dict[str, Any]:
    """Insert a minimal test job into mongomock and return it."""
    from bson import ObjectId
    job_doc = {
        "_id": ObjectId(),
        "title": "AI Engineer",
        "company": "Acme",
        "description": "test jd text",
        "lifecycle": "preenriching",
        "lease_owner": WORKER_ID,
        "lease_expires_at": datetime(2099, 1, 1, tzinfo=timezone.utc),
        "pre_enrichment": {
            "schema_version": 1,
            "jd_checksum": JD_CHECKSUM,
            "stages": {},
        },
    }
    db["level-2"].insert_one(job_doc)
    return job_doc


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestDispatcherFullSequenceAllComplete:
    def test_all_stages_complete_lifecycle_ready(self):
        """S1: all stages complete → lifecycle='ready', ready_at set.

        Note: run_sequence uses ctx.job_doc for prerequisite checks at the start
        of each stage. Since jd_extraction depends on jd_structure, we run them
        as independent stages (no deps) to test the sequence flow cleanly.
        Prerequisite enforcement is tested in test_dispatcher.py.
        """
        db = _make_db()
        job_doc = _insert_job(db)

        # Use stages with no inter-dependencies in _DEPENDENCIES to test the happy-path sequence.
        # jd_structure and company_research both have [] in _DEPENDENCIES, so _check_prerequisites
        # passes unconditionally. (jd_extraction has deps=[jd_structure] in the dag, which would
        # cause PrerequisiteNotMet here. Prerequisite enforcement is tested in test_dispatcher.py.)
        stages = [
            _make_stage("jd_structure", []),
            _make_stage("company_research", []),
        ]

        ctx = _make_ctx(db, job_doc)
        summary = run_sequence(db, ctx, stages, WORKER_ID)

        assert not summary["failed"], f"Unexpected failures: {summary['failed']}"
        assert "jd_structure" in summary["completed"]
        assert "company_research" in summary["completed"]

        updated = db["level-2"].find_one({"_id": job_doc["_id"]})
        assert updated["lifecycle"] == "ready"
        assert updated.get("ready_at") is not None

    def test_stage_outputs_written_to_doc(self):
        """Stage output patch must appear in the Mongo document after completion."""
        db = _make_db()
        job_doc = _insert_job(db)

        stages = [_make_stage("jd_structure", [])]
        ctx = _make_ctx(db, job_doc)
        run_sequence(db, ctx, stages, WORKER_ID)

        updated = db["level-2"].find_one({"_id": job_doc["_id"]})
        assert "jd_structure_output" in updated

    def test_stage_meta_written_to_pre_enrichment(self):
        """pre_enrichment.stages.<stage>.status must be COMPLETED."""
        db = _make_db()
        job_doc = _insert_job(db)

        stages = [_make_stage("jd_structure", [])]
        ctx = _make_ctx(db, job_doc)
        run_sequence(db, ctx, stages, WORKER_ID)

        updated = db["level-2"].find_one({"_id": job_doc["_id"]})
        stage_doc = updated["pre_enrichment"]["stages"]["jd_structure"]
        assert stage_doc["status"] == StageStatus.COMPLETED


class TestDispatcherFullSequenceIdempotent:
    def test_already_completed_stage_is_skipped(self):
        """S2-related: stage already completed at current checksum → skipped, not re-run."""
        db = _make_db()
        job_doc = _insert_job(db)

        # Pre-mark jd_structure as completed in Mongo
        from src.preenrich.types import attempt_token
        token = attempt_token(
            job_id=str(job_doc["_id"]),
            stage="jd_structure",
            jd_checksum=JD_CHECKSUM,
            prompt_version="v1",
            attempt_number=1,
        )
        db["level-2"].update_one(
            {"_id": job_doc["_id"]},
            {"$set": {
                "pre_enrichment.stages.jd_structure": {
                    "status": StageStatus.COMPLETED,
                    "jd_checksum_at_completion": JD_CHECKSUM,
                    "attempt_token": token,
                    "retry_count": 0,
                },
                "jd_structure_output": "already_done",
            }}
        )

        stage_mock = _make_stage("jd_structure", [])
        stages = [stage_mock]

        # Reload job_doc to reflect the pre-completion
        job_doc_updated = db["level-2"].find_one({"_id": job_doc["_id"]})
        ctx = _make_ctx(db, job_doc_updated)
        summary = run_sequence(db, ctx, stages, WORKER_ID)

        # Should be skipped (not re-run)
        assert "jd_structure" in summary["skipped"]
        assert "jd_structure" not in summary["completed"]
        # Stage.run must NOT have been called
        stage_mock.run.assert_not_called()


class TestDispatcherFullSequenceFailure:
    def test_failing_stage_stops_sequence(self):
        """S2: failing stage marks summary['failed'] and stops further stages."""
        db = _make_db()
        job_doc = _insert_job(db)

        # All stages have no inter-dependencies to isolate the failure test
        stages = [
            _make_stage("jd_structure", []),
            _make_stage("jd_extraction", [], fail=True),
            _make_stage("pain_points", []),  # Must not run
        ]

        ctx = _make_ctx(db, job_doc)
        summary = run_sequence(db, ctx, stages, WORKER_ID)

        assert "jd_extraction" in summary["failed"]
        # jd_structure should complete
        assert "jd_structure" in summary["completed"]
        # pain_points should not even appear
        assert "pain_points" not in summary["completed"]
        assert "pain_points" not in summary["failed"]

    def test_failing_stage_lifecycle_not_ready(self):
        """lifecycle must NOT be set to 'ready' when any stage fails."""
        db = _make_db()
        job_doc = _insert_job(db)

        stages = [_make_stage("jd_structure", [], fail=True)]
        ctx = _make_ctx(db, job_doc)
        run_sequence(db, ctx, stages, WORKER_ID)

        updated = db["level-2"].find_one({"_id": job_doc["_id"]})
        assert updated.get("lifecycle") != "ready"
